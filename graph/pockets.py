"""Pockets: a named branch cut as a clone of canon, declared in-band.

A collaborator's own version of a knowledge base is a branch born from
canon's whole graph rather than its schema stratum alone — hard-isolated
from live canon like every branch, with its own home, backup, chained
log, and pin. What makes it a POCKET is its declaration: who cut it,
when, who is invited to look, the base kind, and the canon identity and
sequence it forked from. The declaration lives in two in-band places
and no file: the branch database's identity stamp, and a bracketed
machinery citizen [Pocket] (kernel 0.16.0) named for the branch in the
branch's own graph, so the front door can ask "who cut this, who may
look" and the backup carries the answer.

The engine writes the row at the cut and rewrites it through the invite
verbs; nobody authors it by hand (the delta gate refuses that), it is
set aside from the line's content identity (an invite change re-exports
the backup without moving the chain), and succession strips it — canon
is never a pocket. Readability stays declarative here; making it
physical is a later rung.
"""

from datetime import datetime, timezone

from .extract import GraphData
from .ontology import DECLARATION_LABELS, KERNEL_POCKET_LABEL

SCHEMA_ONLY = "schema-only"
CLONE_OF_CANON = "clone-of-canon"
BASES = (SCHEMA_ONLY, CLONE_OF_CANON)
STAMP_PREFIX = "pocket_"
REPORT_FILE = "branches-report.json"


def declaration(by, invited, forked_from, forked_sequence, cut_at=None):
    """The pocket's facts, as the [Pocket] row carries them."""
    return {
        "cut_by": by,
        "cut_at": cut_at or datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "invited": sorted(set(invited or ())),
        "base": CLONE_OF_CANON,
        "forked_from": forked_from,
        "forked_sequence": forked_sequence,
    }


def clone_graph(graph):
    copy = GraphData()
    for (label, name), props in graph.nodes.items():
        copy.ensure_node(label, name, **dict(props))
    copy.edges = list(graph.edges)
    return copy


def with_declaration(graph, branch, facts):
    """A copy of the graph carrying the branch's [Pocket] row."""
    copy = clone_graph(graph)
    copy.ensure_node(KERNEL_POCKET_LABEL, branch, **dict(facts))
    return copy


def pocket_row(graph, branch):
    """The branch's declaration, or None for a branch that is no pocket."""
    return graph.nodes.get((KERNEL_POCKET_LABEL, branch))


def strip_declarations(graph):
    """A copy without any declaration row — what succession adopts."""
    copy = GraphData()
    for (label, name), props in graph.nodes.items():
        if label not in DECLARATION_LABELS:
            copy.ensure_node(label, name, **dict(props))
    copy.edges = [edge for edge in graph.edges
                  if edge.from_label not in DECLARATION_LABELS
                  and edge.to_label not in DECLARATION_LABELS]
    return copy


def stamp_facts(row):
    """The declaration as identity-stamp properties (pocket_ prefixed)."""
    return {STAMP_PREFIX + key: value for key, value in dict(row).items()}


# -- the listing: every branch of this knowledge base, from its backup ------


def branch_rows(base_dir):
    """One row per branch home under graph/branches — base kind, cut by,
    invited, sequence, adopted — read from the backups alone."""
    from .ontology import ARCHETYPE_LABEL
    from .proposal import branch_home, export_dir, read_branch_fork
    from .refs import ONTOLOGY_ANCHOR
    from .report import ref_key
    from .restore import read_export
    from .succession import read_adoption

    homes = branch_home(base_dir, "any").parent  # graph/branches/
    rows = []
    if not homes.is_dir():
        return rows
    for home in sorted(p for p in homes.iterdir() if p.is_dir()):
        branch = home.name
        row: dict = {"branch": branch}
        try:
            graph = read_export(export_dir(base_dir, branch))
        except (FileNotFoundError, ValueError, OSError) as exc:
            row.update(code="branch-unreadable", status="unreadable",
                       problem=(f"Attempted to read branch '{branch}''s "
                                f"backup. Failed due to: {exc}."))
            row["ref"] = ref_key(row["code"])
            rows.append(row)
            continue
        anchor = graph.nodes.get((ARCHETYPE_LABEL, ONTOLOGY_ANCHOR)) or {}
        version = anchor.get("version")
        row["sequence"] = (version if isinstance(version, int)
                           and not isinstance(version, bool) else 0)
        pocket = pocket_row(graph, branch)
        fork = read_branch_fork(base_dir, branch) or {}
        row["base"] = (pocket or {}).get("base") or fork.get("base") \
            or "unrecorded"
        row["pocket"] = dict(pocket) if pocket else None
        adoption = read_adoption(base_dir, branch)
        row["adopted"] = ({"by": adoption.get("adopted_by"),
                           "at": adoption.get("adopted_at")}
                          if isinstance(adoption, dict) else None)
        if row["adopted"]:
            row.update(status="adopted", code="branch-adopted")
        elif pocket:
            row.update(status="pocket", code="branch-pocket")
        else:
            row.update(status="line", code="branch-line")
        row["ref"] = ref_key(row["code"])
        rows.append(row)
    return rows


def branches_report(base_dir, rows):
    from .report import record_header
    doc = record_header(base_dir, "branches-report")
    doc["branches"] = rows
    return doc


def render_rows(rows):
    if not rows:
        return "No branches."
    lines = []
    for row in rows:
        head = f"{row['status']:<9} {row['branch']}"
        if row["status"] == "unreadable":
            lines.append(f"{head} — {row['problem']}")
            continue
        pocket = row.get("pocket")
        if pocket:
            invited = ", ".join(pocket.get("invited") or []) or "nobody yet"
            lines.append(f"{head} — cut by {pocket.get('cut_by')} "
                         f"({pocket.get('cut_at')}) from canon at sequence "
                         f"{pocket.get('forked_sequence')}; invited: "
                         f"{invited}; sequence {row['sequence']}")
        else:
            lines.append(f"{head} — {row['base']}; sequence "
                         f"{row['sequence']}")
        if row.get("adopted"):
            lines[-1] += (f"; adopted by {row['adopted']['by']} at "
                          f"{row['adopted']['at']}")
    return "\n".join(lines)
