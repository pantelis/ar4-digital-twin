"""The arm of twin_ok.py with its values typed in as numbers instead of read from the kDB.
Its gripper types in the jaw stroke (0.012 m) and speed and reads the jaw force; build_gripper() reads everything.
The 40 N jaw force read does not trace J2's typed-in effort limit of 40 N m, because a torque must come from a torque."""
import warp as wp

import newton
from fixtures.gripper import add_gripper, add_gripper_values, mount_on
from twin_tools.kdb import si


def build(builder: newton.ModelBuilder) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=2700.0)
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, xform=wp.transform((0.15, 0.0, 0.0), wp.quat_identity()), hx=0.15, hy=0.03, hz=0.01, cfg=cfg)
    fore = builder.add_link(label="forearm")
    builder.add_shape_box(fore, xform=wp.transform((0.11, 0.0, 0.0), wp.quat_identity()), hx=0.11, hy=0.025, hz=0.01, cfg=cfg)
    builder.add_joint_revolute(-1, upper, parent_xform=wp.transform((0.0, 0.0, 0.5), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               limit_lower=-0.7, limit_upper=1.5, effort_limit=40.0, velocity_limit=2.0, label="J2")
    builder.add_joint_revolute(upper, fore, parent_xform=wp.transform((0.280, 0.0, 0.0), wp.quat_identity()), axis=(0.0, 1.0, 0.0),
                               limit_lower=-1.2, limit_upper=1.2, effort_limit=20.0, velocity_limit=2.5, label="J3")
    add_gripper_values(builder, fore, mount_on(0.22), stroke=0.012, force=si("grippers/servo.md", "jaw_force"), speed=0.06,
                       density=si("materials/petg.md", "density"))
    builder.add_articulation(list(range(builder.joint_count)))


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity())
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
