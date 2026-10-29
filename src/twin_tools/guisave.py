"""Save FreeCAD documents once with the GUI, so they open in GUI FreeCAD as they were built.

    twin-guisave [cad] [--json]

freecadcmd, and the FreeCAD MCP server that runs on it, save a document without GuiDocument.xml, the view state
GUI FreeCAD restores on opening. GUI FreeCAD then opens every part hidden, and an Assembly's joints have no view
provider: no joint markers, and the Assembly workbench's simulation fails. twin-guisave opens each .FCStd under
cad (the folder, its subfolders such as cad/gripper/, or one file) in GUI FreeCAD on a virtual display (Xvfb),
shows the parts, gives each joint its view provider, solves each assembly, and saves. Part documents go first and
assemblies last. Run it after every change to cad/ and before twin-sync, which reports a document without
GuiDocument.xml (sync.gui). Run it in the project container, which has GUI FreeCAD and xvfb; TWIN_FREECAD_GUI names
another GUI FreeCAD binary. The exit status is 0 when every document was saved, 1 when one was not and 2 when the
tool could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TIMEOUT = 900  # s for the whole GUI run
GUI_SCRIPT = Path(__file__).with_name("guisave_gui.py")


def is_assembly(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return b"Assembly::AssemblyObject" in z.read("Document.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        return False


def documents(cad: Path) -> list[Path]:
    """The documents to save, parts before assemblies, so an assembly saves after the parts it links."""
    docs = [cad] if cad.is_file() else sorted(cad.rglob("*.FCStd"))
    return sorted(docs, key=lambda d: (is_assembly(d), str(d)))


def gui_binary() -> str | None:
    return os.environ.get("TWIN_FREECAD_GUI") or shutil.which("freecad") or shutil.which("FreeCAD")


def _xvfb() -> tuple[subprocess.Popen, str]:
    """Start Xvfb on a free display it picks itself (-displayfd); returns the process and the DISPLAY value."""
    exe = shutil.which("Xvfb")
    if exe is None:
        raise RuntimeError("Xvfb is not installed; run twin-guisave in the project container")
    read, write = os.pipe()
    proc = subprocess.Popen([exe, "-displayfd", str(write), "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                            pass_fds=(write,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(write)
    with os.fdopen(read) as f:
        number = f.readline().strip()
    if not number:
        proc.kill()
        raise RuntimeError("Xvfb did not start")
    return proc, f":{number}"


def guisave(docs: list[Path]) -> list[dict]:
    """Save each document once with the GUI; one result per document. Raises RuntimeError when the run fails."""
    exe = gui_binary()
    if exe is None:
        raise RuntimeError("GUI FreeCAD (freecad) is not installed; run twin-guisave in the project container")
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "result.json"
        xvfb, display = _xvfb()
        env = dict(os.environ, TWIN_GUISAVE_FILES=json.dumps([str(d.resolve()) for d in docs]),
                   TWIN_GUISAVE_RESULT=str(result), QT_QPA_PLATFORM="xcb", DISPLAY=display)
        try:
            done = subprocess.run([exe, str(GUI_SCRIPT)], env=env, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"GUI FreeCAD took more than {TIMEOUT} s") from None
        finally:
            xvfb.terminate()
            xvfb.wait(timeout=30)
        if not result.is_file():
            tail = (done.stderr or done.stdout or "no output").strip().splitlines()[-5:]
            raise RuntimeError(f"GUI FreeCAD exited {done.returncode} without a result: {' | '.join(tail)}")
        return json.loads(result.read_text())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-guisave", description=__doc__.split("\n\n")[0])
    p.add_argument("cad", type=Path, nargs="?", default=Path("cad"), help="a folder of .FCStd files, or one file (default: cad)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if not a.cad.exists():
        print(f"twin-guisave: no such file or folder {a.cad}", file=sys.stderr)
        return 2
    docs = documents(a.cad)
    if not docs:
        print(f"twin-guisave: no .FCStd under {a.cad}", file=sys.stderr)
        return 2
    try:
        results = guisave(docs)
    except RuntimeError as e:
        print(f"twin-guisave: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(results))
    else:
        for r in results:
            if r.get("ok"):
                print(f"saved {r['path']}" + (f": {r['joints']} joints, solve {r['solve']}" if r.get("joints") else ""))
            else:
                print(f"failed {r['path']}: {r.get('error')}")
    failed = [r for r in results if not r.get("ok") or any(s != 0 for s in r.get("solve", []))]
    return 1 if failed or len(results) != len(docs) else 0


if __name__ == "__main__":
    sys.exit(main())
