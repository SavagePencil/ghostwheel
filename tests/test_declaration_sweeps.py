"""The glossary sweep's file set is declaration-driven, not hardcoded.

The swept prose is what the schema on the graph declares — markdown
sources and the markdown members of file-valued (fingerprint) labels —
minus the sources declared non-prose (a list riding the Ontology
anchor). No directory or filename is baked into the engine: a corpus
with a different layout is swept from its own declarations.
"""

import json

from graph.extract import GraphData, make_edge
from graph.ontology import ARCHETYPE_LABEL, ontology_from_graph

PROSE_FILES = ("book/00-index.md", "book/01-intro.md", "book/02-rules.md")


def _declare(g, name, layer="Ontology", **props):
    g.ensure_node(ARCHETYPE_LABEL, name, **props)
    g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                             ARCHETYPE_LABEL, layer))


def prose_schema(tmp_path):
    """A graph-built schema declaring three prose pages, one of them
    marked non-prose on the anchor — plus undeclared markdown on disk
    that must never be swept."""
    files = {
        "book/00-index.md": "# Contents\n\n- Intro\n- Rules\n",
        "book/01-intro.md": "# Intro\n\nThe Widget is central.\n",
        "book/02-rules.md": "# Rules\n\nA Gadget resists a Widget.\n",
        # exists on disk but is never declared — must not be swept
        "book/99-undeclared.md": "# Ghost\n\nUndeclared prose.\n",
        # markdown elsewhere in the repo — must not be swept either
        "notes/scratch.md": "# Scratch\n\nStray note.\n",
    }
    for relpath, content in files.items():
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    g = GraphData()
    g.ensure_node(ARCHETYPE_LABEL, "Ontology", version=1,
                  enums_json="{}", defaults_json="{}",
                  non_prose_sources=["book/00-index.md"])
    g.ensure_node(ARCHETYPE_LABEL, "Metaontology", version="0.0.0")
    for kernel in ("Concept", "Provenance"):
        _declare(g, kernel, layer="Metaontology")
    _declare(g, "Lore")
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Lore",
                             ARCHETYPE_LABEL, "Concept"))
    _declare(g, "Page", spec_json=json.dumps(
        {"fingerprint": True, "values": list(PROSE_FILES),
         "concept": ["Provenance", "Lore"]}, sort_keys=True))
    return g


def test_prose_files_is_declaration_driven(tmp_path):
    ontology = ontology_from_graph(prose_schema(tmp_path), tmp_path)
    assert ontology is not None
    prose = ontology.prose_files()
    # The two real prose chapters are swept, drawn from the declaration.
    assert prose == ["book/01-intro.md", "book/02-rules.md"]
    # The file marked non-prose is skipped BY DECLARATION, not by filename.
    assert "book/00-index.md" not in prose
    # A markdown file that exists but is not declared is never swept,
    # wherever it sits.
    assert "book/99-undeclared.md" not in prose
    assert "notes/scratch.md" not in prose


def test_referenced_files_covers_sources_overlays_and_rosters(tmp_path):
    # referenced_files() is the "which files does any declaration
    # consume" view: row sources, overlays, property tables, and the
    # fingerprint roster of files already taken in as citizens.
    g = prose_schema(tmp_path)
    _declare(g, "Thing", spec_json=json.dumps(
        {"source": "data/things.csv", "key": "Thing",
         "overlay": "data/things.yaml",
         "property_tables": [{"source": "data/weights.csv", "key": "Thing",
                              "properties": {}}],
         "catalog": {"weight": {"type": "int", "doc": "how heavy"}}},
        sort_keys=True))
    ontology = ontology_from_graph(g, tmp_path)
    referenced = ontology.referenced_files()
    assert {"data/things.csv", "data/things.yaml", "data/weights.csv"} \
        <= referenced
    assert set(PROSE_FILES) <= referenced  # the fingerprint roster counts
