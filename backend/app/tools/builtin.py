import ast
import operator
import random
from datetime import datetime
from typing import List

import httpx

from .registry import Tool, ToolRegistry

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_ast(node) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_ast(node.operand))
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    raise ValueError("unsupported expression")


def get_current_time(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def get_current_date() -> str:
    return datetime.now().strftime("%A, %Y-%m-%d")


def calculate(expression: str) -> float:
    try:
        result = _eval_ast(ast.parse(expression.strip(), mode="eval"))
    except Exception as exc:
        raise ValueError(f"cannot evaluate {expression!r}: {exc}") from exc
    return float(f"{result:.10g}")


def roll_dice(count: int = 1, sides: int = 6) -> List[int]:
    if sides < 2 or sides > 1000:
        raise ValueError("sides must be between 2 and 1000")
    if count < 1 or count > 100:
        raise ValueError("count must be between 1 and 100")
    return [random.randint(1, sides) for _ in range(count)]


def get_weather(city: str) -> str:
    try:
        resp = httpx.get(
            f"https://wttr.in/{city}?format=j1&lang=en",
            headers={"User-Agent": "curl"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city)
        return (
            f"Weather in {area}: {current.get('weatherDesc', [{}])[0].get('value', 'n/a')}, "
            f"{current.get('temp_C')}C / {current.get('temp_F')}F, "
            f"humidity {current.get('humidity')}%, wind {current.get('windspeedKmph')} km/h"
        )
    except Exception as exc:
        return f"could not fetch weather for {city!r}: {exc}"


def web_search(query: str) -> str:
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers={"User-Agent": "curl"},
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = []
        if data.get("AbstractText"):
            hits.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and topic.get("Text"):
                hits.append(topic["Text"])
            elif isinstance(topic, dict) and topic.get("Topics"):
                for sub in topic["Topics"]:
                    if sub.get("Text"):
                        hits.append(sub["Text"])
            if len(hits) >= 3:
                break
        if hits:
            return "\n\n".join(hits)
        return f"no instant answers found for {query!r}"
    except Exception as exc:
        return f"web search failed for {query!r}: {exc}"


BUILTIN_TOOLS = [
    Tool("get_current_time", "Get the current time. Optionally pass a strftime format string.", get_current_time),
    Tool("get_current_date", "Get today's date (weekday, year, month, day).", get_current_date),
    Tool(
        "calculate",
        "Evaluate a simple arithmetic expression (+, -, *, /, //, %, **). "
        "Takes a plain expression string such as '(12 + 34) * 5' and returns a number.",
        calculate,
    ),
    Tool("roll_dice", "Roll one or more dice and return the list of rolls. count=number of dice, sides=faces per die.", roll_dice),
    Tool("get_weather", "Get the current weather for a city by name.", get_weather),
    Tool("web_search", "Query the DuckDuckGo instant answer API and return up to three top hits.", web_search),
]

registry = ToolRegistry()
for _tool in BUILTIN_TOOLS:
    registry.register(_tool)

ALL_TOOLS = BUILTIN_TOOLS
TOOL_SCHEMAS = registry.schemas()

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. When a question requires live or external information, "
    "call the right tool instead of guessing. If you call a tool, wait for its result and then "
    "summarize the answer for the user. Otherwise answer from your knowledge."
)