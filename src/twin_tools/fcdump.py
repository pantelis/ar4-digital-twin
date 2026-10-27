"""Dump what twin-sync needs from one FreeCAD document. Runs under freecadcmd, not under pytest:

    TWIN_FCDUMP_DOC=cad/link-2.FCStd freecadcmd src/twin_tools/fcdump.py

The script is self-contained, because it runs in FreeCAD's Python. It opens the document, recomputes
it and prints one line, TWIN_FCDUMP followed by a JSON object, among FreeCAD's own output. Lengths
are in millimetres, as FreeCAD keeps them.
"""

import json
import os
import re
import traceback

MARK = "TWIN_FCDUMP "
DIMENSIONAL = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")
# TypeId: [(property, the values of the feature's Type under which the property sets its size, None for any)]
FEATURES = {
    "PartDesign::Pad": [("Length", ("Length", "TwoLengths")), ("Length2", ("TwoLengths",))],
    "PartDesign::Pocket": [("Length", ("Length", "TwoLengths")), ("Length2", ("TwoLengths",))],
    "PartDesign::Revolution": [("Angle", ("Angle", "TwoAngles")), ("Angle2", ("TwoAngles",))],
    "PartDesign::Groove": [("Angle", ("Angle", "TwoAngles")), ("Angle2", ("TwoAngles",))],
    "Part::Box": [("Length", None), ("Width", None), ("Height", None)],
    "Part::Cylinder": [("Radius", None), ("Height", None)],
    "Part::Sphere": [("Radius", None)],
    "Part::Cone": [("Radius1", None), ("Radius2", None), ("Height", None)],
}


def _number(v):
    return float(getattr(v, "Value", v))


REFERENCE = re.compile(r"(?:<<([^>]+)>>|\b([A-Za-z_]\w*))\.([\w.\[\]]+)")
DEPTH = 8


def _expressions(obj):
    """The object's expressions by property path. A sketch constraint is stored as Constraints[i] when it has
    no name and as Constraints.name otherwise; the dictionary holds both spellings."""
    out = {path.lstrip("."): expr for path, expr in obj.ExpressionEngine}
    if obj.TypeId == "Sketcher::SketchObject":
        for i, c in enumerate(obj.Constraints):
            found = out.get(f"Constraints[{i}]") or (out.get(f"Constraints.{c.Name}") if c.Name else None)
            if found:
                out[f"Constraints[{i}]"] = found
                if c.Name:
                    out[f"Constraints.{c.Name}"] = found
    return out


def _object(doc, name, label):
    return doc.getObject(name) if name else next((o for o in doc.Objects if o.Label == label), None)


def _reaches(doc, sheet, aliases, expr, depth=DEPTH):
    """True when the expression names a kDB alias, directly or through the expressions of the properties,
    sketch constraints and VarSet entries it reads."""
    for label, name, rest in REFERENCE.findall(expr or ""):
        obj = _object(doc, name, label)
        if obj is None:
            continue
        if obj is sheet:
            if rest.split(".")[0] in aliases:
                return True
        elif depth > 0:
            exprs, path = _expressions(obj), rest
            while path:  # Sketch.Constraints.cw.Value reads the expression of Constraints.cw
                if path in exprs:
                    if _reaches(doc, sheet, aliases, exprs[path], depth - 1):
                        return True
                    break
                path = path.rpartition(".")[0]
    return False


def _text(sheet, cell):
    """A text cell's content without the leading apostrophe FreeCAD keeps in getContents."""
    return sheet.getContents(cell).lstrip("'")


def _kdb_sheet(doc):
    return next((o for o in doc.Objects if o.TypeId == "Spreadsheet::Sheet" and o.Label == "kDB"), None)


def _sheet(sheet):
    if sheet is None:
        return None
    rows = []
    for r in range(1, 501):
        ref = _text(sheet, f"A{r}")
        if not ref:
            continue
        try:
            value = _number(sheet.get(f"B{r}"))
        except Exception:
            value = None
        rows.append({"row": r, "ref": ref, "value": value, "unit": _text(sheet, f"C{r}"),
                     "alias": sheet.getAlias(f"B{r}")})
    return rows


def _dimensions(doc, sheet):
    aliases = {r["alias"] for r in _sheet(sheet) or [] if r["alias"]}
    out = []
    for o in doc.Objects:
        expr = _expressions(o)
        if o.TypeId == "Sketcher::SketchObject":
            for i, c in enumerate(o.Constraints):
                if c.Type in DIMENSIONAL and c.Driving and _number(c.Value) != 0:
                    e = expr.get(f"Constraints[{i}]")
                    out.append({"object": o.Label, "name": c.Name or f"constraint {i + 1}", "type": c.Type, "value": _number(c.Value),
                                "expression": e, "bound": _reaches(doc, sheet, aliases, e)})
        for prop, types in FEATURES.get(o.TypeId, []):
            if types is not None and str(o.Type) not in types:
                continue
            if _number(getattr(o, prop)) != 0:
                out.append({"object": o.Label, "name": prop, "type": o.TypeId, "value": _number(getattr(o, prop)),
                            "expression": expr.get(prop), "bound": _reaches(doc, sheet, aliases, expr.get(prop))})
    return out


def _volume(doc):
    """The volume of the final solid: the first Body's shape, else a top-level object's single solid."""
    bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
    top = [o for o in doc.Objects if not o.InList and hasattr(o, "Shape") and not o.Shape.isNull() and o.Shape.Solids]
    for o in bodies + top:
        if hasattr(o, "Shape") and not o.Shape.isNull() and o.Shape.Solids:
            return sum(s.Volume for s in o.Shape.Solids)
    return None


def _global(o):
    """The object's placement in the document. App::Link has no getGlobalPlacement in FreeCAD 1.1, so it
    is composed from the placement of the Part or Assembly it sits in."""
    if hasattr(o, "getGlobalPlacement"):
        return o.getGlobalPlacement()
    parent = o.getParentGeoFeatureGroup()
    return parent.getGlobalPlacement() * o.Placement if parent else o.Placement


def _placements(doc):
    out = []
    for o in doc.Objects:
        if o.TypeId in ("Spreadsheet::Sheet", "App::Origin", "App::Line", "App::Plane", "App::Point") or not hasattr(o, "Placement"):
            continue
        m = _global(o).toMatrix()
        out.append({"label": o.Label, "matrix": [m.A11, m.A12, m.A13, m.A14, m.A21, m.A22, m.A23, m.A24,
                                                  m.A31, m.A32, m.A33, m.A34, m.A41, m.A42, m.A43, m.A44]})
    return out


def dump(path):
    import FreeCAD

    doc = FreeCAD.openDocument(path)
    doc.recompute()
    sheet = _kdb_sheet(doc)
    return {"path": path, "error": None, "spreadsheet": _sheet(sheet), "dimensions": _dimensions(doc, sheet),
            "invalid": [o.Label for o in doc.Objects if not o.isValid()], "volume": _volume(doc),
            "placements": _placements(doc)}


def main():
    path = os.environ["TWIN_FCDUMP_DOC"]
    try:
        out = dump(path)
    except Exception:
        out = {"path": path, "error": traceback.format_exc(limit=3)}
    print(MARK + json.dumps(out), flush=True)


if "TWIN_FCDUMP_DOC" in os.environ:
    main()
