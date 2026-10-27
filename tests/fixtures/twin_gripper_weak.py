"""The arm of twin_ok.py with a gripper that reads grippers/weak.md (jaw force 0.05 N) on the arm and on its
own. Every other check passes, but the jaws squeeze too weakly for friction to hold the 50 g cube."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from fixtures.twin_ok import FOREARM, joint
from twin_tools.kdb import si

PAGE = "grippers/weak.md"


def build(builder: newton.ModelBuilder, jaw_mu: float | None = None) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    joint(builder, -1, upper, "joints/j2.md", parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()))
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM), page=PAGE, jaw_mu=jaw_mu)
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder, jaw_mu: float | None = None) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity(), page=PAGE, jaw_mu=jaw_mu)
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
