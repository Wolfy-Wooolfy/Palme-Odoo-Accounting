from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]
    result_summary: Optional[str] = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    tool_calls: list[ToolCall] = []


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    company_id: Optional[int] = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCall] = []
