"""twin-check needs Newton, so these tests run inside the project container (see docker/)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("newton")
from twin_tools.check import check  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def rules(report, level="error"):
    return sorted((f.rule, f.path) for f in report.findings if f.level == level)


def test_complete_twin_has_no_findings():
    report = check(FIX / "twin_ok.py", kdb=FIX / "kdb")
    assert report.findings == []
    assert report.summary["bodies"] == 2 and report.summary["joints"] == 2


def test_default_limits_and_massless_link_are_errors():
    report = check(FIX / "twin_defaults.py", trace=False)
    assert rules(report) == [("effort-limit", "J2"), ("joint-limits", "J2"), ("mass", "motor_bracket"), ("velocity-limit", "J2")]


def test_build_errors_are_reported_not_raised():
    assert rules(check(FIX / "twin_broken.py", trace=False)) == [("build", "twin_broken.py")]
    assert rules(check(FIX / "twin_nobuild.py", trace=False)) == [("build", "twin_nobuild.py")]


def test_passive_drop_stays_finite_and_inside_limits():
    report = check(FIX / "twin_ok.py", seconds=1.0, kdb=FIX / "kdb")
    assert report.summary["drop_seconds"] == 1.0
    assert not [f for f in report.findings if f.rule == "drop"]


def test_cli_json_and_exit_status():
    run = lambda name: subprocess.run([sys.executable, "-m", "twin_tools.check", str(FIX / name), "--json", "--kdb", str(FIX / "kdb")],
                                      capture_output=True, text=True, timeout=600)
    ok, bad = run("twin_ok.py"), run("twin_defaults.py")
    assert ok.returncode == 0 and json.loads(ok.stdout)["findings"] == []
    assert bad.returncode == 1 and {f["rule"] for f in json.loads(bad.stdout)["findings"]} >= {"mass", "joint-limits"}


def test_values_typed_in_rather_than_read_from_the_kdb_are_untraced():
    report = check(FIX / "twin_literals.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("trace", "J2"), ("trace", "J3"), ("trace", "forearm"), ("trace", "upper_arm")]
    j2 = next(f for f in report.findings if f.path == "J2")
    assert all(k in j2.message for k in ("lower limit", "upper limit", "effort limit", "velocity limit"))


def test_newtons_default_density_is_untraced():
    report = check(FIX / "twin_default_density.py", seconds=0, kdb=FIX / "kdb")
    assert rules(report) == [("trace", "upper_arm")]
    assert "1000" in report.findings[0].message
