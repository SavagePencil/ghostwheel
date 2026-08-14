"""Branches: an independent line of truth WITHIN a knowledge base.

A branch is cut from a declared base (schema-only here), lives in its own
filesystem home with its own backup and chained event log, runs the full
verify-all-before-apply-any round against its own database, and is
hard-isolated from the KB's live canon — a branch-scoped apply can never
touch the canon database, and the default (unnamed) line's homes stay
byte-for-byte unchanged.

The acceptance round walks three ground facts through a real gate in a
schema-only branch, entirely on graph VALUES (no Neo4j): diff vs the
branch base -> lint clean -> approval recorded against the content hash
-> apply the pinned changeset -> re-derive -> the branch's backup is
written and its log chained — while the default line's export and log
stay untouched. The DB-bound CLI wiring is proven by source inspection,
the precedent in test_schema_inversion_cli.py.
"""

import inspect
from pathlib import Path

import shutil

import pytest

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.delta import diff, lint
from graph.extract import (GraphData, derive, extract, make_edge,
                           schema_only, strip_derived)
from graph.ontology import (ARCHETYPE_LABEL, ERROR, MACHINE_LABELS,
                            SCHEMA_LABELS, is_derived_edge, load_ontology,
                            ontology_from_graph)
from graph.proposal import (APPROVAL_FILE, BASE_FILE, append_applied_log,
                            apply_delta, applied_log_path, authoring_read_problem,
                            base_identity, branch_home, branch_name_problems,
                            branch_target_database, content_hash, current_dir,
                            export_dir, parse_delta, proposals_dir,
                            read_applied_log, serialize_delta,
                            verify_applied_log, write_json)
from graph.restore import read_export

STORYBOOK = Path(__file__).resolve().parent / "fixtures" / "storybook"


def clone(graph):
    copy = GraphData()
    for (label, name), props in graph.nodes.items():
        copy.ensure_node(label, name, **dict(props))
    copy.edges = list(graph.edges)
    return copy


def build_canon():
    ontology, findings = load_ontology(STORYBOOK / "ontology.yaml", STORYBOOK)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR], \
        extract_findings
    return graph


# -- schema_only is exactly the schema stratum -----------------------------


def test_schema_only_keeps_exactly_the_schema_stratum():
    canon = build_canon()
    seed = schema_only(canon)

    # every kept node is a schema (Archetype) citizen — no ground, no machine
    assert all(label in SCHEMA_LABELS for label, _ in seed.nodes), \
        "schema_only kept a non-schema node"
    assert not any(label in MACHINE_LABELS for label, _ in seed.nodes)

    # byte-comparable to strip semantics: the node set is exactly the
    # Archetype subset that survives strip_derived (which keeps schema
    # PLUS ground); schema_only keeps the schema stratum ALONE.
    ground = strip_derived(canon)
    schema_nodes = {key for key in ground.nodes if key[0] in SCHEMA_LABELS}
    assert set(seed.nodes) == schema_nodes
    for key in schema_nodes:
        assert seed.nodes[key] == canon.nodes[key]  # props verbatim

    # every kept edge sits between two Archetypes and is NOT derived —
    # so exactly DECLARED_IN, SUBTYPE_OF, and Archetype-level ladders
    for edge in seed.edges:
        assert edge.from_label == ARCHETYPE_LABEL
        assert edge.to_label == ARCHETYPE_LABEL
        assert not is_derived_edge(edge)
    assert not any(is_derived_edge(edge) for edge in seed.edges)
    kept_types = {edge.type for edge in seed.edges}
    assert kept_types <= {"DECLARED_IN", "SUBTYPE_OF",
                          "INSTANCE_OF", "PRECEDES", "FOLLOWS"}

    # the projection genuinely drops the ground layer
    assert len(seed.nodes) < len(canon.nodes)
    assert any(label not in SCHEMA_LABELS for label, _ in canon.nodes)


# -- default-line paths byte-identical; branch homes under graph/branches --


def test_default_line_paths_are_unchanged_and_branches_nest(tmp_path):
    base = tmp_path
    # the default line keeps today's exact paths
    assert export_dir(base) == base / "graph" / "export"
    assert proposals_dir(base) == base / "graph" / "proposals"
    assert current_dir(base) == base / "graph" / "proposals" / "current"
    assert applied_log_path(base) == \
        base / "graph" / "proposals" / "applied.log"

    # a named branch lives under graph/branches/<name>/ — export/,
    # proposals/, and applied.log as a sibling of proposals/
    home = base / "graph" / "branches" / "rebuild"
    assert export_dir(base, "rebuild") == home / "export"
    assert proposals_dir(base, "rebuild") == home / "proposals"
    assert current_dir(base, "rebuild") == home / "proposals" / "current"
    assert applied_log_path(base, "rebuild") == home / "applied.log"


# -- the hard guard + the branch-name lint ---------------------------------


def test_branch_target_database_is_the_name_no_aliases():
    # the target database IS the branch name — one identity, no override
    target, problems = branch_target_database("rebuild", "neo4j")
    assert (target, problems) == ("rebuild", [])


def test_branch_name_lint_refuses_reserved_names():
    # collision with live canon: refused, and the refusal names the db
    problems = branch_name_problems("neo4j", "neo4j")
    text = " ".join(problems)
    assert "neo4j" in text
    assert "Attempted" in text and "Failed due to" in text
    assert "never becomes canon by flag" in text

    # 'scratch' and any '<name>-scratch' collide with authoring copies
    assert any("reserved" in p
               for p in branch_name_problems("scratch", "neo4j"))
    assert any("reserved" in p
               for p in branch_name_problems("rebuild-scratch", "neo4j"))

    # an empty name is named too
    assert any("no branch name" in p
               for p in branch_name_problems("", "neo4j"))

    # a clean name passes the lint
    assert branch_name_problems("rebuild", "neo4j") == []


def test_authoring_read_problem_refuses_canon_as_source():
    # a branch may never read live canon as its authoring source
    problem = authoring_read_problem("neo4j", "neo4j")
    assert problem is not None and "neo4j" in problem
    assert "hard-isolated from canon" in problem
    # its own <name>-scratch is fine
    assert authoring_read_problem("rebuild-scratch", "neo4j") is None


# -- the acceptance round: three facts through a real gate -----------------


def _snapshot(base):
    """Byte snapshot of every file under base — to prove the default line
    is untouched by branch work."""
    return {p: p.read_bytes()
            for p in sorted(base.rglob("*")) if p.is_file()}


def test_full_branch_round_leaves_canon_byte_untouched(tmp_path):
    base = tmp_path
    branch = "rebuild"

    # 1. canon: build from the storybook and write the DEFAULT line's
    #    backup — this stands in for live canon.
    canon = build_canon()
    export_mod.write_export(canon, export_dir(base))
    # nothing else on the default line: no round, no event log
    assert not applied_log_path(base).exists()
    canon_before = _snapshot(base)

    # 2. cut the branch: schema-only seed -> the branch's OWN backup; pin
    #    the branch round's base at that content identity.
    seed = schema_only(read_export(export_dir(base)))
    export_mod.write_export(seed, export_dir(base, branch))
    base_hash = base_identity(seed)
    write_json(current_dir(base, branch) / BASE_FILE,
               {"base_hash": base_hash, "git_ref": "test",
                "database": branch, "branch": branch})

    # 3. author three ground facts into the branch's graph value
    branch_base = read_export(export_dir(base, branch))
    authored = clone(branch_base)
    authored.ensure_node("Character", "Ember", temperament="bright")
    authored.ensure_node("Place", "Hearth")
    authored.edges.append(
        make_edge("LIVES_IN", "Character", "Ember", "Place", "Hearth"))

    # 4. delta: diff vs the branch base, lint clean
    changes = diff(branch_base, authored)
    assert lint(changes) == []
    assert ("Character", "Ember", {"temperament": "bright"}) \
        in changes.nodes_added
    assert ("Place", "Hearth", {}) in changes.nodes_added
    assert [(e.from_name, e.to_name) for e in changes.edges_added] \
        == [("Ember", "Hearth")]

    # 5. approve: record the approval against the proposal's content hash
    delta_text = serialize_delta(changes)
    delta_id = content_hash(delta_text)
    write_json(current_dir(base, branch) / APPROVAL_FILE,
               {"delta_hash": delta_id, "base_hash": base_hash,
                "by": "owner"})

    # 6. apply the PINNED changeset to the branch's ground, re-derive
    pinned = parse_delta(delta_text)
    ground = strip_derived(branch_base)
    assert apply_delta(ground, pinned) == []
    reconstructed = ontology_from_graph(branch_base, base)
    new_graph, findings = derive(reconstructed, ground)
    assert not [f for f in findings if f.severity == ERROR], findings
    assert ("Character", "Ember") in new_graph.nodes
    assert ("Place", "Hearth") in new_graph.nodes

    # 7. write the branch's backup and chain its event log
    export_mod.write_export(new_graph, export_dir(base, branch))
    chain = append_applied_log(base, delta_id, base_hash,
                               base_identity(new_graph), branch)
    assert chain
    assert verify_applied_log(base, branch) == []
    [(seq, logged_hash, *_rest)] = read_applied_log(base, branch)
    assert seq == 1 and logged_hash == delta_id

    # the branch's home carries the backup, the log, and the round pin
    assert applied_log_path(base, branch).exists()
    assert (export_dir(base, branch) / "nodes.jsonl").exists()

    # 8. THE ISOLATION CLAIM: the default line is byte-for-byte untouched —
    #    every branch artifact landed under graph/branches/, and canon's
    #    export and (absent) event log never moved.
    assert not applied_log_path(base).exists()
    assert read_applied_log(base) == []
    canon_after = {p: b for p, b in _snapshot(base).items()
                   if "branches" not in p.parts}
    assert canon_after == canon_before


# -- the DB-bound CLI wiring, proven by source inspection ------------------

BRANCH_AWARE = ("cmd_restore", "_restore_branch", "cmd_delta",
                "cmd_canonize", "cmd_approve")


def test_cli_round_commands_are_branch_aware():
    for name in BRANCH_AWARE:
        src = inspect.getsource(getattr(main_mod, name))
        assert "branch" in src, f"{name} is not branch-aware"


def test_restore_branch_projects_schema_only_and_guards():
    src = inspect.getsource(main_mod._restore_branch)
    assert "schema_only" in src
    assert "branch_name_problems" in src            # the name lint at the cut
    assert "already exists" in src                  # the re-cut refusal
    assert "no aliases" in src                       # the --database rejection
    # only the schema-only base is accepted in this slice
    assert "schema-only" in src


def test_canonize_guard_fires_before_any_read_or_write():
    src = inspect.getsource(main_mod.cmd_canonize)
    assert "branch_target_database" in src
    assert "authoring_read_problem" in src
    guard = src.index("if guard:")
    read = src.index("delta_mod.read_graph(config)")
    write = src.index("load_mod.load(new_graph")
    export = src.index("export_mod.write_export")
    # verify-all before apply-any: the guard is checked before the
    # authoring copy is even read, and before anything is written.
    assert guard < read
    assert guard < write
    assert guard < export


def test_canonize_targets_branch_home_not_canon():
    src = inspect.getsource(main_mod.cmd_canonize)
    # the target export, log, and archive are branch-scoped: each names
    # `branch` so a branch round writes only under the branch's home
    assert "export_dir(base_dir, branch)" in src
    assert "base_after, branch)" in src            # append_applied_log
    assert "approval[\"delta_hash\"],\n" in src \
        and "branch)" in src                        # archive_round


# -- the round DRIVEN through the real CLI, over a fake driver seam ---------
# The pure-logic test above walks the appliers by hand; this one calls the
# actual cmd_* functions end to end, faking only the Neo4j driver's three
# entry points (load / dump_db / read_graph) with an in-memory DBMS. It is
# the test that would have caught the re-cut, stranding, authoring-read,
# and namespace defects — every one lives in the CLI orchestration the
# hand-walk skipped.


class FakeDBMS:
    """An in-memory stand-in for the three driver entry points the CLI
    calls: databases are GraphData values keyed by name; load() records
    every write, dump_db()/read_graph() serve a fresh copy."""

    def __init__(self):
        self.databases = {}       # database name -> GraphData
        self.load_calls = []      # ordered database names written

    def load(self, graph, config):
        name = config["NEO4J_DATABASE"]
        self.load_calls.append(name)
        self.databases[name] = clone(graph)
        return {"loaded_nodes": len(graph.nodes),
                "loaded_edges": len(graph.edges),
                "nodes_by_label": {}, "edges_by_type": {}}

    def dump_db(self, config):
        name = config["NEO4J_DATABASE"]
        if name not in self.databases:
            raise RuntimeError(f"no such database '{name}'")
        return clone(self.databases[name])

    def read_graph(self, config):
        return self.dump_db(config)


@pytest.fixture
def driven_kb(tmp_path, monkeypatch):
    """A storybook KB with canon exported, the fake driver wired into the
    three CLI entry points, and the default line's durable artifacts
    snapshotted. Returns (base_dir, fake, canon_snapshot)."""
    base = tmp_path / "kb"
    shutil.copytree(STORYBOOK, base)
    canon = build_canon()
    export_mod.write_export(canon, export_dir(base))

    fake = FakeDBMS()
    monkeypatch.setattr("graph.load.load", fake.load)
    monkeypatch.setattr("graph.restore.dump_db", fake.dump_db)
    monkeypatch.setattr("graph.delta.read_graph", fake.read_graph)

    def canon_snapshot():
        # the default LINE's durable artifacts only — export + proposals +
        # event log; transient graph/reports/ is not canon.
        files = {}
        for root in (export_dir(base), proposals_dir(base)):
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    files[p] = p.read_bytes()
        files["__log__"] = read_applied_log(base)
        return files

    return base, fake, canon_snapshot


def test_full_branch_round_driven_through_the_cli(driven_kb, capsys):
    base, fake, canon_snapshot = driven_kb
    branch = "rebuild"
    canon_before = canon_snapshot()

    # 1. cut the branch through the CLI: schema-only seed loaded into the
    #    branch database, its backup born, its base pinned.
    assert main_mod.cmd_restore(base, branch=branch, base="schema-only") == 0
    assert fake.load_calls == [branch]            # only the branch db written
    assert (export_dir(base, branch) / "nodes.jsonl").exists()
    assert (current_dir(base, branch) / BASE_FILE).exists()
    branch_export_after_cut = (
        export_dir(base, branch) / "nodes.jsonl").read_bytes()

    # 2. re-cut is REFUSED by name; the committed branch work is intact
    #    (no truncation, no second load).
    assert main_mod.cmd_restore(base, branch=branch, base="schema-only") == 1
    assert "already exists" in capsys.readouterr().err
    assert fake.load_calls == [branch]            # nothing re-loaded
    assert (export_dir(base, branch) / "nodes.jsonl").read_bytes() \
        == branch_export_after_cut

    # 3. author three ground facts into the branch's authoring copy
    #    (<name>-scratch) — what an agent session leaves in scratch.
    seed = read_export(export_dir(base, branch))
    authored = clone(seed)
    authored.ensure_node("Character", "Ember", temperament="bright")
    authored.ensure_node("Place", "Hearth")
    authored.edges.append(
        make_edge("LIVES_IN", "Character", "Ember", "Place", "Hearth"))
    fake.databases[f"{branch}-scratch"] = authored

    # 4. delta -> approve -> canonize --apply, each through the CLI
    assert main_mod.cmd_delta(base, None, branch=branch) == 0
    assert (current_dir(base, branch) / "delta.json").exists()
    assert main_mod.cmd_approve(base, "owner", branch=branch) == 0
    assert (current_dir(base, branch) / APPROVAL_FILE).exists()
    loads_before_apply = list(fake.load_calls)
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0

    # 5. the three facts landed in the branch home: its backup carries
    #    Ember, its event log is chained, its round is archived.
    assert fake.load_calls == loads_before_apply + [branch]  # branch db only
    branch_canon = read_export(export_dir(base, branch))
    assert ("Character", "Ember") in branch_canon.nodes
    assert ("Place", "Hearth") in branch_canon.nodes
    assert applied_log_path(base, branch).exists()
    assert verify_applied_log(base, branch) == []
    [(seq, *_rest)] = read_applied_log(base, branch)
    assert seq == 1
    # the round archived under the branch's proposals, current/ drained
    archives = [p for p in (proposals_dir(base, branch)).iterdir()
                if p.is_dir() and p.name != "current"]
    assert archives, "the branch round did not archive"
    assert not (current_dir(base, branch) / APPROVAL_FILE).exists()

    # 6. THE ISOLATION CLAIM: the default line's durable artifacts are
    #    byte-for-byte what they were — canon's database was never loaded,
    #    its export/proposals never moved, its event log never grew.
    assert branch not in [c for c in fake.load_calls if c == "neo4j"]
    assert "neo4j" not in fake.load_calls        # live canon never written
    assert canon_snapshot() == canon_before


def test_canonize_guard_fires_before_any_write_over_the_cli(driven_kb, capsys):
    base, fake, _ = driven_kb

    # a branch NAMED like live canon: refused before any database write
    assert main_mod.cmd_canonize(base, None, apply=True, branch="neo4j") == 1
    err = capsys.readouterr().err
    assert "hard-isolated from canon" in err and "neo4j" in err
    assert fake.load_calls == []                  # nothing written

    # a branch reading live canon AS its authoring source: also refused
    assert main_mod.cmd_canonize(base, "neo4j", apply=True,
                                 branch="rebuild") == 1
    assert "authoring source" in capsys.readouterr().err
    assert fake.load_calls == []                  # still nothing written


def test_restore_branch_rejects_database_alias_over_the_cli(driven_kb,
                                                            capsys):
    base, fake, _ = driven_kb
    # a branch's database IS its name — --database is refused outright,
    # before any write, and no branch home is created.
    assert main_mod.cmd_restore(base, branch="rebuild", base="schema-only",
                                database="sandbox") == 1
    assert "no aliases" in capsys.readouterr().err
    assert fake.load_calls == []
    assert not branch_home(base, "rebuild").exists()
