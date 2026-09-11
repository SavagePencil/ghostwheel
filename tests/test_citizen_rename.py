"""Declared moves: a citizen rename — identity preserved end to end.

The moves idiom's third verb: {"rename_citizens": {"<Label>": {"Old":
"New"}}}. The gate itemizes each rename with its counts and refuses by
name what cannot move; apply performs them between the label renames
and the rehomes, so a rename declared under a label the same round
renames resolves THROUGH it, and a rehomed citizen's name resolves
through its own rename; every property travels, every edge endpoint
re-points, and the attribution ledger's citizen refs follow. A by-hand
remove-and-add loses exactly that identity — the defect this verb
exists to avoid.

Storybook domain: Pip takes an elder name; the wilting tale keeps
every thread that names him.
"""

import json

import pytest

from graph.delta import Delta
from graph.extract import make_edge
from graph.moves import (CITIZEN_RENAME, apply_moves, kernel_names,
                         move_records, normalize)
from graph.ontology import ARCHETYPE_LABEL
from graph.report import REF_KEYS
from tests.test_branch import build_canon


def _moved(moves):
    delta = Delta()
    delta.moves = moves
    return delta


# -- the declaration's shape -----------------------------------------------


def test_normalize_admits_the_third_verb_and_keeps_house_shape():
    doc = {"rename_citizens": {"Character": {"Pip": "Pip the Elder",
                                             "Maren": "Maren of the Vale"}}}
    out = normalize(doc)
    assert out[CITIZEN_RENAME] == {
        "Character": {"Maren": "Maren of the Vale",
                      "Pip": "Pip the Elder"}}
    with pytest.raises(ValueError, match="rename_citizens"):
        normalize({"rename_citizens": {"Character": ["Pip"]}})
    with pytest.raises(ValueError, match="rename_citizens"):
        normalize({"rename_citizens": {"Character": {"Pip": ""}}})
    # the unknown-kind refusal now teaches all three verbs
    with pytest.raises(ValueError, match="rename_citizens"):
        normalize({"recall": {}})


# -- the gate itemizes and refuses -----------------------------------------


def test_the_gate_itemizes_a_citizen_rename_with_its_counts():
    base = build_canon()
    delta = _moved({CITIZEN_RENAME: {"Character": {"Pip": "Pip the Elder"}}})
    items, violations = move_records(delta, base)
    assert violations == [], [v.message for v in violations]
    [item] = items
    assert item.code == "citizen-renamed"
    assert "'Pip' becomes 'Pip the Elder'" in item.message
    edges = sum(1 for e in base.edges
                if (e.from_label, str(e.from_name)) == ("Character", "Pip")
                or (e.to_label, str(e.to_name)) == ("Character", "Pip"))
    assert item.data["edges"] == edges and edges > 0
    assert "citizen-renamed" in REF_KEYS


def test_the_gate_refuses_what_cannot_move():
    base = build_canon()
    # the new name already held under the label
    delta = _moved({CITIZEN_RENAME: {"Character": {"Pip": "Maren"}}})
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-target-held"
    # held by an arrival of this very round
    delta = _moved({CITIZEN_RENAME: {"Character": {"Pip": "Newcomer"}}})
    delta.nodes_added.append(("Character", "Newcomer", {}))
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-target-held"
    # the old citizen missing
    delta = _moved({CITIZEN_RENAME: {"Character": {"Nobody": "Somebody"}}})
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-missing"
    # an unknown label, and a machinery label, each by name
    delta = _moved({CITIZEN_RENAME: {"Nonesuch": {"a": "b"}}})
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-label-unknown"
    delta = _moved({CITIZEN_RENAME: {ARCHETYPE_LABEL: {"Character": "X"}}})
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-label-unknown"
    assert "schema row" in v.message  # the rename verb owns that road
    # two olds collapsing onto one new
    delta = _moved({CITIZEN_RENAME: {"Character": {"Pip": "One",
                                                   "Maren": "One"}}})
    [v] = move_records(delta, base)[1]
    assert v.code == "citizen-rename-target-held"
    assert "collapse" in v.message


def test_a_rename_declared_under_a_renamed_label_resolves_through():
    base = build_canon()
    delta = _moved({"rename": {"Character": "[Character]"},
                    CITIZEN_RENAME: {"Character": {"Pip": "Pip the Elder"}}})
    items, violations = move_records(delta, base)
    assert violations == [], [v.message for v in violations]
    [item] = [i for i in items if i.code == "citizen-renamed"]
    assert "[Character]" in item.message  # the label as it will stand


# -- apply: identity travels whole -----------------------------------------


def test_apply_carries_props_edges_and_order():
    base = build_canon()
    moves = normalize({
        "rename": {"Character": "[Character]"},
        "rename_citizens": {"Character": {"Pip": "Pip the Elder"}}})
    moved, problems = apply_moves(base, moves, kernel_names(base))
    assert problems == []
    assert ("[Character]", "Pip the Elder") in moved.nodes
    assert ("[Character]", "Pip") not in moved.nodes
    assert moved.nodes[("[Character]", "Pip the Elder")] == \
        base.nodes[("Character", "Pip")]
    assert not any(str(e.from_name) == "Pip" or str(e.to_name) == "Pip"
                   for e in moved.edges
                   if e.from_label == "[Character]"
                   or e.to_label == "[Character]")
    assert any((e.from_label, str(e.from_name)) ==
               ("[Character]", "Pip the Elder") or
               (e.to_label, str(e.to_name)) ==
               ("[Character]", "Pip the Elder") for e in moved.edges)


def test_a_rehome_resolves_through_the_citizen_rename():
    base = build_canon()
    base.ensure_node(ARCHETYPE_LABEL, "Wanderer", doc="a kind",
                     spec_json=json.dumps({"concept": "Character"}))
    base.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Wanderer",
                                ARCHETYPE_LABEL, "Ontology"))
    base.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "Wanderer",
                                ARCHETYPE_LABEL, "Character"))
    moves = normalize({
        "rename_citizens": {"Character": {"Pip": "Pip the Elder"}},
        "rehome": {"Character": {"Wanderer": ["Pip"]}}})
    moved, problems = apply_moves(base, moves, kernel_names(base))
    assert problems == []
    assert ("Wanderer", "Pip the Elder") in moved.nodes
    assert ("Character", "Pip") not in moved.nodes
    assert ("Character", "Pip the Elder") not in moved.nodes


def test_the_ledger_s_citizen_refs_follow(tmp_path):
    from graph.moves import rewrite_ledger
    from graph.proposal import attribution_log_path
    path = attribution_log_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"claim": "the vine wilted", "citizens": [["Character", "Pip"],
                                                    ["Place", "Hearth"]]}
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    moves = normalize({"rename_citizens": {"Character":
                                           {"Pip": "Pip the Elder"}}})
    assert rewrite_ledger(tmp_path, moves) == 1
    kept = json.loads(path.read_text(encoding="utf-8"))
    assert kept["citizens"] == [["Character", "Pip the Elder"],
                                ["Place", "Hearth"]]


def test_an_alias_may_target_the_round_s_own_rename():
    # the alias ceremony admits a target born by the round — and a
    # citizen RENAMED by the round is born under its new name just the
    # same: the graph the round produces holds it
    from graph.delta import ceremony_records
    base = build_canon()
    spec_before = {"properties": {}}
    spec_after = {"properties": {},
                  "aliases": {"The Elder": "Pip the Elder"}}
    delta = _moved({CITIZEN_RENAME: {"Character": {"Pip": "Pip the Elder"}}})
    base.ensure_node(ARCHETYPE_LABEL, "Character-Roster", doc="a roster",
                     spec_json=json.dumps(spec_before))
    delta.nodes_changed.append(
        ("Archetype", "Character-Roster",
         {"spec_json": (json.dumps(spec_before), json.dumps(spec_after))}))
    # the alias resolves through the round's own citizen rename... but
    # only under the RIGHT label: the roster row's citizens live under
    # its own label, so the through-resolution reads the rename map of
    # the row's label
    delta.moves = {CITIZEN_RENAME: {"Character-Roster":
                                    {"Pip": "Pip the Elder"}}}
    base.ensure_node("Character-Roster", "Pip", doc="the same soul")
    _items, violations = ceremony_records(delta, base)[0:2]
    missing = [v for v in violations if v.code == "alias-target-missing"]
    assert missing == [], [v.message for v in missing]
