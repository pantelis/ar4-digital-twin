"""The arm of twin_ok.py whose gripper reads grippers/strong.md (jaw force 80 N), while build_gripper()
reads grippers/servo.md (40 N): the gripper on the arm is not the one built on its own."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from fixtures.twin_ok import FOREARM, joint
from twin_tools.kdb import si


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    joint(builder, -1, upper, "joints/j2.md", parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()))
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM), page="grippers/strong.md")
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
