"""The docs reader: engine design records are pulled from the installed
package, never vendored into a knowledge base (the copy-retirement,
stage 1). The command opens no knowledge base and no database — it must
answer from anywhere, including a bare directory with no base in sight.
"""

from graph.__main__ import ENGINE_DOCS_DIR, main


def _no_base_anywhere(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)


def test_known_record_prints_the_packaged_file(capsys, tmp_path,
                                               monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["docs", "ontology-doctrine"]) == 0
    out = capsys.readouterr().out
    packaged = (ENGINE_DOCS_DIR / "ontology-doctrine.md") \
        .read_text(encoding="utf-8")
    assert out == packaged


def test_bare_docs_lists_every_packaged_record(capsys, tmp_path,
                                               monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["docs"]) == 0
    out = capsys.readouterr().out
    packaged = sorted(p.stem for p in ENGINE_DOCS_DIR.glob("*.md"))
    assert packaged, "the package must ship design records"
    for name in packaged:
        assert name in out


def test_unknown_record_refuses_naming_the_available(capsys, tmp_path,
                                                     monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["docs", "no-such-record"]) == 2
    err = capsys.readouterr().err
    assert "no packaged record carries that name" in err
    assert "ontology-doctrine" in err
