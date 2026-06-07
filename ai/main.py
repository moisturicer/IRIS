from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(
    title="IRIS AI Gateway",
    description="FastAPI async gateway for LLM and Vector Search in IRIS",
    version="1.0.0"
)

# Setup CORS
cors_origins = os.getenv("CORS_ORIGINS", '["http://localhost:5173"]').strip("[]").replace('"', '').split(", ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Healthcheck endpoint for Docker Compose."""
    return {"status": "healthy", "service": "ai-gateway"}

@app.get("/")
async def root():
    return {"message": "Welcome to IRIS AI Gateway"}

from ai.routes.chat import router as chat_router

app.include_router(chat_router, prefix="/api/v1/ai", tags=["ai"])
