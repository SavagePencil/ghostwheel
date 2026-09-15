"""A merge carries removals: a struck citizen leaves whole.

The replay lands ground changesets in the target's full working copy —
a copy that also holds the derived layer. A round that strikes a
citizen records the node and its ground connections; the derived
connections are the derive's business and never ride a changeset. So
the applier takes them with the citizen — a removed citizen keeps no
connections, exactly as the database's detach would take them — and
the landed copy reads back as written instead of refusing on edges
that could not survive their endpoint.

Storybook domain, over the driven-kb harness: Pip is struck from
Maren's pocket, and canon takes the round up.
"""

import graph.__main__ as main_mod
from graph.delta import Delta
from graph.extract import make_edge
from graph.pockets import CLONE_OF_CANON
from graph.proposal import apply_delta
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, \
    export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon

POCKET = "maren-sketches"


def _strike_whole(graph, label, name):
    """The authoring gesture the field makes: detach-delete."""
    del graph.nodes[(label, name)]
    graph.edges = [e for e in graph.edges
                   if (e.from_label, str(e.from_name)) != (label, name)
                   and (e.to_label, str(e.to_name)) != (label, name)]


def test_the_applier_takes_a_struck_citizens_remaining_edges():
    # the unit seam: a ground changeset removes the citizen and its
    # ground connection; the derived connection is not the changeset's
    # to carry — the applier takes it with the citizen
    canon = build_canon()
    ground_edge = next(e for e in canon.edges
                       if e.type == "LIVES_IN" and str(e.from_name) == "Pip")
    delta = Delta()
    delta.nodes_removed.append(
        ("Character", "Pip", dict(canon.nodes[("Character", "Pip")])))
    delta.edges_removed.append(ground_edge)
    assert apply_delta(canon, delta) == []
    assert ("Character", "Pip") not in canon.nodes
    dangling = [e for e in canon.edges
                if "Pip" in (str(e.from_name), str(e.to_name))]
    assert dangling == []


def test_a_bystanders_derived_edges_survive_the_removal():
    canon = build_canon()
    ground_edge = next(e for e in canon.edges
                       if e.type == "LIVES_IN" and str(e.from_name) == "Pip")
    delta = Delta()
    delta.nodes_removed.append(
        ("Character", "Pip", dict(canon.nodes[("Character", "Pip")])))
    delta.edges_removed.append(ground_edge)
    assert apply_delta(canon, delta) == []
    assert any(e.type == "INSTANCE_OF" and str(e.from_name) == "Maren"
               for e in canon.edges)


def test_a_merge_whose_round_strikes_a_citizen_lands_clean(driven_kb):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0
    authored = clone(read_export(export_dir(base, POCKET)))
    _strike_whole(authored, "Character", "Pip")
    fake.databases[f"{POCKET}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0
    # canon takes the round up
    _mount_live_canon(base, fake)
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    copy = fake.databases["scratch"]
    assert ("Character", "Pip") not in copy.nodes
    # nothing still touches the struck citizen — a dangling connection
    # is exactly what the database write would drop, and what the
    # round-trip check would then count as a loss
    assert not [e for e in copy.edges
                if "Pip" in (str(e.from_name), str(e.to_name))]
    # the bystanders' derived layer rode across untouched
    assert any(e.type == "INSTANCE_OF" and str(e.from_name) == "Maren"
               for e in copy.edges)


def test_a_round_adding_beside_a_removal_still_replays(driven_kb):
    # the mixed shape: one round strikes Pip and births a Place — both
    # halves land, and the new citizen's derived layer is not expected
    # (it arrives at apply, as ever)
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, branch=POCKET, base=CLONE_OF_CANON,
                                by="Maren") == 0
    authored = clone(read_export(export_dir(base, POCKET)))
    _strike_whole(authored, "Character", "Pip")
    authored.ensure_node("Place", "Hearth")
    authored.edges.append(make_edge("LIVES_IN", "Character", "Maren",
                                    "Place", "Hearth"))
    fake.databases[f"{POCKET}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=POCKET) == 0
    assert main_mod.cmd_approve(base, "owner", branch=POCKET) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=POCKET) == 0
    _mount_live_canon(base, fake)
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert main_mod.cmd_merge(base, POCKET, "canon") == 0
    copy = fake.databases["scratch"]
    assert ("Place", "Hearth") in copy.nodes
    assert ("Character", "Pip") not in copy.nodes
    assert not [e for e in copy.edges
                if "Pip" in (str(e.from_name), str(e.to_name))]
