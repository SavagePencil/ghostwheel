"""Workspace identity: every database says what it is, in-band. The
stamp describes the DATABASE, never the canon it holds — read-back
strips it, and the round machinery refuses a working copy whose
identity does not match the round it claims to serve (several KBs can
share one DBMS)."""

import graph.__main__ as main_mod
from graph.__main__ import _authoring_database
from graph.extract import GraphData, make_edge
from graph.load import read_config
from graph.workspace import (WORKSPACE_LABEL, identity_problem, strip)

# the in-memory DBMS and its wired KB fixture (imported into this
# module's namespace so pytest resolves the fixture here too)
from tests.test_branch import (STORYBOOK, FakeDBMS, build_canon,  # noqa: F401
                               driven_kb)


def _graph_with_stamp():
    graph = GraphData()
    graph.ensure_node("Archetype", "Concept", doc="root")
    graph.ensure_node(WORKSPACE_LABEL, "This database",
                      role="working-copy", base_hash="abc")
    graph.edges.append(make_edge(
        "INSTANCE_OF", "Archetype", "Concept", "Archetype", "Concept"))
    graph.edges.append(make_edge(
        "DESCRIBES", WORKSPACE_LABEL, "This database",
        "Archetype", "Concept"))
    return graph


def test_strip_removes_the_stamp_and_its_edges_only():
    graph = strip(_graph_with_stamp())
    assert list(graph.nodes) == [("Archetype", "Concept")]
    assert [edge.type for edge in graph.edges] == ["INSTANCE_OF"]


def test_strip_of_an_unstamped_graph_changes_nothing():
    graph = GraphData()
    graph.ensure_node("Archetype", "Concept", doc="root")
    before_nodes = dict(graph.nodes)
    strip(graph)
    assert graph.nodes == before_nodes


def test_missing_stamp_is_not_a_problem():
    assert identity_problem(None, "deadbeef", "scratch") is None


def test_missing_pin_is_not_a_problem():
    found = {"role": "working-copy", "base_hash": "abc"}
    assert identity_problem(found, None, "scratch") is None


def test_matching_working_copy_passes():
    found = {"role": "working-copy", "base_hash": "deadbeef"}
    assert identity_problem(found, "deadbeef", "scratch") is None


def test_matching_branch_copy_passes():
    found = {"role": "branch", "base_hash": "deadbeef"}
    assert identity_problem(found, "deadbeef", "rebuild") is None


def test_a_canon_database_refuses_to_serve_as_a_working_copy():
    found = {"role": "canon", "base_hash": "deadbeef"}
    problem = identity_problem(found, "deadbeef", "rulesdata")
    assert problem is not None
    assert "line of truth" in problem
    assert "rulesdata" in problem


def test_another_rounds_copy_refuses_with_both_identities_named():
    found = {"role": "working-copy", "base_hash": "aaaa1111aaaa1111"}
    problem = identity_problem(found, "bbbb2222bbbb2222", "scratch")
    assert problem is not None
    assert "aaaa1111aaaa" in problem and "bbbb2222bbbb" in problem
    assert "restore --database scratch" in problem


def test_authoring_database_explicit_flag_wins():
    config = {"NEO4J_SCRATCH_DATABASE": "manual-scratch"}
    assert _authoring_database("elsewhere", None, config) == "elsewhere"


def test_authoring_database_reads_the_kb_settings():
    config = {"NEO4J_SCRATCH_DATABASE": "manual-scratch"}
    assert _authoring_database(None, None, config) == "manual-scratch"


def test_authoring_database_default_is_unchanged():
    assert _authoring_database(None, None, {}) == "scratch"
    assert _authoring_database(None, None, None) == "scratch"
    assert _authoring_database(None, "rebuild", {}) == "rebuild-scratch"


def test_authoring_database_branch_composes_with_the_kb_name():
    config = {"NEO4J_SCRATCH_DATABASE": "manual-scratch"}
    assert _authoring_database(None, "rebuild", config) \
        == "rebuild-manual-scratch"


def test_stamp_queries_never_match_on_the_label_token():
    """A MATCH on a label the database has never seen makes the server
    emit an unknown-label notification, which the driver prints raw —
    internals reaching a designer-facing surface. The stamp's MATCH
    queries therefore carry the label as a parameterized labels()
    check; only CREATE (which births the label, quietly) inlines it.
    Proven by source inspection — the precedent for DB-bound wiring."""
    import inspect

    from graph import workspace

    for fn in (workspace.stamp, workspace.read_stamp):
        assert "MATCH (w:`" not in inspect.getsource(fn), fn.__name__


# --- the round machinery trusts only the round's own copy (CLI flow) ----

def test_the_rounds_own_copy_passes_the_identity_gate(driven_kb):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_delta(base, None) == 0


def test_another_kbs_copy_refuses_at_the_round(driven_kb, capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, database="scratch") == 0
    # another KB sharing the DBMS cuts a copy under the same name
    fake.stamp({"NEO4J_DATABASE": "scratch"}, "working-copy",
               "0000aaaa0000aaaa")
    assert main_mod.cmd_delta(base, None) == 1
    err = capsys.readouterr().err
    assert "working copy cut from base 0000aaaa0000" in err
    assert "restore --database scratch" in err


def test_a_canon_database_refuses_at_the_round(driven_kb, capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base) == 0  # canon restored + stamped
    canon_name = read_config(base)["NEO4J_DATABASE"]
    assert main_mod.cmd_delta(base, canon_name) == 1
    err = capsys.readouterr().err
    assert "line of truth" in err


def test_a_pre_stamp_copy_passes_with_a_note(driven_kb, capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, database="scratch") == 0
    # a copy cut before stamps existed carries none
    from graph.workspace import WORKSPACE_LABEL as wl
    scratch = fake.databases["scratch"]
    scratch.nodes = {key: props for key, props in scratch.nodes.items()
                     if key[0] != wl}
    assert main_mod.cmd_delta(base, None) == 0
    out = capsys.readouterr().out
    assert "no workspace identity stamp" in out
