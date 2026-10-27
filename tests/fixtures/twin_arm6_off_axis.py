"""The arm of twin_arm6.py with J6 anchored 5 mm off its axis, along z of frame 4. That keeps the J5 and J6 axes
meeting, so only the full chain sees it."""
import numpy as np

from fixtures.twin_arm6 import build_arm, build_gripper  # noqa: F401
from twin_tools import dh


def build(builder):
    frames = dh.frames([dh.row(f"joints/j{n}.md") for n in range(1, 7)], [0.0] * 6)
    build_arm(builder, move=(6, 0.005 * (frames[5][:3, :3].T @ frames[4][:3, 2])))
