"""The taxonomy-membership rule: a citizen's INSTANCE_OF folds up its
label's SUBTYPE_OF chain — a row of a kind is an instance of every
concept that kind is a kind of. The schema ceremony keeps the taxonomy
a DAG and renders a proposed link's consequence: how many citizens
become instances of the concept at derivation.

Storybook domain: the kernel's own [File Location] under
[Artifact Location], and a storybook kind declared at the gate.
"""

import json

from graph.delta import ceremony_records, diff
from graph.extract import derive, make_edge
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_ARTIFACT_LOCATION_LABEL,
                            KERNEL_FILE_LOCATION_LABEL, ontology_from_graph)
from graph.report import REF_KEYS
from tests.test_branch import build_canon, clone

BASE, FILE = KERNEL_ARTIFACT_LOCATION_LABEL, KERNEL_FILE_LOCATION_LABEL


def test_a_row_of_a_kind_is_an_instance_of_what_the_kind_is_a_kind_of(
        tmp_path):
    canon = build_canon()
    assert any(e.type == "SUBTYPE_OF" and e.from_name == FILE
               and e.to_name == BASE for e in canon.edges)
    canon.ensure_node(FILE, "tale-file", scheme="file",
                      address="docs/tale.md", primary=True)
    derived, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert not [f for f in findings if f.severity == "error"], findings
    parents = {e.to_name for e in derived.edges
               if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == (FILE, "tale-file")}
    assert parents == {FILE, BASE}
    # a deeper kind folds all the way up
    canon.ensure_node(ARCHETYPE_LABEL, "[Sketch File]", doc="a kind of file",
                      spec_json=json.dumps({"concept": "Provenance"}))
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL,
                                 "[Sketch File]", ARCHETYPE_LABEL, "Ontology"))
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL,
                                 "[Sketch File]", ARCHETYPE_LABEL, FILE))
    canon.ensure_node("[Sketch File]", "sketch-1", scheme="file",
                      address="art/sketch.png", primary=True)
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    parents = {e.to_name for e in derived.edges
               if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("[Sketch File]",
                                                   "sketch-1")}
    assert parents == {"[Sketch File]", FILE, BASE}


def test_the_ceremony_keeps_the_taxonomy_a_dag_and_reports_the_matches():
    base = build_canon()
    scratch = clone(base)
    # a storybook kind under the kernel's file kind: the consequence names
    # how many rows become instances of [File Location]
    scratch.ensure_node(ARCHETYPE_LABEL, "[Sketch File]", doc="a kind of file",
                        spec_json=json.dumps({"concept": "Provenance"}))
    scratch.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL,
                                   "[Sketch File]", ARCHETYPE_LABEL,
                                   "Ontology"))
    scratch.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL,
                                   "[Sketch File]", ARCHETYPE_LABEL, FILE))
    scratch.ensure_node("[Sketch File]", "sketch-1", scheme="file",
                        address="art/sketch.png", primary=True)
    scratch.ensure_node("[Sketch File]", "sketch-2", scheme="file",
                        address="art/sketch-2.png", primary=True)
    items, violations, _, _ = ceremony_records(diff(base, scratch), base)
    assert violations == [], [str(v) for v in violations]
    [taxonomy] = [i for i in items if i.code == "taxonomy-declared"]
    assert "2 citizens of that kind become instances of ([File Location])" \
        in str(taxonomy)
    assert taxonomy.row()["data"] == {"matches": 2, "concept": FILE}
    # a link that would make a concept a kind of itself refuses by name
    cyclic = clone(base)
    cyclic.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, BASE,
                                  ARCHETYPE_LABEL, FILE))
    _, violations, _, _ = ceremony_records(diff(base, cyclic), base)
    [verdict] = violations
    assert verdict.code == "taxonomy-cycle"
    assert "a taxonomy has no cycles" in str(verdict)
    assert REF_KEYS["taxonomy-cycle"] == "kind-of-itself"
