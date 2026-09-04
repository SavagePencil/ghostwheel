"""Dependencies and bookmarks: the kernel's vocabulary for one knowledge
base pinning another and citing a citizen that lives there.

Kernel 0.15.0 declares two Provenance-rooted machinery concepts —
bracketed, because a designer never authors either as subject matter.
A [Dependency] pins another knowledge base to an edition with a read
or write intent; a [Bookmark] names a citizen in a dependency with
exactly one RESOLVES_IN edge to it. The delta gate checks their SHAPE;
resolution against the dependency's backup is the next rung.
`init --world` seeds the same knowledge base plus the dependency
settings block — a world is a role, never a type.

Storybook domain: the tale pins a herbal it cites for Nightbell.
"""

import json
from pathlib import Path

import graph.__main__ as main_mod
from graph.delta import diff
from graph.dependencies import (BOOKMARK_REQUIRED, DEPENDENCY_REQUIRED,
                                RESOLVES_IN_EDGE, gate_verdicts)
from graph.extract import make_edge
from graph.kernel_migrate import fresh_kernel
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_BOOKMARK_LABEL,
                            KERNEL_DEPENDENCY_LABEL)
from graph.report import REF_KEYS, record_path
from tests.test_branch import build_canon, clone, driven_kb  # noqa: F401

DEPENDENCY, BOOKMARK = KERNEL_DEPENDENCY_LABEL, KERNEL_BOOKMARK_LABEL
HERBAL = {"edition": "a" * 64, "sequence": 12, "intent": "read",
          "ref": "v3.0.0", "doc": "the herbal this tale consults"}
NIGHTBELL = {"dependency": "herbal", "citizen_label": "Herb",
             "citizen_name": "Nightbell", "edition": "a" * 64,
             "doc": "the herb the tale's tea is made of"}


def _pin(graph, dependency="herbal", props=HERBAL):
    graph.ensure_node(DEPENDENCY, dependency, **dict(props))
    return graph


def _bookmark(graph, name="herbal:Herb:Nightbell", props=NIGHTBELL,
              dependency="herbal", link=True):
    graph.ensure_node(BOOKMARK, name, **dict(props))
    if link:
        graph.edges.append(make_edge(RESOLVES_IN_EDGE, BOOKMARK, name,
                                     DEPENDENCY, dependency))
    return graph


def _codes(base, scratch):
    return sorted(v.code for v in gate_verdicts(diff(base, scratch), scratch))


# -- the kernel declares them ---------------------------------------------


def test_the_kernel_declares_both_under_provenance_bracketed(tmp_path):
    seed, findings = fresh_kernel(tmp_path)
    assert seed is not None, findings
    for label in (DEPENDENCY, BOOKMARK):
        assert label.startswith("[") and label.endswith("]")
        assert (ARCHETYPE_LABEL, label) in seed.nodes
        parents = {e.to_name for e in seed.edges
                   if e.type == "INSTANCE_OF"
                   and (e.from_label, e.from_name) == (ARCHETYPE_LABEL, label)}
        assert parents == {"Provenance"}
        assert any(e.type == "DECLARED_IN" and e.to_name == "Metaontology"
                   and e.from_name == label for e in seed.edges)
    assert DEPENDENCY == "[Dependency]" and BOOKMARK == "[Bookmark]"
    assert DEPENDENCY_REQUIRED == ("edition", "sequence", "intent")
    assert BOOKMARK_REQUIRED == ("dependency", "citizen_label",
                                 "citizen_name", "edition")


# -- the shape at the gate -------------------------------------------------


def test_a_well_formed_pin_and_bookmark_pass():
    base = build_canon()
    scratch = _bookmark(_pin(clone(base)))
    assert _codes(base, scratch) == []
    # a bookmark on a dependency the BASE already pins passes the same way
    base2 = _pin(clone(base))
    assert _codes(base2, _bookmark(clone(base2))) == []
    # and a domain citizen pointing at the bookmark is ordinary ground
    scratch.edges.append(make_edge("BREWS_FROM", "Character", "Ember",
                                   BOOKMARK, "herbal:Herb:Nightbell"))
    assert _codes(base, scratch) == []


def test_a_dependency_refuses_by_name_when_malformed():
    base = build_canon()
    bare = _pin(clone(base), props={"doc": "no pin, no intent"})
    [verdict] = gate_verdicts(diff(base, bare), bare)
    assert verdict.code == "dependency-incomplete"
    assert verdict.data["missing"] == ["edition", "sequence", "intent"]
    assert "pin knowledge base 'herbal' as a dependency" in str(verdict)
    odd = _pin(clone(base), props={**HERBAL, "intent": "borrow",
                                   "sequence": "twelve"})
    assert _codes(base, odd) == ["dependency-intent-unknown",
                                 "dependency-sequence-invalid"]
    # a change to an existing dependency is judged the same way
    pinned = _pin(clone(base))
    changed = clone(pinned)
    changed.nodes[(DEPENDENCY, "herbal")]["intent"] = "steal"
    assert _codes(pinned, changed) == ["dependency-intent-unknown"]


def test_a_bookmark_resolves_in_exactly_one_pinned_dependency():
    base = build_canon()
    unlinked = _bookmark(_pin(clone(base)), link=False)
    [verdict] = gate_verdicts(diff(base, unlinked), unlinked)
    assert verdict.code == "bookmark-unresolved"
    assert "carries no RESOLVES_IN edge" in str(verdict)
    dangling = _bookmark(clone(base))  # linked to a dependency nobody pinned
    [verdict] = gate_verdicts(diff(base, dangling), dangling)
    assert verdict.code == "bookmark-unresolved"
    assert "'herbal', which is no dependency" in str(verdict)
    assert verdict.data["dangling"] == ["herbal"]
    twice = _bookmark(_pin(_pin(clone(base), "almanac")))
    twice.edges.append(make_edge(RESOLVES_IN_EDGE, BOOKMARK,
                                 "herbal:Herb:Nightbell", DEPENDENCY,
                                 "almanac"))
    [verdict] = gate_verdicts(diff(base, twice), twice)
    assert verdict.code == "bookmark-unresolved"
    assert "2 RESOLVES_IN edges" in str(verdict)
    # the dependency named on the bookmark and the one it resolves in agree
    crossed = _bookmark(_pin(_pin(clone(base), "almanac")),
                        dependency="almanac")
    [verdict] = gate_verdicts(diff(base, crossed), crossed)
    assert verdict.code == "bookmark-dependency-mismatch"
    assert verdict.data == {"dependency": "herbal", "resolved": "almanac"}
    # the bookmark's own properties
    thin = _bookmark(_pin(clone(base)), props={"doc": "which herb?"})
    [verdict] = gate_verdicts(diff(base, thin), thin)
    assert verdict.code == "bookmark-incomplete"
    assert verdict.data["missing"] == list(BOOKMARK_REQUIRED)


def test_resolves_in_runs_only_from_bookmark_to_dependency_and_holds_it():
    base = build_canon()
    misused = _pin(clone(base))
    misused.edges.append(make_edge(RESOLVES_IN_EDGE, "Character", "Ember",
                                   DEPENDENCY, "herbal"))
    [verdict] = gate_verdicts(diff(base, misused), misused)
    assert verdict.code == "resolves-in-misused"
    assert "from a bookmark to the dependency it lives in" in str(verdict)
    # unpinning a dependency still cited refuses; retiring both together lands
    pinned = _bookmark(_pin(clone(base)))
    orphaned = clone(pinned)
    del orphaned.nodes[(DEPENDENCY, "herbal")]  # the bookmark still resolves there
    [verdict] = gate_verdicts(diff(pinned, orphaned), orphaned)
    assert verdict.code == "dependency-still-cited"
    assert verdict.data["bookmarks"] == ["herbal:Herb:Nightbell"]
    retired = clone(base)
    assert _codes(pinned, retired) == []


def test_every_code_carries_a_designer_safe_ref():
    for code in ("dependency-incomplete", "dependency-intent-unknown",
                 "dependency-sequence-invalid", "dependency-still-cited",
                 "bookmark-incomplete", "bookmark-unresolved",
                 "bookmark-dependency-mismatch", "resolves-in-misused"):
        assert code in REF_KEYS


# -- through the round -----------------------------------------------------


def test_a_pin_lands_through_a_round_and_a_bad_one_refuses(driven_kb,
                                                            monkeypatch,
                                                            capsys):
    base, fake, _ = driven_kb
    # the gate also reads the dependency's backup: a real herbal on disk,
    # pinned at what it holds
    from tests.test_dependencies_at_the_gate import _herbal
    root, identity = _herbal(base.parent)
    monkeypatch.setenv("GHOSTWHEEL_DEPENDENCY_HERBAL", str(root))
    canon = build_canon()
    fake.databases["neo4j"] = clone(canon)
    fake.databases["scratch"] = _bookmark(
        _pin(clone(canon), props={**HERBAL, "edition": identity,
                                  "sequence": 0}))
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    from graph.restore import read_export
    from tests.test_branch import export_dir
    landed = read_export(export_dir(base))
    assert (DEPENDENCY, "herbal") in landed.nodes
    assert (BOOKMARK, "herbal:Herb:Nightbell") in landed.nodes
    assert any(e.type == RESOLVES_IN_EDGE for e in landed.edges)
    # a bookmark nobody pinned refuses at the gate, by name, in the record
    fake.databases["scratch"] = _bookmark(clone(landed),
                                          name="almanac:Sky:Comet",
                                          props={**NIGHTBELL,
                                                 "dependency": "almanac"},
                                          dependency="almanac")
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 1
    record = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    codes = {row["code"] for row in record["verdicts"]}
    assert "bookmark-unresolved" in codes


# -- init --world ----------------------------------------------------------


def test_init_world_seeds_the_same_knowledge_base_plus_dependency_settings(
        tmp_path, capsys):
    plain, world = tmp_path / "hearth", tmp_path / "tale"
    assert main_mod.cmd_init(plain, name="hearth") == 0
    assert main_mod.cmd_init(world, name="tale", world=True) == 0
    from graph.restore import read_export
    seeds = [read_export(p / "graph" / "export") for p in (plain, world)]
    # nothing structural marks a world: same rows, same edges
    assert set(seeds[0].nodes) - {(ARCHETYPE_LABEL, "Ontology")} == \
        set(seeds[1].nodes) - {(ARCHETYPE_LABEL, "Ontology")}
    assert len(seeds[0].edges) == len(seeds[1].edges)
    env = (world / ".env").read_text(encoding="utf-8")
    assert "NEO4J_DATABASE=tale\n" in env
    assert f"# {main_mod.DEPENDENCY_PATH_PREFIX}<name>=" in env
    assert main_mod.DEPENDENCY_PATH_PREFIX not in \
        (plain / ".env").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "pin each dependency as a [Dependency] entry" in out
    # an existing .env is kept, and the block is shown to add by hand
    kept = tmp_path / "ember"
    kept.mkdir()
    (kept / ".env").write_text("NEO4J_DATABASE=mine\n", encoding="utf-8")
    assert main_mod.cmd_init(kept, world=True) == 0
    assert (kept / ".env").read_text(encoding="utf-8") == \
        "NEO4J_DATABASE=mine\n"
    assert "Add the dependency block by hand" in capsys.readouterr().out
    assert Path(kept / "graph" / "export" / "nodes.jsonl").exists()
