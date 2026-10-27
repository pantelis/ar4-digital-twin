"""The weak gripper of twin_gripper_weak.py whose build_gripper() returns its grasp frame turned over, z pointing
into the gripper. Gravity along that z pulls the cube onto the gripper base 5 mm below it, so the base, not
the jaws, would hold the cube."""
import math

import warp as wp

import newton
from fixtures.gripper import add_gripper
from fixtures.twin_gripper_weak import PAGE, build  # noqa: F401  (the arm is the weak twin's)


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity(), page=PAGE)
    builder.add_articulation(list(range(builder.joint_count)))
    flip = wp.transform(wp.vec3(0.0, 0.0, 0.0), wp.quat_from_axis_angle(wp.vec3(1.0, 0.0, 0.0), math.pi))
    return wp.transform_multiply(grasp, flip)
