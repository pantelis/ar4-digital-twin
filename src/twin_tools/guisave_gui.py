"""Run inside GUI FreeCAD by twin-guisave (see guisave.py); never imported by the other tools.

For each document in TWIN_GUISAVE_FILES (a JSON list, parts before assemblies) it opens the document with the GUI
up, shows the parts, gives every Assembly joint its view provider (JointObject.ViewProviderJoint, or
ViewProviderGroundedJoint for a grounded joint) so its markers draw, saves the document and closes it. A document
saved with the GUI holds GuiDocument.xml, the view state that FreeCAD restores on opening. Without it, which is
what freecadcmd writes, the GUI opens the parts hidden and the joints with no view provider. The result, one
entry per document, goes to the JSON file TWIN_GUISAVE_RESULT. Then FreeCAD exits.
"""
import json
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui

HIDDEN_TYPES = ("App::Origin", "App::Line", "App::Plane", "App::Point", "Spreadsheet::Sheet", "App::VarSet")


def _show(obj, visible: bool) -> None:
    obj.Visibility = visible
    vo = getattr(obj, "ViewObject", None)
    if vo is not None:
        vo.Visibility = visible


def _proxy_class(obj) -> str:
    proxy = getattr(obj, "Proxy", None)
    return "" if proxy is None or isinstance(proxy, int) else type(proxy).__name__


def show_parts(doc) -> None:
    """What the GUI shows after a person builds the part: each Body and its tip, top-level shapes, Links and the
    assembly; never origins, sketches or sheets."""
    in_body = set()
    for obj in doc.Objects:
        if obj.TypeId == "PartDesign::Body":
            for feature in obj.Group:
                in_body.add(feature.Name)
                _show(feature, feature is obj.Tip)
            _show(obj, True)
    for obj in doc.Objects:
        if obj.Name in in_body or obj.TypeId == "PartDesign::Body":
            continue
        if obj.TypeId in HIDDEN_TYPES or obj.TypeId.startswith("Sketcher::") or _proxy_class(obj) in ("Joint", "GroundedJoint"):
            continue
        if obj.isDerivedFrom("Part::Feature") or obj.TypeId in ("App::Link", "App::Part", "Assembly::AssemblyObject",
                                                                  "Assembly::JointGroup"):
            _show(obj, True)


def attach_joints(doc) -> int:
    """Give each Assembly joint its view provider, as the Assembly workbench does when a person adds the joint."""
    import JointObject

    count = 0
    for obj in doc.Objects:
        kind = _proxy_class(obj)
        if kind not in ("Joint", "GroundedJoint"):
            continue
        vo = obj.ViewObject
        want = JointObject.ViewProviderJoint if kind == "Joint" else JointObject.ViewProviderGroundedJoint
        if not isinstance(getattr(vo, "Proxy", None), want):
            want(vo)
        proxy = vo.Proxy
        if kind == "Joint":
            if not hasattr(proxy, "switch_JCS1"):  # FreeCAD attaches when the proxy is set; attach once if it did not
                proxy.attach(vo)
            if vo.DisplayMode != "Wireframe":
                try:  # the proxy's only display mode, which draws the markers
                    vo.DisplayMode = "Wireframe"
                except ValueError:
                    pass
            proxy.redrawJointPlacements(obj)
        elif not hasattr(proxy, "app_obj"):
            proxy.attach(vo)
        _show(obj, True)
        count += 1
    return count


def _close_all() -> None:
    for name in list(App.listDocuments()):
        App.closeDocument(name)


def _save_once(path: str) -> dict:
    """Open, show, attach, solve and save; return what was done."""
    entry = {}
    doc = App.openDocument(path)
    Gui.getDocument(doc.Name)  # the GUI document exists, so saving writes GuiDocument.xml
    show_parts(doc)
    entry["joints"] = attach_joints(doc)
    doc.recompute()
    assemblies = [o for o in doc.Objects if o.TypeId == "Assembly::AssemblyObject"]
    entry["solve"] = [a.solve() for a in assemblies]
    if entry["joints"]:
        attach_joints(doc)  # solving moves the parts; redraw the markers where they now are
        joints = [o for o in doc.Objects if _proxy_class(o) == "Joint"]
        entry["display"] = sorted({str(o.ViewObject.DisplayMode) for o in joints})
        entry["markers"] = sum(1 for o in joints if o.ViewObject.Proxy.switch_JCS1.whichChild.getValue() != -1)
    doc.save()
    return entry


def main() -> None:
    files = json.loads(os.environ["TWIN_GUISAVE_FILES"])
    out = []
    for path in files:
        entry = {"path": path}
        try:
            entry.update(_save_once(path))
            _close_all()
            if entry.get("joints"):
                # A view provider attached to an object that already had one keeps an empty display mode list, so
                # the markers do not draw. Opening the saved file again creates each joint's view provider from
                # GuiDocument.xml, with its proxy from the start, as when a person adds the joint. Save that.
                entry["first"] = {k: entry[k] for k in ("display", "markers")}
                entry.update(_save_once(path))
            entry["ok"] = True
        except Exception as e:  # one bad document is a result, not a crash
            entry.update(ok=False, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc())
        finally:
            _close_all()
        out.append(entry)
    with open(os.environ["TWIN_GUISAVE_RESULT"], "w") as f:
        json.dump(out, f)


try:
    main()
finally:
    os._exit(0)
