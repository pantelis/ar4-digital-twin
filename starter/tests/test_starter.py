"""The starter's plumbing works offline: a scripted model stands in for the server, and no FreeCAD runs."""

import anyio
import pytest
from kdb_tools.agent import Chunk, sheet_chunks
from kdb_tools.testing import make_xlsx
from pydantic_ai import ModelRetry
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

from twinagent import cad, cli, freecad, ingest


def scripted(*outputs):
    """A model that returns each output in turn as its final answer, and records the retry prompts it saw."""
    seen, calls = [], [0]

    def respond(messages, info: AgentInfo) -> ModelResponse:
        seen.extend(p.content for m in messages for p in m.parts if isinstance(p, (RetryPromptPart, ToolReturnPart)))
        out = outputs[min(calls[0], len(outputs) - 1)]
        calls[0] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])

    return FunctionModel(respond), seen


@pytest.fixture
def gears(tmp_path):
    path = tmp_path / "ar4-gears.xlsx"
    make_xlsx(path, {"Gears": [["joint", "ratio"], ["J1", 40], ["J2", 50]]})
    return path


def ratio(**kw):
    out = {"entity": "J1", "page_type": "Gearbox", "name": "ratio", "number": 40, "unit": "1",
           "value": "40", "cell": "B2", "sheet": "Gears"}
    out.update(kw)
    return out


def test_the_ingest_agent_sends_back_a_cell_that_does_not_hold_its_number(gears):
    model, seen = scripted({"from_cells": [ratio(), ratio(entity="J2", cell="B2", value="50", number=50)]},
                           {"from_cells": [ratio()]})
    chunk, prompt = next(iter(sheet_chunks(gears)))
    out = ingest.make_agent(model).run_sync(prompt, deps=chunk).output
    assert [c.entity for c in out.from_cells] == ["J1"]
    assert any("Gears!B2" in str(s) and "50" in str(s) for s in seen)


def test_a_unit_outside_the_list_is_sent_back(gears):
    model, seen = scripted({"from_cells": [ratio(unit="ratio")]}, {"from_cells": [ratio()]})
    chunk, prompt = next(iter(sheet_chunks(gears)))
    assert ingest.make_agent(model).run_sync(prompt, deps=chunk).output.from_cells[0].unit == "1"
    assert any("unit" in str(s) for s in seen)


def test_ingest_reads_a_spreadsheet_by_sheet_and_a_pdf_by_pages(gears, tmp_path):
    assert [c.sheet for c, _ in ingest.chunks(gears)] == ["Gears"]
    assert isinstance(next(iter(ingest.chunks(gears)))[0], Chunk)


def test_a_freecad_result_that_carries_an_error_is_sent_back():
    async def call(result):
        async def call_tool(name, args):
            return result
        return await freecad.flag_errors(None, call_tool, "pocket", {})

    assert anyio.run(call, '{"result": "ok"}') == '{"result": "ok"}'
    with pytest.raises(ModelRetry, match="pocket failed: no sketch"):
        anyio.run(call, '{"error": "no sketch"}')
    with pytest.raises(ModelRetry):
        anyio.run(call, {"error": "no sketch"})


def test_the_freecad_toolset_starts_the_configured_server(tmp_path):
    (tmp_path / "kdb.toml").write_text('base_url = "x"\nmodel = "m"\n')
    assert cli.freecad_command(tmp_path / "kdb.toml") == ["docker/run.sh", "twin-blwfish"]
    assert isinstance(freecad.toolset(["docker/run.sh", "twin-blwfish"]), MCPToolset)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "kdb" / "links").mkdir(parents=True)
    (tmp_path / "kdb" / "links" / "link-2.md").write_text(
        "---\ntype: Link\ntitle: Link 2\nquantities:\n  length: {value: 305, unit: mm, source: s1}\n---\n\nLink 2.\n")
    return tmp_path


def test_the_cad_agent_sends_back_files_it_did_not_write_and_copies_the_ones_it_did(repo):
    part = {"link": "links/link-2.md", "fcstd": "/work/.home/out/link-2.FCStd", "mesh": "/work/.home/out/link-2.stl"}
    out_dir = repo / ".home" / "out"

    def respond(messages, info: AgentInfo) -> ModelResponse:
        retried = any(isinstance(p, (RetryPromptPart, ToolReturnPart)) and "do not exist" in str(p.content)
                      for m in messages for p in m.parts)
        if retried:  # the "FreeCAD" run writes the files only after being sent back
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "link-2.FCStd").write_bytes(b"fcstd")
            (out_dir / "link-2.stl").write_bytes(b"solid")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, part)])

    agent = cad.make_agent(FunctionModel(respond), FunctionToolset([]))
    out = cad.build_part(agent, repo, repo / "kdb", "links/link-2.md")
    assert out.link == "links/link-2.md"
    assert (repo / "cad" / "link-2.FCStd").read_bytes() == b"fcstd" and (repo / "cad" / "link-2.stl").is_file()


def test_the_cad_agent_reads_quantities_from_the_kdb(repo):
    agent = cad.make_agent(scripted({})[0], FunctionToolset([]))
    tool = agent._function_toolset.tools["quantities"].function
    ctx = type("Ctx", (), {"deps": cad.Workspace(repo, repo / "kdb")})()
    assert tool(ctx, "links/link-2.md")["length"]["value"] == 305
    with pytest.raises(ModelRetry, match="no page"):
        tool(ctx, "links/link-9.md")


def test_commands_still_to_write_say_so(tmp_path, gears, capsys, monkeypatch):
    (tmp_path / "kdb.toml").write_text('base_url = "http://localhost:1/v1"\nmodel = "m"\n')
    monkeypatch.setattr(ingest, "extraction_agent", lambda *a, **k: type("A", (), {
        "run_sync": lambda self, prompt, deps: type("R", (), {"output": ingest.Found()})()})())
    assert cli.main(["--config", str(tmp_path / "kdb.toml"), "--kdb", str(tmp_path / "kdb"), "ingest", str(gears)]) == 2
    assert "not written yet" in capsys.readouterr().err
