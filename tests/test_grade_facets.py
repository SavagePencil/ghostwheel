"""An artifact's grade is two facets, graded independently.

What the SOURCE SAYS (provenance_known_at: the documentary chain,
which decays as links rot — the verification sweep's stale readings
are its signal) and what was EXAMINED (examined_known_at: what eyes-on
inspection confirmed at a gate, which does not age). Each facet rides
the Completeness ladder; the earning rules live where they always
meant to — eyes-on earns the examined facet, a checked chain earns the
provenance facet — and a legacy single grade reads asymmetrically by
what it meant: Cited was metadata-derived (the provenance facet),
Attested was always eyes-on (the examined facet).

Storybook domain: a plate of sketches, graded honestly.
"""

from graph.artifacts import (VERIFIED_FINGERPRINT, gate_verdicts,
                             legacy_grade_advisories)
from graph.delta import Delta
from graph.extract import make_edge
from graph.ontology import KERNEL_ARTIFACT_LABEL, KERNEL_FILE_LOCATION_LABEL
from tests.test_branch import build_canon

ART = KERNEL_ARTIFACT_LABEL


def _plate(canon, **props):
    canon.ensure_node(ART, "the plate", **props)
    delta = Delta()
    delta.nodes_changed.append((ART, "the plate", {"doc": ("", "touched")}))
    return delta


def _verdicts(canon, delta, tmp_path, code=None):
    found = gate_verdicts(delta, canon, tmp_path)
    return [v for v in found if code is None or v.code == code]


def test_each_facet_validates_its_vocabulary(tmp_path):
    canon = build_canon()
    delta = _plate(canon, provenance_known_at="Rumored",
                   examined_known_at="Glimpsed")
    faults = _verdicts(canon, delta, tmp_path, "artifact-grade-unknown")
    assert len(faults) == 2
    text = " ".join(v.message for v in faults)
    assert "Rumored" in text and "Glimpsed" in text
    assert "source says" in text and "examined" in text


def test_transcribed_stays_parked_on_both_facets(tmp_path):
    canon = build_canon()
    delta = _plate(canon, provenance_known_at="Transcribed")
    assert _verdicts(canon, delta, tmp_path, "artifact-grade-parked")
    canon2 = build_canon()
    delta2 = _plate(canon2, examined_known_at="Transcribed")
    assert _verdicts(canon2, delta2, tmp_path, "artifact-grade-parked")


def test_examined_attested_keeps_the_eyes_on_earning(tmp_path):
    canon = build_canon()
    delta = _plate(canon, examined_known_at="Attested")
    [fault] = _verdicts(canon, delta, tmp_path, "artifact-grade-unearned")
    assert "description" in fault.message
    # earned: description + a confirmed depiction
    canon2 = build_canon()
    delta2 = _plate(canon2, examined_known_at="Attested",
                    description="sketches of the vale")
    canon2.edges.append(make_edge("DEPICTS", ART, "the plate",
                                  "Character", "Pip"))
    assert _verdicts(canon2, delta2, tmp_path,
                     "artifact-grade-unearned") == []


def test_provenance_attested_needs_a_checked_chain(tmp_path):
    canon = build_canon()
    delta = _plate(canon, provenance_known_at="Attested")
    [fault] = _verdicts(canon, delta, tmp_path, "artifact-grade-unearned")
    assert "verif" in fault.message.lower()
    # earned: a location row the engine verified
    canon2 = build_canon()
    delta2 = _plate(canon2, provenance_known_at="Attested")
    canon2.ensure_node(KERNEL_FILE_LOCATION_LABEL, "the plate (file)",
                       scheme="file", address="art/plate.png",
                       primary=True,
                       **{VERIFIED_FINGERPRINT: "abc123", "size": 9})
    canon2.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                  KERNEL_FILE_LOCATION_LABEL,
                                  "the plate (file)"))
    assert _verdicts(canon2, delta2, tmp_path,
                     "artifact-grade-unearned") == []


def test_legacy_grades_read_by_what_they_meant(tmp_path):
    # a legacy Cited was metadata-derived: the provenance facet — so a
    # legacy-Cited artifact claiming nothing examined earns no examined
    # checks and no provenance-Attested checks either
    canon = build_canon()
    delta = _plate(canon, known_at="Cited")
    assert _verdicts(canon, delta, tmp_path,
                     "artifact-grade-unearned") == []
    # a legacy Attested was ALWAYS eyes-on: the examined facet — its
    # earning rule (description + depiction) applies exactly as before
    canon2 = build_canon()
    delta2 = _plate(canon2, known_at="Attested")
    [fault] = _verdicts(canon2, delta2, tmp_path,
                        "artifact-grade-unearned")
    assert "description" in fault.message
    # the new props win when both are present
    canon3 = build_canon()
    delta3 = _plate(canon3, known_at="Attested",
                    provenance_known_at="Cited",
                    examined_known_at="Cited")
    assert _verdicts(canon3, delta3, tmp_path,
                     "artifact-grade-unearned") == []


def test_a_touched_legacy_artifact_hears_the_split_advisory(tmp_path):
    canon = build_canon()
    delta = _plate(canon, known_at="Cited")
    [advisory] = legacy_grade_advisories(delta, canon)
    assert advisory.code == "grade-facet-legacy"
    assert "the plate" in advisory.message
    assert "source says" in advisory.message  # names the facet it reads as
    # an artifact already split hears nothing
    canon2 = build_canon()
    delta2 = _plate(canon2, provenance_known_at="Cited")
    assert legacy_grade_advisories(delta2, canon2) == []
