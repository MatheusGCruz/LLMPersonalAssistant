import inspect
import json
from typing import Any, Callable, Dict, List

_TYPE_MAP = {
    int: "integer",
    float: "number",
    str: "string",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _js_type(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "string"
    if annotation in _TYPE_MAP:
        return _TYPE_MAP[annotation]
    for base in getattr(annotation, "__mro__", []):
        if base in _TYPE_MAP:
            return _TYPE_MAP[base]
    return "string"


def _coerce(value: Any, js_type: str) -> Any:
    if js_type == "integer":
        return int(float(value))
    if js_type == "number":
        return float(value)
    if js_type == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value)
    if js_type == "array":
        if isinstance(value, str):
            return json.loads(value)
        return list(value)
    return str(value)


def _as_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class ToolError(Exception):
    pass


class Tool:
    def __init__(self, name: str, description: str, func: Callable[..., Any]):
        self.name = name
        self.description = description
        self.func = func
        self.schema = self._build_schema()

    def _build_schema(self) -> Dict[str, Any]:
        sig = inspect.signature(self.func)
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for pname, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            js_type = _js_type(param.annotation)
            prop: Dict[str, Any] = {"type": js_type}
            if param.default is not inspect.Parameter.empty:
                prop["default"] = param.default
            else:
                required.append(pname)
            properties[pname] = prop
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @classmethod
    def from_schema(
        cls,
        name: str,
        description: str,
        schema: Dict[str, Any],
        func: Callable[..., Any],
    ) -> "Tool":
        tool = cls.__new__(cls)
        tool.name = name
        tool.description = description
        tool.func = func
        tool.schema = schema
        return tool

    def parameters(self) -> Dict[str, Dict[str, Any]]:
        return self.schema["function"]["parameters"]["properties"]

    def run(self, arguments: Dict[str, Any]) -> Any:
        coerced: Dict[str, Any] = {}
        for pname, schema in self.parameters().items():
            if pname not in arguments:
                continue
            try:
                coerced[pname] = _coerce(arguments[pname], schema["type"])
            except (TypeError, ValueError) as exc:
                raise ToolError(f"invalid value for '{pname}': {arguments[pname]!r} ({exc})") from exc
        try:
            return _as_json_safe(self.func(**coerced))
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"tool '{self.name}' failed: {exc}") from exc


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool(self, name: str) -> Tool:
        return self._tools[name]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def run(self, name: str, arguments: Dict[str, Any]) -> Any:
        tool = self.get(name)
        if tool is None:
            return _as_json_safe(f"unknown tool: {name}")
        try:
            return tool.run(arguments)
        except ToolError as exc:
            return _as_json_safe(str(exc))

    def schemas(self) -> List[Dict[str, Any]]:
        return [t.schema for t in self._tools.values()]