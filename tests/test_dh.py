"""twin_tools.dh: standard DH frames from the kDB's rows, checked against poses worked out by hand."""
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from twin_tools import dh, kdb  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "kdb"
D = math.radians

# A made-up six-joint table, the rows of fixtures/kdb: theta offset and alpha in degrees, d and a in mm
ROWS = [(0, -90, 150, 50), (90, 0, 0, 280), (-90, 90, 0, 0), (0, -90, 240, 0), (0, 90, 0, 0), (0, 0, 35, 0)]
ARM = [dh.DH(D(t), D(al), d * 1e-3, a * 1e-3) for t, al, d, a in ROWS]


@pytest.fixture(autouse=True)
def fixture_kdb():
    kdb.use(FIX)
    kdb.clear()
    yield
    kdb.use(None)


def test_a_pose_with_the_wrist_bent():
    flange = dh.frames(ARM, [D(a) for a in (0, 0, 0, 0, 90, 0)])[-1]
    assert flange[:3, 3] == pytest.approx([0.085, 0, 0.11], abs=1e-9)
    assert flange[:3, :3] == pytest.approx(np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]]), abs=1e-9)


def test_all_joints_at_zero():
    flange = dh.frames(ARM, [0] * 6)[-1]
    assert flange[:3, 3] == pytest.approx([0.05, 0, 0.145], abs=1e-9)


def test_frames_start_at_the_world_frame_and_axes_are_those_of_the_previous_frame():
    frames = dh.frames(ARM, [0] * 6)
    assert len(frames) == 7
    assert np.array_equal(frames[0], np.eye(4))
    axes = dh.axes(frames)
    assert len(axes) == 6
    origin, z = axes[1]
    assert origin == pytest.approx(frames[1][:3, 3])
    assert z == pytest.approx(frames[1][:3, 2])
    assert np.linalg.norm(z) == pytest.approx(1)


def test_row_reads_and_records():
    got = dh.row("joints/j2.md")
    assert got == dh.DH(D(90), 0.0, 0.0, 0.280)
    assert dh.row("joints/j3.md") == dh.DH(D(-90), D(90), 0.0, 0.0)
    assert [r.name for r in kdb.reads()[:4]] == ["dh_theta_offset", "dh_alpha", "dh_d", "dh_a"]
    assert len(kdb.reads()) == 8
