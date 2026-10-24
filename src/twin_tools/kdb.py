"""Read the twin's numbers from the kDB, in SI units, so twin-check can trace each one to its page.

    from twin_tools.kdb import si
    upper = si("joints/j2.md", "upper_limit")   # 90 deg on the page, 1.5708 rad here

The kDB is the directory kdb/ under the current directory, or the one twin-check --kdb or
TWIN_KDB names. Every value read is recorded; twin-check compares the masses, densities and
joint limits in the Newton model with these reads and reports any value that was typed in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import units as U


class KdbError(LookupError):
    """A page or quantity that is not in the kDB; the message says what is there."""


@dataclass(frozen=True)
class Read:
    page: str
    name: str
    value: float
    unit: str
    si: float


_root: Path | None = None
_reads: list[Read] = []


def use(root: Path | str | None) -> None:
    """Read from this kDB from now on; None goes back to TWIN_KDB or ./kdb."""
    global _root
    _root = Path(root) if root is not None else None


def root() -> Path:
    return _root or Path(os.environ.get("TWIN_KDB", "kdb"))


def reads() -> list[Read]:
    return list(_reads)


def clear() -> None:
    _reads.clear()


def page(rel: str) -> tuple[dict, str]:
    """A page's frontmatter and body."""
    base = root().resolve()
    path = (base / rel.lstrip("/")).resolve()
    if not path.is_file() or not path.is_relative_to(base):
        raise KdbError(f"there is no page {rel} in the kDB at {base}")
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    if not text.startswith("---\n") or end == -1:
        raise KdbError(f"{rel} has no frontmatter")
    fm = yaml.safe_load(text[4:end]) or {}
    return (fm if isinstance(fm, dict) else {}), text[end + 4:].lstrip("-\n")


def quantities(rel: str) -> dict:
    found = page(rel)[0].get("quantities")
    return found if isinstance(found, dict) else {}


def si(page: str, name: str) -> float:
    """The quantity's value converted to SI units (rad, rad/s, N m, kg, m, kg/m^3), recorded for twin-check."""
    found = quantities(page)
    q = found.get(name)
    if not isinstance(q, dict):
        raise KdbError(f"{page} has no quantity {name}; it has {', '.join(found) or 'none'}")
    value, unit = q.get("value"), q.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or unit not in U.UNITS:
        raise KdbError(f"{page} quantity {name} needs a number value and a known unit; run okf-validate")
    out = U.to_si(float(value), unit)
    _reads.append(Read(page.lstrip("/"), name, float(value), unit, out))
    return out
