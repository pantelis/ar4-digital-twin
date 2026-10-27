"""The two-link arm of twin_ok.py with no gripper: it defines build() and no build_gripper()."""
import warp as wp

import newton
from twin_tools.kdb import si


def joint(builder, parent, child, page, **kw):
    return builder.add_joint_revolute(parent, child, axis=(0.0, 1.0, 0.0), label=page.split("/")[-1][:-3].upper(),
                                      limit_lower=si(page, "lower_limit"), limit_upper=si(page, "upper_limit"),
                                      effort_limit=si(page, "effort_limit"), velocity_limit=si(page, "velocity_limit"), **kw)


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((0.11, 0.0, 0.0), wp.quat_identity()), hx=0.11, hy=0.025, hz=0.01, cfg=cfg)
    j2 = joint(builder, -1, upper, "joints/j2.md", parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()))
    j3 = joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    builder.add_articulation([j2, j3])
