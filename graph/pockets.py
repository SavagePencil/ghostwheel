"""Pockets: a named branch cut as a clone of canon, declared in-band.

A collaborator's own version of a knowledge base is a branch born from
canon's whole graph rather than its schema stratum alone — hard-isolated
from live canon like every branch, with its own home, backup, chained
log, and pin. What makes it a POCKET is its declaration: who cut it,
when, who is invited to look, the base kind, and the canon identity and
sequence it forked from. The declaration lives in two in-band places
and no file: the branch database's identity stamp, and a bracketed
machinery citizen [Pocket Universe] (kernel 0.16.0) named for the branch in the
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
    """The pocket's facts, as the [Pocket Universe] row carries them."""
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
    """A copy of the graph carrying the branch's [Pocket Universe] row."""
    copy = clone_graph(graph)
    copy.ensure_node(KERNEL_POCKET_LABEL, branch, **dict(facts))
    return copy


def pocket_row(graph, branch):
    """The branch's declaration, or None for a branch that is no pocket."""
    return graph.nodes.get((KERNEL_POCKET_LABEL, branch))


RETIRED_MARKER = "retired.json"


def retirement_marker_path(base_dir, branch):
    from .proposal import branch_home
    return branch_home(base_dir, branch) / RETIRED_MARKER


def read_retirement(base_dir, branch):
    """The line's retirement record, or None while it lives."""
    import json
    path = retirement_marker_path(base_dir, branch)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"retired_by": "unrecorded", "retired_at": "unrecorded"}


def retired_problem(base_dir, branch, attempted):
    """The refusal for working a retired line, or None. The record
    stands; deliberate rehydration (restore --from the archived export
    into an inspection database) is the road for walking history."""
    record = read_retirement(base_dir, branch)
    if record is None:
        return None
    return (f"Attempted to {attempted} on branch '{branch}'. Failed due "
            f"to: the line was retired by {record.get('retired_by')}'s "
            f"word on {record.get('retired_at')} — its record stands "
            f"whole at graph/branches/{branch}/, and a retired line "
            "takes no further rounds. To walk its history, rehydrate "
            "deliberately: restore --from "
            f"graph/branches/{branch}/export --database <inspection>.")


def retirement_problems(base_dir, branch, by):
    """Verify-all before anything: the refusals that keep retirement
    honest, collated. A line retires when the owner's word is recorded
    (--by) and every round it landed has crossed into canon (or it
    landed none); un-crossed work says merge first, and deliberate
    abandonment is a different act, unbuilt on purpose."""
    from .proposal import (branch_home, read_applied_log,
                          taken_up_rounds)
    problems = []
    if read_retirement(base_dir, branch) is not None:
        problems.append(f"Attempted to retire branch '{branch}'. Failed "
                        "due to: it is already retired; the record "
                        "stands.")
        return problems
    if not branch_home(base_dir, branch).is_dir():
        problems.append(f"Attempted to retire branch '{branch}'. Failed "
                        f"due to: no such line — nothing at "
                        f"graph/branches/{branch}/.")
        return problems
    if not (by or "").strip():
        problems.append(f"Attempted to retire branch '{branch}'. Failed "
                        "due to: retirement IS the owner's word, and "
                        "--by records it — name who ruled.")
    taken = taken_up_rounds(base_dir, None, branch)
    uncrossed = [(seq, delta_hash)
                 for seq, delta_hash, *_rest
                 in read_applied_log(base_dir, branch)
                 if delta_hash not in taken]
    for seq, delta_hash in uncrossed:
        problems.append(f"Attempted to retire branch '{branch}'. Failed "
                        f"due to: its round {seq} ({delta_hash[:12]}) "
                        "was never taken up by canon — merge first, so "
                        "no work is abandoned. (Deliberate abandonment "
                        "is a different act, and no verb performs it.)")
    return problems


def write_retirement(base_dir, branch, by):
    """The closed-by-the-owner's-word record, the adoption marker's
    sibling. Returns the record written."""
    import json
    from datetime import datetime, timezone
    from .proposal import read_applied_log
    record = {
        "retired_by": by,
        "retired_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "rounds_taken_up": [delta_hash for _seq, delta_hash, *_rest
                            in read_applied_log(base_dir, branch)],
    }
    path = retirement_marker_path(base_dir, branch)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return record


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
        retirement = read_retirement(base_dir, branch)
        row["retired"] = ({"by": retirement.get("retired_by"),
                           "at": retirement.get("retired_at")}
                          if retirement else None)
        if row["retired"]:
            row.update(status="retired", code="branch-retired")
        elif row["adopted"]:
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
                         f"{invited}; rounds landed {row['sequence']}")
        else:
            lines.append(f"{head} — {row['base']}; rounds landed "
                         f"{row['sequence']}")
        if row.get("adopted"):
            lines[-1] += (f"; adopted by {row['adopted']['by']} at "
                          f"{row['adopted']['at']}")
        if row.get("retired"):
            lines[-1] += (f"; retired by {row['retired']['by']} at "
                          f"{row['retired']['at']}")
    return "\n".join(lines)
