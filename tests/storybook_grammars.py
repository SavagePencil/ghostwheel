"""Corpus-two's grammar module: the storybook fixtures' own parse
strategies, registered through the engine's grammar registry exactly as
a consuming corpus would (the engine HOSTS grammars, it never contains
them — the registry ships empty). Only what the fixture corpora
declare: the size-comparison matrix parser, its table inverter, and the
requirements-cell inverter.
"""

from graph.grammars import register
from graph.parsers import parse_int


@register("size_matrix")
def size_matrix(raw_rows):
    """Parse a size-comparison matrix CSV.

    Layout: row 0 has 'Visitor: X' column headers; column 0 has '**Keeper: X**'
    row labels. Cells are signed modifiers ('+2') or 'N/A'.

    Returns (entries, bad_cells): entries is (visitor, keeper,
    modifier) with bare size codes; bad_cells is (row_label, col_label,
    cell_text) for cells that are neither a modifier nor N/A.
    """
    entries = []
    bad_cells = []
    if not raw_rows:
        return entries, bad_cells
    visitors = [h.strip().removeprefix("Visitor:").strip()
                 for h in raw_rows[0][1:]]
    for row in raw_rows[1:]:
        if not row or not row[0].strip():
            continue
        keeper = row[0].strip().strip("*").removeprefix("Keeper:").strip()
        for visitor, cell in zip(visitors, row[1:]):
            value, ok = parse_int(cell)
            if value is None:
                if not ok:
                    bad_cells.append((keeper, visitor, cell))
                continue
            entries.append((visitor, keeper, value))
    return entries, bad_cells


@register("size_matrix.table")
def size_matrix_table(graph, ontology, label, rel, header):
    """Rebuild the matrix CSV FROM the lifted edges — the round-trip
    inverse of the size_matrix parser. Only the CSV header is read (the
    visitor axis and its column order); keeper row labels are
    reconstructed, and every cell is a graph edge's modifier (or 'N/A'
    where the matrix holds no edge)."""
    codes = [h.strip().removeprefix("Visitor:").strip() for h in header[1:]
             if h and h.strip()]
    if not codes:
        return ""
    aliases = (ontology.nodes.get(label) or {}).get("aliases") or {}

    def citizen(code):
        return aliases.get(code, code)

    modifier = {}
    for edge in graph.edges:
        if edge.type == rel["type"] and edge.from_label == label:
            modifier[(edge.from_name, edge.to_name)] = \
                dict(edge.props).get("modifier")

    width = len(codes) + 1
    lines = ["| " + " | ".join([""] + [f"Visitor: {c}" for c in codes]) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    for keeper in codes:
        cells = [f"**Keeper: {keeper}**"]
        for visitor in codes:
            value = modifier.get((citizen(visitor), citizen(keeper)))
            cells.append("N/A" if value is None else f"{value:+d}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


@register("prerequisites.cell")
def prerequisites_cell(graph, label, name, rel, props):
    """Reconstruct a requirements cell FROM the structured edges: a
    staged edge renders '<target> at <stage> or higher', a bare edge
    renders 'Requires: <target>', and any clause the parser could not
    structure rides verbatim from the declared unmatched property."""
    clauses = []
    for edge in graph.edges:
        if edge.type != rel["type"] \
                or edge.from_label != label or edge.from_name != name:
            continue
        stage = dict(edge.props).get("min_stage")
        if stage:
            clauses.append(f"{edge.to_name} at {stage} or higher")
        else:
            clauses.append(f"Requires: {edge.to_name}")
    remainder = props.get(rel.get("unmatched_property"))
    if remainder:
        clauses.append(str(remainder))
    return ". ".join(clauses)


@register("prerequisites")
def prerequisites(cell):
    """Parse a requirements cell: '<Target> at <Stage> or higher'
    clauses become staged items, 'Needs: <Name>' clauses become named
    items, and anything else is unmatched (kept verbatim by the
    caller). Targets are generic — the rel spec, not the grammar,
    declares which labels they resolve against."""
    import re
    parsed, unmatched = [], []
    for clause in re.split(r"[.;]\s*", (cell or "").strip()):
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r"(?P<target>.+?) at (?P<stage>\w+) or higher$",
                         clause)
        if match:
            parsed.append({"kind": "staged",
                           "target": match.group("target"),
                           "stage": match.group("stage")})
            continue
        match = re.match(r"Needs: (?P<target>.+)$", clause)
        if match:
            parsed.append({"kind": "named",
                           "target": match.group("target")})
            continue
        unmatched.append(clause)
    return parsed, unmatched
