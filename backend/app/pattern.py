import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .tools.registry import Tool

DEFAULT_RULES = [
    {
        "name": "direct:time",
        "pattern": r"^(?:what time is it|what'?s the time|current time|time now)\??$",
        "tool": "get_current_time",
        "args": {},
    },
    {
        "name": "direct:date",
        "pattern": r"^(?:what'?s the date|current date|what date is today|today'?s date)\??$",
        "tool": "get_current_date",
        "args": {},
    },
    {
        "name": "direct:calc",
        "pattern": r"^(?:calc(?:ulate)?)\s*[:=]?\s*(?P<expression>.+)$",
        "tool": "calculate",
        "args_from_groups": ["expression"],
    },
    {
        "name": "direct:dice",
        "pattern": r"^roll(?:\s+(?P<count>\d+))?(?:\s*d(?P<sides>\d+))?$",
        "tool": "roll_dice",
        "args_from_groups": ["count", "sides"],
    },
    {
        "name": "direct:weather",
        "pattern": r"^(?:weather|forecast)\s+(?:in|for)?\s*(?P<city>.+)$",
        "tool": "get_weather",
        "args_from_groups": ["city"],
    },
    {
        "name": "direct:search",
        "pattern": r"^(?:search|look up|find)\s+(?P<query>.+)$",
        "tool": "web_search",
        "args_from_groups": ["query"],
    },
    {
        "name": "direct:youtube_search",
        "pattern": r"^(?:yt|youtube)\s+(?:search\s+)?(?P<query>.+)$",
        "tool": "youtube_search",
        "args_from_groups": ["query"],
    },
]


@dataclass
class RouteHit:
    rule_name: str
    tool_name: str
    arguments: Dict[str, Any]


class PatternRouter:
    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None, lookup=None) -> None:
        self._rules = list(rules if rules is not None else DEFAULT_RULES)
        self._lookup = lookup

    def _coerce_kwargs(self, tool: Tool, rule: Dict[str, Any], groups: Dict[str, str]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        for key, value in rule.get("args", {}).items():
            kwargs[key] = value
        for param_name in rule.get("args_from_groups", []):
            if param_name not in groups or groups.get(param_name) is None:
                continue
            raw = groups[param_name].strip()
            schema = tool.parameters().get(param_name)
            if schema and schema["type"] == "integer":
                kwargs[param_name] = int(float(raw))
            elif schema and schema["type"] == "number":
                kwargs[param_name] = float(raw)
            else:
                kwargs[param_name] = raw
        return kwargs

    def route(self, message: str) -> Optional[RouteHit]:
        text = message.strip().lower()
        for rule in self._rules:
            match = re.match(rule["pattern"], text)
            if not match:
                continue
            tool_name = rule["tool"]
            tool = self._lookup(tool_name) if self._lookup else None
            if tool is None:
                continue
            arguments = self._coerce_kwargs(tool, rule, match.groupdict())
            return RouteHit(rule_name=rule["name"], tool_name=tool_name, arguments=arguments)
        return None


def load_custom_rules(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return DEFAULT_RULES
    try:
        if isinstance(raw, str):
            parsed = json.loads(raw)
        else:
            parsed = raw
        if isinstance(parsed, dict):
            parsed = parsed.get("rules", [])
        if not isinstance(parsed, list):
            raise ValueError("custom rules must be a list")
        rules = []
        for entry in parsed:
            if not all(k in entry for k in ("name", "pattern", "tool")):
                raise ValueError(f"rule missing name/pattern/tool: {entry}")
            rules.append(
                {
                    "name": entry["name"],
                    "pattern": entry["pattern"],
                    "tool": entry["tool"],
                    "args": entry.get("args", {}),
                    "args_from_groups": entry.get("args_from_groups", []),
                }
            )
        return rules
    except (json.JSONDecodeError, ValueError) as exc:
        return DEFAULT_RULES