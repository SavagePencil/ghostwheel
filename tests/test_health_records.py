"""Health-check verdicts as durable records.

Five surfaces used to compute structured rows and discard them as
terminal prose: check, corpus, verify-seal, the restore drill (canon
and branch), and the receipts sweep. Each now leaves a record beside
graph/reports/ — kind, the line of truth, coded rows with designer-
facing refs, PASS rows included — while every line on screen stays
byte-identical. The record reflects the latest run; a run refused
before it could check anything records the guard that stopped it.
"""

import json

import graph.__main__ as main_mod
from graph import corpus as corpus_mod
from graph import export as export_mod
from graph.__main__ import (CHECK_REPORT_FILE, RESTORE_REPORT_FILE,
                            SEAL_REPORT_FILE, check_report, run_checks)
from graph.corpus import (CORPUS_REPORT_FILE, FLOOR_FAILED,
                          FLOOR_GUARD_MISSING, FLOOR_HELD, corpus_report,
                          floor_records, missing_guards, render_report)
from graph.extract import GraphData
from graph.proposal import export_dir
from graph.report import (clear_record, record_header, record_path,
                          write_record)

# the driven CLI harness for the drill (imported into this module's
# namespace so pytest resolves the fixture here too)
from tests.test_branch import (STORYBOOK, FakeDBMS, build_canon,  # noqa: F401
                               clone, driven_kb)


def _record(base, filename):
    return json.loads(record_path(base, filename).read_text(encoding="utf-8"))


# -- the shared plumbing ---------------------------------------------------


def test_write_record_is_canonical_and_best_effort(tmp_path):
    text = write_record(tmp_path, "thing.json", {"b": 1, "a": [2]})
    assert text == '{\n  "a": [\n    2\n  ],\n  "b": 1\n}\n'
    assert _record(tmp_path, "thing.json") == {"a": [2], "b": 1}
    clear_record(tmp_path, "thing.json")
    assert not record_path(tmp_path, "thing.json").exists()
    clear_record(tmp_path, "thing.json")  # absent is fine
    # a directory where the file should be: the write fails quietly
    record_path(tmp_path, "blocked.json").mkdir(parents=True)
    assert write_record(tmp_path, "blocked.json", {}) is None


def test_record_header_names_the_line_of_truth(tmp_path):
    doc = record_header(tmp_path, "some-report")
    assert doc["kind"] == "some-report" and "kb" in doc
    assert "branch" not in doc
    assert record_header(tmp_path, "x", "rebuild")["branch"] == "rebuild"


# -- check -----------------------------------------------------------------


class _Session:
    def __init__(self, rows_by_text):
        self.rows_by_text = rows_by_text

    def run(self, text):
        # the session receives the whole check file; the fixture keys
        # its rows by the query on the file's last line
        return list(self.rows_by_text.get(text.strip().splitlines()[-1],
                                          []))


def _check_files(tmp_path):
    checks = tmp_path / "graph" / "cypher" / "checks"
    checks.mkdir(parents=True)
    files = {
        "a-holds": "// expect: empty\n// Every Herb names a hue.\nQ1",
        "b-broken": "// expect: empty\n// Every Blade has a reach.\nQ2",
        "c-census": "// Placeholder census.\nQ3",
    }
    for stem, text in files.items():
        (checks / f"{stem}.cypher").write_text(text, encoding="utf-8")
    return sorted(checks.glob("*.cypher"))


def test_run_checks_records_every_verdict(tmp_path):
    session = _Session({"Q2": [{"name": "Sabre"}],
                        "Q3": [{"n": i} for i in range(25)]})
    records = run_checks(session, _check_files(tmp_path))
    by_name = {r["check"]: r for r in records}
    assert by_name["a-holds"]["status"] == "pass"
    assert by_name["a-holds"]["code"] == "check-passed"
    assert by_name["a-holds"]["ref"] == "held"
    assert by_name["b-broken"]["status"] == "fail"
    assert by_name["b-broken"]["sample"] == [{"name": "Sabre"}]
    assert by_name["b-broken"]["ref"] == "integrity-broken"
    assert by_name["c-census"]["mode"] == "informational"
    assert by_name["c-census"]["rows"] == 25
    assert len(by_name["c-census"]["sample"]) == 20  # capped like the screen
    doc = check_report(tmp_path, records=records)
    assert doc["kind"] == "check-report"
    assert doc["counts"] == {"checks": 3, "failed": 1, "findings": 25}


def test_check_cli_files_the_record_and_keeps_its_voice(tmp_path, capsys):
    files = _check_files(tmp_path)
    assert files
    session = _Session({"Q2": [{"name": "Sabre"}]})

    class Driver:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def session(self, database=None):
            return self

        def run(self, text):
            return session.run(text)

    # the driver factory is injected: the suite never needs the driver
    assert main_mod.cmd_check(
        tmp_path, driver_factory=lambda *args, **kwargs: Driver()) == 1
    captured = capsys.readouterr()
    assert "== a-holds: PASS (assertion; 0 rows)" in captured.out
    assert "== b-broken: FAIL (assertion; 1 rows)" in captured.out
    assert "   {'name': 'Sabre'}" in captured.out
    assert "Checks complete: 3 checks, 1 failed assertions" in captured.out
    assert "FAILED: b-broken" in captured.err
    doc = _record(tmp_path, CHECK_REPORT_FILE)
    assert [r["status"] for r in doc["checks"]] == ["pass", "fail",
                                                    "findings"]


def test_check_cli_records_the_guard_when_the_store_is_unreachable(
        tmp_path, capsys):
    _check_files(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("no route to the store")

    assert main_mod.cmd_check(tmp_path, driver_factory=broken) == 1
    assert "Check run failed: no route to the store" in \
        capsys.readouterr().err
    doc = _record(tmp_path, CHECK_REPORT_FILE)
    assert doc["guard"]["code"] == "check-unreachable"
    assert doc["guard"]["ref"] == "store-unreachable"
    assert "checks" not in doc


def test_check_cli_records_nothing_to_check(tmp_path, capsys):
    assert main_mod.cmd_check(tmp_path) == 2
    assert "No checks found" in capsys.readouterr().err
    assert _record(tmp_path, CHECK_REPORT_FILE)["guard"]["code"] == \
        "check-none"


# -- corpus ----------------------------------------------------------------


_FLOORS = [
    {"check": "tests/test_a.py::test_one", "scope": "engine",
     "expectation": "one holds", "provenance": "PR 1"},
    {"check": "tests/test_a.py::test_two", "scope": "engine",
     "expectation": "two holds", "provenance": "PR 2"},
    {"check": "tests/test_gone.py::test_three", "scope": "engine",
     "expectation": "three holds", "provenance": "PR 3"},
]
_COLLECTED = {"tests/test_a.py::test_one", "tests/test_a.py::test_two"}


def test_floor_records_speak_three_statuses():
    records = floor_records(_FLOORS, _COLLECTED,
                            failed_ids={"tests/test_a.py::test_two"})
    assert [r["status"] for r in records] == [FLOOR_HELD, FLOOR_FAILED,
                                              FLOOR_GUARD_MISSING]
    assert [r["ref"] for r in records] == ["held", "approval-broken",
                                           "protection-lost"]
    assert "problem" not in records[0]
    assert "blessed at PR 2" in records[1]["problem"]
    assert "is GONE" in records[2]["problem"]
    # the prose helpers derive from the same records
    assert missing_guards(_FLOORS, _COLLECTED) == [records[2]["problem"]]


def test_corpus_report_carries_rows_counts_or_the_guard(tmp_path):
    records = floor_records(_FLOORS, _COLLECTED)
    doc = corpus_report(tmp_path, records)
    assert doc["kind"] == "corpus-report"
    assert doc["counts"] == {FLOOR_HELD: 2, FLOOR_FAILED: 0,
                             FLOOR_GUARD_MISSING: 1}
    guarded = corpus_report(tmp_path, [], guard_problem="suite is broken")
    assert guarded["guard"]["code"] == "corpus-uncollectable"
    assert guarded["guard"]["ref"] == "suite-not-runnable"
    assert "floors" not in guarded


def test_corpus_cli_files_the_record_and_keeps_its_prose(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    corpus_mod.save_floors(corpus_mod.floors_path(tmp_path), _FLOORS)
    monkeypatch.setattr(corpus_mod, "collect_guards",
                        lambda base_dir: set(_COLLECTED))
    monkeypatch.setattr(corpus_mod, "failed_floor_ids",
                        lambda base_dir, floors, collected:
                        {"tests/test_a.py::test_two"})
    assert main_mod.cmd_corpus(tmp_path) == 1
    out = capsys.readouterr().out
    expected = render_report(_FLOORS,
                             missing_guards(_FLOORS, _COLLECTED),
                             [r["problem"] for r in floor_records(
                                 _FLOORS, _COLLECTED,
                                 {"tests/test_a.py::test_two"})
                              if r["status"] == FLOOR_FAILED])
    assert out == expected + "\n"
    doc = _record(tmp_path, CORPUS_REPORT_FILE)
    assert [r["status"] for r in doc["floors"]] == [
        FLOOR_HELD, FLOOR_FAILED, FLOOR_GUARD_MISSING]


def test_corpus_cli_records_an_uncollectable_suite(tmp_path, monkeypatch,
                                                    capsys):
    corpus_mod.save_floors(corpus_mod.floors_path(tmp_path), _FLOORS)
    monkeypatch.setattr(corpus_mod, "collect_guards", lambda base_dir: set())
    assert main_mod.cmd_corpus(tmp_path) == 1
    assert "collection returned nothing" in capsys.readouterr().err
    assert _record(tmp_path, CORPUS_REPORT_FILE)["guard"]["code"] == \
        "corpus-uncollectable"


def test_corpus_cli_records_an_empty_corpus(tmp_path, capsys):
    assert main_mod.cmd_corpus(tmp_path) == 0
    assert "The corpus is empty" in capsys.readouterr().out
    doc = _record(tmp_path, CORPUS_REPORT_FILE)
    assert doc["floors"] == [] and doc["counts"][FLOOR_HELD] == 0


# -- verify-seal -----------------------------------------------------------


def _sealed_canon(tmp_path, digest):
    graph = GraphData()
    graph.ensure_node("Sealed Exam", "The Herbal, sealed",
                      fingerprint=digest, sealed_on="day one",
                      authored_by="the keeper")
    export_mod.write_export(graph, tmp_path / "graph" / "export")


def test_seal_verified_and_broken_both_leave_records(tmp_path, capsys):
    import hashlib
    exam = tmp_path / "exam.md"
    exam.write_text("the exam", encoding="utf-8")
    digest = hashlib.sha256(b"the exam").hexdigest()
    _sealed_canon(tmp_path, digest)
    assert main_mod.cmd_verify_seal(tmp_path, exam) == 0
    assert "SEAL VERIFIED" in capsys.readouterr().out
    doc = _record(tmp_path, SEAL_REPORT_FILE)
    assert doc["status"] == "verified" and doc["ref"] == "sealed-intact"
    assert doc["matched"]["name"] == "The Herbal, sealed"
    assert doc["digest"] == digest
    exam.write_text("the exam, edited", encoding="utf-8")
    assert main_mod.cmd_verify_seal(tmp_path, exam) == 1
    assert "SEAL BROKEN" in capsys.readouterr().err
    doc = _record(tmp_path, SEAL_REPORT_FILE)
    assert doc["code"] == "seal-broken" and "matched" not in doc
    assert doc["candidates"][0]["fingerprint"] == digest[:16]


def test_seal_none_and_unreadable_leave_guards(tmp_path, capsys):
    exam = tmp_path / "exam.md"
    exam.write_text("the exam", encoding="utf-8")
    assert main_mod.cmd_verify_seal(tmp_path, exam) == 1
    assert "no Sealed Exam citizens" in capsys.readouterr().err
    assert _record(tmp_path, SEAL_REPORT_FILE)["code"] == "seal-none"
    assert main_mod.cmd_verify_seal(tmp_path, tmp_path / "ghost.md") == 1
    assert "Failed due to" in capsys.readouterr().err
    assert _record(tmp_path, SEAL_REPORT_FILE)["code"] == \
        "seal-file-unreadable"


# -- the restore drill, over the driven CLI --------------------------------


def test_branch_cut_drill_records_pass_then_the_recut_guard(driven_kb,
                                                            capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 0
    assert "DRILL PASSED" in capsys.readouterr().out
    doc = _record(base, RESTORE_REPORT_FILE)
    assert doc["code"] == "drill-passed" and doc["ref"] == "backup-faithful"
    assert doc["branch"] == "rebuild" and doc["database"] == "rebuild"
    assert doc["loaded"]["nodes"] > 0
    # the re-cut refuses before any write, and the record says why
    assert main_mod.cmd_restore(base, branch="rebuild",
                                base="schema-only") == 1
    assert "already exists" in capsys.readouterr().err
    doc = _record(base, RESTORE_REPORT_FILE)
    assert doc["code"] == "restore-guard" and doc["ref"] == "cannot-begin"
    assert any("already exists" in p for p in doc["problems"])


def test_canon_drill_records_pass_and_a_failed_drill(driven_kb, capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base) == 0
    assert "DRILL PASSED" in capsys.readouterr().out
    doc = _record(base, RESTORE_REPORT_FILE)
    assert doc["code"] == "drill-passed" and "branch" not in doc
    # a store that reads back differently than what was written
    real_dump = fake.dump_db

    def drifted(config):
        graph = real_dump(config)
        graph.ensure_node("Ghost", "Not in the backup")
        return graph

    fake.dump_db = drifted
    import graph.restore as restore_mod
    original = restore_mod.dump_db
    restore_mod.dump_db = drifted
    try:
        assert main_mod.cmd_restore(base) == 1
    finally:
        restore_mod.dump_db = original
    assert "DRILL FAILED" in capsys.readouterr().err
    doc = _record(base, RESTORE_REPORT_FILE)
    assert doc["code"] == "drill-failed" and doc["ref"] == "backup-mismatch"
    assert doc["problems"]


def test_restore_guard_without_a_target_database_is_recorded(driven_kb,
                                                              capsys):
    base, _fake, _ = driven_kb
    assert main_mod.cmd_restore(base, from_dir=str(export_dir(base))) == 1
    assert "must name it with --database" in capsys.readouterr().err
    doc = _record(base, RESTORE_REPORT_FILE)
    assert doc["code"] == "restore-guard"
    assert doc["from"] == str(export_dir(base))
