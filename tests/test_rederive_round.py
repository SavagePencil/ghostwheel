"""rederive is a first-class round: the derived-layer refresh.

After an engine change moves a derive pass (or a ceremony reshapes the
schema), canon's committed backup carries derived rows the installed
engine would no longer produce. The refresh re-derives from the backup
against the schema the graph carries: the dry run prints what leaves
and arrives (the owner's gate report) and writes nothing; --apply
stamps the anchor with the next sequence, loads, reads back
byte-identical, re-exports, chains the round's record into the event
log, and archives it — so the chain-head guard, which every appender
runs, sees a log that agrees with its backup. Ground never moves here.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.extract import make_edge
from graph.ontology import ARCHETYPE_LABEL
from graph.proposal import (APPLIED_FILE, REDERIVE_FILE, applied_log_path,
                            base_identity, log_head_divergence,
                            proposals_dir, read_applied_log)
from graph.restore import read_export
from tests.test_branch import driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon


def _plant_stale_derived_edge(base):
    """A derived row the installed engine would never produce again:
    a MENTIONS edge between two citizens, as an older derive pass might
    have left it."""
    canon = read_export(export_dir(base))
    (label_a, name_a), (label_b, name_b) = [
        key for key in sorted(canon.nodes, key=str)
        if key[0] != ARCHETYPE_LABEL][:2]
    stale = make_edge("MENTIONS", label_a, name_a, label_b, name_b)
    assert stale not in canon.edges
    canon.edges.append(stale)
    export_mod.write_export(canon, export_dir(base))
    return stale


def test_the_dry_run_names_what_leaves_and_writes_nothing(driven_kb,
                                                          capsys):
    base, fake, snapshot = driven_kb
    stale = _plant_stale_derived_edge(base)
    before = snapshot()
    capsys.readouterr()
    assert main_mod.cmd_rederive(base) == 0
    out = capsys.readouterr().out
    assert "Derived-layer refresh against engine" in out
    assert "edges leaving (1):" in out
    assert f"-[:MENTIONS]-> ({stale.to_label}) {stale.to_name}" in out
    assert "ground layer: unchanged." in out
    assert "Dry run: nothing written." in out
    assert snapshot() == before
    assert read_applied_log(base) == []


def test_apply_refreshes_as_a_chained_round(driven_kb, capsys):
    base, fake, _ = driven_kb
    stale = _plant_stale_derived_edge(base)
    _mount_live_canon(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_rederive(base, apply=True) == 0
    out = capsys.readouterr().out
    assert "Refreshed canon's derived layers against engine" in out
    assert "Round archived:" in out and "record rides with it" in out
    canon = read_export(export_dir(base))
    assert stale not in canon.edges
    # the anchor carries the round's sequence and the log agrees with
    # the backup: the next appender's chain-head guard passes
    [entry] = read_applied_log(base)
    assert entry[0] == 1
    assert canon.nodes[(ARCHETYPE_LABEL, "Ontology")]["version"] == 1
    assert entry[3] == base_identity(canon)
    assert log_head_divergence(base, canon) is None
    # the record rides in the archive, naming the engine and the diff
    archive = proposals_dir(base) / entry[1][:12]
    record = json.loads((archive / REDERIVE_FILE).read_text("utf-8"))
    assert record["kind"] == "rederive-report" and record["sequence"] == 1
    assert record["engine"] == main_mod.engine_version()
    [left] = record["edges_left"]
    assert left["type"] == "MENTIONS"
    assert left["to"]["name"] == stale.to_name
    assert record["edges_arrived"] == []
    applied = json.loads((archive / APPLIED_FILE).read_text("utf-8"))
    assert applied["applied"] == "derived-layer-refresh"
    assert not (proposals_dir(base) / "current" / REDERIVE_FILE).exists()
    # a second refresh has nothing left to do
    assert main_mod.cmd_rederive(base, apply=True) == 0
    assert "nothing to refresh" in capsys.readouterr().out
    assert len(read_applied_log(base)) == 1


def test_apply_refuses_over_an_in_flight_round_and_a_log_out_of_step(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    _plant_stale_derived_edge(base)
    _mount_live_canon(base, fake)
    # a round in flight pins its base: the refresh would move it
    main_mod.pin_round(base, read_export(export_dir(base)), "scratch")
    capsys.readouterr()
    assert main_mod.cmd_rederive(base, apply=True) == 1
    assert "a round is in flight" in capsys.readouterr().err
    (proposals_dir(base) / "current" / "base.json").unlink()
    # a log that disagrees with its backup refuses before anything moves
    path = applied_log_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"1 deadbeef {'0' * 8} {'x' * 64} genesis {'c' * 12}\n",
                    encoding="utf-8")
    assert main_mod.cmd_rederive(base, apply=True) == 1
    err = capsys.readouterr().err
    assert "rederive refused — the event log" in err
    assert "disagrees with the backup it would build on" in err
