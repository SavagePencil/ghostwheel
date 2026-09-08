"""Graph-resident program bodies: the files released, the body the only
copy.

A program label needs only its reader to lift: a label that registers
no files lifts the bodies its citizens carry exactly as a file-registered
one does. The schema ceremony admits SOURCE UNREGISTRATION — a program
label dropping its file list and nothing else — when every citizen
under it, after the round's own edits, carries a body and cites no
file. The delta gate's roster reads the round's own schema, so the
adoption round is not accused by the registration it retires. The
body-sync gate stays a file-world verb. Afterward a body is a ground
prop: edit it, re-derivation re-lifts.

Storybook domain: the wilting tale, authored graph-natively over the
storybook canon (the answer-key fixture's program and tables).
"""

import json

from graph import export as export_mod
from graph.answer_keys import CHECKS_EDGE, KEY_JSON_PROP, canon_check
from graph.delta import body_sync_verdicts, ceremony_records, diff, lint
from graph.extract import (GraphData, derive, gate_roster_findings,
                           make_edge, procedure_roster_findings)
from graph.ontology import (ARCHETYPE_LABEL, ERROR, KERNEL_ANSWER_KEY_LABEL,
                            ontology_from_graph)
from graph.report import REF_KEYS
from tests.test_branch import build_canon

PROGRAM = """\
procedure: Wilt
possible_outcomes:
  Wilted:
    ends: done wilting
    guarantee: cannot-fail
steps:
  - branch on: the target's Vigor
    cases:
      Fresh:
        - when: Rot > 10
          then:
            - become: Limp
        - stop: done wilting
      Limp:
        - when: Rot > 5
          then:
            - become: Dozed
        - stop: done wilting
"""

FILES = {
    "data/wilt-transitions.csv": (
        "From Vigor,To Vigor\nFresh,Limp\nLimp,Dozed\n"),
    "data/wilt-thresholds.csv": (
        "Vigor,Rot Needed\nFresh,10\nLimp,5\nDozed,N/A\n"),
    "data/procedures/wilt.yaml": PROGRAM,
}

# the answer-key fixture's two declarations, as canon citizens
KEYS = {
    "Wilt walks its ladder": {
        "derives": "transitions", "table": "data/wilt-transitions.csv",
        KEY_JSON_PROP: json.dumps({"from_column": "From Vigor",
                                   "to_column": "To Vigor"})},
    "Wilt holds its thresholds": {
        "derives": "thresholds", "table": "data/wilt-thresholds.csv",
        KEY_JSON_PROP: json.dumps({"key_column": "Vigor",
                                   "value_column": "Rot Needed",
                                   "condition_pattern": "Rot > {value}"})},
}


def _with_keys(graph, keys=KEYS, procedure="Wilt"):
    for name, props in keys.items():
        graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, name, **props)
        graph.edges.append(make_edge(CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL,
                                     name, "[Procedure]", procedure))
    return graph


def _corpus(tmp_path):
    """The wilting tale as the file era left it on canon: a registered
    program file whose citizen carries the body and cites the file."""
    for relpath, content in FILES.items():
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    graph = build_canon()
    graph.ensure_node(ARCHETYPE_LABEL, "Vigor", spec_json=json.dumps(
        {"concept": ["Story Concept", "Exclusive", "Stateful"]},
        sort_keys=True))
    graph.edges.append(make_edge(
        "DECLARED_IN", ARCHETYPE_LABEL, "Vigor", ARCHETYPE_LABEL, "Ontology"))
    for parent in ("Story Concept", "Exclusive", "Stateful"):
        graph.edges.append(make_edge(
            "INSTANCE_OF", ARCHETYPE_LABEL, "Vigor", ARCHETYPE_LABEL, parent))
    for name in ("Fresh", "Limp", "Dozed"):
        graph.ensure_node("Vigor", name)
    row = graph.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
    row["spec_json"] = json.dumps(
        {"concept": "[Procedure]", "reader": "procedure_yaml",
         "source": ["data/procedures/wilt.yaml"]}, sort_keys=True)
    graph.ensure_node("[Procedure]", "Wilt", body=PROGRAM,
                      source_path="data/procedures/wilt.yaml",
                      completeness="transcribed")
    filed, findings = derive(ontology_from_graph(graph, tmp_path), graph)
    assert not [f for f in findings if f.severity == ERROR], findings
    return tmp_path, filed


def _clone(graph):
    g = GraphData()
    for (label, name), props in graph.nodes.items():
        g.ensure_node(label, name, **dict(props))
    g.edges = list(graph.edges)
    return g


def _released_spec(spec_json):
    spec = json.loads(spec_json)
    spec.pop("source")
    return json.dumps(spec, sort_keys=True)


def _adopt(graph):
    """The adoption round's edits: every program citizen drops its file
    citation; the label's spec drops its registration."""
    for (label, _name), props in graph.nodes.items():
        if label == "[Procedure]":
            props.pop("source_path", None)
    row = graph.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
    row["spec_json"] = _released_spec(row["spec_json"])
    return graph


# -- the lift without a registered file -----------------------------------


def test_a_program_body_lifts_without_a_registered_file(tmp_path):
    base_dir, filed = _corpus(tmp_path)
    resident = _adopt(_clone(filed))
    (base_dir / "data" / "procedures" / "wilt.yaml").unlink()
    rederived, findings = derive(ontology_from_graph(resident, base_dir),
                                 resident)
    assert not [f for f in findings if f.severity == ERROR], findings
    # the machine layers are the file era's, byte for byte, but for the
    # released registration and citation
    expected = _adopt(_clone(filed))
    assert export_mod.serialize(rederived) == export_mod.serialize(expected)
    assert [n for (label, n) in rederived.nodes if label == "[Step]"]
    assert any(e.type == "KNOWN_AT" and e.from_name == "Wilt"
               for e in rederived.edges)
    assert {(e.to_name) for e in rederived.edges
            if e.type == "MUTATES" and e.from_name == "Wilt"} == \
        {"Limp", "Dozed"}


def test_answer_keys_still_hold_over_resident_bodies(tmp_path):
    base_dir, filed = _corpus(tmp_path)
    resident = _with_keys(_adopt(_clone(filed)))
    (base_dir / "data" / "procedures" / "wilt.yaml").unlink()
    rows = canon_check(resident, ontology_from_graph(resident, base_dir),
                       base_dir)
    assert [r["status"] for r in rows] == ["held", "held"]


def test_a_resident_body_edit_re_lifts_on_derivation(tmp_path):
    base_dir, filed = _corpus(tmp_path)
    resident = _adopt(_clone(filed))
    node = resident.nodes[("[Procedure]", "Wilt")]
    node["body"] = node["body"].replace("become: Dozed", "become: Fresh")
    rederived, findings = derive(ontology_from_graph(resident, base_dir),
                                 resident)
    assert not [f for f in findings if f.severity == ERROR], findings
    mutated = {e.to_name for e in rederived.edges
               if e.type == "MUTATES" and e.from_name == "Wilt"}
    assert "Fresh" in mutated and "Dozed" not in mutated
    # a malformed body refuses collated at derivation, never silently
    node["body"] = "procedure: Wilt\nsteps:\n  - dance: wildly\n"
    _, findings = derive(ontology_from_graph(resident, base_dir), resident)
    assert [f for f in findings if f.severity == ERROR]


def test_the_body_sync_gate_stays_a_file_world_verb(tmp_path):
    base_dir, filed = _corpus(tmp_path)
    (base_dir / "data" / "procedures" / "wilt.yaml").unlink()
    assert body_sync_verdicts(filed, base_dir)  # a cited file, gone
    assert body_sync_verdicts(_adopt(_clone(filed)), base_dir) == []


# -- the ceremony class ----------------------------------------------------


def test_source_unregistration_is_ceremony_when_every_body_is_carried(
        tmp_path):
    base_dir, base = _corpus(tmp_path)
    scratch = _adopt(_clone(base))
    d = diff(base, scratch)
    items, violations, nodes, _ = ceremony_records(d, base)
    assert violations == [] and lint(d, base) == []
    assert (ARCHETYPE_LABEL, "[Procedure]") in nodes
    [item] = items
    assert item.code == "source-unregistered"
    assert "PROGRAM FILES RELEASED from '[Procedure]'" in str(item)
    assert "1 registered file leave" in str(item)
    assert item.row()["data"]["files"] == ["data/procedures/wilt.yaml"]
    assert REF_KEYS["source-unregistered"] == "program-files-released"


def test_source_unregistration_refuses_while_a_citizen_still_cites_a_file(
        tmp_path):
    base_dir, base = _corpus(tmp_path)
    scratch = _clone(base)
    row = scratch.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
    row["spec_json"] = _released_spec(row["spec_json"])  # bodies untouched
    items, violations, nodes, _ = ceremony_records(diff(base, scratch), base)
    assert items == [] and (ARCHETYPE_LABEL, "[Procedure]") not in nodes
    [verdict] = violations
    assert verdict.code == "source-unregistration-refused"
    assert "'Wilt' still cites data/procedures/wilt.yaml" in str(verdict)
    assert verdict.row()["data"]["citizens"] == [
        "'Wilt' still cites data/procedures/wilt.yaml"]


def test_source_unregistration_refuses_a_bodiless_citizen_and_no_base(
        tmp_path):
    base_dir, base = _corpus(tmp_path)
    scratch = _adopt(_clone(base))
    scratch.ensure_node("[Procedure]", "Bloom", completeness="transcribed")
    _, violations, _, _ = ceremony_records(diff(base, scratch), base)
    [verdict] = violations
    assert "'Bloom' carries no program body" in str(verdict)
    _, violations, _, _ = ceremony_records(diff(base, _adopt(_clone(base))),
                                           None)
    [verdict] = violations
    assert verdict.code == "source-unregistration-refused"
    assert "no base graph" in str(verdict)


def test_any_other_spec_change_alongside_stays_out_of_class(tmp_path):
    base_dir, base = _corpus(tmp_path)
    scratch = _adopt(_clone(base))
    row = scratch.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
    spec = json.loads(row["spec_json"])
    spec["doc"] = "smuggled"
    row["spec_json"] = json.dumps(spec, sort_keys=True)
    _, violations, _, _ = ceremony_records(diff(base, scratch), base)
    assert [v.code for v in violations] == ["schema-edit-out-of-class"]
    # dropping the reader with the source leaves the label unliftable:
    # not an unregistration, out of class
    scratch = _adopt(_clone(base))
    spec = json.loads(scratch.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
                      ["spec_json"])
    spec.pop("reader")
    scratch.nodes[(ARCHETYPE_LABEL, "[Procedure]")]["spec_json"] = \
        json.dumps(spec, sort_keys=True)
    _, violations, _, _ = ceremony_records(diff(base, scratch), base)
    assert [v.code for v in violations] == ["schema-edit-out-of-class"]


# -- the roster at the gate ------------------------------------------------


def test_the_gate_roster_reads_the_round_s_own_schema(tmp_path):
    base_dir, base = _corpus(tmp_path)
    scratch = _adopt(_clone(base))
    # judged by the schema it retires, the adoption round would be
    # accused of shipping a file without its citizen
    accused = procedure_roster_findings(
        ontology_from_graph(base, base_dir), scratch)
    assert [f.code for f in accused] == ["roster-gap"]
    # judged by its own schema, nothing is registered and nothing is owed
    assert gate_roster_findings(scratch, base_dir) == []
    # and a file-registered line still owes its citizens
    orphaned = _clone(base)
    del orphaned.nodes[("[Procedure]", "Wilt")]
    assert [f.code for f in gate_roster_findings(orphaned, base_dir)] == \
        ["roster-gap"]
