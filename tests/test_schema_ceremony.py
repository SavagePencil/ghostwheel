"""The schema-delta ceremony: the owner-gated path through the freeze.

Three permitted classes ride an ordinary round and itemize under the
report's marked ceremony section — a new declared concept, a doc edit,
and the removal of an unreferenced schema row. Everything else on the
schema stratum still refuses by name (labels and specs move data
underneath them and belong to the migration charter). The owner's
approval of a round whose report carries the ceremony section IS the
ceremony ruling.
"""

import json
from pathlib import Path

from graph.delta import ceremony_classify, diff, lint, render_report
from graph.extract import GraphData, extract, make_edge, strip_derived
from graph.ontology import ERROR, load_ontology, ontology_from_graph
from graph.proposal import apply_delta

STORYBOOK = Path(__file__).resolve().parent / "fixtures" / "storybook"


def base_graph():
    g = GraphData()
    g.ensure_node("Archetype", "Ontology")
    g.ensure_node("Archetype", "Theme", doc="a philosophy statement")
    g.ensure_node("Archetype", "Terrain",
                  spec_json=json.dumps({"key": "Terrain"}))
    g.ensure_node("Archetype", "Forgotten Motif", doc="never referenced")
    g.ensure_node("Archetype", "Anchored Motif", doc="carries a judgment")
    g.ensure_node("Decision", "Motifs stay moody")
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Theme",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Forgotten Motif",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Anchored Motif",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("ABOUT", "Decision", "Motifs stay moody",
                             "Archetype", "Anchored Motif"))
    return g


def clone(graph):
    g = GraphData()
    for (label, name), props in graph.nodes.items():
        g.ensure_node(label, name, **dict(props))
    g.edges = list(graph.edges)
    return g


def test_declared_concept_addition_is_ceremony_not_refusal():
    base = base_graph()
    scratch = clone(base)
    scratch.ensure_node("Archetype", "Night Songs",
                        doc="the stories hum after dark")
    scratch.edges.append(make_edge("DECLARED_IN", "Archetype", "Night Songs",
                                   "Archetype", "Ontology"))
    scratch.edges.append(make_edge("INSTANCE_OF", "Archetype", "Night Songs",
                                   "Archetype", "Theme"))
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, violations, nodes, edges = ceremony_classify(d, base)
    assert violations == [] and ("Archetype", "Night Songs") in nodes
    assert len(edges) == 2
    [item] = items
    assert "NEW CONCEPT 'Night Songs'" in item
    assert "declared in Ontology" in item and "instance of Theme" in item
    report = render_report(d, [], items)
    assert "## Schema changes — the ceremony" in report
    assert "approving this round is the ceremony ruling" in report


def test_doc_edit_is_ceremony_and_other_props_refuse():
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Theme")]["doc"] = "a refined statement"
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, _, nodes, _ = ceremony_classify(d, base)
    assert ("Archetype", "Theme") in nodes
    assert any("DOC EDIT on 'Theme'" in i for i in items)
    # a doc edit smuggling another prop refuses whole
    scratch.nodes[("Archetype", "Theme")]["stub"] = True
    d = diff(base, scratch)
    assert any("beyond its doc text" in v and "stub" in v
               for v in lint(d, base))


def test_unreferenced_removal_lands_and_referenced_refuses():
    base = base_graph()
    scratch = clone(base)
    del scratch.nodes[("Archetype", "Forgotten Motif")]
    scratch.edges = [e for e in scratch.edges
                     if e.from_name != "Forgotten Motif"]
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, _, nodes, _ = ceremony_classify(d, base)
    assert ("Archetype", "Forgotten Motif") in nodes
    assert any("REMOVED CONCEPT 'Forgotten Motif'" in i for i in items)
    # the anchored row refuses, naming its references
    scratch = clone(base)
    del scratch.nodes[("Archetype", "Anchored Motif")]
    scratch.edges = [e for e in scratch.edges
                     if "Anchored Motif" not in (str(e.from_name),
                                                 str(e.to_name))]
    d = diff(base, scratch)
    assert any("still referenced in the base" in v and "ABOUT" in v
               for v in lint(d, base))


def test_label_rows_stay_frozen_both_directions():
    base = base_graph()
    scratch = clone(base)
    scratch.ensure_node("Archetype", "Ledger",
                        spec_json=json.dumps({"key": "Ledger"}))
    d = diff(base, scratch)
    assert any("new Archetype LABEL" in v and "migration charter" in v
               for v in lint(d, base))
    scratch = clone(base)
    del scratch.nodes[("Archetype", "Terrain")]
    d = diff(base, scratch)
    assert any("a LABEL row" in v and "migration charter" in v
               for v in lint(d, base))


def test_removal_without_base_refuses():
    base = base_graph()
    scratch = clone(base)
    del scratch.nodes[("Archetype", "Forgotten Motif")]
    scratch.edges = [e for e in scratch.edges
                     if e.from_name != "Forgotten Motif"]
    d = diff(base, scratch)
    assert any("without the base graph in view" in v for v in lint(d))


def test_ceremony_round_end_to_end_over_the_storybook():
    # a new Theme rides a real round: diff -> clean lint -> apply to the
    # ground layer -> the reconstructed ontology KNOWS the new concept
    ontology, findings = load_ontology(STORYBOOK / "ontology.yaml",
                                       STORYBOOK)
    assert not [f for f in findings if f.severity == ERROR]
    canon, _ = extract(ontology)
    scratch = clone(canon)
    scratch.ensure_node("Archetype", "Lantern Nights",
                        doc="the village gathers when the lanterns rise")
    scratch.edges.append(make_edge("DECLARED_IN", "Archetype",
                                   "Lantern Nights",
                                   "Archetype", "Ontology"))
    d = diff(canon, scratch)
    assert lint(d, canon) == []
    ground = strip_derived(canon)
    assert apply_delta(ground, d) == []
    assert ("Archetype", "Lantern Nights") in ground.nodes
    rebuilt = ontology_from_graph(ground, STORYBOOK)
    assert rebuilt is not None
    assert "Lantern Nights" in rebuilt.concepts
    assert rebuilt.concepts["Lantern Nights"]["doc"] \
        == "the village gathers when the lanterns rise"
