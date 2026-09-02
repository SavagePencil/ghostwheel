"""The two coverage sweeps are declaration-driven, not hardcoded.

The glossary sweep's file set is the ontology's declared prose (markdown)
sources minus those declared non-prose; the unmapped-artifact sweep walks
the declared content roots and reports files no declaration consumes. No
directory or filename is baked into the engine — a corpus with a different
layout is swept from its own declarations.
"""

from graph.ontology import ERROR, WARNING, load_ontology
from graph.validate import unmapped_artifacts


def errors_of(findings):
    return [f for f in findings if f.severity == ERROR]


# --- Sweep 1: the prose (glossary) sweep --------------------------------------

PROSE_FILES = {
    "book/00-index.md": "# Contents\n\n- Intro\n- Rules\n",
    "book/01-intro.md": "# Intro\n\nThe Widget is central.\n",
    "book/02-rules.md": "# Rules\n\nA Gadget resists a Widget.\n",
    # exists on disk but is never declared — must not be swept
    "book/99-undeclared.md": "# Ghost\n\nUndeclared prose.\n",
    # markdown outside every content root — must not be swept either
    "notes/scratch.md": "# Scratch\n\nStray note.\n",
}

PROSE_ONTOLOGY = """\
    version: 1
    content_roots:
      - book
    non_prose_sources:
      - book/00-index.md
    concepts:
      Lore: { instance_of: Concept }
    nodes:
      Page:
        fingerprint: true
        values:
          - book/00-index.md
          - book/01-intro.md
          - book/02-rules.md
        concept: [Provenance, Lore]
    """


def test_prose_files_is_declaration_driven(make_repo):
    base, path = make_repo(PROSE_FILES, PROSE_ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []
    prose = ontology.prose_files()
    # The two real prose chapters are swept, drawn from the declaration.
    assert prose == ["book/01-intro.md", "book/02-rules.md"]
    # The file marked non-prose is skipped BY DECLARATION, not by filename.
    assert "book/00-index.md" not in prose
    # A markdown file that exists but is not declared is never swept, whether
    # it sits under a content root or entirely outside one.
    assert "book/99-undeclared.md" not in prose
    assert "notes/scratch.md" not in prose


# --- Sweep 2: the unmapped-artifact sweep -------------------------------------

UNMAPPED_FILES = {
    "data/things.csv": "Thing,Kind\nRock,Mineral\n",
    "data/things.yaml": "Rock:\n  weight: 5\n",   # overlay: referenced
    "data/checks.csv": "Case,Expected\nA,1\n",     # answer-key table: referenced
    "data/notes.txt": "a stray non-csv file\n",    # unreferenced, under a root
    "data/aside/README.md": "nested stray\n",      # unreferenced, nested
    "outside/loose.md": "outside every content root\n",
}

UNMAPPED_ONTOLOGY = """\
    version: 1
    content_roots:
      - data
    concepts:
      Kind: { instance_of: Concept }
    nodes:
      Thing:
        source: data/things.csv
        key: Thing
        overlay: data/things.yaml
        catalog:
          weight: { type: int, doc: "how heavy" }
    answer_keys:
      - procedure: Check It
        derives: recompute
        table: data/checks.csv
        result:
          formula: "1"
          expected_column: Expected
    """


def test_unmapped_sweep_surfaces_only_unreferenced_files_under_roots(make_repo):
    base, path = make_repo(UNMAPPED_FILES, UNMAPPED_ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []

    flagged = {f.file for f in unmapped_artifacts(ontology)}

    # A non-CSV unreferenced file under a content root surfaces, at any depth.
    assert "data/notes.txt" in flagged
    assert "data/aside/README.md" in flagged
    # A file outside every content root is never swept.
    assert "outside/loose.md" not in flagged
    # Files any declaration consumes — a source, an overlay, an answer-key
    # table — are recognized as referenced and do not surface.
    assert "data/things.csv" not in flagged
    assert "data/things.yaml" not in flagged
    assert "data/checks.csv" not in flagged


def test_referenced_files_covers_overlays_and_answer_key_tables(make_repo):
    base, path = make_repo(UNMAPPED_FILES, UNMAPPED_ONTOLOGY)
    ontology, _ = load_ontology(path, base)
    assert ontology is not None
    referenced = ontology.referenced_files()
    assert {"data/things.csv", "data/things.yaml", "data/checks.csv"} \
        <= referenced


# --- Validation of the new declarations ---------------------------------------

def test_content_roots_must_be_a_list_of_strings(make_repo):
    bad = UNMAPPED_ONTOLOGY.replace(
        "content_roots:\n      - data", "content_roots: 7")
    base, path = make_repo(UNMAPPED_FILES, bad)
    _, findings = load_ontology(path, base)
    assert any("'content_roots' must be a list" in f.detail
               for f in errors_of(findings))


def test_non_prose_sources_must_be_a_list_of_strings(make_repo):
    bad = PROSE_ONTOLOGY.replace(
        "non_prose_sources:\n      - book/00-index.md",
        "non_prose_sources: { not: a-list }")
    base, path = make_repo(PROSE_FILES, bad)
    _, findings = load_ontology(path, base)
    assert any("'non_prose_sources' must be a list" in f.detail
               for f in errors_of(findings))


def test_missing_content_root_warns(make_repo):
    bad = UNMAPPED_ONTOLOGY.replace(
        "content_roots:\n      - data",
        "content_roots:\n      - data\n      - nowhere")
    base, path = make_repo(UNMAPPED_FILES, bad)
    _, findings = load_ontology(path, base)
    assert any(f.severity == WARNING and "nowhere" in f.detail
               for f in findings)
