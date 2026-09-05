"""The bracket sweep and kernel-migrate's rename rule.

A kernel ceremony may rename what it declares. The metaontology's
`renamed` map (old -> new) drives a mechanical rewrite of a canon
BEFORE the splice: every citizen under an old label relabeled, every
edge endpoint re-pointed, every Archetype row under an old name
renamed with its schema edges, project specs' concept bindings and
relationship targets rewritten, the attribution ledger rewritten at
apply; a project-declared row renamed onto a kernel name is ADOPTED —
its file-era spec retires, extra concept bindings survive as declared
memberships on each citizen; a new name the canon already uses refuses
by name. The whole rename lands as one chained round whose inverse
relabels back.

Storybook domain, over the driven-kb harness: a canon frozen at the
kernel before the sweep, migrated forward.
"""

import json

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.extract import GraphData, make_edge
from graph.kernel_migrate import (apply_renames, installed_renames, leaks,
                                  relabel_census, rename_problems,
                                  rewrite_attribution_labels)
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL,
                            KERNEL_DECISION_LABEL, KERNEL_PROCEDURE_LABEL,
                            MEMBERSHIP_EDGE_TYPE)
from graph.proposal import (apply_delta, attribution_log_path, parse_delta,
                            proposals_dir, read_applied_log)
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon

OLD_ARTIFACT, OLD_DECISION = "Artifact", "Decision"


def _before_the_sweep(canon):
    """The storybook canon as it stood one kernel back: kernel rows and
    citizens under the old names, the artifact label PROJECT-declared
    (bound to Provenance and to the storybook's own Book concept), a
    decision citizen ABOUT a character, and the anchor at 0.16.0."""
    back = {KERNEL_ARTIFACT_LABEL: OLD_ARTIFACT,
            KERNEL_DECISION_LABEL: OLD_DECISION,
            KERNEL_PROCEDURE_LABEL: "Procedure"}
    old = GraphData()
    for (label, name), props in canon.nodes.items():
        new_label = back.get(label, label)
        new_name = back.get(name, name) if label == ARCHETYPE_LABEL else name
        old.ensure_node(new_label, new_name, **dict(props))
    for edge in canon.edges:
        fl = back.get(edge.from_label, edge.from_label)
        tl = back.get(edge.to_label, edge.to_label)
        fn = back.get(edge.from_name, edge.from_name) \
            if edge.from_label == ARCHETYPE_LABEL else edge.from_name
        tn = back.get(edge.to_name, edge.to_name) \
            if edge.to_label == ARCHETYPE_LABEL else edge.to_name
        if edge.type == "DECLARED_IN" and fn == OLD_ARTIFACT:
            tn = "Ontology"  # project-declared, as the first consumer's was
        old.edges.append(make_edge(edge.type, fl, fn, tl, tn,
                                   dict(edge.props)))
    row = old.nodes[(ARCHETYPE_LABEL, OLD_ARTIFACT)]
    row["spec_json"] = json.dumps({"concept": ["Provenance", "Book"],
                                   "fingerprint": True,
                                   "values": ["docs/tale.md"]},
                                  sort_keys=True)
    old.ensure_node(OLD_DECISION, "Pip is curious", decided_by="owner",
                    doc="a ruling")
    old.edges.append(make_edge("ABOUT", OLD_DECISION, "Pip is curious",
                               "Character", "Pip"))
    old.nodes[(ARCHETYPE_LABEL, "Metaontology")]["version"] = "0.16.0"
    return old


def _kernel_seed():
    canon = build_canon()
    return canon


# -- the rule, unit by unit --------------------------------------------------


def test_the_installed_kernel_names_its_renames():
    renames = installed_renames()
    assert renames["Procedure"] == KERNEL_PROCEDURE_LABEL
    assert renames["Decision"] == KERNEL_DECISION_LABEL
    assert renames["Artifact"] == KERNEL_ARTIFACT_LABEL
    assert renames["Step"] == "[Step]" and renames["Outcome"] == "[Outcome]"
    assert renames["[Dependency]"] == "[Knowledge Base Dependency]"
    assert "Theme" not in renames  # designer lexicon, on record


def test_apply_renames_relabels_repoints_rewrites_and_adopts():
    old = _before_the_sweep(_kernel_seed())
    renames = installed_renames()
    assert [name for name, _ in relabel_census(old, renames)] == [
        "Artifact", "Decision", "Procedure"]
    renamed, adoptions = apply_renames(old, renames, "0.17.0")
    # citizens relabeled, edges re-pointed
    assert (KERNEL_DECISION_LABEL, "Pip is curious") in renamed.nodes
    assert (OLD_DECISION, "Pip is curious") not in renamed.nodes
    assert any(e.type == "ABOUT" and e.from_label == KERNEL_DECISION_LABEL
               for e in renamed.edges)
    assert (KERNEL_ARTIFACT_LABEL, "docs/tale.md") in renamed.nodes
    # Archetype rows renamed with their schema edges
    assert (ARCHETYPE_LABEL, KERNEL_DECISION_LABEL) in renamed.nodes
    assert (ARCHETYPE_LABEL, OLD_DECISION) not in renamed.nodes
    assert any(e.type == "DECLARED_IN" and e.from_name == KERNEL_DECISION_LABEL
               for e in renamed.edges)
    # the adoption: spec retired, project DECLARED_IN dropped, the extra
    # concept binding kept as a declared membership per citizen
    [adoption] = adoptions
    assert adoption["label"] == OLD_ARTIFACT
    assert adoption["new"] == KERNEL_ARTIFACT_LABEL
    assert adoption["citizens"] == 1
    assert adoption["retired_spec_keys"] == ["concept", "fingerprint",
                                             "values"]
    # Book is a Provenance-side concept, not subject matter: no declared
    # membership can carry that binding, so it retires with the spec —
    # named, never silent
    assert adoption["memberships"] == []
    assert adoption["bindings_dropped"] == ["Book"]
    row = renamed.nodes[(ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL)]
    assert "spec_json" not in row
    assert not any(e.type == "DECLARED_IN" and e.from_name == KERNEL_ARTIFACT_LABEL
                   for e in renamed.edges)
    assert not [e for e in renamed.edges if e.type == MEMBERSHIP_EDGE_TYPE
                and e.from_label == KERNEL_ARTIFACT_LABEL]
    # a subject-matter binding DOES survive as a membership per citizen
    subject = _before_the_sweep(_kernel_seed())
    subject.nodes[(ARCHETYPE_LABEL, OLD_ARTIFACT)]["spec_json"] = json.dumps(
        {"concept": ["Provenance", "Story Concept"], "values": ["docs/tale.md"]})
    renamed, [adoption] = apply_renames(subject, renames, "0.17.0")
    assert adoption["memberships"] == ["Story Concept"]
    [membership] = [e for e in renamed.edges if e.type == MEMBERSHIP_EDGE_TYPE
                    and e.from_label == KERNEL_ARTIFACT_LABEL]
    assert membership.to_name == "Story Concept"
    assert "adopted at the kernel ceremony" in dict(membership.props)["basis"]


def test_a_new_name_the_canon_already_uses_refuses_by_name():
    old = _before_the_sweep(_kernel_seed())
    old.ensure_node(ARCHETYPE_LABEL, KERNEL_DECISION_LABEL, doc="mine")
    [problem] = rename_problems(old, installed_renames())
    assert "rename 'Decision' to '[Decision]'" in problem
    assert "already holds '[Decision]'" in problem
    assert rename_problems(_kernel_seed(), installed_renames()) == []


def test_the_leak_check_admits_exactly_the_relabels():
    from graph.delta import diff
    old = _before_the_sweep(_kernel_seed())
    renames = installed_renames()
    renamed, adoptions = apply_renames(old, renames, "0.17.0")
    changes = diff(old, renamed)
    kernel = {n for (l, n) in old.nodes if l == ARCHETYPE_LABEL}
    kernel |= set(renames) | set(renames.values())
    relabeled = set(renames) | set(renames.values())
    adopted = {a["label"] for a in adoptions} | {a["new"] for a in adoptions}
    assert leaks(changes, kernel, relabeled_labels=relabeled,
                 adopted=adopted) == []
    # without the rule's allowances the same delta is a leak
    assert leaks(changes, kernel)


def test_the_attribution_ledger_moves_with_the_canon(tmp_path):
    path = attribution_log_path(tmp_path)
    path.parent.mkdir(parents=True)
    rows = [{"citizens": [["Decision", "Pip is curious"],
                          ["Archetype", "Procedure"]],
             "claim": "c", "locator": "l", "source": "s", "sequence": 1},
            {"citizens": [["Character", "Pip"]], "claim": "d",
             "locator": "l", "source": "s", "sequence": 1}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert rewrite_attribution_labels(tmp_path, installed_renames()) == 1
    first, second = [json.loads(l) for l in
                     path.read_text().splitlines()]
    assert first["citizens"] == [[KERNEL_DECISION_LABEL, "Pip is curious"],
                                 ["Archetype", KERNEL_PROCEDURE_LABEL]]
    assert second["citizens"] == [["Character", "Pip"]]


# -- the migration round, end to end -------------------------------------


def test_kernel_migrate_lands_the_sweep_as_one_round_with_its_inverse(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    old = _before_the_sweep(read_export(export_dir(base)))
    export_mod.write_export(old, export_dir(base))
    path = attribution_log_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"citizens": [["Decision", "Pip is curious"]],
                                "claim": "c", "locator": "l", "source": "s",
                                "sequence": 1}) + "\n")
    _mount_live_canon(base, fake)
    capsys.readouterr()
    assert main_mod.cmd_kernel_migrate(base) == 0
    out = capsys.readouterr().out
    assert "Kernel migration: 0.16.0 ->" in out
    assert "Decision -> [Decision] (1 citizen relabeled)" in out
    assert "adopted (1): project label 'Artifact' -> [Artifact]" in out
    assert "1 citizens keep their rows" in out
    assert "declared memberships: none" in out
    assert "binding to Book retired with the spec" in out
    assert "Dry run" in out
    assert main_mod.cmd_kernel_migrate(base, apply=True) == 0
    out = capsys.readouterr().out
    assert "attribution ledger: 1 row rewritten" in out
    migrated = read_export(export_dir(base))
    assert (KERNEL_DECISION_LABEL, "Pip is curious") in migrated.nodes
    assert (KERNEL_ARTIFACT_LABEL, "docs/tale.md") in migrated.nodes
    assert (OLD_DECISION, "Pip is curious") not in migrated.nodes
    assert (ARCHETYPE_LABEL, OLD_ARTIFACT) not in migrated.nodes
    assert migrated.nodes[(ARCHETYPE_LABEL, "Metaontology")]["version"] != \
        "0.16.0"
    # the artifact is an instance of the kernel concept
    parents = {e.to_name for e in migrated.edges
               if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == (KERNEL_ARTIFACT_LABEL,
                                                   "docs/tale.md")}
    assert KERNEL_ARTIFACT_LABEL in parents
    assert json.loads(path.read_text())["citizens"] == \
        [[KERNEL_DECISION_LABEL, "Pip is curious"]]
    # one chained round, and its inverse relabels back
    [entry] = read_applied_log(base)
    archive = proposals_dir(base) / entry[1][:12]
    inverse = parse_delta((archive / "inverse.json").read_text("utf-8"))
    from graph.extract import strip_derived
    walked_back = clone(strip_derived(migrated))
    assert apply_delta(walked_back, inverse) == []
    assert (OLD_DECISION, "Pip is curious") in walked_back.nodes
    assert (KERNEL_DECISION_LABEL, "Pip is curious") not in walked_back.nodes
    assert (ARCHETYPE_LABEL, OLD_ARTIFACT) in walked_back.nodes
    # a second run has nothing left to do
    assert main_mod.cmd_kernel_migrate(base) == 0
    assert "nothing to migrate" in capsys.readouterr().out
