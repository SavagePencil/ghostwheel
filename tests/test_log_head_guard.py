"""The chain's head against the backup it builds on.

Every verb that appends to the event log first checks that the log's
last entry left the base the backup now IS (base_after equals the
backup's identity) and that the backup's anchor carries that entry's
sequence. A log behind its backup — a line lost to bookkeeping — would
otherwise chain the next entry off a stale predecessor: a duplicate
sequence, a prev_chain skipping a real round, silent corruption of the
tamper-evident chain. The disagreement refuses by name, both heads
shown, before any write: at canonize --apply (advisory on the dry
run), at kernel-migrate, and as two succession gates.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph.extract import GraphData
from graph.proposal import (applied_log_path, base_identity,
                            log_head_divergence, read_applied_log)
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import clone, driven_kb  # noqa: F401
from tests.test_branch import export_dir
from tests.test_succession import _author_and_canonize_branch, _mount_live_canon


def _graph(version=None):
    g = GraphData()
    props = {"doc": "anchor"}
    if version is not None:
        props["version"] = version
    g.ensure_node("Archetype", "Ontology", **props)
    g.ensure_node("Blade", "Falchion", reach="martial")
    return g


def _log_line(base_dir, seq, base_after, prev="genesis"):
    path = applied_log_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{seq} deadbeef {'0' * 8} {base_after} {prev} "
                     f"{'c' * 12}\n")


# -- the check itself -------------------------------------------------------


def test_an_empty_log_is_judged_by_nothing(tmp_path):
    # a bootstrap version on the anchor is not a sequence
    assert log_head_divergence(tmp_path, _graph(version="1")) is None
    assert log_head_divergence(tmp_path, _graph()) is None


def test_a_log_in_step_passes(tmp_path):
    graph = _graph(version=2)
    _log_line(tmp_path, 1, "x" * 64)
    _log_line(tmp_path, 2, base_identity(graph), prev="c" * 12)
    assert log_head_divergence(tmp_path, graph) is None


def test_a_log_behind_its_backup_names_both_heads(tmp_path):
    graph = _graph(version=2)
    _log_line(tmp_path, 1, "x" * 64)  # round 2's line was lost
    problem = log_head_divergence(tmp_path, graph)
    assert problem is not None
    assert "graph/proposals/applied.log" in problem
    assert "round 1" in problem and "left the base at xxxxxxxxxxxx" in problem
    assert f"identity is {base_identity(graph)[:12]}" in problem
    assert "the backup's anchor says round 2 was applied" in problem
    assert "corrupt the tamper-evident chain" in problem
    # identity alone, when the anchor carries no sequence
    problem = log_head_divergence(tmp_path, _graph())
    assert problem is not None and "anchor says" not in problem


def test_the_codes_carry_designer_safe_refs():
    for code in ("log-head-diverged", "canon-log-head-diverged",
                 "branch-log-head-diverged"):
        assert REF_KEYS[code] == "history-out-of-step"


# -- the appenders refuse -------------------------------------------------


def _lose_last_line(base, branch):
    path = applied_log_path(base, branch)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(lines[:-1]), encoding="utf-8")


def _cut_and_author(base, fake, branch, name):
    """A further round on the branch: pin its base the way the cut does,
    author one citizen into its scratch, run delta and approve."""
    current = read_export(export_dir(base, branch))
    main_mod.pin_round(base, current, f"{branch}-scratch", branch)
    authored = clone(current)
    authored.ensure_node("Place", name)
    fake.databases[f"{branch}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=branch) == 0
    assert main_mod.cmd_approve(base, "owner", branch=branch) == 0
    return current


def test_canonize_refuses_when_the_log_is_behind_the_backup(driven_kb,
                                                            capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _cut_and_author(base, fake, branch, "Orchard")
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0
    assert len(read_applied_log(base, branch)) == 2
    _lose_last_line(base, branch)  # round 2's line, lost to bookkeeping
    before = _cut_and_author(base, fake, branch, "Mill")
    capsys.readouterr()
    # the dry run advises, the apply refuses — nothing written either way
    assert main_mod.cmd_canonize(base, None, apply=False, branch=branch) == 0
    assert "Advisory: the event log" in capsys.readouterr().err
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 1
    err = capsys.readouterr().err
    assert "--apply refused — the event log" in err
    assert "disagrees with the backup it would build on" in err
    assert read_export(export_dir(base, branch)).nodes == before.nodes
    assert len(read_applied_log(base, branch)) == 1
    record = json.loads(record_path(base, "canonize-refusal.json")
                        .read_text(encoding="utf-8"))
    assert record["refusals"][0]["code"] == "log-head-diverged"
    assert record["refusals"][0]["ref"] == "history-out-of-step"


def test_succession_gates_name_a_line_out_of_step(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _cut_and_author(base, fake, branch, "Orchard")
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0
    _mount_live_canon(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=branch, apply=False) == 0
    out = capsys.readouterr().out
    assert "event log agrees with its backup" in out
    _lose_last_line(base, branch)
    assert main_mod.cmd_succession(base, branch=branch, apply=False) == 1
    captured = capsys.readouterr()
    assert f"branch '{branch}''s event log agrees with its backup" in \
        captured.out + captured.err
    assert "disagrees with the backup it would build on" in \
        captured.out + captured.err
