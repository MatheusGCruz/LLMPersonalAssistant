from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import get_settings
from ..llm import get_engine
from ..pattern import PatternRouter, load_custom_rules
from ..tools.builtin import DEFAULT_SYSTEM_PROMPT, registry

router = APIRouter(prefix="/assistant", tags=["assistant"])


class Turn(BaseModel):
    role: str
    content: str


class AssistantRequest(BaseModel):
    message: Optional[str] = None
    messages: Optional[List[Turn]] = None
    max_tool_iterations: Optional[int] = Field(None, ge=1, le=10)

    def conversation(self) -> List[Dict[str, str]]:
        if self.messages:
            return [t.model_dump() for t in self.messages]
        return [{"role": "user", "content": self.message or ""}]


@router.post("")
def assistant(req: AssistantRequest) -> Dict[str, Any]:
    settings = get_settings()
    messages = req.conversation()
    if not messages[-1]["content"].strip():
        raise HTTPException(status_code=400, detail="message content is empty")

    rules = load_custom_rules(settings.tool_routing_rules)
    router = PatternRouter(rules=rules, lookup=registry.get)
    hit = router.route(messages[-1]["content"])
    if hit is not None:
        result = registry.run(hit.tool_name, hit.arguments)
        return {
            "handled_by": "tool",
            "rule": hit.rule_name,
            "tool": hit.tool_name,
            "arguments": hit.arguments,
            "result": result,
            "content": result,
            "used_model": False,
        }

    if not any(m["role"] == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})

    engine = get_engine(settings)
    try:
        outcome = engine.tool_loop(messages, max_iterations=req.max_tool_iterations)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "handled_by": "llm",
        "content": outcome.get("content") or "",
        "tool_calls": outcome.get("tool_calls"),
        "iterations": outcome.get("iterations"),
        "note": outcome.get("note"),
        "used_model": True,
        "model": "local-qwen3-0.6b",
    }


@router.get("/rules")
def rules() -> Dict[str, Any]:
    return {"rules": load_custom_rules(None)}


@router.get("/tools")
def tools() -> Dict[str, Any]:
    return {"tools": registry.schemas()}