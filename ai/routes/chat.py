from fastapi import APIRouter, Depends, HTTPException
from ai.models.schemas import AskRequest, AskResponse, EmbedRequest, EmbedResponse
from ai.services.interfaces import LLMProvider, EmbeddingProvider
from ai.core.dependencies import get_llm_provider, get_embedding_provider

router = APIRouter()

@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest, 
    llm: LLMProvider = Depends(get_llm_provider)
):
    try:
        # Currently a placeholder context until we integrate with vector search
        context = "The IRIS repository contains research papers."
        
        answer = await llm.generate_response(prompt=request.query, context=context)
        
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
        vector = await embedder.generate_embedding(request.text)
        
        return EmbedResponse(
            record_id=request.record_id,
            dimensions=len(vector),
            success=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
