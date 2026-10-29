"""Build the documents twin-sync checks: one bound box, its STL, a one-link assembly and a kDB to match.

    cad_dir, kdb_dir = build(tmp_path)                       # a part that matches the kDB
    cad_dir, kdb_dir = build(tmp_path, free_pad=True)        # a mutant, one keyword per rule

link-2 is a 280 x 40 x 30 mm box whose sketch and pad are bound to the kDB spreadsheet. The kDB holds
link-2's length, width and height, and joints j1 and j2 with j2's child link-2, so the assembly puts
link-2 at frame 2.
"""

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

from twin_tools import dh, guisave, kdb

FIX = Path(__file__).parent / "kdb"
DIMS = {"length": 280.0, "width": 40.0, "height": 30.0}  # mm
J1 = """---
type: Joint
title: J1
child: ../links/link-1.md
quantities:
  dh_theta_offset: {value: 0, unit: deg, source: s1}
  dh_alpha: {value: -90, unit: deg, source: s1}
  dh_d: {value: 150, unit: mm, source: s1}
  dh_a: {value: 50, unit: mm, source: s1}
---
"""
LINK = "---\ntype: Link\ntitle: Link 2\nquantities:\n" + "".join(
    f"  {k}: {{value: {v:g}, unit: mm, source: s1}}\n" for k, v in DIMS.items()) + "---\n"

SCRIPT = '''
import json, os
import FreeCAD as App, Part, Sketcher

spec = json.loads(os.environ["TWIN_CAD_SPEC"])
out = spec["out"]
doc = App.newDocument("link2")
S = spec["sheet_name"]
sheet = doc.addObject("Spreadsheet::Sheet", S)
sheet.Label = "kDB"
for r, (name, value) in enumerate(spec["dims"].items(), start=1):
    sheet.set(f"A{r}", spec["refs"].get(name, f"/links/link-2.md#{name}"))
    sheet.set(f"B{r}", str(value))
    sheet.setAlias(f"B{r}", name)
    sheet.set(f"C{r}", "mm")
doc.recompute()
body = doc.addObject("PartDesign::Body", "Body")
sk = body.newObject("Sketcher::SketchObject", "Sketch")
sk.AttachmentSupport = [(next(f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"), "")]
sk.MapMode = "FlatFace"
L, W = 280.0, 40.0
pts = [(0, 0), (L, 0), (L, W), (0, W)]
for i in range(4):
    a, b = pts[i], pts[(i + 1) % 4]
    sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
for i in range(4):
    sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
sk.addConstraint(Sketcher.Constraint("Horizontal", 2))
sk.addConstraint(Sketcher.Constraint("Vertical", 1))
sk.addConstraint(Sketcher.Constraint("Vertical", 3))
sk.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
ix = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, L))
iy = sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, W))
if spec["unnamed"]:
    sk.setExpression(f"Constraints[{ix}]", f"{S}.length")
    sk.setExpression(f"Constraints[{iy}]", f"{S}.width")
else:
    sk.renameConstraint(ix, "cl")
    sk.renameConstraint(iy, "cw")
    sk.setExpression("Constraints.cl", f"{S}.length")
    sk.setExpression("Constraints.cw", f"{S}.width")
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sk
pad.Length = 30.0
mode = spec["indirect"]
if mode == "constraint":
    pad.setExpression("Length", f"Sketch.Constraints[{iy}] * 0.75" if spec["unnamed"] else "Sketch.Constraints.cw * 0.75")
elif mode in ("varset", "varset_free"):
    vs = doc.addObject("App::VarSet", "Vars")
    vs.addProperty("App::PropertyLength", "hgt", "Base", "")
    vs.hgt = 30.0
    if mode == "varset":
        vs.setExpression("hgt", f"{S}.height")
    pad.setExpression("Length", "Vars.hgt")
elif not spec["free_pad"]:
    pad.setExpression("Length", f"{S}.height")
doc.recompute()
doc.saveAs(os.path.join(out, "link-2.FCStd"))
App.closeDocument(doc.Name)

asm = App.newDocument("ar4")
if spec["asm_sheet"] is not None:  # the assembly binds one quantity of its own
    asheet = asm.addObject("Spreadsheet::Sheet", "kDB")
    asheet.Label = "kDB"
    asheet.set("A1", "/links/link-2.md#length")
    asheet.set("B1", str(spec["asm_sheet"]))
    asheet.setAlias("B1", "length")
    asheet.set("C1", "mm")
    asm.recompute()
asm.saveAs(os.path.join(out, "ar4.FCStd"))  # a link needs a saved owner
if not spec["omit_link"]:
    if spec["link"]:  # an App::Link to the body of the link document saved above
        linked = App.openDocument(os.path.join(out, "link-2.FCStd"))
        part = asm.addObject("App::Link", "Link")
        part.LinkedObject = linked.getObject("Body")
    else:
        part = asm.addObject("App::Part", "Part")
    part.Label = "link-2"
    part.Placement = App.Placement(App.Matrix(*spec["matrix"]))
    if spec["outer"]:
        if spec["link"] == "assembly":
            import Assembly
            outer = asm.addObject("Assembly::AssemblyObject", "Outer")
        else:
            outer = asm.addObject("App::Part", "Outer")
        outer.Label = "assembly"
        outer.Placement = App.Placement(App.Matrix(*spec["outer"]))
        outer.addObject(part)
asm.recompute()
asm.save()
'''


def write_stl(path: Path, dx: float, dy: float, dz: float) -> None:
    """A binary STL of the box [0,dx] x [0,dy] x [0,dz], in mm."""
    v = np.array([[x, y, z] for x in (0, dx) for y in (0, dy) for z in (0, dz)], dtype=np.float32)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = [(q[0], q[1], q[2]) for q in quads] + [(q[0], q[2], q[3]) for q in quads]
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(tris)))
        for t in tris:
            f.write(struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *v[i]) for i in t) + b"\0\0")


def frame2(kdb_dir: Path) -> np.ndarray:
    """The expected placement of link 2, from the kDB's DH rows."""
    kdb.use(kdb_dir)
    try:
        return dh.frames([dh.row("joints/j1.md"), dh.row("joints/j2.md")], [0.0, 0.0])[2]
    finally:
        kdb.use(None)
        kdb.clear()


def build(tmp: Path, free_pad=False, sheet_value=None, bad_ref=False, stale_export=False, off_frame=False, corrupt=False,
          unnamed=False, sheet_name="kDB", indirect=None, nested=False, omit_link=False, link=None, asm_sheet=None,
          headless=False):
    """Write tmp/kdb and tmp/cad. Each keyword makes one mutant or one variant that must stay clean:
    unnamed constraints, a sheet whose object name is not kDB, a pad bound through a constraint or a VarSet,
    link-2 nested in an App::Part, link-2 left out of the assembly, link-2 an App::Link to the saved link document
    (link="top" at the top level, "part" inside an App::Part, "assembly" inside an Assembly::AssemblyObject).
    asm_sheet=280.0 gives the assembly a kDB sheet with link-2's length in mm; another number puts that sheet off the kDB.
    The documents are then saved once with GUI FreeCAD (twin-guisave), as a student's must be; headless=True leaves them
    as freecadcmd wrote them."""
    kdb_dir, cad_dir = tmp / "kdb", tmp / "cad"
    shutil.copytree(FIX, kdb_dir)
    (kdb_dir / "links").mkdir()
    (kdb_dir / "links" / "link-2.md").write_text(LINK)
    (kdb_dir / "joints" / "j1.md").write_text(J1)
    j2 = (kdb_dir / "joints" / "j2.md").read_text().replace("title: J2\n", "title: J2\nchild: ../links/link-2.md\n")
    (kdb_dir / "joints" / "j2.md").write_text(j2)
    cad_dir.mkdir()
    matrix = frame2(kdb_dir).copy()
    matrix[:3, 3] *= 1e3  # FreeCAD is in mm
    if off_frame:
        matrix[0, 3] += 5.0
    outer = None
    if nested or link in ("part", "assembly"):  # the link sits in a part that is itself rotated and moved
        outer = np.array([[0, -1, 0, 100.0], [1, 0, 0, -20.0], [0, 0, 1, 5.0], [0, 0, 0, 1]])
        matrix = np.linalg.inv(outer) @ matrix
    spec = {"out": str(cad_dir), "dims": dict(DIMS, length=sheet_value if sheet_value else DIMS["length"]),
            "refs": {"length": "/links/link-2.md#lenght"} if bad_ref else {}, "free_pad": free_pad,
            "matrix": matrix.reshape(-1).tolist(), "unnamed": unnamed, "sheet_name": sheet_name,
            "indirect": indirect, "omit_link": omit_link, "link": link, "asm_sheet": asm_sheet, "outer": None if outer is None else outer.reshape(-1).tolist()}
    script = tmp / "build_cad.py"
    script.write_text(SCRIPT)
    done = subprocess.run(["freecadcmd", str(script)], env=dict(os.environ, TWIN_CAD_SPEC=json.dumps(spec)),
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    assert (cad_dir / "ar4.FCStd").is_file(), done.stdout + done.stderr
    if not headless:
        results = guisave.guisave(guisave.documents(cad_dir))
        assert all(r.get("ok") for r in results), results
    write_stl(cad_dir / "link-2.stl", 280, 40, 36 if stale_export else 30)
    if corrupt:
        (cad_dir / "link-2.FCStd").write_bytes(b"this is not a FreeCAD document")
    return cad_dir, kdb_dir
