"""Minimal in-process MCP tool registry for Phase 3."""

from dataclasses import dataclass
import inspect
from typing import Any, Awaitable, Callable, Optional


ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    """Registered tool definition and callable handler."""

    name: str
    description: str
    arguments: dict[str, dict[str, Any]]
    handler: ToolHandler

    def public_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


class ToolRegistry:
    """Register, describe, validate, and invoke MCP-compatible tools."""

    _python_types = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        arguments: dict[str, dict[str, Any]],
        handler: ToolHandler,
    ) -> Tool:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        tool = Tool(name, description, arguments, handler)
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_definitions(self) -> list[dict[str, Any]]:
        return [self._tools[name].public_definition() for name in sorted(self._tools)]

    def validate(self, tool: Tool, arguments: dict[str, Any]) -> None:
        unknown = sorted(set(arguments) - set(tool.arguments))
        if unknown:
            raise ValueError(f"Unknown argument: {unknown[0]}")

        for name, schema in tool.arguments.items():
            if schema.get("required") and name not in arguments:
                raise ValueError(f"Missing required argument: {name}")
            if name not in arguments:
                continue
            expected_type = self._python_types.get(schema.get("type"))
            if expected_type is None:
                raise ValueError(f"Unsupported argument type for {name}")
            value = arguments[name]
            if schema.get("type") == "integer" and isinstance(value, bool):
                raise ValueError(f"Argument {name} must be an integer")
            if not isinstance(value, expected_type):
                raise ValueError(f"Argument {name} must be a {schema.get('type')}")

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get(name)
        if tool is None:
            raise KeyError(name)
        self.validate(tool, arguments)
        result = tool.handler(arguments)
        if inspect.isawaitable(result):
            return await result
        return result


registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    arguments: dict[str, dict[str, Any]],
    handler: ToolHandler,
) -> Tool:
    """Register a tool in the process-wide Phase 3 registry."""
    return registry.register(name, description, arguments, handler)


async def _list_events_stub(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"events": [], "date_range": arguments["date_range"], "stub": True}


async def _create_event_stub(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"event": arguments, "created": False, "stub": True}


register_tool(
    "google_calendar.list_events",
    "List events from Google Calendar (Phase 3 stub).",
    {"date_range": {"type": "string", "required": True}},
    _list_events_stub,
)
register_tool(
    "google_calendar.create_event",
    "Create a Google Calendar event (Phase 3 stub).",
    {
        "summary": {"type": "string", "required": True},
        "start": {"type": "string", "required": True},
        "end": {"type": "string", "required": True},
    },
    _create_event_stub,
)
