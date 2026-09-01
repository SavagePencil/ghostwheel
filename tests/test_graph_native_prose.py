"""Graph-native prose: the section machinery unhooked from source files.

A born-graph-native label has no `source:` — its bodies live on the
nodes as ground. An explicit `reader: markdown_sections` marks it prose
anyway, and the part_of parser takes its linking prop from the
relationship spec (`column`, defaulting to `file` — the from-sources
shape, unchanged), so containment re-derives as PART_OF exactly like
every other machine layer.
"""

from pathlib import Path

from graph.extract import Extractor
from graph.ontology import Ontology, Reader, node_reader


def _prose_ontology(tmp_path, column=None):
    rel = {"type": "PART_OF", "to": "Record", "parser": "part_of"}
    if column:
        rel["column"] = column
    return Ontology(
        path=tmp_path / "graph" / "ontology.yaml", base_dir=tmp_path,
        raw={},
        nodes={"Record": {"concept": "Record"},
               "Section": {"concept": "Section",
                           "reader": "markdown_sections",
                           "relationships": [rel]}})


def test_explicit_reader_needs_no_source_file():
    assert node_reader({"reader": "markdown_sections"}) \
        == Reader.MARKDOWN_SECTIONS
    # Unresolvable stays unresolvable: no reader, no source.
    assert node_reader({"concept": "Section"}) is None
    # From-sources inference is unchanged.
    assert node_reader({"source": "docs/x.md"}) == Reader.MARKDOWN_SECTIONS


def test_part_of_derives_from_the_declared_linking_prop(tmp_path):
    extractor = Extractor(_prose_ontology(tmp_path, column="record"))
    extractor.graph.ensure_node("Record", "The Doctrine")
    extractor.graph.ensure_node("Section", "Opening",
                                body="# Opening\n", rank=0,
                                record="The Doctrine")
    extractor.derive_markdown_rels()
    assert any(e.type == "PART_OF"
               and (e.from_label, e.from_name) == ("Section", "Opening")
               and (e.to_label, e.to_name) == ("Record", "The Doctrine")
               for e in extractor.graph.edges)
    # The prose body was captured for the term/mention machinery.
    assert extractor.section_bodies[("Section", "Opening")] == "# Opening\n"


def test_part_of_default_linking_prop_stays_file(tmp_path):
    extractor = Extractor(_prose_ontology(tmp_path))
    extractor.graph.ensure_node("Record", "docs/x.md")
    extractor.graph.ensure_node("Section", "Opening",
                                body="# Opening\n", file="docs/x.md")
    extractor.derive_markdown_rels()
    assert any(e.type == "PART_OF"
               and (e.to_label, e.to_name) == ("Record", "docs/x.md")
               for e in extractor.graph.edges)


def test_sections_without_the_linking_prop_derive_nothing(tmp_path):
    extractor = Extractor(_prose_ontology(tmp_path, column="record"))
    extractor.graph.ensure_node("Section", "Loose Note", body="hm\n")
    extractor.derive_markdown_rels()
    assert not [e for e in extractor.graph.edges if e.type == "PART_OF"]
