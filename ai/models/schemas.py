from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class EmbedRequest(BaseModel):
    record_id: int
    text: str

class EmbedResponse(BaseModel):
    record_id: int
    dimensions: int
    success: bool
    error: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[Dict[str, Any]] = None

class SearchResult(BaseModel):
    record_id: int
    title: str
    abstract: str
    score: float

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]

class AskRequest(BaseModel):
    query: str
    top_k: int = 5
    # Add history or context later if needed

class AskResponse(BaseModel):
    query: str
    answer: str
    sources: List[SearchResult]
