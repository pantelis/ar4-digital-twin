"""Find where the FreeCAD documents have drifted from the kDB.

    twin-sync [cad] [--json] [--kdb kdb]

cad is a directory of one document per link, cad/<page stem>.FCStd with the mesh cad/<page stem>.stl
beside it, for kdb/links/<page stem>.md, and the assembly cad/ar4.FCStd. Run it where freecadcmd is
installed, such as the project container. The rules:

    sync.ref     a cell in column A of the document's kDB spreadsheet names no kDB quantity
    sync.value   the value in column B, in the unit in column C, differs from the kDB value
    sync.free    a dimensional sketch constraint or a feature dimension (Pad and Pocket lengths,
                 Revolution and Groove angles, Box, Cylinder, Sphere and Cone sizes) has no
                 expression that reaches a kDB alias
    sync.export  the STL's volume differs from the recomputed solid's by more than 0.5%
    sync.frame   in the assembly, a link's placement differs from its DH frame at q = 0
    sync.load    a document that FreeCAD cannot open or recompute, or freecadcmd missing
    sync.gui     a document anywhere under cad, cad/gripper/ included, saved without the GUI (no
                 GuiDocument.xml), or an Assembly joint with no view provider or hidden (twin_tools.guicheck);
                 twin-guisave fixes it

The kDB spreadsheet is the sheet labeled kDB. Row r holds the quantity's reference in A, such as
/links/link-2.md#length, its value in B with an alias, and the value's unit in C. The assembly gets
sync.ref and sync.value for its own kDB sheet when it has one; an assembly without one is not a
finding, and sync.free and sync.export do not apply to it. The assembly's
link is the top-level object whose label is the link page's stem. Frame n is the child link of
joints/j<n>.md, and the link page named base is frame 0. Meshes are in millimetres, as FreeCAD exports them.
The exit status is 0 when there are no findings, 1 when there are findings and 2 when the tool could not run.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import posixpath
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import yaml

from . import dh, guicheck
from . import kdb as K
from . import units as U
from .check import Report

ASSEMBLY = "ar4"
TIMEOUT = 300  # s per document
VALUE_TOLERANCE = 1e-9  # relative
EXPORT_TOLERANCE = 0.005  # relative volume
FRAME_TOLERANCE = 1e-6  # m and rad
MARK = "TWIN_FCDUMP "


def _dump(doc: Path) -> dict:
    """What fcdump reads from one document; raises RuntimeError with the reason when it cannot."""
    exe = shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if exe is None:
        raise RuntimeError("freecadcmd is not installed; run twin-sync in the project container")
    script = Path(__file__).with_name("fcdump.py")
    try:
        done = subprocess.run([exe, str(script)], env=dict(os.environ, TWIN_FCDUMP_DOC=str(doc.resolve())),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"freecadcmd took more than {TIMEOUT} s") from None
    lines = [line[len(MARK):] for line in done.stdout.splitlines() if line.startswith(MARK)]
    if not lines:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"freecadcmd exited {done.returncode} without a dump ({tail[0]})")
    out = json.loads(lines[-1])
    if out.get("error"):
        raise RuntimeError(out["error"].strip().splitlines()[-1])
    return out


def _stl_volume(path: Path) -> float:
    """The volume of a closed binary or ASCII STL, in its own units cubed."""
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else -1
    if len(data) == 84 + 50 * n:
        tri = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)["v"]
    else:
        text = data.decode("ascii", errors="replace")
        tri = np.array([float(x) for m in re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text) for x in m]).reshape(-1, 3, 3)
    tri = tri.astype(float)
    return abs(float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()) / 6)


def _check_rows(doc: Path, dump: dict, report: Report) -> None:
    """sync.ref and sync.value for the kDB spreadsheet's rows."""
    rows = dump["spreadsheet"]
    if rows is None:
        report.error("sync.ref", str(doc), "has no spreadsheet labeled kDB")
        return
    for row in rows:
        where = f"row {row['row']} ({row['ref']})"
        page, _, name = row["ref"].partition("#")
        try:
            q = K.quantities(page).get(name)
        except (K.KdbError, yaml.YAMLError) as e:
            report.error("sync.ref", str(doc), f"{where}: {e}")
            continue
        if not isinstance(q, dict) or not isinstance(q.get("value"), (int, float)) or q.get("unit") not in U.UNITS:
            report.error("sync.ref", str(doc), f"{where}: {page} has no quantity {name} with a number and a known unit")
            continue
        if row["value"] is None or row["unit"] not in U.UNITS:
            report.error("sync.value", str(doc), f"{where}: column B needs a number and column C a unit from twin_tools.units")
            continue
        have, want = U.to_si(row["value"], row["unit"]), U.to_si(float(q["value"]), q["unit"])
        if not math.isclose(have, want, rel_tol=VALUE_TOLERANCE, abs_tol=1e-12):
            report.error("sync.value", str(doc), f"{where}: the sheet has {row['value']:g} {row['unit']} but the kDB has {q['value']:g} {q['unit']}")


def _check_free(doc: Path, dump: dict, report: Report) -> None:
    for d in dump["dimensions"]:
        if not d["bound"]:
            how = f"the expression {d['expression']}" if d["expression"] else "no expression"
            report.error("sync.free", str(doc), f"{d['object']} {d['name']} ({d['type']}, {d['value']:g}) has {how}, which does not reach a kDB alias; bind it to the spreadsheet")


def _check_export(doc: Path, dump: dict, report: Report) -> None:
    stl = doc.with_suffix(".stl")
    if dump["volume"] is None:
        report.error("sync.load", str(doc), "has no solid after recompute")
    elif not stl.is_file():
        report.error("sync.export", str(doc), f"has no mesh {stl.name} beside it")
    else:
        try:
            have = _stl_volume(stl)
        except Exception as e:
            report.error("sync.export", str(doc), f"{stl.name} cannot be read: {e}")
            return
        if abs(have - dump["volume"]) > EXPORT_TOLERANCE * dump["volume"]:
            report.error("sync.export", str(doc), f"{stl.name} has volume {have:.6g} mm^3 but the recomputed part has {dump['volume']:.6g}; export it again")


def _link_frames(kdb: Path) -> dict[str, int]:
    """Link page stem to its frame number: the base is 0 and joints/j<n>.md's child is n."""
    out = {"base": 0}
    for page in sorted((kdb / "joints").glob("j*.md")):
        m = re.fullmatch(r"j(\d+)", page.stem)
        try:
            child = K.page(f"joints/{page.name}")[0].get("child")
        except (K.KdbError, yaml.YAMLError):
            continue
        if m and isinstance(child, str):
            out[Path(posixpath.normpath(posixpath.join("joints", child))).stem] = int(m.group(1))
    return out


def _check_frames(doc: Path, dump: dict, stems: list[str], kdb: Path, report: Report) -> None:
    """Every link document in cad/ must be base or a joint's child, and placed in the assembly at its DH frame."""
    numbers = _link_frames(kdb)
    placed = {}
    for p in dump["placements"]:
        placed.setdefault(p["label"], p)
    rows: list[dh.DH] = []
    for stem in stems:
        p = placed.get(stem)
        if p is None:
            report.error("sync.frame", str(doc), f"{stem} has a document but is not in the assembly; place it at its DH frame")
            continue
        n = numbers.get(stem)
        if n is None:
            report.error("sync.frame", str(doc), f"{stem} is neither base nor the child of a joint page, so it has no DH frame; name the document after its link page")
            continue
        try:
            while len(rows) < n:
                rows.append(dh.row(f"joints/j{len(rows) + 1}.md"))
        except K.KdbError as e:
            report.error("sync.frame", str(doc), f"{stem} is frame {n}, which needs joints j1 to j{n}: {e}")
            continue
        want = dh.frames(rows[:n], [0.0] * n)[n]
        have = np.array(p["matrix"]).reshape(4, 4)
        have[:3, 3] *= 1e-3
        shift = float(np.abs(have[:3, 3] - want[:3, 3]).max())
        r = have[:3, :3].T @ want[:3, :3]
        skew = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]) / 2
        turn = math.atan2(float(np.linalg.norm(skew)), (np.trace(r) - 1) / 2)
        if shift > FRAME_TOLERANCE or turn > FRAME_TOLERANCE:
            report.error("sync.frame", str(doc), f"{stem} is {shift * 1e3:.4g} mm and {turn:.4g} rad off DH frame {n}; its origin belongs at the joint's frame")


def sync(cad: Path, kdb: Path) -> Report:
    report = Report(tool="twin-sync")
    K.use(kdb)
    try:
        return _sync(cad, kdb, report)
    finally:
        K.use(None)


def _sync(cad: Path, kdb: Path, report: Report) -> Report:
    docs = sorted(cad.glob("*.FCStd"))
    stems = [d.stem for d in docs if d.stem != ASSEMBLY]
    report.summary["documents"] = len(docs)
    guicheck.check_all(cad, report, top_level_loaded=True)
    for doc in docs:
        try:
            dump = _dump(doc)
        except RuntimeError as e:
            report.error("sync.load", str(doc), str(e))
            continue
        except (json.JSONDecodeError, OSError) as e:
            report.error("sync.load", str(doc), f"fcdump failed: {e}")
            continue
        if dump["invalid"]:
            report.error("sync.load", str(doc), f"does not recompute: {', '.join(dump['invalid'])}")
        if doc.stem == ASSEMBLY:
            if dump["spreadsheet"] is not None:  # an assembly may bind nothing
                _check_rows(doc, dump, report)
            _check_frames(doc, dump, stems, kdb, report)
            continue
        _check_rows(doc, dump, report)
        _check_free(doc, dump, report)
        _check_export(doc, dump, report)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-sync", description=__doc__.split("\n\n")[0])
    p.add_argument("cad", type=Path, nargs="?", default=Path("cad"), help="the directory of FreeCAD documents (default: cad)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--kdb", type=Path, help="the kDB (default: TWIN_KDB, or kdb/)")
    a = p.parse_args(argv)
    kdb = a.kdb or K.root()
    for path in (a.cad, kdb):
        if not path.is_dir():
            print(f"twin-sync: no such directory {path}", file=sys.stderr)
            return 2
    report = sync(a.cad, kdb)
    if a.json:
        print(json.dumps({"tool": report.tool, "findings": [asdict(f) for f in report.findings], "summary": report.summary}))
    else:
        for f in report.findings:
            print(f"{f.level} {f.rule} {f.path}: {f.message}")
        print(f"{len(report.findings)} findings; " + ", ".join(f"{k} {v}" for k, v in report.summary.items()))
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
