"""The arm of twin_ok.py whose jaws, on the arm and alone, take their effort limit from the PETG density read
(1270 kg/m^3 in SI) instead of the page's jaw force. The number comes from the kDB, but it is a density, not a force."""
import warp as wp

import newton
from fixtures.gripper import add_gripper_values, mount_on
from fixtures.twin_ok import FOREARM, joint
from twin_tools.kdb import si

PAGE = "grippers/servo.md"


def gripper(builder, parent, xform):
    density = si("materials/petg.md", "density")
    return add_gripper_values(builder, parent, xform, stroke=si(PAGE, "jaw_stroke"), force=density,
                              speed=si(PAGE, "jaw_speed"), density=density)


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    joint(builder, -1, upper, "joints/j2.md", parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()))
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    gripper(builder, fore, mount_on(FOREARM))
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
