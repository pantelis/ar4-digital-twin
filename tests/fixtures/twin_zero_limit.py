"""The arm of twin_ok.py with J2's lower limit typed in as 0. Only a jaw's closed limit may be 0 without a kDB read;
no arm joint of the AR4 has a limit of 0, so this one is untraced."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from fixtures.twin_ok import FOREARM, build_gripper, joint  # noqa: F401  (the standalone gripper is twin_ok's)
from twin_tools.kdb import si


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    page = "joints/j2.md"
    builder.add_joint_revolute(-1, upper, parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               label="J2", limit_lower=0.0, limit_upper=si(page, "upper_limit"),
                               effort_limit=si(page, "effort_limit"), velocity_limit=si(page, "velocity_limit"))
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM))
    builder.add_articulation(list(range(builder.joint_count)))
