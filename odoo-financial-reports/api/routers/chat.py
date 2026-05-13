from fastapi import APIRouter, Depends, HTTPException

from api.config import settings
from api.deps import get_odoo_client
from api.models.chat import ChatRequest, ChatResponse
from api.services import ai_assistant

router = APIRouter(tags=["ai-chat"])


@router.get("/chat/status")
def chat_status():
    return {
        "available": bool(settings.openai_api_key),
        "model": settings.openai_model if settings.openai_api_key else None,
    }


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, client=Depends(get_odoo_client)):
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI assistant is not configured. Set OPENAI_API_KEY in .env",
        )
    try:
        return ai_assistant.chat(request, client)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
