"""Citations resolve among artifact kinds first and never fail in
silence; an artifact is [Artifact] or any kind of it, everywhere.

A program's artifact citation resolves among [Artifact] and its kinds
before the bare name is tried across every label, so a location row (or
any machinery row) sharing the artifact's name never competes. A
citation that still resolves to nothing, or to several, is an ERROR by
name (derived-edge-lost, with both remedies) — what canonize --apply,
rederive, and kernel-migrate refuse on, and the delta gate previews.
And a citizen re-homed under a kind of [Artifact] is an artifact to
every rule: it may author LOCATED_AT, its file locations are stamped at
apply, the sweep reads them.

Storybook domain: the tale's own chapter file; the wilting programs.
"""

import hashlib
import json

import tests.conftest as conftest
import graph.__main__ as main_mod
from graph.artifacts import (LOCATED_AT, VERIFIED_FINGERPRINT,
                             artifact_labels, gate_verdicts, location_rows,
                             verification_stamp)
from graph.delta import diff
from graph.extract import derive, extract, make_edge
from graph.ontology import (ARCHETYPE_LABEL, ERROR, KERNEL_ARTIFACT_LABEL,
                            KERNEL_FILE_LOCATION_LABEL, load_ontology,
                            ontology_from_graph)
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, export_dir  # noqa: F401
from tests.test_procedures import FILES, ONTOLOGY, artifact_cited
from tests.test_succession import _mount_live_canon

_make_repo = getattr(conftest.make_repo, "__wrapped__", conftest.make_repo)
ART, FILE = KERNEL_ARTIFACT_LABEL, KERNEL_FILE_LOCATION_LABEL
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(16))


def _corpus(tmp_path):
    files = dict(FILES)
    files["data/procedures/spanned.yaml"] = artifact_cited()
    ontology_text = ONTOLOGY.replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/spanned.yaml]").replace(
        "      DocSection:\n        source: [docs/rules.md]\n",
        "      DocSection:\n        source: [docs/rules.md]\n"
        "        concept: Tale Concept\n")  # every canon label has a row
    base_dir, path = _make_repo(tmp_path)(files, ontology_text)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR]
    return base_dir, graph


def _spanned_citation(graph):
    return {(e.to_label, e.to_name) for e in graph.edges
            if e.type == "SPECIFIED_IN" and e.from_name == "Spanned"}


def _errors(findings):
    return [f for f in findings if f.severity == ERROR]


# -- resolution among artifact kinds ----------------------------------------


def test_an_artifact_citation_ignores_a_location_row_sharing_the_name(
        tmp_path):
    base_dir, graph = _corpus(tmp_path)
    assert _spanned_citation(graph) == {(ART, "docs/rules.md")}
    # a file location named exactly like its artifact — the shape that
    # silenced the first consumer's citations
    located = clone(graph)
    located.ensure_node(FILE, "docs/rules.md", scheme="file",
                        address="docs/rules.md", primary=True)
    located.edges.append(make_edge(LOCATED_AT, ART, "docs/rules.md", FILE,
                                   "docs/rules.md"))
    derived, findings = derive(ontology_from_graph(located, base_dir),
                               located)
    assert _errors(findings) == [], [f.detail for f in _errors(findings)]
    assert _spanned_citation(derived) == {(ART, "docs/rules.md")}
    # a kind of artifact sharing the name is a real ambiguity — named,
    # with both remedies, never a dropped edge
    twin = clone(graph)
    twin.ensure_node(ARCHETYPE_LABEL, "[Scan]", doc="a kind of artifact",
                     spec_json=json.dumps({"concept": "Provenance"}))
    twin.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "[Scan]",
                                ARCHETYPE_LABEL, "Ontology"))
    twin.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "[Scan]",
                                ARCHETYPE_LABEL, ART))
    twin.ensure_node("[Scan]", "docs/rules.md", doc="a scan of the rules")
    _, findings = derive(ontology_from_graph(twin, base_dir), twin)
    [lost] = _errors(findings)
    assert lost.verdict_code == "derived-edge-lost"
    assert "'docs/rules.md' is ambiguous ([Artifact], [Scan])" in lost.detail
    assert "qualify it as 'Label: docs/rules.md', or rename" in lost.detail
    assert "The SPECIFIED_IN connection would be lost" in lost.detail
    assert REF_KEYS["derived-edge-lost"] == "citation-lost"
    # qualified, it resolves
    twin.nodes[(ARCHETYPE_LABEL, "[Procedure]")]  # the label exists
    assert artifact_labels(twin) == {ART, "[Scan]"}


def test_a_section_citation_that_collides_refuses_by_name(tmp_path):
    base_dir, graph = _corpus(tmp_path)
    assert ("DocSection", "rules § Overview") in {
        (e.to_label, e.to_name) for e in graph.edges
        if e.type == "SPECIFIED_IN" and e.from_name == "Tend"}
    collided = clone(graph)
    collided.ensure_node("Reserve", "rules § Overview", doc="a collider")
    _, findings = derive(ontology_from_graph(collided, base_dir), collided)
    lost = [f for f in _errors(findings)
            if f.verdict_code == "derived-edge-lost"]
    assert lost and "(DocSection, Reserve)" in lost[0].detail
    assert "'Tend' specified_in" in lost[0].location
    # a citation to nothing is the same refusal
    gone = clone(graph)
    del gone.nodes[("DocSection", "rules § Overview")]
    gone.edges = [e for e in gone.edges
                  if (e.to_label, e.to_name) != ("DocSection",
                                                 "rules § Overview")
                  and (e.from_label, e.from_name) != ("DocSection",
                                                     "rules § Overview")]
    _, findings = derive(ontology_from_graph(gone, base_dir), gone)
    assert [f.verdict_code for f in _errors(findings)
            if f.verdict_code == "derived-edge-lost"]


# -- an artifact is any kind of [Artifact] ---------------------------------


def _chapter_kind(graph):
    graph.ensure_node(ARCHETYPE_LABEL, "[Chapter]", doc="a kind of artifact",
                      spec_json=json.dumps({"concept": "Provenance"}))
    graph.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "[Chapter]",
                                 ARCHETYPE_LABEL, "Ontology"))
    graph.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "[Chapter]",
                                 ARCHETYPE_LABEL, ART))
    return graph


def test_a_citizen_under_a_kind_of_artifact_is_an_artifact_to_the_gate(
        tmp_path):
    base = _chapter_kind(build_canon())
    assert artifact_labels(base) == {ART, "[Chapter]"}
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "one.md").write_bytes(PNG)
    scratch = clone(base)
    scratch.ensure_node("[Chapter]", "one", known_at="Cited")
    scratch.ensure_node(FILE, "one (file)", scheme="file",
                        address="docs/one.md", primary=True)
    scratch.edges.append(make_edge(LOCATED_AT, "[Chapter]", "one", FILE,
                                   "one (file)"))
    assert gate_verdicts(diff(base, scratch), scratch, tmp_path) == []
    # a wrong fingerprint on the kind's row is judged like a plain artifact's
    scratch.nodes[("[Chapter]", "one")]["fingerprint"] = "0" * 64
    [verdict] = gate_verdicts(diff(base, scratch), scratch, tmp_path)
    assert verdict.code == "artifact-fingerprint-mismatch"
    assert verdict.subject.label == "[Chapter]"
    del scratch.nodes[("[Chapter]", "one")]["fingerprint"]
    # the stamp finds it through the kind
    assert verification_stamp(scratch, tmp_path, 3,
                              {("[Chapter]", "one")}) == []
    row = scratch.nodes[(FILE, "one (file)")]
    assert row[VERIFIED_FINGERPRINT] == hashlib.sha256(PNG).hexdigest()
    assert scratch.nodes[("[Chapter]", "one")]["medium"] == "image"
    [location] = location_rows(scratch, tmp_path)
    assert location["artifact"] == "one" and location["status"] == "verified"


def test_a_round_re_homing_into_a_kind_still_stamps_at_apply(driven_kb,
                                                              capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    (base / "docs").mkdir(exist_ok=True)
    (base / "docs" / "one.md").write_bytes(PNG)
    authored = _chapter_kind(clone(canon))
    authored.ensure_node("[Chapter]", "one", known_at="Cited")
    authored.ensure_node(FILE, "one (file)", scheme="file",
                         address="docs/one.md", primary=True)
    authored.edges.append(make_edge(LOCATED_AT, "[Chapter]", "one", FILE,
                                    "one (file)"))
    fake.databases["scratch"] = authored
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    landed = read_export(export_dir(base))
    assert landed.nodes[(FILE, "one (file)")][VERIFIED_FINGERPRINT] == \
        hashlib.sha256(PNG).hexdigest()
    assert landed.nodes[("[Chapter]", "one")]["medium"] == "image"
    parents = {e.to_name for e in landed.edges if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("[Chapter]", "one")}
    assert ART in parents
    assert main_mod.cmd_receipts(base) == 0
    doc = json.loads(record_path(base, "receipts-report.json")
                     .read_text(encoding="utf-8"))
    assert doc["locations"][0]["status"] == "verified"
