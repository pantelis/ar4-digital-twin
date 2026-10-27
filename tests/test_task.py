"""twin_tools.task: the placement ranges hold, and the box never starts against the cube."""
import math

import pytest

np = pytest.importorskip("numpy")

from twin_tools import task  # noqa: E402

CLEARANCE = 0.03  # m between the cube's footprint and the box's outer wall


def test_placements_stay_in_range_and_apart():
    cube, box = task.sample_placements(np.random.default_rng(0), 10_000)
    assert cube.shape == (10_000, 3) and box.shape == (10_000, 2)
    assert cube[:, 0].min() >= task.CUBE_X[0] and cube[:, 0].max() <= task.CUBE_X[1]
    assert cube[:, 1].min() >= task.CUBE_Y[0] and cube[:, 1].max() <= task.CUBE_Y[1]
    assert cube[:, 2].min() >= -math.pi and cube[:, 2].max() <= math.pi
    assert box[:, 0].min() >= task.BOX_X[0] and box[:, 0].max() <= task.BOX_X[1]
    assert np.abs(box[:, 1]).min() >= task.BOX_ABS_Y[0] and np.abs(box[:, 1]).max() <= task.BOX_ABS_Y[1]
    assert np.all(np.sign(box[:, 1]) == -np.sign(cube[:, 1]))
    # The cube's circumscribed circle against the box's outer square, as the distance from the circle to the square
    half = task.BOX_INNER / 2 + task.BOX_WALL_THICKNESS
    outside = np.maximum(np.abs(cube[:, :2] - box) - half, 0.0)
    gap = np.linalg.norm(outside, axis=1) - task.CUBE_EDGE / math.sqrt(2)
    assert gap.min() >= CLEARANCE
