"""Merge — the fifth job: one line takes up another's rounds while
both persist.

A pocket and the canon it forked from each land rounds. `merge --from
<line> --into <line>` reconciles them three-way at citizen grain from
the fork: rounds only one side touched replay mechanically into the
target's fresh working copy; citizens changed on both lines stay at the
target's version and are listed base / yours / theirs. The merge
prepares the target's ORDINARY round — delta, approve, canonize --apply
land it — and at apply the target's log records the rounds taken up, so
a second merge skips them and succession's divergence advisory does not
re-list them. Both directions.

Storybook domain, over the driven-kb harness: Maren's pocket and canon
both move Pip's temperament; each adds a citizen of its own.
"""

import json

import graph.__main__ as main_mod
from graph.merge import REPORT_FILE, touched
from graph.pockets import CLONE_OF_CANON
from graph.proposal import (MERGE_FILE, current_dir, proposals_dir,
                            read_applied_log, read_merged_annotations)
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from graph.succession import post_fork_rounds
from tests.test_branch import clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _live_canon_name, _mount_live_canon

POCKET = "maren-sketches"


def _cut_pocket(base):
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren", invite=["Pip"]) == 0


def _land_pocket_round(base, fake, edit):
    authored = clone(read_export(export_dir(base, POCKET)))
    edit(authored)
    fake.databases[f"{POCKET}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0


def _land_canon_round(base, fake, edit):
    _mount_live_canon(base, fake)
    authored = clone(read_export(export_dir(base)))
    edit(authored)
    fake.databases["scratch"] = authored
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0


def _diverge(base, fake):
    """Both lines move since the fork: each adds a citizen of its own
    (disjoint) and both change Pip's temperament (contested)."""
    _cut_pocket(base)

    def pocket_edit(graph):
        graph.ensure_node("Character", "Ember", temperament="bright")
        graph.nodes[("Character", "Pip")]["temperament"] = "bold"

    def canon_edit(graph):
        graph.ensure_node("Place", "Hearth")
        graph.nodes[("Character", "Pip")]["temperament"] = "brave"

    _land_pocket_round(base, fake, pocket_edit)
    _land_canon_round(base, fake, canon_edit)


def _fresh_canon_copy(base, fake):
    assert main_mod.cmd_restore(base, database="scratch") == 0


def _fresh_pocket_copy(base, fake):
    assert main_mod.cmd_restore(
        base, database=f"{POCKET}-scratch",
        from_dir=str(export_dir(base, POCKET))) == 0


def _report(base):
    return json.loads(record_path(base, REPORT_FILE)
                      .read_text(encoding="utf-8"))


# -- the reconciliation ---------------------------------------------------


def test_touched_names_every_subject_a_changeset_moves():
    from graph.delta import Delta
    from graph.extract import make_edge
    delta = Delta(nodes_added=[("Place", "Hearth", {})],
                  nodes_changed=[("Character", "Pip", {"t": ("a", "b")})],
                  edges_added=[make_edge("LIVES_IN", "Character", "Pip",
                                         "Place", "Hearth")])
    nodes, edges = touched(delta)
    assert nodes == {("Place", "Hearth"), ("Character", "Pip")}
    assert edges == {("LIVES_IN", "Character", "Pip", "Place", "Hearth")}


# -- landing a pocket's work into canon ----------------------------------


def test_canon_takes_up_the_pocket_s_rounds_and_records_it(driven_kb,
                                                            capsys):
    base, fake, _ = driven_kb
    _diverge(base, fake)
    _fresh_canon_copy(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    out = capsys.readouterr().out
    assert "Merge from maren-sketches into canon" in out
    assert "taken up   round 1" in out
    assert "Contested (1)" in out and "(Character) Pip" in out
    assert "yours:  {'temperament': 'brave'}" in out
    assert "theirs: {'temperament': 'bold'}" in out
    # the replay landed in canon's working copy; Pip stays canon's
    copy = fake.databases["scratch"]
    assert ("Character", "Ember") in copy.nodes
    assert copy.nodes[("Character", "Pip")]["temperament"] == "brave"
    stamp = fake.read_stamp({"NEO4J_DATABASE": "scratch"})
    assert stamp["role"] == "working-copy"
    # the report and the round's record
    doc = _report(base)
    assert doc["kind"] == "merge-report" and doc["from"] == POCKET
    [contested] = doc["contested"]
    assert contested["subject"]["name"] == "Pip"
    assert contested["base"] == {"props": {"temperament": "curious"},
                                 "partial": True}
    assert contested["yours"] == {"temperament": "brave"}
    assert contested["theirs"] == {"temperament": "bold"}
    assert contested["ref"] == "changed-on-both-lines"
    assert doc["round_rows"][0]["ref"] == "taken-up"
    assert (current_dir(base) / MERGE_FILE).exists()
    pocket_round = read_applied_log(base, POCKET)[0][1]
    assert doc["rounds"] == [pocket_round]
    # the round lands like any other, the contested citizen an advisory
    assert main_mod.cmd_delta(base, None) == 0
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [row["code"] for row in report["advisories"]] == \
        ["merge-contested"]
    assert REF_KEYS["merge-contested"] == "changed-on-both-lines"
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    canon = read_export(export_dir(base))
    assert ("Character", "Ember") in canon.nodes
    assert canon.nodes[("Character", "Pip")]["temperament"] == "brave"
    # the merge record archived with the round; the log annotated
    delta_hash = read_applied_log(base)[-1][1]
    archive = proposals_dir(base) / delta_hash[:12]
    assert (archive / MERGE_FILE).exists()
    assert not (current_dir(base) / MERGE_FILE).exists()
    [annotation] = read_merged_annotations(base)
    assert annotation["from"] == POCKET
    assert annotation["rounds"] == [pocket_round]
    assert annotation["contested"] == 1
    # a second merge has nothing to take up
    _fresh_canon_copy(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    assert "Nothing to take up" in capsys.readouterr().out
    assert not (current_dir(base) / MERGE_FILE).exists()


# -- a pocket refreshing from canon --------------------------------------


def test_a_pocket_takes_up_canon_s_rounds_and_succession_knows(driven_kb,
                                                                capsys):
    base, fake, _ = driven_kb
    _diverge(base, fake)
    _fresh_pocket_copy(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_merge(base, "canon", POCKET) == 0
    out = capsys.readouterr().out
    assert "Merge from canon into maren-sketches" in out
    copy = fake.databases[f"{POCKET}-scratch"]
    assert ("Place", "Hearth") in copy.nodes
    assert copy.nodes[("Character", "Pip")]["temperament"] == "bold"
    assert copy.nodes[("Character", "Ember")]["temperament"] == "bright"
    doc = _report(base)
    [contested] = doc["contested"]
    assert contested["yours"] == {"temperament": "bold"}
    assert contested["theirs"] == {"temperament": "brave"}
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0
    pocket = read_export(export_dir(base, POCKET))
    assert ("Place", "Hearth") in pocket.nodes
    canon_round = read_applied_log(base)[-1][1]
    [annotation] = read_merged_annotations(base, POCKET)
    assert annotation["from"] == "canon" and annotation["rounds"] == \
        [canon_round]
    # succession's divergence advisory no longer lists the round that
    # rode across
    fork_known, rounds = post_fork_rounds(base, POCKET)
    assert fork_known and rounds == []
    _mount_live_canon(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=POCKET, apply=False) == 0
    assert "no rounds landed on the line being superseded" in \
        capsys.readouterr().out


# -- refusals ---------------------------------------------------------------


def test_merge_refuses_by_name_where_it_cannot_reconcile(driven_kb, capsys):
    base, fake, _ = driven_kb
    capsys.readouterr()
    assert main_mod.cmd_merge(base, "canon", "canon") == 1
    assert "cannot take up its own rounds" in capsys.readouterr().err
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 0
    _fresh_canon_copy(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_merge(base, "rebuild", "canon") == 1
    assert "a rebuild line, not a pocket" in capsys.readouterr().err
    _cut_pocket(base)
    assert main_mod.cmd_restore(base, branch="other", base=CLONE_OF_CANON,
                                by="Pip") == 0
    assert main_mod.cmd_merge(base, POCKET, "other") == 1
    assert "two branches share no fork point" in capsys.readouterr().err
    # a working copy that already differs from its base refuses
    _fresh_canon_copy(base, fake)
    fake.databases["scratch"].ensure_node("Place", "Mill")
    assert main_mod.cmd_merge(base, POCKET, "canon") == 1
    assert "a merge wants a fresh copy" in capsys.readouterr().err


def test_a_prepared_merge_is_discarded_with_the_copy_it_landed_in(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    _diverge(base, fake)
    _fresh_canon_copy(base, fake)
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    assert (current_dir(base) / MERGE_FILE).exists()
    capsys.readouterr()
    _fresh_canon_copy(base, fake)  # re-cut: the replay is gone with it
    assert "a merge prepared from maren-sketches was discarded" in \
        capsys.readouterr().out
    assert not (current_dir(base) / MERGE_FILE).exists()
    assert ("Character", "Ember") not in fake.databases["scratch"].nodes
