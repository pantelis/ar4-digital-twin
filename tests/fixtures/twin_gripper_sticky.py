"""The weak gripper of twin_gripper_weak.py (jaw force 0.05 N) with jaw shapes of friction 100. Friction that
high would hold the 50 g cube, but the grasp check sets the jaws' friction to the course's own value, so the
cube still falls."""
import warp as wp

import newton
from fixtures import twin_gripper_weak as weak

JAW_MU = 100.0


def build(builder: newton.ModelBuilder) -> None:
    weak.build(builder, jaw_mu=JAW_MU)


def build_gripper(builder: newton.ModelBuilder) -> wp.transform:
    return weak.build_gripper(builder, jaw_mu=JAW_MU)
