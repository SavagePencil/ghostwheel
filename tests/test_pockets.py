"""Pockets: a named branch cut as a clone of canon, declared in-band.

A collaborator's own version of a knowledge base is a branch born from
canon's whole graph, hard-isolated from canon like every branch. Its
declaration — who cut it, when, who is invited, the canon identity and
sequence it forked from — lives on the branch database's identity stamp
and as a bracketed [Pocket] citizen (kernel 0.16.0) in the branch's own
graph and export; no file. The engine writes it and the invite verbs
rewrite it; nobody authors it by hand; it is set aside from the line's
content identity, so an invite change moves no chain; succession strips
it. `branches` lists the pocket roster from the backups alone.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.kernel_migrate import fresh_kernel
from graph.ontology import ARCHETYPE_LABEL, KERNEL_POCKET_LABEL
from graph.pockets import (CLONE_OF_CANON, REPORT_FILE, pocket_row,
                           strip_declarations)
from graph.proposal import base_identity, log_head_divergence, read_applied_log
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon

POCKET = KERNEL_POCKET_LABEL


def _declaration(graph, branch):
    row = pocket_row(graph, branch)
    assert row is not None, f"'{branch}' carries no declaration"
    return row


def _cut_pocket(base, name="maren-sketches", by="Maren", invite=("Pip",)):
    assert main_mod.cmd_restore(base, branch=name, base=CLONE_OF_CANON,
                                by=by, invite=list(invite)) == 0
    return read_export(export_dir(base, name))


def _land_round(base, fake, branch, node):
    authored = clone(read_export(export_dir(base, branch)))
    authored.ensure_node("Character", node, temperament="bright")
    fake.databases[f"{branch}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=branch) == 0
    assert main_mod.cmd_approve(base, "owner", branch=branch) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0


# -- the kernel declares it -------------------------------------------------


def test_the_kernel_declares_pocket_under_provenance_bracketed(tmp_path):
    seed, findings = fresh_kernel(tmp_path)
    assert seed is not None, findings
    assert POCKET == "[Pocket]"
    assert (ARCHETYPE_LABEL, POCKET) in seed.nodes
    parents = {e.to_name for e in seed.edges
               if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == (ARCHETYPE_LABEL, POCKET)}
    assert parents == {"Provenance"}


# -- the cut ----------------------------------------------------------------


def test_a_pocket_is_canon_byte_for_byte_plus_its_declaration(driven_kb,
                                                              capsys):
    base, fake, snapshot = driven_kb
    canon = read_export(export_dir(base))
    before = snapshot()
    capsys.readouterr()
    pocket = _cut_pocket(base)
    out = capsys.readouterr().out
    assert "Cutting pocket 'maren-sketches'" in out
    assert "cut by Maren, invited: Pip" in out
    # everything canon holds, plus the one declaration row
    assert set(pocket.nodes) - {(POCKET, "maren-sketches")} == set(canon.nodes)
    assert set(pocket.edges) == set(canon.edges)
    assert export_mod.serialize(strip_declarations(pocket)) == \
        export_mod.serialize(canon)
    row = _declaration(pocket, "maren-sketches")
    assert row["cut_by"] == "Maren" and row["invited"] == ["Pip"]
    assert row["base"] == CLONE_OF_CANON
    assert row["forked_from"] == base_identity(canon)
    assert row["forked_sequence"] == 0 and row["cut_at"]
    # the declaration is set aside from identity: the pocket's identity
    # IS canon's, and the branch database carries the same row
    assert base_identity(pocket) == base_identity(canon)
    assert (POCKET, "maren-sketches") in fake.databases["maren-sketches"].nodes
    stamp = fake.read_stamp({"NEO4J_DATABASE": "maren-sketches"})
    assert stamp["role"] == "branch" and stamp["pocket_cut_by"] == "Maren"
    assert stamp["pocket_invited"] == ["Pip"]
    assert stamp["pocket_forked_from"] == base_identity(canon)
    assert stamp["base_hash"] == base_identity(canon)
    # canon is untouched
    assert snapshot() == before


def test_the_cut_refuses_a_pocket_with_nobody_named_and_a_line_declared(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    capsys.readouterr()
    assert main_mod.cmd_restore(base, branch="anon", base=CLONE_OF_CANON) == 1
    err = capsys.readouterr().err
    assert "a pocket declares who cut it — pass --by <who>" in err
    assert main_mod.cmd_restore(base, branch="rebuild", base="schema-only",
                                by="Maren") == 1
    err = capsys.readouterr().err
    assert "a schema-only branch is a rebuild line and carries no " \
           "declaration" in err
    assert main_mod.cmd_restore(base, branch="odd", base="from-nothing") == 1
    assert "--base schema-only or --base clone-of-canon" in \
        capsys.readouterr().err
    assert "anon" not in fake.databases and "odd" not in fake.databases


# -- rounds on a pocket -----------------------------------------------------


def test_a_round_lands_on_the_pocket_and_canon_is_untouched(driven_kb):
    base, fake, snapshot = driven_kb
    before = snapshot()
    _cut_pocket(base)
    _land_round(base, fake, "maren-sketches", "Ember")
    landed = read_export(export_dir(base, "maren-sketches"))
    assert ("Character", "Ember") in landed.nodes
    assert _declaration(landed, "maren-sketches")["cut_by"] == "Maren"
    assert len(read_applied_log(base, "maren-sketches")) == 1
    assert log_head_divergence(base, landed, "maren-sketches") is None
    assert snapshot() == before


def test_the_declaration_is_never_authored_by_hand(driven_kb, capsys):
    base, fake, _ = driven_kb
    _cut_pocket(base)
    branch = "maren-sketches"
    # a second declaration authored in scratch refuses by name
    authored = clone(read_export(export_dir(base, branch)))
    authored.ensure_node(POCKET, "smuggled", cut_by="Pip", invited=[])
    fake.databases[f"{branch}-scratch"] = authored
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None, branch=branch) == 1
    record = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [row["code"] for row in record["verdicts"]] == \
        ["declaration-authored"]
    assert REF_KEYS["declaration-authored"] == "declaration-engine-written"
    # an edit to the existing row in scratch never itemizes: the invite
    # verb is the way, and the round carries only the real change
    edited = clone(read_export(export_dir(base, branch)))
    edited.nodes[(POCKET, branch)]["invited"] = ["Everyone"]
    edited.ensure_node("Character", "Ember", temperament="bright")
    fake.databases[f"{branch}-scratch"] = edited
    assert main_mod.cmd_delta(base, None, branch=branch) == 0
    assert main_mod.cmd_approve(base, "owner", branch=branch) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0
    landed = read_export(export_dir(base, branch))
    assert ("Character", "Ember") in landed.nodes
    assert _declaration(landed, branch)["invited"] == ["Pip"]


# -- invite and uninvite ----------------------------------------------------


def test_invite_and_uninvite_rewrite_the_row_and_the_stamp_only(driven_kb,
                                                                 capsys):
    base, fake, _ = driven_kb
    _cut_pocket(base)
    branch = "maren-sketches"
    _land_round(base, fake, branch, "Ember")
    landed = read_export(export_dir(base, branch))
    identity = base_identity(landed)
    log_before = read_applied_log(base, branch)
    capsys.readouterr()
    assert main_mod.cmd_branch(base, branch) == 0
    assert "cut by Maren" in capsys.readouterr().out
    assert main_mod.cmd_branch(base, branch, invite=["Wren", "Pip"],
                               uninvite=["Pip"]) == 0
    assert "invited: Wren" in capsys.readouterr().out
    after = read_export(export_dir(base, branch))
    assert _declaration(after, branch)["invited"] == ["Wren"]
    assert base_identity(after) == identity
    assert export_mod.serialize(strip_declarations(after)) == \
        export_mod.serialize(strip_declarations(landed))
    assert read_applied_log(base, branch) == log_before
    assert log_head_divergence(base, after, branch) is None
    stamp = fake.read_stamp({"NEO4J_DATABASE": branch})
    assert stamp["pocket_invited"] == ["Wren"]
    assert stamp["base_hash"] == identity
    assert _declaration(fake.databases[branch], branch)["invited"] == ["Wren"]
    # withdrawing a name nobody holds, and a rebuild line, refuse
    assert main_mod.cmd_branch(base, branch, uninvite=["Ghost"]) == 1
    assert "nobody by that name is invited" in capsys.readouterr().err
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 0
    assert main_mod.cmd_branch(base, "rebuild", invite=["Pip"]) == 1
    assert "a rebuild line, not a pocket" in capsys.readouterr().err


# -- the roster -------------------------------------------------------------


def test_branches_lists_pockets_and_lines_from_the_backups(driven_kb, capsys):
    base, fake, _ = driven_kb
    capsys.readouterr()
    assert main_mod.cmd_branches(base) == 0
    assert capsys.readouterr().out.strip() == "No branches."
    _cut_pocket(base)
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 0
    assert main_mod.cmd_branches(base) == 0
    out = capsys.readouterr().out
    assert "pocket    maren-sketches — cut by Maren" in out
    assert "invited: Pip; sequence " in out
    assert "line      rebuild — schema-only; sequence " in out
    record = json.loads(record_path(base, REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert record["kind"] == "branches-report"
    rows = {row["branch"]: row for row in record["branches"]}
    assert rows["maren-sketches"]["code"] == "branch-pocket"
    assert rows["maren-sketches"]["ref"] == "pocket"
    assert rows["maren-sketches"]["pocket"]["invited"] == ["Pip"]
    assert rows["rebuild"]["code"] == "branch-line" and \
        rows["rebuild"]["pocket"] is None


# -- succession from a pocket ---------------------------------------------


def test_succession_adopts_a_pocket_and_strips_its_declaration(driven_kb,
                                                                capsys):
    base, fake, _ = driven_kb
    _cut_pocket(base)
    branch = "maren-sketches"
    _land_round(base, fake, branch, "Ember")
    _mount_live_canon(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    canon = read_export(export_dir(base))
    assert ("Character", "Ember") in canon.nodes
    assert not [key for key in canon.nodes if key[0] == POCKET]
    assert main_mod.cmd_branches(base) == 0
    assert "adopted   maren-sketches" in capsys.readouterr().out
