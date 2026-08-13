"""The exam seal: canon holds only the fingerprint; the grading-day
handshake verifies a produced file against it."""

import hashlib
import json

from graph.__main__ import cmd_verify_seal


def seal_repo(tmp_path, exam_bytes, fingerprint=None):
    exam = tmp_path / "private-exam.md"
    exam.write_bytes(exam_bytes)
    export_dir = tmp_path / "graph" / "export"
    export_dir.mkdir(parents=True)
    row = {"label": "Sealed Exam", "name": "Corpus-One Expert Exam",
           "properties": {
               "fingerprint": fingerprint or hashlib.sha256(
                   exam_bytes).hexdigest(),
               "authored_by": "Robin", "sealed_on": "2026-08-03"}}
    (export_dir / "nodes.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")
    return exam


def test_matching_file_verifies(tmp_path, capsys):
    exam = seal_repo(tmp_path, b"which Beast takes the first turn at dusk?")
    assert cmd_verify_seal(tmp_path, exam) == 0
    assert "SEAL VERIFIED" in capsys.readouterr().out


def test_tampered_file_breaks_the_seal(tmp_path, capsys):
    exam = seal_repo(tmp_path, b"original exam",
                     fingerprint=hashlib.sha256(b"other").hexdigest())
    assert cmd_verify_seal(tmp_path, exam) == 1
    err = capsys.readouterr().err
    assert "SEAL BROKEN" in err and "Corpus-One Expert Exam" in err


def test_no_seal_yet_is_a_clear_refusal(tmp_path, capsys):
    exam = tmp_path / "exam.md"
    exam.write_bytes(b"early")
    (tmp_path / "graph" / "export").mkdir(parents=True)
    (tmp_path / "graph" / "export" / "nodes.jsonl").write_text(
        "", encoding="utf-8")
    assert cmd_verify_seal(tmp_path, exam) == 1
    assert "no Sealed Exam citizens yet" in capsys.readouterr().err
