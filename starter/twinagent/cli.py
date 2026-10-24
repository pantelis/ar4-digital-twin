"""The twin command: ingest and cad."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from kdb_tools import config, guard

from . import cad, freecad, ingest

DEFAULT_FREECAD = ["docker/run.sh", "twin-blwfish"]


def freecad_command(path: Path) -> list[str]:
    raw = tomllib.loads(Path(path).read_text())
    return list(raw.get("freecad", DEFAULT_FREECAD))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="twin")
    p.add_argument("--kdb", type=Path, default=Path("kdb"), help="the kDB bundle")
    p.add_argument("--config", type=Path, default=Path("kdb.toml"))
    p.add_argument("--repo", type=Path, default=Path("."), help="the project repository, mounted at /work in the container")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ingest", help="add the numbers in one document to the kDB")
    i.add_argument("document", type=Path)
    c = sub.add_parser("cad", help="model one link in FreeCAD from its kDB page")
    c.add_argument("link", help="the Link page, such as links/link-2.md")
    args = p.parse_args(argv)
    try:
        cfg = config.load(args.config)
        if args.cmd == "ingest":
            found = ingest.ingest(args.kdb, args.document, cfg)
            print(f"{len(found.from_text)} quantities from text, {len(found.from_cells)} from cells")
        else:
            tools = freecad.toolset(freecad_command(args.config), cwd=str(args.repo))
            agent = cad.make_agent(config.model_from(cfg), tools, config.settings_from(cfg))
            part = cad.build_part(agent, args.repo.resolve(), args.kdb.resolve(), args.link)
            print(part.model_dump_json(indent=1))
    except NotImplementedError as e:
        print(f"twin {args.cmd}: not written yet: {e}", file=sys.stderr)
        return 2
    except (guard.PromptTooLong, config.ConfigError) as e:
        print(f"twin {args.cmd}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
