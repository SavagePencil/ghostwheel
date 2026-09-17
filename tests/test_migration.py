"""The migration ceremony: citizens change worlds, verbatim.

Two verbs, one content-addressed record, ordinary pocket rounds. The
record carries every leaving citizen and connection with properties
whole; the source's round removes them and rewrites every staying
reference into a bookmark toward the destination; the destination's
round adds them byte-identical and rewrites every moved reference
into a bookmark back. The ordering law — arrive, re-pin, leave — is
enforced by the citation stack's own resolution gate: an emigration's
bookmarks cannot resolve until the destination's pinned edition holds
the arrivals. Derived rows never ride; they re-derive at the
destination, where the foreign-name derivation takes over.

Storybook domain: the plate of sketches emigrates to the gallery.
"""

import json

from graph.dependencies import RESOLVES_IN_EDGE
from graph.delta import Delta, diff
from graph.extract import GraphData, make_edge
from graph.migration import (build_record, emigrate_stage,
                             immigrate_stage, migration_verdicts,
                             record_id)
from graph.ontology import (KERNEL_ARTIFACT_LABEL, KERNEL_BOOKMARK_LABEL,
                            KERNEL_DEPENDENCY_LABEL,
                            KERNEL_FILE_LOCATION_LABEL,
                            KERNEL_INTERPRETATION_LABEL)
from tests.test_branch import build_canon, clone

ART = KERNEL_ARTIFACT_LABEL
LOC = KERNEL_FILE_LOCATION_LABEL
INTERP = KERNEL_INTERPRETATION_LABEL


def _source_world():
    """The source: one artifact family (location + hand interpretation
    + a depicted local citizen), a derived row that must stay home, and
    a mutual pin toward the gallery."""
    canon = build_canon()
    canon.ensure_node(KERNEL_DEPENDENCY_LABEL, "gallery",
                      edition="g" * 64, sequence=4, intent="read")
    canon.ensure_node(ART, "the plate", known_at="Cited",
                      provenance_known_at="Cited",
                      description="sketches of the vale")
    canon.ensure_node(LOC, "the plate (file)", scheme="file",
                      address="art/plate.png", primary=True,
                      verified_fingerprint="abc123", size=9)
    canon.ensure_node(INTERP, "the vale study",
                      intent="the owner's own reading")
    canon.ensure_node(INTERP, "a machine reading",
                      intent="boilerplate", derived_from="primary depiction")
    canon.edges.append(make_edge("LOCATED_AT", ART, "the plate",
                                 LOC, "the plate (file)"))
    canon.edges.append(make_edge("DEPICTS", ART, "the plate",
                                 "Character", "Pip", {"role": "primary"}))
    canon.edges.append(make_edge("ABOUT", INTERP, "the vale study",
                                 ART, "the plate"))
    canon.edges.append(make_edge("ABOUT", INTERP, "a machine reading",
                                 ART, "the plate"))
    # a staying citizen referencing a mover: the inbound edge that must
    # be rewritten toward the gallery
    canon.edges.append(make_edge("DRAWS_ON", INTERP, "the vale study",
                                 "Character", "Pip"))
    return canon


def _record(canon):
    record, problems = build_record(canon, [(ART, "the plate")],
                                    source="hearthfall",
                                    destination="gallery")
    assert problems == [] and record is not None
    return record


# -- the record: closure and identity ---------------------------------------


def test_the_closure_rides_the_family_and_leaves_the_machine_home():
    record = _record(_source_world())
    names = {name for _label, name, _props in record["citizens"]}
    assert names == {"the plate", "the plate (file)", "the vale study"}
    # verbatim: the fingerprint and both grade facets ride whole
    props = {name: dict(p) for _l, name, p in record["citizens"]}
    assert props["the plate (file)"]["verified_fingerprint"] == "abc123"
    assert props["the plate"]["provenance_known_at"] == "Cited"


def test_the_record_is_content_addressed():
    record = _record(_source_world())
    assert record["id"] == record_id(record)
    tampered = json.loads(json.dumps(record))
    tampered["citizens"][0][2]["description"] = "forged"
    assert record_id(tampered) != record["id"]


def test_edges_partition_by_who_moves():
    record = _record(_source_world())
    internal = {(e[0], e[2], e[4]) for e in record["connections"]}
    assert ("LOCATED_AT", "the plate", "the plate (file)") in internal
    assert ("ABOUT", "the vale study", "the plate") in internal
    outbound = {(e[0], e[2], e[4]) for e in record["outbound"]}
    assert ("DEPICTS", "the plate", "Pip") in outbound
    assert ("DRAWS_ON", "the vale study", "Pip") in outbound
    assert record["inbound"] == []  # no stayer references a mover here


# -- staging: the two sides -------------------------------------------------


def test_emigrate_stages_the_departure(tmp_path):
    canon = _source_world()
    record = _record(canon)
    staged = clone(canon)
    problems = emigrate_stage(staged, record)
    assert problems == []
    assert (ART, "the plate") not in staged.nodes
    assert (LOC, "the plate (file)") not in staged.nodes
    assert (INTERP, "the vale study") not in staged.nodes
    assert (INTERP, "a machine reading") in staged.nodes  # stays home
    assert not [e for e in staged.edges
                if "the plate" in (str(e.from_name), str(e.to_name))]


def test_immigrate_stages_the_arrival_with_bookmarked_stayers(tmp_path):
    canon = _source_world()
    record = _record(canon)
    gallery = build_canon()
    gallery.ensure_node(KERNEL_DEPENDENCY_LABEL, "hearthfall",
                        edition="h" * 64, sequence=9, intent="read")
    problems = immigrate_stage(gallery, record)
    assert problems == []
    assert dict(gallery.nodes[(ART, "the plate")])["description"] == \
        "sketches of the vale"
    assert dict(gallery.nodes[(LOC, "the plate (file)")])[
        "verified_fingerprint"] == "abc123"
    # the outbound references landed as bookmarks into the source
    bm = [name for (label, name) in gallery.nodes
          if label == KERNEL_BOOKMARK_LABEL]
    assert len(bm) == 1
    [bm_name] = bm
    assert dict(gallery.nodes[(KERNEL_BOOKMARK_LABEL, bm_name)])[
        "citizen_name"] == "Pip"
    assert any(e.type == "DEPICTS" and str(e.to_name) == bm_name
               for e in gallery.edges)
    assert any(e.type == RESOLVES_IN_EDGE and str(e.from_name) == bm_name
               for e in gallery.edges)


def test_staging_refuses_collated_without_the_counterpart_pin():
    canon = _source_world()
    record = _record(canon)
    gallery = build_canon()  # no pin toward the source at all
    problems = immigrate_stage(gallery, record)
    assert problems and all("hearthfall" in p for p in problems)
    # nothing was half-written: verify-all before apply-any
    assert (ART, "the plate") not in gallery.nodes


# -- the gate: the record against the round ---------------------------------


def test_the_emigration_gate_passes_a_faithful_round(tmp_path):
    canon = _source_world()
    record = _record(canon)
    staged = clone(canon)
    assert emigrate_stage(staged, record) == []
    delta = diff(canon, staged)
    verdicts = migration_verdicts(delta, canon, record)
    assert [v for v in verdicts if v.severity == "refusal"] == []
    [line] = [v for v in verdicts if v.code == "emigration-declared"]
    assert "3" in line.message and "gallery" in line.message


def test_the_immigration_gate_byte_verifies_the_arrivals(tmp_path):
    canon = _source_world()
    record = _record(canon)
    gallery = build_canon()
    gallery.ensure_node(KERNEL_DEPENDENCY_LABEL, "hearthfall",
                        edition="h" * 64, sequence=9, intent="read")
    base = clone(gallery)
    assert immigrate_stage(gallery, record) == []
    delta = diff(base, gallery)
    verdicts = migration_verdicts(delta, base, record)
    assert [v for v in verdicts if v.severity == "refusal"] == []
    [line] = [v for v in verdicts if v.code == "immigration-declared"]
    assert "hearthfall" in line.message
    # an arrival that drifted from the record refuses by name
    drifted = clone(base)
    assert immigrate_stage(drifted, record) == []
    drifted.nodes[(ART, "the plate")]["description"] = "retouched"
    verdicts = migration_verdicts(diff(base, drifted), base, record)
    [fault] = [v for v in verdicts
               if v.code == "migration-arrival-mismatch"]
    assert "the plate" in fault.message


def test_a_tampered_record_refuses_as_drift(tmp_path):
    canon = _source_world()
    record = _record(canon)
    staged = clone(canon)
    assert emigrate_stage(staged, record) == []
    tampered = json.loads(json.dumps(record))
    tampered["citizens"][0][2]["description"] = "forged"
    verdicts = migration_verdicts(diff(canon, staged), canon, tampered)
    assert any(v.code == "migration-record-drift" for v in verdicts)


def test_a_split_family_refuses_by_name(tmp_path):
    canon = _source_world()
    record = _record(canon)
    # the round forgets the location row: departures no longer match
    # the record's closure
    staged = clone(canon)
    assert emigrate_stage(staged, record) == []
    staged.ensure_node(LOC, "the plate (file)", scheme="file",
                       address="art/plate.png", primary=True,
                       verified_fingerprint="abc123", size=9)
    verdicts = migration_verdicts(diff(canon, staged), canon, record)
    [fault] = [v for v in verdicts
               if v.code == "migration-closure-broken"]
    assert "the plate (file)" in fault.message


# -- the ordering law rides the citation stack ------------------------------


def test_the_ordering_law_is_the_resolution_gates_own(tmp_path):
    """An emigration whose stayers now cite the gallery refuses through
    the EXISTING bookmark resolution until the gallery's pinned edition
    holds the arrivals — no new sequencing machinery."""
    from graph import export as export_mod
    from graph.dependencies import resolution_verdicts, settings_key
    from graph.proposal import base_identity

    canon = _source_world()
    # a stayer references a mover, so the emigration mints a bookmark
    canon.ensure_node("Trinket", "the frame", doc="holds the plate")
    canon.edges.append(make_edge("SHOWS", "Trinket", "the frame",
                                 ART, "the plate"))
    record, problems = build_record(canon, [(ART, "the plate")],
                                    source="hearthfall",
                                    destination="gallery")
    assert problems == [] and record is not None
    assert len(record["inbound"]) == 1
    staged = clone(canon)
    assert emigrate_stage(staged, record) == []
    # the stayer's edge now points at a gallery bookmark
    [bm_name] = [name for (label, name) in staged.nodes
                 if label == KERNEL_BOOKMARK_LABEL]
    assert any(e.type == "SHOWS" and str(e.to_name) == bm_name
               for e in staged.edges)
    # a gallery checkout WITHOUT the arrivals: the citation stack refuses
    empty = build_canon()
    export_mod.write_export(empty, tmp_path / "gallery" / "graph" / "export")
    config = {settings_key("gallery"): str(tmp_path / "gallery")}
    staged.nodes[(KERNEL_DEPENDENCY_LABEL, "gallery")].update(
        edition=base_identity(empty), sequence=0)
    verdicts = resolution_verdicts(diff(canon, staged), staged, config)
    assert any(v.code == "bookmark-target-missing" for v in verdicts)
    # the arrivals land there; the same round resolves clean
    arrived = build_canon()
    assert immigrate_stage(
        arrived,
        json.loads(json.dumps(record))) != []  # no pin: still refuses
    arrived.ensure_node(KERNEL_DEPENDENCY_LABEL, "hearthfall",
                        edition="h" * 64, sequence=9, intent="read")
    assert immigrate_stage(arrived, record) == []
    export_mod.write_export(arrived,
                            tmp_path / "gallery" / "graph" / "export")
    staged.nodes[(KERNEL_DEPENDENCY_LABEL, "gallery")].update(
        edition=base_identity(arrived), sequence=0)
    verdicts = resolution_verdicts(diff(canon, staged), staged, config)
    assert not [v for v in verdicts
                if v.code == "bookmark-target-missing"]
