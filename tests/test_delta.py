"""Delta v0: diff, ground-facts lint, and report — pure logic over
GraphData pairs (the driver-facing reader is exercised by the live demo)."""

from graph.delta import Delta, diff, lint, render_report
from graph.extract import GraphData, make_edge


def base_graph():
    g = GraphData()
    g.ensure_node("Terrain", "Marsh", defense_mod=-2)
    g.ensure_node("Knack", "Pounce")
    g.ensure_node("Archetype", "Terrain", doc="existing machine node")
    g.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Marsh",
                             "Knack", "Pounce"))
    g.edges.append(make_edge("INSTANCE_OF", "Terrain", "Marsh",
                             "Archetype", "Terrain"))
    return g


def scratch_from(base):
    g = GraphData()
    for (label, name), props in base.nodes.items():
        g.ensure_node(label, name, **dict(props))
    g.edges = list(base.edges)
    return g


def test_identical_graphs_are_empty_delta():
    base = base_graph()
    d = diff(base, scratch_from(base))
    assert d.empty
    assert lint(d) == []
    assert "no proposal present" in render_report(d, [])


def test_added_node_and_edge_are_itemized():
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Terrain", "Fog", from_text="quote here")
    scratch.edges.append(make_edge("BORDERS", "Terrain", "Fog",
                                   "Terrain", "Marsh"))
    d = diff(base, scratch)
    assert d.nodes_added == [("Terrain", "Fog",
                              {"from_text": "quote here"})]
    assert [e.type for e in d.edges_added] == ["BORDERS"]
    assert lint(d) == []
    report = render_report(d, [])
    assert "**Fog**" in report and "BORDERS" in report
    assert "Clean — every addition is a ground fact." in report


def test_property_change_shows_before_and_after():
    base = base_graph()
    scratch = scratch_from(base)
    scratch.nodes[("Terrain", "Marsh")]["defense_mod"] = -4
    d = diff(base, scratch)
    assert d.nodes_changed == [("Terrain", "Marsh",
                                {"defense_mod": (-2, -4)})]
    assert "-2 → -4" in render_report(d, []).replace("'", "")


def test_removals_carry_their_before_image():
    base = base_graph()
    base.nodes[("Knack", "Pounce")]["note"] = "leaps far"
    scratch = scratch_from(base)
    del scratch.nodes[("Knack", "Pounce")]
    scratch.edges = [e for e in scratch.edges if e.type != "GRANTS_KNACK"]
    d = diff(base, scratch)
    # the removal records everything the node held — the undo record
    assert d.nodes_removed == [("Knack", "Pounce", {"note": "leaps far"})]
    assert [e.type for e in d.edges_removed] == ["GRANTS_KNACK"]
    assert "held" in render_report(d, []) and "leaps far" in \
        render_report(d, [])


def test_edge_property_edit_is_one_changed_entry():
    base = base_graph()
    base.edges.append(make_edge("SWAPS_WITH", "Knack", "Pounce",
                                "Knack", "Pounce", {"trigger": "dawn"}))
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "SWAPS_WITH"]
    scratch.edges.append(make_edge("SWAPS_WITH", "Knack", "Pounce",
                                   "Knack", "Pounce", {"trigger": "dusk"}))
    d = diff(base, scratch)
    # a property correction is ONE changed entry, not a remove+add pair
    assert d.edges_added == [] and d.edges_removed == []
    [(edge, changes)] = d.edges_changed
    assert edge.type == "SWAPS_WITH"
    assert changes == {"trigger": ("dawn", "dusk")}
    report = render_report(d, [])
    assert "Edges changed (before → after)" in report
    assert "dawn" in report and "dusk" in report


def test_ambiguous_parallel_edges_are_not_paired_into_changes():
    # two removed against one added between the same endpoints: which
    # removed edge "became" the added one is a guess — stay adds/removes
    base = base_graph()
    base.edges.append(make_edge("SWAPS_WITH", "Knack", "Pounce",
                                "Knack", "Pounce", {"trigger": "dawn"}))
    base.edges.append(make_edge("SWAPS_WITH", "Knack", "Pounce",
                                "Knack", "Pounce", {"trigger": "noon"}))
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "SWAPS_WITH"]
    scratch.edges.append(make_edge("SWAPS_WITH", "Knack", "Pounce",
                                   "Knack", "Pounce", {"trigger": "dusk"}))
    d = diff(base, scratch)
    assert d.edges_changed == []
    assert [dict(e.props)["trigger"] for e in d.edges_added] == ["dusk"]
    assert sorted(dict(e.props)["trigger"] for e in d.edges_removed) == \
        ["dawn", "noon"]


def test_lint_rejects_hand_modified_derived_edges():
    base = base_graph()
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "INSTANCE_OF"]
    scratch.edges.append(make_edge("INSTANCE_OF", "Terrain", "Marsh",
                                   "Archetype", "Terrain",
                                   {"confidence": "high"}))
    d = diff(base, scratch)
    [(edge, _)] = d.edges_changed
    assert edge.type == "INSTANCE_OF"
    problems = " | ".join(lint(d))
    assert "can't be modified by hand" in problems
    assert "derived type INSTANCE_OF" in problems


def test_lint_rejects_derived_edges_machine_and_schema():
    # three refusal classes in one changeset: a MACHINE label (built
    # automatically), a SCHEMA label (frozen until the schema-delta
    # ceremony), and DERIVED edges from citizens (computed automatically).
    # A citizen's INSTANCE_OF is its derived shadow — not schema — so it
    # keeps the machinery message.
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Step", "Turn the page")       # machine label
    scratch.ensure_node("Archetype", "Woven Concept")  # schema label (frozen)
    scratch.ensure_node("Terrain", None)               # unnamed
    scratch.edges.append(make_edge("INSTANCE_OF", "Terrain", "Marsh",
                                   "Archetype", "Woven Concept"))
    scratch.edges.append(make_edge("READS", "Knack", "Pounce",
                                   "Terrain", "Marsh"))
    d = diff(base, scratch)
    problems = " | ".join(lint(d))
    # human-readable refusals: what happened, why, what to do instead
    assert "built automatically by the system" in problems  # machine label
    assert "without declaring it" in problems  # schema add, no DECLARED_IN
    assert "derived type INSTANCE_OF" in problems
    assert "derived type READS" in problems
    assert "computed automatically from the facts" in problems
    assert "To undo" in problems
    assert "without a name" in problems


def test_machine_label_node_keeps_the_derived_machinery_message():
    # Step/Outcome are re-derived machinery — their refusal is unchanged
    # by the schema freeze (they are not schema, they are machine layers)
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Step", "Turn the page")
    d = diff(base, scratch)
    problems = " | ".join(lint(d))
    assert "built automatically by the system" in problems
    assert "frozen until the schema-delta ceremony" not in problems


def test_schema_label_node_is_the_freeze_not_the_machine_message():
    # an Archetype node is GROUND since the inversion, so its refusal is
    # the schema FREEZE, not the machine-built message
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Archetype", "Woven Concept")
    d = diff(base, scratch)
    problems = " | ".join(lint(d))
    assert "without declaring it" in problems
    assert "Attempted to author 'Woven Concept' as a new Archetype" \
        in problems
    assert "built automatically by the system" not in problems


def test_schema_edge_addition_is_frozen_not_machine_built():
    # a hand-authored schema edge (DECLARED_IN, or a concept-tower
    # INSTANCE_OF FROM an Archetype) is FROZEN, distinct from a citizen's
    # derived INSTANCE_OF shadow — no "computed automatically" wording
    base = base_graph()
    scratch = scratch_from(base)
    scratch.edges.append(make_edge("DECLARED_IN", "Archetype", "Terrain",
                                   "Archetype", "Ontology"))
    scratch.edges.append(make_edge("INSTANCE_OF", "Archetype", "Terrain",
                                   "Archetype", "Concept"))
    d = diff(base, scratch)
    problems = lint(d)
    text = " | ".join(problems)
    assert len(problems) == 2
    assert text.count("outside the ceremony's classes") == 2
    assert "DECLARED_IN" in text and "INSTANCE_OF" in text
    assert "computed automatically from the facts" not in text


def test_schema_edge_modification_is_frozen():
    # editing a schema edge's properties by hand is a frozen schema
    # change, reported in the "Attempted... Failed due to..." form
    base = base_graph()
    base.edges.append(make_edge("SUBTYPE_OF", "Archetype", "Terrain",
                                "Archetype", "Concept", {"note": "old"}))
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "SUBTYPE_OF"]
    scratch.edges.append(make_edge("SUBTYPE_OF", "Archetype", "Terrain",
                                   "Archetype", "Concept", {"note": "new"}))
    d = diff(base, scratch)
    [(edge, _)] = d.edges_changed
    assert edge.type == "SUBTYPE_OF"
    problems = " | ".join(lint(d))
    assert "Attempted to modify the connection" in problems
    assert "outside the ceremony's classes" in problems
    assert "computed automatically from the facts" not in problems


def test_lint_ignores_machine_layers_already_in_base():
    # the base's own INSTANCE_OF edges are the derivation's, not the
    # author's — only ADDITIONS are linted
    base = base_graph()
    d = diff(base, scratch_from(base))
    assert lint(d) == []


def test_node_deletion_leaves_derived_edges_to_rederivation():
    # deleting a node takes its machine edge with it in scratch; the
    # shadow must NOT itemize as an edge removal (the applier works on
    # the machine-stripped ground layer, where it could never verify) —
    # only the node and its ground edges itemize
    base = base_graph()
    scratch = scratch_from(base)
    del scratch.nodes[("Terrain", "Marsh")]
    scratch.edges = [e for e in scratch.edges
                     if e.from_name != "Marsh" and e.to_name != "Marsh"]
    d = diff(base, scratch)
    assert [name for _, name, _ in d.nodes_removed] == ["Marsh"]
    assert [e.type for e in d.edges_removed] == ["GRANTS_KNACK"]
    assert lint(d) == []


def test_hand_deleted_derived_edge_is_a_noop():
    # vandalizing scratch by deleting a machine edge itemizes nothing:
    # re-derivation restores the edge at apply regardless
    base = base_graph()
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "INSTANCE_OF"]
    d = diff(base, scratch)
    assert d.empty


def test_machine_layer_drift_is_left_to_rederivation():
    # a rederive can move canon's MACHINE layer (Step/Outcome — e.g. a
    # procedure body edit re-lifting its steps) after scratch was cut,
    # so scratch holds the stale machine nodes. Those never itemize:
    # the applier works on the machine-stripped ground layer where they
    # could never verify, and re-derivation owns them at apply. Since
    # the inversion the schema stratum is GROUND and out of rederive's
    # reach — schema mutations itemize and are refused by the freeze
    # (covered below), never treated as drift.
    base = base_graph()
    scratch = scratch_from(base)
    base.ensure_node("Step", "Turn the page", body="reworded by re-lift")
    d = diff(base, scratch)
    assert d.empty
    assert lint(d) == []


def test_stale_machine_layer_round_applies_cleanly():
    # the round's real work rides through untouched by machine drift:
    # the ground addition itemizes alone and applies to the ground layer
    from graph.extract import strip_derived
    from graph.proposal import apply_delta
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Terrain", "Fog")
    base.ensure_node("Step", "Turn the page", body="reworded by re-lift")
    d = diff(base, scratch)
    assert [name for _, name, _ in d.nodes_added] == ["Fog"]
    assert d.nodes_changed == [] and d.nodes_removed == []
    ground = strip_derived(base)
    assert apply_delta(ground, d) == []
    assert ("Terrain", "Fog") in ground.nodes


def test_hand_authored_schema_node_still_itemizes_and_refuses():
    # the drift filter must not open a door for authors: an Archetype
    # ADDED in scratch still itemizes, and the lint still refuses it —
    # now as a frozen schema change, not machine machinery
    base = base_graph()
    scratch = scratch_from(base)
    scratch.ensure_node("Archetype", "Woven Concept")
    d = diff(base, scratch)
    assert [name for _, name, _ in d.nodes_added] == ["Woven Concept"]
    assert any("without declaring it" in v for v in lint(d))


def test_node_deletion_changeset_applies_to_ground_layer():
    # the end-to-end shape that refused live: a deletion round must
    # verify and apply against the machine-stripped ground layer
    from graph.extract import strip_derived
    from graph.proposal import apply_delta
    base = base_graph()
    scratch = scratch_from(base)
    del scratch.nodes[("Terrain", "Marsh")]
    scratch.edges = [e for e in scratch.edges
                     if e.from_name != "Marsh" and e.to_name != "Marsh"]
    d = diff(base, scratch)
    ground = strip_derived(base)
    assert apply_delta(ground, d) == []
    assert ("Terrain", "Marsh") not in ground.nodes


def test_stitch_lint_holds_the_door_narrow():
    # the stitch is only for edges whose endpoint is born by this
    # round's schema edit: derived types refuse, unnamed ends refuse,
    # and an edge both of whose ends already exist in scratch is told
    # to ride the main changeset instead
    from graph.delta import lint_stitch
    base = base_graph()
    scratch = scratch_from(base)
    d = diff(base, scratch)
    d.stitch = [
        make_edge("DERIVED_FROM", "Knack", "Pounce", "Archetype", "Newborn"),
        make_edge("INSTANCE_OF", "Knack", "Pounce", "Archetype", "Newborn"),
        make_edge("GRANTS_KNACK", "Terrain", "Marsh", "Knack", "Pounce"),
        make_edge("GRANTS_KNACK", "Terrain", None, "Knack", "Pounce"),
    ]
    problems = lint_stitch(d, scratch)
    text = " | ".join(problems)
    assert len(problems) == 3  # the first edge genuinely needs the stitch
    assert "derived type INSTANCE_OF" in text
    assert "doesn't need the stitch" in text
    assert "unnamed" in text


def test_stitch_schema_edge_gets_the_freeze_message():
    # a schema edge in the stitch is frozen, not the generic
    # "derived — carries ground facts only" refusal
    from graph.delta import lint_stitch
    base = base_graph()
    scratch = scratch_from(base)
    d = diff(base, scratch)
    d.stitch = [make_edge("DECLARED_IN", "Archetype", "Newborn",
                          "Archetype", "Ontology")]
    problems = lint_stitch(d, scratch)
    text = " | ".join(problems)
    assert len(problems) == 1
    assert "the stitch never carries schema" in text
    assert "Remove it from the stitch file" in text
    assert "computed automatically" not in text


def test_stitch_itemizes_in_the_report():
    base = base_graph()
    d = diff(base, scratch_from(base))
    d.stitch = [make_edge("DERIVED_FROM", "Knack", "Pounce",
                          "Archetype", "Newborn")]
    assert not d.empty  # a stitch alone is a proposal
    report = render_report(d, [])
    assert "Stitch — lands after re-derivation" in report
    assert "1 stitched" in report
    assert "DERIVED_FROM" in report and "Newborn" in report


# -- the freeze covers every mutation class --------------------------------


def test_schema_node_prop_edit_beyond_doc_is_refused():
    # A schema prop edit BEYOND the doc classes surfaces as a refusal —
    # never vanishes from the changeset into a green apply.
    base = base_graph()
    scratch = scratch_from(base)
    scratch.nodes[("Archetype", "Terrain")]["temporal"] = True
    d = diff(base, scratch)
    assert [(l, n) for l, n, _ in d.nodes_changed] == \
        [("Archetype", "Terrain")]
    problems = lint(d)
    assert any("Attempted to modify 'Terrain' (Archetype) beyond its "
               "doc text" in p
               and "outside the ceremony's classes" in p
               for p in problems)


def test_schema_node_removal_is_itemized_and_refused():
    base = base_graph()
    scratch = scratch_from(base)
    del scratch.nodes[("Archetype", "Terrain")]
    # its edges go with it, as a real deletion would take them
    scratch.edges = [e for e in scratch.edges
                     if e.to_label != "Archetype"]
    d = diff(base, scratch)
    assert [(l, n) for l, n, _ in d.nodes_removed] == \
        [("Archetype", "Terrain")]
    problems = lint(d)   # no base in view: removals refuse outright
    assert any("Attempted to remove 'Terrain' (Archetype)" in p
               and "without the base graph in view" in p
               for p in problems)


def test_schema_edge_removal_is_itemized_and_refused():
    base = base_graph()
    base.ensure_node("Archetype", "Concept")
    base.edges.append(make_edge("DECLARED_IN", "Archetype", "Terrain",
                                "Archetype", "Ontology"))
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges
                     if e.type != "DECLARED_IN"]
    d = diff(base, scratch)
    assert [e.type for e in d.edges_removed] == ["DECLARED_IN"]
    problems = lint(d)
    assert any("Attempted to remove the connection" in p
               and "DECLARED_IN" in p
               and "outside the ceremony's classes" in p
               for p in problems)


def test_instance_shadow_edge_removal_still_never_itemizes():
    # the instance-level INSTANCE_OF is a machine shadow: rederive owns
    # it, so its removal stays out of the changeset (pre-inversion rule)
    base = base_graph()
    scratch = scratch_from(base)
    scratch.edges = [e for e in scratch.edges if e.type != "INSTANCE_OF"]
    d = diff(base, scratch)
    assert d.edges_removed == []
    assert lint(d) == []
