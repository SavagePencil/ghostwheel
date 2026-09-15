"""Foreign depiction: DEPICTS honors the citizen-bookmark citation.

An artifact may depict a citizen that lives in another knowledge base:
the DEPICTS edge targets a [Citizen Bookmark], and everywhere the
machinery READS "the depicted citizen" the bookmarked target means the
foreign citizen the bookmark names — the derived interpretation
carries the foreign name, the earning rule counts the pairing, the
advisories speak "{name} (in {kb})", and depictions aggregate at
foreign-identity grain so two bookmark rows citing one citizen read
as one subject. Everything the machinery WRITES stays inside the
local graph, landing on the bookmark row. A bookmark-free graph is
byte-identical.

Storybook domain: a plate of sketches depicting a neighbor's kettle.
"""

from graph.artifacts import depiction_advisories, gate_verdicts
from graph.dependencies import RESOLVES_IN_EDGE
from graph.extract import derive, make_edge, strip_derived
from graph.delta import Delta
from graph.ontology import (KERNEL_ARTIFACT_LABEL, KERNEL_BOOKMARK_LABEL,
                            KERNEL_DEPENDENCY_LABEL,
                            KERNEL_INTERPRETATION_LABEL,
                            ontology_from_graph)
from tests.test_branch import build_canon

ART = KERNEL_ARTIFACT_LABEL
INTERP = KERNEL_INTERPRETATION_LABEL
MARKER = "derived_from"


def _bookmarked(canon, bm_name="hearthfall:Tool:Hearth Kettle",
                citizen="Hearth Kettle"):
    canon.ensure_node(KERNEL_DEPENDENCY_LABEL, "hearthfall",
                      edition="a" * 64, sequence=3, intent="read")
    canon.ensure_node(KERNEL_BOOKMARK_LABEL, bm_name,
                      dependency="hearthfall", citizen_label="Tool",
                      citizen_name=citizen, edition="a" * 64)
    canon.edges.append(make_edge(RESOLVES_IN_EDGE, KERNEL_BOOKMARK_LABEL,
                                 bm_name, KERNEL_DEPENDENCY_LABEL,
                                 "hearthfall"))
    return bm_name


def _with_plate(role: "str | None" = "primary"):
    canon = build_canon()
    bm = _bookmarked(canon)
    canon.ensure_node(ART, "the plate", known_at="Cited",
                      description="sketches of a neighbor's kettle")
    props = {"role": role} if role else None
    canon.edges.append(make_edge("DEPICTS", ART, "the plate",
                                 KERNEL_BOOKMARK_LABEL, bm, props))
    return canon, bm


def _derived(canon, tmp_path):
    derived, _ = derive(ontology_from_graph(canon, tmp_path), canon)
    return derived


def test_a_bookmarked_depiction_passes_the_gate(tmp_path):
    canon, bm = _with_plate()
    delta = Delta()
    delta.nodes_changed.append((ART, "the plate", {"doc": ("", "t")}))
    codes = {v.code for v in gate_verdicts(delta, canon, tmp_path)}
    assert "depicts-target-missing" not in codes
    assert "artifact-edge-misused" not in codes


def test_the_earning_rule_counts_a_bookmarked_pairing(tmp_path):
    canon, _bm = _with_plate()
    canon.nodes[(ART, "the plate")]["examined_known_at"] = "Attested"
    delta = Delta()
    delta.nodes_changed.append((ART, "the plate", {"doc": ("", "t")}))
    assert [v for v in gate_verdicts(delta, canon, tmp_path)
            if v.code == "artifact-grade-unearned"] == []


def test_the_derived_interpretation_carries_the_foreign_name(tmp_path):
    canon, bm = _with_plate()
    derived = _derived(canon, tmp_path)
    key = (INTERP, "the plate as Hearth Kettle reference")
    assert key in derived.nodes
    assert derived.nodes[key]["intent"] == \
        "reference image for Hearth Kettle"
    edges = {(e.type, e.to_label, str(e.to_name)) for e in derived.edges
             if (e.from_label, str(e.from_name)) == key}
    assert ("ABOUT", ART, "the plate") in edges
    # the writes stay local: the bookmark row is the stand-in
    assert ("INTERPRETED_AS", KERNEL_BOOKMARK_LABEL, bm) in edges
    assert ("DRAWS_ON", KERNEL_BOOKMARK_LABEL, bm) in edges


def test_the_fixpoint_holds_over_the_bookmarked_shape(tmp_path):
    canon, _bm = _with_plate()
    once = _derived(canon, tmp_path)
    twice = _derived(strip_derived(once), tmp_path)
    assert set(twice.nodes) == set(once.nodes)


def test_advisories_speak_the_foreign_name_and_its_home(tmp_path):
    canon, bm = _with_plate(role=None)
    delta = Delta()
    delta.edges_added.append(make_edge("DEPICTS", ART, "the plate",
                                       KERNEL_BOOKMARK_LABEL, bm,
                                       {"role": "primary"}))
    advisories = depiction_advisories(delta, canon)
    [line] = [a for a in advisories if a.code == "reference-correlated"]
    assert "'Hearth Kettle' (in hearthfall)" in line.message
    assert bm not in line.message  # the row name is machinery, not voice


def test_second_primary_groups_at_foreign_identity_grain(tmp_path):
    # two bookmark rows citing ONE foreign citizen: a second primary
    # through the other row is the SAME subject gaining its second
    # reference
    canon, _bm = _with_plate()
    other = _bookmarked(canon, bm_name="the kettle next door")
    canon.ensure_node(ART, "the second plate", known_at="Cited")
    delta = Delta()
    delta.edges_added.append(make_edge("DEPICTS", ART, "the second plate",
                                       KERNEL_BOOKMARK_LABEL, other,
                                       {"role": "primary"}))
    seconds = [a for a in depiction_advisories(delta, canon)
               if a.code == "second-primary-reference"]
    [second] = seconds
    assert "Hearth Kettle" in second.message
    # …and a LOCAL namesake is a different subject entirely
    canon2, _bm2 = _with_plate()
    canon2.ensure_node("Tool", "Hearth Kettle", brews_tea=True)
    canon2.ensure_node(ART, "the second plate", known_at="Cited")
    delta2 = Delta()
    delta2.edges_added.append(make_edge("DEPICTS", ART,
                                        "the second plate", "Tool",
                                        "Hearth Kettle",
                                        {"role": "primary"}))
    assert [a for a in depiction_advisories(delta2, canon2)
            if a.code == "second-primary-reference"] == []


def test_a_bookmark_free_graph_is_byte_identical(tmp_path):
    canon = build_canon()
    canon.ensure_node(ART, "the plate", known_at="Cited",
                      description="sketches")
    canon.edges.append(make_edge("DEPICTS", ART, "the plate",
                                 "Character", "Pip", {"role": "primary"}))
    derived = _derived(canon, tmp_path)
    assert (INTERP, "the plate as Pip reference") in derived.nodes
