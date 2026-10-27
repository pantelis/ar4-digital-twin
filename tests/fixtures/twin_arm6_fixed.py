"""The arm of twin_arm6.py with J4 welded instead of revolute."""
from fixtures.twin_arm6 import build_arm, build_gripper  # noqa: F401


def build(builder):
    build_arm(builder, fixed=4)
