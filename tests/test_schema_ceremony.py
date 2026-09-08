"""The schema-delta ceremony: the owner-gated path through the freeze.

Five permitted classes ride an ordinary round and itemize under the
report's marked ceremony section — a new declared concept, a label
birth (a spec-carrying row with nothing yet underneath it), a doc edit,
an added alias (a new surface spelling reading as an existing citizen),
and the removal of an unreferenced schema row. Everything else on the
schema stratum still refuses by name (changes to existing labels and
specs move data underneath them and belong to the migration charter).
The owner's approval of a round whose report carries the ceremony
section IS the ceremony ruling.
"""

import json

from graph.delta import ceremony_classify, diff, lint, render_report
from graph.extract import GraphData, make_edge, strip_derived
from graph.ontology import ontology_from_graph
from graph.proposal import apply_delta
from tests.test_branch import STORYBOOK, build_canon


def base_graph():
    g = GraphData()
    g.ensure_node("Archetype", "Ontology")
    g.ensure_node("Archetype", "Theme", doc="a philosophy statement")
    g.ensure_node("Archetype", "Terrain",
                  spec_json=json.dumps({"key": "Terrain"}))
    g.ensure_node("Terrain", "Mesa")
    g.ensure_node("Archetype", "Forgotten Motif", doc="never referenced")
    g.ensure_node("Archetype", "Anchored Motif", doc="carries a judgment")
    g.ensure_node("[Decision]", "Motifs stay moody")
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Theme",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Forgotten Motif",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Anchored Motif",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("ABOUT", "[Decision]", "Motifs stay moody",
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
    # An undeclared spec row is not a birth — it refuses (a clean birth
    # arrives WITH its declaration; see the label-birth tests below).
    scratch = clone(base)
    scratch.ensure_node("Archetype", "Ledger",
                        spec_json=json.dumps({"key": "Ledger"}))
    d = diff(base, scratch)
    assert any("without declaring it" in v for v in lint(d, base))
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
    canon = build_canon()
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


# -- the added-alias class ---------------------------------------------------


def _terrain_spec(aliases=None, **extra):
    spec = {"key": "Terrain"}
    if aliases is not None:
        spec["aliases"] = aliases
    spec.update(extra)
    return json.dumps(spec, sort_keys=True)


def test_alias_addition_is_ceremony_not_refusal():
    from graph.delta import ceremony_records
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Mesa"})
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, violations, nodes, _ = ceremony_records(d, base)
    assert violations == [] and ("Archetype", "Terrain") in nodes
    [item] = items
    assert item.code == "alias-added"
    assert item.data == {"alias": "Butte", "target": "Mesa"}
    assert "ALIAS ADDED on 'Terrain'" in str(item)
    assert "'Butte' reads as the 'Mesa' citizen" in str(item)
    report = render_report(d, [], [str(item)])
    assert "## Schema changes — the ceremony" in report
    assert "added aliases" in report


def test_alias_addition_rides_with_a_doc_edit():
    from graph.delta import ceremony_records
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Mesa"})
    scratch.nodes[("Archetype", "Terrain")]["doc"] = "the lay of the land"
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, violations, nodes, _ = ceremony_records(d, base)
    assert violations == [] and ("Archetype", "Terrain") in nodes
    codes = sorted(i.code for i in items)
    assert codes == ["alias-added", "doc-edit"]
    # the spec_json change never renders as a doc edit
    doc_items = [i for i in items if i.code == "doc-edit"]
    assert all(i.data["property"] == "doc" for i in doc_items)


def test_list_alias_targets_verify_each_including_in_round():
    from graph.delta import ceremony_records
    base = base_graph()
    scratch = clone(base)
    scratch.ensure_node("Terrain", "Ridge")  # target born by this round
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Overlook": ["Mesa", "Ridge"]})
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, violations, nodes, _ = ceremony_records(d, base)
    assert violations == [] and ("Archetype", "Terrain") in nodes
    [item] = [i for i in items if i.code == "alias-added"]
    assert item.data == {"alias": "Overlook", "target": ["Mesa", "Ridge"]}
    assert "'Overlook' reads as the 'Mesa', 'Ridge' citizens" in str(item)


def test_alias_to_missing_citizen_refuses_by_name():
    from graph.delta import ceremony_records
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Nowhere"})
    d = diff(base, scratch)
    items, violations, nodes, _ = ceremony_records(d, base)
    assert items == [] and ("Archetype", "Terrain") not in nodes
    [violation] = violations
    assert violation.code == "alias-target-missing"
    assert violation.data == {"alias": "Butte", "missing": ["Nowhere"]}
    assert "no 'Nowhere' citizen exists under 'Terrain'" in str(violation)
    assert any("alias 'Butte'" in v for v in lint(d, base))


def test_alias_without_base_refuses():
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Mesa"})
    d = diff(base, scratch)
    # no base in view: the target cannot be verified, so it refuses
    assert any("alias 'Butte'" in v for v in lint(d))


def test_alias_removal_and_retarget_refuse():
    base = base_graph()
    base.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Mesa"})
    # removal
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = _terrain_spec()
    d = diff(base, scratch)
    assert any("beyond its doc text" in v and "spec_json" in v
               for v in lint(d, base))
    # retarget
    scratch = clone(base)
    scratch.ensure_node("Terrain", "Ridge")
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Ridge"})
    d = diff(base, scratch)
    assert any("beyond its doc text" in v and "spec_json" in v
               for v in lint(d, base))


def test_alias_bundled_with_other_spec_change_refuses():
    base = base_graph()
    scratch = clone(base)
    scratch.nodes[("Archetype", "Terrain")]["spec_json"] = \
        _terrain_spec({"Butte": "Mesa"}, key="Landform")
    d = diff(base, scratch)
    assert any("beyond its doc text" in v and "spec_json" in v
               and "migration charter" in v for v in lint(d, base))


def test_alias_codes_carry_designer_safe_refs():
    from graph.report import ref_key
    assert ref_key("alias-added") == "spelling-added"
    assert ref_key("alias-target-missing") == "spelling-target-missing"


# ---------------------------------------------------------------------------
# Label birth: the fifth permitted class. A born-graph-native project
# layer starts with zero labels, so growing one through an owner-gated
# round must be possible — the charter's data-movement rationale does
# not bite a label with nothing yet underneath.
# ---------------------------------------------------------------------------

def _birth(scratch, name, spec=None, declare=True, parent=None):
    scratch.ensure_node("Archetype", name,
                        doc=f"{name.lower()}s of the manual",
                        spec_json=json.dumps(
                            spec if spec is not None
                            else {"concept": name}))
    if declare:
        scratch.edges.append(make_edge("DECLARED_IN", "Archetype", name,
                                       "Archetype", "Ontology"))
    if parent:
        scratch.edges.append(make_edge("INSTANCE_OF", "Archetype", name,
                                       "Archetype", parent))


def test_label_birth_is_ceremony_not_refusal():
    base = base_graph()
    scratch = clone(base)
    _birth(scratch, "Night Rule", parent="Theme")
    d = diff(base, scratch)
    assert lint(d, base) == []
    items, violations, nodes, edges = ceremony_classify(d, base)
    assert violations == [] and ("Archetype", "Night Rule") in nodes
    assert len(edges) == 2
    [item] = items
    assert "NEW LABEL 'Night Rule'" in item and "born empty" in item
    assert "declared in Ontology" in item
    assert "binding concept Night Rule" in item
    assert "instance of Theme" in item
    report = render_report(d, [], items)
    assert "## Schema changes — the ceremony" in report


def test_label_birth_with_rows_already_underneath_refuses():
    base = base_graph()
    # Degenerate base: ground rows exist under a label with no schema row.
    base.ensure_node("Night Rule", "Hum Softly")
    scratch = clone(base)
    _birth(scratch, "Night Rule")
    _, violations, nodes, _ = ceremony_classify(diff(base, scratch), base)
    assert ("Archetype", "Night Rule") not in nodes
    assert any("already holds 1 ground row" in v
               and "Hum Softly" in v for v in violations)


def test_label_birth_without_base_refuses():
    base = base_graph()
    scratch = clone(base)
    _birth(scratch, "Night Rule")
    _, violations, nodes, _ = ceremony_classify(diff(base, scratch), None)
    assert ("Archetype", "Night Rule") not in nodes
    assert any("no base graph to verify against" in v for v in violations)


def test_label_birth_undeclared_refuses():
    base = base_graph()
    scratch = clone(base)
    _birth(scratch, "Night Rule", declare=False)
    _, violations, nodes, _ = ceremony_classify(diff(base, scratch), base)
    assert ("Archetype", "Night Rule") not in nodes
    assert any("without declaring it" in v for v in violations)


def test_label_birth_with_unreadable_spec_refuses():
    base = base_graph()
    scratch = clone(base)
    scratch.ensure_node("Archetype", "Night Rule", spec_json="not json{")
    scratch.edges.append(make_edge("DECLARED_IN", "Archetype", "Night Rule",
                                   "Archetype", "Ontology"))
    _, violations, nodes, _ = ceremony_classify(diff(base, scratch), base)
    assert ("Archetype", "Night Rule") not in nodes
    assert any("does not parse" in v for v in violations)


def test_label_birth_rides_a_round_end_to_end():
    """The full path a born-graph-native round takes: birth the label,
    author ground rows under it in the same delta, apply."""
    base = base_graph()
    scratch = clone(base)
    _birth(scratch, "Night Rule", parent="Theme")
    scratch.ensure_node("Night Rule", "Hum Softly", rank=0)
    scratch.ensure_node("Night Rule", "Dim The Lanterns", rank=1)
    d = diff(base, scratch)
    assert lint(d, base) == []
    assert apply_delta(base, d) == []  # applies in place, collates problems
    assert ("Archetype", "Night Rule") in base.nodes
    assert ("Night Rule", "Hum Softly") in base.nodes
    assert ("Night Rule", "Dim The Lanterns") in base.nodes
