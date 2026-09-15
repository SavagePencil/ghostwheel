"""Membership confers by declared policy, and the gate queries intent.

A kind's parentage never holds automatically over its members — the
policy is canon content the gate reads, never engine code: a `confers`
mark on the kind's own SUBTYPE_OF link declares that membership below
flows through it, hop by hop (an unmarked link stops the climb), and
a member that is the exception declines the parent on its own
membership edge. The gate speaks both sides aloud: a conferring link
announces what the member becomes and names the decline road; an
unmarked link asks the intent question and names the direct-declaration
road. Nothing confers unstated — a knowledge base with no policy
derives exactly as before.

Storybook domain: Pip's heirloom blade, and what a blade is a kind of.
"""

from graph.delta import (Delta, ceremony_records, lint_verdicts,
                         membership_advisories)
from graph.extract import derive, make_edge, strip_derived
from graph.ontology import (ARCHETYPE_LABEL, CONCEPT_ROOT,
                            ontology_from_graph)
from tests.test_branch import build_canon

MEMBER = "DECLARED_MEMBER_OF"


def _concept(canon, name):
    canon.ensure_node(ARCHETYPE_LABEL, name, doc="a concept of the tale")
    canon.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, CONCEPT_ROOT))


def _taxonomy(canon, kind, parent, confers=False):
    props = {"confers": True} if confers else None
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, kind,
                                 ARCHETYPE_LABEL, parent, props))


def _membership(kind, declines=None, citizen="Pip"):
    props = {"basis": "the owner's ruling"}
    if declines:
        props["declines"] = declines
    return make_edge(MEMBER, "Character", citizen,
                     ARCHETYPE_LABEL, kind, props)


def _world(confers_heirloom=False, confers_tool=False,
           confers_treasure=False):
    canon = build_canon()
    for name in ("Blade", "Heirloom", "Tool", "Treasure"):
        _concept(canon, name)
    _taxonomy(canon, "Blade", "Heirloom", confers=confers_heirloom)
    _taxonomy(canon, "Blade", "Tool", confers=confers_tool)
    _taxonomy(canon, "Heirloom", "Treasure", confers=confers_treasure)
    return canon


def _instance_targets(derived, citizen="Pip"):
    return {str(e.to_name) for e in derived.edges
            if e.type == "INSTANCE_OF"
            and (e.from_label, str(e.from_name)) == ("Character", citizen)}


def _derive(canon, tmp_path):
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    return derived


def test_no_policy_derives_only_the_kind(tmp_path):
    # the probe's shape, pinned: unmarked links never climb
    canon = _world()
    canon.edges.append(_membership("Blade"))
    targets = _instance_targets(_derive(canon, tmp_path))
    assert "Blade" in targets
    assert "Heirloom" not in targets and "Tool" not in targets


def test_a_marked_link_confers_and_its_sibling_does_not(tmp_path):
    canon = _world(confers_heirloom=True)
    canon.edges.append(_membership("Blade"))
    targets = _instance_targets(_derive(canon, tmp_path))
    assert "Heirloom" in targets
    assert "Tool" not in targets


def test_the_climb_is_policy_gated_hop_by_hop(tmp_path):
    # a marked upper link continues the climb; unmarked, it stops
    marked = _world(confers_heirloom=True, confers_treasure=True)
    marked.edges.append(_membership("Blade"))
    assert "Treasure" in _instance_targets(_derive(marked, tmp_path))
    stopped = _world(confers_heirloom=True)
    stopped.edges.append(_membership("Blade"))
    assert "Treasure" not in _instance_targets(_derive(stopped, tmp_path))


def test_a_decline_cuts_its_parent_and_the_climb_through_it(tmp_path):
    canon = _world(confers_heirloom=True, confers_tool=True,
                   confers_treasure=True)
    canon.edges.append(_membership("Blade", declines="Heirloom"))
    targets = _instance_targets(_derive(canon, tmp_path))
    assert "Heirloom" not in targets
    assert "Treasure" not in targets  # only reachable through the cut
    assert "Tool" in targets          # the sibling conferral stands


def test_an_unknown_decline_refuses_by_name(tmp_path):
    canon = _world(confers_heirloom=True)
    delta = Delta()
    # Tool's link does not confer — a decline answers a conferral
    # that exists
    delta.edges_added.append(_membership("Blade", declines="Tool"))
    faults = [v for v in lint_verdicts(delta, canon)
              if v.code == "membership-decline-unknown"]
    [fault] = faults
    assert "Tool" in fault.message
    # declining the conferral that exists is clean
    delta2 = Delta()
    delta2.edges_added.append(_membership("Blade", declines="Heirloom"))
    assert [v for v in lint_verdicts(delta2, canon)
            if v.code == "membership-decline-unknown"] == []


def test_the_gate_announces_the_conferral_with_the_decline_road(tmp_path):
    canon = _world(confers_heirloom=True)
    delta = Delta()
    delta.edges_added.append(_membership("Blade"))
    items, _v, _n, _e = ceremony_records(delta, canon)
    lines = [i for i in items if i.code == "membership-confers"]
    [line] = lines
    assert "Pip" in line.message and "Heirloom" in line.message
    assert "decline" in line.message.lower()
    # a declined parent is answered — no announcement for it
    delta2 = Delta()
    delta2.edges_added.append(_membership("Blade", declines="Heirloom"))
    items2, _v, _n, _e = ceremony_records(delta2, canon)
    assert [i for i in items2 if i.code == "membership-confers"] == []


def test_the_gate_asks_the_intent_question_on_an_unmarked_link(tmp_path):
    canon = _world(confers_heirloom=True)
    delta = Delta()
    delta.edges_added.append(_membership("Blade"))
    advisories = membership_advisories(delta, canon)
    open_lines = [a for a in advisories
                  if a.code == "membership-intent-open"]
    [line] = open_lines
    assert "Tool" in line.message
    assert "declare it directly" in line.message.lower()


def test_the_confers_declaration_counts_its_members(tmp_path):
    # the mark lands on an existing link: the ceremony line counts the
    # citizens that actually confer — and a decline is subtracted
    canon = _world()
    canon.edges.append(_membership("Blade"))
    canon.edges.append(_membership("Blade", citizen="Maren",
                                   declines="Heirloom"))
    delta = Delta()
    changed = make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, "Blade",
                        ARCHETYPE_LABEL, "Heirloom", {"confers": True})
    delta.edges_changed.append((changed, {"confers": (None, True)}))
    items, violations, _n, _e = ceremony_records(delta, canon)
    assert not [v for v in violations if v.code == "schema-edge-modified"]
    [line] = [i for i in items if i.code == "taxonomy-confers"]
    assert "1" in line.message and "Heirloom" in line.message
    assert line.data["matches"] == 1
    # the lint admits the confers-only edit too
    assert not [v for v in lint_verdicts(delta, canon)
                if v.code == "schema-edge-modified"]


def test_fixpoint_holds_and_the_double_declaration_folds_to_one(tmp_path):
    canon = _world(confers_heirloom=True)
    canon.edges.append(_membership("Blade"))
    canon.edges.append(_membership("Heirloom"))  # the doubled idiom
    once = _derive(canon, tmp_path)
    rows = [e for e in once.edges if e.type == "INSTANCE_OF"
            and (e.from_label, str(e.from_name)) == ("Character", "Pip")
            and str(e.to_name) == "Heirloom"]
    assert len(rows) == 1
    twice = _derive(strip_derived(once), tmp_path)
    assert _instance_targets(twice) == _instance_targets(once)
