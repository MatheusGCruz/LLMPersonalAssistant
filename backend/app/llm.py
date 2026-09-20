import json
import threading
from typing import Any, Dict, List, Optional

from llama_cpp import Llama

from .config import Settings
from .tools.builtin import registry


def _as_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return obj.__dict__


class LocalToolEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._llm: Optional[Llama] = None
        self._lock = threading.RLock()

    def loaded(self) -> bool:
        return self._llm is not None

    def load(self) -> Llama:
        with self._lock:
            if self._llm is not None:
                return self._llm
            settings = self.settings
            if not settings.model_path.is_file():
                raise FileNotFoundError(
                    f"model file not found at {settings.model_path}; "
                    "it should be downloaded by the app startup hook"
                )
            kwargs: Dict[str, Any] = dict(
                model_path=str(settings.model_path),
                n_ctx=settings.llama_n_ctx,
                n_gpu_layers=settings.llama_n_gpu_layers,
                n_threads=settings.llama_threads,
                n_batch=settings.llama_n_batch,
                verbose=settings.llama_verbose,
            )
            if settings.llama_chat_format:
                kwargs["chat_format"] = settings.llama_chat_format
            self._llm = Llama(**kwargs)
            return self._llm

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: bool = True,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        with self._lock:
            llm = self.load()
            kwargs: Dict[str, Any] = dict(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            if tools:
                kwargs["tools"] = registry.schemas()
                kwargs["tool_choice"] = "auto"
            return _as_dict(llm.create_chat_completion(**kwargs))

    def _parse_arguments(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return {}

    def tool_loop(self, messages: List[Dict[str, Any]], max_iterations: Optional[int] = None) -> Dict[str, Any]:
        iterations = max_iterations or self.settings.max_tool_iterations
        results: List[Dict[str, Any]] = []
        current = list(messages)
        for _ in range(iterations):
            response = self.chat(current, tools=True)
            message = response["choices"][0]["message"]
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return {
                    "content": content,
                    "tool_calls": results,
                    "iterations": len(results),
                }
            executed: List[Dict[str, Any]] = []
            assistant_payload: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                normalized_calls = []
                for call in tool_calls:
                    function = call.get("function", {})
                    name = function.get("name")
                    arguments = self._parse_arguments(function.get("arguments"))
                    outcome = registry.run(name, arguments)
                    normalized_calls.append(
                        {
                            "id": call.get("id") or name,
                            "type": call.get("type") or "function",
                            "function": {"name": name, "arguments": function.get("arguments") or arguments},
                        }
                    )
                    executed.append({"name": name, "arguments": arguments, "result": outcome})
                assistant_payload["tool_calls"] = normalized_calls
                current.append(assistant_payload)
                for call, step in zip(normalized_calls, executed):
                    current.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": step["name"],
                            "content": json.dumps(step["result"], ensure_ascii=False),
                        }
                    )
                results.extend(executed)
            else:
                current.append(assistant_payload)
        return {
            "content": None,
            "tool_calls": results,
            "iterations": len(results),
            "note": f"stopped after {iterations} tool iterations",
        }


engine = None


def get_engine(settings: Settings) -> LocalToolEngine:
    global engine
    if engine is None:
        engine = LocalToolEngine(settings)
    return engine