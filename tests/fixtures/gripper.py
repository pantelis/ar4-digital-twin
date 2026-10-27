"""A two-jaw gripper for the twin-check fixtures: a box base and two box jaws on prismatic joints JAW1 and JAW2.

In the gripper's frame z points out of the gripper and the jaws open along x. Each jaw's coordinate is
its opening from closed. Closed, the jaw faces are 10 mm apart; each jaw opens by the page's jaw_stroke
(12 mm on grippers/servo.md), so open they are 34 mm apart and the course's 25 mm cube (task.CUBE_EDGE) fits between them.
"""
import math
import posixpath

import warp as wp

import newton
from twin_tools import kdb
from twin_tools.kdb import si

BASE = (0.03, 0.015, 0.01)    # half extents of the base box (m); it spans z 0 to 0.02
JAW = (0.005, 0.01, 0.02)     # half extents of each jaw box; a jaw spans z 0.02 to 0.06
CLOSED_GAP = 0.010            # distance between the jaw faces when closed (m)
GRASP_Z = BASE[2] * 2 + JAW[2]  # the grasp point sits halfway along the jaws


def add_gripper(builder: newton.ModelBuilder, parent: int, xform: wp.transform, page: str = "grippers/servo.md",
                jaw_mu: float | None = None, on_jaw=None) -> wp.transform:
    """Build the gripper on body parent (-1 for the world) at xform, with every value read from the kDB page.
    jaw_mu, when given, is the friction coefficient of the jaw shapes (Newton's default otherwise).
    on_jaw, when given, is called as on_jaw(builder, jaw_body, side) right after each jaw's joint, to add parts to it."""
    material = posixpath.normpath(posixpath.join(posixpath.dirname(page), kdb.page(page)[0]["material"]))
    return add_gripper_values(builder, parent, xform, stroke=si(page, "jaw_stroke"), force=si(page, "jaw_force"),
                              speed=si(page, "jaw_speed"), density=si(material, "density"), jaw_mu=jaw_mu,
                              on_jaw=on_jaw)


def add_gripper_values(builder, parent, xform, *, stroke, force, speed, density, jaw_mu=None, on_jaw=None) -> wp.transform:
    """add_gripper with its values passed in. Returns the grasp frame in world coordinates (at the parent's build pose)."""
    cfg = newton.ModelBuilder.ShapeConfig(density=density)
    jaw_cfg = cfg if jaw_mu is None else newton.ModelBuilder.ShapeConfig(density=density, mu=jaw_mu)
    world = builder.body_q[parent] if parent >= 0 else wp.transform_identity()
    at = lambda x, z: wp.transform((x, 0.0, z), wp.quat_identity())
    base_xform = wp.transform_multiply(world, xform)
    base = builder.add_link(xform=base_xform, label="gripper_base")
    builder.add_shape_box(base, xform=at(0.0, BASE[2]), hx=BASE[0], hy=BASE[1], hz=BASE[2], cfg=cfg)
    builder.add_joint_fixed(parent, base, parent_xform=xform, label="gripper_mount")
    for n, side in ((1, 1.0), (2, -1.0)):
        rest = at(side * (CLOSED_GAP / 2 + JAW[0]), BASE[2] * 2 + JAW[2])
        jaw = builder.add_link(xform=wp.transform_multiply(base_xform, rest), label=f"jaw{n}")
        builder.add_shape_box(jaw, hx=JAW[0], hy=JAW[1], hz=JAW[2], cfg=jaw_cfg)
        builder.add_joint_prismatic(base, jaw, parent_xform=rest, axis=(side, 0.0, 0.0), label=f"JAW{n}",
                                    limit_lower=0.0, limit_upper=stroke, effort_limit=force, velocity_limit=speed)
        if on_jaw is not None:
            on_jaw(builder, jaw, side)
    return wp.transform_multiply(base_xform, at(0.0, GRASP_Z))


def mount_on(length: float) -> wp.transform:
    """Where the gripper sits on a link along x of this length: at its end, z turned to point along the link's x."""
    return wp.transform((length, 0.0, 0.0), wp.quat_from_axis_angle(wp.vec3(0.0, 1.0, 0.0), math.pi / 2))
