"""Declared moves: a world renames its own label or re-homes citizens
under a kind, as a gated round.

moves.json beside the stitch declares RENAME (old -> new) and REHOME
(source label -> {kind label -> [names]}); the proposal embeds it; the
gate itemizes each move with counts and refuses by name what cannot
move (a held new name, a kernel name, a target that is no kind of the
source, a citizen not under the source); canonize --apply performs the
moves after the authored changeset and before the stitch and
re-derivation, rewrites the attribution ledger, and records the inverse
as the full ground diff so the relabel walks back. A stale declaration
is discarded when the copy is re-cut.

Storybook domain, over the driven-kb harness: the tale's Characters gain
a Wanderer kind; the Place concept takes a bracketed name.
"""

import json

import graph.__main__ as main_mod
from graph.delta import diff
from graph.extract import make_edge, strip_derived
from graph.moves import apply_moves, kernel_names, move_records, normalize
from graph.ontology import ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL
from graph.proposal import (MOVES_FILE, apply_delta, attribution_log_path,
                            current_dir, parse_delta, proposals_dir,
                            read_applied_log)
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon


def _declare(base, moves):
    current = current_dir(base)
    current.mkdir(parents=True, exist_ok=True)
    (current / MOVES_FILE).write_text(json.dumps(moves), encoding="utf-8")


def _kind(graph, name, of):
    """A storybook kind of `of`, declared as a spec-carrying label."""
    graph.ensure_node(ARCHETYPE_LABEL, name, doc=f"a kind of {of}",
                      spec_json=json.dumps({"concept": "Story Concept"}))
    graph.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, "Ontology"))
    graph.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, of))
    return graph


# -- the declaration ---------------------------------------------------------


def test_the_declaration_normalizes_or_refuses_in_the_house_form():
    assert normalize({"rename": {"Place": "[Place]"}}) == \
        {"rename": {"Place": "[Place]"}}
    assert normalize({"rehome": {"Character": {"Wanderer": ["Pip", "Maren",
                                                            "Pip"]}}}) == \
        {"rehome": {"Character": {"Wanderer": ["Maren", "Pip"]}}}
    for bad, why in (([], "not an object"), ({"move": {}}, "unknown move"),
                     ({"rename": {"A": 3}}, "old names to new names"),
                     ({"rehome": {"A": {"B": "Pip"}}}, "list citizen")):
        try:
            normalize(bad)
        except ValueError as exc:
            assert str(exc).startswith("Attempted to read the round's moves")
            assert why in str(exc)
        else:
            raise AssertionError(bad)


# -- the gate ------------------------------------------------------------------


def _records(base, scratch, moves):
    delta = diff(base, scratch)
    delta.moves = normalize(moves)
    return move_records(delta, base)


def test_a_rename_and_a_rehome_itemize_with_their_counts():
    base = _kind(build_canon(), "Wanderer", "Character")
    items, refusals = _records(base, clone(base), {
        "rename": {"Place": "[Place]"},
        "rehome": {"Character": {"Wanderer": ["Pip"]}}})
    assert refusals == [], [str(v) for v in refusals]
    rename, rehome = items
    assert rename.code == "project-renamed"
    assert "PROJECT RENAME — 'Place' becomes '[Place]'" in str(rename)
    places = sum(1 for l, _ in base.nodes if l == "Place")
    assert rename.row()["data"]["citizens"] == places
    assert rename.row()["data"]["edges"] > 0
    assert rehome.code == "citizens-rehomed"
    assert "RE-HOMED — 1 citizen of 'Character' become 'Wanderer'" in str(rehome)
    assert REF_KEYS["project-renamed"] == "renamed"
    assert REF_KEYS["citizens-rehomed"] == "rehomed"


def test_each_move_refuses_by_name_when_it_cannot(tmp_path):
    base = _kind(build_canon(), "Wanderer", "Character")
    codes = lambda moves: sorted(v.code for v in _records(base, clone(base),
                                                          moves)[1])
    assert codes({"rename": {KERNEL_ARTIFACT_LABEL: "[Thing]"}}) == \
        ["move-kernel-name"]
    assert codes({"rename": {"Nobody": "[Nobody]"}}) == ["move-source-missing"]
    assert codes({"rename": {"Place": "Character"}}) == ["move-target-held"]
    assert codes({"rename": {"Place": KERNEL_ARTIFACT_LABEL}}) == \
        ["move-target-held"]
    assert codes({"rehome": {"Character": {"Place": ["Pip"]}}}) == \
        ["rehome-not-a-kind"]
    [verdict] = _records(base, clone(base),
                         {"rehome": {"Character": {"Wanderer": ["Ghost"]}}})[1]
    assert verdict.code == "rehome-citizen-missing"
    assert verdict.data["missing"] == ["Ghost"]
    # a kind declared by this round's own changeset counts
    scratch = _kind(clone(build_canon()), "Wanderer", "Character")
    assert _records(build_canon(), scratch,
                    {"rehome": {"Character": {"Wanderer": ["Pip"]}}})[1] == []


# -- the transform -------------------------------------------------------------


def test_apply_moves_renames_and_rehomes_keeping_every_fact():
    base = _kind(build_canon(), "Wanderer", "Character")
    moved, problems = apply_moves(
        base, normalize({"rename": {"Place": "[Place]"},
                         "rehome": {"Character": {"Wanderer": ["Pip"]}}}),
        kernel_names(base))
    assert problems == []
    assert (ARCHETYPE_LABEL, "[Place]") in moved.nodes
    assert not [k for k in moved.nodes if k[0] == "Place"]
    # the project rename keeps its spec (no adoption)
    assert "spec_json" in moved.nodes[(ARCHETYPE_LABEL, "[Place]")]
    assert ("Wanderer", "Pip") in moved.nodes
    assert ("Character", "Pip") not in moved.nodes
    assert moved.nodes[("Wanderer", "Pip")]["temperament"] == "curious"
    assert ("Character", "Maren") in moved.nodes
    assert any(e.from_label == "Wanderer" and e.from_name == "Pip"
               for e in moved.edges)
    assert len(moved.nodes) == len(base.nodes)
    assert len(moved.edges) == len(base.edges)


# -- the round -------------------------------------------------------------------


def test_a_round_with_moves_lands_and_walks_back(driven_kb, capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    # the round declares a kind in scratch, re-homes one citizen into it,
    # renames the Place concept, and declares the renamed concept a kind
    # of Story Concept — authored in scratch under the OLD name (scratch
    # was cut before the rename); the rename re-points it. One gate for
    # one intention.
    authored = _kind(clone(canon), "Wanderer", "Character")
    authored.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "Place",
                                    ARCHETYPE_LABEL, "Story Concept"))
    fake.databases["scratch"] = authored
    _declare(base, {"rename": {"Place": "[Place]"},
                    "rehome": {"Character": {"Wanderer": ["Pip"]}}})
    path = attribution_log_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"citizens": [["Character", "Pip"],
                                             ["Archetype", "Place"]],
                                "claim": "c", "locator": "l", "source": "s",
                                "sequence": 0}) + "\n")
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    out = capsys.readouterr().out
    assert "PROJECT RENAME — 'Place' becomes '[Place]'" in out
    assert "RE-HOMED — 1 citizen of 'Character' become 'Wanderer'" in out
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert {i["code"] for i in report["ceremony"]} >= {"project-renamed",
                                                       "citizens-rehomed",
                                                       "taxonomy-declared"}
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    out = capsys.readouterr().out
    assert "attribution ledger:" in out and "follow the moves" in out
    landed = read_export(export_dir(base))
    assert (ARCHETYPE_LABEL, "[Place]") in landed.nodes
    assert not [k for k in landed.nodes if k[0] == "Place"]
    assert ("Wanderer", "Pip") in landed.nodes
    assert any(e.type == "SUBTYPE_OF" and e.from_name == "[Place]"
               and e.to_name == "Story Concept" for e in landed.edges)
    # the fold: Pip is a Wanderer AND still a Character
    parents = {e.to_name for e in landed.edges if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("Wanderer", "Pip")}
    assert {"Wanderer", "Character"} <= parents
    # the ledger followed
    row = json.loads(path.read_text().splitlines()[0])
    assert row["citizens"] == [["Wanderer", "Pip"], ["Archetype", "[Place]"]]
    # the archive carries the declaration; the inverse walks the ground back
    [entry] = read_applied_log(base)
    archive = proposals_dir(base) / entry[1][:12]
    assert json.loads((archive / MOVES_FILE).read_text())["rename"] == \
        {"Place": "[Place]"}
    assert not (current_dir(base) / MOVES_FILE).exists()
    inverse = parse_delta((archive / "inverse.json").read_text("utf-8"))
    back = clone(strip_derived(landed))
    assert apply_delta(back, inverse) == []
    assert ("Character", "Pip") in back.nodes
    assert (ARCHETYPE_LABEL, "Place") in back.nodes
    assert (ARCHETYPE_LABEL, "Wanderer") not in back.nodes
    assert set(back.nodes) == set(strip_derived(canon).nodes)


def test_a_refused_move_blocks_the_gate_and_a_stale_one_is_discarded(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    fake.databases["scratch"] = clone(canon)
    _declare(base, {"rename": {"Place": "Character"}})
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 1
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [v["code"] for v in report["verdicts"]] == ["move-target-held"]
    # an unreadable declaration is a refusal too
    (current_dir(base) / MOVES_FILE).write_text('{"move": 1}')
    assert main_mod.cmd_delta(base, None) == 1
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [v["code"] for v in report["verdicts"]] == ["moves-file-unreadable"]
    # re-cutting the copy discards the declaration, with a note
    capsys.readouterr()
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert "moves declaration left by a round that was never applied" in \
        capsys.readouterr().out
    assert not (current_dir(base) / MOVES_FILE).exists()
