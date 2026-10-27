"""The arm of twin_arm6.py with J5 turning about -z. Its pairs are still right, so only the full chain sees it."""
from fixtures.twin_arm6 import build_arm, build_gripper  # noqa: F401


def build(builder):
    build_arm(builder, flip=5)
