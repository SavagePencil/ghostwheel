"""The custody road joins verification: scheme-routed, depot-home base.

Verification follows the SCHEME, not the label: the file kind rides
the KB home exactly as ever, and the depot scheme rides the same road
with the depot home as base — by convention the KB's own home, the
environment overriding for unusual layouts. First touch RECORDS the
fingerprint (the stamp's normal behavior), the sweep VERIFIES forever
after (verified → stale, the decay signal), an unreadable file at
apply refuses collated, and a source URL stays unverifiable by design
— no fetch inside a gate.

Storybook domain: the gallery holds its plates' bytes.
"""

import hashlib

from graph.artifacts import (VERIFIED_FINGERPRINT, location_rows,
                             verification_stamp)
from graph.extract import make_edge
from graph.ontology import KERNEL_ARTIFACT_LABEL
from tests.test_branch import build_canon

ART = KERNEL_ARTIFACT_LABEL
CUSTODY = "[Custody Location]"


def _declare_kind(canon, kind):
    from graph.ontology import ARCHETYPE_LABEL
    canon.ensure_node(ARCHETYPE_LABEL, kind, doc="a location kind")
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL, kind,
                                 ARCHETYPE_LABEL, "[Artifact Location]"))


def _held(canon, tmp_path, address="depot/plate.png", data=b"the plate",
          scheme="git-lfs", name="the plate (held)"):
    _declare_kind(canon, CUSTODY)
    path = tmp_path / address
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    canon.ensure_node(ART, "the plate", description="sketches")
    canon.ensure_node(CUSTODY, name, scheme=scheme, address=address,
                      primary=True, pinned_commit="abc123def")
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 CUSTODY, name))
    return path


def test_the_custody_scheme_stamps_against_the_kb_home(tmp_path):
    canon = build_canon()
    _held(canon, tmp_path)
    problems = verification_stamp(canon, tmp_path, 7,
                                  [(ART, "the plate")])
    assert problems == []
    row = canon.nodes[(CUSTODY, "the plate (held)")]
    assert row[VERIFIED_FINGERPRINT] == \
        hashlib.sha256(b"the plate").hexdigest()
    assert row["size"] == len(b"the plate")
    # pinned_commit rides untouched — provenance, never load-bearing
    assert row["pinned_commit"] == "abc123def"


def test_the_environment_override_names_the_depot_home(tmp_path,
                                                       monkeypatch):
    canon = build_canon()
    elsewhere = tmp_path / "the-shelf"
    (elsewhere / "depot").mkdir(parents=True)
    (elsewhere / "depot" / "plate.png").write_bytes(b"held bytes")
    canon.ensure_node(ART, "the plate", description="sketches")
    canon.ensure_node(CUSTODY, "the plate (held)", scheme="git-lfs",
                      address="depot/plate.png", primary=True)
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 CUSTODY, "the plate (held)"))
    monkeypatch.setenv("GHOSTWHEEL_DEPOT_BASE", str(elsewhere))
    kb_home = tmp_path / "kb"
    kb_home.mkdir()
    assert verification_stamp(canon, kb_home, 3,
                              [(ART, "the plate")]) == []
    row = canon.nodes[(CUSTODY, "the plate (held)")]
    assert row[VERIFIED_FINGERPRINT] == \
        hashlib.sha256(b"held bytes").hexdigest()


def test_the_confinement_guard_holds_on_the_custody_road(tmp_path):
    canon = build_canon()
    canon.ensure_node(ART, "the plate", description="sketches")
    canon.ensure_node(CUSTODY, "the escape", scheme="git-lfs",
                      address="../outside.png", primary=True)
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 CUSTODY, "the escape"))
    problems = verification_stamp(canon, tmp_path, 1,
                                  [(ART, "the plate")])
    [problem] = problems
    assert "outside" in problem
    assert VERIFIED_FINGERPRINT not in canon.nodes[(CUSTODY, "the escape")]


def test_first_touch_records_and_the_sweep_verifies(tmp_path):
    canon = build_canon()
    path = _held(canon, tmp_path)
    # before any stamp: unverified, never unverifiable
    [row] = [r for r in location_rows(canon, tmp_path)
             if r["kind"] == CUSTODY]
    assert row["status"] == "unverified"
    assert verification_stamp(canon, tmp_path, 7,
                              [(ART, "the plate")]) == []
    [row] = [r for r in location_rows(canon, tmp_path)
             if r["kind"] == CUSTODY]
    assert row["status"] == "verified"
    # the bytes drift: the sweep reads stale — a finding, the decay
    # signal, never a refusal
    path.write_bytes(b"retouched")
    [row] = [r for r in location_rows(canon, tmp_path)
             if r["kind"] == CUSTODY]
    assert row["status"] == "stale"
    assert row["recorded"] != row["actual"]


def test_an_unreadable_custody_file_refuses_apply_collated(tmp_path):
    canon = build_canon()
    good = _held(canon, tmp_path)
    canon.ensure_node(CUSTODY, "the missing", scheme="git-lfs",
                      address="depot/gone.png", primary=False)
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 CUSTODY, "the missing"))
    problems = verification_stamp(canon, tmp_path, 2,
                                  [(ART, "the plate")])
    assert problems and "gone.png" in problems[0]
    # verify-all before apply-any: the readable sibling stayed unstamped
    assert VERIFIED_FINGERPRINT not in canon.nodes[
        (CUSTODY, "the plate (held)")]
    assert good.exists()


def test_a_source_url_stays_unverifiable_by_design(tmp_path):
    canon = build_canon()
    canon.ensure_node(ART, "the plate", description="sketches")
    _declare_kind(canon, "[Artifact Location]")
    canon.ensure_node("[Artifact Location]", "the plate (source)",
                      scheme="https", address="https://example.test/p",
                      primary=False)
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 "[Artifact Location]",
                                 "the plate (source)"))
    [row] = [r for r in location_rows(canon, tmp_path)
             if r["kind"] == "[Artifact Location]"]
    assert row["status"] == "unverifiable"
    assert verification_stamp(canon, tmp_path, 1,
                              [(ART, "the plate")]) == []


def test_the_file_road_is_byte_identical(tmp_path):
    from graph.ontology import KERNEL_FILE_LOCATION_LABEL as FILE
    canon = build_canon()
    (tmp_path / "art").mkdir()
    (tmp_path / "art" / "p.png").write_bytes(b"file bytes")
    canon.ensure_node(ART, "the plate", description="sketches")
    canon.ensure_node(FILE, "the plate (file)", scheme="file",
                      address="art/p.png", primary=True)
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 FILE, "the plate (file)"))
    assert verification_stamp(canon, tmp_path, 5,
                              [(ART, "the plate")]) == []
    row = canon.nodes[(FILE, "the plate (file)")]
    assert row[VERIFIED_FINGERPRINT] == \
        hashlib.sha256(b"file bytes").hexdigest()
    assert canon.nodes[(ART, "the plate")]["fingerprint"] == \
        row[VERIFIED_FINGERPRINT]
