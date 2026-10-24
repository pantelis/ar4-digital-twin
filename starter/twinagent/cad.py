"""cad <link page>: model one link in FreeCAD from the numbers in its kDB page.

What the starter does: an agent with the FreeCAD MCP server's tools and a tool that reads kDB
quantities. It must save the FreeCAD document and export a mesh; the output validator checks
that both files exist and copies them into cad/. What is yours: instructions that make the part
parametric (a spreadsheet of dimensions bound to the sketches), checking the solid it built
against the kDB, the failures blwfish reports as success, and the links' frames and joint axes.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from twin_tools import kdb as K

CONTAINER_REPO = Path("/work")  # where docker/run.sh mounts this repository


class Part(BaseModel):
    link: str = Field(description="the kDB Link page you modeled, such as links/link-2.md")
    fcstd: str = Field(description="the FreeCAD document you saved, as a path inside the container")
    mesh: str = Field(description="the STL mesh you exported, as a path inside the container")


@dataclass
class Workspace:
    repo: Path  # this repository on the host
    kdb: Path


INSTRUCTIONS = (
    "You model one link of the AR4 robot arm in FreeCAD through its tools. Read the link's dimensions with "
    "quantities() and use no other numbers. Save the document and export an STL mesh under /work/.home/out/, "
    "the only place FreeCAD may write, and return their paths."
)  # yours to improve


def host_path(ws: Workspace, path: str) -> Path:
    p = Path(path)
    return ws.repo / p.relative_to(CONTAINER_REPO) if p.is_relative_to(CONTAINER_REPO) else p


def make_agent(model, freecad, settings: dict | None = None) -> Agent[Workspace, Part]:
    agent = Agent(model, deps_type=Workspace, output_type=Part, instructions=INSTRUCTIONS, retries=2,
                  toolsets=[freecad], model_settings=settings or None)

    @agent.tool
    def quantities(ctx: RunContext[Workspace], page: str) -> dict:
        """The quantities on a kDB page, such as links/link-2.md, each with its value and unit."""
        K.use(ctx.deps.kdb)
        try:
            return K.quantities(page)
        except K.KdbError as e:
            raise ModelRetry(str(e)) from e

    @agent.output_validator
    def files_exist(ctx: RunContext[Workspace], part: Part) -> Part:
        missing = [p for p in (part.fcstd, part.mesh) if not host_path(ctx.deps, p).is_file()]
        if missing:
            raise ModelRetry(f"these files do not exist: {', '.join(missing)}. Save and export them, then answer again.")
        cad = ctx.deps.repo / "cad"
        cad.mkdir(exist_ok=True)
        stem = Path(part.link).stem
        for src, suffix in ((part.fcstd, ".FCStd"), (part.mesh, ".stl")):
            shutil.copyfile(host_path(ctx.deps, src), cad / f"{stem}{suffix}")
        return part

    return agent


def build_part(agent: Agent[Workspace, Part], repo: Path, kdb: Path, link: str) -> Part:
    return agent.run_sync(f"Model the link described on {link}.", deps=Workspace(repo, kdb)).output
