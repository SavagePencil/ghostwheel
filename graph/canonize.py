"""Canonization: render an approved delta into source-file edits.

The derived-era applier (design: graph/design/agentic-etl.md, ruling on
the sources-are-canon decision): scratch work becomes canon exclusively as edits to the sources —
files stay canonical, git stays the event log, and a rebuild reproduces
the scratch state (the fixpoint: after apply + rebuild, the delta drains
to empty).

Renders are split by how deterministic the mapping is:
- DETERMINISTIC (written by --apply): CSV row appends via the label's
  inverted property mapping, multi-value cell appends for plain
  relationship columns, edge-table rows, overlay entries for
  catalog-only properties.
- REVIEW-REQUIRED (never auto-applied): unknown labels, unknown edge
  types, parser-backed relationships, prose/procedure-reader labels,
  values:-list labels — anything whose rendering is an ontology edit,
  because the ontology has an owner. Drafts are emitted for the
  owner to rule on.
- MANUAL: removals (additive-first culture; deletions are approver acts).

Receipt metadata (from_text/source/grade) is review evidence, not domain
data — it is reported and deliberately NOT rendered into sources.

FILE-ERA MODULE, retired from the CLI at the flip (the flip to graph-primacy and graph-native apply): canonize
--apply now applies deltas to the graph directly and never edits a
source file. This module remains while the bootstrap scaffolding lives
— its planner/applier still document (and test) the file era's
semantics.
"""

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ontology import Reader, node_reader
from .refs import ONTOLOGY_ANCHOR
from .parsers import EMPTY_MARKERS

# Agent-authoring metadata consumed at review time, never rendered.
RECEIPT_PROPS = {"from_text", "source", "grade", "source_path"}
JOINER = ", "


# -- schema-stratum identity + version auto-stamp (the schema inversion) ----------------------
# The graph's (Archetype, "Ontology") anchor is what a fresh connection
# interrogates for "what schema am I looking at?". Post-wiring (owner
# ruling, 2026-08-03) the project ontology's version IS the event-log
# sequence, and the anchor's fingerprint is the content hash of the
# ground schema stratum. So the version a connection reads moves with the
# GRAPH, not with a file — the hand-bumped-integer era ends. The stamp
# happens at apply, after the ground facts land and the machine layers
# re-derive, before anything is written.
# (the anchor's name itself is refs.py's constant, imported above)
# The anchor's own stamps are metadata about the schema, not part of its
# shape — excluded from the fingerprint so re-stamping is idempotent (the
# fingerprint never chases its own tail).
_SCHEMA_STAMP_PROPS = {"version", "fingerprint"}


def schema_fingerprint(graph):
    """sha256 over the serialized GROUND schema stratum: the Archetype
    citizens, the schema edges (DECLARED_IN, SUBTYPE_OF), and the
    schema-level stratified edges (a tower/ladder rooted AT an Archetype —
    a citizen's own INSTANCE_OF is its re-derived shadow, not schema).
    Deterministic: identical strata hash identically regardless of node
    or edge insertion order. The anchors' own version/fingerprint stamps
    are excluded so re-stamping is idempotent."""
    from .ontology import (ARCHETYPE_LABEL, SCHEMA_EDGE_TYPES,
                           SCHEMA_LABELS, STRATIFIED_EDGE_TYPES)
    lines = []
    for (label, name), props in graph.nodes.items():
        if label not in SCHEMA_LABELS:
            continue
        kept = {k: v for k, v in props.items()
                if k not in _SCHEMA_STAMP_PROPS}
        lines.append("N\t" + json.dumps([label, name, kept],
                                        sort_keys=True, ensure_ascii=False,
                                        default=str))
    for edge in graph.edges:
        is_schema = (edge.type in SCHEMA_EDGE_TYPES
                     or (edge.type in STRATIFIED_EDGE_TYPES
                         and edge.from_label == ARCHETYPE_LABEL))
        if not is_schema:
            continue
        lines.append("E\t" + json.dumps(
            [edge.type, edge.from_label, edge.from_name,
             edge.to_label, edge.to_name, dict(edge.props)],
            sort_keys=True, ensure_ascii=False, default=str))
    blob = "\n".join(sorted(lines))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def stamp_ontology_anchor(graph, version):
    """Stamp the (Archetype, 'Ontology') anchor IN PLACE with this round's
    version — the event-log sequence number — and re-stamp its fingerprint
    as the schema stratum's content hash. The optional free-text tag is
    left untouched (owner-set display metadata, the version-tag ruling). Every graph carries
    the anchor as ground schema, so its absence is a fault to surface, not
    swallow: returns [] on success, else a collated one-item problem list
    (verify-all-before-apply-any, apply_delta's doctrine)."""
    from .ontology import ARCHETYPE_LABEL
    node = graph.nodes.get((ARCHETYPE_LABEL, ONTOLOGY_ANCHOR))
    if node is None:
        return [f"Attempted to stamp the ({ARCHETYPE_LABEL}, "
                f"'{ONTOLOGY_ANCHOR}') version anchor. Failed due to: the "
                "graph carries no such anchor — every graph should carry "
                "one as ground schema; restore canon before applying."]
    node["version"] = version
    node["fingerprint"] = schema_fingerprint(graph)
    return []


@dataclass
class EditPlan:
    csv_appends: dict = field(default_factory=dict)   # relpath -> [row dict]
    cell_edits: list = field(default_factory=list)    # (relpath, key_col, key, col, old, new, where)
    # `where` narrows the row match beyond the key column (column -> expected
    # cell text) — needed when several rows share a key, as in edge tables.
    overlay_entries: dict = field(default_factory=dict)  # relpath -> {name: {prop: value}}
    review_required: list = field(default_factory=list)  # (title, draft text)
    manual_actions: list = field(default_factory=list)
    notices: list = field(default_factory=list)

    @property
    def deterministic_empty(self):
        return not (self.csv_appends or self.cell_edits
                    or self.overlay_entries)

    @property
    def blocked(self):
        return bool(self.review_required)


def render_value(value):
    """Graph property value -> CSV cell text (inverts convert())."""
    if value is True:
        return "Y"
    if value is False:
        return ""
    return str(value)


def read_rows(base_dir, relpath):
    with open(Path(base_dir) / relpath, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build_plan(delta, ontology, base_dir):
    """Classify every delta item into the EditPlan. Reads current source
    files so cell appends carry full before/after values (apply verifies
    the before-image — the derived era's precondition check)."""
    plan = EditPlan()
    _plan_added_nodes(delta, ontology, plan)
    _plan_changed_nodes(delta, ontology, plan)
    _plan_added_edges(delta, ontology, base_dir, plan)
    _plan_changed_edges(delta, ontology, plan)
    for label, name, props in delta.nodes_removed:
        held = ", ".join(f"{k}: {v!r}" for k, v in sorted(props.items())
                         if k not in RECEIPT_PROPS)
        plan.manual_actions.append(
            f"remove ({label}) '{name}'"
            + (f" — it held {held}" if held else "")
            + " — delete its source row/entry manually; removals are "
            "approver acts (the before-image above is the undo record)")
    for edge in delta.edges_removed:
        held = ", ".join(f"{k}: {v!r}" for k, v in edge.props
                         if k not in RECEIPT_PROPS)
        plan.manual_actions.append(
            f"remove ({edge.from_name})-[:{edge.type}]->({edge.to_name})"
            + (f" — it held {held}" if held else "")
            + " — edit the owning cell/row manually")
    return plan


def _split_props(label, props, spec, plan, name):
    """Partition a node's props: column-mapped, overlay-bound, receipts,
    unmappable (review)."""
    columns = {}
    overlay = {}
    catalog = spec.get("catalog") or {}
    mapping = {prop: (m or {}).get("column")
               for prop, m in (spec.get("properties") or {}).items()}
    for prop, value in sorted(props.items()):
        if prop in RECEIPT_PROPS:
            plan.notices.append(
                f"({label}) '{name}': receipt metadata '{prop}' kept for "
                "review, not rendered to sources")
            continue
        if prop in mapping and mapping[prop]:
            columns[mapping[prop]] = render_value(value)
        elif prop in catalog:
            if spec.get("overlay"):
                overlay[prop] = value
            else:
                plan.review_required.append((
                    f"({label}) '{name}' property '{prop}'",
                    f"catalog property '{prop}' has no column and the label "
                    f"declares no overlay: — add `overlay: "
                    f"data/overlays/{label.lower()}.yaml` to the ontology "
                    "(owner ruling) or map a column"))
        else:
            plan.review_required.append((
                f"({label}) '{name}' property '{prop}'",
                f"'{prop}' is not in the {label} catalog — catalog "
                "additions are owner-governed; draft: add "
                f"`{prop}: {{ type: text, doc: \"...\" }}`"))
    return columns, overlay


def _plan_added_nodes(delta, ontology, plan):
    for label, name, props in delta.nodes_added:
        spec = ontology.nodes.get(label)
        if spec is None:
            prop_lines = "".join(f"\n#       {p}: {{ type: text, doc: \"...\" }}"
                                 for p in sorted(set(props) - RECEIPT_PROPS))
            plan.review_required.append((
                f"unknown label ({label}) '{name}'",
                f"no ontology entry for label '{label}' — a NEW LABEL is a "
                "plan-gate decision (naming, concept binding, facets). "
                "Draft:\n"
                f"#   {label}:\n"
                f"#     source: data/<owner-names-this>.csv\n"
                f"#     key: <key column>\n"
                f"#     concept: Gameplay Concept\n"
                f"#     catalog:{prop_lines or ' {}'}\n"
                f"#   first row: {name}"))
            continue
        reader = node_reader(spec)
        if spec.get("values") is not None:
            plan.review_required.append((
                f"values:-list label ({label}) '{name}'",
                f"'{label}' is an inline values: list — adding '{name}' is "
                "an ontology.yaml edit (owner-governed)"))
            continue
        if spec.get("implicit"):
            if set(props) - RECEIPT_PROPS:
                plan.review_required.append((
                    f"implicit label ({label}) '{name}' with properties",
                    "implicit nodes materialize from referencing cells and "
                    "carry no authored properties — give the label a source "
                    "or an overlay (owner ruling)"))
            else:
                plan.notices.append(
                    f"({label}) '{name}' is implicit — it will exist in the "
                    "rebuild only once a rendered edge references it")
            continue
        if reader != Reader.CSV_ROWS:
            plan.review_required.append((
                f"({label}) '{name}'",
                f"label '{label}' is {reader}-sourced — prose/procedure "
                "files are authored directly, not rendered from deltas "
                "(v0 scope)"))
            continue
        columns, overlay = _split_props(label, props, spec, plan, name)
        row = {spec["key"]: str(name), **columns}
        plan.csv_appends.setdefault(spec["source"], []).append(row)
        if overlay:
            plan.overlay_entries.setdefault(
                spec["overlay"], {}).setdefault(str(name), {}).update(overlay)


def _plan_changed_nodes(delta, ontology, plan):
    for label, name, changes in delta.nodes_changed:
        spec = ontology.nodes.get(label)
        if spec is None or node_reader(spec) != Reader.CSV_ROWS:
            plan.review_required.append((
                f"changed ({label}) '{name}'",
                "property changes on non-CSV labels are manual in v0"))
            continue
        mapping = {prop: (m or {}).get("column")
                   for prop, m in (spec.get("properties") or {}).items()}
        # property-table props render as cell edits in THEIR source file
        table_homes = {}
        for table in spec.get("property_tables") or []:
            for prop, m in (table.get("properties") or {}).items():
                table_homes[prop] = (table["source"], table["key"],
                                     (m or {}).get("column"))
        catalog = spec.get("catalog") or {}
        for prop, (before, after) in sorted(changes.items()):
            if prop in RECEIPT_PROPS:
                plan.notices.append(
                    f"({label}) '{name}': receipt metadata '{prop}' change "
                    "kept for review, not rendered")
            elif prop in mapping and mapping[prop]:
                plan.cell_edits.append((
                    spec["source"], spec["key"], str(name), mapping[prop],
                    render_value(before) if before is not None else "",
                    render_value(after) if after is not None else "", {}))
            elif prop in table_homes:
                source, key_col, column = table_homes[prop]
                plan.cell_edits.append((
                    source, key_col, str(name), column,
                    render_value(before) if before is not None else "",
                    render_value(after) if after is not None else "", {}))
            elif prop in catalog and spec.get("overlay"):
                plan.overlay_entries.setdefault(
                    spec["overlay"], {}).setdefault(str(name), {})[prop] = after
            else:
                plan.review_required.append((
                    f"changed ({label}) '{name}' property '{prop}'",
                    "no column mapping or overlay for this property — "
                    "owner ruling needed"))


def _match_rel_spec(ontology, edge):
    """Find the from-label relationship spec this edge renders through.
    Constant `props:` stamps discriminate between same-type specs."""
    spec = ontology.nodes.get(edge.from_label) or {}
    edge_props = dict(edge.props)
    grounded = {k: v for k, v in edge_props.items() if k not in RECEIPT_PROPS}
    candidates = []
    for rel in spec.get("relationships") or []:
        if rel.get("type") != edge.type:
            continue
        target_ok = rel.get("to") in (edge.to_label, "any")
        if not target_ok:
            continue
        constants = rel.get("props") or {}
        prop_cols = rel.get("prop_columns") or {}
        leftover = {k: v for k, v in grounded.items() if k not in constants
                    and k not in prop_cols}
        if all(grounded.get(k) == v for k, v in constants.items()) \
                and not (leftover and not rel.get("from_column")):
            candidates.append((rel, leftover))
    return candidates[0] if candidates else (None, None)


def _plan_added_edges(delta, ontology, base_dir, plan):
    # Plain multi-value cell appends coalesce per (file, row, column): two
    # edges landing in the same cell must become ONE edit building on ONE
    # before-image, or the second write silently discards the first.
    pending = {}  # (source, key_col, key, column) -> {"current": str, "parts": [..]}
    for edge in delta.edges_added:
        rel, leftover = _match_rel_spec(ontology, edge)
        if rel is None:
            plan.review_required.append((
                f"unknown edge ({edge.from_name})-[:{edge.type}]->"
                f"({edge.to_name})",
                f"no relationship spec of type {edge.type} on label "
                f"'{edge.from_label}' targeting '{edge.to_label}' — a new "
                "edge type is an ontology decision. Draft:\n"
                f"#   - {{ type: {edge.type}, to: {edge.to_label}, "
                "column: \"<the owner names the column>\" }"))
            continue
        if rel.get("parser"):
            plan.review_required.append((
                f"parser-backed edge ({edge.from_name})-[:{edge.type}]->"
                f"({edge.to_name})",
                f"relationship uses the {rel['parser']} parser — its source "
                "format needs hand-editing (v0 scope)"))
            continue
        cell_value = (f"{edge.to_label}: {edge.to_name}"
                      if rel.get("to") == "any" else str(edge.to_name))
        if rel.get("from_column"):
            grounded = {k: v for k, v in dict(edge.props).items()
                        if k not in RECEIPT_PROPS}
            row = {rel["from_column"]: str(edge.from_name),
                   rel["column"]: cell_value}
            for prop, column in (rel.get("prop_columns") or {}).items():
                if prop in grounded:
                    row[column] = render_value(grounded[prop])
            plan.csv_appends.setdefault(rel["source"], []).append(row)
            continue
        # plain multi-value cell append on the label's own source
        spec = ontology.nodes.get(edge.from_label)
        source, key_col = spec["source"], spec["key"]
        cell = (source, key_col, str(edge.from_name), rel["column"])
        if cell not in pending:
            current = ""
            for row in read_rows(base_dir, source):
                if (row.get(key_col) or "").strip() == str(edge.from_name):
                    current = (row.get(rel["column"]) or "").strip()
                    break
            parts = [] if current in EMPTY_MARKERS else [
                p.strip() for p in current.split(",") if p.strip()]
            pending[cell] = {"current": current, "parts": parts,
                             "dirty": False}
        if cell_value in pending[cell]["parts"]:
            plan.notices.append(
                f"({edge.from_name})-[:{edge.type}]->({edge.to_name}) "
                "already present in the source cell — nothing to render")
            continue
        pending[cell]["parts"].append(cell_value)
        pending[cell]["dirty"] = True
    for (source, key_col, key, column), state in pending.items():
        if not state["dirty"]:
            continue  # every candidate was already present
        plan.cell_edits.append((source, key_col, key, column,
                                state["current"], JOINER.join(state["parts"]),
                                {}))


def _plan_changed_edges(delta, ontology, plan):
    """A property correction on an existing connection renders as cell
    edits in the edge table that owns it — one edit per changed property,
    each carrying its before-image, the row pinned by key AND target so
    parallel rows are never mistaken for each other."""
    for edge, changes in delta.edges_changed:
        rel, _ = _match_rel_spec(ontology, edge)
        if rel is None:
            plan.review_required.append((
                f"changed edge ({edge.from_name})-[:{edge.type}]->"
                f"({edge.to_name})",
                f"no relationship spec of type {edge.type} on label "
                f"'{edge.from_label}' targeting '{edge.to_label}' — a new "
                "edge type is an ontology decision"))
            continue
        if rel.get("parser") or not rel.get("from_column"):
            plan.review_required.append((
                f"changed edge ({edge.from_name})-[:{edge.type}]->"
                f"({edge.to_name})",
                "this connection's properties don't render from deltas — "
                "its source format needs hand-editing (v0 scope)"))
            continue
        prop_cols = rel.get("prop_columns") or {}
        cell_value = (f"{edge.to_label}: {edge.to_name}"
                      if rel.get("to") == "any" else str(edge.to_name))
        where = {rel["column"]: cell_value}
        for prop, (before, after) in sorted(changes.items()):
            if prop in RECEIPT_PROPS:
                plan.notices.append(
                    f"({edge.from_label}) '{edge.from_name}': receipt "
                    f"metadata '{prop}' change kept for review, not "
                    "rendered")
                continue
            if prop not in prop_cols:
                plan.review_required.append((
                    f"changed edge ({edge.from_name})-[:{edge.type}]->"
                    f"({edge.to_name}) property '{prop}'",
                    f"'{prop}' has no column mapping on this relationship "
                    "— owner ruling needed"))
                continue
            plan.cell_edits.append((
                rel["source"], rel["from_column"], str(edge.from_name),
                prop_cols[prop],
                render_value(before) if before is not None else "",
                render_value(after) if after is not None else "", where))


def _find_row(rows, key_col, key, where):
    """The row a cell edit targets: key column matches, and every `where`
    constraint (column -> expected text) matches — the pin that keeps
    parallel rows (edge tables) from being mistaken for each other."""
    for row in rows:
        if (row.get(key_col) or "").strip() != key:
            continue
        if all((row.get(col) or "").strip() == str(val).strip()
               for col, val in where.items()):
            return row
    return None


def apply_plan(plan, base_dir):
    """Write the deterministic edits — two-phase per the error doctrine:
    VERIFY every precondition first (collating every problem into one
    report), then write. No partial writes on failure."""
    base_dir = Path(base_dir)
    problems = []

    # --- verify phase: read everything, check every precondition ---------
    csv_files = {}
    for relpath in sorted(set(list(plan.csv_appends)
                              + [e[0] for e in plan.cell_edits])):
        path = base_dir / relpath
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                csv_files[relpath] = ((reader.fieldnames or []), list(reader))
        except OSError as exc:
            problems.append(
                f"Attempted to open {relpath} to apply edits. Failed due "
                f"to: {exc}.")
    for relpath, appends in sorted(plan.csv_appends.items()):
        if relpath not in csv_files:
            continue
        header, _ = csv_files[relpath]
        for row in appends:
            unknown = sorted(set(row) - set(header))
            if unknown:
                problems.append(
                    f"Attempted to append a row to {relpath} (columns "
                    f"{unknown}). Failed due to: those columns are not in "
                    "the file's header — the ontology mapping and the CSV "
                    "disagree; fix the mapping or the file first.")
    seen_cells = {}
    for relpath, key_col, key, column, old_val, new_val, where in \
            plan.cell_edits:
        cell = (relpath, key_col, key, column, tuple(sorted(where.items())))
        if cell in seen_cells:
            problems.append(
                f"Attempted to edit the '{column}' cell of row '{key}' in "
                f"{relpath} twice in one plan (to '{seen_cells[cell]}' and "
                f"to '{new_val}'). Failed due to: the second edit would "
                "silently discard the first — the plan builder must "
                "coalesce edits to a shared cell; rebuild the plan "
                "(python -m graph canonize).")
            continue
        seen_cells[cell] = new_val
        if relpath not in csv_files:
            continue
        header, rows = csv_files[relpath]
        match = _find_row(rows, key_col, key, where)
        if match is None:
            # a row this same plan is appending is a valid target — its
            # cells start empty (the write phase appends before editing)
            pending = any((row.get(key_col) or "").strip() == key
                          for row in plan.csv_appends.get(relpath, []))
            if pending and not old_val.strip():
                continue
            problems.append(
                f"Attempted to edit the '{column}' cell of row '{key}' in "
                f"{relpath}. Failed due to: no row with {key_col} = "
                f"'{key}' exists — the file changed since the plan was "
                "built; rebuild the plan (python -m graph canonize).")
        elif (match.get(column) or "").strip() != old_val.strip():
            current = (match.get(column) or "").strip()
            problems.append(
                f"Attempted to edit the '{column}' cell of row '{key}' in "
                f"{relpath} (expected it to read '{old_val}'). Failed due "
                f"to: the cell now reads '{current}' — the file moved "
                "under the plan; rebuild the plan (python -m graph "
                "canonize) so you are approving current reality.")
    if problems:
        raise RuntimeError(
            "nothing was written — every problem collated below:\n  - "
            + "\n  - ".join(problems))

    # --- write phase: all preconditions held ------------------------------
    changed = []
    for relpath, appends in sorted(plan.csv_appends.items()):
        header, rows = csv_files[relpath]
        for row in appends:
            rows.append({col: row.get(col, "") for col in header})
        changed.append(relpath)
    for relpath, key_col, key, column, _, new_val, where in plan.cell_edits:
        _, rows = csv_files[relpath]
        match = _find_row(rows, key_col, key, where)
        if match is not None:
            match[column] = new_val
        changed.append(relpath)
    for relpath in sorted(set(changed)):
        header, rows = csv_files[relpath]
        with open(base_dir / relpath, "w", newline="",
                  encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
    for relpath, entries in sorted(plan.overlay_entries.items()):
        path = base_dir / relpath
        data = {}
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, props in entries.items():
            data.setdefault(name, {}).update(props)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=True,
                                       allow_unicode=True),
                        encoding="utf-8")
        changed.append(relpath)
    return sorted(set(changed))


# -- canonize refusals as durable records ---------------------------------
#
# Every refusal class prints its collated stderr block exactly as it
# always has — and additionally leaves an inspectable artifact: the
# same facts as Verdict records rendered to canonize-refusal.json in
# graph/reports/. The file is a rendering of the LATEST canonize
# outcome, so a run that ends cleanly removes it.

REFUSAL_REPORT_FILE = "canonize-refusal.json"


def refusal_report_path(base_dir):
    from pathlib import Path
    return Path(base_dir) / "graph" / "reports" / REFUSAL_REPORT_FILE


def write_refusal_report(base_dir, branch, verdicts):
    """The refusal record beside the round: kind, the line of truth it
    was refused on (kb + branch, per the reference rules), and one row
    per verdict. Best-effort — a report that cannot be written must
    never mask the refusal it describes."""
    from .refs import kb_name_from_export
    doc = {"kind": "canonize-refusal",
           "kb": kb_name_from_export(base_dir)}
    if branch:
        doc["branch"] = branch
    doc["refusals"] = [v.row(kb=doc["kb"], branch=branch)
                       for v in verdicts]
    try:
        path = refusal_report_path(base_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n",
                        encoding="utf-8")
    except OSError:
        pass


def clear_refusal_report(base_dir):
    """A clean run retires the artifact — the report reflects the
    latest outcome, never a stale one."""
    try:
        refusal_report_path(base_dir).unlink(missing_ok=True)
    except OSError:
        pass
