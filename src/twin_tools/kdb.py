"""Read the twin's numbers from the kDB, in SI units, so twin-check can trace each one to its page.

    from twin_tools.kdb import si
    upper = si("joints/j2.md", "upper_limit")   # 90 deg on the page, 1.5708 rad here

The kDB is the directory kdb/ under the current directory, or the one twin-check --kdb or
TWIN_KDB names. Every read is recorded with the float object si() returned. twin-check looks at
the very object the builder received for each mass, density and joint limit, and traces it only
when it is the object a read returned (read_of). So a typed number is untraced even when some read
returned the same number. An operation that computes a value, such as a sum, a product or a
negation, makes a new float, so a value computed from reads is not a read: state it on a page as a
formula quantity and read that instead. A few operations hand back the same object, such as +x,
float(x), min(x, y) or max(x, y). They keep the read's own number, so that does no harm. si()
returns a plain float, so Warp and NumPy take it as they take any number.

The reads live in a private registry. twin-check does not trust it alone: before it traces a value
to a read, it reads that page from disk again, and it checks that the read comes from the page and
quantity the value belongs to.
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


class _Registry:
    """The reads of the current build, in order. Private: twin-check re-reads every read it relies on from disk."""

    __slots__ = ("_items",)

    def __init__(self):
        self._items: list[Read] = []


_root: Path | None = None
_registry = _Registry()


def use(root: Path | str | None) -> None:
    """Read from this kDB from now on; None goes back to TWIN_KDB or ./kdb."""
    global _root
    _root = Path(root) if root is not None else None


def root() -> Path:
    return _root or Path(os.environ.get("TWIN_KDB", "kdb"))


def reads() -> tuple[Read, ...]:
    """A snapshot of the reads so far."""
    return tuple(_registry._items)


def read_of(value) -> Read | None:
    """The read whose si() call returned this very object, or None. Identity, not equality: a typed 40.0 is not
    the 40.0 a read returned, and neither is any number computed from a read."""
    return next((r for r in reversed(_registry._items) if r.si is value), None)


def clear() -> None:
    _registry._items.clear()


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
    """The quantity's value converted to SI units (rad, rad/s, N m, kg, m, kg/m^3), recorded for twin-check.
    Pass the float it returns to the builder unchanged: twin-check traces that object, not its number."""
    found = quantities(page)
    q = found.get(name)
    if not isinstance(q, dict):
        raise KdbError(f"{page} has no quantity {name}; it has {', '.join(found) or 'none'}")
    value, unit = q.get("value"), q.get("unit")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or unit not in U.UNITS:
        raise KdbError(f"{page} quantity {name} needs a number value and a known unit; run okf-validate")
    out = float(U.to_si(float(value), unit)) + 0.0  # a new float object for every call, so read_of tells reads apart
    _registry._items.append(Read(page.lstrip("/"), name, float(value), unit, out))
    return out
