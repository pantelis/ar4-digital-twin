"""The FreeCAD MCP server as a Pydantic AI toolset.

blwfish reports many failures as a normal result whose text is {"error": ...}. The toolset turns
those into retries, so the model sees that the call failed. It cannot catch the failures that
blwfish reports as success; the project README lists them, and checking what was built is yours.
"""

from __future__ import annotations

import json

from pydantic_ai import ModelRetry
from pydantic_ai.mcp import MCPToolset, StdioTransport


def failure(result) -> str | None:
    """The error a result carries in its body, the way twin-mcp-log summary finds it."""
    body = result
    if isinstance(result, str):
        try:
            body = json.loads(result)
        except ValueError:
            return None
    if isinstance(body, dict) and body.get("error"):
        return str(body["error"])
    return None


async def flag_errors(ctx, call_tool, name: str, args: dict):
    result = await call_tool(name, args)
    error = failure(result)
    if error:
        raise ModelRetry(f"{name} failed: {error}")
    return result


def toolset(command: list[str], cwd: str | None = None) -> MCPToolset:
    return MCPToolset(StdioTransport(command[0], command[1:], cwd=cwd), process_tool_call=flag_errors)
