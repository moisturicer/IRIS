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

from pydantic import BaseModel, Field


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
