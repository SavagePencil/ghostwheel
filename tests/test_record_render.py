"""The canon-backed record render.

The golden snapshot pins the render within a version (same canon, same
bytes), regenerated deliberately in the change set that moves the canon
(GOLDEN_REGEN=1 pytest tests/test_record_render.py). The parity tests
that once held every render byte-identical to a prose file retired with
the files at the flip; the golden is the render's keeper now.
"""

import hashlib
import json
import os
from pathlib import Path

from graph import records
from graph.__main__ import main

GOLDEN = Path(__file__).resolve().parent / "golden" / "record_render.json"


def _renders():
    canon = records.load_canon()
    assert canon is not None, "the package must ship the manual's canon"
    return {handle: records.render(canon, label, name)
            for handle, (label, name) in records.records(canon).items()}


def test_render_matches_the_golden_snapshot():
    hashes = {handle: hashlib.sha256(text.encode("utf-8")).hexdigest()
              for handle, text in sorted(_renders().items())}
    if os.environ.get("GOLDEN_REGEN"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(hashes, indent=2, sort_keys=True)
                          + "\n", encoding="utf-8")
    assert GOLDEN.is_file(), \
        "no golden snapshot — regenerate: GOLDEN_REGEN=1 pytest " \
        "tests/test_record_render.py"
    assert hashes == json.loads(GOLDEN.read_text(encoding="utf-8")), \
        "the render moved. If the canon changed on purpose, regenerate " \
        "in this change set: GOLDEN_REGEN=1 pytest tests/test_record_render.py"


def test_docs_serves_the_canon_render(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    renders = _renders()
    handle = sorted(renders)[0]
    assert main(["docs", handle]) == 0
    assert capsys.readouterr().out == renders[handle]


def test_a_missing_canon_reads_as_none():
    assert records.load_canon(Path("/nowhere/at/all")) is None


def test_docs_refuses_plainly_without_the_packaged_canon(capsys,
                                                         monkeypatch):
    monkeypatch.setattr(records, "load_canon", lambda *a, **k: None)
    assert main(["docs"]) == 2
    assert "the packaged canon is missing" in capsys.readouterr().err


def test_render_orders_members_by_rank():
    from graph.extract import GraphData, make_edge
    graph = GraphData()
    graph.ensure_node("Thing", "container", handle="thing")
    graph.ensure_node("Piece", "tail", rank=2, body="tail")
    graph.ensure_node("Piece", "head", rank=1, body="head ")
    for name in ("tail", "head"):
        graph.edges.append(make_edge(
            "PART_OF", "Piece", name, "Thing", "container"))
    assert records.render(graph, "Thing", "container") == "head tail"
