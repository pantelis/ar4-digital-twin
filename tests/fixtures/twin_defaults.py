"""Joints left at Newton's defaults (limits of 1e10, effort and velocity limits of 1e6) and a link with no shapes.
Its gripper is correct, so every finding comes from the arm."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on


def build(builder: newton.ModelBuilder) -> None:
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, hx=0.15, hy=0.03, hz=0.01, cfg=newton.ModelBuilder.ShapeConfig(density=2700.0))
    empty = builder.add_link(label="motor_bracket")
    builder.add_joint_revolute(-1, upper, axis=(0.0, 1.0, 0.0), label="J2")
    builder.add_joint_revolute(upper, empty, parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               limit_lower=-1.0, limit_upper=1.0, effort_limit=5.0, velocity_limit=2.0, label="J3")
    add_gripper(builder, upper, mount_on(0.15))
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
