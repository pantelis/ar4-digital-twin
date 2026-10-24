"""Load a twin's Newton builder and check the model it builds.

    twin-check twin/build.py [--json] [--seconds 1.0] [--kdb kdb] [--no-trace]

The file must define build(builder: newton.ModelBuilder) -> None. The checks:

    build           the module imports, build() runs and the model finalizes
    mass            every link has mass (a link with no shapes and no mass gets 0)
    joint-limits    every revolute and prismatic joint has limits (Newton's default is 1e10)
    effort-limit    every such joint has an effort limit (default 1e6)
    velocity-limit  every such joint has a velocity limit (default 1e6)
    trace           every joint limit, effort limit and velocity limit, every shape density and
                    every link mass set in build() was read from the kDB with twin_tools.kdb.si
    drop            released at rest under gravity with no drive, the model stays finite and
                    each joint stays within its limits

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
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import kdb as K

UNSET_LIMIT = 1e9   # Newton's default joint limits are +-1e10
UNSET_RATE = 1e6    # and its default effort and velocity limits are 1e6
LIMIT_SLACK = 0.05  # rad or m a joint may overshoot its limit during the drop
TRACE_TOLERANCE = 1e-5  # relative; Newton stores joint values as float32


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


def _load_build(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build = getattr(module, "build", None)
    if not callable(build):
        raise AttributeError("no build(builder) function")
    return build


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


def _traced(value: float, reads: list[float]) -> bool:
    return any(math.isclose(value, r, rel_tol=TRACE_TOLERANCE, abs_tol=1e-9) for r in reads)


def _trace(model, masses, report):
    import newton

    reads = [r.si for r in K.reads()]
    types, qd_start = model.joint_type.numpy(), model.joint_qd_start.numpy()
    arrays = {"lower limit": model.joint_limit_lower.numpy(), "upper limit": model.joint_limit_upper.numpy(),
              "effort limit": model.joint_effort_limit.numpy(), "velocity limit": model.joint_velocity_limit.numpy()}
    for j, label in enumerate(model.joint_label):
        if types[j] not in (newton.JointType.REVOLUTE, newton.JointType.PRISMATIC):
            continue
        untraced = []
        for what, values in arrays.items():
            for d in range(qd_start[j], qd_start[j + 1]):
                v = float(values[d])
                unset = abs(v) >= UNSET_LIMIT if what in ("lower limit", "upper limit") else not 0 < v < UNSET_RATE
                if not unset and not _traced(v, reads):
                    untraced.append(f"{what} {v:.6g}")
        if untraced:
            report.error("trace", label, f"{', '.join(untraced)} not read from the kDB; read each with twin_tools.kdb.si")
    for body, found in sorted(masses.items()):
        label = model.body_label[body] if body < len(model.body_label) else str(body)
        untraced = [f"shape density {v:g} kg/m^3" + (" (Newton's default)" if v == 1000.0 else "")
                    for v in sorted(found["density"]) if not _traced(v, reads)]
        untraced += [f"mass {v:g} kg" for v in sorted(found["mass"]) if not _traced(v, reads)]
        if untraced:
            report.error("trace", label, f"{', '.join(untraced)} not read from the kDB; read each with twin_tools.kdb.si")


def _check_values(model, report):
    import newton

    for i, label in enumerate(model.body_label):
        if model.body_mass.numpy()[i] <= 0:
            report.error("mass", label, "has no mass: give its shapes a density, or set its mass from a datasheet")
    types, qd_start = model.joint_type.numpy(), model.joint_qd_start.numpy()
    lower, upper = model.joint_limit_lower.numpy(), model.joint_limit_upper.numpy()
    effort, velocity = model.joint_effort_limit.numpy(), model.joint_velocity_limit.numpy()
    limited = []
    for j, label in enumerate(model.joint_label):
        if types[j] not in (newton.JointType.REVOLUTE, newton.JointType.PRISMATIC):
            continue
        dofs = range(qd_start[j], qd_start[j + 1])
        if any(abs(lower[d]) >= UNSET_LIMIT or abs(upper[d]) >= UNSET_LIMIT or lower[d] >= upper[d] for d in dofs):
            report.error("joint-limits", label, "has no joint limits (Newton's default is +-1e10)")
        else:
            limited.append(j)
        if any(not 0 < effort[d] < UNSET_RATE for d in dofs):
            report.error("effort-limit", label, "has no effort limit (Newton's default is 1e6)")
        if any(not 0 < velocity[d] < UNSET_RATE for d in dofs):
            report.error("velocity-limit", label, "has no velocity limit (Newton's default is 1e6)")
    return limited


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


def check(path: Path, seconds: float = 1.0, device: str = "cpu", kdb: Path | None = None, trace: bool = True) -> Report:
    import newton

    path, report = Path(path), Report()
    K.use(kdb)
    K.clear()
    try:
        build = _load_build(path)
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
    if not report.findings and seconds > 0:
        _drop(model, limited, seconds, report)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-check", description=__doc__.split("\n\n")[0])
    p.add_argument("build", type=Path, help="the Python file that defines build(builder)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--seconds", type=float, default=1.0, help="length of the drop test; 0 skips it")
    p.add_argument("--kdb", type=Path, help="the kDB that build() reads (default: TWIN_KDB, or kdb/)")
    p.add_argument("--no-trace", dest="trace", action="store_false", help="skip the check that values come from the kDB")
    a = p.parse_args(argv)
    if not a.build.is_file():
        print(f"twin-check: no such file {a.build}", file=sys.stderr)
        return 2
    with contextlib.redirect_stdout(sys.stderr):  # Warp prints its banner and kernel loads to stdout
        report = check(a.build, a.seconds, kdb=a.kdb, trace=a.trace)
    if a.json:
        print(json.dumps({"tool": report.tool, "findings": [asdict(f) for f in report.findings], "summary": report.summary}))
    else:
        for f in report.findings:
            print(f"{f.level} {f.rule} {f.path}: {f.message}")
        print(f"{len(report.findings)} findings; " + ", ".join(f"{k} {v}" for k, v in report.summary.items()))
    return 1 if any(f.level == "error" for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
