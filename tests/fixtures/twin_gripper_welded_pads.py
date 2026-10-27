"""The weak gripper of twin_gripper_weak.py (jaw force 0.05 N) with a thin pad on each jaw's inner face. Each pad is
its own body, welded to its jaw with a fixed joint, and its shape is sticky (friction 100) and soft. Pads like
that would hold the 50 g cube, but the grasp check gives every shape of the gripper the course's friction and
contact, so the cube still falls."""
import warp as wp

import newton
from fixtures.gripper import JAW, add_gripper
from fixtures.twin_gripper_weak import PAGE, build  # noqa: F401  (the arm is the weak twin's)
from twin_tools.kdb import si

PAD = 0.0005  # m, half the pad's thickness
PAD_MU = 100.0
PAD_KE, PAD_KD = 100.0, 20.0  # a soft contact: MuJoCo time constant 2 / kd = 0.1 s


def add_pad(builder: newton.ModelBuilder, jaw: int, side: float) -> None:
    cfg = newton.ModelBuilder.ShapeConfig(density=si("materials/petg.md", "density"), mu=PAD_MU, ke=PAD_KE, kd=PAD_KD)
    face = wp.transform((-side * (JAW[0] + PAD), 0.0, 0.0), wp.quat_identity())  # on the jaw's inner face
    pad = builder.add_link(xform=wp.transform_multiply(builder.body_q[jaw], face), label=f"{builder.body_label[jaw]}_pad")
    builder.add_shape_box(pad, hx=PAD, hy=JAW[1], hz=JAW[2], cfg=cfg)
    builder.add_joint_fixed(jaw, pad, parent_xform=face, label=f"{builder.body_label[jaw]}_pad_weld")


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    grasp = add_gripper(builder, -1, wp.transform_identity(), page=PAGE, on_jaw=add_pad)
    builder.add_articulation(list(range(builder.joint_count)))
    return grasp
