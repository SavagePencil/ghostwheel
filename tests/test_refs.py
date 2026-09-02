"""CitizenRef: identity is the (knowledge base, label, name) composite.

The structs are the one shape every machine surface serializes citizens
through; rows carry the knowledge base (and branch, off the default
line) whenever the serializer knows its line of truth. The KB's own
name is declared on the graph — the Ontology anchor — at ``init`` or
through a gated round (the ``kb-named`` ceremony class); a canon that
has not adopted one falls back to its directory basename.
"""

import json

from graph import refs
from graph.__main__ import main
from graph.attribution import Attribution
from graph.delta import Delta, build_report, ceremony_records
from graph.extract import GraphData
from graph.ontology import ARCHETYPE_LABEL
from graph.refs import CitizenRef, ConnectionRef, connection_ref
from graph.report import render_json
from graph.restore import read_export


def _no_base_anywhere(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)


# -- the struct rows: one shape, self-contained addressing -----------------

def test_a_citizen_row_carries_its_address_when_the_line_is_known():
    ref = CitizenRef("Artifact", "Chaos Sword")
    assert ref.row() == {"kind": "citizen", "label": "Artifact",
                         "name": "Chaos Sword"}
    assert ref.row(kb="vcs") == {
        "kind": "citizen", "label": "Artifact", "name": "Chaos Sword",
        "kb": "vcs"}
    assert ref.row(kb="vcs", branch="artifacts") == {
        "kind": "citizen", "label": "Artifact", "name": "Chaos Sword",
        "kb": "vcs", "branch": "artifacts"}


def test_a_connection_row_names_type_endpoints_and_address():
    class EdgeShaped:
        type = "WIELDS"
        from_label, from_name = "Person", "Errant Knight"
        to_label, to_name = "Artifact", "Chaos Sword"

    row = connection_ref(EdgeShaped()).row(kb="vcs", branch="artifacts")
    assert row == {"kind": "connection", "type": "WIELDS",
                   "from": {"label": "Person", "name": "Errant Knight"},
                   "to": {"label": "Artifact", "name": "Chaos Sword"},
                   "kb": "vcs", "branch": "artifacts"}
    assert isinstance(connection_ref(EdgeShaped()), ConnectionRef)


def test_the_token_is_stable_and_every_composite_part_moves_it():
    ref = CitizenRef("Artifact", "Chaos Sword")
    token = ref.token("vcs")
    assert token == ref.token("vcs")  # derived, deterministic
    assert token != ref.token("otherworld")
    assert token != ref.token("vcs", branch="artifacts")
    assert token != CitizenRef("Spell", "Chaos Sword").token("vcs")
    assert token != CitizenRef("Artifact", "Chaos Blade").token("vcs")


# -- the KB's name: declared on the anchor, basename fallback --------------

def test_kb_name_prefers_the_declared_name(tmp_path):
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR,
                      kb_name="vcs", version=3)
    assert refs.kb_name(graph, tmp_path / "some-directory") == "vcs"


def test_kb_name_falls_back_to_the_basename(tmp_path):
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR, version=3)
    base = tmp_path / "some-directory"
    assert refs.kb_name(graph, base) == "some-directory"
    assert refs.kb_name(GraphData(), base) == "some-directory"


def test_init_declares_the_name_and_the_export_reader_finds_it(
        tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    named = tmp_path / "somewhere"
    assert main(["init", str(named), "--name", "otherworld"]) == 0
    graph = read_export(named / "graph" / "export")
    anchor = graph.nodes[(ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR)]
    assert anchor[refs.KB_NAME_PROP] == "otherworld"
    assert refs.kb_name_from_export(named) == "otherworld"

    defaulted = tmp_path / "moondance"
    assert main(["init", str(defaulted)]) == 0
    assert refs.kb_name_from_export(defaulted) == "moondance"


def test_the_export_reader_falls_back_when_nothing_is_readable(tmp_path):
    assert refs.kb_name_from_export(tmp_path / "bare-ground") \
        == "bare-ground"


# -- adoption by round: the kb-named ceremony class ------------------------

def _anchor_base():
    base = GraphData()
    base.ensure_node(ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR, version=3)
    return base


def test_declaring_the_kb_name_is_a_ceremony_item_not_a_refusal():
    changes = Delta(nodes_changed=[
        (ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR,
         {refs.KB_NAME_PROP: (None, "vcs")})])
    _, violations, _nodes, _edges = ceremony_records(changes,
                                                     _anchor_base())
    assert violations == []
    items = ceremony_records(changes, _anchor_base())[0]
    assert [i.code for i in items] == ["kb-named"]
    assert "declares its name: 'vcs'" in items[0].message
    assert "unnamed until now" in items[0].message


def test_blanking_the_kb_name_refuses():
    changes = Delta(nodes_changed=[
        (ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR,
         {refs.KB_NAME_PROP: ("vcs", None)})])
    _, violations, _n, _e = ceremony_records(changes, _anchor_base())
    assert [v.code for v in violations] == ["schema-edit-out-of-class"]


def test_hand_editing_the_anchor_stamps_still_refuses():
    changes = Delta(nodes_changed=[
        (ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR,
         {"version": (3, 99), refs.KB_NAME_PROP: (None, "vcs")})])
    _, violations, _n, _e = ceremony_records(changes, _anchor_base())
    assert [v.code for v in violations] == ["schema-edit-out-of-class"]


def test_the_kb_name_class_covers_only_the_anchor():
    changes = Delta(nodes_changed=[
        (ARCHETYPE_LABEL, "Some Concept",
         {refs.KB_NAME_PROP: (None, "vcs")})])
    _, violations, _n, _e = ceremony_records(changes, _anchor_base())
    assert [v.code for v in violations] == ["schema-edit-out-of-class"]


# -- the serializers stamp every row ---------------------------------------

def test_delta_report_rows_carry_the_line_of_truth():
    changes = Delta(nodes_changed=[
        (ARCHETYPE_LABEL, refs.ONTOLOGY_ANCHOR,
         {refs.KB_NAME_PROP: (None, "vcs")})])
    items = ceremony_records(changes, _anchor_base())[0]
    doc = json.loads(render_json(build_report(changes, [], items),
                                 kb="vcs", branch="artifacts"))
    assert doc["kb"] == "vcs" and doc["branch"] == "artifacts"
    subject = doc["ceremony"][0]["subject"]
    assert subject["kb"] == "vcs" and subject["branch"] == "artifacts"
    assert doc["ceremony"][0]["ref"] == "name-declared"


def test_census_rows_are_citizen_rows_not_strings():
    verdict = Attribution(
        claim="the bog binds", verdict="attributed", rung="properties",
        citizens=[("Terrain", "Bog")], nearest=[("Knack", "Bound")])
    row = verdict.row(kb="vcs")
    assert row["citizens"] == [{"kind": "citizen", "label": "Terrain",
                                "name": "Bog", "kb": "vcs"}]
    assert row["nearest"] == [{"kind": "citizen", "label": "Knack",
                               "name": "Bound", "kb": "vcs"}]
