"""The course's pick-and-place task: the cube the gripper picks up and the box it places the cube in.

Lengths are in m, masses in kg, angles in rad. The table top is the plane z = TABLE_Z, and the arm's base is
welded to the world origin, so x runs away from the base and y to its left.
"""
import math

CUBE_EDGE = 0.025    # m; a cube that fits the gripper's open jaws with room to spare
CUBE_MASS = 0.05     # kg
CUBE_FRICTION = 0.8  # Coulomb friction coefficient of the cube's surface

TABLE_Z = 0.0           # m; height of the table top
BOX_INNER = 0.08        # m; side of the box's square opening, inside the walls
BOX_WALL_HEIGHT = 0.05  # m
BOX_WALL_THICKNESS = 0.004  # m
BOX_MASS = 0.3          # kg; light enough that a bad place pushes the box

# Where a reset puts the cube (x, y, and yaw about z) and the box (x, and |y| on the side opposite the cube)
CUBE_X = (0.25, 0.35)      # m
CUBE_Y = (-0.15, 0.15)     # m
BOX_X = (0.25, 0.35)       # m
BOX_ABS_Y = (0.15, 0.25)   # m
HOLD_S = 0.5               # s a skill must hold its success condition to count

# How a round of evaluation is run
EVAL_EPISODES = 512        # episodes per round; stage 3 measured every skill on 512
ACTION_TIMEOUT_S = 5.0     # s a skill gets per action, the episode length it trained with
PRACTICE_SEED = 30_000     # the seed students practice on, apart from the training seeds and from 10 000 and 20 000


def sample_placements(rng, n: int):
    """n cube poses (x, y, yaw) and n box centers (x, y), the box on the side opposite the cube's y.

    The box is at least 0.15 m from the cube along y, so the cube starts at least 0.03 m from the box's outer wall.
    """
    import numpy as np

    cube = np.stack([rng.uniform(*CUBE_X, n), rng.uniform(*CUBE_Y, n), rng.uniform(-math.pi, math.pi, n)], axis=1)
    side = np.where(cube[:, 1] == 0.0, rng.choice([-1.0, 1.0], n), -np.sign(cube[:, 1]))
    box = np.stack([rng.uniform(*BOX_X, n), side * rng.uniform(*BOX_ABS_Y, n)], axis=1)
    return cube, box
