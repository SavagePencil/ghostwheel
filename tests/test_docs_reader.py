"""The docs reader: engine records are pulled from the packaged canon,
never vendored into a knowledge base (the copy retirement, completed by
the flip). The command opens no knowledge base and no database — it
must answer from anywhere, including a bare directory with no base in
sight.
"""

from graph import records
from graph.__main__ import main


def _no_base_anywhere(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)


def test_known_record_prints_the_canon_render(capsys, tmp_path,
                                              monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    canon = records.load_canon()
    label, name = records.records(canon)["ontology-doctrine"]
    assert main(["docs", "ontology-doctrine"]) == 0
    assert capsys.readouterr().out == records.render(canon, label, name)


def test_bare_docs_lists_every_canon_record(capsys, tmp_path,
                                            monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["docs"]) == 0
    out = capsys.readouterr().out
    listing = records.records(records.load_canon())
    assert listing, "the packaged canon must carry records"
    for handle in listing:
        assert handle in out
    labels = {label for label, _ in listing.values()}
    assert len(labels) > 1, "both record kinds must be in canon"


def test_conduct_record_prints_the_canon_render(capsys, tmp_path,
                                                monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    canon = records.load_canon()
    label, name = records.records(canon)["agentic-intake"]
    assert records.is_conduct(label)
    assert main(["docs", "agentic-intake"]) == 0
    assert capsys.readouterr().out == records.render(canon, label, name)


def test_unknown_record_refuses_naming_the_available(capsys, tmp_path,
                                                     monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["docs", "no-such-record"]) == 2
    err = capsys.readouterr().err
    assert "no record in the engine's canon carries that name" in err
    assert "ontology-doctrine" in err
