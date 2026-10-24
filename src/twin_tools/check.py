"""Load a twin's Newton builder and check the model it builds.

    twin-check twin/build.py [--json] [--seconds 1.0]

The file must define build(builder: newton.ModelBuilder) -> None. The checks:

    build           the module imports, build() runs and the model finalizes
    mass            every link has mass (a link with no shapes and no mass gets 0)
    joint-limits    every revolute and prismatic joint has limits (Newton's default is 1e10)
    effort-limit    every such joint has an effort limit (default 1e6)
    velocity-limit  every such joint has a velocity limit (default 1e6)
    drop            released at rest under gravity with no drive, the model stays finite and
                    each joint stays within its limits

Newton accepts the defaults silently. Every one of these values should come from your kDB.
The exit status is 0 when there are no errors, 1 when there are errors and 2 when the tool could not run.
"""

import argparse
import contextlib
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

UNSET_LIMIT = 1e9   # Newton's default joint limits are +-1e10
UNSET_RATE = 1e6    # and its default effort and velocity limits are 1e6
LIMIT_SLACK = 0.05  # rad or m a joint may overshoot its limit during the drop


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


def check(path: Path, seconds: float = 1.0, device: str = "cpu") -> Report:
    import newton

    path, report = Path(path), Report()
    try:
        build = _load_build(path)
        builder = newton.ModelBuilder()
        build(builder)
        model = builder.finalize(device=device)
    except Exception as e:  # any failure in the student's module is a finding, not a crash
        report.error("build", path.name, f"{type(e).__name__}: {e}")
        return report
    report.summary.update(bodies=model.body_count, joints=model.joint_count, dofs=model.joint_dof_count)
    limited = _check_values(model, report)
    if not report.findings and seconds > 0:
        _drop(model, limited, seconds, report)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="twin-check", description=__doc__.split("\n\n")[0])
    p.add_argument("build", type=Path, help="the Python file that defines build(builder)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--seconds", type=float, default=1.0, help="length of the drop test; 0 skips it")
    a = p.parse_args(argv)
    if not a.build.is_file():
        print(f"twin-check: no such file {a.build}", file=sys.stderr)
        return 2
    with contextlib.redirect_stdout(sys.stderr):  # Warp prints its banner and kernel loads to stdout
        report = check(a.build, a.seconds)
    if a.json:
        print(json.dumps({"tool": report.tool, "findings": [asdict(f) for f in report.findings], "summary": report.summary}))
    else:
        for f in report.findings:
            print(f"{f.level} {f.rule} {f.path}: {f.message}")
        print(f"{len(report.findings)} findings; " + ", ".join(f"{k} {v}" for k, v in report.summary.items()))
    return 1 if any(f.level == "error" for f in report.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
