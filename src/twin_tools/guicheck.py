"""twin-sync's sync.gui rule: every FreeCAD document under cad/ was saved once with the GUI.

freecadcmd, and the FreeCAD MCP server that runs on it, save a document without GuiDocument.xml. GUI FreeCAD then
opens its parts hidden, and an Assembly's joints get no view provider, so they draw no markers and the Assembly
workbench's simulation fails. twin-guisave saves each document with the GUI. This rule reads only the zip and its
XML, so it needs no FreeCAD:

    a document with no GuiDocument.xml
    an Assembly joint (JointObject.Joint or GroundedJoint in Document.xml) with no view provider of its class
    (JointObject.ViewProviderJoint or ViewProviderGroundedJoint) in GuiDocument.xml, or one that is hidden

It checks every .FCStd under cad/, subfolders such as cad/gripper/ included.
"""
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

VIEW_CLASS = {"Joint": "ViewProviderJoint", "GroundedJoint": "ViewProviderGroundedJoint"}
FIX = "open and save it with GUI FreeCAD: run twin-guisave"


def _proxies(root: ET.Element, tag: str) -> dict[str, tuple[str, str]]:
    """name -> (module, class) of the Python proxy of each <tag name=...> element that has one."""
    out = {}
    for el in root.iter(tag):
        for prop in el.iter("Property"):
            if prop.get("name") == "Proxy":
                py = prop.find("Python")
                if py is not None and el.get("name"):
                    out[el.get("name")] = (py.get("module", ""), py.get("class", ""))
    return out


def _hidden(root: ET.Element) -> set[str]:
    hidden = set()
    for el in root.iter("ViewProvider"):
        for prop in el.iter("Property"):
            if prop.get("name") == "Visibility":
                b = prop.find("Bool")
                if b is not None and b.get("value") == "false":
                    hidden.add(el.get("name"))
    return hidden


def check(path: Path, report, unreadable: bool = True) -> None:
    """Report sync.gui findings on one document. unreadable=False skips a file that is not a FreeCAD zip, for a
    caller (twin-sync on the top of cad/) that reports it as sync.load already."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            document = ET.fromstring(z.read("Document.xml"))
            gui = ET.fromstring(z.read("GuiDocument.xml")) if "GuiDocument.xml" in names else None
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError) as e:
        if unreadable:
            report.error("sync.gui", str(path), f"cannot read the document: {e}")
        return
    if gui is None:
        report.error("sync.gui", str(path), "was saved without the GUI: it has no GuiDocument.xml, so GUI FreeCAD "
                                            f"opens its parts hidden and its joints with no markers; {FIX}")
        return
    joints = {name: cls for name, (module, cls) in _proxies(document, "Object").items()
              if module == "JointObject" and cls in VIEW_CLASS}
    views, hidden = _proxies(gui, "ViewProvider"), _hidden(gui)
    missing = sorted(n for n, cls in joints.items() if views.get(n) != ("JointObject", VIEW_CLASS[cls]))
    invisible = sorted(n for n in joints if n not in missing and n in hidden)
    if missing:
        report.error("sync.gui", str(path), f"joints with no view provider, so no markers and no simulation: "
                                            f"{', '.join(missing)}; {FIX}")
    if invisible:
        report.error("sync.gui", str(path), f"hidden joints: {', '.join(invisible)}; {FIX}")


def documents(cad: Path) -> list[Path]:
    return sorted(cad.rglob("*.FCStd"))


def check_all(cad: Path, report, top_level_loaded: bool = False) -> None:
    """check() on every .FCStd under cad. With top_level_loaded, an unreadable file at the top of cad is left to
    sync.load."""
    for doc in documents(cad):
        check(doc, report, unreadable=not (top_level_loaded and doc.parent == cad))
