"""Names on a shared DBMS.

Several knowledge bases share one DBMS. Every database the engine
creates already says what it is in-band; now the stamp also says WHICH
knowledge base it belongs to, and the stamps together are the DBMS's
registry of names: every load reads the target's stamp first, and a
database another knowledge base holds refuses by name before a byte is
written. An unstamped database, an older engine's stamp, or this
knowledge base's own proceeds as ever. A knowledge base is born with
its own names: `init` writes its settings naming the canon database
after the knowledge base and the working copy `<kb>-scratch`.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph import refs as refs_mod
from graph.__main__ import _authoring_database, default_database_name
from graph.extract import GraphData
from graph.load import read_config
from graph.proposal import branch_home
from graph.report import record_path
from graph.restore import read_export
from graph.workspace import held_by_problem
from tests.test_branch import driven_kb, export_dir  # noqa: F401
from tests.test_succession import _author_and_canonize_branch


def _kb(base):
    return refs_mod.kb_name(read_export(export_dir(base)), base)


def _stamp(fake, name):
    return fake.read_stamp({"NEO4J_DATABASE": name})


# -- the judge -------------------------------------------------------------


def test_only_another_knowledge_base_s_stamp_is_a_problem():
    assert held_by_problem(None, "hearth", "scratch") is None
    older = {"role": "working-copy", "base_hash": "abc"}
    assert held_by_problem(older, "hearth", "scratch") is None
    own = {"role": "canon", "base_hash": "abc", "kb": "hearth"}
    assert held_by_problem(own, "hearth", "hearth") is None
    theirs = {"role": "branch", "base_hash": "abc", "kb": "ember"}
    problem = held_by_problem(theirs, "hearth", "rebuild")
    assert problem is not None
    assert "load knowledge base 'hearth' into database 'rebuild'" in problem
    assert "knowledge base 'ember''s branch" in problem
    assert "Nothing is renamed" in problem


# -- every creation path stamps its knowledge base -------------------------


def test_every_creation_path_stamps_its_knowledge_base(driven_kb):
    base, fake, _ = driven_kb
    kb = _kb(base)
    assert main_mod.cmd_restore(base) == 0
    assert _stamp(fake, "neo4j")["kb"] == kb
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert _stamp(fake, "scratch")["kb"] == kb
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 0
    assert _stamp(fake, "rebuild")["kb"] == kb
    # a round applied on the branch re-stamps the branch's database
    _author_and_canonize_branch(base, fake, "orchard")
    assert _stamp(fake, "orchard")["kb"] == kb
    assert _stamp(fake, "orchard")["role"] == "branch"


# -- the registry refuses --------------------------------------------------


def test_a_database_another_knowledge_base_holds_refuses_before_any_write(
        driven_kb, capsys):
    base, fake, snapshot = driven_kb
    kb = _kb(base)
    fake.stamp({"NEO4J_DATABASE": "scratch"}, "working-copy", "abc",
               kb="ember")
    before = snapshot()
    calls = list(fake.load_calls)
    capsys.readouterr()
    assert main_mod.cmd_restore(base, database="scratch") == 1
    err = capsys.readouterr().err
    assert f"load knowledge base '{kb}' into database 'scratch'" in err
    assert "knowledge base 'ember''s working-copy" in err
    assert fake.load_calls == calls and snapshot() == before
    record = json.loads(record_path(base, "restore-report.json")
                        .read_text(encoding="utf-8"))
    assert record["code"] == "restore-guard"
    assert "ember" in record["problems"][0]
    # a branch of the same name another knowledge base already cut
    fake.stamp({"NEO4J_DATABASE": "rebuild"}, "branch", "abc",
               branch="rebuild", kb="ember")
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 1
    assert "knowledge base 'ember''s branch" in capsys.readouterr().err
    assert not branch_home(base, "rebuild").exists()
    assert fake.load_calls == calls


def test_an_unstamped_or_own_database_proceeds(driven_kb):
    base, fake, _ = driven_kb
    kb = _kb(base)
    fake.databases["scratch"] = GraphData()  # made by hand, unstamped
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert _stamp(fake, "scratch")["kb"] == kb
    # this knowledge base's own: re-cutting is ordinary
    assert main_mod.cmd_restore(base, database="scratch") == 0
    # an older engine's stamp names no knowledge base: let through
    fake.stamp({"NEO4J_DATABASE": "old"}, "working-copy", "abc")
    assert main_mod.cmd_restore(base, database="old") == 0
    assert _stamp(fake, "old")["kb"] == kb


# -- born with its own names -----------------------------------------------


def test_init_names_the_new_knowledge_base_s_databases(tmp_path, capsys):
    target = tmp_path / "hearth"
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    assert "NEO4J_DATABASE=hearth\n" in env
    assert "NEO4J_SCRATCH_DATABASE=hearth-scratch\n" in env
    config = read_config(target)
    assert config["NEO4J_DATABASE"] == "hearth"
    assert _authoring_database(None, None, config) == "hearth-scratch"
    out = capsys.readouterr().out
    assert "canon database 'hearth', working copy 'hearth-scratch'" in out
    assert "restore --database hearth-scratch" in out
    # existing settings are never overwritten
    other = tmp_path / "ember"
    other.mkdir()
    (other / ".env").write_text("NEO4J_DATABASE=mine\n", encoding="utf-8")
    assert main_mod.cmd_init(other) == 0
    assert (other / ".env").read_text(encoding="utf-8") == \
        "NEO4J_DATABASE=mine\n"
    assert "kept as-is" in capsys.readouterr().out


def test_default_database_names_take_the_shape_a_dbms_accepts():
    assert default_database_name("Tale of the Hearth") == \
        "tale-of-the-hearth"
    assert default_database_name("ember_hearth") == "ember-hearth"
    assert default_database_name("---") == "canon"
