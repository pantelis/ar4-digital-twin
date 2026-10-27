"""The ar4 profile: every quantity has a unit and a cited source or a formula the checker recomputes."""

import pytest
from conftest import concept

from kdb_tools.validate import validate
from twin_tools.profile import PROFILE

SRC = {"id": "manual-p37-2", "resource": "/papers/kim2024.pdf", "page": 1,
       "quote": "OpenVLA is trained on 970k robot episodes.", "bbox": [72, 700, 400, 714]}
BODY = "J2 turns from -42 to 90 degrees.[^manual-p37-2]\n\n[^manual-p37-2]: AR4 manual, p. 37\n"


def q(value, unit, **kw):
    return {"value": value, "unit": unit, **({"source": "manual-p37-2"} if not kw else kw)}


def joint(**quantities):
    base = {"lower_limit": q(-42, "deg"), "upper_limit": q(90, "deg"), "velocity_limit": q(45, "deg/s"),
            "effort_limit": q(20, "N m"),
            "dh_theta_offset": q(0, "deg"), "dh_alpha": q(-90, "deg"), "dh_d": q(150, "mm"), "dh_a": q(50, "mm")}
    base.update(quantities)
    return concept(type="Joint", title="J2", parent="/links/link-1.md", child="/links/link-2.md",
                   sources=[dict(SRC)], quantities={k: v for k, v in base.items() if v is not None})


def errors(report):
    return sorted({(f.rule, f.path) for f in report.findings if f.level == "error"})


@pytest.fixture
def arm(bundle):
    bundle.add("materials/aluminum-6061.md", concept(type="Material", title="Aluminum 6061", sources=[dict(SRC)],
                                                     quantities={"density": q(2.70, "g/cm^3")}), BODY)
    for n in (1, 2):
        bundle.add(f"links/link-{n}.md", concept(type="Link", title=f"Link {n}", sources=[dict(SRC)],
                                                material="/materials/aluminum-6061.md"), BODY)
    bundle.add("motors/j2.md", concept(type="Motor", title="J2 motor", sources=[dict(SRC)],
                                       quantities={"max_speed": q(1500, "rpm")}), BODY)
    bundle.add("gearboxes/j2.md", concept(type="Gearbox", title="J2 gearbox", sources=[dict(SRC)],
                                          quantities={"ratio": q(50, "1")}), BODY)
    return bundle


def check(bundle):
    return errors(validate(bundle.root, [PROFILE]))


def test_a_complete_joint_passes(arm):
    arm.add("joints/j2.md", joint(), BODY)
    assert check(arm) == []


def test_a_joint_without_an_effort_limit_fails(arm):
    arm.add("joints/j2.md", joint(effort_limit=None), BODY)
    assert check(arm) == [("ar4.required", "joints/j2.md")]


def test_a_joint_without_dh_fails(arm):
    arm.add("joints/j2.md", joint(dh_a=None), BODY)
    assert check(arm) == [("ar4.required", "joints/j2.md")]


def test_a_limit_in_the_wrong_kind_of_unit_fails(arm):
    arm.add("joints/j2.md", joint(upper_limit=q(90, "mm")), BODY)
    assert check(arm) == [("ar4.required", "joints/j2.md")]


@pytest.mark.parametrize("bad", [q("ninety", "deg"), q(90, "furlongs"), {"value": 90, "unit": "deg"},
                                 q(90, "deg", source="manual-p37-2", formula="1"), q(90, "deg", source="no-such-id")])
def test_a_quantity_needs_a_number_a_known_unit_and_one_source_or_formula(arm, bad):
    arm.add("joints/j2.md", joint(upper_limit=bad), BODY)
    assert ("ar4.quantity", "joints/j2.md") in check(arm)


def test_a_formula_is_recomputed_from_the_quantities_it_names(arm):
    speed = {"value": 180, "unit": "deg/s", "formula": "6 * /motors/j2.md#max_speed / /gearboxes/j2.md#ratio"}
    arm.add("joints/j2.md", joint(velocity_limit=speed), BODY)
    assert check(arm) == []


def test_a_formula_whose_value_was_not_computed_from_it_fails(arm):
    speed = {"value": 45, "unit": "deg/s", "formula": "6 * /motors/j2.md#max_speed / /gearboxes/j2.md#ratio"}
    arm.add("joints/j2.md", joint(velocity_limit=speed), BODY)
    assert check(arm) == [("ar4.formula", "joints/j2.md")]


@pytest.mark.parametrize("formula", ["/motors/j2.md#torque * 50", "__import__('os')", "/motors/nope.md#max_speed"])
def test_a_formula_may_use_only_numbers_arithmetic_and_existing_quantities(arm, formula):
    arm.add("joints/j2.md", joint(effort_limit={"value": 1, "unit": "N m", "formula": formula}), BODY)
    assert check(arm) == [("ar4.formula", "joints/j2.md")]


def test_a_joint_connects_two_link_pages(arm):
    arm.add("joints/j2.md", dict(joint(), child="/motors/j2.md"), BODY)
    assert check(arm) == [("ar4.link", "joints/j2.md")]


def test_a_link_names_its_material_page(arm):
    arm.add("links/link-3.md", concept(type="Link", title="Link 3", sources=[dict(SRC)]), BODY)
    assert check(arm) == [("ar4.required", "links/link-3.md")]


def test_a_gearbox_needs_its_ratio_and_a_material_its_density(arm):
    arm.add("gearboxes/j3.md", concept(type="Gearbox", title="J3 gearbox", sources=[dict(SRC)]), BODY)
    arm.add("materials/steel.md", concept(type="Material", title="Steel", sources=[dict(SRC)]), BODY)
    assert check(arm) == [("ar4.required", "gearboxes/j3.md"), ("ar4.required", "materials/steel.md")]


def gripper(**quantities):
    base = {"jaw_stroke": q(12, "mm"), "jaw_force": q(40, "N"), "jaw_speed": q(60, "mm/s")}
    base.update(quantities)
    return concept(type="Gripper", title="Servo gripper", material="/materials/aluminum-6061.md",
                   sources=[dict(SRC)], quantities={k: v for k, v in base.items() if v is not None})


def test_a_gripper_needs_stroke_force_and_speed(arm):
    arm.add("grippers/servo.md", concept(type="Gripper", title="Servo gripper", material="/materials/aluminum-6061.md",
                                         sources=[dict(SRC)]), BODY)
    report = validate(arm.root, [PROFILE])
    found = [f for f in report.findings if f.level == "error"]
    assert errors(report) == [("ar4.required", "grippers/servo.md")]
    text = " ".join(f.message for f in found)
    for name in ("jaw_stroke", "jaw_force", "jaw_speed"):
        assert name in text


def test_a_complete_gripper_passes(arm):
    arm.add("grippers/servo.md", gripper(), BODY)
    assert check(arm) == []


def test_jaw_speed_in_a_length_unit_is_an_error(arm):
    arm.add("grippers/servo.md", gripper(jaw_speed=q(60, "mm")), BODY)
    report = validate(arm.root, [PROFILE])
    found = [f for f in report.findings if f.level == "error"]
    assert errors(report) == [("ar4.required", "grippers/servo.md")]
    assert len(found) == 1 and "speed" in found[0].message


def test_a_gripper_needs_its_material(arm):
    arm.add("grippers/servo.md", concept(type="Gripper", title="Servo gripper", sources=[dict(SRC)],
                                         quantities={"jaw_stroke": q(12, "mm"), "jaw_force": q(40, "N"),
                                                     "jaw_speed": q(60, "mm/s")}), BODY)
    report = validate(arm.root, [PROFILE])
    assert errors(report) == [("ar4.required", "grippers/servo.md")]
    assert "material" in " ".join(f.message for f in report.findings if f.level == "error")


def test_a_formula_over_volume_and_density_gives_a_mass(arm):
    arm.add("materials/petg.md", concept(type="Material", title="PETG", sources=[dict(SRC)],
                                         quantities={"density": q(1.27, "g/cm^3")}), BODY)
    arm.add("grippers/servo.md", concept(
        type="Gripper", title="Servo gripper", material="/materials/petg.md", sources=[dict(SRC)],
        quantities={"jaw_stroke": q(12, "mm"), "jaw_force": q(40, "N"), "jaw_speed": q(60, "mm/s"),
                    "volume": q(20000, "mm^3"),
                    "mass": {"value": 0.0254, "unit": "kg",
                             "formula": "/grippers/servo.md#volume * /materials/petg.md#density * 1e-6"}}), BODY)
    assert check(arm) == []


def test_time_units_are_known():
    from twin_tools import units as U
    assert U.kind("s") == U.kind("us") == "time"
    assert U.to_si(1, "us") == 1e-6
