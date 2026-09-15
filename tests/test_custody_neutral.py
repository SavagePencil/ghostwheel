"""Custody is the customer's: the engine never prescribes git.

The engine's durable record is plain files — the committed backup, the
round archives with their inverses, the hash-chained event log — and a
knowledge base keeps them under whatever custody suits it. So a
recovery road in a designer-facing message names "wherever this
knowledge base keeps its history", never one revision-control tool;
and the packaged canon tells the custody story once, carries the
ruling's own words, and speaks git only where it names a convention
(a dependency pin's provenance ref, a lesson's anecdote) — never as
law.
"""

import json
import re
from pathlib import Path

import pytest

import graph.__main__ as main_mod
from graph.restore import read_export
from tests.test_branch import driven_kb  # noqa: F401

CANON = Path("graph/engine_docs/canon/nodes.jsonl")
NEUTRAL = "keeps its history"


def test_a_missing_backup_file_names_the_neutral_road(tmp_path):
    with pytest.raises(FileNotFoundError) as caught:
        read_export(tmp_path)
    message = str(caught.value)
    assert NEUTRAL in message
    assert "git" not in message.lower()


def test_a_missing_knowledge_base_names_the_neutral_road(tmp_path, capsys):
    assert main_mod.cmd_rederive(tmp_path) == 1
    err = capsys.readouterr().err
    assert NEUTRAL in err
    assert "git" not in err.lower()


def test_a_failed_drill_names_the_neutral_road(driven_kb, monkeypatch,
                                               capsys):
    base, fake, _ = driven_kb
    from graph import restore as restore_mod
    monkeypatch.setattr(restore_mod, "verify_against_backup",
                        lambda dumped, export_dir: ["a forced difference"])
    assert main_mod.cmd_restore(base, database="scratch") == 1
    err = capsys.readouterr().err
    assert "DRILL FAILED" in err
    assert NEUTRAL in err
    assert "git" not in err.lower()


def test_the_canon_tells_the_custody_story_and_never_speaks_git_as_law():
    bodies = []
    for line in CANON.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        bodies.append(" ".join(str(v) for v in row["properties"].values()))
    text = re.sub(r"\s+", " ", " ".join(bodies))
    # the story is told, with the ruling's own words
    assert "Custody is the customer" in text
    assert "Customers may not be using git to revision control " \
           "their graph." in text
    # the retired law-phrases are gone
    for retired in ("git archaeology", "committed to git", "git-tracked",
                    "archives in git", "goes in git", "gitignored"):
        assert retired not in text, retired
