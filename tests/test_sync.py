"""twin-sync: the FreeCAD documents against the kDB. Needs freecadcmd, so these run in the container."""
import json
import shutil

import pytest

pytest.importorskip("numpy")

from twin_tools import sync  # noqa: E402

from fixtures import cad  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("freecadcmd") is None, reason="needs freecadcmd")


def found(report):
    return sorted((f.rule, f.path) for f in report.findings)


def test_a_bound_part_has_no_findings(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path)
    assert found(sync.sync(cad_dir, kdb_dir)) == []


def test_a_typed_in_pad_length_is_free(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, free_pad=True)
    report = sync.sync(cad_dir, kdb_dir)
    assert found(report) == [("sync.free", str(cad_dir / "link-2.FCStd"))]
    assert "Length" in report.findings[0].message


def test_a_spreadsheet_value_off_the_kdb(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, sheet_value=281.0)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.value", str(cad_dir / "link-2.FCStd"))]


def test_a_reference_to_no_quantity(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, bad_ref=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.ref", str(cad_dir / "link-2.FCStd"))]


def test_a_stale_export(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, stale_export=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.export", str(cad_dir / "link-2.FCStd"))]


def test_a_link_off_its_dh_frame(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, off_frame=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.frame", str(cad_dir / "ar4.FCStd"))]


def test_a_corrupt_document_is_a_finding(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, corrupt=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.load", str(cad_dir / "link-2.FCStd"))]


def test_a_missing_freecad_is_a_finding(tmp_path, monkeypatch):
    cad_dir, kdb_dir = cad.build(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    assert ("sync.load", str(cad_dir / "link-2.FCStd")) in found(sync.sync(cad_dir, kdb_dir))


@pytest.mark.parametrize("variant", [{"unnamed": True}, {"sheet_name": "Spreadsheet"}, {"indirect": "constraint"},
                                     {"indirect": "varset"}, {"unnamed": True, "indirect": "constraint"}])
def test_a_part_bound_in_the_usual_ways_has_no_findings(tmp_path, variant):
    cad_dir, kdb_dir = cad.build(tmp_path, **variant)
    assert found(sync.sync(cad_dir, kdb_dir)) == []


def test_a_chain_that_misses_the_sheet_is_free(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, indirect="varset_free")
    report = sync.sync(cad_dir, kdb_dir)
    assert found(report) == [("sync.free", str(cad_dir / "link-2.FCStd"))]
    assert "Length" in report.findings[0].message


def test_a_link_nested_in_a_part_is_checked_by_its_global_placement(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, nested=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == []
    cad_dir, kdb_dir = cad.build(tmp_path / "off", nested=True, off_frame=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.frame", str(cad_dir / "ar4.FCStd"))]


@pytest.mark.parametrize("link", ["top", "part", "assembly"])
def test_an_app_link_is_checked_by_its_global_placement(tmp_path, link):
    cad_dir, kdb_dir = cad.build(tmp_path / "good", link=link)
    assert found(sync.sync(cad_dir, kdb_dir)) == []
    cad_dir, kdb_dir = cad.build(tmp_path / "off", link=link, off_frame=True)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.frame", str(cad_dir / "ar4.FCStd"))]


def test_a_link_missing_from_the_assembly(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, omit_link=True)
    report = sync.sync(cad_dir, kdb_dir)
    assert found(report) == [("sync.frame", str(cad_dir / "ar4.FCStd"))]
    assert "link-2" in report.findings[0].message


def test_a_link_document_that_is_no_joints_child(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path)
    j2 = kdb_dir / "joints" / "j2.md"
    j2.write_text(j2.read_text().replace("child: ../links/link-2.md\n", ""))
    report = sync.sync(cad_dir, kdb_dir)
    assert found(report) == [("sync.frame", str(cad_dir / "ar4.FCStd"))]
    assert "link-2" in report.findings[0].message


def test_an_assembly_sheet_that_matches_has_no_findings(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, asm_sheet=280.0)
    assert found(sync.sync(cad_dir, kdb_dir)) == []


def test_an_assembly_sheet_value_off_the_kdb(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path, asm_sheet=281.0)
    assert found(sync.sync(cad_dir, kdb_dir)) == [("sync.value", str(cad_dir / "ar4.FCStd"))]


def test_no_assembly_yet_is_no_frame_finding(tmp_path):
    cad_dir, kdb_dir = cad.build(tmp_path)
    (cad_dir / "ar4.FCStd").unlink()
    assert found(sync.sync(cad_dir, kdb_dir)) == []


def test_cli_exit_status(tmp_path, capsys):
    good, kdb_good = cad.build(tmp_path / "good")
    assert sync.main([str(good), "--kdb", str(kdb_good)]) == 0
    bad, kdb_bad = cad.build(tmp_path / "bad", free_pad=True)
    assert sync.main([str(bad), "--kdb", str(kdb_bad), "--json"]) == 1
    out = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert out["findings"][0]["rule"] == "sync.free"
    assert sync.main([str(tmp_path / "missing"), "--kdb", str(kdb_bad)]) == 2
