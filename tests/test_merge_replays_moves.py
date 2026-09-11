"""Merge replays a round's MOVES, and identity survives the crossing.

A moves-only round is not an empty round: its renames and re-homings
are the round. The replay carries each round's declared moves in
sequence, exactly as canonize performed them on the source line — so a
citizen renamed in the pocket keeps its new name in the copy, a later
round's connection onto the renamed citizen lands on a citizen that
exists, and a boolean authored in the pocket is a boolean in the copy.
And when the landed copy still reads back differently than what was
written, the refusal shows the first differences instead of blaming
the driver blind.

Storybook domain, over the driven-kb harness: Pip takes an elder name
in Maren's pocket; canon takes the rounds up.
"""

import json

import graph.__main__ as main_mod
from graph.extract import GraphData, make_edge
from graph.merge import first_differences
from graph.pockets import CLONE_OF_CANON
from graph.proposal import MOVES_FILE, current_dir
from graph.restore import read_export
from tests.test_branch import clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon

POCKET = "maren-sketches"


def _cut_pocket(base):
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0


def _land_pocket_round(base, fake, edit=None, moves=None):
    authored = clone(read_export(export_dir(base, POCKET)))
    if edit:
        edit(authored)
    fake.databases[f"{POCKET}-scratch"] = authored
    if moves:
        current = current_dir(base, POCKET)
        current.mkdir(parents=True, exist_ok=True)
        (current / MOVES_FILE).write_text(json.dumps(moves),
                                          encoding="utf-8")
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0


def test_a_moves_only_round_replays_its_moves(driven_kb):
    base, fake, _ = driven_kb
    _cut_pocket(base)
    # round 1: moves only — the rename IS the round
    _land_pocket_round(base, fake, moves={
        "rename_citizens": {"Character": {"Pip": "Pip the Elder"}}})
    # round 2: a connection onto the renamed citizen
    def edit(graph):
        graph.ensure_node("Place", "Hearth")
        graph.edges.append(make_edge("LIVES_IN", "Character",
                                     "Pip the Elder", "Place", "Hearth"))
    _land_pocket_round(base, fake, edit=edit)
    # canon takes the rounds up
    _mount_live_canon(base, fake)
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    copy = fake.databases["scratch"]
    assert ("Character", "Pip the Elder") in copy.nodes
    assert ("Character", "Pip") not in copy.nodes
    assert copy.nodes[("Character", "Pip the Elder")] == \
        read_export(export_dir(base, POCKET)).nodes[
            ("Character", "Pip the Elder")]
    assert any((e.from_label, str(e.from_name)) ==
               ("Character", "Pip the Elder") and e.type == "LIVES_IN"
               for e in copy.edges)


def test_a_boolean_authored_in_the_pocket_stays_a_boolean(driven_kb):
    base, fake, _ = driven_kb
    _cut_pocket(base)
    def edit(graph):
        graph.nodes[("Character", "Maren")]["wary"] = True
    _land_pocket_round(base, fake, edit=edit)
    _mount_live_canon(base, fake)
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    wary = fake.databases["scratch"].nodes[("Character", "Maren")]["wary"]
    assert wary is True  # a boolean, never the string 'True'


def test_the_roundtrip_refusal_shows_its_first_differences():
    a = GraphData()
    a.ensure_node("Character", "Pip", temperament="bright")
    b = GraphData()
    b.ensure_node("Character", "Pip", temperament="bold")
    b.ensure_node("Place", "Hearth")
    lines = first_differences(a, b)
    text = " ".join(lines)
    assert "Pip" in text and "temperament" in text
    assert "Hearth" in text
    assert len(lines) <= 4
