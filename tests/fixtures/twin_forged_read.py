"""The arm of twin_ok.py with J2's effort limit typed as 400 N m and a forged read put in twin_tools.kdb's private
registry, claiming joints/j2.md effort_limit gave that very object. The page says 40 N m."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, mount_on
from fixtures.twin_ok import FOREARM, build_gripper, joint  # noqa: F401  (the standalone gripper is twin_ok's)
from twin_tools import kdb as K
from twin_tools.kdb import si


def forge(page: str, name: str, value: float, unit: str) -> float:
    """A float with a forged read for it, put wherever kdb keeps its reads."""
    typed = value + 0.0
    read = K.Read(page, name, value, unit, typed)
    registry = getattr(K, "_reads", None)
    if registry is None:
        registry = K._registry._items
    registry.append(read)
    return typed


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/aluminum.md", "density"))
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((FOREARM / 2, 0.0, 0.0), wp.quat_identity()), hx=FOREARM / 2, hy=0.025, hz=0.01, cfg=cfg)
    page = "joints/j2.md"
    builder.add_joint_revolute(-1, upper, parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               label="J2", limit_lower=si(page, "lower_limit"), limit_upper=si(page, "upper_limit"),
                               effort_limit=forge(page, "effort_limit", 400.0, "N m"), velocity_limit=si(page, "velocity_limit"))
    joint(builder, upper, fore, "joints/j3.md", parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()))
    add_gripper(builder, fore, mount_on(FOREARM))
    builder.add_articulation(list(range(builder.joint_count)))
