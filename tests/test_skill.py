"""twin_tools.skill: the observation layout, and loading and checking a saved skill."""
import pytest

torch = pytest.importorskip("torch")

from twin_tools import skill  # noqa: E402


def save(module, path):
    torch.jit.script(module).save(str(path))
    return path


def test_the_observation_layout_adds_up():
    assert skill.OBS_DIM == sum(size for _, size in skill.OBSERVATION)
    assert skill.OBS_DIM == 37
    assert skill.ACT_DIM == 7


def test_a_scripted_skill_passes(tmp_path):
    path = save(torch.nn.Linear(skill.OBS_DIM, skill.ACT_DIM), tmp_path / "ok.pt")
    assert skill.check_skill(path) == []
    act = skill.load_skill(path)
    assert act(torch.zeros(5, skill.OBS_DIM)).shape == (5, skill.ACT_DIM)


def test_a_skill_of_the_wrong_size_is_reported(tmp_path):
    path = save(torch.nn.Linear(skill.OBS_DIM - 1, skill.ACT_DIM), tmp_path / "small.pt")
    problems = skill.check_skill(path)
    assert len(problems) == 1
    assert str(skill.OBS_DIM - 1) in problems[0] and str(skill.OBS_DIM) in problems[0]


def test_a_skill_with_the_wrong_output_size_is_reported(tmp_path):
    path = save(torch.nn.Linear(skill.OBS_DIM, 6), tmp_path / "six.pt")
    problems = skill.check_skill(path)
    assert len(problems) == 1 and "6" in problems[0] and "7" in problems[0]


def test_a_file_that_is_not_torchscript_is_reported(tmp_path):
    path = tmp_path / "junk.pt"
    path.write_bytes(b"not a model")
    problems = skill.check_skill(path)
    assert len(problems) == 1 and "TorchScript" in problems[0]
    assert skill.check_skill(tmp_path / "missing.pt")


def test_a_skill_that_gives_nan_is_reported(tmp_path):
    class Nan(torch.nn.Module):
        def forward(self, x):
            return x[:, :7] * float("nan")

    problems = skill.check_skill(save(Nan(), tmp_path / "nan.pt"))
    assert any("not finite" in p for p in problems)


def test_a_skill_that_only_takes_one_row_is_reported(tmp_path):
    class OneRow(torch.nn.Module):
        def forward(self, x):
            return x.view(1, -1)[:, :7]

    problems = skill.check_skill(save(OneRow(), tmp_path / "one.pt"))
    assert len(problems) == 1
