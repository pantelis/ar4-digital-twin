"""twin_tools.kdb: build.py reads quantities in SI units, and every read is recorded for twin-check."""
import math
from pathlib import Path

import pytest

from twin_tools import kdb

FIX = Path(__file__).parent / "fixtures" / "kdb"


@pytest.fixture(autouse=True)
def fixture_kdb():
    kdb.use(FIX)
    yield
    kdb.use(None)


def test_si_converts_to_si_units():
    assert kdb.si("joints/j3.md", "upper_limit") == pytest.approx(1.2)
    assert kdb.si("joints/j3.md", "effort_limit") == pytest.approx(20.0)
    assert kdb.si("materials/aluminum.md", "density") == pytest.approx(2700.0)


def test_every_read_is_recorded():
    kdb.si("joints/j2.md", "upper_limit")
    kdb.si("joints/j3.md", "lower_limit")
    assert [(r.page, r.name) for r in kdb.reads()[-2:]] == [("joints/j2.md", "upper_limit"), ("joints/j3.md", "lower_limit")]
    assert kdb.reads()[-1].si == pytest.approx(-1.2)


@pytest.mark.parametrize("page, name, says", [("joints/j9.md", "upper_limit", "no page"),
                                               ("joints/j2.md", "torque", "lower_limit"),
                                               ("../outside.md", "x", "no page")])
def test_a_missing_page_or_quantity_says_what_there_is(page, name, says):
    with pytest.raises(kdb.KdbError, match=says):
        kdb.si(page, name)


def test_a_degree_value_comes_back_in_radians():
    assert math.degrees(kdb.si("joints/j3.md", "upper_limit")) == pytest.approx(68.75493541569878)
