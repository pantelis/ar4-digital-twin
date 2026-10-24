import json
import subprocess
import sys
from pathlib import Path

from twin_tools.mcp_log import summarize

FAKE = Path(__file__).parent / "fixtures" / "fake_server.py"


def rpc(i, method, params=None):
    return json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}})


def run_session(tmp_path, lines):
    log = tmp_path / "calls.jsonl"
    out = subprocess.run([sys.executable, "-m", "twin_tools.mcp_log", "run", "--log", str(log), "--", sys.executable, str(FAKE)],
                         input="\n".join(lines) + "\n", capture_output=True, text=True, timeout=30)
    return out, log


def test_proxy_passes_messages_through_unchanged(tmp_path):
    out, _ = run_session(tmp_path, [rpc(1, "initialize"), rpc(2, "tools/list")])
    replies = [json.loads(l) for l in out.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["ok", "flagged", "hidden"]
    assert out.returncode == 0


def test_log_records_both_directions(tmp_path):
    _, log = run_session(tmp_path, [rpc(1, "initialize")])
    records = [json.loads(l) for l in log.read_text().splitlines()]
    assert [r["dir"] for r in records] == ["to_server", "to_agent"]
    assert records[0]["msg"]["method"] == "initialize"
    assert all(isinstance(r["t"], float) for r in records)


def test_summary_pairs_calls_and_catches_hidden_errors(tmp_path):
    _, log = run_session(tmp_path, [rpc(1, "initialize")] + [
        rpc(i, "tools/call", {"name": n, "arguments": {"x": i}}) for i, n in [(2, "ok"), (3, "flagged"), (4, "hidden")]])
    calls = summarize(log)
    assert [(c["tool"], c["ok"]) for c in calls] == [("ok", True), ("flagged", False), ("hidden", False)]
    assert calls[0]["args"] == {"x": 2}
    assert "Failed to parse expression" in calls[2]["reason"]
    assert all(c["secs"] >= 0 for c in calls)


def test_summary_marks_unanswered_calls(tmp_path):
    log = tmp_path / "calls.jsonl"
    log.write_text(json.dumps({"t": 1.0, "dir": "to_server", "msg": json.loads(rpc(7, "tools/call", {"name": "pad", "arguments": {}}))}) + "\n")
    [call] = summarize(log)
    assert call["ok"] is False and call["reason"] == "no response"


def test_summary_of_missing_log_exits_2(tmp_path):
    out = subprocess.run([sys.executable, "-m", "twin_tools.mcp_log", "summary", str(tmp_path / "none.jsonl")],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 2
    assert "no such file" in out.stderr and "Traceback" not in out.stderr
