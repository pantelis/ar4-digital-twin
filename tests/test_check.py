"""twin-check needs Newton, so these tests run inside the project container (see docker/)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("newton")
from twin_tools import check as check_module  # noqa: E402
from twin_tools import kdb  # noqa: E402
from twin_tools.check import GRASP_PENETRATION, Report, Solid, _grasp, _jaw_penetration, _penetration, check  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
# The fixture twins import fixtures.gripper, so the twin-check subprocess needs tests/ on its path as pytest has.
ENV = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(FIX.parent), os.environ.get("PYTHONPATH")])))


def rules(report, level="error"):
    return sorted((f.rule, f.path) for f in report.findings if f.level == level)


def test_complete_twin_has_no_findings():
    report = check(FIX / "twin_ok.py", kdb=FIX / "kdb")
    assert report.findings == []
    # upper arm, forearm, gripper base and two jaws; J2, J3, the fixed mount, JAW1 and JAW2
    assert report.summary["bodies"] == 5 and report.summary["joints"] == 5
    assert report.summary["gripper"] == "ok"
    # a MuJoCo contact needs some overlap to push, so the closed jaws sink in a little, but less than the bound
    assert 0 < report.summary["grasp_penetration_m"] < GRASP_PENETRATION


def kinematics(report):
    return [f for f in report.findings if f.rule == "kinematics"]


def test_axes_follow_the_dh_rows():
    assert kinematics(check(FIX / "twin_ok.py", kdb=FIX / "kdb", seconds=0, grasp=False)) == []


def test_a_flipped_axis_is_caught():
    report = check(FIX / "twin_axis_flipped.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    (f,) = kinematics(report)
    assert "J3" in f.message and "3.14" in f.message and "expects 0.0000" in f.message
    assert [x.rule for x in report.findings] == ["kinematics"]


def test_an_offset_axis_is_caught():
    report = check(FIX / "twin_axis_offset.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    (f,) = kinematics(report)
    assert "J3" in f.message and "0.330" in f.message and "0.280" in f.message
    assert [x.rule for x in report.findings] == ["kinematics"]


def test_a_pair_tilted_inside_the_angle_tolerance_is_parallel():
    report = check(FIX / "twin_axis_tilted.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    assert kinematics(report) == []


def test_a_partial_arm_skips_the_full_chain():
    report = check(FIX / "twin_ok.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    assert report.findings == []
    assert report.summary["kinematics"] == "pairs only"


def test_an_exact_six_joint_arm_has_no_kinematics_finding():
    # rotated joint frames make the J2 and J3 axes parallel only to float32 noise
    report = check(FIX / "twin_arm6.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    assert kinematics(report) == []
    assert report.summary["kinematics"] == "full chain"


def test_a_flipped_j5_is_caught_by_the_full_chain():
    report = check(FIX / "twin_arm6_flipped.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    (f,) = kinematics(report)
    assert f.message.startswith("J5 ")


def test_a_joint_slid_along_its_axis_passes():
    report = check(FIX / "twin_arm6_slid.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    assert kinematics(report) == []


def test_a_joint_anchored_off_its_axis_is_caught():
    report = check(FIX / "twin_arm6_off_axis.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    (f,) = kinematics(report)
    assert f.message.startswith("J6 ")


def test_a_non_revolute_j4_is_a_finding_and_skips_its_pairs():
    report = check(FIX / "twin_arm6_fixed.py", kdb=FIX / "kdb", seconds=0, grasp=False)
    (f,) = kinematics(report)
    assert f.message.startswith("J4 ") and "revolute" in f.message


def test_default_limits_and_massless_link_are_errors():
    report = check(FIX / "twin_defaults.py", trace=False, kdb=FIX / "kdb")
    assert rules(report) == [("effort-limit", "J2"), ("joint-limits", "J2"), ("mass", "motor_bracket"), ("velocity-limit", "J2")]


def test_build_errors_are_reported_not_raised():
    assert rules(check(FIX / "twin_broken.py", trace=False)) == [("build", "twin_broken.py")]
    assert rules(check(FIX / "twin_nobuild.py", trace=False)) == [("build", "twin_nobuild.py")]


def test_passive_drop_stays_finite_and_inside_limits():
    report = check(FIX / "twin_ok.py", seconds=1.0, kdb=FIX / "kdb")
    assert report.summary["drop_seconds"] == 1.0
    assert not [f for f in report.findings if f.rule == "drop"]


def test_cli_json_and_exit_status():
    run = lambda name: subprocess.run([sys.executable, "-m", "twin_tools.check", str(FIX / name), "--json", "--kdb", str(FIX / "kdb")],
                                      capture_output=True, text=True, env=ENV, timeout=600)
    ok, bad = run("twin_ok.py"), run("twin_defaults.py")
    assert ok.returncode == 0 and json.loads(ok.stdout)["findings"] == []
    assert bad.returncode == 1 and {f["rule"] for f in json.loads(bad.stdout)["findings"]} >= {"mass", "joint-limits"}


def test_values_typed_in_rather_than_read_from_the_kdb_are_untraced():
    report = check(FIX / "twin_literals.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("trace", "J2"), ("trace", "J3"), ("trace", "JAW1"), ("trace", "JAW2"),
                             ("trace", "forearm"), ("trace", "upper_arm")]
    j2 = next(f for f in report.findings if f.path == "J2")
    assert all(k in j2.message for k in ("lower limit", "upper limit", "effort limit", "velocity limit"))


def test_newtons_default_density_is_untraced():
    report = check(FIX / "twin_default_density.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("trace", "upper_arm")]
    assert "1000" in report.findings[0].message


def test_a_twin_without_a_gripper_is_one_finding():
    report = check(FIX / "twin_no_gripper.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("gripper", "twin_no_gripper.py")]
    assert all(k in report.findings[0].message for k in ("build_gripper(builder)", "JAW1", "JAW2"))


def test_the_arms_gripper_must_match_the_standalone_one():
    report = check(FIX / "twin_gripper_differs.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("gripper", "JAW1"), ("gripper", "JAW2")]
    assert all("effort limit" in f.message and "80" in f.message and "40" in f.message for f in report.findings)


def test_a_closed_jaw_limit_of_zero_is_not_untraced():
    report = check(FIX / "twin_ok.py", seconds=0, kdb=FIX / "kdb", grasp=False)
    assert not [f for f in report.findings if f.rule == "trace" and "lower limit 0" in f.message]


def test_an_arm_joint_limit_typed_as_zero_is_untraced():
    report = check(FIX / "twin_zero_limit.py", seconds=0, kdb=FIX / "kdb", grasp=False)
    assert rules(report) == [("trace", "J2")]
    assert "lower limit 0" in report.findings[0].message


def test_a_value_read_in_the_wrong_kind_is_untraced():
    # the jaws' effort limit is the PETG density read: a kDB number, but a density where a force belongs
    report = check(FIX / "twin_wrong_kind.py", seconds=0, kdb=FIX / "kdb", grasp=False)
    assert rules(report) == [("trace", "JAW1"), ("trace", "JAW1 (build_gripper)"), ("trace", "JAW2"),
                             ("trace", "JAW2 (build_gripper)")]
    assert all("effort limit 1270" in f.message and "density" in f.message for f in report.findings)
    assert "gripper" not in report.summary  # the standalone gripper has findings, so the gripper rule is not ok


def test_the_gripper_holds_the_cube():
    report = check(FIX / "twin_ok.py", kdb=FIX / "kdb")
    assert not [f for f in report.findings if f.rule == "grasp"]
    assert report.summary["grasp_slip_m"] < 0.005


def test_a_weak_gripper_drops_the_cube():
    report = check(FIX / "twin_gripper_weak.py", kdb=FIX / "kdb")
    assert rules(report) == [("grasp", "cube")]
    message = report.findings[0].message
    assert "mm" in message and "2.0 s" in message


def test_grasp_runs_only_when_everything_else_passes():
    report = check(FIX / "twin_no_gripper.py", kdb=FIX / "kdb")
    assert not [f for f in report.findings if f.rule == "grasp"]
    assert "grasp_slip_m" not in report.summary


def test_cli_no_grasp_skips_it():
    run = subprocess.run([sys.executable, "-m", "twin_tools.check", str(FIX / "twin_ok.py"), "--json", "--kdb", str(FIX / "kdb"),
                          "--no-grasp"], capture_output=True, text=True, env=ENV, timeout=600)
    assert run.returncode == 0
    assert "grasp_slip_m" not in json.loads(run.stdout)["summary"]


def test_a_cube_held_by_something_other_than_the_jaws_is_an_error():
    report = check(FIX / "twin_gripper_upside_down.py", kdb=FIX / "kdb")
    assert rules(report) == [("grasp", "cube")]
    assert "other than the jaws" in report.findings[0].message and "z" in report.findings[0].message


def test_the_jaws_friction_is_the_courses_not_the_twins():
    report = check(FIX / "twin_gripper_sticky.py", kdb=FIX / "kdb")
    assert rules(report) == [("grasp", "cube")]
    assert "slipped" in report.findings[0].message


def test_pads_welded_to_the_jaws_get_the_courses_friction_and_contact():
    report = check(FIX / "twin_gripper_welded_pads.py", kdb=FIX / "kdb")
    assert rules(report) == [("grasp", "cube")]
    assert "slipped" in report.findings[0].message


def fixture_gripper(stroke=None, raw_contact=False):
    """build_gripper for the fixture gripper on grippers/servo.md, for calling _grasp directly.
    stroke replaces the page's jaw stroke; raw_contact gives the jaws a very soft raw MuJoCo contact."""
    import warp as wp

    import newton
    from fixtures.gripper import add_gripper, add_gripper_values
    from twin_tools.kdb import si

    def build_gripper(builder):
        if raw_contact:
            newton.solvers.SolverMuJoCo.register_custom_attributes(builder)
        if stroke is None:
            grasp = add_gripper(builder, -1, wp.transform_identity())
        else:
            page = "grippers/servo.md"
            grasp = add_gripper_values(builder, -1, wp.transform_identity(), stroke=stroke, force=si(page, "jaw_force"),
                                       speed=si(page, "jaw_speed"), density=si("materials/petg.md", "density"))
        if raw_contact:
            jaws = {i for i, label in enumerate(builder.body_label) if label in ("jaw1", "jaw2")}
            attrs = builder.custom_attributes
            for i, body in enumerate(builder.shape_body):
                if body in jaws:
                    attrs["mujoco:solref_mode"].values[i] = 1  # raw MuJoCo solref
                    attrs["mujoco:solref"].values[i] = (0.2, 1.0)
                    attrs["mujoco:geom_solimp"].values[i] = (0.1, 0.2, 0.01, 0.5, 2.0)
                    attrs["mujoco:geom_priority"].values[i] = 5
        builder.add_articulation(list(range(builder.joint_count)))
        return grasp

    kdb.use(FIX / "kdb")
    return build_gripper


def test_too_deep_a_penetration_fails_before_the_hold(monkeypatch):
    monkeypatch.setattr(check_module, "GRASP_PENETRATION", -1.0)  # any closed pose is too deep
    report = Report()
    _grasp(fixture_gripper(), report)
    assert rules(report) == [("grasp", "cube")]
    assert "into the cube" in report.findings[0].message
    assert "grasp_penetration_m" in report.summary and "grasp_slip_m" not in report.summary


def test_a_twins_own_mujoco_contact_does_not_reach_the_grasp():
    report = Report()
    _grasp(fixture_gripper(raw_contact=True), report, hold_s=0.0)
    assert report.findings == []
    assert report.summary["grasp_penetration_m"] < GRASP_PENETRATION


def test_a_jaw_with_equal_limits_is_a_clear_error():
    report = Report()
    _grasp(fixture_gripper(stroke=0.0), report)
    assert rules(report) == [("grasp", "JAW1"), ("grasp", "JAW2")]
    assert "same lower and upper limit" in report.findings[0].message
    assert "grasp_penetration_m" not in report.summary


def test_the_grasp_step_must_be_short_enough_for_the_contact():
    with pytest.raises(ValueError, match="time constant"):
        _grasp(fixture_gripper(), Report(), dt=check_module.GRASP_CONTACT_TIMECONST)


def test_a_solver_that_cannot_be_built_is_its_own_error(monkeypatch):
    import newton

    def refuse(*args, **kwargs):
        raise RuntimeError("no solver today")

    monkeypatch.setattr(newton.solvers, "SolverMuJoCo", refuse)
    report = Report()
    _grasp(fixture_gripper(), report)
    assert rules(report) == [("grasp", "cube")]
    message = report.findings[0].message
    assert "MuJoCo" in message and "no solver today" in message and "grasp frame" not in message


def test_jaw_penetration_counts_bodies_welded_to_the_jaw():
    import warp as wp

    import newton
    builder = newton.ModelBuilder()
    cube = builder.add_body(xform=wp.transform_identity(), label="cube")
    builder.add_shape_box(cube, hx=0.0125, hy=0.0125, hz=0.0125)
    joints = []
    for n, side in ((1, 1.0), (2, -1.0)):
        # the jaw body's own shape is 25 mm clear of the cube; a pad welded to it sits 2 mm inside the cube's face,
        # and on JAW1 a second pad is welded to the first
        rest = wp.transform((side * 0.04, 0.0, 0.0), wp.quat_identity())
        jaw = builder.add_link(xform=rest, label=f"jaw{n}")
        builder.add_shape_box(jaw, hx=0.0025, hy=0.01, hz=0.01)
        joints.append(builder.add_joint_prismatic(-1, jaw, parent_xform=rest, axis=(side, 0.0, 0.0), label=f"JAW{n}",
                                                  limit_lower=0.0, limit_upper=0.02))
        pad_at = wp.transform((-side * 0.0275, 0.0, 0.0), wp.quat_identity())  # inner face 10.5 mm from the center
        pad = builder.add_link(xform=wp.transform_multiply(rest, pad_at), label=f"pad{n}")
        builder.add_shape_box(pad, hx=0.002, hy=0.01, hz=0.01)
        joints.append(builder.add_joint_fixed(jaw, pad, parent_xform=pad_at))
        if n == 1:
            tip_at = wp.transform((-0.003, 0.0, 0.0), wp.quat_identity())  # 3 mm further in: 5 mm inside the face
            tip = builder.add_link(xform=wp.transform_multiply(wp.transform_multiply(rest, pad_at), tip_at), label="tip1")
            builder.add_shape_box(tip, hx=0.002, hy=0.005, hz=0.005)
            joints.append(builder.add_joint_fixed(pad, tip, parent_xform=tip_at))
    builder.add_articulation(joints)
    model = builder.finalize(device="cpu")
    state = model.state()
    newton.eval_fk(model, model.joint_q, model.joint_qd, state)
    depths = _jaw_penetration(model, state.body_q.numpy(), cube)
    assert depths["JAW1"] == pytest.approx(0.005, abs=1e-6)
    assert depths["JAW2"] == pytest.approx(0.002, abs=1e-6)


def test_jaw_penetration_follows_each_jaws_axis():
    import math

    import warp as wp

    import newton
    turn = wp.quat_from_axis_angle(wp.vec3(0.0, 0.0, 1.0), math.radians(30.0))  # the jaws close off the world axes
    builder = newton.ModelBuilder()
    cube = builder.add_body(xform=wp.transform((0.0, 0.0, 0.0), turn), label="cube")
    builder.add_shape_box(cube, hx=0.0125, hy=0.0125, hz=0.0125)
    joints = []
    for n, side in ((1, 1.0), (2, -1.0)):
        # at q = 0 a jaw's inner face is 7.5 mm from the cube's center, 5 mm inside its face; q opens the jaw
        rest = wp.transform(wp.quat_rotate(turn, wp.vec3(side * 0.0125, 0.0, 0.0)), turn)
        jaw = builder.add_link(xform=rest, label=f"jaw{n}")
        builder.add_shape_box(jaw, hx=0.005, hy=0.01, hz=0.01)
        joints.append(builder.add_joint_prismatic(-1, jaw, parent_xform=rest, axis=(side, 0.0, 0.0), label=f"JAW{n}",
                                                  limit_lower=0.0, limit_upper=0.02))
    builder.add_articulation(joints)
    model = builder.finalize(device="cpu")
    q, q_start = model.joint_q.numpy(), model.joint_q_start.numpy()
    q[q_start[joints[0]]], q[q_start[joints[1]]] = 0.003, 0.0045
    model.joint_q.assign(q)
    state = model.state()
    newton.eval_fk(model, model.joint_q, model.joint_qd, state)
    depths = _jaw_penetration(model, state.body_q.numpy(), cube)
    assert depths["JAW1"] == pytest.approx(0.002, abs=1e-6)
    assert depths["JAW2"] == pytest.approx(0.0005, abs=1e-6)


def test_penetration_is_how_far_a_jaw_passes_the_cubes_near_face():
    import math

    import newton
    G = newton.GeoType
    still = (0.0, 0.0, 0.0, 1.0)
    cube = Solid(G.BOX, (0.0125, 0.0125, 0.0125), (0.0, 0.0, 0.0) + still)
    close = (-1.0, 0.0, 0.0)  # the jaw sits on +x and closes along -x

    def jaw(x, y=0.0, geo=G.BOX, scale=(0.005, 0.01, 0.02), q=still, points=None):
        return Solid(geo, scale, (x, y, 0.0) + q, points)

    # a box jaw whose inner face is at x = 10 mm, 2.5 mm inside the cube's face at 12.5 mm
    assert _penetration(close, [jaw(0.015)], cube) == pytest.approx(0.0025)
    # short of the cube, or beside it, there is no penetration
    assert _penetration(close, [jaw(0.020)], cube) == 0.0
    assert _penetration(close, [jaw(0.015, y=0.05)], cube) == 0.0
    # the deepest shape of the jaw counts
    assert _penetration(close, [jaw(0.020), jaw(0.013)], cube) == pytest.approx(0.0045)
    # a sphere and a capsule lying along y: their leading points are at x = 11 mm
    assert _penetration(close, [jaw(0.015, geo=G.SPHERE, scale=(0.004, 0.0, 0.0))], cube) == pytest.approx(0.0015)
    along_y = (-math.sin(math.pi / 4), 0.0, 0.0, math.cos(math.pi / 4))  # z turned onto y
    assert _penetration(close, [jaw(0.015, geo=G.CAPSULE, scale=(0.004, 0.02, 0.0), q=along_y)], cube) == pytest.approx(0.0015)
    # a mesh jaw: its vertices, scaled, give the leading point
    corners = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    assert _penetration(close, [jaw(0.015, geo=G.MESH, scale=(0.005, 0.01, 0.02), points=corners)], cube) == pytest.approx(0.0025)
    # a cube turned 45 degrees about z meets the jaw with an edge, 17.7 mm from its center
    turned = Solid(G.BOX, (0.0125, 0.0125, 0.0125), (0.0, 0.0, 0.0, 0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)))
    assert _penetration(close, [jaw(0.015)], turned) == pytest.approx(0.0125 * math.sqrt(2) - 0.010)
    # away from the origin: the same jaw and cube 40 mm up, and the jaw 50 mm above the cube
    up = lambda s, dz=0.0: s._replace(xform=(s.xform[0], s.xform[1], s.xform[2] + 0.04 + dz) + s.xform[3:])
    assert _penetration(close, [up(jaw(0.015))], up(cube)) == pytest.approx(0.0025)
    assert _penetration(close, [up(jaw(0.015), 0.05)], up(cube)) == 0.0
    # the method does not depend on the closing direction being an axis
    d = (-math.sqrt(0.5), -math.sqrt(0.5), 0.0)
    diag = Solid(G.SPHERE, (0.004, 0.0, 0.0), (0.006, 0.006, 0.0) + still)
    ball = Solid(G.SPHERE, (0.01, 0.0, 0.0), (0.0, 0.0, 0.0) + still)
    assert _penetration(d, [diag], ball) == pytest.approx(0.014 - 0.006 * math.sqrt(2))
