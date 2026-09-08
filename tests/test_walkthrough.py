"""The lens walkthrough: the lens design's acceptance story, executable
— a villager who knows where the sunstone is, but only inside a pocket
realm. Branch selects the world; the lens filters within it; the grant
is itself branch content, so temporary permission needs no mechanism at
all."""

from graph.extract import GraphData, make_edge
from graph.lens import apply_lens, compile_lens, explain

SUNSTONE_NODES = [["Gem", "Sunstone"], ["Grove", "The Hollow Oak"]]
SUNSTONE_EDGE = ["HIDDEN_IN", "Gem", "Sunstone", "Grove", "The Hollow Oak"]


def canon_graph():
    g = GraphData()
    g.ensure_node("Fact", "Water is wet")
    g.ensure_node("Fact", "the mayor lives on the hill")
    g.ensure_node("Terrain", "Bramble", defense_mod=-2)  # ungated mechanics
    return g


def canon_declarations():
    return {
        "groups": {
            "pip": {},
            "maren": {},
            "villagers": {"members": ["pip", "maren"]},
        },
        "classes": {
            "common-knowledge": {"kind": "knowledge"},
            "villager-knowledge": {"kind": "knowledge",
                                   "includes": ["common-knowledge"]},
        },
        "membership": {
            "common-knowledge": {"nodes": [["Fact", "Water is wet"]]},
            "villager-knowledge": {
                "nodes": [["Fact", "the mayor lives on the hill"]]},
        },
        "verdicts": [
            {"group": "villagers", "class": "villager-knowledge",
             "verdict": "allow"},
        ],
    }


def pocket_graph():
    """The branch: canon plus the pocket's delta (the sunstone fact)."""
    g = canon_graph()
    g.ensure_node("Gem", "Sunstone")
    g.ensure_node("Grove", "The Hollow Oak")
    g.edges.append(make_edge(*SUNSTONE_EDGE))
    return g


def pocket_declarations():
    """The branch's declarations: canon's plus the sunstone-secret class
    and the grant — the grant is branch content like any other fact."""
    decls = canon_declarations()
    decls["classes"]["sunstone-secret"] = {"kind": "knowledge"}
    decls["membership"]["sunstone-secret"] = {"nodes": SUNSTONE_NODES,
                                              "edges": [SUNSTONE_EDGE]}
    decls["verdicts"].append(
        {"group": "pip", "class": "sunstone-secret", "verdict": "allow"})
    return decls


def visible_names(graph, decls, subject):
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            subject=subject))
    return {name for _, name in lensed.nodes}


def test_in_canon_pip_knows_town_but_no_sunstone_exists():
    seen = visible_names(canon_graph(), canon_declarations(), "pip")
    assert "Water is wet" in seen            # inherited via includes
    assert "the mayor lives on the hill" in seen
    assert "Bramble" in seen                  # ungated mechanics stay
    assert "Sunstone" not in seen             # nothing to know


def test_inside_the_pocket_pip_knows_the_sunstone_and_maren_does_not():
    graph, decls = pocket_graph(), pocket_declarations()
    pip = visible_names(graph, decls, "pip")
    assert {"Sunstone", "The Hollow Oak"} <= pip
    maren = visible_names(graph, decls, "maren")
    assert "Sunstone" not in maren
    # coherence: the HIDDEN_IN edge vanished with its endpoints
    lensed = apply_lens(graph, compile_lens(decls, graph,
                                            subject="maren"))
    assert not any(e.type == "HIDDEN_IN" for e in lensed.edges)
    # and Maren still knows what every villager knows
    assert "the mayor lives on the hill" in maren


def test_exiting_the_pocket_returns_the_canon_view():
    # dropping the branch = querying canon's graph and declarations;
    # the fact, the class, and the grant simply do not exist there
    seen = visible_names(canon_graph(), canon_declarations(), "pip")
    assert "Sunstone" not in seen


def test_landing_the_pocket_makes_the_knowledge_canon():
    # canonize applies the branch delta: fact, class membership, and
    # grant become canon rows — now Pip knows the sunstone in the real
    # world, and only Pip
    graph, decls = pocket_graph(), pocket_declarations()
    assert "Sunstone" in visible_names(graph, decls, "pip")
    assert "Sunstone" not in visible_names(graph, decls, "maren")


def test_the_owner_walks_lens_free():
    # super admin = no lens applied: the identity lens sees the whole
    # pocket, sunstone and all
    graph = pocket_graph()
    lens_obj = compile_lens(pocket_declarations(), graph)
    assert lens_obj.is_identity
    lensed = apply_lens(graph, lens_obj)
    assert lensed.nodes == graph.nodes and lensed.edges == graph.edges


def test_explain_names_the_grant_that_would_open_the_sunstone():
    trace = explain(pocket_declarations(), "maren",
                    ("Gem", "Sunstone"))
    assert "sunstone-secret" in trace
    # the unfolded re-evaluation says what WOULD open it
    assert "allow" in trace.lower()


def test_the_canonical_backup_refuses_to_be_lensed():
    # the one place lenses materialize is a lens-scoped export
    # ELSEWHERE — graph/export is always lens-free, what restore and
    # every round build from
    from pathlib import Path

    from graph.__main__ import cmd_export_lensed
    base_dir = Path(__file__).resolve().parent.parent
    assert cmd_export_lensed(base_dir, ["judgment"], "graph/export") == 1


def test_the_backup_guard_covers_child_paths_too():
    # review catch: an exact-path check let --out graph/export/runtime
    # pollute the backup tree from inside
    from pathlib import Path

    from graph.__main__ import cmd_export_lensed
    base_dir = Path(__file__).resolve().parent.parent
    assert cmd_export_lensed(base_dir, ["judgment"],
                             "graph/export/runtime") == 1


def test_explain_never_promises_a_grant_a_co_class_deny_defeats():
    # review catch: an element in two knowledge classes, one denied —
    # the would-open line for the other class must carry the caveat
    decls = pocket_declarations()
    decls["classes"]["thornmark-curse"] = {"kind": "knowledge"}
    decls["membership"]["thornmark-curse"] = {
        "nodes": [["Gem", "Sunstone"]]}
    decls["verdicts"].append(
        {"group": "maren", "class": "thornmark-curse", "verdict": "deny"})
    trace = explain(decls, "maren", ("Gem", "Sunstone"))
    assert "keeps this element hidden" in trace
    assert "thornmark-curse" in trace


def test_knowledge_class_cannot_include_a_masking_class():
    import pytest as _pytest

    from graph.lens import load_declarations
    decls = canon_declarations()
    decls["classes"]["judgment"] = {"kind": "masking"}
    decls["classes"]["villager-knowledge"]["includes"] = ["judgment"]
    with _pytest.raises(ValueError, match="knowledge classes only"):
        load_declarations(decls)


def test_restore_from_requires_a_workspace_database():
    # --from loads workspaces only: no database named refuses, and the
    # live canon database refuses — canon only ever restores from the
    # canonical backup
    from pathlib import Path

    from graph.__main__ import cmd_restore
    from graph.load import read_config
    base_dir = Path(__file__).resolve().parent.parent
    live = read_config(base_dir)["NEO4J_DATABASE"]
    assert cmd_restore(base_dir, database=None,
                       from_dir="/tmp/anywhere") == 1
    assert cmd_restore(base_dir, database=live,
                       from_dir=str(base_dir / "graph" / "export")) == 1


def activation_declarations():
    """The pocket as a wearable group: membership in Pocket
    Realm-1234 is what carries the sunstone grant."""
    decls = pocket_declarations()
    decls["groups"]["pocket-realm-1234"] = {"members": ["pip"]}
    decls["verdicts"] = [v for v in decls["verdicts"]
                         if v["class"] != "sunstone-secret"]
    decls["verdicts"].append({"group": "pocket-realm-1234",
                              "class": "sunstone-secret", "verdict": "allow"})
    return decls


def test_exiting_the_pocket_is_a_lens_subtraction():
    # session activation: "remove myself from Pocket Realm-1234"
    # without touching any membership — the fold minus the named group
    graph, decls = pocket_graph(), activation_declarations()
    wearing = apply_lens(graph, compile_lens(decls, graph,
                                             subject="pip"))
    assert ("Gem", "Sunstone") in wearing.nodes
    exited = apply_lens(graph, compile_lens(
        decls, graph, subject="pip",
        without=("pocket-realm-1234",)))
    assert ("Gem", "Sunstone") not in exited.nodes
    assert ("Fact", "the mayor lives on the hill") in exited.nodes


def test_wearing_one_hat_folds_only_that_group():
    # subject as an iterable: the exact hats worn this session
    graph, decls = pocket_graph(), activation_declarations()
    town_view = apply_lens(graph, compile_lens(
        decls, graph, subject=("villagers",)))
    assert ("Fact", "the mayor lives on the hill") in town_view.nodes
    assert ("Gem", "Sunstone") not in town_view.nodes
    # an empty active set is honest assume-deny, not an error
    bare = apply_lens(graph, compile_lens(decls, graph, subject=()))
    assert ("Fact", "the mayor lives on the hill") not in bare.nodes
    assert ("Terrain", "Bramble") in bare.nodes  # ungated mechanics


def test_subtracting_an_unknown_group_refuses():
    import pytest as _pytest
    graph, decls = pocket_graph(), activation_declarations()
    with _pytest.raises(ValueError, match="no such group"):
        compile_lens(decls, graph, subject="pip",
                     without=("never-declared",))
