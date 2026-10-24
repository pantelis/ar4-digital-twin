"""cad <link page>: model one link in FreeCAD from the numbers in its kDB page.

What the starter does: an agent with the FreeCAD MCP server's tools and a tool that reads kDB
pages. It must save the FreeCAD document, export a mesh, and state the volume, size and number of
through holes it expects, worked out from the page's quantities. The output validator measures
the mesh, sends the agent back with the measurements when they differ from what it expected, and
copies the files into cad/ only when they agree. The check cannot catch a part whose expectation
is wrong in the same way as its geometry. What is yours: instructions that make the part
parametric (a spreadsheet of dimensions bound to the sketches), stronger checks against the kDB,
and the links' frames and joint axes.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from twin_tools import kdb as K

from . import solid

CONTAINER_REPO = Path("/work")  # where docker/run.sh mounts this repository
VOLUME_TOLERANCE = 0.01  # relative; a mesh's flat facets cut a little off every curved face
SIZE_TOLERANCE = 0.5  # mm on each side of the bounding box
RETRIES = 5  # FreeCAD calls fail often while a model learns the tools


class Part(BaseModel):
    link: str = Field(description="the kDB Link page you modeled, such as links/link-2.md")
    fcstd: str = Field(description="the FreeCAD document you saved, as a path inside the container")
    mesh: str = Field(description="the STL mesh you exported, as a path inside the container")
    expected_volume_mm3: float = Field(description="the part's volume worked out from the page's quantities, in mm^3")
    expected_size_mm: list[float] = Field(min_length=3, max_length=3,
                                          description="the part's bounding box lengths along x, y and z, from the quantities, in mm")
    expected_through_holes: int = Field(ge=0, description="the number of holes that go all the way through the part")


@dataclass
class Workspace:
    repo: Path  # this repository on the host
    kdb: Path


# How to work with the blwfish tools. These rules come from the model-driven runs on 2026-10-24, where every
# model lost most of its calls to these mistakes. The server's own advice is added to them at the start of a run.
WORKFLOW = """\
Working with the FreeCAD tools:
1. Call spawn_freecad_instance(gui=false) once, first. No other FreeCAD tool works before it. Never call it
   again: a new instance starts empty and everything built so far is lost.
2. Create the document with view_control(operation="create_document") in a call of its own. When a call
   answers "No active document", create the document; do not spawn another instance.
3. Pass only the parameters a tool's schema lists. When you are unsure how a tool is called, call
   api_introspection or get_usage_guidance(operation="find", problem="...") instead of guessing.
4. Prefer sketch_operations, partdesign_operations and part_operations to execute_python. If you do use
   execute_python, never assign a new Shape to a parametric object such as a Part::Box and then recompute:
   the recompute rebuilds it from its own parameters and your change is lost. Add a Part::Feature instead.
5. Do not use partdesign hole, fillet or chamfer: they wait for a click in the 3D view. Make a hole as a
   circle in a sketch and a pocket at least as deep as the part.
6. Save the document with view_control(operation="save_document", filename=...) and export with
   mesh_operations(operation="export_mesh", object_name=..., file_path=...), both under /work/.home/out/.
7. Before you answer, measure the solid you built with measurement_operations (get_volume and
   get_bounding_box), and when something fails use operation="find_root_cause" on it."""
GUIDANCE_TOPICS = ("document", "measurement")  # the server's tactics worth reading for building one part

INSTRUCTIONS = (
    "You model one link of the AR4 robot arm in FreeCAD through its tools. Read the link's page with "
    "read_page() and use no numbers but its quantities. Before you build, work out from the quantities the part's "
    "volume, its bounding box size and its number of through holes. Save the document and export an STL mesh under "
    "/work/.home/out/, the only place FreeCAD may write, and return their paths with what you expect. The mesh is "
    "measured, and you are sent back if it does not match."
)  # yours to improve


def host_path(ws: Workspace, path: str) -> Path:
    p = Path(path)
    return ws.repo / p.relative_to(CONTAINER_REPO) if p.is_relative_to(CONTAINER_REPO) else p


async def server_guidance(freecad) -> str:
    """blwfish's own advice: its strategy and the tactics in GUIDANCE_TOPICS, from get_usage_guidance."""
    call = getattr(freecad, "direct_call_tool", None)
    if call is None:  # not an MCP toolset, as in the tests
        return ""
    parts = []
    for args in [{"operation": "strategy"}] + [{"operation": "tactics", "topic": t} for t in GUIDANCE_TOPICS]:
        try:
            parts.append(str(await call("get_usage_guidance", args)))
        except Exception:  # an older server without the tool: run without its advice
            break
    return "\n\n".join(parts)


def make_agent(model, freecad, settings: dict | None = None) -> Agent[Workspace, Part]:
    agent = Agent(model, deps_type=Workspace, output_type=Part, instructions=[INSTRUCTIONS, WORKFLOW], retries=RETRIES,
                  toolsets=[freecad], model_settings=settings or None)
    fetched: list[str] = []

    @agent.instructions
    async def advice_from_the_server(ctx: RunContext[Workspace]) -> str:
        if not fetched:
            fetched.append(await server_guidance(freecad))
        return f"Advice from the FreeCAD server:\n{fetched[0]}" if fetched[0] else ""

    @agent.tool
    def read_page(ctx: RunContext[Workspace], page: str) -> dict:
        """A kDB page, such as links/link-2.md: its title, its text, and its quantities with their values and units."""
        K.use(ctx.deps.kdb)
        try:
            fm, body = K.page(page)
        except K.KdbError as e:
            raise ModelRetry(str(e)) from e
        quantities = fm.get("quantities") if isinstance(fm.get("quantities"), dict) else {}
        return {"title": fm.get("title"), "text": body, "quantities": quantities}

    @agent.output_validator
    def files_hold_the_part(ctx: RunContext[Workspace], part: Part) -> Part:
        missing = [p for p in (part.fcstd, part.mesh) if not host_path(ctx.deps, p).is_file()]
        if missing:
            raise ModelRetry(f"these files do not exist: {', '.join(missing)}. Save and export them, then answer again.")
        problems = mismatches(solid.measure(host_path(ctx.deps, part.mesh)), part)
        if problems:
            raise ModelRetry("The mesh does not match the part you expected: " + "; ".join(problems) + ". Find what "
                             "went wrong in FreeCAD, fix the part, export it again and answer again.")
        cad = ctx.deps.repo / "cad"
        cad.mkdir(exist_ok=True)
        stem = Path(part.link).stem
        for src, suffix in ((part.fcstd, ".FCStd"), (part.mesh, ".stl")):
            shutil.copyfile(host_path(ctx.deps, src), cad / f"{stem}{suffix}")
        return part

    return agent


def mismatches(m: solid.Measure, part: Part) -> list[str]:
    """What differs between the measured mesh and the part the agent expected."""
    if not m.closed:
        return ["the mesh is not closed, so it is not a solid"]
    out = []
    if m.pieces != 1:
        out.append(f"the mesh is {m.pieces} separate pieces, not one")
    if abs(m.volume - part.expected_volume_mm3) > VOLUME_TOLERANCE * max(part.expected_volume_mm3, 1.0):
        out.append(f"its volume is {m.volume:.1f} mm^3, not {part.expected_volume_mm3:.1f}")
    got, want = sorted(m.size), sorted(part.expected_size_mm)
    if any(abs(g - w) > SIZE_TOLERANCE for g, w in zip(got, want)):
        out.append(f"its bounding box is {' x '.join(f'{v:.1f}' for v in m.size)} mm, not "
                   f"{' x '.join(f'{v:.1f}' for v in part.expected_size_mm)}")
    if m.through_holes is not None and m.through_holes != part.expected_through_holes:
        out.append(f"it has {m.through_holes} through holes, not {part.expected_through_holes}")
    return out


def build_part(agent: Agent[Workspace, Part], repo: Path, kdb: Path, link: str) -> Part:
    return agent.run_sync(f"Model the link described on {link}.", deps=Workspace(repo, kdb)).output
