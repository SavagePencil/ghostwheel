"""The reading room: fingerprints as identity, deterministic section ids,
duplicate headings as a non-event, and the archive round trip. Pure logic
— no database needed."""

from graph.comprehension import (fingerprint_bytes, parse_archive,
                                 read_archive, read_artifact, serialize,
                                 write_archive)

DOC = b"""\
# The Hollow Oak

Intro prose.

## The Knot Door

Opening rules. {{csv:data/door_sizes.csv}}

### Door Size Comparison Matrix

The matrix explained.
{{csv:data/size_matrix.csv|columns=Visitor, Keeper}}

## The Hollow Oak

The duplicate-heading section the flat era silently dropped.
"""


def test_fingerprint_is_identity_regardless_of_origin():
    a = read_artifact(DOC, title="my_doc.docx", origin="/Users/james/Downloads")
    b = read_artifact(DOC, title="cool_doc.docx", origin="C:/Temp")
    assert a.fingerprint == b.fingerprint == fingerprint_bytes(DOC)
    # title and origin are display metadata, never identity
    assert [s["id"] for s in a.sections] == [s["id"] for s in b.sections]


def test_section_tree_nesting_and_order():
    reading = read_artifact(DOC, title="doc")
    by_heading_pos = reading.sections
    root, block, matrix, dup = by_heading_pos
    assert root["parent"] is None and root["level"] == 1
    assert block["parent"] == root["id"] and block["level"] == 2
    assert matrix["parent"] == block["id"] and matrix["level"] == 3
    assert dup["parent"] == root["id"] and dup["level"] == 2
    # sibling order within a parent
    assert block["order"] == 0 and dup["order"] == 1


def test_duplicate_headings_are_a_non_event():
    reading = read_artifact(DOC, title="doc")
    dupes = [s for s in reading.sections if s["heading"] == "The Hollow Oak"]
    assert len(dupes) == 2
    assert dupes[0]["id"] != dupes[1]["id"]
    assert "silently dropped" in dupes[1]["body"]  # nothing lost


def test_ids_are_deterministic_and_positional():
    once = read_artifact(DOC, title="doc")
    twice = read_artifact(DOC, title="doc")
    assert [s["id"] for s in once.sections] == \
        [s["id"] for s in twice.sections]
    # ids derive from fingerprint + position, never heading text
    for section in once.sections:
        prefix, _, path = section["id"].partition(":")
        assert prefix == once.short
        assert all(part.isdigit() for part in path.split("."))


def test_skipped_levels_attach_to_nearest_ancestor():
    doc = b"# Top\n\n### Deep\n\nbody\n"
    reading = read_artifact(doc, title="doc")
    top, deep = reading.sections
    assert deep["parent"] == top["id"]


def test_embedded_table_refs_are_parsed():
    reading = read_artifact(DOC, title="doc")
    embeds = {s["heading"]: s["embeds"] for s in reading.sections}
    assert embeds["The Knot Door"] == ["data/door_sizes.csv"]
    assert embeds["Door Size Comparison Matrix"] == ["data/size_matrix.csv"]
    assert embeds["The Hollow Oak"] == []


def test_archive_round_trip_in_memory():
    reading = read_artifact(DOC, title="my_doc.docx", origin="Downloads")
    files = serialize(reading)
    back = parse_archive(files)
    assert back.fingerprint == reading.fingerprint
    assert back.title == reading.title
    assert back.sections == reading.sections
    # deterministic: same Reading, byte-identical archive
    assert serialize(back) == files


def test_spans_classify_tables_and_prose_in_order():
    reading = read_artifact(DOC, title="doc")
    block = next(s for s in reading.sections
                 if s["heading"] == "The Knot Door")
    assert [span["class"] for span in block["spans"]] == \
        ["rule-prose", "table"]
    assert block["spans"][1]["table"] == "data/door_sizes.csv"
    assert "Opening rules." in block["spans"][0]["text"]
    assert block["classes"] == ["rule-prose", "table"]


def test_cited_sections_classify_as_procedure():
    reading = read_artifact(DOC, title="doc",
                            cited_sections={"The Knot Door"})
    block = next(s for s in reading.sections
                 if s["heading"] == "The Knot Door")
    assert [span["class"] for span in block["spans"]] == \
        ["procedure", "table"]
    # only the cited section changes; siblings stay rule-prose
    dup = [s for s in reading.sections
           if s["heading"] == "The Hollow Oak"][1]
    assert dup["classes"] == ["rule-prose"]


def test_prose_never_defaults_to_verbatim_carried():
    # flavor is designer judgment at the plan gate, never a machine guess
    flavor = (b"# The Tale of the Hollow Oak\n\n"
              b"Readers follow a small Beast through the wood.\n")
    reading = read_artifact(flavor, title="intro")
    assert reading.sections[0]["classes"] == ["rule-prose"]


def test_carried_fraction_math():
    from graph.comprehension import carried_fraction
    sections = [{"spans": [
        {"class": "verbatim-carried", "text": "aaaa"},       # 4 chars
        {"class": "rule-prose", "text": "bbbbbbbbbbbb"},     # 12 chars
        {"class": "table", "text": "{{csv:x.csv}}"},         # excluded
    ]}]
    assert carried_fraction(sections) == 4 / 16
    assert carried_fraction([{"spans": []}]) == 0.0


def test_archive_round_trip_on_disk(tmp_path):
    reading = read_artifact(DOC, title="doc")
    write_archive(reading, tmp_path / "doc-abc123")
    back = read_archive(tmp_path / "doc-abc123")
    assert back.sections == reading.sections
    # a deleted archive is recoverable by recomputation from the bytes
    recomputed = read_artifact(DOC, title="doc")
    assert serialize(recomputed) == serialize(back)
