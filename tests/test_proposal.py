"""The proposal lifecycle: canonical delta documents, content-hash
identity, divergence naming, and the Approved-to-Applied freeze. Pure
logic plus the mini-repo — no database needed."""

from graph.canonize import apply_plan, build_plan
from graph.delta import diff
from graph.extract import extract, make_edge
from graph.ontology import load_ontology
from graph.proposal import (archive_round, base_identity, content_hash,
                            current_dir, divergence, parse_delta,
                            serialize_delta, write_json)
from tests.test_canonize import agent_scratch, build_base, clone


def rich_delta(make_repo):
    base_dir, path, ontology, base = build_base(make_repo)
    scratch = agent_scratch(base)
    del scratch.nodes[("Knack", "Blink")]          # a removal w/ before-image
    scratch.edges = [e for e in scratch.edges       # an edge property edit
                     if e.type != "SWAPS_WITH" or e.from_name != "Frost"]
    return base_dir, path, ontology, base, scratch


def test_delta_document_round_trips(make_repo):
    _, _, _, base, scratch = rich_delta(make_repo)
    delta = diff(base, scratch)
    text = serialize_delta(delta)
    back = parse_delta(text)
    assert serialize_delta(back) == text
    assert back.nodes_added == delta.nodes_added
    assert back.nodes_removed == delta.nodes_removed
    assert back.edges_added == delta.edges_added
    assert back.edges_changed == delta.edges_changed


def test_proposal_id_is_stable_and_content_bound(make_repo):
    _, _, _, base, scratch = rich_delta(make_repo)
    once = content_hash(serialize_delta(diff(base, scratch)))
    twice = content_hash(serialize_delta(diff(base, scratch)))
    assert once == twice
    scratch.ensure_node("Knack", "Nimbus", knack_class="Active")
    assert content_hash(serialize_delta(diff(base, scratch))) != once


def test_divergence_names_both_directions(make_repo):
    _, _, _, base, scratch = rich_delta(make_repo)
    pinned = diff(base, scratch)
    assert divergence(pinned, diff(base, scratch)) == []  # frozen
    # tamper AFTER approval: one new fact, one reviewed fact withdrawn
    scratch.ensure_node("Knack", "Nimbus", knack_class="Active")
    del scratch.nodes[("Knack", "Glimmer")]
    scratch.edges = [e for e in scratch.edges
                     if e.from_name != "Glimmer"]
    problems = divergence(pinned, diff(base, scratch))
    text = " | ".join(problems)
    assert "Nimbus" in text and "never reviewed" in text
    assert "Glimmer" in text and "no longer in scratch" in text


def test_apply_replays_the_pinned_document(make_repo):
    # the pinned artifact drives apply — parse(serialize(delta)) must
    # reach the same fixpoint as applying the live delta would
    base_dir, path, ontology, base, scratch = rich_delta(make_repo)
    pinned_text = serialize_delta(diff(base, scratch))
    plan = build_plan(parse_delta(pinned_text), ontology, base_dir)
    assert not plan.blocked, plan.review_required
    apply_plan(plan, base_dir)
    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)
    residual = diff(new_base, scratch)
    assert residual.nodes_added == []
    assert residual.edges_added == []


def test_base_identity_tracks_source_changes(make_repo):
    base_dir, path, ontology, base = build_base(make_repo)
    pinned = base_identity(base)
    assert base_identity(base) == pinned
    knacks = base_dir / "data" / "knacks.csv"
    knacks.write_text(knacks.read_text(encoding="utf-8").replace(
        "Frost,Reactive", "Frost,Hybrid"), encoding="utf-8")
    ontology2, _ = load_ontology(path, base_dir)
    moved, _ = extract(ontology2)
    assert base_identity(moved) != pinned  # the base moved under the round


def test_archive_round_moves_the_artifacts(tmp_path):
    current = current_dir(tmp_path)
    write_json(current / "base.json", {"base_hash": "abc"})
    write_json(current / "delta.json", {"nodes_added": []})
    write_json(current / "approval.json", {"delta_hash": "d" * 64})
    archive = archive_round(tmp_path, "d" * 64)
    assert archive.name == "d" * 12
    assert (archive / "approval.json").exists()
    assert not (current / "approval.json").exists()  # current is clean


# -- the event log: inverses, replay, walk-back, chain ------------------------

from graph.proposal import (append_applied_log, apply_delta, ground_identity,
                            invert_delta, verify_applied_log)


def test_apply_delta_replays_the_round(make_repo):
    # applying the logged delta to the base reproduces the ground truth
    # the file edits produced — replay equivalence
    base_dir, path, ontology, base, scratch = rich_delta(make_repo)
    delta = diff(base, scratch)
    plan = build_plan(delta, ontology, base_dir)
    apply_plan(plan, base_dir)
    ontology2, _ = load_ontology(path, base_dir)
    new_base, _ = extract(ontology2)

    # the file era executes adds and changes; removals are manual
    # approver acts — the replay compares what was actually executed
    from graph.proposal import file_era_executed
    replayed = clone(base)
    problems = apply_delta(
        replayed, parse_delta(serialize_delta(file_era_executed(delta))))
    assert problems == []
    assert ground_identity(replayed) == ground_identity(new_base)


def test_walk_back_returns_to_base(make_repo):
    # apply, then apply the inverse — identical
    _, _, _, base, scratch = rich_delta(make_repo)
    delta = diff(base, scratch)
    walked = clone(base)
    assert apply_delta(walked, delta) == []
    assert ground_identity(walked) != ground_identity(base)
    inverse = parse_delta(serialize_delta(invert_delta(delta)))
    assert apply_delta(walked, inverse) == []
    assert ground_identity(walked) == ground_identity(base)


def test_inverse_covers_every_class(make_repo):
    # a delta exercising all six classes inverts and walks back
    base_dir, _, _, base = build_base(make_repo)
    scratch = clone(base)
    scratch.ensure_node("Knack", "Ember", knack_class="Active")  # added
    del scratch.nodes[("Knack", "Blink")]                        # removed
    scratch.nodes[("Knack", "Frost")]["knack_class"] = "Active"  # changed
    scratch.edges = [e for e in scratch.edges                    # edge change
                     if e.type != "SWAPS_WITH" or e.from_name != "Frost"]
    scratch.edges.append(make_edge("SWAPS_WITH", "Knack", "Frost",
                                   "Knack", "Bolt", {"trigger": "flip"}))
    scratch.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Frost",
                                   "Knack", "Bolt"))             # edge added
    delta = diff(base, scratch)
    assert delta.nodes_added and delta.nodes_removed and \
        delta.nodes_changed and delta.edges_added and delta.edges_changed
    walked = clone(base)
    assert apply_delta(walked, delta) == []
    assert apply_delta(walked, invert_delta(delta)) == []
    assert ground_identity(walked) == ground_identity(base)


def test_apply_refuses_moved_base_and_applies_nothing(make_repo):
    _, _, _, base, scratch = rich_delta(make_repo)
    delta = diff(base, scratch)
    moved = clone(base)
    moved.nodes[("Knack", "Blink")]["knack_class"] = "Hybrid"  # under the log
    before = ground_identity(moved)
    problems = apply_delta(moved, delta)
    assert any("properties changed since the before-image" in p
               for p in problems)
    assert ground_identity(moved) == before  # verify-all before apply-any


def test_applied_log_chains_and_detects_rewrites(tmp_path):
    append_applied_log(tmp_path, "d" * 64, "b" * 64, "c" * 64)
    append_applied_log(tmp_path, "e" * 64, "c" * 64, "f" * 64)
    assert verify_applied_log(tmp_path) == []
    # rewrite history: alter entry 1's delta hash
    from graph.proposal import applied_log_path
    path = applied_log_path(tmp_path)
    tampered = path.read_text(encoding="utf-8").replace("d" * 64, "x" * 64)
    path.write_text(tampered, encoding="utf-8")
    problems = verify_applied_log(tmp_path)
    assert any("entry 1" in p and "altered" in p for p in problems)
    assert any("entry 2" in p and "rewritten above" in p for p in problems)


def test_version_stamp_does_not_touch_ground_identity(make_repo):
    # the schema boundary: the restamp at apply mutates the (Archetype,
    # 'Ontology') anchor — a SCHEMA (UNAUTHORABLE) citizen — so
    # ground_identity, which EXCLUDES the schema stratum, is unchanged by
    # it, and the pinned base identity survives the mid-apply restamp.
    # When schema becomes authorable, ground_identity must WIDEN to
    # include the stratum; this test pins today's boundary.
    from graph.canonize import stamp_ontology_anchor
    from graph.extract import GraphData
    g = GraphData()
    g.ensure_node("Terrain", "Frost", defense_mod=-2)
    g.ensure_node("Archetype", "Ontology", version=3, fingerprint="x")
    g.ensure_node("Archetype", "Terrain")
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Terrain",
                             "Archetype", "Ontology"))
    before = ground_identity(g)
    assert stamp_ontology_anchor(g, 99) == []
    assert g.nodes[("Archetype", "Ontology")]["version"] == 99
    assert ground_identity(g) == before


def test_edge_documents_survive_props(make_repo):
    delta_edges = [make_edge("SWAPS_WITH", "Knack", "A", "Knack", "B",
                             {"trigger": "feint"})]
    from graph.delta import Delta
    delta = Delta()
    delta.edges_added = delta_edges
    back = parse_delta(serialize_delta(delta))
    assert back.edges_added == delta_edges


# -- the stitch: same-round endpoints land after re-derivation ----------------

import json as _json

import pytest

from graph.delta import Delta
from graph.extract import GraphData
from graph.proposal import STITCH_FILE, apply_stitch, read_stitch


def test_stitch_rides_the_document_and_the_hash():
    delta = Delta()
    text_without = serialize_delta(delta)
    delta.stitch = [make_edge("LINKS", "A", "x", "B", "y")]
    text_with = serialize_delta(delta)
    # the approval hash covers the stitch; pre-stitch archived rounds
    # keep their recorded ids (the key appears only when declared)
    assert content_hash(text_with) != content_hash(text_without)
    assert '"stitch"' in text_with and '"stitch"' not in text_without
    assert parse_delta(text_with).stitch == delta.stitch
    assert parse_delta(text_without).stitch == []


def test_stitch_divergence_and_inverse():
    pinned = Delta()
    pinned.stitch = [make_edge("LINKS", "A", "x", "B", "y")]
    frozen = Delta()
    frozen.stitch = [make_edge("LINKS", "A", "x", "B", "y")]
    assert divergence(pinned, frozen) == []
    problems = " | ".join(divergence(pinned, Delta()))
    assert "stitch" in problems and "no longer in scratch" in problems
    # the undo record removes what the stitch landed
    assert invert_delta(pinned).edges_removed == pinned.stitch


def test_apply_stitch_verifies_all_before_landing_any():
    graph = GraphData()
    graph.ensure_node("A", "x")
    graph.ensure_node("B", "y")
    good = make_edge("LINKS", "A", "x", "B", "y")
    ghost = make_edge("LINKS", "A", "x", "B", "ghost")
    problems = apply_stitch(graph, [good, ghost])
    assert any("'ghost' does not exist" in p for p in problems)
    assert good not in graph.edges  # nothing landed
    assert apply_stitch(graph, [good]) == []
    assert good in graph.edges
    assert any("already exists" in p for p in apply_stitch(graph, [good]))


def test_the_newborn_endpoint_round_lands_in_one_gate():
    # the shape that bit twice: a round births a citizen via its schema
    # edit and wants a ground edge pointing at it. Before derivation the
    # endpoint is absent and the stitch refuses whole; after derivation
    # births it, the same stitch lands.
    ground = GraphData()
    ground.ensure_node("Gauge", "Lamp Oil")
    stitch = [make_edge("DERIVED_FROM", "Gauge", "Lamp Oil",
                        "Archetype", "Lantern")]
    assert apply_stitch(ground, stitch) != []
    ground.ensure_node("Archetype", "Lantern")  # derivation's act
    assert apply_stitch(ground, stitch) == []
    assert stitch[0] in ground.edges


def test_read_stitch_reads_the_declared_file(tmp_path):
    assert read_stitch(tmp_path) == []
    path = current_dir(tmp_path) / STITCH_FILE
    path.parent.mkdir(parents=True)
    path.write_text(_json.dumps(
        [{"type": "LINKS", "from_label": "A", "from_name": "x",
          "to_label": "B", "to_name": "y", "props": {}}]),
        encoding="utf-8")
    [edge] = read_stitch(tmp_path)
    assert edge.type == "LINKS" and edge.to_name == "y"
    path.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        read_stitch(tmp_path)


def test_archive_round_carries_the_stitch_file(tmp_path):
    src = current_dir(tmp_path)
    src.mkdir(parents=True)
    (src / STITCH_FILE).write_text("[]", encoding="utf-8")
    dst = archive_round(tmp_path, "abcdef123456ffff")
    assert (dst / STITCH_FILE).read_text(encoding="utf-8") == "[]"
    assert not (src / STITCH_FILE).exists()
