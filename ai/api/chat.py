from fastapi import APIRouter, Depends, HTTPException
from ai.api.schemas import AskRequest, AskResponse, EmbedRequest, EmbedResponse
from ai.domain.ports import LLMProvider, EmbeddingProvider
from ai.infrastructure.dependencies import get_llm_provider, get_embedding_provider
from ai.services.chat_service import ChatService
from ai.services.embedding_service import EmbeddingService

router = APIRouter()

@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest, 
    llm: LLMProvider = Depends(get_llm_provider)
):
    try:
        chat_service = ChatService(llm)
        answer = await chat_service.ask_question(request.query)
        
        return AskResponse(
            query=request.query,
            answer=answer,
            sources=[] # To be populated by vector search later
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embed", response_model=EmbedResponse)
async def create_embedding(
    request: EmbedRequest,
    embedder: EmbeddingProvider = Depends(get_embedding_provider)
):
    try:
        embedding_service = EmbeddingService(embedder)
        vector = await embedding_service.create_embedding(request.text)
        
        return EmbedResponse(
            record_id=request.record_id,
            dimensions=len(vector),
            success=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
