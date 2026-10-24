"""Record every message between an agent and an MCP server, then summarize the tool calls.

    twin-mcp-log run --log calls.jsonl -- <server command...>
    twin-mcp-log summary calls.jsonl [--json]

`run` sits between the agent and a stdio MCP server. Point your agent at it instead of the server:
it starts the server, passes every message through unchanged and appends each one to the log
as {"t": unix time, "dir": "to_server" | "to_agent", "msg": the JSON-RPC message}.

`summary` pairs each tools/call request with its response. A call counts as failed when the
response is a JSON-RPC error, when the result sets isError, or when the result text is a JSON
object with an "error" field: some FreeCAD servers report failures only that way.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path


def _pump(src, dst, direction, log, lock):
    for line in iter(src.readline, b""):
        dst.write(line)
        dst.flush()
        try:
            msg = json.loads(line)
        except ValueError:
            msg = {"raw": line.decode(errors="replace").rstrip("\n")}
        with lock:
            log.write(json.dumps({"t": time.time(), "dir": direction, "msg": msg}) + "\n")
            log.flush()


def run(log_path: Path, command: list[str]) -> int:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    lock = threading.Lock()
    with open(log_path, "a") as log:
        def to_server():
            _pump(sys.stdin.buffer, proc.stdin, "to_server", log, lock)
            proc.stdin.close()

        threading.Thread(target=to_server, daemon=True).start()
        _pump(proc.stdout, sys.stdout.buffer, "to_agent", log, lock)
    return proc.wait()


def _failure(msg: dict) -> str | None:
    if "error" in msg:
        return json.dumps(msg["error"])
    result = msg.get("result") or {}
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
    if result.get("isError"):
        return text or "isError"
    try:
        body = json.loads(text)
    except ValueError:
        return None
    if isinstance(body, dict) and body.get("error"):
        return str(body["error"])
    return None


def summarize(log_path: Path) -> list[dict]:
    """One entry per tools/call: tool, args, ok, secs and, for failures, the reason."""
    calls, pending = [], {}
    for line in Path(log_path).read_text().splitlines():
        rec = json.loads(line)
        msg = rec["msg"]
        if rec["dir"] == "to_server" and msg.get("method") == "tools/call" and "id" in msg:
            params = msg.get("params", {})
            call = {"tool": params.get("name"), "args": params.get("arguments", {}), "ok": False, "secs": 0.0,
                    "reason": "no response", "_t": rec["t"]}
            pending[msg["id"]] = call
            calls.append(call)
        elif rec["dir"] == "to_agent" and msg.get("id") in pending:
            call = pending.pop(msg["id"])
            reason = _failure(msg)
            call.update(ok=reason is None, secs=round(rec["t"] - call["_t"], 3), reason=reason)
    for call in calls:
        del call["_t"]
    return calls


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-mcp-log", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="proxy an MCP server and log every message")
    r.add_argument("--log", required=True, type=Path)
    r.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the server command")
    s = sub.add_parser("summary", help="list the tool calls in a log")
    s.add_argument("log", type=Path)
    s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "run":
        command = a.command[1:] if a.command[:1] == ["--"] else a.command
        if not command:
            p.error("give the server command after --")
        return run(a.log, command)
    if not a.log.is_file():
        print(f"twin-mcp-log: no such file {a.log}", file=sys.stderr)
        return 2
    calls = summarize(a.log)
    if a.json:
        print(json.dumps(calls, indent=1))
    else:
        for c in calls:
            print(f"{'OK ' if c['ok'] else 'ERR'} {c['secs']:7.2f}s  {c['tool']}" + ("" if c["ok"] else f"  :: {c['reason'][:200]}"))
        failed = sum(not c["ok"] for c in calls)
        print(f"{len(calls)} calls, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
