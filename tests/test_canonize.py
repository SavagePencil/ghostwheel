"""Canonization: the fixpoint (render → re-extract → ground facts are
canonical; the only surplus is machinery), the REVIEW-REQUIRED refusals,
and the apply preconditions. Runs on the test_extract mini-repo fixture —
no database needed."""

import pytest

from graph.canonize import RECEIPT_PROPS, apply_plan, build_plan
from graph.delta import diff, lint
from graph.extract import GraphData, extract, make_edge
from graph.ontology import (SCHEMA_EDGE_TYPES, is_derived_edge,
                            load_ontology)
from tests.test_extract import FILES, ONTOLOGY


def clone(graph):
    copy = GraphData()
    for (label, name), props in graph.nodes.items():
        copy.ensure_node(label, name, **dict(props))
    copy.edges = list(graph.edges)
    return copy


def build_base(make_repo):
    base_dir, path = make_repo(FILES, ONTOLOGY)
    ontology, _ = load_ontology(path, base_dir)
    base, _ = extract(ontology)
    return base_dir, path, ontology, base


def agent_scratch(base):
    """What an agent session leaves in scratch: base + ground facts only."""
    scratch = clone(base)
    scratch.ensure_node("Knack", "Glimmer", knack_class="Active",
                        note="a hidden note", from_text="quoted evidence")
    scratch.edges.append(make_edge("HAS_KNACK_SPARK", "Knack", "Glimmer",
                                   "Spark", "Faint"))
    # cell append onto a row that already has content
    scratch.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Windswept",
                                   "Knack", "Glimmer"))
    # edge-table row with a prop column
    scratch.edges.append(make_edge("SWAPS_WITH", "Knack", "Glimmer",
                                   "Knack", "Frost", {"trigger": "feint"}))
    # to: any relationship -> rendered as a qualified cell
    scratch.ensure_node("Note", "third one")
    scratch.edges.append(make_edge("ABOUT", "Note", "third one",
                                   "Knack", "Frost"))
    # property changes on an existing node: column-mapped + overlay-bound
    scratch.nodes[("Knack", "Frost")]["knack_class"] = "Active"
    scratch.nodes[("Knack", "Frost")]["note"] = "updated note"
    return scratch


def test_fixpoint_ground_facts_become_canonical(make_repo):
    base_dir, path, ontology, base = build_base(make_repo)
    scratch = agent_scratch(base)
    delta = diff(base, scratch)
    assert lint(delta) == []

    plan = build_plan(delta, ontology, base_dir)
    assert not plan.blocked, plan.review_required
    apply_plan(plan, base_dir)

    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)
    residual = diff(new_base, scratch)
    # nothing the agent wrote is missing from the rebuilt canon
    assert residual.nodes_added == []
    assert residual.edges_added == []
    assert residual.nodes_removed == []
    # the rebuild's surplus over scratch is exclusively machinery — checked
    # directly on the edge sets, since machine shadows never itemize
    surplus = set(new_base.edges) - set(scratch.edges)
    assert surplus, "derivation should have run"
    assert all(is_derived_edge(e) or e.type in SCHEMA_EDGE_TYPES
               or e.from_label == "Archetype" for e in surplus)
    assert residual.edges_removed == []
    # and the only property surplus in scratch is receipt metadata
    for _, _, changes in residual.nodes_changed:
        assert set(changes) <= RECEIPT_PROPS, changes


def test_receipts_are_reported_not_rendered(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = agent_scratch(base)
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    assert any("receipt metadata 'from_text'" in n for n in plan.notices)
    appended = plan.csv_appends["data/knacks.csv"][0]
    assert "from_text" not in " ".join(appended)


def test_unknown_label_is_review_required(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.ensure_node("Gremlin", "Cave Mouth", grade="agent-proposed")
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    assert plan.blocked
    title, draft = plan.review_required[0]
    assert "unknown label (Gremlin)" in title
    assert "plan-gate decision" in draft
    assert plan.deterministic_empty  # nothing sneaks through


def test_unknown_edge_type_is_review_required(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.edges.append(make_edge("ENABLES_TERRAIN", "Knack", "Frost",
                                   "Terrain", "Mire"))
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    assert plan.blocked
    assert "no relationship spec of type ENABLES_TERRAIN" in \
        plan.review_required[0][1]


def test_values_and_implicit_labels(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.ensure_node("Gem", "Sapphire")               # values: list
    scratch.ensure_node("Rune", "Gleaming")              # implicit, no props
    scratch.ensure_node("Rune", "Cursed", doc="x")       # implicit + props
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    problems = " | ".join(t for t, _ in plan.review_required)
    assert "values:-list label (Gem) 'Sapphire'" in problems
    assert "implicit label (Rune) 'Cursed'" in problems
    assert any("'Gleaming' is implicit" in n for n in plan.notices)


def test_removals_are_manual(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    del scratch.nodes[("Knack", "Blink")]
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    assert any("removals are approver acts" in a for a in plan.manual_actions)
    assert not plan.blocked  # manual != blocked; report carries them


def test_two_edges_into_one_cell_coalesce(make_repo):
    # two connections landing in the same (row, column) become ONE edit
    # built on one before-image — the second must not discard the first
    base_dir, path, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Frost",
                                   "Knack", "Frost"))
    scratch.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Frost",
                                   "Knack", "Bolt"))
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    edits = [e for e in plan.cell_edits if e[3] == "Knacks Granted"]
    assert len(edits) == 1
    _, _, key, _, old, new, _ = edits[0]
    assert key == "Frost" and old == ""
    assert "Frost" in new and "Bolt" in new

    apply_plan(plan, base_dir)
    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)
    residual = diff(new_base, scratch)
    assert residual.edges_added == []  # BOTH connections survived the write


def test_edge_property_correction_is_one_pinned_cell_edit(make_repo):
    # transitions.csv holds Frost -> Bolt {trigger: switcheroo}; correcting
    # the trigger renders as one cell edit pinned to the right row
    base_dir, path, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.edges = [e for e in scratch.edges if e.type != "SWAPS_WITH"]
    scratch.edges.append(make_edge("SWAPS_WITH", "Knack", "Frost",
                                   "Knack", "Bolt", {"trigger": "flip"}))
    delta = diff(base, scratch)
    assert len(delta.edges_changed) == 1

    plan = build_plan(delta, ontology, base_dir)
    assert not plan.blocked, plan.review_required
    [(relpath, key_col, key, column, old, new, where)] = plan.cell_edits
    assert (relpath, key_col, key, column) == \
        ("data/transitions.csv", "From", "Frost", "Trigger")
    assert (old, new) == ("switcheroo", "flip")
    assert where == {"To": "Bolt"}  # the pin: parallel rows stay safe

    apply_plan(plan, base_dir)
    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)
    assert diff(new_base, scratch).edges_changed == []


def test_conflicting_edits_to_one_cell_are_refused(make_repo):
    # defense in depth: a plan that somehow carries two edits to the same
    # cell is refused with both named, nothing written
    from graph.canonize import EditPlan
    base_dir, _, _, _ = build_base(make_repo)
    plan = EditPlan()
    plan.cell_edits.append(("data/knacks.csv", "Knack", "Frost", "Prevented By",
                            "", "Mire", {}))
    plan.cell_edits.append(("data/knacks.csv", "Knack", "Frost", "Prevented By",
                            "", "Windswept", {}))
    with pytest.raises(RuntimeError) as exc:
        apply_plan(plan, base_dir)
    message = str(exc.value)
    assert "twice in one plan" in message
    assert "Mire" in message and "Windswept" in message
    assert "nothing was written" in message


def test_removal_manual_action_shows_before_image(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    del scratch.nodes[("Knack", "Blink")]
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    action = next(a for a in plan.manual_actions if "Blink" in a)
    assert "it held" in action  # the undo record travels with the ask
    assert "removals are approver acts" in action


def test_apply_precondition_catches_file_drift(make_repo):
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.nodes[("Knack", "Frost")]["knack_class"] = "Active"
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    # the file moves under the plan
    knacks = base_dir / "data" / "knacks.csv"
    knacks.write_text(knacks.read_text(encoding="utf-8").replace(
        "Frost,Reactive", "Frost,Hybrid"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Attempted to edit"):
        apply_plan(plan, base_dir)
    # two-phase: NOTHING was written despite other valid edits
    assert "Hybrid" in knacks.read_text(encoding="utf-8")


def test_apply_collates_every_problem(make_repo):
    # error doctrine: collate, don't stop — both drifted cells reported
    # in ONE failure, and nothing written
    base_dir, _, ontology, base = build_base(make_repo)
    scratch = clone(base)
    scratch.nodes[("Knack", "Frost")]["knack_class"] = "Active"
    scratch.nodes[("Knack", "Bolt")]["knack_class"] = "Reactive"
    plan = build_plan(diff(base, scratch), ontology, base_dir)
    knacks = base_dir / "data" / "knacks.csv"
    text = knacks.read_text(encoding="utf-8")
    knacks.write_text(text.replace("Frost,Reactive", "Frost,Hybrid")
                          .replace("Bolt,Active", "Bolt,Hybrid"),
                      encoding="utf-8")
    with pytest.raises(RuntimeError) as exc:
        apply_plan(plan, base_dir)
    message = str(exc.value)
    assert message.count("Attempted to edit") == 2
    assert "nothing was written" in message


# -- property-table props render as cell edits in their own file ---------------

TABLE_FILES = {
    "data/things.csv": """\
        Thing,Kind
        Rock,Mineral
        Stick,Wood
        """,
    "data/weights.csv": """\
        Thing,Weight
        Rock,2.5
        Stick,0.5
        """,
}

TABLE_ONTOLOGY = """\
    version: 1
    nodes:
      Thing:
        source: data/things.csv
        key: Thing
        catalog:
          kind:   { type: text,  doc: "what it is" }
          weight: { type: float, doc: "how heavy" }
        properties:
          kind: { column: Kind }
        property_tables:
          - source: data/weights.csv
            key: Thing
            properties:
              weight: { column: Weight }
    """


# -- version auto-stamp + schema fingerprint (owner ruling) ------------------

from graph.canonize import schema_fingerprint, stamp_ontology_anchor


def schema_graph():
    """A tiny graph with a schema stratum and one ground fact — enough to
    exercise the anchor stamp and the stratum fingerprint without a DB."""
    g = GraphData()
    g.ensure_node("Terrain", "Frost", defense_mod=-2)        # a ground fact
    # schema stratum: the anchor + a one-concept tower
    g.ensure_node("Archetype", "Ontology", doc="the schema anchor",
                  rank=1, version=7, fingerprint="stale")
    g.ensure_node("Archetype", "Terrain", doc="a domain concept")
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Terrain",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("INSTANCE_OF", "Archetype", "Terrain",
                             "Archetype", "Concept"))
    # a citizen's derived shadow — NOT part of the schema stratum
    g.edges.append(make_edge("INSTANCE_OF", "Terrain", "Frost",
                             "Archetype", "Terrain"))
    return g


def test_apply_stamps_version_from_the_log_sequence():
    g = schema_graph()
    assert stamp_ontology_anchor(g, 42) == []
    assert g.nodes[("Archetype", "Ontology")]["version"] == 42
    # the fingerprint moved off its stale value to the stratum's real hash
    fp = g.nodes[("Archetype", "Ontology")]["fingerprint"]
    assert fp != "stale"
    assert fp == schema_fingerprint(g)


def test_second_identical_stamp_is_idempotent():
    g = schema_graph()
    stamp_ontology_anchor(g, 42)
    first = dict(g.nodes[("Archetype", "Ontology")])
    stamp_ontology_anchor(g, 42)
    assert dict(g.nodes[("Archetype", "Ontology")]) == first


def test_schema_fingerprint_is_deterministic_and_order_free():
    g1, g2 = schema_graph(), schema_graph()
    g2.edges = list(reversed(g2.edges))  # insertion order must not matter
    assert schema_fingerprint(g1) == schema_fingerprint(g2)


def test_fingerprint_ignores_anchor_stamps_but_tracks_schema_shape():
    g = schema_graph()
    before = schema_fingerprint(g)
    # bumping the anchor's OWN version/fingerprint must not move the hash
    g.nodes[("Archetype", "Ontology")]["version"] = 999
    g.nodes[("Archetype", "Ontology")]["fingerprint"] = "whatever"
    assert schema_fingerprint(g) == before
    # a real schema edit (a new concept) does move it
    g.ensure_node("Archetype", "Newborn Concept")
    assert schema_fingerprint(g) != before


def test_stamp_preserves_the_free_text_tag():
    g = schema_graph()
    g.nodes[("Archetype", "Ontology")]["tag"] = "a later round"
    stamp_ontology_anchor(g, 5)
    assert g.nodes[("Archetype", "Ontology")]["tag"] == "a later round"


def test_stamp_names_a_missing_anchor():
    g = GraphData()
    g.ensure_node("Terrain", "Frost")
    problems = stamp_ontology_anchor(g, 1)
    assert problems and "version anchor" in problems[0]
    assert "Failed due to" in problems[0]


def test_property_table_prop_edits_its_own_file(make_repo):
    base_dir, path = make_repo(TABLE_FILES, TABLE_ONTOLOGY)
    ontology, _ = load_ontology(path, base_dir)
    base, _ = extract(ontology)
    scratch = clone(base)
    scratch.nodes[("Thing", "Rock")]["weight"] = 9.0

    plan = build_plan(diff(base, scratch), ontology, base_dir)
    assert not plan.blocked
    # the edit lands in the property table's file, not the label's source
    assert [(e[0], e[3]) for e in plan.cell_edits] == \
        [("data/weights.csv", "Weight")]

    apply_plan(plan, base_dir)
    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)
    residual = diff(new_base, scratch)
    assert residual.nodes_changed == []
    assert residual.nodes_added == []


# -- canonize refusals as durable records (the durable-refusal work) -----

from graph.canonize import (clear_refusal_report, refusal_report_path,
                            write_refusal_report)


def test_refusal_report_writes_coded_rows(tmp_path):
    from graph.report import Verdict
    from graph import export as export_mod
    g = GraphData()
    g.ensure_node("Terrain", "Bog")
    export_mod.write_export(g, tmp_path / "graph" / "export")
    write_refusal_report(tmp_path, None, [Verdict(
        code="approval-missing", message="no approval on record",
        remedy="approve first", data={"items": ["a", "b"]})])
    import json as json_mod
    doc = json_mod.loads(refusal_report_path(tmp_path).read_text())
    assert doc["kind"] == "canonize-refusal"
    assert doc["kb"]  # the line of truth is named
    row = doc["refusals"][0]
    assert row["code"] == "approval-missing"
    assert row["ref"] == "no-approval"     # designer-safe ref key
    assert row["data"]["items"] == ["a", "b"]
    # a clean run retires the artifact — never a stale report
    clear_refusal_report(tmp_path)
    assert not refusal_report_path(tmp_path).exists()


def test_a_refused_apply_leaves_the_artifact(tmp_path, monkeypatch,
                                             capsys):
    # the smallest real refusal: an apply with no approval on record —
    # stderr prints as it always has AND the record lands beside the
    # round, coded and inspectable
    from graph import export as export_mod
    from graph.__main__ import cmd_canonize, cmd_init
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    assert cmd_init(tmp_path) == 0

    class Quiet:
        def __getattr__(self, name):
            raise AssertionError("no database should be touched")

    # scratch equals the base: dodge the DB by pointing the reader at
    # the export itself
    import graph.__main__ as main_mod
    from graph.restore import read_export
    monkeypatch.setattr(
        "graph.delta.read_graph",
        lambda config: read_export(tmp_path / "graph" / "export"))
    monkeypatch.setattr("graph.__main__._working_copy_check",
                        lambda *a, **k: "")
    assert cmd_canonize(tmp_path, None, apply=True) == 1
    assert "no approval on record" in capsys.readouterr().err
    import json as json_mod
    doc = json_mod.loads(refusal_report_path(tmp_path).read_text())
    assert [r["code"] for r in doc["refusals"]] == ["approval-missing"]
    # and a clean dry run clears it
    assert cmd_canonize(tmp_path, None, apply=False) == 0
    assert not refusal_report_path(tmp_path).exists()
