"""Wire shapes for the AI gateway.

**No Django here.** This is a standalone FastAPI service with its own
`requirements.txt`, and Django is not in it -- these three lines

    from django.db.models.enums import StrEnum
    from django.db.models import TextChoices

made the module unimportable, which is one of the reasons `ai-gateway` never
booted (IR-156). A gateway that imports Django would also quietly re-open
ADR-014's precondition 4, since the next step from `TextChoices` is a model,
and a model is a second path to the database that Django is supposed to own.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union  # noqa: F401  (used by schemas below)

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class DOCUMENT_STATUS(str, Enum):
    """Plain enum, not django TextChoices -- see the module docstring."""

    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    FAILED = "failed"


# --- the chat/embed contract -------------------------------------------------
# `api/chat.py` has always imported these four; they were never defined, so the
# router failed at import even once the service layer existed (IR-156).

class AskRequest(BaseModel):
    """A question put to the gateway by Django -- never by a browser."""

    query: str = Field(min_length=1)


class AskResponse(BaseModel):
    query: str
    answer: str
    #: Empty until retrieval moves behind the gateway. It stays in the shape
    #: because an answer without its sources is the thing ADR-008 forbids, and
    #: a caller should never have to guess whether the field will appear.
    sources: List[str] = []


class EmbedRequest(BaseModel):
    record_id: str
    text: str = Field(min_length=1)


class EmbedResponse(BaseModel):
    record_id: str
    dimensions: int
    success: bool


class DocumentResponse(BaseModel):
    id: str
    filename: str
    status: str = DOCUMENT_STATUS.PENDING.value
    content_type: str 
    file_size: int = 0
    page_count: int = 0
    created_at: datetime

class ChunkBboxResponse(BaseModel):
    page: int
    bbox: List[float]

class ChunkDocItemResponse(BaseModel):
    self_ref: str
    label: str

class DocChunkResponse(BaseModel):
    """Canonical doc chunk — wire shape consumed by features/chunks on the front."""
    id: str
    doc_id: str
    sequence: int
    text: str
    headings: List[str] = []
    source_page: int
    token_count: int
    bboxes: List[ChunkBboxResponse] = []
    doc_items: List[ChunkDocItemResponse] = []
    created_at: datetime
    updated_at: datetime

class SearchResultItem(BaseModel):
    """A single search result with content and metadata."""
    doc_id: str
    filename: str
    content: str
    chunk_index: int
    page_number: int
    score: float
    headings: List[str] = []
    highlights: List[str] = []

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]

class PipelineOptionsRequest(BaseModel):
    """Docling pipeline configuration options."""
    model_config = ConfigDict(populate_by_name=True)

    do_ocr: bool = Field(default=True, validation_alias=AliasChoices("do_ocr", "doOcr"))
    do_table_structure: bool = Field(default=True, validation_alias=AliasChoices("do_table_structure", "doTableStructure"))
    table_mode: str = Field(default="accurate", validation_alias=AliasChoices("table_mode", "tableMode"))
    do_code_enrichment: bool = Field(default=False, validation_alias=AliasChoices("do_code_enrichment", "doCodeEnrichment"))
    do_formula_enrichment: bool = Field(default=False, validation_alias=AliasChoices("do_formula_enrichment", "doFormulaEnrichment"))
    do_picture_classification: bool = Field(default=False, validation_alias=AliasChoices("do_picture_classification", "doPictureClassification"))
    do_picture_description: bool = Field(default=False, validation_alias=AliasChoices("do_picture_description", "doPictureDescription"))
    generate_picture_images: bool = Field(default=False, validation_alias=AliasChoices("generate_picture_images", "generatePictureImages"))
    generate_page_images: bool = Field(default=False, validation_alias=AliasChoices("generate_page_images", "generatePageImages"))
    images_scale: float = Field(default=1.0, validation_alias=AliasChoices("images_scale", "imagesScale"))

    @field_validator("table_mode")
    @classmethod
    def validate_table_mode(cls, v: str) -> str:
        if v not in ("accurate", "fast"):
            raise ValueError('table_mode must be "accurate" or "fast"')
        return v

    @field_validator("images_scale")
    @classmethod
    def validate_images_scale(cls, v: float) -> float:
        if v <= 0 or v > 10:
            raise ValueError("images_scale must be between 0 (exclusive) and 10")
        return v

class ChunkingOptionsRequest(BaseModel):
    """Docling chunking configuration options."""
    model_config = ConfigDict(populate_by_name=True)

    chunker_type: str = Field(default="hybrid", validation_alias=AliasChoices("chunker_type", "chunkerType"))
    max_tokens: int = Field(default=512, validation_alias=AliasChoices("max_tokens", "maxTokens"))
    merge_peers: bool = Field(default=True, validation_alias=AliasChoices("merge_peers", "mergePeers"))
    repeat_table_header: bool = Field(default=True, validation_alias=AliasChoices("repeat_table_header", "repeatTableHeader"))

    @field_validator("chunker_type")
    @classmethod
    def validate_chunker_type(cls, v: str) -> str:
        if v not in ("hybrid", "hierarchical"):
            raise ValueError('chunker_type must be "hybrid" or "hierarchical"')
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v < 64 or v > 8192:
            raise ValueError("max_tokens must be between 64 and 8192")
        return v


