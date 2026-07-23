from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class ProcessingInfo(BaseModel):
    pipeline_used: str = Field(description="Pipeline type: 'native', 'ocr', 'hybrid'")
    ocr_engine: Optional[str] = Field(default=None, description="OCR engine used, e.g. 'ocrmac'")
    model: str = Field(description="LLM/VLM model used for extraction")
    duration_seconds: Optional[float] = Field(default=None, description="Total processing time in seconds")

class DocumentInfo(BaseModel):
    source_file: str = Field(description="Original filename")
    page_count: int = Field(description="Number of pages")
    document_type: str = Field(description="Detected document type, e.g. 'invoice', 'report', 'form', 'letter', 'contract', 'other'")
    language: str = Field(default="en", description="Primary language ISO code")
    processing: ProcessingInfo

class Metadata(BaseModel):
    title: Optional[str] = Field(default=None, description="Document title if found")
    date: Optional[str] = Field(default=None, description="Document date if found (ISO format preferred)")
    parties: list[str] = Field(default_factory=list, description="Organizations or people mentioned as parties")
    reference_numbers: list[str] = Field(default_factory=list, description="Reference/invoice/contract numbers")

class KeyValue(BaseModel):
    key: str = Field(description="Field name/label")
    value: str = Field(description="Field value")
    confidence: Optional[float] = Field(default=None, description="Extraction confidence 0.0-1.0")

class Table(BaseModel):
    caption: Optional[str] = Field(default=None, description="Table caption/title if found")
    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[list[str]] = Field(default_factory=list, description="Table rows, each row is a list of cell values")

class Entity(BaseModel):
    type: str = Field(description="Entity type: 'person', 'organization', 'date', 'amount', 'address', 'email', 'phone', 'other'")
    value: str = Field(description="Entity value")

class DocumentAnalysis(BaseModel):
    document: DocumentInfo
    metadata: Metadata = Field(default_factory=Metadata)
    summary: str = Field(default="", description="Brief document summary")
    key_values: list[KeyValue] = Field(default_factory=list, description="Extracted key-value pairs")
    tables: list[Table] = Field(default_factory=list, description="Extracted tables")
    entities: list[Entity] = Field(default_factory=list, description="Named entities")
    raw_text_markdown: str = Field(default="", description="Full document text in Markdown format")


def get_json_schema() -> dict:
    return DocumentAnalysis.model_json_schema()


def get_extraction_schema() -> dict:
    schema = DocumentAnalysis.model_json_schema()
    return schema
