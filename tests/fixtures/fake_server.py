"""A stand-in MCP server over stdio. It answers initialize, tools/list and three tools:
ok (a normal result), flagged (isError set) and hidden (a normal result whose body reports an error)."""
import json
import sys

for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method, rid = msg.get("method"), msg["id"]
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "inputSchema": {"type": "object"}} for n in ("ok", "flagged", "hidden")]}
    elif method == "tools/call":
        name = msg["params"]["name"]
        if name == "ok":
            result = {"content": [{"type": "text", "text": '{"result": "pad created"}'}], "isError": False}
        elif name == "flagged":
            result = {"content": [{"type": "text", "text": "sketch not found"}], "isError": True}
        else:
            result = {"content": [{"type": "text", "text": '{"error": "Failed to parse expression"}'}], "isError": False}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no such method"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)
