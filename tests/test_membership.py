"""The declared-membership pattern: an authored DECLARED_MEMBER_OF ground
edge (citizen -> a Concept-rooted Archetype, carrying a required `basis`)
that derivation folds into the citizen's INSTANCE_OF — so one citizen can
be an instance of several concepts at once while a sibling on the same
roster is not.

Storybook domain, the engine's own membership test: a Label `Object` binds
concept Treasure, so every Object is a Treasure by its roster. The Golden
Key is ALSO declared a Tool; the Plain Pebble is not.
"""

import json

import pytest

from graph import export as export_mod
from graph.delta import Delta, diff, lint
from graph.extract import GraphData, derive, make_edge, strip_derived
from graph.ontology import (ARCHETYPE_LABEL, ERROR, INFO, WARNING,
                            MEMBERSHIP_EDGE_TYPE, ontology_from_graph)
from graph.proposal import apply_delta, invert_delta, parse_delta, \
    serialize_delta
from tests.test_branch import build_canon


@pytest.fixture
def built(tmp_path):
    """The storybook canon grown by two concepts (Treasure, Tool) and a
    roster label Object bound to Treasure — the schema authored the way
    every post-flip schema arrives: Archetype rows, tower edges,
    DECLARED_IN. Derived once so the fixture is a stable fixpoint."""
    graph = build_canon()
    for concept in ("Treasure", "Tool"):
        graph.ensure_node(ARCHETYPE_LABEL, concept)
        graph.edges.append(make_edge(
            "DECLARED_IN", ARCHETYPE_LABEL, concept,
            ARCHETYPE_LABEL, "Ontology"))
        graph.edges.append(make_edge(
            "INSTANCE_OF", ARCHETYPE_LABEL, concept,
            ARCHETYPE_LABEL, "Concept"))
    graph.ensure_node(ARCHETYPE_LABEL, "Object",
                      spec_json=json.dumps({"concept": "Treasure"},
                                           sort_keys=True))
    graph.edges.append(make_edge(
        "DECLARED_IN", ARCHETYPE_LABEL, "Object",
        ARCHETYPE_LABEL, "Ontology"))
    graph.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, "Object",
        ARCHETYPE_LABEL, "Treasure"))
    graph.ensure_node("Object", "Golden Key")
    graph.ensure_node("Object", "Plain Pebble")
    ontology = ontology_from_graph(graph, tmp_path)
    base, findings = derive(ontology, graph)
    assert not [f for f in findings if f.severity == ERROR], findings
    return ontology, base


def _copy(graph):
    clone = GraphData()
    for key, props in graph.nodes.items():
        clone.nodes[key] = dict(props)
    clone.edges = list(graph.edges)
    return clone


def _membership(citizen, target, basis="opens the locked door"):
    return make_edge(MEMBERSHIP_EDGE_TYPE, "Object", citizen,
                     ARCHETYPE_LABEL, target, {"basis": basis})


def _instance_targets(graph, citizen):
    return {e.to_name for e in graph.edges
            if e.type == "INSTANCE_OF" and e.from_name == citizen
            and e.from_label == "Object"}


# -- the worked example ----------------------------------------------------

def test_declared_membership_folds_into_instance_of(built):
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(_membership("Golden Key", "Tool"))
    derived, findings = derive(ontology, graph)
    assert not [f for f in findings if f.severity == ERROR], findings
    # the Golden Key is now an instance of BOTH its roster label and Tool
    assert _instance_targets(derived, "Golden Key") == {"Object", "Tool"}
    # a sibling on the same roster is untouched — only its roster binding
    assert _instance_targets(derived, "Plain Pebble") == {"Object"}
    # the authored ground edge survives the strip (it is not derived)
    assert any(e.type == MEMBERSHIP_EDGE_TYPE and e.from_name == "Golden Key"
               and e.to_name == "Tool" for e in derived.edges)


def test_twice_derive_is_a_stable_fixpoint(built):
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(_membership("Golden Key", "Tool"))
    once, _ = derive(ontology, graph)
    twice, _ = derive(ontology, once)
    assert export_mod.serialize(once) == export_mod.serialize(twice)


def test_redundant_membership_is_skipped_with_info(built):
    # Treasure is already the Golden Key's roster-reachable concept (via
    # Object) — declaring it adds no INSTANCE_OF, only an INFO.
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(_membership("Golden Key", "Treasure"))
    derived, findings = derive(ontology, graph)
    infos = [f for f in findings
             if f.severity == INFO and "redundant" in f.detail]
    assert infos, findings
    # no direct citizen->Treasure INSTANCE_OF was emitted (the tower is the
    # single home for roster-implied membership)
    assert "Treasure" not in _instance_targets(derived, "Golden Key")


def test_non_concept_target_is_dropped_with_warning(built):
    # Ordered is a Facet, not a subject-matter Concept — the fold drops it.
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(_membership("Golden Key", "Ordered"))
    derived, findings = derive(ontology, graph)
    warnings = [f for f in findings
                if f.severity == WARNING
                and "not an existing Concept-rooted Archetype" in f.detail]
    assert warnings, findings
    assert "Ordered" not in _instance_targets(derived, "Golden Key")


def test_dangling_target_is_dropped_with_warning(built):
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(_membership("Golden Key", "Nonesuch"))
    derived, findings = derive(ontology, graph)
    assert [f for f in findings
            if f.severity == WARNING and "Nonesuch" in f.detail], findings
    assert "Nonesuch" not in _instance_targets(derived, "Golden Key")


# -- the lint refusals (each by message fragment) --------------------------

def _lint_one(base, edge):
    return " | ".join(lint(Delta(edges_added=[edge]), base))


def test_clean_membership_lints_clean(built):
    _, base = built
    assert _lint_one(base, _membership("Golden Key", "Tool")) == ""


def test_lint_refuses_membership_from_an_archetype(built):
    _, base = built
    edge = make_edge(MEMBERSHIP_EDGE_TYPE, ARCHETYPE_LABEL, "Object",
                     ARCHETYPE_LABEL, "Tool", {"basis": "x"})
    assert "runs FROM an Archetype" in _lint_one(base, edge)


def test_lint_refuses_a_facet_target(built):
    _, base = built
    problems = _lint_one(base, _membership("Golden Key", "Ordered"))
    assert "not an existing Concept-rooted Archetype" in problems


def test_lint_refuses_a_label_archetype_target(built):
    # a label's Archetype is a home with a catalog, not a subject to
    # classify against — authored membership never re-homes.
    _, base = built
    problems = _lint_one(base, _membership("Golden Key", "Object"))
    assert "not an existing Concept-rooted Archetype" in problems


def test_lint_refuses_a_missing_target(built):
    _, base = built
    problems = _lint_one(base, _membership("Golden Key", "Nonesuch"))
    assert "not an existing Concept-rooted Archetype" in problems


def test_lint_refuses_missing_basis(built):
    _, base = built
    edge = make_edge(MEMBERSHIP_EDGE_TYPE, "Object", "Golden Key",
                     ARCHETYPE_LABEL, "Tool")
    assert "no `basis`" in _lint_one(base, edge)


def test_lint_still_refuses_hand_authored_instance_of(built):
    # the fold computes INSTANCE_OF; hand-authoring it stays refused as it
    # is today — DECLARED_MEMBER_OF is the authorable route, INSTANCE_OF is
    # not.
    _, base = built
    edge = make_edge("INSTANCE_OF", "Object", "Golden Key",
                     ARCHETYPE_LABEL, "Tool")
    problems = _lint_one(base, edge)
    assert "derived type INSTANCE_OF" in problems
    assert "computed automatically from the facts" in problems


def test_lint_refuses_membership_without_a_base_graph():
    # Without the base graph the target cannot be verified — refused, not
    # silently permitted (the fold's WARNING is only a second belt and
    # never blocks an apply).
    edge = _membership("Golden Key", "Tool")
    problems = " | ".join(lint(Delta(edges_added=[edge]), None))
    assert "cannot be verified without the base graph" in problems


def test_lint_refuses_an_edit_that_strips_the_basis(built):
    # An edit must not defeat the audit invariant the add-side enforced:
    # blanking the basis is refused by name.
    _, base = built
    after = _membership("Golden Key", "Tool", basis="")
    problems = " | ".join(lint(
        Delta(edges_changed=[(after, {"basis": ("why", "")})]), base))
    assert "leaves it with no `basis`" in problems


def test_fold_ignores_an_archetype_sourced_edge(built):
    # Second belt behind the lint: an Archetype-sourced membership edge in
    # a drifted canon must never induce an Archetype->Archetype
    # INSTANCE_OF (that shape is schema ground and would corrupt the
    # fixpoint) — it is ignored with a WARNING.
    ontology, base = built
    graph = _copy(base)
    graph.edges.append(make_edge(
        MEMBERSHIP_EDGE_TYPE, ARCHETYPE_LABEL, "Object",
        ARCHETYPE_LABEL, "Tool", {"basis": "x"}))
    derived, findings = derive(ontology, graph)
    assert [f for f in findings
            if f.severity == WARNING and "tower/roster shape" in f.detail], \
        findings
    assert not any(
        e.type == "INSTANCE_OF" and e.from_label == ARCHETYPE_LABEL
        and e.from_name == "Object" and e.to_name == "Tool"
        for e in derived.edges)


# -- the delta path end to end ---------------------------------------------

def test_membership_rides_the_delta_path_and_inverts_cleanly(built):
    # The real round: author in scratch -> diff -> lint clean -> apply onto
    # the stripped ground -> re-derive folds the INSTANCE_OF; the inverse
    # removes the declaration and the derived membership disappears.
    ontology, base = built
    scratch = _copy(base)
    scratch.edges.append(_membership("Golden Key", "Tool"))

    changes = diff(base, scratch)
    assert [e.type for e in changes.edges_added] == [MEMBERSHIP_EDGE_TYPE]
    assert lint(changes, base) == []

    pinned = parse_delta(serialize_delta(changes))
    ground = strip_derived(base)
    assert apply_delta(ground, pinned) == []
    applied, findings = derive(ontology, ground)
    assert not [f for f in findings if f.severity == ERROR], findings
    assert _instance_targets(applied, "Golden Key") == {"Object", "Tool"}

    inverse = invert_delta(pinned)
    unwound = strip_derived(applied)
    assert apply_delta(unwound, inverse) == []
    reverted, _ = derive(ontology, unwound)
    assert _instance_targets(reverted, "Golden Key") == {"Object"}
    assert export_mod.serialize(reverted) == export_mod.serialize(base)
