"""Two defects the first declared-moves round exposed, closed by name.

A re-home spelled under a name the same round renames resolves through
that rename: rename A -> [A] with re-home X -> A lands the citizens under
[A], with their membership. And an unknown label is not nothing: a
citizen whose label has no schema row refuses by name at the gate and at
derivation, and every derived connection a round's landing would drop
is itemized at the gate and named at apply.

Storybook domain, over the driven-kb harness.
"""

import json

import graph.__main__ as main_mod
from graph.delta import diff, lint_verdicts
from graph.extract import derive, make_edge, orphan_citizen_findings
from graph.moves import apply_moves, kernel_names, move_records, normalize
from graph.ontology import ARCHETYPE_LABEL, ontology_from_graph
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, export_dir  # noqa: F401
from tests.test_project_moves import _declare, _kind
from tests.test_succession import _mount_live_canon


# -- defect 1: rename + re-home of the same concept -------------------------


def test_a_rehome_spelled_under_the_old_name_lands_under_the_new_one():
    base = _kind(build_canon(), "Wanderer", "Character")
    moves = normalize({"rename": {"Wanderer": "[Wanderer]"},
                       "rehome": {"Character": {"Wanderer": ["Pip"]}}})
    # the gate names the labels as they will stand
    items, refusals = move_records(_delta(base, moves), base)
    assert refusals == [], [str(v) for v in refusals]
    [rehome] = [i for i in items if i.code == "citizens-rehomed"]
    assert "become '[Wanderer]' (a kind of 'Character')" in str(rehome)
    moved, problems = apply_moves(base, moves, kernel_names(base))
    assert problems == []
    assert ("[Wanderer]", "Pip") in moved.nodes
    assert not [k for k in moved.nodes if k[0] == "Wanderer"]
    assert (ARCHETYPE_LABEL, "[Wanderer]") in moved.nodes
    # and derivation gives the moved citizen its membership, folded up
    derived, findings = derive(ontology_from_graph(moved, "/nowhere"), moved)
    assert not [f for f in findings if f.severity == "error"], [
        f.detail for f in findings if f.severity == "error"]
    parents = {e.to_name for e in derived.edges if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("[Wanderer]", "Pip")}
    assert {"[Wanderer]", "Character"} <= parents


def _delta(base, moves):
    delta = diff(base, clone(base))
    delta.moves = moves
    return delta


def test_the_round_lands_the_citizens_under_the_renamed_kind(driven_kb,
                                                              capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    fake.databases["scratch"] = _kind(clone(canon), "Wanderer", "Character")
    _declare(base, {"rename": {"Wanderer": "[Wanderer]"},
                    "rehome": {"Character": {"Wanderer": ["Pip"]}}})
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    landed = read_export(export_dir(base))
    assert ("[Wanderer]", "Pip") in landed.nodes
    assert not [k for k in landed.nodes if k[0] == "Wanderer"]
    parents = {e.to_name for e in landed.edges if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == ("[Wanderer]", "Pip")}
    assert {"[Wanderer]", "Character"} <= parents


# -- defect 2: an unknown label is not nothing -------------------------------


def test_an_undeclared_label_refuses_at_the_gate_and_at_derivation():
    base = build_canon()
    scratch = clone(base)
    scratch.ensure_node("Ghost", "Whisper", doc="under no schema row")
    [verdict] = [v for v in lint_verdicts(diff(base, scratch), base)
                 if v.code == "citizen-label-undeclared"]
    assert "no schema row declares 'Ghost'" in str(verdict)
    assert REF_KEYS["citizen-label-undeclared"] == "unknown-kind"
    # a label born by the same round is fine
    born = clone(scratch)
    born.ensure_node(ARCHETYPE_LABEL, "Ghost", doc="now declared",
                     spec_json=json.dumps({"concept": "Story Concept"}))
    born.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Ghost",
                                ARCHETYPE_LABEL, "Ontology"))
    assert not [v for v in lint_verdicts(diff(base, born), base)
                if v.code == "citizen-label-undeclared"]
    # derivation refuses the orphan by name — the guard every apply,
    # rederive, and kernel-migrate already runs
    [finding] = orphan_citizen_findings(scratch)
    assert finding.severity == "error"
    assert finding.verdict_code == "citizen-label-undeclared"
    assert "1 citizen under 'Ghost' ('Whisper')" in finding.detail
    _, findings = derive(ontology_from_graph(scratch, "/nowhere"), scratch)
    assert any(f.verdict_code == "citizen-label-undeclared" for f in findings)
    assert orphan_citizen_findings(base) == []


def test_derived_connections_that_leave_are_itemized_at_the_gate(driven_kb,
                                                                  capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    # removing a citizen takes its membership with it: the gate says so
    authored = clone(canon)
    victim = next(k for k in authored.nodes if k[0] == "Character")
    del authored.nodes[victim]
    authored.edges = [e for e in authored.edges
                      if (e.from_label, e.from_name) != victim
                      and (e.to_label, e.to_name) != victim]
    fake.databases["scratch"] = authored
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    leaving = [row for row in report["advisories"]
               if row["code"] == "derived-edges-leaving"]
    assert leaving, report["advisories"]
    instance = next(row for row in leaving if row["data"]["type"] == "INSTANCE_OF")
    assert instance["data"]["count"] >= 1
    assert instance["data"]["examples"][0]["from"]["name"] == victim[1]
    assert REF_KEYS["derived-edges-leaving"] == "connections-lost"
    assert "derived INSTANCE_OF connection" in capsys.readouterr().out
    # and apply names them too
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    assert "derived connections leaving with this round:" in \
        capsys.readouterr().out


def test_apply_refuses_a_landing_with_an_orphaned_label(driven_kb, capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    # a re-home into a kind the round declares, then the kind's row is
    # removed by hand from the moves target: the gate refuses before apply
    fake.databases["scratch"] = clone(canon)
    _declare(base, {"rehome": {"Character": {"Ghost": ["Pip"]}}})
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 1
    report = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    assert [v["code"] for v in report["verdicts"]] == ["rehome-not-a-kind"]
