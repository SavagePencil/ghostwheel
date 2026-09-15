"""Convention over configuration: a checkout resolves as a sibling.

A dependency's checkout defaults to a sibling directory of the
depending knowledge base — named by the dependency's own name, or by
the one machine-independent `checkout` word the pin records when the
directory is called otherwise. Settings stay the override lane
(environment first, then .env — both arrive through the merged
config), and the convention never trusts a directory's name: the
found checkout must DECLARE the dependency's kb name or resolution
refuses by name. When every road is empty, the refusal names all
three, so the designer sees every door.

Storybook domain: Emberhold, pinned from a neighboring hearth.
"""

from graph import export as export_mod
from graph.dependencies import (drift_rows, read_dependency,
                                settings_key)
from graph.extract import GraphData
from graph.ontology import ARCHETYPE_LABEL
from graph.refs import KB_NAME_PROP, ONTOLOGY_ANCHOR

DEP = "emberhold"


def _checkout(root, dirname, kb, version=3):
    home = root / dirname
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, ONTOLOGY_ANCHOR,
                      **{KB_NAME_PROP: kb, "version": version})
    export_mod.write_export(graph, home / "graph" / "export")
    return home


def _depender(root):
    home = root / "hearthfall"
    home.mkdir(parents=True, exist_ok=True)
    return home


def test_the_convention_resolves_the_sibling_by_name(tmp_path):
    base = _depender(tmp_path)
    sibling = _checkout(tmp_path, DEP, DEP)
    checkout, problem = read_dependency({}, DEP, base_dir=base, props={})
    assert problem is None
    assert checkout is not None and checkout.path == sibling
    assert checkout.kb == DEP and checkout.sequence == 3


def test_the_pins_checkout_word_wins_over_the_name(tmp_path):
    base = _depender(tmp_path)
    named = _checkout(tmp_path, "the-emberhold-shelf", DEP)
    checkout, problem = read_dependency(
        {}, DEP, base_dir=base, props={"checkout": "the-emberhold-shelf"})
    assert problem is None
    assert checkout is not None and checkout.path == named


def test_settings_beat_the_convention(tmp_path):
    base = _depender(tmp_path)
    _checkout(tmp_path, DEP, DEP)  # the sibling exists…
    elsewhere = _checkout(tmp_path / "far", DEP, DEP, version=7)
    config = {settings_key(DEP): str(elsewhere)}
    checkout, problem = read_dependency(config, DEP, base_dir=base,
                                        props={})
    assert problem is None
    assert checkout is not None and checkout.path == elsewhere
    assert checkout.sequence == 7  # …and the configured one is read


def test_a_namesake_sibling_declaring_the_wrong_kb_refuses(tmp_path):
    base = _depender(tmp_path)
    _checkout(tmp_path, DEP, "some other hearth")
    checkout, problem = read_dependency({}, DEP, base_dir=base, props={})
    assert checkout is None
    assert problem is not None
    assert DEP in problem and "some other hearth" in problem


def test_an_empty_house_names_all_three_roads(tmp_path):
    base = _depender(tmp_path)
    checkout, problem = read_dependency({}, DEP, base_dir=base, props={})
    assert checkout is None
    assert problem is not None
    assert settings_key(DEP) in problem       # the settings roads
    assert ".env" in problem
    assert str(tmp_path / DEP) in problem     # the convention's exact try


def test_the_configured_road_is_byte_identical_without_base_dir(tmp_path):
    elsewhere = _checkout(tmp_path / "far", DEP, DEP)
    config = {settings_key(DEP): str(elsewhere)}
    checkout, problem = read_dependency(config, DEP)
    assert problem is None and checkout is not None
    missing, problem2 = read_dependency({}, DEP)
    assert missing is None
    assert "no path is configured" in str(problem2)


def test_drift_reads_ride_the_convention(tmp_path):
    base = _depender(tmp_path)
    _checkout(tmp_path, DEP, DEP, version=5)
    graph = GraphData()
    graph.ensure_node("[Knowledge Base Dependency]", DEP,
                      edition="stale", sequence=1, intent="read")
    [row] = drift_rows(graph, {}, base_dir=base)
    assert row["status"] == "behind"
    assert row["current"]["sequence"] == 5
