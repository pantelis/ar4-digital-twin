"""The arm of twin_ok.py with J3 tilted 5e-5 rad about z, in the plane of the two axes. That is inside the angle
tolerance, so the pair is parallel and 0.280 m apart, but the lines now meet."""
import math

import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from twin_tools.kdb import si

FOREARM = 0.22  # m
TILT = 5e-5  # rad


def joint(builder, parent, child, page, axis=(0.0, 1.0, 0.0), **kw):
    return builder.add_joint_revolute(parent, child, axis=axis, label=page.split("/")[-1][:-3].upper(),
                                      limit_lower=si(page, "lower_limit"), limit_upper=si(page, "upper_limit"),
                                      effort_limit=si(page, "effort_limit"), velocity_limit=si(page, "velocity_limit"), **kw)


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    joint(builder, -1, upper, "joints/j2.md", parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()))
    joint(builder, upper, fore, "joints/j3.md", axis=(-math.sin(TILT), math.cos(TILT), 0.0), parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM))
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
