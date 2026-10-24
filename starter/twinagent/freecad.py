"""The FreeCAD MCP server as a Pydantic AI toolset.

blwfish reports many failures as a normal result whose text is {"error": ...}. The toolset turns
those into retries, so the model sees that the call failed. It cannot catch the failures that
blwfish reports as success; the project README lists them, and checking what was built is yours.

A small model can also fall into a loop, making the same call with the same arguments again and
again (a 12B model once added the same rectangle 95 times). The toolset refuses a call that
repeats the one before it REPEATS times in a row and tells the model so.
"""

from __future__ import annotations

import json

REPEATS = 3  # identical calls in a row before the next one is refused

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


def loop_guard(repeats: int = REPEATS):
    """A process_tool_call step that refuses the same call made repeats times in a row."""
    last: dict = {"key": None, "count": 0}

    async def guarded(ctx, call_tool, name: str, args: dict):
        key = (name, json.dumps(args, sort_keys=True, default=str))
        last["count"] = last["count"] + 1 if key == last["key"] else 1
        last["key"] = key
        if last["count"] > repeats:
            raise ModelRetry(f"you have made this exact {name} call {repeats} times in a row and its result will not "
                             "change. Read the last result, then change the arguments or do the next step.")
        return await flag_errors(ctx, call_tool, name, args)

    return guarded


async def flag_errors(ctx, call_tool, name: str, args: dict):
    result = await call_tool(name, args)
    error = failure(result)
    if error:
        raise ModelRetry(f"{name} failed: {error}")
    return result


def toolset(command: list[str], cwd: str | None = None, retries: int = 5) -> MCPToolset:
    """retries is how many times a failed FreeCAD call may be retried before the run stops."""
    return MCPToolset(StdioTransport(command[0], command[1:], cwd=cwd), process_tool_call=loop_guard(),
                      max_retries=retries)
