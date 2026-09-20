import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .tools.registry import Tool
from .tools.builtin import registry

_SERVERS_DIR = Path(__file__).parent / "mcp_servers"

DEFAULT_MCP_SERVERS = [
    {"name": "web-search", "script": "web_search.py"},
    {"name": "youtube-search", "script": "youtube_search.py"},
]


class McpToolError(Exception):
    pass


def _resolve_script(script: str) -> str:
    path = Path(script)
    if path.is_absolute():
        return str(path)
    return str(_SERVERS_DIR / script)


def _load_server_specs(raw: str) -> List[Dict[str, Any]]:
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return parsed
        except (ValueError, TypeError):
            pass
    return [dict(entry) for entry in DEFAULT_MCP_SERVERS]


def _to_tool_schema(name: str, description: str, input_schema: Dict[str, Any]) -> Dict[str, Any]:
    input_schema = input_schema or {}
    properties = input_schema.get("properties") or {}
    normalized: Dict[str, Any] = {}
    for pname, pschema in properties.items():
        raw_type = pschema.get("type", "string")
        if isinstance(raw_type, list):
            raw_type = next((t for t in raw_type if t in ("integer", "number", "string")), "string")
        if raw_type not in ("integer", "number", "string", "boolean", "array", "object"):
            raw_type = "string"
        prop: Dict[str, Any] = {"type": raw_type}
        if "enum" in pschema:
            prop["enum"] = pschema["enum"]
        if "default" in pschema:
            prop["default"] = pschema["default"]
        normalized[pname] = prop
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or "",
            "parameters": {
                "type": "object",
                "properties": normalized,
                "required": list(input_schema.get("required") or []),
            },
        },
    }


class McpBridge:
    def __init__(
        self,
        name: str,
        script: str,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 120.0,
    ) -> None:
        self.name = name
        self.script = _resolve_script(script)
        self.env = env
        self.timeout = timeout
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._ready: Optional[threading.Event] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._streams: List[Any] = []
        self._lock = threading.RLock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name=f"mcp-{self.name}", daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(timeout=self.timeout):
            raise McpToolError(f"server '{self.name}' did not initialize in time")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _serve(self) -> None:
        parameters = StdioServerParameters(command=sys.executable, args=[self.script], env=self.env)
        self._stop_event = asyncio.Event()
        try:
            async with stdio_client(parameters) as (read_stream, write_stream):
                self._streams = [read_stream, write_stream]
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as exc:
            print(f"[mcp] server {self.name} terminated: {exc}")
            self._ready.set()
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            async def _list() -> List[Dict[str, Any]]:
                result = await self._session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]

            future = asyncio.run_coroutine_threadsafe(_list(), self._loop)
        return future.result(timeout=self.timeout)

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        with self._lock:
            async def _call() -> str:
                result = await self._session.call_tool(name, arguments)
                texts = [block.text for block in result.content if getattr(block, "text", None) is not None]
                text = "\n".join(texts)
                if getattr(result, "isError", False):
                    raise McpToolError(text or f"tool '{name}' failed")
                return text

            future = asyncio.run_coroutine_threadsafe(_call(), self._loop)
        return future.result(timeout=self.timeout)

    def shutdown(self) -> None:
        if self._session is None or self._loop is None or not (self._thread and self._thread.is_alive()):
            return
        try:
            async def _close() -> None:
                try:
                    await self._session.__aexit__(None, None, None)
                except Exception:
                    pass
                for stream in getattr(self, "_streams", []) or []:
                    try:
                        await stream.aclose()
                    except Exception:
                        pass

            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=10)
        except Exception:
            pass
        if self._stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except Exception:
                pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass


def wrap_mcp_tool(bridge: McpBridge, name: str, description: str, input_schema: Dict[str, Any]) -> Tool:
    schema = _to_tool_schema(name, description, input_schema)

    def func(**kwargs: Any) -> Any:
        return bridge.call_tool(name, kwargs)

    return Tool.from_schema(name, description, schema, func)


_bridges: List[McpBridge] = []


def register_mcp_tools(settings) -> List[str]:
    global _bridges
    _bridges = []
    registered: List[str] = []
    if not settings.mcp_enabled:
        return registered
    specs = _load_server_specs(settings.mcp_servers)
    for spec in specs:
        bridge = McpBridge(
            name=spec.get("name") or spec.get("script"),
            script=spec.get("script", ""),
            env=spec.get("env"),
            timeout=float(getattr(settings, "mcp_timeout", 120.0)),
        )
        try:
            bridge.start()
        except Exception as exc:
            print(f"[mcp] failed to start server {bridge.name}: {exc}")
            continue
        try:
            tools = bridge.list_tools()
        except Exception as exc:
            print(f"[mcp] failed to list tools from {bridge.name}: {exc}")
            continue
        for tool in tools:
            registry.register(wrap_mcp_tool(bridge, tool["name"], tool["description"] or "", tool["inputSchema"]))
            registered.append(tool["name"])
        _bridges.append(bridge)
    return registered


def shutdown_mcp() -> None:
    for bridge in _bridges:
        try:
            bridge.shutdown()
        except Exception:
            pass


def mcp_status() -> Dict[str, Any]:
    return {"enabled": bool(_bridges), "servers": [bridge.name for bridge in _bridges]}
