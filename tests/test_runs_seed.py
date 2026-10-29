"""The runs seed: every class maps to ML Schema or PROV-O, and the link fields are properties."""

from pathlib import Path

import pytest
import yaml

SEED = Path(__file__).parent.parent / "src" / "twin_tools" / "seeds" / "runs.yaml"
NAMESPACES = ("http://www.w3.org/ns/mls#", "http://www.w3.org/ns/prov#")
LINK_FIELDS = ("achieves", "implementation", "algorithm", "inputs", "outputs", "generated_by", "started", "ended",
               "judged_by")


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(SEED.read_text())


def test_the_seed_parses_and_maps_every_class(spec):
    assert spec["domain"] == "runs"
    assert spec["base_iri"] == "https://kdb.aegean.ai/ar4/runs/"
    classes = {c["slug"]: c for c in spec["classes"]}
    assert set(classes) == {"task", "action", "predicate", "task-object", "evaluation-spec", "algorithm",
                            "implementation", "trainer-config", "design-snapshot", "training-run", "policy",
                            "evaluation", "episode", "metric"}
    for slug, c in classes.items():
        assert c["close_match"], slug
        assert all(m.startswith(NAMESPACES) for m in c["close_match"]), slug
    properties = {p["slug"] for p in spec["properties"]}
    assert set(LINK_FIELDS) <= properties


def test_the_profile_ships_the_seed():
    from twin_tools.profile import PROFILE

    assert PROFILE.check_rows is not None
    assert (Path(str(PROFILE.seeds)) / "runs.yaml").is_file()
