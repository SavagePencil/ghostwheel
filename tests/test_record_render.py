"""The canon-backed record render.

Parity: every record the canon carries renders byte-identical to the
packaged prose file it was born from — the flip criterion. These
assertions retire with the files; the golden snapshot does not: it pins
the render within a version (same canon, same bytes), regenerated
deliberately in the change set that moves the canon
(GOLDEN_REGEN=1 pytest tests/test_record_render.py).
"""

import hashlib
import json
import os
from pathlib import Path

from graph import records
from graph.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = Path(__file__).resolve().parent / "golden" / "record_render.json"


def _renders():
    canon = records.load_canon()
    assert canon is not None, "the package must ship the manual's canon"
    return {handle: records.render(canon, label, name)
            for handle, (label, name) in records.records(canon).items()}


def _source_path(handle, label_name):
    label, _ = label_name
    if records.is_conduct(label):
        return ROOT / ".claude" / "skills" / handle / "SKILL.md"
    return ROOT / "design" / f"{handle}.md"


def test_every_canon_record_renders_byte_identical_to_its_file():
    canon = records.load_canon()
    listing = records.records(canon)
    assert listing, "the canon must carry records"
    for handle, (label, name) in sorted(listing.items()):
        source = _source_path(handle, (label, name))
        assert source.is_file(), f"{handle}: no prose file at {source}"
        rendered = records.render(canon, label, name)
        assert rendered == source.read_text(encoding="utf-8"), \
            f"{handle} render drifted from {source}"


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


def test_docs_serves_canon_for_a_canonized_record(capsys, tmp_path,
                                                  monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    renders = _renders()
    handle = sorted(renders)[0]
    assert main(["docs", handle]) == 0
    assert capsys.readouterr().out == renders[handle]


def test_docs_falls_back_to_the_file_for_the_rest(capsys, tmp_path,
                                                  monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    in_canon = set(_renders())
    on_file = {d.name for d in
               (ROOT / "graph" / "engine_docs" / "skills").iterdir()
               if (d / "SKILL.md").is_file()}
    fallbacks = sorted(on_file - in_canon)
    if not fallbacks:  # post-flip: nothing left to fall back to
        return
    handle = fallbacks[0]
    assert main(["docs", handle]) == 0
    packaged = (ROOT / "graph" / "engine_docs" / "skills" / handle /
                "SKILL.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out == packaged


def test_a_missing_canon_means_files_only(tmp_path):
    assert records.load_canon(tmp_path / "nowhere") is None


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
