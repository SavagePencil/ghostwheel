"""Canonize's durable pieces: the schema anchor's version stamp and
fingerprint, and the refusal record.

The graph is primary: canonize --apply lands the pinned changeset on the
graph, re-derives the machine layers, re-exports the backup, and chains
the event log (graph/__main__.py). What lives here is what apply stamps
and what a refused apply leaves behind — the (Archetype, "Ontology")
anchor's version (the event-log sequence) and content fingerprint, and
the coded refusal record beside the prose. The file-era planner that
once rendered a delta into source-file edits is gone with the files.
"""

import hashlib
import json
from pathlib import Path

from .refs import ONTOLOGY_ANCHOR

# Agent-authoring metadata consumed at review time, never domain data.
RECEIPT_PROPS = {"from_text", "source", "grade", "source_path"}


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
    from .report import record_header, write_record
    doc = record_header(base_dir, "canonize-refusal", branch)
    doc["refusals"] = [v.row(kb=doc["kb"], branch=branch)
                       for v in verdicts]
    write_record(base_dir, REFUSAL_REPORT_FILE, doc)


def clear_refusal_report(base_dir):
    """A clean run retires the artifact — the report reflects the
    latest outcome, never a stale one."""
    from .report import clear_record
    clear_record(base_dir, REFUSAL_REPORT_FILE)
