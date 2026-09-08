"""The origin-fields settlement: loud births and the source release.

A citizen born by reference under a declared `implicit:` label is
never silent — derivation notes each birth by label and name, and the
delta gate itemizes them as advisories beside the changeset. And the
release-files ceremony class widens to any label: a spec edit whose
only change is the source registration leaving is admitted and
itemized; anything else riding along refuses exactly as before.
"""

import json

from graph.delta import Delta, ceremony_records, lint_verdicts
from graph.extract import derive, make_edge
from graph.ontology import ARCHETYPE_LABEL, INFO, ontology_from_graph
from graph.report import REF_KEYS
from tests.test_branch import build_canon

BIRTH_CODE = "citizen-born-by-reference"


def _declare(canon, label, spec):
    canon.ensure_node(ARCHETYPE_LABEL, label, doc="a kind",
                      spec_json=json.dumps(spec))
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                 ARCHETYPE_LABEL, "Ontology"))


# -- loud births -----------------------------------------------------------


def test_a_birth_by_reference_is_noted_by_label_and_name(tmp_path):
    canon = build_canon()
    _declare(canon, "Rumor", {"implicit": True})
    _declare(canon, "Notice", {
        "reader": "markdown_sections",
        "relationships": [{"type": "PART_OF", "to": "Rumor",
                           "parser": "part_of",
                           "column": "spreads"}]})
    canon.ensure_node("Notice", "the fair opens",
                      body="# the fair opens\n",
                      spreads="the bell is cracked")
    derived, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert ("Rumor", "the bell is cracked") in derived.nodes
    [birth] = [f for f in findings if f.code == BIRTH_CODE]
    assert birth.severity == INFO
    assert "'the bell is cracked'" in birth.detail
    assert "Rumor" in birth.detail and "born by reference" in birth.detail
    assert BIRTH_CODE in REF_KEYS


def test_an_existing_citizen_is_no_birth(tmp_path):
    canon = build_canon()
    _declare(canon, "Rumor", {"implicit": True})
    _declare(canon, "Notice", {
        "reader": "markdown_sections",
        "relationships": [{"type": "PART_OF", "to": "Rumor",
                           "parser": "part_of",
                           "column": "spreads"}]})
    canon.ensure_node("Rumor", "the bell is cracked", heard="often")
    canon.ensure_node("Notice", "the fair opens",
                      body="# the fair opens\n",
                      spreads="the bell is cracked")
    _, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert not [f for f in findings if f.code == BIRTH_CODE]


# -- the source release, generalized ---------------------------------------


def _spec_edit(label, name, before, after):
    delta = Delta()
    delta.nodes_changed.append(
        (label, name, {"spec_json": (json.dumps(before),
                                     json.dumps(after))}))
    return delta


def test_a_plain_source_release_is_admitted_and_itemized():
    before = {"source": "data/herbs.csv",
              "properties": {"potency": {"type": "int"}}}
    after = {"properties": {"potency": {"type": "int"}}}
    delta = _spec_edit(ARCHETYPE_LABEL, "Herb", before, after)
    assert lint_verdicts(delta) == []
    items, violations, _, _ = ceremony_records(delta)
    assert violations == []
    [item] = [i for i in items if i.code == "source-released"]
    assert "SOURCE RELEASED" in item.message
    assert "Herb" in item.message
    assert "source-released" in REF_KEYS


def test_relationship_source_rows_release_in_the_same_class():
    before = {"properties": {"potency": {"type": "int"}},
              "relationships": [{"type": "BREWS_INTO", "to": "Tea",
                                 "source": "data/brews.csv"}]}
    after = {"properties": {"potency": {"type": "int"}},
             "relationships": [{"type": "BREWS_INTO", "to": "Tea"}]}
    delta = _spec_edit(ARCHETYPE_LABEL, "Herb", before, after)
    assert lint_verdicts(delta) == []
    items, violations, _, _ = ceremony_records(delta)
    assert violations == []
    [item] = [i for i in items if i.code == "source-released"]
    assert "Herb" in item.message


def test_anything_riding_the_release_refuses_as_before():
    before = {"source": "data/herbs.csv",
              "properties": {"potency": {"type": "int"}}}
    after = {"properties": {"potency": {"type": "int"},
                            "aroma": {"type": "str"}}}
    delta = _spec_edit(ARCHETYPE_LABEL, "Herb", before, after)
    violations = lint_verdicts(delta)
    assert violations, "a property change rode the release unrefused"
    assert any("spec" in v.message or "schema" in v.message
               for v in violations)


def test_a_release_may_not_silently_change_the_reader(tmp_path):
    # the reader was inferred from the source's extension: losing the
    # source would silently lose the derivation the reader drives
    before = {"source": "docs/tales.md"}
    after = {}
    delta = _spec_edit(ARCHETYPE_LABEL, "Tale", before, after)
    assert lint_verdicts(delta), "an inferred reader was silently lost"
    # declaring the same reader explicitly in the same edit keeps it
    kept = {"reader": "markdown_sections"}
    delta = _spec_edit(ARCHETYPE_LABEL, "Tale", before, kept)
    assert lint_verdicts(delta) == []
    items, violations, _, _ = ceremony_records(delta)
    assert violations == []
    [item] = [i for i in items if i.code == "source-released"]
    assert "Tale" in item.message


def test_the_gate_itemizes_births_as_advisories():
    # the preview's wiring, proven by source inspection (the DB-bound
    # CLI precedent): birth findings become advisories, never dropped
    import inspect

    import graph.__main__ as main_mod
    src = inspect.getsource(main_mod.cmd_delta)
    assert "citizen-born-by-reference" in src
    assert "derived_advisories" in src
