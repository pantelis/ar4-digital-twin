"""The arm of twin_ok.py with values typed in next to kDB reads that hold the same numbers but are never used.

J2's effort limit is typed as 40.0 while si("joints/j2.md", "effort_limit") (40 N m) is read and dropped. The upper
arm's density is typed as 2700.0, the aluminum density, in a shape config of its own. J2's velocity limit is computed
from a read (times 1.0), so it is a derived value, not the read. None of the three is traced to the kDB."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from fixtures.twin_ok import FOREARM, build_gripper, joint  # noqa: F401  (the standalone gripper is twin_ok's)
from twin_tools.kdb import si


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    typed = newton.ModelBuilder.ShapeConfig(density=2700.0)
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=typed)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    page = "joints/j2.md"
    si(page, "effort_limit")  # read, and never used
    builder.add_joint_revolute(-1, upper, parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               label="J2", limit_lower=si(page, "lower_limit"), limit_upper=si(page, "upper_limit"),
                               effort_limit=40.0, velocity_limit=si(page, "velocity_limit") * 1.0)
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM))
    builder.add_articulation(list(range(builder.joint_count)))
