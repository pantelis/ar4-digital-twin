"""Joints left at Newton's defaults (limits of 1e10, effort and velocity limits of 1e6) and a link with no shapes."""
import warp as wp

import newton


def build(builder: newton.ModelBuilder) -> None:
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, hx=0.15, hy=0.03, hz=0.01, cfg=newton.ModelBuilder.ShapeConfig(density=2700.0))
    empty = builder.add_link(label="motor_bracket")
    j2 = builder.add_joint_revolute(-1, upper, axis=(0.0, 1.0, 0.0), label="J2")
    j3 = builder.add_joint_revolute(upper, empty, parent_xform=wp.transform((0.3, 0.0, 0.0), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                                    limit_lower=-1.0, limit_upper=1.0, effort_limit=5.0, velocity_limit=2.0, label="J3")
    builder.add_articulation([j2, j3])
