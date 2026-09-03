"""Answer keys on canon: the kernel citizen, the gate, and the sweep.

An Answer Key is a kernel Judgment citizen (kernel 0.14.0) carrying its
kind and table as props, the rest of its declaration as JSON, and one
CHECKS edge to the Procedure it holds still. The check reads program
bodies from canon and runs in two places: at the delta gate whenever a
round touches a key or a checked program's body (refusal on the live
line, advisory on a branch), and as the DB-free `answer-keys` sweep
writing a record beside its prose. The canon path and the file path
are one check: same findings, word for word.

Storybook domain: the wilting tale from the answer-key fixtures.
"""

import json

import tests.conftest as conftest
from graph import export as export_mod
from graph.__main__ import cmd_answer_keys
from graph.answer_keys import (ANSWER_KEYS_REPORT_FILE, CHECKS_EDGE, DRIFT,
                               HELD, INVALID, KEY_JSON_PROP,
                               PROCEDURE_MISSING, UNREADABLE,
                               answer_keys_report, canon_check, check,
                               gate_verdicts, keys_from_graph,
                               render_report)
from graph.delta import diff
from graph.extract import extract, make_edge
from graph.kernel_migrate import fresh_kernel
from graph.ontology import (ARCHETYPE_LABEL, ERROR, KERNEL_ANSWER_KEY_LABEL,
                            Category, load_ontology, ontology_from_graph)
from graph.report import ADVISORY, REFUSAL, REF_KEYS, record_path
from graph.restore import read_export
from tests.test_answer_keys import FILES, GOOD_KEYS, ONTOLOGY

_make_repo = getattr(conftest.make_repo, "__wrapped__", conftest.make_repo)

# the fixture's two declarations, as canon citizens
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


def _corpus(tmp_path, files=None, keys=GOOD_KEYS):
    base_dir, path = _make_repo(tmp_path)(files or FILES,
                                          ONTOLOGY.format(keys=keys))
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR]
    return base_dir, ontology, graph


def _with_keys(graph, keys=KEYS, procedure="Wilt"):
    for name, props in keys.items():
        graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, name, **props)
        graph.edges.append(make_edge(CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL,
                                     name, "Procedure", procedure))
    return graph


def _details(findings):
    return sorted(f.detail for f in findings)


# -- the kernel citizen ----------------------------------------------------


def test_the_kernel_declares_answer_key_under_judgment(tmp_path):
    seed, findings = fresh_kernel(tmp_path)
    assert seed is not None, findings
    assert (ARCHETYPE_LABEL, KERNEL_ANSWER_KEY_LABEL) in seed.nodes
    parents = {e.to_name for e in seed.edges
               if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == (ARCHETYPE_LABEL,
                                                   KERNEL_ANSWER_KEY_LABEL)}
    assert parents == {"Judgment"}
    assert any(e.type == "DECLARED_IN" and e.to_name == "Metaontology"
               and e.from_name == KERNEL_ANSWER_KEY_LABEL
               for e in seed.edges)


def test_keys_read_back_from_their_citizens(tmp_path):
    _, _, graph = _corpus(tmp_path)
    _with_keys(graph)
    read = {name: key for name, key, problem in keys_from_graph(graph)}
    assert read["Wilt walks its ladder"] == {
        "procedure": "Wilt", "derives": "transitions",
        "table": "data/wilt-transitions.csv",
        "from_column": "From Vigor", "to_column": "To Vigor"}
    assert read["Wilt holds its thresholds"]["condition_pattern"] == \
        "Rot > {value}"


# -- one check, two homes --------------------------------------------------


def test_canon_check_matches_the_file_check_word_for_word(tmp_path):
    base_dir, ontology, graph = _corpus(tmp_path)
    _with_keys(graph)
    rows = canon_check(graph, ontology_from_graph(graph, base_dir), base_dir)
    assert [r["status"] for r in rows] == ["held", "held"]
    assert {r["code"] for r in rows} == {HELD}
    assert _details(check(ontology)) == []
    # a table row the program lost, a threshold that moved: the canon
    # path names each exactly as the file path does
    (base_dir / "data" / "wilt-transitions.csv").write_text(
        "From Vigor,To Vigor\nFresh,Limp\nLimp,Dozed\nDozed,Fresh\n",
        encoding="utf-8")
    (base_dir / "data" / "wilt-thresholds.csv").write_text(
        "Vigor,Rot Needed\nFresh,12\nLimp,5\nDozed,N/A\n", encoding="utf-8")
    rows = canon_check(graph, ontology_from_graph(graph, base_dir), base_dir)
    canon_details = sorted(f.detail for r in rows for f in r["problems"])
    assert canon_details == _details(
        f for f in check(ontology) if f.category == Category.ANSWER_KEY)
    assert [r["status"] for r in rows] == ["drift", "drift"]
    assert {r["code"] for r in rows} == {DRIFT}
    assert {r["ref"] for r in rows} == {"program-table-drift"}


def test_uncheckable_citizens_are_named_not_skipped(tmp_path):
    base_dir, _, graph = _corpus(tmp_path)
    graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, "Garbled",
                      **{KEY_JSON_PROP: "{not json"})
    graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, "Checks nothing",
                      derives="transitions",
                      table="data/wilt-transitions.csv",
                      **{KEY_JSON_PROP: "{}"})
    graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, "Misspelled",
                      derives="transitions",
                      table="data/wilt-transitions.csv",
                      **{KEY_JSON_PROP: json.dumps(
                          {"from_colun": "From Vigor",
                           "to_column": "To Vigor"})})
    graph.edges.append(make_edge(CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL,
                                 "Misspelled", "Procedure", "Wilt"))
    graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, "Checks a ghost",
                      derives="transitions",
                      table="data/wilt-transitions.csv",
                      **{KEY_JSON_PROP: json.dumps(
                          {"from_column": "From Vigor",
                           "to_column": "To Vigor"})})
    graph.edges.append(make_edge(CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL,
                                 "Checks a ghost", "Procedure", "Bloom"))
    rows = {r["name"]: r for r in canon_check(
        graph, ontology_from_graph(graph, base_dir), base_dir)}
    assert rows["Garbled"]["code"] == UNREADABLE
    assert rows["Checks nothing"]["code"] == PROCEDURE_MISSING
    assert rows["Misspelled"]["code"] == INVALID
    assert "unknown answer-key field(s) ['from_colun']" in \
        rows["Misspelled"]["findings"][0]["message"]
    assert rows["Checks a ghost"]["code"] == PROCEDURE_MISSING
    assert all(r["status"] == "invalid" for r in rows.values())
    for code in (HELD, DRIFT, INVALID, UNREADABLE, PROCEDURE_MISSING):
        assert code in REF_KEYS


# -- the delta gate --------------------------------------------------------


def _clone(graph):
    from graph.extract import GraphData
    g = GraphData()
    for (label, name), props in graph.nodes.items():
        g.ensure_node(label, name, **dict(props))
    g.edges = list(graph.edges)
    return g


def test_a_body_edit_that_breaks_a_key_refuses_at_the_gate(tmp_path):
    base_dir, _, base = _corpus(tmp_path)
    _with_keys(base)
    ontology = ontology_from_graph(base, base_dir)
    scratch = _clone(base)
    node = scratch.nodes[("Procedure", "Wilt")]
    node["body"] = node["body"].replace("Rot > 10", "Rot > 11")
    delta = diff(base, scratch)
    verdicts = gate_verdicts(delta, scratch, ontology, base_dir)
    [verdict] = verdicts
    assert verdict.code == DRIFT and verdict.severity == REFUSAL
    assert "Wilt holds its thresholds" in verdict.message
    assert "case 'Fresh'" in verdict.message
    assert verdict.subject is not None
    assert verdict.row()["data"]["table"] == "data/wilt-thresholds.csv"
    # on a branch mid-rebuild the same finding advises
    [advisory] = gate_verdicts(delta, scratch, ontology, base_dir,
                               advisory=True)
    assert advisory.severity == ADVISORY


def test_a_round_touching_nothing_keyed_runs_no_keys(tmp_path):
    base_dir, _, base = _corpus(tmp_path)
    _with_keys(base)
    ontology = ontology_from_graph(base, base_dir)
    scratch = _clone(base)
    scratch.ensure_node("Vigor", "Crisp")
    assert gate_verdicts(diff(base, scratch), scratch, ontology,
                         base_dir) == []


def test_a_key_landing_without_its_program_refuses(tmp_path):
    base_dir, _, base = _corpus(tmp_path)
    ontology = ontology_from_graph(base, base_dir)
    scratch = _clone(base)
    scratch.ensure_node(KERNEL_ANSWER_KEY_LABEL, "Orphan",
                        derives="transitions",
                        table="data/wilt-transitions.csv",
                        **{KEY_JSON_PROP: "{}"})
    [verdict] = gate_verdicts(diff(base, scratch), scratch, ontology,
                              base_dir)
    assert verdict.code == PROCEDURE_MISSING
    assert "checks no program" in verdict.message
    # landing the key WITH its edge, against a faithful program: clean
    scratch.edges.append(make_edge(CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL,
                                   "Orphan", "Procedure", "Wilt"))
    scratch.nodes[(KERNEL_ANSWER_KEY_LABEL, "Orphan")][KEY_JSON_PROP] = \
        json.dumps({"from_column": "From Vigor", "to_column": "To Vigor"})
    assert gate_verdicts(diff(base, scratch), scratch, ontology,
                         base_dir) == []


# -- the sweep -------------------------------------------------------------


def test_the_sweep_writes_its_record_and_fails_on_drift(tmp_path, capsys):
    base_dir, _, graph = _corpus(tmp_path)
    _with_keys(graph)
    export_mod.write_export(graph, base_dir / "graph" / "export")
    assert cmd_answer_keys(base_dir) == 0
    out = capsys.readouterr().out
    assert "2 held · 0 drifted · 0 invalid" in out
    assert "PASS — every program agrees with its approved table." in out
    record = json.loads(record_path(base_dir, ANSWER_KEYS_REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert record["kind"] == "answer-keys-report" and record["passed"]
    assert [k["ref"] for k in record["keys"]] == ["held", "held"]
    assert "problems" not in record["keys"][0]
    # the table drifts underneath: the sweep fails by name, record beside
    (base_dir / "data" / "wilt-thresholds.csv").write_text(
        "Vigor,Rot Needed\nFresh,12\nLimp,5\nDozed,N/A\n", encoding="utf-8")
    assert cmd_answer_keys(base_dir) == 1
    out = capsys.readouterr().out
    assert "⚠ drift — 'Wilt holds its thresholds'" in out
    assert "FAIL" in out
    record = json.loads(record_path(base_dir, ANSWER_KEYS_REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert not record["passed"]
    assert record["counts"] == {"held": 1, "drift": 1, "invalid": 0}
    assert read_export(base_dir / "graph" / "export")  # canon untouched


def test_the_sweep_with_no_keys_says_so(tmp_path):
    doc = answer_keys_report(tmp_path, [])
    assert doc["passed"] and doc["counts"] == {"held": 0, "drift": 0,
                                               "invalid": 0}
    assert "No answer keys on canon" in render_report(doc)
