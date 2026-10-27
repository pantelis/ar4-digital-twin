"""The arm of twin_arm6.py with J4 anchored 30 mm along its own axis. It is the same mechanism."""
from fixtures.twin_arm6 import build_arm, build_gripper  # noqa: F401


def build(builder):
    build_arm(builder, move=(4, (0.0, 0.0, 0.03)))
