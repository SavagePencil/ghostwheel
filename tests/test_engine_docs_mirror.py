"""The packaged canon mirror (graph/engine_docs/canon/) must byte-match
the manual's committed export — the package ships exactly the canon the
records are rendered from. A consuming knowledge base pulls records
FROM the installed package; a stale mirror would ship a second truth."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = ROOT / "graph" / "engine_docs"


def test_canon_mirror_byte_identical():
    sources = sorted((ROOT / "manual" / "graph" / "export").glob("*.jsonl"))
    assert sources, "the manual's export is empty?"
    for source in sources:
        mirrored = MIRROR / "canon" / source.name
        assert mirrored.exists(), f"{source.name} missing from the mirror"
        assert mirrored.read_bytes() == source.read_bytes(), \
            f"{source.name} drifted — re-copy manual/graph/export/ into " \
            "graph/engine_docs/canon/"
    extras = {p.name for p in (MIRROR / "canon").glob("*.jsonl")} \
        - {s.name for s in sources}
    assert not extras, f"mirror carries retired files: {sorted(extras)}"


def test_the_prose_mirrors_stay_retired():
    for retired in ("design", "skills"):
        assert not (MIRROR / retired).exists(), \
            f"graph/engine_docs/{retired}/ returned after the flip — " \
            "records live in canon; the packaged prose mirrors are retired"
