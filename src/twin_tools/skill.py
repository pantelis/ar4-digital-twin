"""The skill interface: what a trained skill takes in and gives out, so the course can run every student's skill the same way.

A skill is a TorchScript file. It maps a float32 batch of raw observations, shape (N, OBS_DIM), to a float32 batch of
actions, shape (N, ACT_DIM). Raw means not normalized: if your policy normalizes its inputs, the normalizer lives inside
the saved module (rsl_rl's export_policy_to_jit saves it that way).

Observation, in the order of OBSERVATION. Positions are in m in the base frame, which is DH frame 0 and also the world,
because the arm's base is welded at the origin. Quaternions are (x, y, z, w), the order Warp uses.
    joint_pos    6  rad     J1 to J6
    joint_vel    6  rad/s   J1 to J6
    jaw_opening  1  m       JAW1 plus JAW2, so 0 is closed and jaw_stroke is fully open
    grasp_pos    3  m       the grasp point between the jaws
    grasp_quat   4          orientation of the grasp point
    cube_pos     3  m       center of the cube
    cube_quat    4          orientation of the cube
    box_pos      3  m       center of the box's bottom face
    last_action  7          the action at the previous control step, after the clip to [-1, 1] below, so in
                            [-1, 1] even when the skill gave more (zeros at the first step)

Action, in the order of ACTION. The skill runs at CONTROL_HZ. Each value is first clipped to [-1, 1].
    arm   6   each value moves its joint's position target. The targets start at the arm's joint positions when the
              skill starts. Then, at every control step, for each joint J1 to J6:
                  a      = clip(a, -1, 1)
                  target = clip(target + a * v_max / CONTROL_HZ, lower limit, upper limit)
              where v_max is the joint's velocity limit, in rad/s, and the limits are its joint limits, all from the
              twin (its kDB values). An action of 1 moves the target at the joint's full speed; 0 leaves it still.
    jaw   1   a >= 0 opens the jaws to jaw_stroke, a < 0 closes them. The jaw target does not jump: it moves toward
              the new end at a constant rate, a full stroke in JAW_RAMP_S, updated at every physics step. A jaw driven
              straight to closed hits the cube hard enough to bounce off it.
"""
from pathlib import Path

OBSERVATION = (  # (name, size), in the order the skill receives them
    ("joint_pos", 6),
    ("joint_vel", 6),
    ("jaw_opening", 1),
    ("grasp_pos", 3),
    ("grasp_quat", 4),
    ("cube_pos", 3),
    ("cube_quat", 4),
    ("box_pos", 3),
    ("last_action", 7),
)
ACTION = (("arm", 6), ("jaw", 1))  # (name, size), in the order the skill gives them

OBS_DIM = sum(size for _, size in OBSERVATION)  # 37
ACT_DIM = sum(size for _, size in ACTION)       # 7
CONTROL_HZ = 50       # Hz; how often the skill is called
JAW_RAMP_S = 0.1      # s a jaw target takes to move from fully open to closed, or back


def load_skill(path, device="cpu"):
    """The skill saved at path, as a function from a (N, OBS_DIM) float32 tensor to a (N, ACT_DIM) one.

    The caller puts the observations on the given device."""
    import torch

    model = torch.jit.load(str(path), map_location=device)
    model.eval()

    def act(obs):
        with torch.no_grad():
            return model(obs)

    return act


def _accepted_size(act, limit=256):
    """The observation size the module accepts, found by trying 1, 2, ... (None if none up to limit works)."""
    import torch

    for n in range(1, limit + 1):
        try:
            act(torch.zeros(1, n))
            return n
        except Exception:
            pass
    return None


def _last_line(err):
    """The last line of an error's message, or the exception's type name if it has no message."""
    lines = str(err).strip().splitlines()
    return lines[-1] if lines else type(err).__name__


def _output_problem(out, n):
    """A sentence if out is not a finite (n, ACT_DIM) tensor, else None."""
    import torch

    if not isinstance(out, torch.Tensor):
        return f"the skill must give a tensor and gave a {type(out).__name__} for a batch of {n}"
    if out.ndim != 2 or out.shape[0] != n:
        return f"the skill must give a tensor of shape ({n}, {ACT_DIM}) for a batch of {n} and gave shape {tuple(out.shape)}"
    if out.shape[1] != ACT_DIM:
        return f"the skill gives {out.shape[1]} actions, the interface has {ACT_DIM}"
    if not torch.isfinite(out).all():
        return f"the skill gives actions that are not finite on a batch of {n}"
    return None


def check_skill(path) -> list[str]:
    """The problems with the skill file at path, as plain sentences. An empty list means the skill fits the interface.

    It never raises for a bad file.
    """
    import torch

    if not Path(path).is_file():
        return [f"there is no file at {path}"]
    try:
        act = load_skill(path)
    except Exception as err:
        return [f"{path} is not a TorchScript file ({_last_line(err)}); save it with torch.jit.script(...).save() or export_policy_to_jit"]

    try:
        out = act(torch.zeros(1, OBS_DIM))
    except Exception as err:
        size = _accepted_size(act)
        if size is None:
            return [f"the skill failed on a (1, {OBS_DIM}) batch: {_last_line(err)}"]
        return [f"the skill expects {size} observations, the interface has {OBS_DIM}"]
    problem = _output_problem(out, 1)
    if problem:
        return [problem]

    problems = []
    for n, obs in ((64, torch.randn(64, OBS_DIM, generator=torch.Generator().manual_seed(0))),):
        try:
            problem = _output_problem(act(obs), n)
        except Exception as err:
            return [f"the skill failed on a ({n}, {OBS_DIM}) batch: {_last_line(err)}"]
        if problem:
            problems.append(problem)
    return problems
