from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..tools.builtin import DEFAULT_SYSTEM_PROMPT

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(0.9, gt=0.0, le=1.0)


@router.post("")
def chat(req: ChatRequest) -> Dict[str, Any]:
    from ..config import get_settings
    from ..llm import get_engine

    settings = get_settings()
    messages: List[Dict[str, str]] = [m.model_dump() for m in req.messages if m.role != "system"]
    if not any(m["role"] == "system" for m in req.messages):
        messages.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})
    engine = get_engine(settings)
    try:
        response = engine.chat(
            messages,
            tools=True,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    choice = response["choices"][0]
    message = choice.get("message", {})
    return {
        "content": message.get("content") or "",
        "tool_calls": [
            {
                "name": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments"),
            }
            for tc in message.get("tool_calls") or []
        ],
        "usage": response.get("usage"),
        "model": "local-qwen3-0.6b",
    }