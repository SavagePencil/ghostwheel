"""The canon -> markdown-table renderer: a table rendered FROM THE GRAPH
round-trips green through the round-trip judge's table tier, and a CSV no
declaration maps is reported loudly as a gap (never silently skipped)
with a proposed declaration shape.

Runs on an imaginary domain (gadgets) — engine tests speak no project
vocabulary. The graph is constructed the way canon holds it (schema rows
carrying spec_json, citizens and edges as ground), then rendered from
that graph, so the render proves the graph carries the table (it never
copies the CSV).
"""

import json

from graph import render_tables, roundtrip
from graph.extract import GraphData, make_edge
from graph.ontology import (ARCHETYPE_LABEL, RENDERED_VIEWS_PROP,
                            ontology_from_graph)

# One source-mapped label with a property AND an edge-carried column, plus
# a second label reached only by that edge. `Boost` shares an edge type
# across two columns disambiguated by props (a shared-edge shape seen in
# the wild) to exercise the props matcher.
PART_SPEC = {"values": ["Bolt", "Spring", "Cog"], "concept": "Gadget Concept"}
GIZMO_SPEC = {
    "source": "data/gizmos.csv",
    "key": "Gizmo",
    "concept": "Gadget Concept",
    "catalog": {"power": {"type": "int", "doc": "power rating"}},
    "properties": {"power": {"column": "Power"}},
    "relationships": [
        {"type": "USES_PART", "to": "Part", "column": "Parts"},
        {"type": "BOOSTS", "to": "Part", "column": "On Attack",
         "props": {"when": "attack"}},
        {"type": "BOOSTS", "to": "Part", "column": "On Defense",
         "props": {"when": "defense"}},
    ],
}

GIZMOS = """\
Gizmo,Power,Parts,On Attack,On Defense
Widget,5,Bolt,Cog,Spring
Sprocket,3,"Bolt, Spring",,Cog
"""

DOC = """\
# Gadgets

## Catalog

{{csv:data/gizmos.csv}}
"""

# A chapter that also embeds a CSV no declaration consumes (the gap class).
TRINKETS = "Trinket,Shine\nBauble,bright\n"
DOC_WITH_GAP = """\
# Gadgets

## Catalog

{{csv:data/gizmos.csv}}

## Oddments

{{csv:data/trinkets.csv}}
"""


def write_files(base_dir, files):
    for relpath, content in files.items():
        path = base_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def declare_label(graph, label, spec, **props):
    graph.ensure_node(ARCHETYPE_LABEL, label,
                      spec_json=json.dumps(spec, sort_keys=True), **props)
    graph.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                 ARCHETYPE_LABEL, "Ontology"))
    return graph


def build(tmp_path, doc=DOC, extra=None):
    files = {"docs/gadgets.md": doc, "data/gizmos.csv": GIZMOS}
    files.update(extra or {})
    write_files(tmp_path, files)
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, "Ontology")
    declare_label(graph, "Part", PART_SPEC)
    declare_label(graph, "Gizmo", GIZMO_SPEC)
    for part in PART_SPEC["values"]:
        graph.ensure_node("Part", part)
    graph.ensure_node("Gizmo", "Widget", power=5)
    graph.ensure_node("Gizmo", "Sprocket", power=3)
    graph.edges += [
        make_edge("USES_PART", "Gizmo", "Widget", "Part", "Bolt"),
        make_edge("USES_PART", "Gizmo", "Sprocket", "Part", "Bolt"),
        make_edge("USES_PART", "Gizmo", "Sprocket", "Part", "Spring"),
        make_edge("BOOSTS", "Gizmo", "Widget", "Part", "Cog",
                  {"when": "attack"}),
        make_edge("BOOSTS", "Gizmo", "Widget", "Part", "Spring",
                  {"when": "defense"}),
        make_edge("BOOSTS", "Gizmo", "Sprocket", "Part", "Cog",
                  {"when": "defense"}),
    ]
    return tmp_path, ontology_from_graph(graph, tmp_path), graph


def test_rendered_source_mapped_table_round_trips_green(tmp_path):
    base_dir, ontology, graph = build(tmp_path)
    chapter = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology)
    [table] = chapter.tables
    assert table.rendered and table.label == "Gizmo"

    result = roundtrip.run(base_dir, "docs/gadgets.md",
                           _write(base_dir, chapter))
    tier = next(t for t in result.tiers if t.tier == "table")
    assert tier.passed, roundtrip.render_report(result)
    assert tier.checked == 2  # both source rows accounted for


def test_edge_cells_come_from_the_graph_not_the_csv(tmp_path):
    # break the graph (drop an edge) and the judge must red — proof the
    # edge cell was rendered from the graph, not copied from the CSV
    base_dir, ontology, graph = build(tmp_path)
    graph.edges = [e for e in graph.edges
                   if not (e.type == "USES_PART" and e.from_name == "Widget")]
    chapter = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology)
    result = roundtrip.run(base_dir, "docs/gadgets.md",
                           _write(base_dir, chapter))
    tier = next(t for t in result.tiers if t.tier == "table")
    assert not tier.passed
    assert any("Widget" in str(f) for f in tier.findings)


def test_shared_edge_type_is_split_by_declaration_props(tmp_path):
    # Widget's On Attack=Cog and On Defense=Spring share the BOOSTS edge
    # type; the props matcher must keep each column's target distinct, so
    # both source cells round-trip.
    base_dir, ontology, graph = build(tmp_path)
    chapter = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology)
    result = roundtrip.run(base_dir, "docs/gadgets.md",
                           _write(base_dir, chapter))
    tier = next(t for t in result.tiers if t.tier == "table")
    assert tier.passed, roundtrip.render_report(result)


def test_unmapped_csv_is_reported_as_a_loud_gap(tmp_path):
    base_dir, ontology, graph = build(
        tmp_path, doc=DOC_WITH_GAP,
        extra={"data/trinkets.csv": TRINKETS})
    chapter = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology)
    by_path = {t.relpath: t for t in chapter.tables}

    gap = by_path["data/trinkets.csv"]
    assert not gap.rendered
    assert gap.gap and "no declaration consumes it" in gap.gap
    # the gap is named in the draft, not silently dropped
    assert "data/trinkets.csv" in chapter.draft()
    assert "MAPPING GAP" in chapter.draft()
    # a proposed declaration shape names the CSV's own columns
    assert "PROPOSED" in gap.proposal
    assert "source: data/trinkets.csv" in gap.proposal
    assert "'Shine'" in gap.proposal
    # the sibling source-mapped table still renders
    assert by_path["data/gizmos.csv"].rendered


def test_bool_property_emits_no_invented_token():
    # a boolean stores no source token — format_value emits no cell rather
    # than inventing one, so the honest signal is a cell-loss, not a wrong
    # value smuggled into the draft
    from graph.ontology import PropType
    assert render_tables.format_value({"type": PropType.BOOL}, True) is None
    assert render_tables.format_value({"type": PropType.INT}, -4) == "-4"
    assert render_tables.format_value({"type": PropType.TEXT}, "x") == "x"


def test_pipe_in_a_cell_is_escaped():
    # a value containing the table delimiter must not split into phantom
    # cells (which would corrupt every downstream row)
    assert render_tables.cell_text("a|b") == "a\\|b"
    assert render_tables.cell_text("one\ntwo") == "one two"


def _write(base_dir, chapter):
    draft = base_dir / "draft.md"
    draft.write_text(chapter.draft(), encoding="utf-8")
    return draft


# -- Leg 2: rendered_view (render/judge-only mapping) -----------------------

WIDGET_VIEW_SPEC = {
    "implicit": True,
    "concept": "Gadget Concept",
    "catalog": {"power": {"type": "int", "doc": "power rating"}},
}
WIDGET_VIEW = {
    "source": "data/widgets.csv",
    "key": "Code",
    "name_template": "Widget {key}",
    "properties": {"power": {"column": "Power"}},
}


def test_rendered_view_renders_implicit_label_and_round_trips(tmp_path):
    # an implicit label (citizens by delta) renders from its CSV via
    # rendered_view: name_template recovers the key cell, the int column
    # round-trips type-aware ("+5" the source token, 5 in the graph)
    write_files(tmp_path, {"data/widgets.csv": "Code,Power\n7,+5\n",
                           "docs/widgets.md": "# W\n\n"
                                              "{{csv:data/widgets.csv}}\n"})
    schema = GraphData()
    schema.ensure_node(ARCHETYPE_LABEL, "Ontology")
    declare_label(schema, "Widget", WIDGET_VIEW_SPEC,
                  **{RENDERED_VIEWS_PROP: json.dumps([WIDGET_VIEW])})
    ontology = ontology_from_graph(schema, tmp_path)

    graph = GraphData()
    graph.nodes[("Widget", "Widget 7")] = {"power": 5}
    chapter = render_tables.render_chapter(
        tmp_path, "docs/widgets.md", graph, ontology)
    [table] = chapter.tables
    assert table.rendered and table.label == "Widget"

    result = roundtrip.run(tmp_path, "docs/widgets.md",
                           _write(tmp_path, chapter), ontology=ontology)
    tier = next(t for t in result.tiers if t.tier == "table")
    assert tier.passed, roundtrip.render_report(result)


def test_key_from_name_inverts_the_template():
    assert render_tables.key_from_name("Widget 7", "Widget {key}") == "7"
    assert render_tables.key_from_name("Level 12", "Level {key}") == "12"
    # a name that does not fit the template falls back to the name itself
    assert render_tables.key_from_name("Bolt", "Widget {key}") == "Bolt"
    # no template: the name IS the key cell
    assert render_tables.key_from_name("Bolt", None) == "Bolt"


# -- Leg 3: parser-column inversions ---------------------------------------

GRADE_SPEC = {
    "values": ["Tiny", "Big"],
    "aliases": {"T": "Tiny", "B": "Big"},
    "concept": "Gadget Concept",
    "relationships": [
        {"type": "BEATS", "to": "Grade", "source": "data/matrix.csv",
         "parser": "size_matrix"},
    ],
}

MATRIX = ",Visitor: T,Visitor: B\n**Keeper: T**,+0,+2\n**Keeper: B**,-1,N/A\n"


def test_size_matrix_inverts_to_the_source_layout(tmp_path):
    # the matrix parser lifts cells to edges; the inverter rebuilds the
    # matrix FROM those edges and round-trips (N/A cells carry no edge)
    write_files(tmp_path, {"data/matrix.csv": MATRIX,
                           "docs/matrix.md": "# M\n\n"
                                             "{{csv:data/matrix.csv}}\n"})
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, "Ontology")
    declare_label(graph, "Grade", GRADE_SPEC)
    for grade in GRADE_SPEC["values"]:
        graph.ensure_node("Grade", grade)
    # the matrix's lifted edges: (visitor)-[:BEATS {modifier}]->(keeper)
    graph.edges += [
        make_edge("BEATS", "Grade", "Tiny", "Grade", "Tiny", {"modifier": 0}),
        make_edge("BEATS", "Grade", "Big", "Grade", "Tiny", {"modifier": 2}),
        make_edge("BEATS", "Grade", "Tiny", "Grade", "Big", {"modifier": -1}),
    ]
    ontology = ontology_from_graph(graph, tmp_path)

    chapter = render_tables.render_chapter(
        tmp_path, "docs/matrix.md", graph, ontology)
    [table] = chapter.tables
    assert table.rendered, chapter.draft()
    assert "**Keeper: T**" in table.markdown and "N/A" in table.markdown

    result = roundtrip.run(tmp_path, "docs/matrix.md",
                           _write(tmp_path, chapter), ontology=ontology)
    tier = next(t for t in result.tiers if t.tier == "table")
    assert tier.passed, roundtrip.render_report(result)


TOOL_SPEC = {
    "source": "data/tools.csv",
    "key": "Tool",
    "concept": "Gadget Concept",
    "catalog": {"note_text": {"type": "text", "doc": "unmatched remainder"}},
    "relationships": [
        {"type": "BLOCKED_BY", "to": "Trait", "column": "Blocked",
         "on_missing": "report", "unmatched_property": "note_text"},
    ],
}


def test_mixed_column_renders_edges_plus_verbatim_remainder(tmp_path):
    # a column that mixes known targets (edges) with prose the parser could
    # not resolve (kept in unmatched_property) renders BOTH in the one cell,
    # and round-trips as an order-free set
    write_files(tmp_path, {
        "data/tools.csv": "Tool,Blocked\nHammer,\"Sharp, some prose\"\n",
        "docs/tools.md": "# T\n\n{{csv:data/tools.csv}}\n"})
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, "Ontology")
    declare_label(graph, "Trait", {"values": ["Sharp", "Heavy"],
                                   "concept": "Gadget Concept"})
    declare_label(graph, "Tool", TOOL_SPEC)
    for trait in ("Sharp", "Heavy"):
        graph.ensure_node("Trait", trait)
    graph.ensure_node("Tool", "Hammer", note_text="some prose")
    graph.edges.append(make_edge("BLOCKED_BY", "Tool", "Hammer",
                                 "Trait", "Sharp"))
    ontology = ontology_from_graph(graph, tmp_path)

    chapter = render_tables.render_chapter(
        tmp_path, "docs/tools.md", graph, ontology)
    [table] = chapter.tables
    assert "Sharp" in table.markdown and "some prose" in table.markdown

    result = roundtrip.run(tmp_path, "docs/tools.md",
                           _write(tmp_path, chapter), ontology=ontology)
    tier = next(t for t in result.tiers if t.tier == "table")
    assert tier.passed, roundtrip.render_report(result)


def test_prerequisites_cell_inverter_reconstructs_from_edges():
    # the per-cell parser inverter rebuilds a requirements cell from the
    # structured edges plus the verbatim remainder (imaginary labels)
    from graph.grammars import get
    invert = get("prerequisites.cell")
    graph = GraphData()
    graph.edges = [
        make_edge("NEEDS", "Tool", "Drill", "Skill", "Welding",
                  {"min_stage": "Novice"}),
        make_edge("NEEDS", "Tool", "Drill", "Trait", "Sharp", {})]
    rel = {"type": "NEEDS", "unmatched_property": "note"}
    cell = invert(graph, "Tool", "Drill", rel, {"note": "extra clause"})
    assert "Welding at Novice or higher" in cell
    assert "Sharp" in cell
    assert "extra clause" in cell


def test_header_row_carries_declared_column_names(tmp_path):
    # the declarations have always known every column's name; the header
    # row says them instead of positional placeholders
    base_dir, ontology, graph = build(tmp_path)
    chapter = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology)
    [table] = chapter.tables
    header = table.markdown.splitlines()[0]
    assert "Gizmo" in header and "Power" in header and "Parts" in header
    assert "col1" not in header


def test_numeric_rosters_order_as_a_ladder():
    # string sort put rung 10 before rung 3; numeric names order numerically
    from graph.render_tables import _members
    g = GraphData()
    for n in ["10", "3", "18", "4"]:
        g.ensure_node("Rung", n)
    assert _members(g, "Rung") == ["3", "4", "10", "18"]
    h = GraphData()
    for n in ["Rung 10", "Rung 3", "Rung 18"]:
        h.ensure_node("[Step]", n)
    assert _members(h, "[Step]") == ["Rung 3", "Rung 10", "Rung 18"]


def test_multi_label_contributors_align_by_column_name():
    # a contributor whose declaration maps fewer/different columns must
    # land its cells under the SHARED header positions, never slide left
    # (owner-caught: a boost value rendered under a span column)
    from graph.render_tables import render_view_table
    g = GraphData()
    g.ensure_node("Gizmo", "Auger", span="1", boost="2")
    g.ensure_node("Baseline", "Ground Boost", boost="10")
    view = {
        "key": "Type",
        "labels": [
            {"label": "Gizmo",
             "properties": {"span": {"column": "Span"},
                            "boost": {"column": "Boost"}}},
            {"label": "Baseline",
             "properties": {"boost": {"column": "Boost"}}},
        ],
    }

    class _Ont:
        nodes = {"Gizmo": {}, "Baseline": {}}
    table = render_view_table(g, _Ont(), "Gizmo", view)
    lines = table.splitlines()
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    base_row = [c.strip() for c in
                next(l for l in lines if "Ground Boost" in l)
                .strip("|").split("|")]
    assert header == ["Type", "Span", "Boost"]
    assert base_row == ["Ground Boost", "", "10"]  # 10 under Boost, not Span


def test_unregistered_parser_column_renders_nothing():
    # no named-but-always-empty ghost columns: a parser mapping without a
    # registered inverter is excluded from header AND cells alike
    from graph.render_tables import render_label_table

    class _Ont:
        nodes = {"Potion": {
            "key": "Potion",
            "properties": {"strength": {"column": "Strength"}},
            "relationships": [
                {"type": "MYSTERY", "parser": "no_such_grammar",
                 "column": "Ghost"},
            ],
        }}
    g = GraphData()
    g.ensure_node("Potion", "Vigor", strength="3")
    table = render_label_table(g, _Ont(), "Potion")
    assert "Ghost" not in table
    header = table.splitlines()[0]
    assert "Strength" in header
