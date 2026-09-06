"""Every citizen whose label has a schema row is a direct instance of
that row; the taxonomy fold then climbs from it.

A kernel concept's own label, a concept-bound project label, and a
world's concept used as a label (a re-homed row under a declared kind)
are treated alike: a declared label means membership. A machine row
([Step], [Outcome]) and the schema stratum itself are not citizens and
get none.

Storybook domain: a chapter kind under [Artifact]; a wanderer kind
under the tale's Characters.
"""

import json

from graph.extract import derive, make_edge
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL,
                            KERNEL_DECISION_LABEL, STEP_LABEL,
                            ontology_from_graph)
from tests.test_branch import build_canon


def _parents(graph, key):
    return {e.to_name for e in graph.edges if e.type == "INSTANCE_OF"
            and (e.from_label, e.from_name) == key}


def test_a_concept_used_as_a_label_gives_its_citizens_direct_membership(
        tmp_path):
    canon = build_canon()
    # a world's concept (no label spec) declared a kind of [Artifact],
    # then a citizen re-homed under it — the first consumer's chapters
    canon.ensure_node(ARCHETYPE_LABEL, "[Chapter]", doc="a chapter")
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "[Chapter]",
                                 ARCHETYPE_LABEL, "Ontology"))
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "[Chapter]",
                                 ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL))
    canon.ensure_node("[Chapter]", "docs/one.md", known_at="Cited")
    derived, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert not [f for f in findings if f.severity == "error"], [
        f.detail for f in findings if f.severity == "error"]
    assert _parents(derived, ("[Chapter]", "docs/one.md")) == {
        "[Chapter]", KERNEL_ARTIFACT_LABEL}
    # a kernel label's citizen: direct membership as before
    canon.ensure_node(KERNEL_DECISION_LABEL, "a ruling", decided_by="owner")
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    assert _parents(derived, (KERNEL_DECISION_LABEL, "a ruling")) == {
        KERNEL_DECISION_LABEL}
    # a concept-bound project label: exactly one direct membership, no
    # duplicate from the general pass
    ember = [e for e in derived.edges if e.type == "INSTANCE_OF"
             and (e.from_label, e.from_name) == ("Character", "Pip")
             and e.to_name == "Character"]
    assert len(ember) == 1
    # a machine row is not a citizen of anything
    canon.ensure_node(STEP_LABEL, "ghost §1")
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    assert _parents(derived, (STEP_LABEL, "ghost §1")) == set()


def test_no_duplicate_instance_edges_anywhere(tmp_path):
    canon = build_canon()
    canon.ensure_node(ARCHETYPE_LABEL, "[Sketch File]", doc="a kind of file",
                      spec_json=json.dumps({"concept": "Provenance"}))
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL,
                                 "[Sketch File]", ARCHETYPE_LABEL, "Ontology"))
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL,
                                 "[Sketch File]", ARCHETYPE_LABEL,
                                 "[File Location]"))
    canon.ensure_node("[Sketch File]", "sketch", scheme="file",
                      address="art/s.png", primary=True)
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    instance = [e for e in derived.edges if e.type == "INSTANCE_OF"]
    assert len(instance) == len(set(instance))
    assert _parents(derived, ("[Sketch File]", "sketch")) == {
        "[Sketch File]", "[File Location]", "[Artifact Location]"}
