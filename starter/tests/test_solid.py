"""twinagent.solid measures a mesh: volume, size, closed, pieces and through holes."""
import pytest
from meshes import box, frame, write

from twinagent import solid


def test_a_box_is_one_closed_piece_with_no_holes(tmp_path):
    m = solid.measure(write(tmp_path / "box.stl", box(365, 60, 20)))
    assert m.volume == pytest.approx(438000) and m.size == pytest.approx((365, 60, 20))
    assert m.closed and m.pieces == 1 and m.through_holes == 0


def test_a_frame_has_one_through_hole(tmp_path):
    m = solid.measure(write(tmp_path / "frame.stl", frame(60, 20, 10)))
    assert m.volume == pytest.approx((60**2 - 20**2) * 10) and m.through_holes == 1


def test_an_open_mesh_is_not_a_solid(tmp_path):
    m = solid.measure(write(tmp_path / "open.stl", box(10, 10, 10)[:-2]))
    assert not m.closed and m.through_holes is None


def test_two_separate_boxes_are_two_pieces(tmp_path):
    far = [tuple((x + 100, y, z) for x, y, z in t) for t in box(10, 10, 10)]
    assert solid.measure(write(tmp_path / "two.stl", box(10, 10, 10) + far)).pieces == 2


def test_an_ascii_stl_reads_the_same(tmp_path):
    lines = ["solid s"] + [f"facet normal 0 0 0\nouter loop\n" + "".join(f"vertex {x} {y} {z}\n" for x, y, z in t)
                           + "endloop\nendfacet" for t in box(2, 3, 4)] + ["endsolid s"]
    (tmp_path / "a.stl").write_text("\n".join(lines))
    assert solid.measure(tmp_path / "a.stl").volume == pytest.approx(24)
