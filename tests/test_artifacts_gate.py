"""Artifacts at the gate.

An [Artifact]'s identity is its name; WHERE it is lives on
[Artifact Location] rows behind LOCATED_AT, with [File Location] the
kernel's kind. The gate reads every file location the round touches,
holds a declared fingerprint to the bytes, wants exactly one primary,
grades content held (Cited / Attested / Transcribed) and keeps
verification on the location row; DEPICTS names objective contents; an
[Interpretation] is ABOUT exactly one artifact and DRAWS_ON only what it
depicts; a [Resolver] binds a location kind to one procedure. At apply
the engine stamps what it verified; the receipts sweep re-reads it.

Storybook domain, over the driven-kb harness: the tale's own chapter
file and a sketch of the Falchion.
"""

import hashlib
import json

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.artifacts import (DEPICTS, DRAWS_ON, INTERPRETED_AS, LOCATED_AT,
                             OPENS_WITH, SUPERSEDES, VERIFIED_AT,
                             VERIFIED_FINGERPRINT, gate_verdicts,
                             location_labels, location_rows,
                             verification_stamp)
from graph.delta import diff
from graph.extract import make_edge
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL,
                            KERNEL_ARTIFACT_LOCATION_LABEL,
                            KERNEL_FILE_LOCATION_LABEL,
                            KERNEL_INTERPRETATION_LABEL,
                            KERNEL_PROCEDURE_LABEL, KERNEL_RESOLVER_LABEL)
from graph.report import REF_KEYS, record_path
from graph.restore import read_export
from tests.test_branch import build_canon, clone, driven_kb, export_dir  # noqa: F401
from tests.test_succession import _mount_live_canon

ART, LOC, FILE = (KERNEL_ARTIFACT_LABEL, KERNEL_ARTIFACT_LOCATION_LABEL,
                  KERNEL_FILE_LOCATION_LABEL)
INTERP, RESOLVER = KERNEL_INTERPRETATION_LABEL, KERNEL_RESOLVER_LABEL
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(16))


def _sketch(base, graph, name="falchion-sketch", address="art/sketch.png",
            primary=True, kind=FILE, **props):
    (base / address).parent.mkdir(parents=True, exist_ok=True)
    (base / address).write_bytes(PNG)
    graph.ensure_node(ART, name, **props)
    graph.ensure_node(kind, f"{name}@file", scheme="file", address=address,
                      primary=primary)
    graph.edges.append(make_edge(LOCATED_AT, ART, name, kind, f"{name}@file"))
    return graph


def _codes(base, before, after):
    return sorted(v.code for v in gate_verdicts(diff(before, after), after,
                                                base))


# -- locations -------------------------------------------------------------


def test_location_kinds_include_every_subtype(tmp_path):
    canon = build_canon()
    assert location_labels(canon) == {LOC, FILE}
    canon.ensure_node(ARCHETYPE_LABEL, "[Sketch File]")
    canon.edges.append(make_edge("SUBTYPE_OF", ARCHETYPE_LABEL,
                                 "[Sketch File]", ARCHETYPE_LABEL, FILE))
    assert location_labels(canon) == {LOC, FILE, "[Sketch File]"}


def test_a_well_formed_artifact_with_a_file_location_passes(tmp_path):
    base = build_canon()
    scratch = _sketch(tmp_path, clone(base))
    assert _codes(tmp_path, base, scratch) == []
    # the declared fingerprint, when present, must match the bytes
    ok = _sketch(tmp_path, clone(base),
                 fingerprint=hashlib.sha256(PNG).hexdigest())
    assert _codes(tmp_path, base, ok) == []
    bad = _sketch(tmp_path, clone(base), fingerprint="0" * 64)
    [verdict] = gate_verdicts(diff(base, bad), bad, tmp_path)
    assert verdict.code == "artifact-fingerprint-mismatch"
    assert "python -m graph receipt art/sketch.png" in str(verdict)
    assert REF_KEYS[verdict.code] == "cited-bytes-differ"


def test_locations_refuse_by_name_when_malformed(tmp_path):
    base = build_canon()
    # unreadable file
    scratch = clone(base)
    scratch.ensure_node(ART, "ghost")
    scratch.ensure_node(FILE, "ghost@file", scheme="file",
                        address="art/missing.png", primary=True)
    scratch.edges.append(make_edge(LOCATED_AT, ART, "ghost", FILE,
                                   "ghost@file"))
    assert _codes(tmp_path, base, scratch) == ["file-location-unreadable"]
    # outside the knowledge base
    scratch.nodes[(FILE, "ghost@file")]["address"] = "../secrets.png"
    assert _codes(tmp_path, base, scratch) == ["file-location-unreadable"]
    # no primary, two primaries
    none = _sketch(tmp_path, clone(base), primary=False)
    assert _codes(tmp_path, base, none) == ["artifact-primary-location"]
    two = _sketch(tmp_path, clone(base))
    two.ensure_node(LOC, "falchion-sketch@shelf", scheme="physical",
                    address="cabinet X, drawer Y", primary=True)
    two.edges.append(make_edge(LOCATED_AT, ART, "falchion-sketch", LOC,
                               "falchion-sketch@shelf"))
    [verdict] = gate_verdicts(diff(base, two), two, tmp_path)
    assert verdict.code == "artifact-primary-location"
    assert verdict.data["primaries"] == ["falchion-sketch@file",
                                         "falchion-sketch@shelf"]
    # a physical location alone is fine: unverifiable by design
    shelf = clone(base)
    shelf.ensure_node(ART, "painting")
    shelf.ensure_node(LOC, "painting@shelf", scheme="physical",
                      address="cabinet X, drawer Y", primary=True)
    shelf.edges.append(make_edge(LOCATED_AT, ART, "painting", LOC,
                                 "painting@shelf"))
    assert _codes(tmp_path, base, shelf) == []
    # incomplete, shared, wrong kind, wrong source
    thin = clone(shelf)
    thin.nodes[(LOC, "painting@shelf")].pop("address")
    assert _codes(tmp_path, base, thin) == ["location-incomplete"]
    shared = clone(shelf)
    shared.ensure_node(ART, "copy")
    shared.edges.append(make_edge(LOCATED_AT, ART, "copy", LOC,
                                  "painting@shelf"))
    assert "location-shared" in _codes(tmp_path, base, shared)
    wrong = clone(base)
    wrong.ensure_node(ART, "odd")
    wrong.edges.append(make_edge(LOCATED_AT, ART, "odd", "Character", "Pip"))
    assert _codes(tmp_path, base, wrong) == ["location-kind-unknown"]
    misused = clone(base)
    misused.ensure_node(LOC, "somewhere", scheme="physical", address="x",
                        primary=True)
    misused.edges.append(make_edge(LOCATED_AT, "Character", "Pip", LOC,
                                   "somewhere"))
    assert _codes(tmp_path, base, misused) == ["artifact-edge-misused"]


# -- grade, depiction, supersession -----------------------------------------


def test_the_grade_is_content_held_never_verification(tmp_path):
    base = build_canon()
    cited = _sketch(tmp_path, clone(base), known_at="Cited")
    assert _codes(tmp_path, base, cited) == []
    unearned = _sketch(tmp_path, clone(base), known_at="Attested")
    [verdict] = gate_verdicts(diff(base, unearned), unearned, tmp_path)
    assert verdict.code == "artifact-grade-unearned"
    assert verdict.data["lacks"] == ["a description",
                                     "at least one DEPICTS fact"]
    earned = _sketch(tmp_path, clone(base), known_at="Attested",
                     description="a sketch of the Falchion")
    earned.edges.append(make_edge(DEPICTS, ART, "falchion-sketch",
                                  "Character", "Pip"))
    assert _codes(tmp_path, base, earned) == []
    parked = _sketch(tmp_path, clone(base), known_at="Transcribed")
    assert _codes(tmp_path, base, parked) == ["artifact-grade-parked"]
    odd = _sketch(tmp_path, clone(base), known_at="Glanced")
    assert _codes(tmp_path, base, odd) == ["artifact-grade-unknown"]
    # depiction targets exist; only an artifact depicts
    dangling = _sketch(tmp_path, clone(base))
    dangling.edges.append(make_edge(DEPICTS, ART, "falchion-sketch",
                                    "Beast", "Nobody"))
    assert _codes(tmp_path, base, dangling) == ["depicts-target-missing"]
    misused = clone(base)
    misused.edges.append(make_edge(DEPICTS, "Character", "Pip", "Character",
                                   "Pip"))
    assert _codes(tmp_path, base, misused) == ["artifact-edge-misused"]
    # supersession
    retired = _sketch(tmp_path, clone(base), superseded_at=12)
    assert _codes(tmp_path, base, retired) == []
    retired.nodes[(ART, "falchion-sketch")]["superseded_at"] = "twelve"
    assert _codes(tmp_path, base, retired) == \
        ["artifact-superseded-at-invalid"]
    newer = _sketch(tmp_path, clone(base))
    newer.ensure_node(ART, "falchion-sketch-v2")
    newer.edges.append(make_edge(SUPERSEDES, ART, "falchion-sketch-v2", ART,
                                 "falchion-sketch"))
    assert _codes(tmp_path, base, newer) == []
    newer.edges.append(make_edge(SUPERSEDES, ART, "falchion-sketch-v2",
                                 "Character", "Pip"))
    assert _codes(tmp_path, base, newer) == ["artifact-edge-misused"]


# -- interpretations and resolvers -------------------------------------------


def test_an_interpretation_reads_one_artifact_and_draws_on_what_it_depicts(
        tmp_path):
    base = build_canon()
    scratch = _sketch(tmp_path, clone(base))
    scratch.edges.append(make_edge(DEPICTS, ART, "falchion-sketch", "Character",
                                   "Pip"))
    scratch.ensure_node(INTERP, "the fighter's blade", intent="class art",
                        by="Maren")
    scratch.edges.append(make_edge("ABOUT", INTERP, "the fighter's blade",
                                   ART, "falchion-sketch"))
    scratch.edges.append(make_edge(INTERPRETED_AS, INTERP,
                                   "the fighter's blade", "Character",
                                   "Maren"))
    scratch.edges.append(make_edge(DRAWS_ON, INTERP, "the fighter's blade",
                                   "Character", "Pip"))
    assert _codes(tmp_path, base, scratch) == []
    mute = clone(scratch)
    mute.nodes[(INTERP, "the fighter's blade")].pop("intent")
    assert _codes(tmp_path, base, mute) == ["interpretation-intent-missing"]
    twice = clone(scratch)
    twice.ensure_node(ART, "other")
    twice.edges.append(make_edge("ABOUT", INTERP, "the fighter's blade", ART,
                                 "other"))
    [verdict] = gate_verdicts(diff(base, twice), twice, tmp_path)
    assert verdict.code == "interpretation-about"
    assert verdict.data["about"] == ["falchion-sketch", "other"]
    undepicted = clone(scratch)
    undepicted.edges.append(make_edge(DRAWS_ON, INTERP, "the fighter's blade",
                                      "Character", "Maren"))
    assert _codes(tmp_path, base, undepicted) == ["draws-on-undepicted"]
    assert REF_KEYS["draws-on-undepicted"] == "draws-on-undepicted"


def test_a_resolver_binds_a_location_kind_to_one_procedure(tmp_path):
    base = build_canon()
    scratch = clone(base)
    scratch.ensure_node(KERNEL_PROCEDURE_LABEL, "Open a sketch",
                        known_at="Cited")
    scratch.ensure_node(RESOLVER, "sketchbook", scheme="sketchbook",
                        location_kind=FILE)
    scratch.edges.append(make_edge(OPENS_WITH, RESOLVER, "sketchbook",
                                   KERNEL_PROCEDURE_LABEL, "Open a sketch"))
    assert _codes(tmp_path, base, scratch) == []
    unbound = clone(scratch)
    unbound.edges = [e for e in unbound.edges if e.type != OPENS_WITH]
    assert _codes(tmp_path, base, unbound) == ["resolver-opens-with"]
    odd = clone(scratch)
    odd.nodes[(RESOLVER, "sketchbook")]["location_kind"] = "Character"
    assert _codes(tmp_path, base, odd) == ["resolver-kind-unknown"]
    thin = clone(scratch)
    thin.nodes[(RESOLVER, "sketchbook")].pop("scheme")
    assert _codes(tmp_path, base, thin) == ["resolver-incomplete"]


# -- the apply-time stamp and the sweep ---------------------------------------


def test_apply_stamps_verification_on_the_location_and_medium_on_the_artifact(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    canon = read_export(export_dir(base))
    _mount_live_canon(base, fake)
    authored = _sketch(base, clone(canon), known_at="Cited")
    fake.databases["scratch"] = authored
    capsys.readouterr()
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    landed = read_export(export_dir(base))
    row = landed.nodes[(FILE, "falchion-sketch@file")]
    digest = hashlib.sha256(PNG).hexdigest()
    assert row[VERIFIED_FINGERPRINT] == digest
    assert row[VERIFIED_AT] == 1 and row["size"] == len(PNG)
    artifact = landed.nodes[(ART, "falchion-sketch")]
    assert artifact["fingerprint"] == digest and artifact["medium"] == "image"
    assert artifact["known_at"] == "Cited"  # verification never grades
    # the file location is an instance of the base kind by the fold
    parents = {e.to_name for e in landed.edges if e.type == "INSTANCE_OF"
               and (e.from_label, e.from_name) == (FILE,
                                                   "falchion-sketch@file")}
    assert parents == {FILE, LOC}
    # the receipts sweep re-reads it: verified, then stale once it moves
    assert main_mod.cmd_receipts(base) == 0
    doc = json.loads(record_path(base, "receipts-report.json")
                     .read_text(encoding="utf-8"))
    [loc] = doc["locations"]
    assert loc["status"] == "verified" and loc["ref"] == "held"
    assert "1 verified" in capsys.readouterr().out
    (base / "art" / "sketch.png").write_bytes(PNG + b"!")
    assert main_mod.cmd_receipts(base) == 0
    doc = json.loads(record_path(base, "receipts-report.json")
                     .read_text(encoding="utf-8"))
    assert doc["locations"][0]["status"] == "stale"
    assert "stale: 'falchion-sketch' at art/sketch.png" in \
        capsys.readouterr().out
    # the receipt verb prints the location row a file would be cited at
    assert main_mod.cmd_receipt(base, ["art/sketch.png"]) == 0
    out = capsys.readouterr().out
    assert "location: ([File Location]) scheme: file · address: " \
           "art/sketch.png · primary: true" in out


def test_the_stamp_refuses_before_writing_when_a_file_cannot_be_read(tmp_path):
    canon = build_canon()
    canon.ensure_node(ART, "ghost")
    canon.ensure_node(FILE, "ghost@file", scheme="file",
                      address="art/missing.png", primary=True)
    canon.edges.append(make_edge(LOCATED_AT, ART, "ghost", FILE, "ghost@file"))
    before = export_mod.serialize(canon)
    problems = verification_stamp(canon, tmp_path, 1, {"ghost"})
    assert problems and "not readable" in problems[0]
    assert export_mod.serialize(canon) == before
    # nothing to stamp for an artifact with no file location
    canon.ensure_node(ART, "painting")
    assert verification_stamp(canon, tmp_path, 1, {"painting"}) == []
    assert location_rows(canon, tmp_path)[0]["status"] == "unreadable"
