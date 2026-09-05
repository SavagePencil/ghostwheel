"""Bookmarks at the gate: the pin against its checkout, the citation
against what lives there, the behind-pin advisory, and the drift verb.

A [Knowledge Base Dependency]'s checkout is reached by a settings line
(GHOSTWHEEL_DEPENDENCY_<NAME>=<path>) and read as a committed backup:
identity hash, anchor sequence, declared name. At the delta gate a
dependency the round touches must be pinned at what its checkout
holds, and a bookmark the round touches — or any bookmark of a
dependency the round re-pins — must cite a citizen that exists there.
A dependency the gate cannot reach refuses for the rows that touch it
and is an advisory otherwise; every round hears a pin that has fallen
behind. `python -m graph dependencies` answers held / behind /
unreachable per dependency, records it, and exits 1 on any trouble.

Storybook domain: the tale pins a herbal on disk and cites Nightbell.
"""

import json

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.delta import diff
from graph.dependencies import (REPORT_FILE, RESOLVES_IN_EDGE, Checkout,
                                dependencies_report, drift_advisories,
                                drift_rows, read_dependency, render_report,
                                resolution_verdicts, settings_key)
from graph.extract import make_edge
from graph.load import read_config
from graph.ontology import KERNEL_BOOKMARK_LABEL, KERNEL_DEPENDENCY_LABEL
from graph.proposal import base_identity
from graph.report import ADVISORY, REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb  # noqa: F401
from tests.test_branch import export_dir

DEPENDENCY, BOOKMARK = KERNEL_DEPENDENCY_LABEL, KERNEL_BOOKMARK_LABEL


def _herbal(tmp_path, name="herbal"):
    """A second knowledge base on disk, born graph-native, holding one
    Herb citizen. Returns (its root, its backup's identity)."""
    root = tmp_path / name
    assert main_mod.cmd_init(root, name=name) == 0
    graph = read_export(root / "graph" / "export")
    graph.ensure_node("Herb", "Nightbell", virtue="calms the nerves")
    export_mod.write_export(graph, root / "graph" / "export")
    return root, base_identity(read_export(root / "graph" / "export"))


def _config(root, name="herbal"):
    return {settings_key(name): str(root)}


def _pin(graph, identity, name="herbal", sequence=0, intent="read"):
    graph.ensure_node(DEPENDENCY, name, edition=identity, sequence=sequence,
                      intent=intent)
    return graph


def _bookmark(graph, label="Herb", citizen="Nightbell", name="herbal",
              identity="a" * 64):
    bm = f"{name}:{label}:{citizen}"
    graph.ensure_node(BOOKMARK, bm, dependency=name, citizen_label=label,
                      citizen_name=citizen, edition=identity)
    graph.edges.append(make_edge(RESOLVES_IN_EDGE, BOOKMARK, bm,
                                 DEPENDENCY, name))
    return graph


def _codes(base, scratch, config):
    return sorted(v.code for v in resolution_verdicts(diff(base, scratch),
                                                      scratch, config))


# -- reaching a dependency -------------------------------------------------


def test_the_settings_key_takes_the_dependency_s_name_in_settings_shape():
    assert settings_key("herbal") == "GHOSTWHEEL_DEPENDENCY_HERBAL"
    assert settings_key("Tale of the Hearth") == \
        "GHOSTWHEEL_DEPENDENCY_TALE_OF_THE_HEARTH"
    assert settings_key("ember-hearth.v2") == "GHOSTWHEEL_DEPENDENCY_EMBER_HEARTH_V2"


def test_a_dependency_reads_from_its_configured_checkout(tmp_path,
                                                        monkeypatch):
    root, identity = _herbal(tmp_path)
    checkout, problem = read_dependency(_config(root), "herbal")
    assert problem is None and isinstance(checkout, Checkout)
    assert checkout.identity == identity and checkout.sequence == 0
    assert checkout.kb == "herbal" and checkout.path == root
    assert ("Herb", "Nightbell") in checkout.graph.nodes
    # no path configured, and a path with nothing readable there
    checkout, problem = read_dependency({}, "herbal")
    assert checkout is None
    assert "no path is configured" in str(problem)
    assert "GHOSTWHEEL_DEPENDENCY_HERBAL=<path" in str(problem)
    checkout, problem = read_dependency({settings_key("herbal"):
                                         str(tmp_path / "nowhere")}, "herbal")
    assert checkout is None and "nowhere" in str(problem)
    # the environment names a checkout like any other setting
    monkeypatch.setenv("GHOSTWHEEL_DEPENDENCY_HERBAL", str(root))
    assert read_config(tmp_path)["GHOSTWHEEL_DEPENDENCY_HERBAL"] == str(root)


# -- the gate reads the backup --------------------------------------------


def test_a_pin_must_match_its_checkout_and_its_name(tmp_path):
    root, identity = _herbal(tmp_path)
    config = _config(root)
    base = build_canon()
    assert _codes(base, _pin(clone(base), identity), config) == []
    [verdict] = resolution_verdicts(
        diff(base, _pin(clone(base), "0" * 64)),
        _pin(clone(base), "0" * 64), config)
    assert verdict.code == "dependency-edition-mismatch"
    assert "at edition 000000000000 (sequence 0)" in str(verdict)
    assert f"is at edition {identity[:12]} (sequence 0)" in str(verdict)
    assert verdict.data["checkout"]["path"] == str(root)
    assert REF_KEYS["dependency-edition-mismatch"] == "pin-checkout-differs"
    # a pin at the right edition but the wrong sequence differs too
    assert _codes(base, _pin(clone(base), identity, sequence=3), config) == \
        ["dependency-edition-mismatch"]
    # the entry is named for the knowledge base it pins
    almanac = _pin(clone(base), identity, name="almanac")
    assert _codes(base, almanac, _config(root, "almanac")) == \
        ["dependency-name-mismatch"]
    # a dependency the gate cannot reach refuses for the rows touching it
    [verdict] = resolution_verdicts(diff(base, _pin(clone(base), identity)),
                                    _pin(clone(base), identity), {})
    assert verdict.code == "dependency-unreachable"
    assert "must be able to read it" in str(verdict)
    assert verdict.data["settings_key"] == "GHOSTWHEEL_DEPENDENCY_HERBAL"
    # an untouched pin is not re-read by this gate at all
    pinned = _pin(clone(base), "0" * 64)
    other = clone(pinned)
    other.ensure_node("Character", "Ember", temperament="bright")
    assert _codes(pinned, other, {}) == []


def test_a_bookmark_must_cite_a_citizen_that_lives_there(tmp_path):
    root, identity = _herbal(tmp_path)
    config = _config(root)
    base = build_canon()
    pinned = _pin(clone(base), identity)
    assert _codes(pinned, _bookmark(clone(pinned)), config) == []
    [verdict] = resolution_verdicts(
        diff(pinned, _bookmark(clone(pinned), citizen="Moonwort")),
        _bookmark(clone(pinned), citizen="Moonwort"), config)
    assert verdict.code == "bookmark-target-missing"
    assert "(Herb) 'Moonwort' in dependency 'herbal'" in str(verdict)
    assert verdict.data["checkout"]["edition"] == identity
    assert REF_KEYS["bookmark-target-missing"] == "foreign-citation-missing"
    # the bookmark's own edition is provenance: an older one still passes
    # when the citizen lives at the dependency's current pin
    assert _codes(pinned, _bookmark(clone(pinned), identity="b" * 64),
                  config) == []
    # unreachable: the bookmark's dependency is named once, not the bookmark
    codes = _codes(pinned, _bookmark(clone(pinned)), {})
    assert codes == ["dependency-unreachable"]


def test_a_re_pin_re_resolves_every_bookmark_living_there(tmp_path):
    root, identity = _herbal(tmp_path)
    config = _config(root)
    base = _bookmark(_pin(build_canon(), identity))
    # the herbal moves on: Nightbell is struck from it
    moved = read_export(root / "graph" / "export")
    del moved.nodes[("Herb", "Nightbell")]
    export_mod.write_export(moved, root / "graph" / "export")
    new_identity = base_identity(read_export(root / "graph" / "export"))
    repinned = clone(base)
    repinned.nodes[(DEPENDENCY, "herbal")]["edition"] = new_identity
    [verdict] = resolution_verdicts(diff(base, repinned), repinned, config)
    assert verdict.code == "bookmark-target-missing"
    assert verdict.subject.name == "herbal:Herb:Nightbell"


# -- the behind pin, every round ------------------------------------------


def test_the_drift_rows_and_advisories_name_held_behind_and_unreachable(
        tmp_path):
    root, identity = _herbal(tmp_path)
    config = _config(root)
    graph = _pin(build_canon(), identity)
    [row] = drift_rows(graph, config)
    assert row["status"] == "held" and row["code"] == "dependency-held"
    assert row["ref"] == "held" and row["current"]["sequence"] == 0
    assert drift_advisories(graph, config) == []
    # the checkout moves past the pin
    moved = read_export(root / "graph" / "export")
    moved.ensure_node("Herb", "Moonwort")
    export_mod.write_export(moved, root / "graph" / "export")
    [row] = drift_rows(graph, config)
    assert row["status"] == "behind" and row["code"] == "dependency-pin-behind"
    [advisory] = drift_advisories(graph, config)
    assert advisory.severity == ADVISORY
    assert "the pin is behind" in str(advisory)
    assert f"pinned at sequence 0 (edition {identity[:12]})" in str(advisory)
    assert REF_KEYS["dependency-pin-behind"] == "pin-behind"
    # unreachable, and skipped when the round already refused it by name
    [row] = drift_rows(graph, {})
    assert row["status"] == "unreachable" and row["current"] is None
    [advisory] = drift_advisories(graph, {})
    assert advisory.code == "dependency-unreachable"
    assert "Rounds that do not touch it proceed" in str(advisory)
    assert drift_advisories(graph, {}, skip={"herbal"}) == []
    # the record and its rendering
    doc = dependencies_report(tmp_path, drift_rows(graph, config))
    assert doc["kind"] == "dependencies-report" and doc["passed"] is False
    text = render_report(doc)
    assert text.startswith("behind      herbal (read) — pinned at sequence 0")
    assert "a pin is behind" in text
    assert render_report(dependencies_report(tmp_path, [])) == \
        "No dependencies pinned."


def test_every_round_hears_a_behind_pin_and_the_verb_answers(driven_kb,
                                                              monkeypatch,
                                                              capsys):
    base, fake, _ = driven_kb
    root, identity = _herbal(base.parent)
    monkeypatch.setenv("GHOSTWHEEL_DEPENDENCY_HERBAL", str(root))
    canon = _pin(build_canon(), identity)
    export_mod.write_export(canon, export_dir(base))
    fake.databases["neo4j"] = clone(canon)
    capsys.readouterr()
    assert main_mod.cmd_dependencies(base) == 0
    assert "held        herbal (read)" in capsys.readouterr().out
    record = json.loads(record_path(base, REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert record["passed"] is True
    assert record["dependencies"][0]["code"] == "dependency-held"
    # the herbal moves on; an unrelated round hears it, and lands
    moved = read_export(root / "graph" / "export")
    moved.ensure_node("Herb", "Moonwort")
    export_mod.write_export(moved, root / "graph" / "export")
    authored = clone(canon)
    authored.ensure_node("Character", "Ember", temperament="bright")
    fake.databases["scratch"] = authored
    assert main_mod.cmd_delta(base, None) == 0
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [row["code"] for row in report["advisories"]] == \
        ["dependency-pin-behind"]
    assert "the pin is behind" in capsys.readouterr().out
    # the verb says so and exits nonzero for a later tool to alert on
    assert main_mod.cmd_dependencies(base) == 1
    out = capsys.readouterr().out
    assert "behind      herbal (read)" in out
    assert "a pin is behind" in out
    record = json.loads(record_path(base, REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert record["passed"] is False
    assert record["dependencies"][0]["ref"] == "pin-behind"
    # nothing configured: unreachable, exit 1, and the remedy names the key
    monkeypatch.delenv("GHOSTWHEEL_DEPENDENCY_HERBAL")
    assert main_mod.cmd_dependencies(base) == 1
    assert "GHOSTWHEEL_DEPENDENCY_HERBAL=<path" in capsys.readouterr().out
