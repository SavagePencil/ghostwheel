"""The regression corpus: ledger round-trip, guard matching, and the
owner-facing report. Pure logic — no driver."""

import pytest

from graph.corpus import (load_floors, missing_guards, parse_collected,
                         record_floor, render_report, save_floors)


def test_ledger_round_trips(tmp_path):
    floors = []
    record_floor(floors, "tests/test_corpus.py::test_ledger_round_trips",
                 "corpus", "the ledger round-trips", "PR #7")
    path = tmp_path / "floors.jsonl"
    save_floors(path, floors)
    assert load_floors(path) == floors
    assert load_floors(tmp_path / "absent.jsonl") == []


def test_record_refuses_duplicates_and_empties():
    floors = []
    record_floor(floors, "tests/test_x.py::test_a", "s", "e", "PR #1")
    with pytest.raises(ValueError, match="already backs"):
        record_floor(floors, "tests/test_x.py::test_a", "s2", "e2",
                     "PR #2")
    with pytest.raises(ValueError, match="empty provenance"):
        record_floor(floors, "tests/test_x.py::test_b", "s", "e", "  ")
    with pytest.raises(ValueError, match="pytest node id"):
        record_floor(floors, "tests/test_x.py::test_c[param]", "s", "e",
                     "PR #3")
    assert len(floors) == 1  # refusals landed nothing


def test_parse_collected_folds_parameterized_variants():
    text = ("tests/test_a.py::test_plain\n"
            "tests/test_b.py::test_param[awaken-a-gryphon]\n"
            "tests/test_b.py::test_param[perch-at-dusk]\n"
            "\n8 tests collected in 0.1s\n")
    assert parse_collected(text) == {"tests/test_a.py::test_plain",
                                     "tests/test_b.py::test_param"}


def test_missing_guard_names_the_orphaned_approval():
    floors = []
    record_floor(floors, "tests/test_gone.py::test_deleted", "renderer",
                 "ladders render in rank order", "PR #8")
    problems = missing_guards(floors, {"tests/test_x.py::test_a"})
    [problem] = problems
    assert "GONE" in problem
    assert "ladders render in rank order" in problem
    assert "PR #8" in problem
    report = render_report(floors, problems, [])
    assert "Guards missing" in report and "PR #8" in report


def test_holding_corpus_reports_clean():
    floors = []
    record_floor(floors, "tests/test_x.py::test_a", "s",
                 "the expectation", "PR #1")
    report = render_report(floors, [], [])
    assert "1 floors: 1 held" in report
    assert "nothing the owner approved has been broken" in report
    assert "Regression corpus" in render_report([], [], [])
