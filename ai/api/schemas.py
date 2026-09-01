from django.db.models.enums import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator, AliasChoices
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from django.db.models import TextChoices

class DOCUMENT_STATUS(TextChoices):
    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    FAILED = "failed"


class DocumentResponse(BaseModel):
    id: str
    filename: str
    status: str = DOCUMENT_STATUS.PENDING
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


