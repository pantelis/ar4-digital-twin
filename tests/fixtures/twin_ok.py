"""A two-link arm with every value set: masses from shapes, joint limits, effort and velocity limits."""
import warp as wp

import newton


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=2700.0)
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((0.11, 0.0, 0.0), wp.quat_identity()), hx=0.11, hy=0.025, hz=0.01, cfg=cfg)
    j2 = builder.add_joint_revolute(-1, upper, parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                                    limit_lower=-0.7, limit_upper=1.5, effort_limit=40.0, velocity_limit=2.0, label="J2")
    j3 = builder.add_joint_revolute(upper, fore, parent_xform=wp.transform((0.3, 0.0, 0.0), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                                    limit_lower=-1.2, limit_upper=1.2, effort_limit=20.0, velocity_limit=2.5, label="J3")
    builder.add_articulation([j2, j3])
