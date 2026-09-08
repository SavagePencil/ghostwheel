"""The derive-era survivors of the from-sources extraction suite.

The from-sources machinery (the yaml loader, the CSV/markdown/overlay
readers, the bootstrap metamodel passes) left with the from-sources era,
and its tests with it. What stands here is what still runs on every
line: strip_derived's ground/derived boundary, the instance-level
metamodel re-derivation (memberships, value ladders from rank ground
props), and derivation as a stable fixpoint — all over the committed
storybook canon, the way every knowledge base is now born.
"""

import json

from graph import export as export_mod
from graph.extract import derive, make_edge, strip_derived
from graph.ontology import ARCHETYPE_LABEL, ERROR, ontology_from_graph
from tests.test_branch import build_canon


def derived_canon(tmp_path, graph=None):
    graph = graph if graph is not None else build_canon()
    derived, findings = derive(ontology_from_graph(graph, tmp_path), graph)
    assert not [f for f in findings if f.severity == ERROR], findings
    return derived


def with_glow(graph=None):
    """An ordered label authored graph-natively: the Glow ladder's rank
    props are ground; its value-ladder edges re-derive from them."""
    graph = graph if graph is not None else build_canon()
    graph.ensure_node(ARCHETYPE_LABEL, "Glow",
                      doc="how brightly an ember burns",
                      spec_json=json.dumps(
                          {"concept": "Story Concept", "ordered": True},
                          sort_keys=True))
    graph.edges.append(make_edge(
        "DECLARED_IN", ARCHETYPE_LABEL, "Glow", ARCHETYPE_LABEL, "Ontology"))
    graph.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, "Glow",
        ARCHETYPE_LABEL, "Story Concept"))
    graph.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, "Glow", ARCHETYPE_LABEL, "Ordered"))
    for rank, name in enumerate(("Faint", "Bright", "Blazing")):
        graph.ensure_node("Glow", name, rank=rank)
    return graph


def test_derive_is_a_stable_fixpoint(tmp_path):
    # the split's correctness bar, kept past the from-sources era: one
    # derivation codepath, so derive over its own output reproduces it
    # byte-for-byte — and the committed canon IS that output.
    canon = build_canon()
    once = derived_canon(tmp_path, canon)
    assert export_mod.serialize(once) == export_mod.serialize(build_canon())
    twice = derived_canon(tmp_path, once)
    assert export_mod.serialize(once) == export_mod.serialize(twice)


def test_strip_keeps_ground_edges_touching_the_schema_stratum(tmp_path):
    # a Judgment ABOUT a concept is ground, and so is its Archetype
    # endpoint — edge and endpoint both survive the strip.
    # Instance-level INSTANCE_OF still re-derives and is stripped; the
    # schema tower (Archetype -> Archetype) is ground and stays.
    graph = build_canon()
    graph.ensure_node("[Decision]", "name the bay", decided_by="owner")
    about = make_edge("ABOUT", "[Decision]", "name the bay",
                      ARCHETYPE_LABEL, "Story Concept")
    graph.edges.append(about)
    derived = derived_canon(tmp_path, graph)
    stripped = strip_derived(derived)
    assert about in stripped.edges
    assert ("[Decision]", "name the bay") in stripped.nodes
    assert (ARCHETYPE_LABEL, "Story Concept") in stripped.nodes
    instance_level = [e for e in stripped.edges
                      if e.type == "INSTANCE_OF"
                      and e.from_label != ARCHETYPE_LABEL]
    assert instance_level == []
    assert any(e.type == "INSTANCE_OF"
               and e.from_label == ARCHETYPE_LABEL
               for e in stripped.edges)


def test_rank_is_ground_and_survives_the_strip(tmp_path):
    derived = derived_canon(tmp_path, with_glow())
    stripped = strip_derived(derived)
    assert stripped.nodes[("Glow", "Faint")]["rank"] == 0


def test_ladder_edges_rederive_bidirectionally(tmp_path):
    derived = derived_canon(tmp_path, with_glow())
    precedes = {(e.from_name, e.to_name) for e in derived.edges
                if e.type == "PRECEDES" and e.from_label == "Glow"}
    follows = {(e.from_name, e.to_name) for e in derived.edges
               if e.type == "FOLLOWS" and e.from_label == "Glow"}
    assert precedes == {("Faint", "Bright"), ("Bright", "Blazing")}
    assert follows == {(higher, lower) for (lower, higher) in precedes}
    # and the ladder's citizens are instances of their label like any other
    assert any(e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("Glow", "Faint")
               and (e.to_label, e.to_name) == (ARCHETYPE_LABEL, "Glow")
               for e in derived.edges)


def test_value_to_label_to_concept_chain(tmp_path):
    derived = derived_canon(tmp_path)
    instance = {(e.from_label, e.from_name, e.to_label, e.to_name)
                for e in derived.edges if e.type == "INSTANCE_OF"}
    # the citizen's membership re-derives; the tower above it is ground
    assert ("Character", "Pip", ARCHETYPE_LABEL, "Character") in instance
    assert (ARCHETYPE_LABEL, "Character",
            ARCHETYPE_LABEL, "Story Concept") in instance


def test_no_duplicate_instance_edges(tmp_path):
    derived = derived_canon(tmp_path, with_glow())
    instance_edges = [e for e in derived.edges if e.type == "INSTANCE_OF"]
    assert len(instance_edges) == len(set(instance_edges))
