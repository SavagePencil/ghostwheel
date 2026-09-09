"""Membership subjects: a Concept-rooted label row, and same-round birth.

A home with a catalog can be a subject too: authored membership never
re-homes (its only derived output is an added INSTANCE_OF), so a label
row whose tower reaches the Concept root is a legal target — a sword
kind can be declared Equipment while every sword keeps its home. A
Facet, a Judgment anchor, and every Provenance-rooted row stay refused
by the unchanged tower test. And a membership target may be born by
the round that declares into it — the taxonomy ceremony's own pattern.
"""

import json

from graph.delta import Delta, lint_verdicts
from graph.extract import derive, make_edge
from graph.ontology import (ARCHETYPE_LABEL, CONCEPT_ROOT,
                            ontology_from_graph)
from tests.test_branch import build_canon


def _label_row(canon, name, root):
    canon.ensure_node(ARCHETYPE_LABEL, name, doc="a kind with a catalog",
                      spec_json=json.dumps({"properties": {}}))
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, "Ontology"))
    canon.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, root))


def _membership(target):
    return make_edge("DECLARED_MEMBER_OF", "Character", "Pip",
                     ARCHETYPE_LABEL, target,
                     props={"basis": "the owner's ruling"})


def test_a_concept_rooted_label_row_is_a_legal_subject(tmp_path):
    canon = build_canon()
    _label_row(canon, "Blade", CONCEPT_ROOT)
    delta = Delta()
    delta.edges_added.append(_membership("Blade"))
    faults = [v for v in lint_verdicts(delta, canon)
              if v.code == "membership-target-not-concept"]
    assert faults == [], [v.message for v in faults]
    # the fold adds the membership and moves nothing
    canon.edges.append(_membership("Blade"))
    derived, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert any(e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("Character", "Pip")
               and e.to_name == "Blade" for e in derived.edges)
    assert ("Character", "Pip") in derived.nodes  # home unmoved
    assert not [f for f in findings
                if "dropped" in f.detail and "Blade" in f.detail]


def test_a_provenance_rooted_label_row_still_refuses(tmp_path):
    canon = build_canon()
    _label_row(canon, "Ledger", "Provenance")
    delta = Delta()
    delta.edges_added.append(_membership("Ledger"))
    [fault] = [v for v in lint_verdicts(delta, canon)
               if v.code == "membership-target-not-concept"]
    assert "never re-homes" in fault.message
    canon.edges.append(_membership("Ledger"))
    _, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert any("dropped" in f.detail and "Ledger" in f.detail
               for f in findings)


def test_a_target_born_by_the_same_round_is_admitted():
    canon = build_canon()
    delta = Delta()
    delta.nodes_added.append((ARCHETYPE_LABEL, "Gear",
                              {"doc": "a subject born this round"}))
    delta.edges_added.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL,
                                       "Gear", ARCHETYPE_LABEL, "Ontology"))
    delta.edges_added.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL,
                                       "Gear", ARCHETYPE_LABEL,
                                       CONCEPT_ROOT))
    delta.edges_added.append(_membership("Gear"))
    faults = [v for v in lint_verdicts(delta, canon)
              if v.code == "membership-target-not-concept"]
    assert faults == [], [v.message for v in faults]
    # a target that exists nowhere still refuses by name
    delta.edges_added.append(_membership("Nowhere"))
    [fault] = [v for v in lint_verdicts(delta, canon)
               if v.code == "membership-target-not-concept"]
    assert "Nowhere" in fault.message
