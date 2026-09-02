"""Canon -> markdown-table renderer (the table-rendering tier): table-only drafts
for the round-trip judge's table tier.

The purpose is to PROVE the graph carries a chapter's tables. For a
chapter with {{csv:...}} embeds, this renders each table AS MARKDOWN
FROM THE GRAPH — never by copying the CSV (which would pass the judge
while proving nothing). Values come from citizen properties and edges;
only the embed's PATH and COLUMN ORDER are read from the artifact, never
its cell values.

It is generic and declaration-driven. For a label declared with a
`source:` CSV, the renderer INVERTS the declared mapping: the key column
is the citizen name, each `properties:` entry reads its node property,
and each plain `relationships:` entry (a `column:` with no parser and no
foreign `source:`) reads back the citizen's edges of that type — matched
to the declaration's constant `props:` so a bright-gem column and a
dark-gem column that share an edge type stay distinct. Additional
`property_tables:` contribute more columns to the same citizens.

What the generic inverter cannot do is REPORTED, never silently skipped:

- A CSV no `source:` declaration consumes is the expected gap class
  (implicit labels whose citizens arrive by delta; the CSV is "rendered
  authority"). The report names it and proposes a minimal `source:`
  declaration shape — it does NOT touch the real ontology.
- A CSV consumed only through a parser or an edge-table `source:` (a
  lookup matrix, a reified-effects table) has no plain column<->edge map
  the inverter supports; the report names the declaration role it found.

The renderer never judges. It writes the draft; `python -m graph
roundtrip` grades it. A rendered table that reds under the judge is the
honest signal that canon does not carry that cell exactly (a boolean
column stores True, not the source token "Y"; an int column stores 2,
not the display token "+2"; a multi-value edge cell loses the source's
element order). Those reds are findings about what the graph holds, not
bugs in the renderer.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import comprehension
from .grammars import get_optional as grammar_for
from .ontology import (PropType, Reader, node_reader, read_csv_header,
                       rendered_views_of, source_files_of)
from .restore import read_export
from .roundtrip import table_ref_columns


@dataclass
class TableRender:
    """One {{csv:}} embed, rendered or reported as a gap."""
    relpath: str
    columns: "list | None" = None  # the embed's columns= filter, or None
    label: str = ""               # the source-mapped label, if one was found
    markdown: str = ""            # the rendered markdown table (empty on gap)
    gap: str = ""                 # why it could not be rendered (empty if it was)
    proposal: str = ""            # a PROPOSED declaration shape for a gap

    @property
    def rendered(self):
        return bool(self.markdown)


@dataclass
class ChapterRender:
    scope: str
    tables: list = field(default_factory=list)

    def draft(self):
        """A table-only draft: every rendered table in embed order. Gaps
        leave a visible marker so the draft's shape still tracks the
        chapter's embeds (the judge ignores non-table lines)."""
        blocks = [f"# Rendered tables — {self.scope}", ""]
        for table in self.tables:
            blocks.append(f"## {table.relpath}")
            blocks.append("")
            if table.rendered:
                blocks.append(table.markdown)
            else:
                blocks.append(f"<!-- MAPPING GAP: {table.gap} -->")
            blocks.append("")
        return "\n".join(blocks) + "\n"

    @property
    def gaps(self):
        return [t for t in self.tables if not t.rendered]


# -- declaration indexes ---------------------------------------------------


def source_label_index(ontology):
    """{csv relpath: label} for every label whose ground rows come from a
    csv_rows `source:` file — the labels the inverter can render."""
    index = {}
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict) or node_reader(spec) != Reader.CSV_ROWS:
            continue
        for relpath in source_files_of(spec):
            index[relpath] = label
    return index


def rendered_view_index(ontology):
    """{csv relpath: (label, rendered_view spec)} for implicit labels whose
    rendered authority is a CSV (Leg 2, the table-rendering tier). rendered_view is loader-inert
    — only render_tables and the judge's column typing read it."""
    index = {}
    for label, spec in ontology.nodes.items():
        for rview in rendered_views_of(spec):
            if rview.get("source"):
                index[rview["source"]] = (label, rview)
    return index


def parser_source_index(ontology):
    """{csv relpath: (label, rel)} for relationships whose OWN source is a
    matrix/lookup CSV (a `parser:` with a `source:`, e.g. a size-comparison
    matrix). Whole-table inverters (`<parser>.table`) render these; a
    parser with no table inverter falls through to the reported gap."""
    index = {}
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        for rel in spec.get("relationships") or []:
            if isinstance(rel, dict) and rel.get("parser") and rel.get("source"):
                index[rel["source"]] = (label, rel)
    return index


def property_table_index(ontology):
    """{csv relpath: (label, property_table spec)} for the secondary CSVs
    that contribute properties to an existing label's citizens."""
    index = {}
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        for table in spec.get("property_tables") or []:
            if isinstance(table, dict) and table.get("source"):
                index[table["source"]] = (label, table)
    return index


def declaration_role(ontology, relpath):
    """How (if at all) a CSV is referenced by any declaration other than a
    primary row-source — for the gap report. Returns a human sentence."""
    roles = []
    for name, spec in ontology.enums.items():
        if isinstance(spec, dict) and spec.get("source") == relpath:
            roles.append(f"the '{name}' enum's value source")
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        for index, rel in enumerate(spec.get("relationships") or []):
            if rel.get("source") == relpath:
                shape = rel.get("parser") or (
                    "edge table" if rel.get("from_column") else "relationship")
                roles.append(
                    f"the source of {label}.{rel.get('type')} "
                    f"(a {shape}, not a plain column)")
    if not roles:
        return ("no declaration consumes it — it is rendered authority for "
                "citizens that arrive by delta (the implicit-label gap class)")
    return "; ".join(roles)


# -- value + cell formatting ----------------------------------------------


def format_value(prop_spec, value, mapping=None):
    """A citizen property as a table cell string, or None to emit no cell.

    Faithful to what the graph HOLDS. A boolean stores no source token by
    default (Y / Yes / checkmark are all True), so a bare bool property
    emits no cell rather than inventing one. When the column mapping
    declares a `truthy:` token, THAT is the marker the table writes for a
    true value — the renderer emits it (and still nothing for false), so a
    boolean column renders and judges as the table has it (Fix 3)."""
    if value is None:
        return None
    ptype = (prop_spec or {}).get("type", PropType.TEXT)
    if ptype == PropType.BOOL:
        truthy = (mapping or {}).get("truthy")
        if truthy and value:
            return cell_text(truthy)
        return None
    if (mapping or {}).get("signed") and isinstance(value, int) and value > 0:
        # a signed column carries its favoring-side signal: +6, not 6
        # (owner ruling; three reviewers flagged the stripped sign)
        return cell_text(f"+{value}")
    return cell_text(value)


def display_cell(key, template, props):
    """The key/name cell rendered through a display template (Fix 2): the
    template's `{name}` is the key cell, and any `{prop}` is a citizen
    property, so a ladder named "Long" whose code is "L" renders "Long (L)"
    as the table writes it. A missing field leaves the plain key."""
    if not template:
        return key
    fields = {"name": key}
    fields.update({k: v for k, v in props.items() if v is not None})
    try:
        return template.format(**fields)
    except (KeyError, IndexError):
        return key


def cell_text(value):
    """One markdown cell: single line (a table row cannot span lines) with
    the delimiter escaped so a value never splits into phantom cells."""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def edge_columns(spec):
    """The plain relationships an embedded CSV's columns invert to: a
    `column:` with no parser, no foreign `source:`, and no `from_column:`
    (those read OTHER files, not this label's own source rows)."""
    columns = []
    for rel in spec.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        if rel.get("column") and not rel.get("parser") \
                and not rel.get("source") and not rel.get("from_column"):
            columns.append(rel)
    return columns


def _props_match(edge_props, wanted):
    """An edge belongs to a relationship declaration when it carries the
    declaration's constant props (bright-gem vs dark-gem columns share an
    edge type; the props disambiguate which column they came from)."""
    have = dict(edge_props)
    return all(have.get(key) == value for key, value in wanted.items())


def key_from_name(name, name_template):
    """Invert a name_template ("Level {key}") to recover the CSV key cell
    from a citizen name ("Level 1" -> "1"). No template, or a name that does
    not fit it: the citizen name IS the key cell."""
    if not name_template or "{key}" not in name_template:
        return name
    prefix, suffix = name_template.split("{key}", 1)
    if name.startswith(prefix) and name.endswith(suffix) \
            and len(name) >= len(prefix) + len(suffix):
        return name[len(prefix):len(name) - len(suffix)] or name
    return name


def _edge_targets(graph, label, name, rel):
    wanted = rel.get("props") or {}
    return sorted(
        edge.to_name for edge in graph.edges
        if edge.type == rel["type"]
        and edge.from_label == label and edge.from_name == name
        and _props_match(dict(edge.props), wanted))


def _members(graph, label, only_with=None, names=None):
    """The citizens of a label a view renders: all non-placeholder citizens,
    narrowed by an explicit `names:` subset (this doc shows only these) or an
    `only_with:` content filter (render only citizens carrying at least one
    of the named properties — the profile tables' membership: a citizen rides
    a profile table only if it has that profile). Both narrow; neither
    means all."""
    wanted = set(names) if names else None
    rows = []
    for (lbl, name), props in graph.nodes.items():
        if lbl != label or props.get("placeholder"):
            continue
        if wanted is not None and name not in wanted:
            continue
        if only_with and not any(props.get(p) is not None for p in only_with):
            continue
        rows.append(name)

    def natural(name):
        # rungs order numerically wherever a name embeds a number —
        # string sort put "Strength 10" before "Strength 3" and the
        # owner caught it in review; text segments still sort as text
        import re as _re
        return [int(seg) if seg.isdigit() else seg.lower()
                for seg in _re.split(r"(\d+)", str(name))]

    # an Ordered ladder declares its order as rank properties — a roster
    # whose every member carries one orders by it (the owner caught the
    # grade ladders rendering alphabetically)
    ranks = [graph.nodes[(label, name)].get("rank") for name in rows]
    if rows and all(isinstance(r, (int, float)) for r in ranks):
        return [name for _, name in sorted(zip(ranks, rows))]
    return sorted(rows, key=natural)


def _table_rows(graph, label, catalog, prop_specs, rels, name_template=None,
                parser_rels=(), display=None, only_with=None, names=None):
    """One body row per citizen: the key cell (a name_template inverts the
    citizen name back to its CSV key; an optional display template decorates
    it — Fix 2), then each property cell (faithful to what the graph holds; a
    bool column may declare a truthy token — Fix 3), then each edge-carried
    column as a set cell. A plain column that declares an `unmatched_property`
    carries BOTH its edge targets and that verbatim remainder in the one cell
    (Leg 3 — the mixed-content inversion). A `parser:` column is
    reconstructed by its grammar's registered per-cell inverter
    (`<parser>.cell`); a parser with no inverter renders nothing.
    `prop_specs` is a list of (prop_name, column_mapping)."""
    rows = []
    for name in _members(graph, label, only_with, names):
        props = graph.nodes[(label, name)]
        key = key_from_name(name, name_template)
        cells = [cell_text(display_cell(key, display, props))]
        for prop, mapping in prop_specs:
            cell = format_value(catalog.get(prop), props.get(prop), mapping)
            # empty cells hold their position (the column-declaration work): a named header is
            # only honest when every row's cells align under it
            cells.append(cell if cell is not None else "")
        for rel in rels:
            pieces = _edge_targets(graph, label, name, rel)
            remainder = props.get(rel.get("unmatched_property"))
            if remainder:
                pieces = pieces + [str(remainder)]
            cells.append(cell_text(", ".join(pieces)) if pieces else "")
        for rel in parser_rels:
            inverter = grammar_for(f"{rel['parser']}.cell")
            cell = inverter(graph, label, name, rel, props) \
                if inverter else None
            cells.append(cell_text(cell) if cell else "")
        rows.append(cells)
    return rows


def _prop_specs(mapping_dict):
    """[(prop, mapping)] from a properties: block, in declaration order."""
    return [(prop, mapping or {}) for prop, mapping in
            (mapping_dict or {}).items()]


def render_label_table(graph, ontology, label):
    """Invert a source-mapped label's declaration into a markdown table:
    one body row per citizen, cells rebuilt from properties and edges."""
    spec = ontology.nodes[label]
    catalog = spec.get("catalog") or {}
    prop_specs = _prop_specs(spec.get("properties"))
    for table in spec.get("property_tables") or []:
        prop_specs += _prop_specs(table.get("properties"))
    # a parser column with no registered inverter renders NOTHING — no
    # named-but-always-empty ghost column (owner ruling: "drop until we
    # need it"; the column returns the day its inverter is registered)
    parser_rels = [rel for rel in spec.get("relationships") or []
                   if isinstance(rel, dict) and rel.get("parser")
                   and grammar_for(f"{rel['parser']}.cell") is not None]
    rows = _table_rows(graph, label, catalog, prop_specs, edge_columns(spec),
                       parser_rels=parser_rels)
    return markdown_table(label, rows,
                          columns=_column_names(spec.get("key"), prop_specs,
                                                edge_columns(spec),
                                                parser_rels))


def _plain_rels(rels):
    return [rel for rel in rels or []
            if isinstance(rel, dict) and rel.get("column")
            and not rel.get("from_column")]


def _entry_rows(graph, ontology, entry):
    """Rows for one rendered_view contributor: a label with its own property
    and edge maps, membership filter, name_template and display template.
    The catalog (property types) is always the contributor label's real
    top-level schema."""
    label = entry["label"]
    catalog = (ontology.nodes.get(label) or {}).get("catalog") or {}
    return _table_rows(
        graph, label, catalog,
        _prop_specs(entry.get("properties")), _plain_rels(entry.get("relationships")),
        name_template=entry.get("name_template"),
        display=entry.get("display"),
        only_with=entry.get("only_with"),
        names=entry.get("names"))


def render_view_table(graph, ontology, label, view):
    """Invert a rendered_view mapping (Leg 2) into a markdown table. A
    single-label view reads its maps at the top level; a MULTI-LABEL view
    (Fix 5) merges the rows of every entry in its `labels:` list — one
    profile table's rows drawn from several catalogs plus a baseline
    contributor, each reading its own properties/edges into the shared
    columns. A `matrix:` view defers to a registered whole-table grammar
    inverter (`<matrix>.table`)."""
    matrix = view.get("matrix")
    if matrix:
        inverter = grammar_for(f"{matrix}.table")
        if inverter is not None:
            return inverter(graph, ontology, label, view)
        return ""
    if view.get("labels"):
        # shared columns: the first entry's declaration names the header;
        # every contributor's cells are remapped into that order BY COLUMN
        # NAME — appending in each entry's own declaration order slid a
        # a derived value under a distance column (owner-caught, the column-declaration work)
        first = view["labels"][0]
        shared = _column_names(
            view.get("key"), _prop_specs(first.get("properties")),
            _plain_rels(first.get("relationships")))
        rows = []
        for entry in view["labels"]:
            entry_cols = _column_names(
                view.get("key"), _prop_specs(entry.get("properties")),
                _plain_rels(entry.get("relationships")))
            for cells in _entry_rows(graph, ontology, entry):
                by_col = dict(zip(entry_cols, cells))
                remapped = [by_col.get(col, "") for col in shared]
                # the key cell always leads, whatever the key column is called
                if remapped and cells:
                    remapped[0] = cells[0]
                rows.append(remapped)
        return markdown_table(label, rows, columns=shared)
    catalog = ontology.nodes[label].get("catalog") or {}
    rows = _table_rows(graph, label, catalog,
                       _prop_specs(view.get("properties")),
                       _plain_rels(view.get("relationships")),
                       name_template=view.get("name_template"),
                       display=view.get("display"))
    return markdown_table(label, rows, columns=_column_names(
        view.get("key"), _prop_specs(view.get("properties")),
        _plain_rels(view.get("relationships"))))


def _column_names(key_name, prop_specs, rels, parser_rels=()):
    """The declared column names, in the same order _table_rows appends
    cells: the key column, then each property's `column:`, then each
    edge-carried `column:`, then parser columns (the column-declaration work — the declarations
    have always known these names; the header row now says them)."""
    names = [key_name] if key_name else []
    names += [(mapping or {}).get("column") or prop
              for prop, mapping in prop_specs]
    names += [rel.get("column") or rel.get("type", "") for rel in rels]
    names += [rel.get("column") or rel.get("parser", "")
              for rel in parser_rels]
    return names


def markdown_table(header_hint, rows, columns=None):
    """A markdown table wide enough for the widest row. The header line is
    structure the judge ignores; body rows carry the cells it grades.
    `columns` (when given) names the header cells from the declaration;
    placeholders fill only past the declared names."""
    width = max((len(r) for r in rows), default=1)
    named = [n for n in (columns or []) if n]
    if named:
        header = (named + [f"col{i}" for i in range(len(named), width)])[
            :max(width, len(named))]
    else:
        header = [header_hint] + [f"col{i}" for i in range(1, width)]
    width = max(width, len(header))
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    for row in rows:
        padded = row + [""] * (width - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


# -- gap proposal ----------------------------------------------------------


def propose_source_mapping(base_dir, relpath):
    """A minimal `source:` declaration shape for an unmapped CSV — the
    owner rules the real declaration at the gate. The CSV HEADER is
    read (structure, not data) to name the columns; no cell is read."""
    from .ontology import read_csv_header
    try:
        header = read_csv_header(base_dir / relpath)
    except OSError:
        header = []
    if not header:
        return f"# (could not read a header from {relpath})"
    key = header[0]
    lines = [
        "# PROPOSED (not applied) — a minimal row-source mapping:",
        "nodes:",
        "  <LabelName>:            # the owner names the label",
        f"    source: {relpath}",
        f"    key: {key!r}",
        "    concept: <Concept>",
        "    catalog:",
    ]
    for column in header[1:]:
        lines.append(f"      <prop>: {{ type: text, doc: {column!r} }}")
    if len(header) > 1:
        lines.append("    properties:")
        for column in header[1:]:
            lines.append(f"      <prop>: {{ column: {column!r} }}")
    lines.append("# Columns that are cross-references belong in "
                 "relationships: instead of properties:.")
    return "\n".join(lines)


# -- the chapter renderer --------------------------------------------------


def embeds_in(base_dir, scope):
    """The chapter's {{csv:}} embeds, in order — the judge's own view of
    them (via the reading room), so embed order and column filters match
    exactly what roundtrip grades. Returns [(relpath, columns_or_None)]."""
    data = (Path(base_dir) / scope).read_bytes()
    reading = comprehension.read_artifact(
        data, title=Path(scope).name, origin=str(scope))
    embeds = []
    for section in reading.sections:
        for span in section.get("spans", []):
            if span["class"] == comprehension.TABLE:
                embeds.append((span["table"],
                               table_ref_columns(span["text"])))
    return embeds


def render_chapter(base_dir, scope, graph, ontology):
    """Render every table a chapter embeds, in order — each a rendered
    table or a reported gap."""
    base_dir = Path(base_dir)
    sources = source_label_index(ontology)
    prop_tables = property_table_index(ontology)
    rendered_views = rendered_view_index(ontology)
    parser_sources = parser_source_index(ontology)
    chapter = ChapterRender(scope=scope)
    for relpath, columns in embeds_in(base_dir, scope):
        table = TableRender(relpath=relpath, columns=columns)
        matrix = None
        if relpath in parser_sources:
            label, rel = parser_sources[relpath]
            inverter = grammar_for(f"{rel['parser']}.table")
            if inverter is not None:
                try:
                    header = read_csv_header(base_dir / relpath)
                except OSError:
                    header = []
                matrix = inverter(graph, ontology, label, rel, header)
        if relpath in sources:
            table.label = sources[relpath]
            table.markdown = render_label_table(graph, ontology, table.label)
        elif relpath in rendered_views:
            label, view = rendered_views[relpath]
            table.label = label
            table.markdown = render_view_table(graph, ontology, label, view)
        elif matrix is not None:
            table.label = parser_sources[relpath][0]
            table.markdown = matrix
        elif relpath in prop_tables:
            label, _ = prop_tables[relpath]
            table.label = label
            table.markdown = render_label_table(graph, ontology, label)
        else:
            table.gap = declaration_role(ontology, relpath)
            table.proposal = propose_source_mapping(base_dir, relpath)
        chapter.tables.append(table)
    return chapter


def load_backup(base_dir):
    """The canon graph, DB-free: the committed backup (the same path
    test_golden and the round machinery read)."""
    return read_export(Path(base_dir) / "graph" / "export")
