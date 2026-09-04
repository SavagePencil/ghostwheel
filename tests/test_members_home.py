"""Members and bookmarks: the kernel's vocabulary for one knowledge
base mounting another and citing a citizen that lives there.

Kernel 0.15.0 declares two Provenance-rooted machinery concepts —
bracketed, because a designer never authors either as subject matter.
A [Member] pins a mounted knowledge base to an edition with a read or
write intent; a [Bookmark] names a citizen in a member with exactly one
IN_MEMBER edge to it. The delta gate checks their SHAPE; resolution
against the member's backup is the next rung. `init --world` seeds the
same knowledge base plus the member settings block — a world is a role,
never a type.

Storybook domain: the tale mounts a herbal it cites for Nightbell.
"""

import json
from pathlib import Path

import graph.__main__ as main_mod
from graph.delta import diff
from graph.extract import make_edge
from graph.kernel_migrate import fresh_kernel
from graph.members import (BOOKMARK_REQUIRED, IN_MEMBER_EDGE,
                           MEMBER_REQUIRED, gate_verdicts)
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_BOOKMARK_LABEL,
                            KERNEL_MEMBER_LABEL)
from graph.report import REF_KEYS, record_path
from tests.test_branch import build_canon, clone, driven_kb  # noqa: F401

MEMBER, BOOKMARK = KERNEL_MEMBER_LABEL, KERNEL_BOOKMARK_LABEL
HERBAL = {"edition": "a" * 64, "sequence": 12, "intent": "read",
          "ref": "v3.0.0", "doc": "the herbal this tale consults"}
NIGHTBELL = {"member": "herbal", "citizen_label": "Herb",
             "citizen_name": "Nightbell", "edition": "a" * 64,
             "doc": "the herb the tale's tea is made of"}


def _mount(graph, member="herbal", props=HERBAL):
    graph.ensure_node(MEMBER, member, **dict(props))
    return graph


def _bookmark(graph, name="herbal:Herb:Nightbell", props=NIGHTBELL,
              member="herbal", link=True):
    graph.ensure_node(BOOKMARK, name, **dict(props))
    if link:
        graph.edges.append(make_edge(IN_MEMBER_EDGE, BOOKMARK, name,
                                     MEMBER, member))
    return graph


def _codes(base, scratch):
    return sorted(v.code for v in gate_verdicts(diff(base, scratch), scratch))


# -- the kernel declares them ---------------------------------------------


def test_the_kernel_declares_both_under_provenance_bracketed(tmp_path):
    seed, findings = fresh_kernel(tmp_path)
    assert seed is not None, findings
    for label in (MEMBER, BOOKMARK):
        assert label.startswith("[") and label.endswith("]")
        assert (ARCHETYPE_LABEL, label) in seed.nodes
        parents = {e.to_name for e in seed.edges
                   if e.type == "INSTANCE_OF"
                   and (e.from_label, e.from_name) == (ARCHETYPE_LABEL, label)}
        assert parents == {"Provenance"}
        assert any(e.type == "DECLARED_IN" and e.to_name == "Metaontology"
                   and e.from_name == label for e in seed.edges)
    assert MEMBER_REQUIRED == ("edition", "sequence", "intent")
    assert BOOKMARK_REQUIRED == ("member", "citizen_label", "citizen_name",
                                 "edition")


# -- the shape at the gate -------------------------------------------------


def test_a_well_formed_mount_and_bookmark_pass():
    base = build_canon()
    scratch = _bookmark(_mount(clone(base)))
    assert _codes(base, scratch) == []
    # a bookmark on a member the BASE already holds passes the same way
    base2 = _mount(clone(base))
    assert _codes(base2, _bookmark(clone(base2))) == []
    # and a domain citizen pointing at the bookmark is ordinary ground
    scratch.edges.append(make_edge("BREWS_FROM", "Character", "Ember",
                                   BOOKMARK, "herbal:Herb:Nightbell"))
    assert _codes(base, scratch) == []


def test_a_member_refuses_by_name_when_malformed():
    base = build_canon()
    bare = _mount(clone(base), props={"doc": "no pin, no intent"})
    [verdict] = gate_verdicts(diff(base, bare), bare)
    assert verdict.code == "member-incomplete"
    assert verdict.data["missing"] == ["edition", "sequence", "intent"]
    assert "mount knowledge base 'herbal'" in str(verdict)
    odd = _mount(clone(base), props={**HERBAL, "intent": "borrow",
                                     "sequence": "twelve"})
    assert _codes(base, odd) == ["member-intent-unknown",
                                 "member-sequence-invalid"]
    # a change to an existing member is judged the same way
    mounted = _mount(clone(base))
    changed = clone(mounted)
    changed.nodes[(MEMBER, "herbal")]["intent"] = "steal"
    assert _codes(mounted, changed) == ["member-intent-unknown"]


def test_a_bookmark_lives_in_exactly_one_mounted_member():
    base = build_canon()
    unlinked = _bookmark(_mount(clone(base)), link=False)
    [verdict] = gate_verdicts(diff(base, unlinked), unlinked)
    assert verdict.code == "bookmark-unmounted"
    assert "carries no IN_MEMBER edge" in str(verdict)
    dangling = _bookmark(clone(base))  # linked to a member nobody mounted
    [verdict] = gate_verdicts(diff(base, dangling), dangling)
    assert verdict.code == "bookmark-unmounted"
    assert "'herbal', which is no member" in str(verdict)
    assert verdict.data["dangling"] == ["herbal"]
    twice = _bookmark(_mount(_mount(clone(base), "almanac")))
    twice.edges.append(make_edge(IN_MEMBER_EDGE, BOOKMARK,
                                 "herbal:Herb:Nightbell", MEMBER, "almanac"))
    [verdict] = gate_verdicts(diff(base, twice), twice)
    assert verdict.code == "bookmark-unmounted"
    assert "2 IN_MEMBER edges" in str(verdict)
    # the member named on the bookmark and the member it mounts on agree
    crossed = _bookmark(_mount(_mount(clone(base), "almanac")),
                        member="almanac")
    [verdict] = gate_verdicts(diff(base, crossed), crossed)
    assert verdict.code == "bookmark-member-mismatch"
    assert verdict.data == {"member": "herbal", "mounted": "almanac"}
    # the bookmark's own properties
    thin = _bookmark(_mount(clone(base)), props={"doc": "which herb?"})
    [verdict] = gate_verdicts(diff(base, thin), thin)
    assert verdict.code == "bookmark-incomplete"
    assert verdict.data["missing"] == list(BOOKMARK_REQUIRED)


def test_in_member_runs_only_from_bookmark_to_member_and_holds_a_member():
    base = build_canon()
    misused = _mount(clone(base))
    misused.edges.append(make_edge(IN_MEMBER_EDGE, "Character", "Ember",
                                   MEMBER, "herbal"))
    [verdict] = gate_verdicts(diff(base, misused), misused)
    assert verdict.code == "in-member-misused"
    assert "from a bookmark to the member it lives in" in str(verdict)
    # unmounting a member still cited refuses; retiring both together lands
    mounted = _bookmark(_mount(clone(base)))
    orphaned = clone(mounted)
    del orphaned.nodes[(MEMBER, "herbal")]  # the bookmark still points there
    [verdict] = gate_verdicts(diff(mounted, orphaned), orphaned)
    assert verdict.code == "member-still-cited"
    assert verdict.data["bookmarks"] == ["herbal:Herb:Nightbell"]
    retired = clone(base)
    assert _codes(mounted, retired) == []


def test_every_code_carries_a_designer_safe_ref():
    for code in ("member-incomplete", "member-intent-unknown",
                 "member-sequence-invalid", "member-still-cited",
                 "bookmark-incomplete", "bookmark-unmounted",
                 "bookmark-member-mismatch", "in-member-misused"):
        assert code in REF_KEYS


# -- through the round -----------------------------------------------------


def test_a_mount_lands_through_a_round_and_a_bad_one_refuses(driven_kb,
                                                              capsys):
    base, fake, _ = driven_kb
    canon = build_canon()
    fake.databases["neo4j"] = clone(canon)
    fake.databases["scratch"] = _bookmark(_mount(clone(canon)))
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    from graph.restore import read_export
    from tests.test_branch import export_dir
    landed = read_export(export_dir(base))
    assert (MEMBER, "herbal") in landed.nodes
    assert (BOOKMARK, "herbal:Herb:Nightbell") in landed.nodes
    assert any(e.type == IN_MEMBER_EDGE for e in landed.edges)
    # a bookmark nobody mounted refuses at the gate, by name, in the record
    fake.databases["scratch"] = _bookmark(clone(landed),
                                          name="almanac:Sky:Comet",
                                          props={**NIGHTBELL,
                                                 "member": "almanac"},
                                          member="almanac")
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 1
    record = json.loads(record_path(base, "delta-report.json")
                        .read_text(encoding="utf-8"))
    codes = {row["code"] for row in record["verdicts"]}
    assert "bookmark-unmounted" in codes


# -- init --world ----------------------------------------------------------


def test_init_world_seeds_the_same_knowledge_base_plus_member_settings(
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
    assert f"# {main_mod.MEMBER_PATH_PREFIX}<name>=" in env
    assert main_mod.MEMBER_PATH_PREFIX not in \
        (plain / ".env").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "mount each member as a [Member] entry" in out
    # an existing .env is kept, and the block is shown to add by hand
    kept = tmp_path / "ember"
    kept.mkdir()
    (kept / ".env").write_text("NEO4J_DATABASE=mine\n", encoding="utf-8")
    assert main_mod.cmd_init(kept, world=True) == 0
    assert (kept / ".env").read_text(encoding="utf-8") == \
        "NEO4J_DATABASE=mine\n"
    assert "Add the member block by hand" in capsys.readouterr().out
    assert Path(kept / "graph" / "export" / "nodes.jsonl").exists()
