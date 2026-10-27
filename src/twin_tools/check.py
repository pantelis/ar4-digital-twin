"""Load a twin's Newton builder and check the model it builds.

    twin-check twin/build.py [--json] [--seconds 1.0] [--kdb kdb] [--no-trace] [--no-grasp]

The file must define build(builder: newton.ModelBuilder) -> None, which builds the arm with its gripper,
and build_gripper(builder: newton.ModelBuilder) -> wp.transform, which builds the gripper alone, its base
fixed to the world, and returns the grasp frame. The checks:

    build           the module imports, build() runs and the model finalizes
    mass            every link has mass (a link with no shapes and no mass gets 0)
    joint-limits    every revolute and prismatic joint has limits (Newton's default is 1e10)
    effort-limit    every such joint has an effort limit (default 1e6)
    velocity-limit  every such joint has a velocity limit (default 1e6)
    trace           every joint limit, effort limit and velocity limit, every shape density and
                    every link mass set in build() was read from the kDB with twin_tools.kdb.si,
                    from a quantity of the right kind: an angle, a torque and an angular speed for a
                    revolute joint, a length, a force and a speed for a prismatic one, a density for a
                    shape density and a mass for a link mass (a jaw's closed limit of 0 needs no page)
    gripper         build_gripper() exists, both models have prismatic jaws JAW1 and JAW2, the
                    standalone gripper passes the checks above (its findings name it, as in
                    "JAW1 (build_gripper)"), and its jaw limits, effort limits and velocity limits
                    match the gripper on the arm
    kinematics      each joint labeled J<n> turns about the axis that DH row n of the kDB (joints/j<n>.md)
                    puts there, at q = 0. For each present pair J<n-1>, J<n>: the angle between the axes
                    (0 to pi, so a flipped axis counts) equals the magnitude of alpha_(n-1) within KINEMATICS_ANGLE,
                    and the distance between the axis lines equals the magnitude of a_(n-1) within
                    KINEMATICS_DISTANCE. When J1 to J6 are all present, each axis also matches the DH chain in the
                    world, with the base at the world origin: the same direction, with sign, and the DH axis origin on the
                    joint's axis line, wherever along it the joint is anchored
    drop            released at rest under gravity with no drive, the model stays finite and
                    each joint stays within its limits
    grasp           run last, only when nothing else failed: a cube from twin_tools.task sits on the grasp
                    frame with the jaws open. Held open, the jaws must let it fall under gravity along the
                    grasp frame's z (out of the gripper). Closed at their effort limit, they must hold it
                    for 2 s with a slip of at most GRASP_SLIP (5 mm), and once closed neither jaw, with the
                    bodies welded to it, may sink more than GRASP_PENETRATION (2 mm) into the cube. Every shape
                    of the gripper and the cube gets the course's friction CUBE_FRICTION and contact stiffness,
                    whatever the twin sets. --no-grasp skips it

Newton accepts the defaults silently. Every one of these values must come from your kDB, and
the trace check reports any that was typed in or left at a default.
The exit status is 0 when there are no errors, 1 when there are errors and 2 when the tool could not run.
"""

import argparse
import contextlib
import functools
import importlib.util
import inspect
import json
import math
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import NamedTuple

from . import kdb as K
from . import units as U
from .task import CUBE_EDGE, CUBE_FRICTION, CUBE_MASS

UNSET_LIMIT = 1e9   # Newton's default joint limits are +-1e10
UNSET_RATE = 1e6    # and its default effort and velocity limits are 1e6
LIMIT_SLACK = 0.05  # rad or m a joint may overshoot its limit during the drop
TRACE_TOLERANCE = 1e-5  # relative; Newton stores joint values as float32
JAWS = ("JAW1", "JAW2")
STANDALONE = " (build_gripper)"  # added to the path of a finding on the gripper build_gripper() builds alone
KINEMATICS_ANGLE = 1e-4  # rad an axis may differ from its DH row
KINEMATICS_DISTANCE = 1e-4  # m the distance between two axes may differ from its DH row
KINEMATICS_PARALLEL = math.sin(KINEMATICS_ANGLE)  # axes within the angle tolerance of 0 or pi count as parallel
GRASP_SLIP = 0.005  # m the cube may slide in the jaws during the hold
GRASP_FREE_FALL = 0.5  # with the jaws open the cube must fall at least this fraction of the free-fall distance
GRASP_SATURATE = 1e-3  # m of position error at which the jaw drive reaches its effort limit
GRASP_PENETRATION = 0.002  # m a closed jaw may sink into the cube
GRASP_DT = 2.5e-4  # s, the grasp test's time step; light jaws on stiff contacts need a short one
GRASP_CONTACT_TIMECONST = 5e-4  # s, MuJoCo solref time constant of the jaw and cube contacts (_grasp needs dt at most half of it)
GRASP_CONTACT_DAMPRATIO = 1.0  # MuJoCo solref damping ratio of the jaw and cube contacts (1 is critical)


@dataclass
class Finding:
    level: str
    rule: str
    path: str
    message: str


@dataclass
class Report:
    tool: str = "twin-check"
    findings: list[Finding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def error(self, rule, path, message):
        self.findings.append(Finding("error", rule, path, message))


def _load(path: Path) -> tuple[Callable, Callable | None]:
    """The module's build and, when it defines one, its build_gripper."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build = getattr(module, "build", None)
    if not callable(build):
        raise AttributeError("no build(builder) function")
    build_gripper = getattr(module, "build_gripper", None)
    return build, (build_gripper if callable(build_gripper) else None)


def _record_masses(builder) -> dict[int, dict[str, set[float]]]:
    """Wrap the builder's add_shape_* and add_link/add_body methods to record, per body, the densities of
    its shapes and any mass set directly. Newton does not keep shape densities in the finalized model."""
    seen: dict[int, dict[str, set[float]]] = {}

    def entry(body):
        return seen.setdefault(int(body), {"density": set(), "mass": set()})

    def wrap(name, orig):
        sig = inspect.signature(orig)

        @functools.wraps(orig)
        def recorded(*args, **kwargs):
            out = orig(*args, **kwargs)
            try:
                bound = sig.bind_partial(*args, **kwargs).arguments
            except TypeError:
                return out
            if name.startswith("add_shape") and isinstance(bound.get("body"), int) and bound["body"] >= 0:
                cfg = bound.get("cfg") or builder.default_shape_cfg
                if getattr(cfg, "density", 0) > 0:
                    entry(bound["body"])["density"].add(float(cfg.density))
            elif name in ("add_link", "add_body") and isinstance(out, int) and (bound.get("mass") or 0) > 0:
                entry(out)["mass"].add(float(bound["mass"]))
            return out

        return recorded

    for name in dir(builder):
        if name.startswith("add_shape") or name in ("add_link", "add_body"):
            orig = getattr(builder, name)
            if callable(orig):
                setattr(builder, name, wrap(name, orig))
    return seen


def _matches(value: float, reads) -> list:
    """The kDB reads whose SI value equals value."""
    return [r for r in reads if math.isclose(value, r.si, rel_tol=TRACE_TOLERANCE, abs_tol=1e-9)]


def _untraced(what: str, value: float, unit: str, kind: str, reads) -> str | None:
    """None when value was read from a kDB quantity of this kind, else what the finding says about it."""
    found = _matches(value, reads)
    if any(U.kind(r.unit) == kind for r in found):
        return None
    text = f"{what} {value:.6g}{unit}"
    if found:  # a kDB number, but of another kind, such as a density used as a force
        r = found[0]
        text += f" (read from {r.page} {r.name}, {_a(U.kind(r.unit))}, where {_a(kind)} belongs)"
    return text


def _a(word: str) -> str:
    return ("an " if word[0] in "aeiou" else "a ") + word


# The kind of quantity each joint value must be read from, and its SI unit, by joint type.
_JOINT_KINDS = {
    "REVOLUTE": {"limit": ("angle", " rad"), "effort limit": ("torque", " N m"), "velocity limit": ("angular speed", " rad/s")},
    "PRISMATIC": {"limit": ("length", " m"), "effort limit": ("force", " N"), "velocity limit": ("speed", " m/s")},
}


def _trace(model, masses, report, suffix=""):
    import newton

    reads = K.reads()
    types, qd_start = model.joint_type.numpy(), model.joint_qd_start.numpy()
    arrays = {"lower limit": model.joint_limit_lower.numpy(), "upper limit": model.joint_limit_upper.numpy(),
              "effort limit": model.joint_effort_limit.numpy(), "velocity limit": model.joint_velocity_limit.numpy()}
    kinds = {newton.JointType.REVOLUTE: _JOINT_KINDS["REVOLUTE"], newton.JointType.PRISMATIC: _JOINT_KINDS["PRISMATIC"]}
    for j, label in enumerate(model.joint_label):
        if types[j] not in kinds:
            continue
        untraced = []
        for what, values in arrays.items():
            is_limit = what in ("lower limit", "upper limit")
            kind, unit = kinds[types[j]]["limit" if is_limit else what]
            for d in range(qd_start[j], qd_start[j + 1]):
                v = float(values[d])
                unset = abs(v) >= UNSET_LIMIT if is_limit else not 0 < v < UNSET_RATE
                closed_jaw = label in JAWS and what == "lower limit" and v == 0.0  # a jaw's coordinate is its opening
                text = None if unset or closed_jaw else _untraced(what, v, unit, kind, reads)
                if text:
                    untraced.append(text)
        if untraced:
            report.error("trace", label + suffix, f"{', '.join(untraced)} not read from the kDB; read each with twin_tools.kdb.si")
    for body, found in sorted(masses.items()):
        label = model.body_label[body] if body < len(model.body_label) else str(body)
        untraced = [(text + (" (Newton's default)" if v == 1000.0 else ""))
                    for v in sorted(found["density"]) if (text := _untraced("shape density", v, " kg/m^3", "density", reads))]
        untraced += [text for v in sorted(found["mass"]) if (text := _untraced("mass", v, " kg", "mass", reads))]
        if untraced:
            report.error("trace", label + suffix, f"{', '.join(untraced)} not read from the kDB; read each with twin_tools.kdb.si")


def _check_values(model, report, suffix=""):
    import newton

    for i, label in enumerate(model.body_label):
        if model.body_mass.numpy()[i] <= 0:
            report.error("mass", label + suffix, "has no mass: give its shapes a density, or set its mass from a datasheet")
    types, qd_start = model.joint_type.numpy(), model.joint_qd_start.numpy()
    lower, upper = model.joint_limit_lower.numpy(), model.joint_limit_upper.numpy()
    effort, velocity = model.joint_effort_limit.numpy(), model.joint_velocity_limit.numpy()
    limited = []
    for j, label in enumerate(model.joint_label):
        if types[j] not in (newton.JointType.REVOLUTE, newton.JointType.PRISMATIC):
            continue
        dofs = range(qd_start[j], qd_start[j + 1])
        if any(abs(lower[d]) >= UNSET_LIMIT or abs(upper[d]) >= UNSET_LIMIT or lower[d] >= upper[d] for d in dofs):
            report.error("joint-limits", label + suffix, "has no joint limits (Newton's default is +-1e10)")
        else:
            limited.append(j)
        if any(not 0 < effort[d] < UNSET_RATE for d in dofs):
            report.error("effort-limit", label + suffix, "has no effort limit (Newton's default is 1e6)")
        if any(not 0 < velocity[d] < UNSET_RATE for d in dofs):
            report.error("velocity-limit", label + suffix, "has no velocity limit (Newton's default is 1e6)")
    return limited


def _joint_axes(model) -> tuple[dict[int, tuple], dict[int, str]]:
    """World origin and unit direction of each revolute joint labeled J<n>, keyed by n, with every joint at q = 0,
    and the type name of each J<n> that is not revolute. A repeated label is listed with the name "duplicate"."""
    import numpy as np

    import newton
    import warp as wp

    types, q_start = model.joint_type.numpy(), model.joint_q_start.numpy()
    q = model.joint_q.numpy().copy()
    for j in range(model.joint_count):
        if types[j] in (newton.JointType.REVOLUTE, newton.JointType.PRISMATIC):
            q[q_start[j]] = 0.0
    state = model.state()
    newton.eval_fk(model, wp.array(q, dtype=float, device=model.device), model.joint_qd, state)
    body_q, x_p, axis_p, parent = state.body_q.numpy(), model.joint_X_p.numpy(), model.joint_axis.numpy(), model.joint_parent.numpy()
    qd_start = model.joint_qd_start.numpy()
    out, other = {}, {}
    for j, label in enumerate(model.joint_label):
        if not (label[:1] == "J" and label[1:].isdecimal() and label.isascii()):
            continue
        if int(label[1:]) in out or int(label[1:]) in other:
            other[int(label[1:])] = "duplicate"
            continue
        if types[j] != newton.JointType.REVOLUTE:
            other[int(label[1:])] = newton.JointType(int(types[j])).name.lower()
            continue
        frame = body_q[parent[j]] if parent[j] >= 0 else np.array([0.0, 0, 0, 0, 0, 0, 1])
        rot = frame[3:]
        origin = frame[:3] + _rotate(rot, x_p[j][:3])
        direction = _rotate(rot, _rotate(x_p[j][3:], axis_p[qd_start[j]]))
        out[int(label[1:])] = (origin, direction / np.linalg.norm(direction))
    return out, other


def _line_distance(p1, d1, p2, d2) -> float:
    import numpy as np

    n = np.cross(d1, d2)
    if np.linalg.norm(n) < KINEMATICS_PARALLEL:  # parallel lines: the distance from p2 to line 1
        return float(np.linalg.norm(np.cross(p2 - p1, d1)))
    return float(abs(np.dot(p2 - p1, n)) / np.linalg.norm(n))


def _kinematics(path, model, report):
    import numpy as np

    from . import dh

    world, other = _joint_axes(model)
    for n, what in sorted(other.items()):
        report.error("kinematics", path.name, f"J{n} is labeled twice, so its axis cannot be checked" if what == "duplicate"
                     else f"J{n} is a {what} joint, but DH joint {n} is revolute")
    rows = {}
    unreadable = False

    def row(n):
        if n not in rows:
            rows[n] = dh.row(f"joints/j{n}.md")
        return rows[n]

    for n in sorted(world):
        if n - 1 not in world:
            continue
        (p1, d1), (p2, d2) = world[n - 1], world[n]
        try:
            r = row(n - 1)
        except Exception as e:  # a missing or incomplete joint page is a finding, not a crash
            unreadable = True
            report.error("kinematics", path.name, f"J{n}: cannot read DH row {n - 1} from joints/j{n - 1}.md: {type(e).__name__}: {e}")
            continue
        angle = float(np.arccos(np.clip(np.dot(d1, d2), -1.0, 1.0)))
        if abs(angle - abs(r.alpha)) > KINEMATICS_ANGLE:
            report.error("kinematics", path.name, f"J{n}: the angle between the axes of J{n - 1} and J{n} is {angle:.4f} rad, but "
                                                f"DH row {n - 1} (alpha) expects {abs(r.alpha):.4f} rad")
        distance = _line_distance(p1, d1, p2, d2)
        if abs(distance - abs(r.a)) > KINEMATICS_DISTANCE:
            report.error("kinematics", path.name, f"J{n}: the axes of J{n - 1} and J{n} are {distance:.4f} m apart, but "
                                                f"DH row {n - 1} (a) expects {abs(r.a):.4f} m")
    if not all(n in world or n in other for n in range(1, 7)):
        report.summary["kinematics"] = "pairs only"
        return
    report.summary["kinematics"] = "full chain"
    if not unreadable:
        try:
            chain = dh.axes(dh.frames([row(n) for n in range(1, 7)], [0.0] * 6))
        except Exception as e:
            report.error("kinematics", path.name, f"cannot read the DH rows: {type(e).__name__}: {e}")
            return
        for n in range(1, 7):
            if n not in world:
                continue
            (origin, direction), (want_o, want_d) = world[n], chain[n - 1]
            off_axis = np.linalg.norm(np.cross(want_o - origin, direction))  # the DH origin's distance from the twin's axis line
            if off_axis > KINEMATICS_DISTANCE or np.linalg.norm(direction - want_d) > KINEMATICS_ANGLE:
                report.error("kinematics", path.name, f"J{n} turns about {np.round(direction, 4).tolist()} through "
                                                    f"{np.round(origin, 4).tolist()} m in the world, but the DH rows put it about "
                                                    f"{np.round(want_d, 4).tolist()} through {np.round(want_o, 4).tolist()} m")


def _jaws(model) -> dict[str, dict[str, float]]:
    """The prismatic joints labelled JAW1 and JAW2 with their lower, upper, effort and velocity limits."""
    import newton

    types, qd_start = model.joint_type.numpy(), model.joint_qd_start.numpy()
    arrays = {"lower": model.joint_limit_lower.numpy(), "upper": model.joint_limit_upper.numpy(),
              "effort": model.joint_effort_limit.numpy(), "velocity": model.joint_velocity_limit.numpy()}
    return {label: {k: float(v[qd_start[j]]) for k, v in arrays.items()}
            for j, label in enumerate(model.joint_label)
            if label in JAWS and types[j] == newton.JointType.PRISMATIC}


def _gripper(path, model, build_gripper, device, trace, report):
    """Build the gripper alone, check it like the arm, and compare its jaws with the arm's."""
    import newton

    missing = f"define build_gripper(builder) to build the gripper alone, and add prismatic jaws {' and '.join(JAWS)} on both models"
    if build_gripper is None or set(_jaws(model)) != set(JAWS):
        report.error("gripper", path.name, missing)
        return
    before = len(report.findings)
    K.clear()  # trace the standalone gripper against its own reads only
    try:
        builder = newton.ModelBuilder()
        masses = _record_masses(builder)
        build_gripper(builder)
        alone = builder.finalize(device=device)
    except Exception as e:  # as in check(), a failure in the student's module is a finding
        report.error("gripper", path.name, f"build_gripper() failed: {type(e).__name__}: {e}")
        return
    if set(_jaws(alone)) != set(JAWS):
        report.error("gripper", path.name, missing)
        return
    _check_values(alone, report, STANDALONE)
    if trace:
        _trace(alone, masses, report, STANDALONE)
        report.summary["kdb_reads"] = report.summary.get("kdb_reads", 0) + len(K.reads())
    arm, own = _jaws(model), _jaws(alone)
    names = {"lower": "lower limit", "upper": "upper limit", "effort": "effort limit", "velocity": "velocity limit"}
    for jaw in JAWS:
        differ = [f"{names[k]} {arm[jaw][k]:.6g} in build() but {own[jaw][k]:.6g} in build_gripper()"
                  for k in names if not math.isclose(arm[jaw][k], own[jaw][k], rel_tol=TRACE_TOLERANCE, abs_tol=1e-9)]
        if differ:
            report.error("gripper", jaw, f"{', '.join(differ)}; the arm's gripper must be the one build_gripper() builds")
    if len(report.findings) == before:  # no finding at all on the standalone gripper or its jaws
        report.summary["gripper"] = "ok"


def _drop(model, limited, seconds, report, dt=1e-3):
    import numpy as np

    import newton

    solver = newton.solvers.SolverMuJoCo(model)
    s0, s1, control = model.state(), model.state(), model.control()
    newton.eval_fk(model, model.joint_q, model.joint_qd, s0)
    for _ in range(int(round(seconds / dt))):
        solver.step(s0, s1, control, None, dt)
        s0, s1 = s1, s0
    report.summary["drop_seconds"] = seconds
    if not np.isfinite(s0.body_q.numpy()).all():
        report.error("drop", "model", f"the simulation diverged within {seconds} s of release")
        return
    q, q_start = s0.joint_q.numpy(), model.joint_q_start.numpy()
    lower, upper, qd_start = model.joint_limit_lower.numpy(), model.joint_limit_upper.numpy(), model.joint_qd_start.numpy()
    for j in limited:
        qi, d = q_start[j], qd_start[j]
        over = max(lower[d] - q[qi], q[qi] - upper[d])
        if over > LIMIT_SLACK:
            report.error("drop", model.joint_label[j], f"left its limits by {over:.3f} after {seconds} s under gravity")


class Solid(NamedTuple):
    """One collision shape in world coordinates: Newton's GeoType, its scale, its pose (px, py, pz, qx, qy, qz, qw),
    the local vertices of a mesh (before scaling) and a bounding radius for any other shape type."""
    geo: int
    scale: tuple
    xform: tuple
    points: object = None
    radius: float = 0.0


def _support(s: Solid, d) -> float:
    """The largest p . d over the points p of the shape s, for a world direction d."""
    import numpy as np

    import newton

    G = newton.GeoType
    d = np.asarray(d, dtype=float)
    p, (x, y, z, w) = np.asarray(s.xform[:3], dtype=float), s.xform[3:]
    a, sc = _rotate((-x, -y, -z, w), d), np.asarray(s.scale, dtype=float)  # the direction in the shape's frame
    if s.geo == G.SPHERE:
        reach = sc[0]
    elif s.geo == G.BOX:
        reach = float(np.abs(sc * a).sum())
    elif s.geo == G.CAPSULE:  # radius sc[0], half length sc[1] along z
        reach = sc[1] * abs(a[2]) + sc[0]
    elif s.geo == G.CYLINDER:
        reach = sc[1] * abs(a[2]) + sc[0] * math.hypot(a[0], a[1])
    elif s.geo == G.ELLIPSOID:
        reach = float(np.linalg.norm(sc * a))
    elif s.geo in (G.MESH, G.CONVEX_MESH) and s.points is not None:
        reach = float((np.asarray(s.points, dtype=float) * sc @ a).max())
    else:  # any other shape: its bounding sphere
        reach = s.radius
    return float(p @ d) + reach


def _penetration(close, jaw: list[Solid], cube: Solid) -> float:
    """How far the jaw's shapes have passed the cube's near face, along the jaw's closing direction close.

    For each jaw shape that faces the cube (their extents across close overlap), the depth is the shape's
    leading point along close minus the cube's nearest point along close. The result is the largest depth,
    or 0 when no shape reaches the cube.
    """
    import numpy as np

    c = np.asarray(close, dtype=float)
    c = c / np.linalg.norm(c)
    u = np.cross(c, (1.0, 0.0, 0.0) if abs(c[0]) < 0.9 else (0.0, 1.0, 0.0))
    u /= np.linalg.norm(u)
    across = (u, np.cross(c, u))

    def faces(s):
        return all(_support(s, e) > -_support(cube, -e) and _support(cube, e) > -_support(s, -e) for e in across)

    depths = [_support(s, c) + _support(cube, -c) for s in jaw if faces(s)]
    return max([0.0, *depths])


def _welded(model, body: int) -> set[int]:
    """body and every body joined to it through FIXED joints, directly or through other welded bodies."""
    import newton

    fixed = model.joint_type.numpy() == int(newton.JointType.FIXED)
    pairs = list(zip(model.joint_parent.numpy()[fixed].tolist(), model.joint_child.numpy()[fixed].tolist(), strict=True))
    found, todo = {body}, [body]
    while todo:
        b = todo.pop()
        for p, c in pairs:
            for near, other in ((p, c), (c, p)):
                if near == b and other >= 0 and other not in found:
                    found.add(other)
                    todo.append(other)
    return found


def _jaw_penetration(model, body_q, cube: int) -> dict:
    """How far each jaw's shapes sink into the cube's shape, along the jaw's closing direction, at body poses body_q.
    A jaw's shapes are those of its body and of every body welded to it, such as a finger or a pad."""
    import numpy as np

    import newton

    def compose(a, b):  # pose a then pose b, each (px, py, pz, qx, qy, qz, qw)
        qa, qb = np.asarray(a[3:], dtype=float), np.asarray(b[3:], dtype=float)
        return tuple(np.concatenate([np.asarray(a[:3]) + _rotate(qa, b[:3]), _qmul(qa, qb)]))

    shape_body, flags = model.shape_body.numpy(), model.shape_flags.numpy()
    types, scales, xforms, radii = (model.shape_type.numpy(), model.shape_scale.numpy(), model.shape_transform.numpy(),
                                    model.shape_collision_radius.numpy())

    def solids(bodies):
        out = []
        for i in np.flatnonzero(np.isin(shape_body, list(bodies)) & (flags & int(newton.ShapeFlags.COLLIDE_SHAPES) != 0)):
            body = int(shape_body[i])
            source = model.shape_source[i]
            out.append(Solid(int(types[i]), tuple(scales[i]), compose(body_q[body], xforms[i]),
                             getattr(source, "vertices", None), float(radii[i])))
        return out

    (box,) = solids({cube})
    axes, x_p, parent, child = model.joint_axis.numpy(), model.joint_X_p.numpy(), model.joint_parent.numpy(), model.joint_child.numpy()
    qd_start, lower, upper = model.joint_qd_start.numpy(), model.joint_limit_lower.numpy(), model.joint_limit_upper.numpy()
    depths = {}
    for j, label in enumerate(model.joint_label):
        if label not in JAWS:
            continue
        d = qd_start[j]
        if lower[d] == upper[d]:  # a guard for direct callers; _grasp reports such a jaw before it gets here
            raise ValueError(f"{label} has the same lower and upper limit, so it has no closing direction")
        frame = compose(body_q[parent[j]], x_p[j]) if parent[j] >= 0 else tuple(x_p[j])
        close = _rotate(np.asarray(frame[3:]), axes[d]) * np.sign(lower[d] - upper[d])  # toward the lower limit
        depths[label] = _penetration(close, solids(_welded(model, int(child[j]))), box)
    return depths


def _rotate(q, v):
    """Rotate vector v by the unit quaternion q = (x, y, z, w)."""
    import numpy as np

    u, w = np.asarray(q[:3], dtype=float), float(q[3])
    v = np.asarray(v, dtype=float)
    return v + 2.0 * np.cross(u, np.cross(u, v) + w * v)


def _qmul(a, b):
    """The quaternion product a b, both (x, y, z, w)."""
    import numpy as np

    (ax, ay, az, aw), (bx, by, bz, bw) = a, b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


class _StuckJaws(Exception):
    """Jaws whose lower and upper limits are equal, as (label, limit) pairs."""


class _NoSolver(Exception):
    """SolverMuJoCo could not be built for the gripper and the cube; the cause is the first argument."""


def _grasp(build_gripper, report, close_s: float = 0.5, hold_s: float = 2.0, dt: float = GRASP_DT,
           control_s: float = 0.2) -> None:
    """Close the standalone gripper on the course cube, then check that friction in the jaws holds it under gravity.

    The cube starts centered on the grasp frame with the jaws open. Gravity pulls along the grasp frame's z,
    which should point out of the gripper. Two runs share these settings:

    control  the jaws stay open and gravity is on for control_s. The cube must fall at least GRASP_FREE_FALL of
             the free-fall distance (a supported cube sinks a few mm into soft contacts, more than GRASP_SLIP); if
             it does not, something other than the jaws' grip holds it (the base, a stop, open jaws narrower than
             the cube, or a grasp frame whose z points into the gripper), and the grasp run would prove nothing.
    grasp    with gravity off, the jaws close for close_s under a position drive capped by each jaw's effort
             limit. The penetration is then how far each jaw's shapes have passed the cube's near face along
             the jaw's closing direction, from the shapes' geometry and the bodies' poses; the larger of the two
             may be at most GRASP_PENETRATION. Then gravity is on for hold_s. The slip is how far the cube's
             center moves along gravity.

    The friction and the contact stiffness are the course's, not the twin's. Every shape in the model (the gripper,
    with any finger or pad on a body welded to a jaw, and the cube) gets CUBE_FRICTION, so the effective friction
    coefficient (MuJoCo takes the larger of the two surfaces') is CUBE_FRICTION. They also get the MuJoCo solref (GRASP_CONTACT_TIMECONST, GRASP_CONTACT_DAMPRATIO). Newton's
    default contact is soft (time constant 20 ms), and a drive at the effort limit pushes light jaws far into the
    cube. A stiff contact needs a short step, so the test runs at GRASP_DT; a dt above half the time constant is
    refused, because MuJoCo would quietly soften the contact. If the twin registered SolverMuJoCo's custom
    attributes, the shapes' solref mode, raw solref, solimp, priority and solmix go back to their defaults.
    """
    import numpy as np
    import warp as wp

    import newton

    if dt > GRASP_CONTACT_TIMECONST / 2:  # MuJoCo would quietly raise the time constant to 2 dt, softening the contact
        raise ValueError(f"the grasp step dt = {dt} s must be at most half the contact time constant "
                         f"GRASP_CONTACT_TIMECONST = {GRASP_CONTACT_TIMECONST} s")

    def setup(close):
        builder = newton.ModelBuilder()
        frame = build_gripper(builder)
        down = np.array(wp.quat_rotate(frame.q, wp.vec3(0.0, 0.0, 1.0)))  # the grasp frame's z
        cube = builder.add_body(xform=frame, label="cube")
        h = CUBE_EDGE / 2
        builder.add_shape_box(cube, hx=h, hy=h, hz=h,
                              cfg=newton.ModelBuilder.ShapeConfig(density=CUBE_MASS / CUBE_EDGE**3, mu=CUBE_FRICTION))
        model = builder.finalize(device="cpu")
        jaws = [j for j, label in enumerate(model.joint_label) if label in JAWS]
        q_start, qd_start = model.joint_q_start.numpy(), model.joint_qd_start.numpy()
        target_start = model.joint_target_q_start.numpy()
        lower, upper = model.joint_limit_lower.numpy(), model.joint_limit_upper.numpy()
        stuck = [(model.joint_label[j], float(lower[qd_start[j]])) for j in jaws if lower[qd_start[j]] == upper[qd_start[j]]]
        if stuck:  # MuJoCo refuses such a joint, and it would have no closing direction
            raise _StuckJaws(stuck)
        effort, velocity = model.joint_effort_limit.numpy(), model.joint_velocity_limit.numpy()
        q, target = model.joint_q.numpy(), model.joint_target_q.numpy()
        mode, ke, kd = model.joint_target_mode.numpy(), model.joint_target_ke.numpy(), model.joint_target_kd.numpy()
        for j in jaws:
            d = qd_start[j]
            q[q_start[j]] = upper[d]                                # open
            target[target_start[j]] = lower[d] if close else upper[d]  # drive to closed, or hold open
            mode[d] = int(newton.JointTargetMode.POSITION)
            # The check's own gains: the drive reaches the effort limit GRASP_SATURATE short of its target, where
            # MuJoCo caps the force. kd only scales the damping by the velocity limit. MuJoCo has no joint velocity
            # limit and the force saturates before damping matters, so the jaws close as fast as that force allows.
            ke[d], kd[d] = effort[d] / GRASP_SATURATE, effort[d] / velocity[d]
        # The model holds only the gripper and the cube, so every shape gets the course's contact: a finger or pad
        # on a body welded to a jaw touches the cube as much as the jaw does.
        touching = list(range(model.shape_count))
        mu = model.shape_material_mu.numpy()
        mu[touching] = CUBE_FRICTION
        # The contact stiffness is the course's too. SolverMuJoCo turns a shape's ke and kd into MuJoCo's solref
        # as time constant 2 / kd and damping ratio kd / (2 sqrt(ke)); these ke and kd give the course's pair.
        shape_ke, shape_kd = model.shape_material_ke.numpy(), model.shape_material_kd.numpy()
        shape_ke[touching] = 1.0 / (GRASP_CONTACT_TIMECONST * GRASP_CONTACT_DAMPRATIO) ** 2
        shape_kd[touching] = 2.0 / GRASP_CONTACT_TIMECONST
        for array, values in ((model.joint_q, q), (model.joint_target_q, target), (model.joint_target_mode, mode),
                              (model.joint_target_ke, ke), (model.joint_target_kd, kd), (model.shape_material_mu, mu),
                              (model.shape_material_ke, shape_ke), (model.shape_material_kd, shape_kd)):
            array.assign(values)
        # A twin that registered SolverMuJoCo's custom attributes could give its shapes a raw solref, a solimp,
        # a priority or a solmix of its own, which would replace or reweigh the course's contact. Put them back
        # to the defaults, which use ke and kd.
        for name in ("solref_mode", "solref", "geom_solimp", "geom_priority", "geom_solmix"):
            array = getattr(getattr(model, "mujoco", None), name, None)
            if array is not None:
                values = array.numpy()
                default = builder.custom_attributes[f"mujoco:{name}"].default
                values[touching] = list(default) if hasattr(default, "__len__") else default
                array.assign(values)
        gravity = float(np.linalg.norm(model.gravity.numpy()[0])) * down
        model.set_gravity((0.0, 0.0, 0.0))
        # Native MuJoCo is fast for one small model. An elliptic friction cone with impratio 10 is MuJoCo's
        # advice for grasping; with the default pyramidal cone a held object creeps.
        try:
            solver = newton.solvers.SolverMuJoCo(model, use_mujoco_cpu=True, cone="elliptic", impratio=10.0)
        except Exception as e:
            raise _NoSolver(e) from e
        state, control = model.state(), model.control()
        control.joint_target_q.assign(target)
        newton.eval_fk(model, model.joint_q, model.joint_qd, state)
        return model, solver, [state, model.state()], control, cube, down, gravity

    def run(model, solver, states, control, seconds):
        for _ in range(int(round(seconds / dt))):
            solver.step(states[0], states[1], control, None, dt)
            states.reverse()
        return states[0].body_q.numpy().copy()  # on the CPU numpy() is a view of a buffer the next steps reuse

    def gravity_on(model, solver, gravity):
        model.set_gravity(tuple(float(a) for a in gravity))
        solver.notify_model_changed(newton.ModelFlags.MODEL_PROPERTIES)

    try:
        open_run, grasp_run = setup(close=False), setup(close=True)
    except _StuckJaws as e:
        for label, limit in e.args[0]:
            report.error("grasp", label, f"{label} has the same lower and upper limit ({limit:g} m), so it cannot open or "
                                         f"close and the grasp cannot be tested")
        return
    except _NoSolver as e:
        cause = e.args[0]
        report.error("grasp", "cube", f"MuJoCo could not build the grasp model, the gripper build_gripper() builds plus the "
                                      f"cube: {type(cause).__name__}: {cause}")
        return
    except Exception as e:  # build_gripper() already ran in the gripper rule; this catches a bad return value
        report.error("grasp", "cube", f"could not place the cube on the grasp frame build_gripper() returned: {type(e).__name__}: {e}")
        return

    model, solver, states, control, cube, down, gravity = open_run
    start = states[0].body_q.numpy().copy()
    gravity_on(model, solver, gravity)
    fell = run(model, solver, states, control, control_s)
    if not np.isfinite(fell).all():
        report.error("grasp", "cube", "the simulation diverged")
        return
    drop = float(np.dot(fell[cube][:3] - start[cube][:3], down))
    free = 0.5 * float(np.linalg.norm(gravity)) * control_s**2
    report.summary["grasp_open_drop_m"] = drop
    if drop < GRASP_FREE_FALL * free:
        report.error("grasp", "cube", f"with the jaws held open the cube fell only {drop * 1000:.1f} mm in {control_s} s, where a free "
                                      f"cube falls {free * 1000:.0f} mm: something "
                                      f"other than the jaws supports it. Gravity pulls along the z axis of the grasp frame "
                                      f"build_gripper() returns, so that z must point out of the gripper, and nothing may sit "
                                      f"under the cube")
        return

    model, solver, states, control, cube, down, gravity = grasp_run
    closed = run(model, solver, states, control, close_s)
    if not np.isfinite(closed).all():
        report.error("grasp", "cube", "the simulation diverged")
        return
    depths = _jaw_penetration(model, closed, cube)
    jaw, depth = max(depths.items(), key=lambda kv: kv[1])
    report.summary["grasp_penetration_m"] = depth
    if depth > GRASP_PENETRATION:
        report.error("grasp", "cube", f"{jaw} sank {depth * 1000:.1f} mm into the {CUBE_EDGE * 1000:g} mm cube when the jaws "
                                      f"closed (at most {GRASP_PENETRATION * 1000:g} mm). The check gives the jaws and the cube "
                                      f"stiff contacts, so the jaw passes into the cube instead of stopping at its face: check "
                                      f"the jaw shapes, the jaw masses and the jaw force")
        return
    gravity_on(model, solver, gravity)
    held = run(model, solver, states, control, hold_s)
    if not np.isfinite(held).all():
        report.error("grasp", "cube", "the simulation diverged")
        return
    slip = float(np.dot(held[cube][:3] - closed[cube][:3], down))
    report.summary["grasp_slip_m"] = slip
    if slip > GRASP_SLIP:
        report.error("grasp", "cube", f"the {CUBE_MASS * 1000:g} g cube slipped {slip * 1000:.1f} mm in the closed jaws during a "
                                      f"{hold_s} s hold (at most {GRASP_SLIP * 1000:g} mm). Friction in the jaws does not carry "
                                      f"its weight: check the jaw force, the jaw opening and the grasp frame")


def check(path: Path, seconds: float = 1.0, device: str = "cpu", kdb: Path | None = None, trace: bool = True,
          grasp: bool = True) -> Report:
    import newton

    path, report = Path(path), Report()
    K.use(kdb)
    K.clear()
    try:
        build, build_gripper = _load(path)
        builder = newton.ModelBuilder()
        masses = _record_masses(builder)
        build(builder)
        model = builder.finalize(device=device)
    except Exception as e:  # any failure in the student's module is a finding, not a crash
        report.error("build", path.name, f"{type(e).__name__}: {e}")
        return report
    report.summary.update(bodies=model.body_count, joints=model.joint_count, dofs=model.joint_dof_count)
    limited = _check_values(model, report)
    if trace:
        _trace(model, masses, report)
        report.summary["kdb_reads"] = len(K.reads())
    _kinematics(path, model, report)
    _gripper(path, model, build_gripper, device, trace, report)
    if not report.findings and seconds > 0:
        _drop(model, limited, seconds, report)
    if not report.findings and grasp:
        _grasp(build_gripper, report)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-check", description=__doc__.split("\n\n")[0])
    p.add_argument("build", type=Path, help="the Python file that defines build(builder) and build_gripper(builder)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--seconds", type=float, default=1.0, help="length of the drop test; 0 skips it")
    p.add_argument("--kdb", type=Path, help="the kDB that build() reads (default: TWIN_KDB, or kdb/)")
    p.add_argument("--no-trace", dest="trace", action="store_false", help="skip the check that values come from the kDB")
    p.add_argument("--no-grasp", dest="grasp", action="store_false", help="skip the test that the gripper holds the cube")
    a = p.parse_args(argv)
    if not a.build.is_file():
        print(f"twin-check: no such file {a.build}", file=sys.stderr)
        return 2
    with contextlib.redirect_stdout(sys.stderr):  # Warp prints its banner and kernel loads to stdout
        report = check(a.build, a.seconds, kdb=a.kdb, trace=a.trace, grasp=a.grasp)
    if a.json:
        print(json.dumps({"tool": report.tool, "findings": [asdict(f) for f in report.findings], "summary": report.summary}))
    else:
        for f in report.findings:
            print(f"{f.level} {f.rule} {f.path}: {f.message}")
        print(f"{len(report.findings)} findings; " + ", ".join(f"{k} {v}" for k, v in report.summary.items()))
    return 1 if any(f.level == "error" for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
