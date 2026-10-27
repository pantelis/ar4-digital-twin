"""The ar4 profile: the AR4 kDB's page rules, registered with kdb-tools as a profile.

A page states its numbers under quantities. Each quantity has a value, a unit from
twin_tools.units, and either the id of a source on the page that states it, or a formula over
other quantities that the checker recomputes:

    quantities:
      upper_limit: {value: 90, unit: deg, source: manual-p37-2}
      velocity_limit: {value: 180, unit: deg/s, formula: "6 * /motors/j2.md#max_speed / /gearboxes/j2.md#ratio"}

A formula refers to a quantity as <page path from the bundle root>#<name> and uses the values as
written, so it carries its own unit factors (6 turns rpm into deg/s). It may use numbers, + - * /
** and parentheses, nothing else.
"""

from __future__ import annotations

import ast
import operator
import re

from kdb_tools import bundle as B
from kdb_tools.profile import Profile
from kdb_tools.report import Report

from . import units as U

# page type: {quantity: the kind of unit it must have}, and the links it must have to other page types
REQUIRED = {
    "Joint": {"lower_limit": "angle", "upper_limit": "angle", "velocity_limit": "angular speed", "effort_limit": "torque",
              "dh_theta_offset": "angle", "dh_alpha": "angle", "dh_d": "length", "dh_a": "length"},
    "Material": {"density": "density"},
    "Gearbox": {"ratio": "ratio"},
    "Gripper": {"jaw_stroke": "length", "jaw_force": "force", "jaw_speed": "speed"},
}
LINKS = {"Joint": {"parent": "Link", "child": "Link"}, "Link": {"material": "Material"},
         "Gripper": {"material": "Material"}}

REF = re.compile(r"(/[\w./-]+\.md)#(\w+)")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
TOLERANCE = 1e-6  # relative, between a formula's stated value and its recomputed value


class FormulaError(ValueError):
    pass


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def pages_by_rel(b: B.Bundle) -> dict[str, B.Page]:
    index = getattr(b, "_ar4_pages", None)
    if index is None:
        index = {p.rel: p for p in b.concepts}
        b._ar4_pages = index
    return index


def target(b: B.Bundle, page: B.Page, value) -> B.Page | None:
    if not isinstance(value, str):
        return None
    path = B.resolve(b.root, page.rel, value)
    if path is None or not path.is_relative_to(b.root.resolve()):
        return None
    return pages_by_rel(b).get(path.relative_to(b.root.resolve()).as_posix())


def evaluate(b: B.Bundle, formula: str) -> float:
    """The formula's value, from the stated values of the quantities it names."""
    names: dict[str, float] = {}

    def name_for(m: re.Match) -> str:
        page = pages_by_rel(b).get(m.group(1).lstrip("/"))
        if page is None:
            raise FormulaError(f"{m.group(1)} is not a page")
        found = ((page.frontmatter or {}).get("quantities") or {}).get(m.group(2))
        if not isinstance(found, dict) or not is_number(found.get("value")):
            raise FormulaError(f"{m.group(1)} has no quantity {m.group(2)} with a number value")
        key = f"q{len(names)}"
        names[key] = float(found["value"])
        return key

    try:
        tree = ast.parse(REF.sub(name_for, formula), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"cannot parse it: {exc.msg}") from exc

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and is_number(node.value):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](walk(node.operand))
        raise FormulaError("it may use only numbers, quantities written as /<page>.md#<name>, + - * / ** and parentheses")

    try:
        return walk(tree)
    except ZeroDivisionError as exc:
        raise FormulaError("it divides by zero") from exc


def check_quantity(b: B.Bundle, page: B.Page, name: str, q, report: Report) -> None:
    where = f"quantity {name}"
    if not isinstance(q, dict):
        report.error("ar4.quantity", page.rel, f"{where} is a mapping with value, unit and source or formula")
        return
    if not is_number(q.get("value")):
        report.error("ar4.quantity", page.rel, f"{where}: value is a number")
    if U.kind(q.get("unit")) is None:
        report.error("ar4.quantity", page.rel, f"{where}: unit '{q.get('unit')}' is not one of {', '.join(U.UNITS)}")
    if ("source" in q) == ("formula" in q):
        report.error("ar4.quantity", page.rel, f"{where} needs either a source or a formula, not both and not neither")
    elif "source" in q and q["source"] not in page.source_ids:
        report.error("ar4.quantity", page.rel, f"{where} cites '{q['source']}', which is not a source on this page")
    elif "formula" in q:
        if not isinstance(q["formula"], str):
            report.error("ar4.formula", page.rel, f"{where}: formula is a string")
            return
        try:
            got = evaluate(b, q["formula"])
        except FormulaError as exc:
            report.error("ar4.formula", page.rel, f"{where}: formula '{q['formula']}': {exc}")
            return
        if is_number(q.get("value")) and abs(got - q["value"]) > TOLERANCE * max(1.0, abs(got)):
            report.error("ar4.formula", page.rel, f"{where} is {q['value']}, but its formula gives {got:.6g}")


def check_page(b: B.Bundle, page: B.Page, report: Report) -> None:
    fm = page.frontmatter
    kind = fm.get("type")
    quantities = fm.get("quantities", {})
    if not isinstance(quantities, dict):
        report.error("ar4.quantity", page.rel, "quantities is a mapping from a name to its value, unit and source")
        quantities = {}
    for name, q in quantities.items():
        check_quantity(b, page, name, q, report)
    for name, wanted in REQUIRED.get(kind, {}).items():
        q = quantities.get(name)
        if not isinstance(q, dict):
            report.error("ar4.required", page.rel, f"a {kind} needs the quantity {name}")
        elif U.kind(q.get("unit")) not in (None, wanted):
            report.error("ar4.required", page.rel, f"{name} is a {wanted}, but its unit '{q['unit']}' is a {U.kind(q['unit'])}")
    for field, wanted in LINKS.get(kind, {}).items():
        if field not in fm:
            report.error("ar4.required", page.rel, f"a {kind} needs {field}, the path of its {wanted} page")
            continue
        found = target(b, page, fm[field])
        if found is None or (found.frontmatter or {}).get("type") != wanted:
            report.error("ar4.link", page.rel, f"{field} is '{fm[field]}'; it must be the path of a {wanted} page")


PROFILE = Profile("ar4", check_page=check_page)
