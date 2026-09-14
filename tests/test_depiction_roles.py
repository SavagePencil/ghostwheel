"""Depiction roles, and the reference interpretation that derives.

A depiction pairing carries a role: `primary` (the blessed reference
assignment) or `also-shows` (an inventory fact, one hop to query).
Each primary pairing derives its boilerplate interpretation — "X as Y
reference", intent "reference image for Y" — as a machine-layer pass,
idempotent over the whole graph: an assignment round's new primaries
gain theirs at that round's apply, a retrofit needs one rederive, a
zero-pairing round derives nothing. The derived rows carry the
machinery's marker, the strip removes them for the fixpoint, a hand
may never write the marker, and a hand-authored interpretation always
wins its pair. The gate calls the correlations out loud.

Storybook domain: a plate of sketches enters the tale.
"""

import json

from graph.artifacts import depiction_advisories, gate_verdicts
from graph.delta import Delta, lint_verdicts
from graph.extract import derive, make_edge, strip_derived
from graph.ontology import (KERNEL_ARTIFACT_LABEL,
                            KERNEL_INTERPRETATION_LABEL,
                            ontology_from_graph)
from tests.test_branch import build_canon

INTERP = KERNEL_INTERPRETATION_LABEL
MARKER = "derived_from"


def _with_plate(role=None):
    canon = build_canon()
    canon.ensure_node(KERNEL_ARTIFACT_LABEL, "the plate",
                      known_at="Cited", description="sketches of the vale")
    props = {"role": role} if role else None
    canon.edges.append(make_edge("DEPICTS", KERNEL_ARTIFACT_LABEL,
                                 "the plate", "Character", "Pip", props))
    return canon


def _derived(canon, tmp_path):
    return derive(ontology_from_graph(canon, tmp_path), canon)


# -- the role at the gate ---------------------------------------------------


def test_an_unknown_role_refuses_by_name(tmp_path):
    canon = _with_plate()
    delta = Delta()
    delta.edges_added.append(make_edge(
        "DEPICTS", KERNEL_ARTIFACT_LABEL, "the plate", "Character",
        "Maren", {"role": "sideways"}))
    [v] = [v for v in gate_verdicts(delta, canon, tmp_path)
           if v.code == "depiction-role-unknown"]
    assert "sideways" in v.message
    assert "primary" in v.message and "also-shows" in v.message
    for legal in ("primary", "also-shows", None):
        delta = Delta()
        props = {"role": legal} if legal else None
        delta.edges_added.append(make_edge(
            "DEPICTS", KERNEL_ARTIFACT_LABEL, "the plate", "Character",
            "Maren", props))
        assert not [v for v in gate_verdicts(delta, canon, tmp_path)
                    if v.code == "depiction-role-unknown"]


# -- the derivation: a pure function of the primary pairings ---------------


def test_a_primary_pairing_derives_its_reference_interpretation(tmp_path):
    canon = _with_plate(role="primary")
    derived, _ = _derived(canon, tmp_path)
    key = (INTERP, "the plate as Pip reference")
    assert key in derived.nodes
    row = derived.nodes[key]
    assert row["intent"] == "reference image for Pip"
    assert row[MARKER]
    edges = {(e.type, e.to_label, str(e.to_name)) for e in derived.edges
             if (e.from_label, str(e.from_name)) == key}
    assert ("ABOUT", KERNEL_ARTIFACT_LABEL, "the plate") in edges
    assert ("INTERPRETED_AS", "Character", "Pip") in edges
    assert ("DRAWS_ON", "Character", "Pip") in edges


def test_also_shows_and_unroled_derive_nothing(tmp_path):
    for role in ("also-shows", None):
        canon = _with_plate(role=role)
        derived, _ = _derived(canon, tmp_path)
        assert not [k for k in derived.nodes
                    if k[0] == INTERP and "reference" in str(k[1])]


def test_the_strip_removes_the_marker_rows_and_the_fixpoint_holds(
        tmp_path):
    canon = _with_plate(role="primary")
    once, _ = _derived(canon, tmp_path)
    stripped = strip_derived(once)
    assert not [k for k, p in stripped.nodes.items() if p.get(MARKER)]
    assert not [e for e in stripped.edges
                if "reference" in str(e.from_name)]
    twice, _ = _derived(stripped, tmp_path)
    assert set(twice.nodes) == set(once.nodes)


def test_a_hand_authored_interpretation_wins_its_pair(tmp_path):
    canon = _with_plate(role="primary")
    canon.ensure_node(INTERP, "the vale study",
                      intent="the owner's own reading")
    canon.edges.append(make_edge("ABOUT", INTERP, "the vale study",
                                 KERNEL_ARTIFACT_LABEL, "the plate"))
    canon.edges.append(make_edge("INTERPRETED_AS", INTERP, "the vale study",
                                 "Character", "Pip"))
    derived, _ = _derived(canon, tmp_path)
    assert (INTERP, "the vale study") in derived.nodes
    assert (INTERP, "the plate as Pip reference") not in derived.nodes


def test_the_marker_is_never_authorable():
    canon = build_canon()
    delta = Delta()
    delta.nodes_added.append((INTERP, "a forged reading",
                              {MARKER: "primary depiction",
                               "intent": "sneaky"}))
    [v] = [v for v in lint_verdicts(delta, canon)
           if v.code == "machinery-marker-authored"]
    assert "a forged reading" in v.message


# -- the gate calls the correlations out -----------------------------------


def test_the_gate_calls_out_each_new_primary_and_a_second_reference(
        tmp_path):
    canon = _with_plate(role="primary")
    canon.ensure_node(KERNEL_ARTIFACT_LABEL, "the second plate",
                      known_at="Cited")
    delta = Delta()
    delta.edges_added.append(make_edge(
        "DEPICTS", KERNEL_ARTIFACT_LABEL, "the second plate", "Character",
        "Pip", {"role": "primary"}))
    advisories = depiction_advisories(delta, canon)
    correlated = [a for a in advisories if a.code == "reference-correlated"]
    [line] = correlated
    assert "the second plate" in line.message and "Pip" in line.message
    assert "derives with this round" in line.message
    seconds = [a for a in advisories
               if a.code == "second-primary-reference"]
    [second] = seconds
    assert "Pip" in second.message
    # an also-shows pairing raises neither
    delta = Delta()
    delta.edges_added.append(make_edge(
        "DEPICTS", KERNEL_ARTIFACT_LABEL, "the second plate", "Character",
        "Maren", {"role": "also-shows"}))
    assert depiction_advisories(delta, canon) == []
