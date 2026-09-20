import json
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import get_settings

router = APIRouter(tags=["reasoning"])


class ReasoningMessage(BaseModel):
    role: str
    content: str


class ReasoningRequest(BaseModel):
    message: Optional[str] = None
    messages: Optional[List[ReasoningMessage]] = None
    system: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = Field(2048, ge=1, le=32768)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    stream: bool = False
    include_reasoning: bool = True

    def build_messages(self) -> List[Dict[str, str]]:
        msgs = [m.model_dump() for m in self.messages] if self.messages else []
        if not msgs:
            if not self.message:
                raise HTTPException(status_code=400, detail="either message or messages is required")
            msgs = [{"role": "user", "content": self.message}]
        if self.system:
            msgs.insert(0, {"role": "system", "content": self.system})
        return msgs


def _headers(settings) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_http_referer,
        "X-Title": settings.openrouter_app_name,
    }


@router.post("/reasoning")
async def reasoning(req: ReasoningRequest) -> Any:
    settings = get_settings()
    if not settings.has_openrouter_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_API_KEY is not set; the /reasoning route is disabled",
        )
    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    payload: Dict[str, Any] = {
        "model": req.model or settings.openrouter_model,
        "messages": req.build_messages(),
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "stream": req.stream,
    }
    if req.include_reasoning:
        payload["include_reasoning"] = True

    headers = _headers(settings)
    timeout = httpx.Timeout(settings.openrouter_timeout)

    if req.stream:

        async def events():
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"event: error\ndata: {body.decode(errors='replace')}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        yield f"data: {json.dumps(parsed, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/models")
async def available_models() -> Any:
    settings = get_settings()
    if not settings.has_openrouter_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_API_KEY is not set; the /reasoning route is disabled",
        )
    url = f"{settings.openrouter_base_url.rstrip('/')}/models"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(settings))
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    data = resp.json()
    free = sorted(
        model["id"]
        for model in data.get("data", [])
        if model.get("id", "").endswith(":free") or model.get("id") == "openrouter/free"
    )
    return {"count": len(free), "free_models": free}