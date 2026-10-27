"""An exact six-joint arm: body n sits at DH frame T_0n of fixtures/kdb joints J1 to J6, and joint n turns about z of
frame n-1. Every joint frame is rotated, so the axes are never exactly parallel in float32. The gripper is on link 6.
build_arm(flip, fixed, move) names a joint to turn about -z, to weld, or to anchor at move = (n, offset) in frame n-1,
for twin_arm6_flipped.py, twin_arm6_fixed.py, twin_arm6_slid.py and twin_arm6_off_axis.py."""
import numpy as np
import warp as wp

import newton
from fixtures.gripper import add_gripper
from twin_tools import dh
from twin_tools.kdb import si

def pose(m):
    q = wp.quat_from_matrix(wp.mat33(*[float(x) for x in m[:3, :3].flatten()]))
    return wp.transform(tuple(float(x) for x in m[:3, 3]), q)


def build_arm(builder: newton.ModelBuilder, flip=None, fixed=None, move=None) -> None:
    pages = [f"joints/j{n}.md" for n in range(1, 7)]
    rows = [dh.row(p) for p in pages]
    frames = dh.frames(rows, [0.0] * 6)
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    parent = -1
    for n in range(1, 7):
        link = builder.add_link(xform=pose(frames[n]), label=f"link{n}")
        builder.add_shape_box(link, hx=0.02, hy=0.02, hz=0.02, cfg=cfg)
        slide = np.eye(4)
        if move is not None and move[0] == n:
            slide[:3, 3] = move[1]
        child_x = pose(np.linalg.inv(frames[n]) @ frames[n - 1] @ slide)
        kw = dict(parent_xform=pose(slide), child_xform=child_x, label=f"J{n}")
        if n == fixed:
            builder.add_joint_fixed(parent, link, **kw)
        else:
            builder.add_joint_revolute(parent, link, axis=(0.0, 0.0, -1.0 if n == flip else 1.0),
                                       limit_lower=si(pages[n - 1], "lower_limit"), limit_upper=si(pages[n - 1], "upper_limit"),
                                       effort_limit=si(pages[n - 1], "effort_limit"), velocity_limit=si(pages[n - 1], "velocity_limit"), **kw)
        parent = link
    add_gripper(builder, parent, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))


def build(builder: newton.ModelBuilder) -> None:
    build_arm(builder)


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
