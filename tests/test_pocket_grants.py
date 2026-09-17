"""A pocket is born inside the boundary: the grants follow the cut.

The physical boundary is the writer role's whole point — authoring
rides the writer user, never admin. A pocket is the standing authoring
surface, so the cut extends the line's own roles over the pocket's
databases in the main pair's exact shape (the pocket canon reads like
canon, the pocket scratch writes like scratch), and retirement revokes
before it drops. A knowledge base whose settings name no users has no
boundary to extend — the cut says nothing and grants nothing.

Storybook domain, over the driven-kb harness.
"""

import graph.__main__ as main_mod
from graph import connections
from graph.pockets import CLONE_OF_CANON
from tests.test_branch import driven_kb  # noqa: F401
from tests.test_connections import FakeSystem
from tests.test_retirement import _mount_live_canon  # noqa: F401
from graph.pockets import CLONE_OF_CANON as _CLONE
from graph.restore import read_export
from tests.test_branch import clone, export_dir


def _land_named_round(base, fake):
    """The retirement helper, staged at the DERIVED copy name (the KB's
    scratch setting rules the branch copy's name)."""
    authored = clone(read_export(export_dir(base, POCKET)))
    authored.ensure_node("Place", "Hearth")
    fake.databases[f"{POCKET}-tale-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True,
                                 branch=POCKET) == 0


def _spent_named(base, fake, monkeypatch):
    from tests.test_succession import _mount_live_canon as mount
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    assert main_mod.cmd_restore(base, branch=POCKET, base=_CLONE,
                                by="Maren") == 0
    _land_named_round(base, fake)
    mount(base, fake)
    assert main_mod.cmd_restore(base, database="tale-scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    return system

POCKET = "maren-sketches"


def _named_users(base, scratch="tale-scratch"):
    (base / ".env").write_text(
        "NEO4J_READER_USERNAME=tale-reader\n"
        "NEO4J_WRITER_USERNAME=tale-writer\n"
        f"NEO4J_SCRATCH_DATABASE={scratch}\n", encoding="utf-8")


def test_the_cut_extends_the_roles_over_the_pocket(driven_kb, monkeypatch):
    base, fake, _ = driven_kb
    _named_users(base)
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0
    grants = [s for s in system.statements if s.startswith("GRANT")]
    assert f"GRANT ACCESS ON DATABASE `{POCKET}` " \
           "TO `tale_reader_role`" in grants
    assert f"GRANT MATCH {{*}} ON GRAPH `{POCKET}` " \
           "TO `tale_reader_role`" in grants
    copy = f"{POCKET}-tale-scratch"  # the KB's own scratch setting rules
    assert f"GRANT ACCESS ON DATABASE `{copy}` " \
           "TO `tale_writer_role`" in grants
    assert f"GRANT WRITE ON GRAPH `{copy}` " \
           "TO `tale_writer_role`" in grants
    assert f"GRANT NAME MANAGEMENT ON DATABASE `{copy}` " \
           "TO `tale_writer_role`" in grants
    # the plan creates what it grants on, idempotently
    assert any(s.startswith(f"CREATE DATABASE `{copy}` IF NOT")
               for s in system.statements)
    # the bare default name is NOT granted — the setting rules
    assert not any(f"`{POCKET}-scratch`" in s for s in grants)


def test_retirement_revokes_before_it_drops(driven_kb, monkeypatch,
                                            capsys):
    base, fake, _ = driven_kb
    _named_users(base)
    system = _spent_named(base, fake, monkeypatch)
    system.statements.clear()
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0
    revokes = [i for i, s in enumerate(system.statements)
               if s.startswith("REVOKE")]
    drops = [i for i, s in enumerate(system.statements)
             if s.startswith("DROP DATABASE")]
    assert revokes and drops
    assert max(revokes) < min(drops)
    assert any(f"`{POCKET}-tale-scratch`" in system.statements[i]
               and "tale_writer_role" in system.statements[i]
               for i in revokes)
    # the drops sweep the derived name AND the bare default (IF EXISTS
    # is free, and the bug's own minted names get swept up)
    dropped = " ".join(system.statements[i] for i in drops)
    assert f"`{POCKET}-tale-scratch`" in dropped
    assert f"`{POCKET}-scratch`" in dropped


def test_a_kb_without_named_users_cuts_in_silence(driven_kb, monkeypatch,
                                                 capsys):
    base, fake, _ = driven_kb
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    capsys.readouterr()
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0
    assert [s for s in system.statements if s.startswith("GRANT")] == []
    assert "grant" not in capsys.readouterr().out.lower()


def test_an_unreachable_dbms_notes_plainly_and_proceeds(driven_kb,
                                                        monkeypatch,
                                                        capsys):
    base, fake, _ = driven_kb
    _named_users(base)

    def refuse(config):
        raise RuntimeError("no route to the DBMS")
    monkeypatch.setattr(connections, "_system_runner", refuse)
    capsys.readouterr()
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0
    out = capsys.readouterr().out
    assert "Note:" in out and "grant" in out.lower()


def test_a_failed_revoke_never_aborts_the_drops(driven_kb, monkeypatch,
                                                capsys):
    base, fake, _ = driven_kb
    _named_users(base)
    system = _spent_named(base, fake, monkeypatch)

    class RefusesRevokes:
        def __init__(self, inner):
            self.inner = inner

        def run(self, statement):
            if statement.startswith("REVOKE"):
                raise RuntimeError("no such database")
            self.inner.run(statement)
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: RefusesRevokes(system))
    system.statements.clear()
    capsys.readouterr()
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0
    out = capsys.readouterr().out
    # every drop still ran
    drops = [s for s in system.statements if s.startswith("DROP DATABASE")]
    assert len(drops) >= 2
    # the failures are named honestly, and the remedy points at the
    # designer's own eyes, never an assumed name
    assert "REVOKE" in out and "SHOW DATABASES" in out
