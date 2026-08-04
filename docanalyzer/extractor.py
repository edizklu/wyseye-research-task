from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Generator

import httpx
from pydantic import ValidationError

from .schema import DocumentAnalysis, get_extraction_schema

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"

PHASE1_PROMPT = """You are a document analysis expert. Extract metadata from this document.

Source: {source_file} | Pages: {page_count} | Pipeline: {pipeline_used}

{markdown_content}

{vlm_section}

Return a JSON object with EXACTLY these fields and formats:
- "document_type": one of invoice, report, form, letter, contract, receipt, other
- "language": ISO language code (e.g. "en")
- "title": document title string or null
- "date": document date string or null
- "parties": list of PLAIN STRINGS — each party name only, e.g. ["ACME Corp", "John Smith"]
- "reference_numbers": list of PLAIN STRINGS — each number only, e.g. ["INV-001", "PO-123"]
- "summary": concise 1-2 sentence summary string
- "key_values": list of objects, each with {{"key": "...", "value": "...", "confidence": 0.0-1.0}}

CRITICAL RULES for key_values:
- Extract EACH labeled field as a SEPARATE key-value pair
- Include: invoice numbers, dates, totals, subtotals, tax, discount, due dates, payment terms, addresses
- "value" MUST be a simple string, NEVER a list or object
- Example: {{"key": "Subtotal", "value": "$24,000.00", "confidence": 1.0}}

Confidence: 1.0 = clearly visible, 0.8 = interpreted, 0.5 = moderate, 0.3 = low.
Respond with ONLY valid JSON. No explanation, no markdown.
/no_think"""

PHASE2_PROMPT = """Extract ALL tables from this document content as JSON.

{markdown_content}

Return a JSON object with exactly one field:
- "tables": list of table objects, each with:
  - "caption": table caption/title or null
  - "headers": list of column header strings
  - "rows": list of rows, each row is a list of cell value strings

Convert ALL cell values to strings. Include every table you find.
Respond with ONLY valid JSON. No explanation.
/no_think"""

PHASE3_PROMPT = """Extract named entities from this document content as JSON.

{markdown_content}

Return a JSON object with exactly one field:
- "entities": list of entity objects, each with:
  - "type": one of person, organization, date, amount, address, email, phone, other
  - "value": the entity value string

Find ALL people, organizations, dates, monetary amounts, addresses, emails, and phone numbers.
Respond with ONLY valid JSON. No explanation.
/no_think"""

EXTRACTION_PROMPT_TEMPLATE = """You are a document analysis expert. Analyze the following document content and extract structured information.

Document source: {source_file}
Total pages: {page_count}
Pipeline used: {pipeline_used}

## Document Content (Markdown)

{markdown_content}

{vlm_section}

## Instructions

Extract ALL information from the document into the JSON schema. Be thorough:

1. **document_type**: Classify as one of: invoice, report, form, letter, contract, receipt, other
2. **metadata**: Extract title, date, parties, reference numbers
3. **summary**: Write a concise 1-2 sentence summary
4. **key_values**: Extract ALL labeled fields (e.g., "Invoice Number", "Total Amount", "Date", etc.)
5. **tables**: Include ALL tables with their headers and rows. Convert all cell values to strings.
6. **entities**: Extract named entities (people, organizations, dates, amounts, addresses, emails, phones)

Do NOT include the raw_text_markdown field — it will be added automatically.

For confidence scores on key_values, use:
- 1.0: Clearly visible and unambiguous
- 0.8: High confidence but some interpretation needed
- 0.5: Moderate confidence
- 0.3: Low confidence / partially visible

Respond with ONLY the JSON object matching the provided schema. Do not include any explanation or markdown formatting around the JSON.
/no_think

## Target JSON Schema
{json_schema}
"""


def _build_vlm_section(vlm_results: dict[int, str] | None) -> str:
    if not vlm_results:
        return ""
    
    sections = ["## Visual Analysis (from VLM page scans)\n"]
    for page_num in sorted(vlm_results.keys()):
        sections.append(f"### Page {page_num} (VLM Analysis)\n{vlm_results[page_num]}\n")
    
    return "\n".join(sections)


def _clean_json_text(raw: str) -> str:
    raw_text = raw.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text.split("```json", 1)[1]
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```", 1)[1]
    if raw_text.endswith("```"):
        raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()
    
    if not raw_text.startswith("{"):
        idx = raw_text.find("{")
        if idx >= 0:
            raw_text = raw_text[idx:]
            depth = 0
            end_idx = -1
            for i, ch in enumerate(raw_text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            if end_idx > 0:
                raw_text = raw_text[:end_idx + 1]
    
    return raw_text


def _stream_ollama_chat(
    model: str,
    prompt: str,
    timeout: float = 600.0,
) -> Generator[str, None, None]:
    messages = [
        {
            "role": "system",
            "content": "You are a JSON extraction engine. Output ONLY valid JSON. No explanations, no markdown, no thinking — pure JSON only."
        },
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,
        "format": "json",
        "options": {"num_ctx": 4096, "num_predict": 4096, "num_batch": 1024},
    }
    
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                except json.JSONDecodeError:
                    continue


def _call_ollama_chat_blocking(model: str, prompt: str, timeout: float = 600.0) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a JSON extraction engine. Output ONLY valid JSON. No explanations, no markdown, no thinking — pure JSON only."
        },
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"num_ctx": 4096, "num_predict": 4096, "num_batch": 1024},
    }
    
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
    
    data = resp.json()
    return data.get("message", {}).get("content", "")


