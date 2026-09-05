"""Floor receipts for non-text artifacts.

The front door promises any artifact; the reading room reads text.
Every artifact enters at least at its floor receipt — whole-file
fingerprint, size, and the medium its BYTES declare — and a non-text
artifact is cited on the citizen it is about by that receipt. The
reading room refuses such an artifact plainly, receipt in hand, never
with a raw decoding error; the diff gate checks a cited fingerprint
against the file it names; and a receipt verb prints the receipt so
nobody types a hash by hand.

Storybook domain: a sketch of the Falchion.
"""

import hashlib
import json

import pytest

import graph.__main__ as main_mod
from graph.comprehension import (NotTextArtifact, read_artifact, receipt,
                                 sniff_medium)
from graph.delta import Delta, fingerprint_verdicts
from graph.report import REF_KEYS, record_path
from tests.test_branch import driven_kb  # noqa: F401
from tests.test_comprehension import DOC

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(16))
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 8
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "
FLAC = b"fLaC" + b"\x00" * 4


# -- the receipt reads the bytes -----------------------------------------


def test_the_medium_comes_from_the_bytes_never_the_name():
    assert sniff_medium(DOC) == "text"
    assert sniff_medium(PNG) == "image"
    assert sniff_medium(JPEG) == "image"
    assert sniff_medium(WEBP) == "image"
    assert sniff_medium(PDF) == "pdf"
    assert sniff_medium(FLAC) == "audio"
    assert sniff_medium(b"\x00\xff\xfe\x01") == "binary"


def test_the_receipt_is_fingerprint_size_and_medium():
    issued = receipt(PNG)
    assert issued == {"fingerprint": hashlib.sha256(PNG).hexdigest(),
                      "bytes": len(PNG), "medium": "image"}


# -- the reading room refuses plainly ------------------------------------


def test_the_reading_room_refuses_a_non_text_artifact_receipt_in_hand():
    with pytest.raises(NotTextArtifact) as caught:
        read_artifact(PNG, title="falchion-sketch.png")
    text = str(caught.value)
    assert "Attempted to read artifact falchion-sketch.png" in text
    assert "it is an image, not text" in text
    assert hashlib.sha256(PNG).hexdigest()[:12] in text
    assert "python -m graph receipt <file>" in text
    assert caught.value.receipt["bytes"] == len(PNG)
    assert isinstance(caught.value, ValueError)  # the callers' net holds
    # text still reads as ever
    assert read_artifact(DOC, title="doc").sections


def test_comprehend_collates_the_refusal_without_a_traceback(driven_kb,
                                                             capsys):
    base, _fake, _ = driven_kb
    (base / "falchion-sketch.png").write_bytes(PNG)
    capsys.readouterr()
    assert main_mod.cmd_comprehend(base, ["falchion-sketch.png"], None,
                                   False) == 1
    err = capsys.readouterr().err
    assert "every problem collated" in err
    assert "it is an image, not text" in err
    assert "Traceback" not in err and "UnicodeDecodeError" not in err


# -- the gate checks a cited fingerprint against its file ----------------


def _delta(added=(), changed=()):
    delta = Delta()
    delta.nodes_added = list(added)
    delta.nodes_changed = list(changed)
    return delta


def test_the_gate_holds_a_cited_fingerprint_to_the_file_s_bytes(tmp_path):
    (tmp_path / "art").mkdir()
    (tmp_path / "art" / "falchion.png").write_bytes(PNG)
    right = hashlib.sha256(PNG).hexdigest()
    wrong = "0" * 64
    cited_right = ("Sketch", "art/falchion.png", {"fingerprint": right})
    assert fingerprint_verdicts(_delta([cited_right]), tmp_path) == []
    [verdict] = fingerprint_verdicts(
        _delta([("Sketch", "art/falchion.png", {"fingerprint": wrong})]),
        tmp_path)
    assert verdict.code == "fingerprint-mismatch"
    assert verdict.subject.name == "art/falchion.png"
    assert verdict.data == {"file": "art/falchion.png", "declared": wrong,
                            "actual": right}
    assert "python -m graph receipt art/falchion.png" in str(verdict)
    assert REF_KEYS["fingerprint-mismatch"] == "cited-bytes-differ"
    # a re-fingerprinting is judged the same way
    [verdict] = fingerprint_verdicts(
        _delta(changed=[("Sketch", "art/falchion.png",
                         {"fingerprint": (right, wrong)})]), tmp_path)
    assert verdict.code == "fingerprint-mismatch"
    # a change that leaves the fingerprint alone is not judged
    assert fingerprint_verdicts(
        _delta(changed=[("Sketch", "art/falchion.png",
                         {"doc": ("a", "b")})]), tmp_path) == []
    # a name that is no file on disk cites bytes held elsewhere — silent
    assert fingerprint_verdicts(
        _delta([("Sketch", "elsewhere.png", {"fingerprint": wrong})]),
        tmp_path) == []
    # a citizen's name never reaches outside the knowledge base
    outside = str(tmp_path / "art" / "falchion.png")
    assert fingerprint_verdicts(
        _delta([("Sketch", outside, {"fingerprint": wrong}),
                ("Sketch", "../art/falchion.png", {"fingerprint": wrong})]),
        tmp_path) == []
    # a citizen without a fingerprint is none of this gate's business
    assert fingerprint_verdicts(
        _delta([("Sketch", "art/falchion.png", {"doc": "a sketch"})]),
        tmp_path) == []


# -- the receipt verb ----------------------------------------------------


def test_the_receipt_verb_prints_and_records_every_file(driven_kb, capsys):
    base, _fake, _ = driven_kb
    (base / "falchion-sketch.png").write_bytes(PNG)
    (base / "notes.md").write_bytes(DOC)
    capsys.readouterr()
    assert main_mod.cmd_receipt(base, ["falchion-sketch.png",
                                       "notes.md"]) == 0
    out = capsys.readouterr().out
    digest = hashlib.sha256(PNG).hexdigest()
    assert (f"falchion-sketch.png: fingerprint {digest} · {len(PNG)} bytes "
            "· image") in out
    assert "notes.md: fingerprint" in out and "· text" in out
    record = json.loads(record_path(base, "receipt-report.json")
                        .read_text(encoding="utf-8"))
    assert record["kind"] == "receipt-report"
    [sketch, notes] = record["receipts"]
    assert sketch == {"file": "falchion-sketch.png", "fingerprint": digest,
                      "bytes": len(PNG), "medium": "image",
                      "location": {"kind": "[File Location]", "scheme": "file",
                                   "address": "falchion-sketch.png",
                                   "primary": True},
                      "code": "receipt-issued", "ref": "identity-recorded"}
    assert "location: ([File Location]) scheme: file · address: " \
           "falchion-sketch.png · primary: true" in out
    assert notes["medium"] == "text"
    # an unreadable file collates and fails the run; the rest still issue
    assert main_mod.cmd_receipt(base, ["falchion-sketch.png",
                                       "missing.png"]) == 1
    captured = capsys.readouterr()
    assert "Attempted to issue a receipt for missing.png" in captured.err
    assert f"falchion-sketch.png: fingerprint {digest}" in captured.out
    record = json.loads(record_path(base, "receipt-report.json")
                        .read_text(encoding="utf-8"))
    assert [row["code"] for row in record["receipts"]] == \
        ["receipt-issued", "receipt-unreadable"]
    assert record["receipts"][1]["ref"] == "unreadable-file"
