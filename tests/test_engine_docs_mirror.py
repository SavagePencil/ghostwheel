"""The packaged docs mirror (graph/engine_docs/) must byte-match its
sources — design/ and .claude/skills/ — so the package ships exactly
the living copies. A consuming knowledge base vendors FROM the
installed package; a stale mirror would ship a second truth."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = ROOT / "graph" / "engine_docs"


def test_design_records_mirror_byte_identical():
    sources = sorted((ROOT / "design").glob("*.md"))
    assert sources, "design/ is empty?"
    for source in sources:
        mirrored = MIRROR / "design" / source.name
        assert mirrored.exists(), f"{source.name} missing from the mirror"
        assert mirrored.read_bytes() == source.read_bytes(), \
            f"{source.name} drifted — re-copy design/ into graph/engine_docs/"
    extras = {p.name for p in (MIRROR / "design").glob("*.md")} \
        - {s.name for s in sources}
    assert not extras, f"mirror carries retired records: {sorted(extras)}"


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


def test_skills_mirror_byte_identical():
    sources = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    assert sources, ".claude/skills is empty?"
    for source in sources:
        name = source.parent.name
        mirrored = MIRROR / "skills" / name / "SKILL.md"
        assert mirrored.exists(), f"skill {name} missing from the mirror"
        assert mirrored.read_bytes() == source.read_bytes(), \
            f"skill {name} drifted — re-copy into graph/engine_docs/"
    extras = {p.parent.name for p in (MIRROR / "skills").glob("*/SKILL.md")} \
        - {s.parent.name for s in sources}
    assert not extras, f"mirror carries retired skills: {sorted(extras)}"
