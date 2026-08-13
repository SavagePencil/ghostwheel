"""Visibility lenses: pure logic — declarations, fold, compile, apply,
explain, require. No driver anywhere. The coherence rule (an edge never
outlives an endpoint) and the flat-deny rule are the charter's floors."""

import copy

import pytest

from graph.extract import GraphData, make_edge
from graph.lens import (apply_lens, compile_lens, explain, fold,
                        load_declarations, require)


def declarations():
    """The charter's walkthrough shape: an individual, a nesting group,
    common knowledge included by villager knowledge, a masking class for
    the Judgment stratum, and explicit secret membership."""
    return {
        "groups": {
            "pip": {},
            "maren": {},
            "villagers": {"members": ["pip"]},
        },
        "classes": {
            "common-knowledge": {"kind": "knowledge"},
            "villager-knowledge": {"kind": "knowledge",
                                   "includes": ["common-knowledge"]},
            "judgment": {"kind": "masking",
                         "labels": ["Question", "Decision", "Answer",
                                    "Opinion", "Requirement", "TODO",
                                    "Approved Omission",
                                    "Approved Difference"]},
            "sunstone-secret": {"kind": "knowledge"},
        },
        "membership": {
            "sunstone-secret": {
                "nodes": [["Verbatim",
                           "the sunstone is hidden in the hollow oak"]],
                "edges": [["HIDDEN_IN", "Gem", "Sunstone",
                           "Grove", "The Hollow Oak"]],
            },
            "common-knowledge": {
                "nodes": [["Verbatim", "acorns fall in autumn"]]},
            "villager-knowledge": {
                "nodes": [["Verbatim", "market day is on saturday"]]},
        },
        "verdicts": [
            {"group": "pip", "class": "sunstone-secret", "verdict": "allow"},
            {"group": "villagers", "class": "villager-knowledge",
             "verdict": "allow"},
        ],
    }


def small_graph():
    graph = GraphData()
    graph.ensure_node("Gem", "Sunstone")
    graph.ensure_node("Grove", "The Hollow Oak")
    graph.ensure_node("Verbatim", "the sunstone is hidden in the hollow oak")
    graph.ensure_node("Verbatim", "acorns fall in autumn")
    graph.ensure_node("Verbatim", "market day is on saturday")
    graph.ensure_node("Decision", "the sunstone stays hidden", status="ruled")
    graph.edges.append(make_edge(
        "HIDDEN_IN", "Gem", "Sunstone", "Grove", "The Hollow Oak"))
    graph.edges.append(make_edge(
        "QUOTED_IN", "Verbatim", "the sunstone is hidden in the hollow oak",
        "Gem", "Sunstone"))
    graph.edges.append(make_edge(
        "ABOUT", "Decision", "the sunstone stays hidden", "Gem", "Sunstone"))
    return graph


def visible_nodes(graph, lens_obj):
    return set(apply_lens(graph, lens_obj).nodes)


# -- fold ------------------------------------------------------------------


def test_fold_is_transitive_and_an_individual_is_a_size_1_group():
    decls = declarations()
    decls["groups"]["folk"] = {"members": ["villagers"]}
    assert fold(decls, "pip") == {"pip", "villagers", "folk"}
    assert fold(decls, "maren") == {"maren"}
    with pytest.raises(ValueError, match="no group by that name"):
        fold(decls, "stranger")


def test_group_membership_cycle_refuses():
    decls = declarations()
    decls["groups"]["pip"] = {"members": ["villagers"]}
    with pytest.raises(ValueError, match="circle"):
        load_declarations(decls)


def test_includes_cycle_refuses():
    decls = declarations()
    decls["classes"]["common-knowledge"]["includes"] = \
        ["villager-knowledge"]
    with pytest.raises(ValueError, match="circle"):
        load_declarations(decls)


def test_validation_collates_every_problem_into_one_refusal():
    decls = declarations()
    decls["groups"]["villagers"]["members"].append("nobody")
    decls["classes"]["mystery"] = {}  # no kind
    decls["verdicts"].append({"group": "pip", "class": "absent",
                              "verdict": "maybe"})
    decls["verdict"] = []  # typo'd section
    with pytest.raises(ValueError) as caught:
        load_declarations(decls)
    message = str(caught.value)
    assert "Attempted to load the visibility declarations" in message
    assert "unknown member group 'nobody'" in message
    assert "kind 'None'" in message
    assert "unknown class 'absent'" in message
    assert "rules 'maybe'" in message
    assert "unrecognized section 'verdict'" in message


def test_the_file_surface_is_retired(tmp_path):
    # declarations live on the graph; a path (or any non-mapping) is
    # refused by name with the graph reader named as the way in.
    with pytest.raises(ValueError, match="declarations_from_graph"):
        load_declarations(str(tmp_path / "lenses.yaml"))
    with pytest.raises(ValueError, match="file surface is retired"):
        load_declarations(tmp_path / "lenses.yaml")


# -- the knowledge path: assume-deny ---------------------------------------


def test_knowledge_assumes_deny_and_grants_open():
    decls, graph = declarations(), small_graph()
    # maren holds no grants: every knowledge-gated element is hidden,
    # everything ungated stays (universal mechanics)
    nodes = visible_nodes(graph, compile_lens(decls, graph,
                                              subject="maren"))
    assert ("Gem", "Sunstone") in nodes
    assert ("Grove", "The Hollow Oak") in nodes
    assert ("Verbatim",
            "the sunstone is hidden in the hollow oak") not in nodes
    assert ("Verbatim", "acorns fall in autumn") not in nodes
    # pip's allow on sunstone-secret opens the secret node and the gated edge
    lensed = apply_lens(graph, compile_lens(decls, graph, subject="pip"))
    assert ("Verbatim",
            "the sunstone is hidden in the hollow oak") in lensed.nodes
    assert any(edge.type == "HIDDEN_IN" for edge in lensed.edges)
    # the gated HIDDEN_IN edge is hidden for maren even though both its
    # endpoints are visible — edge membership is its own gate
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            subject="maren"))
    assert not any(edge.type == "HIDDEN_IN" for edge in lensed.edges)


def test_includes_grants_the_parent_through_the_child():
    decls, graph = declarations(), small_graph()
    # pip holds no DIRECT allow on common-knowledge; the allow on
    # villager-knowledge (via the villagers group) includes it
    nodes = visible_nodes(graph, compile_lens(decls, graph,
                                              subject="pip"))
    assert ("Verbatim", "acorns fall in autumn") in nodes
    assert ("Verbatim", "market day is on saturday") in nodes


def test_deny_wins_over_allow_on_a_flat_class():
    decls = declarations()
    decls["verdicts"].append(
        {"group": "pip", "class": "sunstone-secret", "verdict": "deny"})
    graph = small_graph()
    nodes = visible_nodes(graph, compile_lens(decls, graph,
                                              subject="pip"))
    assert ("Verbatim",
            "the sunstone is hidden in the hollow oak") not in nodes


def test_deny_against_a_nested_class_refuses():
    decls = declarations()
    decls["verdicts"].append({"group": "pip",
                              "class": "villager-knowledge",
                              "verdict": "deny"})
    with pytest.raises(ValueError, match="FLAT classes"):
        load_declarations(decls)


# -- the masking path: assume-allow ----------------------------------------


def test_masking_assumes_allow():
    decls, graph = declarations(), small_graph()
    # no mask: the Decision row stays (assume-allow), no subject given
    identity = compile_lens(decls, graph)
    assert ("Decision", "the sunstone stays hidden") in \
        visible_nodes(graph, identity)
    # masked: the Decision row is gone; nothing else moves
    masked = compile_lens(decls, graph, mask=("judgment",))
    nodes = visible_nodes(graph, masked)
    assert ("Decision", "the sunstone stays hidden") not in nodes
    assert nodes == set(graph.nodes) - {("Decision",
                                         "the sunstone stays hidden")}


def test_mask_must_name_a_declared_masking_class():
    decls, graph = declarations(), small_graph()
    with pytest.raises(ValueError, match="unknown class 'nonsense'"):
        compile_lens(decls, graph, mask=("nonsense",))
    with pytest.raises(ValueError, match="only masking classes"):
        compile_lens(decls, graph, mask=("sunstone-secret",))


# -- coherence and purity --------------------------------------------------


def test_edge_to_a_hidden_node_disappears_even_if_unmasked():
    decls, graph = declarations(), small_graph()
    # the ABOUT edge is in no class at all, but its Decision endpoint
    # is masked away — the edge must go with it (coherence rule 1)
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            mask=("judgment",)))
    assert not any(edge.type == "ABOUT" for edge in lensed.edges)
    # same rule on the knowledge path: QUOTED_IN is ungated, but its
    # Verbatim endpoint is hidden from maren
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            subject="maren"))
    assert not any(edge.type == "QUOTED_IN" for edge in lensed.edges)


def test_apply_lens_never_mutates_the_input():
    decls, graph = declarations(), small_graph()
    snapshot = copy.deepcopy(graph)
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            subject="maren",
                                            mask=("judgment",)))
    assert graph == snapshot
    lensed.nodes[("Gem", "Sunstone")]["tampered"] = True
    lensed.edges.clear()
    assert graph == snapshot


def test_identity_lens_is_a_no_op():
    decls, graph = declarations(), small_graph()
    lens_obj = compile_lens(decls, graph)  # no subject, no mask
    assert lens_obj.is_identity
    lensed = apply_lens(graph, lens_obj)
    assert lensed == graph
    assert lensed is not graph and lensed.nodes is not graph.nodes


# -- explain: the unfolded re-evaluation -----------------------------------


def test_explain_names_the_blocking_posture_and_the_would_open_grant():
    decls = declarations()
    trace = explain(decls, "maren",
                    ("Verbatim", "the sunstone is hidden in the hollow oak"))
    assert "'sunstone-secret'" in trace and "HIDDEN" in trace
    assert "assume deny" in trace
    assert "An allow on 'sunstone-secret'" in trace \
        and "would open it" in trace


def test_explain_names_the_blocking_verdict_on_a_deny():
    decls = declarations()
    decls["verdicts"].append(
        {"group": "pip", "class": "sunstone-secret", "verdict": "deny"})
    trace = explain(decls, "pip",
                    ("Verbatim", "the sunstone is hidden in the hollow oak"))
    assert "the deny for group 'pip' on 'sunstone-secret'" in trace
    assert "would open it once the deny is lifted" in trace
    assert trace.endswith("HIDDEN.")


def test_explain_traces_an_open_grant_through_includes():
    decls = declarations()
    trace = explain(decls, "pip",
                    ("Verbatim", "acorns fall in autumn"))
    assert ("the allow for group 'villagers' on "
            "'villager-knowledge', which includes "
            "'common-knowledge'") in trace
    assert trace.endswith("visible.")
    # an ungated element and a gated edge both explain themselves
    assert "no visibility class" in explain(decls, "pip",
                                            ("Gem", "Sunstone"))
    edge_trace = explain(decls, "maren",
                         ("HIDDEN_IN", "Gem", "Sunstone",
                          "Grove", "The Hollow Oak"))
    assert "'sunstone-secret'" in edge_trace and "HIDDEN" in edge_trace
    with pytest.raises(ValueError, match="element key"):
        explain(decls, "pip", ("just-one-part",))


# -- require: the build-time declaration check -----------------------------


def test_require_refuses_missing_classes_by_name():
    decls = declarations()
    assert require(decls, "runtime-export",
                   ["judgment", "sunstone-secret"]) == \
        ("judgment", "sunstone-secret")
    with pytest.raises(ValueError) as caught:
        require(decls, "runtime-export", ["judgment", "reader-lore"])
    message = str(caught.value)
    assert "Attempted to build 'runtime-export'" in message
    assert "'reader-lore'" in message and "classes:" in message


# -- integration: a canon-shaped graph under a subject + mask lens ---------


def test_judgment_mask_strips_decision_rows_while_canon_survives():
    graph = GraphData()
    graph.ensure_node("Archetype", "Terrain")
    graph.ensure_node("Terrain", "Bramble")
    graph.ensure_node("Terrain", "Fog")
    graph.ensure_node("Knack", "Leap")
    graph.ensure_node("Decision", "fog stacks with bramble")
    graph.ensure_node("Verbatim", "the teller's hidden twist")
    graph.edges.append(make_edge("INSTANCE_OF", "Terrain", "Bramble",
                                 "Archetype", "Terrain"))
    graph.edges.append(make_edge("INSTANCE_OF", "Terrain",
                                 "Fog", "Archetype", "Terrain"))
    graph.edges.append(make_edge("ABOUT", "Decision",
                                 "fog stacks with bramble",
                                 "Terrain", "Fog"))
    decls = {
        "groups": {"reader-one": {}, "readers": {"members": ["reader-one"]}},
        "classes": {
            "table-knowledge": {"kind": "knowledge"},
            "teller-secrets": {"kind": "knowledge"},
            "judgment": {"kind": "masking",
                         "labels": ["Question", "Decision", "Answer",
                                    "Opinion", "Requirement"]},
        },
        "membership": {
            "teller-secrets": {
                "nodes": [["Verbatim", "the teller's hidden twist"]]},
        },
        "verdicts": [
            {"group": "readers", "class": "table-knowledge",
             "verdict": "allow"},
        ],
    }
    lens_obj = compile_lens(decls, graph, subject="reader-one",
                            mask=("judgment",))
    lensed = apply_lens(graph, lens_obj)
    # the Judgment stratum is stripped, edge and all
    assert ("Decision", "fog stacks with bramble") not in lensed.nodes
    assert not any(edge.type == "ABOUT" for edge in lensed.edges)
    # the knowledge gate holds against the reader subject
    assert ("Verbatim", "the teller's hidden twist") not in lensed.nodes
    # every canonical element survives, INSTANCE_OF tower intact —
    # the caller re-derives machine layers over this lensed graph
    assert ("Terrain", "Bramble") in lensed.nodes
    assert ("Terrain", "Fog") in lensed.nodes
    assert ("Knack", "Leap") in lensed.nodes
    assert sum(edge.type == "INSTANCE_OF" for edge in lensed.edges) == 2


# -- residence: the vocabulary as citizens; Q1/Q2 rulings ------------------

def _residence_graph():
    """The owner's A/B/C acceptance case, as canon citizens: three
    visibility groups, a subject in A only, and one class per group's
    secrets."""
    from graph.extract import GraphData, make_edge
    from graph.lens import CLASS_LABEL, GROUP_LABEL
    g = GraphData()
    for name in ("me", "group-a", "group-b", "group-c"):
        g.ensure_node(GROUP_LABEL, name)
    g.ensure_node(CLASS_LABEL, "a-secrets", kind="knowledge")
    g.ensure_node(CLASS_LABEL, "b-secrets", kind="knowledge")
    g.ensure_node("Fact", "The A secret")
    g.ensure_node("Fact", "The B secret")
    g.ensure_node("Fact", "Water is wet")
    g.edges.append(make_edge("MEMBER_OF", GROUP_LABEL, "me",
                             GROUP_LABEL, "group-a"))
    g.edges.append(make_edge("ALLOWED", GROUP_LABEL, "group-a",
                             CLASS_LABEL, "a-secrets"))
    g.edges.append(make_edge("ALLOWED", GROUP_LABEL, "group-b",
                             CLASS_LABEL, "b-secrets"))
    g.edges.append(make_edge("IN_CLASS", "Fact", "The A secret",
                             CLASS_LABEL, "a-secrets"))
    g.edges.append(make_edge("IN_CLASS", "Fact", "The B secret",
                             CLASS_LABEL, "b-secrets"))
    return g


def test_declarations_read_from_canon_citizens():
    from graph.lens import declarations_from_graph
    decls = declarations_from_graph(_residence_graph())
    assert fold(decls, "me") == {"me", "group-a"}
    assert decls.classes["a-secrets"]["kind"] == "knowledge"


def test_the_owners_abc_case_you_see_a_not_b_or_c():
    # owner acceptance: "Groups A, B, and C. I'm only in Group A. If I
    # query which groups are available, do I only see A, or do B and C
    # come back, too." Ruled: fold-touching.
    from graph.lens import GROUP_LABEL, declarations_from_graph
    graph = _residence_graph()
    decls = declarations_from_graph(graph)
    lensed = apply_lens(graph, compile_lens(decls, graph, subject="me"))
    groups_seen = {name for label, name in lensed.nodes
                   if label == GROUP_LABEL}
    assert groups_seen == {"me", "group-a"}   # A and my own hat — not B, not C
    assert ("Fact", "The A secret") in lensed.nodes
    assert ("Fact", "The B secret") not in lensed.nodes
    assert ("Fact", "Water is wet") in lensed.nodes  # ungated stays


def test_you_see_the_doors_your_keys_open_and_no_others():
    from graph.lens import CLASS_LABEL, declarations_from_graph
    graph = _residence_graph()
    decls = declarations_from_graph(graph)
    lensed = apply_lens(graph, compile_lens(decls, graph, subject="me"))
    classes_seen = {name for label, name in lensed.nodes
                    if label == CLASS_LABEL}
    assert classes_seen == {"a-secrets"}
    # and the no-lens view (super admin) still sees the whole vocabulary
    everything = apply_lens(graph, compile_lens(decls, graph))
    assert ("Visibility Class", "b-secrets") in everything.nodes


def test_the_roster_hides_by_coherence():
    # the owner's "good catch": you see your group, not who else is in
    # it — other members' citizens are out of your fold, so their
    # MEMBER_OF edges drop with them
    from graph.extract import make_edge
    from graph.lens import GROUP_LABEL, declarations_from_graph
    graph = _residence_graph()
    graph.ensure_node(GROUP_LABEL, "somebody-else")
    graph.edges.append(make_edge("MEMBER_OF", GROUP_LABEL,
                                 "somebody-else", GROUP_LABEL, "group-a"))
    decls = declarations_from_graph(graph)
    lensed = apply_lens(graph, compile_lens(decls, graph, subject="me"))
    assert ("Visibility Group", "somebody-else") not in lensed.nodes
    rosters = [e for e in lensed.edges if e.type == "MEMBER_OF"
               and e.from_name == "somebody-else"]
    assert rosters == []


def test_redacted_explain_is_one_uniform_string():
    from graph.lens import REDACTED_REFUSAL, declarations_from_graph
    decls = declarations_from_graph(_residence_graph())
    # a hidden fact, a hidden class, and a hidden group all answer
    # IDENTICALLY — no wording variant becomes an oracle
    hidden_fact = explain(decls, "me", ("Fact", "The B secret"),
                          candid=False)
    hidden_class = explain(decls, "me",
                           ("Visibility Class", "b-secrets"),
                           candid=False)
    hidden_group = explain(decls, "me", ("Visibility Group", "group-c"),
                           candid=False)
    assert hidden_fact == hidden_class == hidden_group == \
        REDACTED_REFUSAL
    assert explain(decls, "me", ("Fact", "The A secret"),
                   candid=False) == "Visible."
    # candid mode (the curator surface) still names everything
    assert "b-secrets" in explain(decls, "me", ("Fact", "The B secret"))
