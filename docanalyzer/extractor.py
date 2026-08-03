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


def extract_document_chunked_streaming(
    source_file: str,
    page_count: int,
    pipeline_used: str,
    markdown_content: str,
    vlm_results: dict[int, str] | None = None,
    fast_model: str = "phi4-mini",
    deep_model: str = "qwen2.5:latest",
    ocr_engine: str | None = None,
    on_token: callable | None = None,
    on_phase_start: callable | None = None,
    on_phase_end: callable | None = None,
) -> DocumentAnalysis:
    vlm_section = _build_vlm_section(vlm_results)
    total_start = time.time()
    
    phase1_label = f"Metadata & Key-Values [{fast_model}]"
    if on_phase_start:
        on_phase_start(1, phase1_label)
    
    p1_prompt = PHASE1_PROMPT.format(
        source_file=source_file,
        page_count=page_count,
        pipeline_used=pipeline_used,
        markdown_content=markdown_content,
        vlm_section=vlm_section,
    )
    
    p1_start = time.time()
    p1_tokens = []
    for token in _stream_ollama_chat(fast_model, p1_prompt):
        p1_tokens.append(token)
        if on_token:
            on_token(token, 1)
    p1_raw = "".join(p1_tokens)
    p1_duration = time.time() - p1_start
    
    if on_phase_end:
        on_phase_end(1, phase1_label, p1_duration)
    
    phase2_label = f"Tables [{deep_model}]"
    if on_phase_start:
        on_phase_start(2, phase2_label)
    
    p2_prompt = PHASE2_PROMPT.format(markdown_content=markdown_content)
    
    p2_start = time.time()
    p2_tokens = []
    for token in _stream_ollama_chat(deep_model, p2_prompt):
        p2_tokens.append(token)
        if on_token:
            on_token(token, 2)
    p2_raw = "".join(p2_tokens)
    p2_duration = time.time() - p2_start
    
    if on_phase_end:
        on_phase_end(2, phase2_label, p2_duration)
    
    phase3_label = f"Entities [{deep_model}]"
    if on_phase_start:
        on_phase_start(3, phase3_label)
    
    p3_prompt = PHASE3_PROMPT.format(markdown_content=markdown_content)
    
    p3_start = time.time()
    p3_tokens = []
    for token in _stream_ollama_chat(deep_model, p3_prompt):
        p3_tokens.append(token)
        if on_token:
            on_token(token, 3)
    p3_raw = "".join(p3_tokens)
    p3_duration = time.time() - p3_start
    
    if on_phase_end:
        on_phase_end(3, phase3_label, p3_duration)
    
    total_duration = time.time() - total_start
    
    p1_json = json.loads(_clean_json_text(p1_raw))
    p2_json = json.loads(_clean_json_text(p2_raw))
    p3_json = json.loads(_clean_json_text(p3_raw))
    
    combined = {
        "document": {
            "source_file": source_file,
            "page_count": page_count,
            "document_type": p1_json.get("document_type", "other"),
            "language": p1_json.get("language", "en"),
            "processing": {
                "pipeline_used": pipeline_used,
                "model": f"{fast_model} + {deep_model}",
                "duration_seconds": round(total_duration, 2),
            },
        },
        "metadata": {
            "title": str(p1_json.get("title")) if p1_json.get("title") else None,
            "date": str(p1_json.get("date")) if p1_json.get("date") else None,
            "parties": [
                p["name"] if isinstance(p, dict) and "name" in p else str(p)
                for p in p1_json.get("parties", [])
            ],
            "reference_numbers": [str(r) for r in p1_json.get("reference_numbers", [])],
        },
        "summary": p1_json.get("summary", ""),
        "key_values": [
            {
                **kv, 
                "value": ", ".join(kv.get("value")) if isinstance(kv.get("value"), list) else str(kv.get("value") or "")
            }
            for kv in p1_json.get("key_values", [])
        ],
        "tables": p2_json.get("tables", []),
        "entities": p3_json.get("entities", []),
        "raw_text_markdown": markdown_content,
    }
    
    if ocr_engine:
        combined["document"]["processing"]["ocr_engine"] = ocr_engine
    
    result = DocumentAnalysis.model_validate(combined)
    logger.info(f"Chunked extraction complete in {total_duration:.1f}s (P1={p1_duration:.1f}s P2={p2_duration:.1f}s P3={p3_duration:.1f}s)")
    return result


def extract_document_json(
    source_file: str,
    page_count: int,
    pipeline_used: str,
    markdown_content: str,
    vlm_results: dict[int, str] | None = None,
    model: str = "qwen3.5",
    ocr_engine: str | None = None,
    max_retries: int = 3,
) -> DocumentAnalysis:
    vlm_section = _build_vlm_section(vlm_results)
    schema = get_extraction_schema()
    
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        source_file=source_file,
        page_count=page_count,
        pipeline_used=pipeline_used,
        markdown_content=markdown_content,
        vlm_section=vlm_section,
        json_schema=json.dumps(schema, indent=2),
    )
    
    last_error = None
    for attempt in range(1, max_retries + 1):
        logger.info(f"Extraction attempt {attempt}/{max_retries} with {model}...")
        
        try:
            start_time = time.time()
            raw_content = _call_ollama_chat_blocking(model, prompt)
            duration = time.time() - start_time
            logger.info(f"LLM response received in {duration:.1f}s")
            logger.info(f"RAW response length: {len(raw_content)} chars")
            logger.debug(f"RAW response (first 500): {raw_content[:500]}")
            
            if not raw_content.strip():
                last_error = "Model returned empty response"
                logger.warning(f"Attempt {attempt} failed: {last_error}")
                continue
            
            raw_text = _clean_json_text(raw_content)
            raw_json = json.loads(raw_text)
            
            if "document" not in raw_json:
                raw_json["document"] = {}
            
            doc_info = raw_json["document"]
            doc_info["source_file"] = source_file
            doc_info["page_count"] = page_count
            
            if "processing" not in doc_info:
                doc_info["processing"] = {}
            
            proc = doc_info["processing"]
            proc["pipeline_used"] = pipeline_used
            proc["model"] = model
            proc["duration_seconds"] = round(duration, 2)
            if ocr_engine:
                proc["ocr_engine"] = ocr_engine
            
            result = DocumentAnalysis.model_validate(raw_json)
            result.raw_text_markdown = markdown_content
            logger.info("Extraction successful — Pydantic validation passed")
            return result
            
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning(f"Attempt {attempt} failed: {last_error}")
        except ValidationError as e:
            last_error = f"Pydantic validation error: {e}"
            logger.warning(f"Attempt {attempt} failed: {last_error}")
        except httpx.HTTPStatusError as e:
            last_error = f"Ollama API error: {e.response.status_code} - {e.response.text[:200]}"
            logger.error(f"Attempt {attempt} failed: {last_error}")
        except httpx.TimeoutException as e:
            last_error = f"Ollama API timeout: {e}"
            logger.error(f"Attempt {attempt} failed: {last_error}")
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            logger.error(f"Attempt {attempt} failed: {last_error}")
            raise
    
    raise RuntimeError(
        f"Extraction failed after {max_retries} attempts. Last error: {last_error}"
    )
def _extract_phase3_entities(markdown: str, model: str = "qwen2.5:latest", max_retries: int = 2) -> list[Entity]:
    return []

def extract_document_json(source_file: str, page_count: int, pipeline_used: str, markdown_content: str, vlm_results: dict | None = None, model: str = "phi4-mini", deep_model: str = "qwen2.5:latest", ocr_engine: str | None = None) -> DocumentAnalysis:
    phase1 = _extract_phase1_metadata(markdown_content, model=model)
    tables = _extract_phase2_tables(markdown_content, model=deep_model)
    return DocumentAnalysis(
        document=DocumentInfo(source_file=source_file, page_count=page_count, document_type=phase1.document_type, language=phase1.language, processing=ProcessingInfo(pipeline_used=pipeline_used, ocr_engine=ocr_engine, model=f"{model}+{deep_model}", duration_seconds=0.0)),
        metadata=phase1.metadata,
        summary=phase1.summary,
        key_values=phase1.key_values,
        tables=tables,
        entities=[],
        raw_text_markdown=markdown_content
    )
