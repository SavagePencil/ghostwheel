"""A spent line retires by the owner's word, and the record stands.

`branch <name> --retire --by <owner>` closes a line whose every round
canon has taken up (or one that never landed a round): the home stays
whole and gains retired.json — who ruled, when, the canon sequence it
closed at — the line's databases drop through the admin road, further
rounds refuse citing the word, and the roster hides retired lines
unless asked. Work that has not crossed refuses collated: merge first;
abandonment is a different act, unbuilt on purpose.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph import connections
from graph.extract import make_edge
from graph.pockets import CLONE_OF_CANON, RETIRED_MARKER, read_retirement
from graph.proposal import branch_home
from graph.restore import read_export
from tests.test_branch import clone, driven_kb, export_dir  # noqa: F401
from tests.test_connections import FakeSystem
from tests.test_succession import _mount_live_canon

POCKET = "maren-sketches"


def _cut_pocket(base):
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0


def _land_pocket_round(base, fake):
    authored = clone(read_export(export_dir(base, POCKET)))
    authored.ensure_node("Place", "Hearth")
    fake.databases[f"{POCKET}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0


def _take_up(base, fake):
    """Canon merges the pocket's rounds, so they read as crossed."""
    _mount_live_canon(base, fake)
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0


def _spent(base, fake, monkeypatch):
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    _cut_pocket(base)
    _land_pocket_round(base, fake)
    _take_up(base, fake)
    return system


def test_a_spent_pocket_retires_whole(driven_kb, monkeypatch, capsys):
    base, fake, _ = driven_kb
    system = _spent(base, fake, monkeypatch)
    system.statements.clear()
    capsys.readouterr()
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0
    out = capsys.readouterr().out
    assert "retired" in out.lower() and "James Clarendon" in out
    record = read_retirement(base, POCKET)
    assert record is not None
    assert record["retired_by"] == "James Clarendon"
    assert record["rounds_taken_up"]
    assert (branch_home(base, POCKET) / RETIRED_MARKER).exists()
    # the record stands whole beside the marker
    assert (branch_home(base, POCKET) / "export").is_dir()
    # the line's databases dropped through the admin road, idempotently
    drops = [s for s in system.statements if s.startswith("DROP DATABASE")]
    assert any(f"`{POCKET}`" in s and "IF EXISTS" in s for s in drops)
    assert any(f"`{POCKET}-scratch`" in s for s in drops)


def test_uncrossed_work_refuses_collated(driven_kb, monkeypatch, capsys):
    base, fake, _ = driven_kb
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    _cut_pocket(base)
    _land_pocket_round(base, fake)  # never taken up
    capsys.readouterr()
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 1
    err = capsys.readouterr().err
    assert "Failed due to" in err and "merge first" in err.lower()
    assert not (branch_home(base, POCKET) / RETIRED_MARKER).exists()
    assert system.statements == []  # nothing dropped


def test_an_empty_line_retires_and_by_is_required(
        driven_kb, monkeypatch, capsys):
    base, fake, _ = driven_kb
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    _cut_pocket(base)
    capsys.readouterr()
    assert main_mod.cmd_branch(base, POCKET, retire=True) == 1
    assert "--by" in capsys.readouterr().err
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0


def test_further_rounds_refuse_citing_the_word(
        driven_kb, monkeypatch, capsys):
    base, fake, _ = driven_kb
    _spent(base, fake, monkeypatch)
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0
    capsys.readouterr()
    assert main_mod.cmd_restore(base, branch=POCKET,
                                base=CLONE_OF_CANON) == 1
    err = capsys.readouterr().err
    assert "retired" in err and "James Clarendon" in err
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 1
    assert "retired" in capsys.readouterr().err


def test_the_roster_hides_retired_unless_asked(
        driven_kb, monkeypatch, capsys):
    base, fake, _ = driven_kb
    _spent(base, fake, monkeypatch)
    assert main_mod.cmd_branch(base, POCKET, retire=True,
                               by="James Clarendon") == 0
    capsys.readouterr()
    assert main_mod.cmd_branches(base) == 0
    assert POCKET not in capsys.readouterr().out
    assert main_mod.cmd_branches(base, all_lines=True) == 0
    out = capsys.readouterr().out
    assert POCKET in out and "retired" in out


def test_the_roster_names_its_quantities_honestly(driven_kb, monkeypatch,
                                                  capsys):
    # a line's own landed-rounds count and canon's log sequence are two
    # quantities; the roster stops printing both under one word
    base, fake, _ = driven_kb
    system = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: system)
    _cut_pocket(base)
    _land_pocket_round(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_branches(base) == 0
    out = capsys.readouterr().out
    assert "rounds landed 1" in out
    assert "from canon at sequence" in out
