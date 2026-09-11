"""Merge — the fifth job: one line takes up another's rounds while both
persist.

A pocket (a clone-of-canon branch) and the canon it forked from each
land their own gated rounds. Merging reconciles them THREE-WAY at
citizen grain from the fork point: the source's rounds since the fork
are read from its archived proposals (code carries values), the
target's likewise. A citizen or connection touched by only one side is
DISJOINT and replays mechanically; one touched by both is CONTESTED and
is left at the target's version, listed base / yours / theirs for a
person to rule.

The merge prepares the target's ORDINARY round: the disjoint replay
lands in the target's fresh working copy through the same applier every
round rides, the contested list rides the round as merge.json, and
ruling is ordinary authoring in that copy — then delta, approve, and
canonize exactly as any round. At apply the target's log gains a
merged-from annotation naming the rounds taken up, so a second merge
skips them and succession's divergence advisory does not re-list rounds
that already rode across. Both directions are the same reconciliation
with the roles swapped: a pocket refreshing from canon, or canon landing
a pocket's work.
"""

from . import export as export_mod
from .delta import Delta
from .extract import GraphData
from .proposal import (apply_delta, parse_delta, proposals_dir,
                       read_applied_log, read_branch_fork, taken_up_rounds)
from .refs import CitizenRef, connection_ref

CANON = "canon"
REPORT_FILE = "merge-report.json"


def line_name(branch):
    return CANON if branch is None else branch


def resolve_line(name):
    """'canon' -> None (the default line); anything else is a branch."""
    return None if name == CANON else name


def describe(branch):
    return "canon" if branch is None else f"branch '{branch}'"


def _edge_identity(edge):
    return (edge.type, edge.from_label, str(edge.from_name),
            edge.to_label, str(edge.to_name))


def _node_key(label, name):
    return (label, str(name))


def touched(delta):
    """The subjects a changeset touches: node keys and edge identities."""
    nodes = {_node_key(l, n) for l, n, _ in delta.nodes_added}
    nodes |= {_node_key(l, n) for l, n, _ in delta.nodes_removed}
    nodes |= {_node_key(l, n) for l, n, _ in delta.nodes_changed}
    edges = {_edge_identity(e) for e in delta.edges_added}
    edges |= {_edge_identity(e) for e in delta.edges_removed}
    edges |= {_edge_identity(e) for e, _ in delta.edges_changed}
    edges |= {_edge_identity(e) for e in delta.stitch}
    return nodes, edges


def rounds_since(base_dir, branch, fork_sequence, taken=()):
    """The line's rounds that postdate the fork and were not already
    taken up: [(sequence, hash, delta-or-None)]. A branch's rounds all
    postdate its fork; canon's are those past the fork sequence. A round
    with no readable changeset (a derived-layer refresh, an adoption)
    carries None."""
    rows = []
    for seq, delta_hash, *_rest in read_applied_log(base_dir, branch):
        if branch is None and seq <= fork_sequence:
            continue
        if delta_hash in taken:
            continue
        path = proposals_dir(base_dir, branch) / delta_hash[:12] / "delta.json"
        try:
            delta = parse_delta(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            delta = None
        rows.append((seq, delta_hash, delta))
    return rows


def filtered(delta, contested_nodes, contested_edges):
    """The changeset with every operation on a contested subject dropped
    — what replays mechanically."""
    keep_node = lambda l, n: _node_key(l, n) not in contested_nodes
    keep_edge = lambda e: _edge_identity(e) not in contested_edges
    out = Delta()
    out.nodes_added = [(l, n, p) for l, n, p in delta.nodes_added
                       if keep_node(l, n)]
    out.nodes_removed = [(l, n, p) for l, n, p in delta.nodes_removed
                         if keep_node(l, n)]
    out.nodes_changed = [(l, n, c) for l, n, c in delta.nodes_changed
                         if keep_node(l, n)]
    out.edges_added = [e for e in delta.edges_added if keep_edge(e)]
    out.edges_removed = [e for e in delta.edges_removed if keep_edge(e)]
    out.edges_changed = [(e, c) for e, c in delta.edges_changed
                         if keep_edge(e)]
    out.stitch = [e for e in delta.stitch if keep_edge(e)]
    return out


def _clone(graph):
    copy = GraphData()
    for (label, name), props in graph.nodes.items():
        copy.ensure_node(label, name, **dict(props))
    copy.edges = list(graph.edges)
    return copy


def _base_image(rounds, key, is_edge=False):
    """What the fork-time state looked like for a subject, from the
    earliest before-image any round recorded: full for a removal, the
    changed properties for an edit, None for a subject born after the
    fork."""
    for _seq, _hash, delta in sorted(rounds, key=lambda r: r[0]):
        if delta is None:
            continue
        if is_edge:
            for edge in delta.edges_removed:
                if _edge_identity(edge) == key:
                    return {"props": dict(edge.props), "partial": False}
            for edge, changes in delta.edges_changed:
                if _edge_identity(edge) == key:
                    return {"props": {p: b for p, (b, _) in changes.items()},
                            "partial": True}
            for edge in delta.edges_added:
                if _edge_identity(edge) == key:
                    return None
            continue
        for label, name, before in delta.nodes_removed:
            if _node_key(label, name) == key:
                return {"props": dict(before), "partial": False}
        for label, name, changes in delta.nodes_changed:
            if _node_key(label, name) == key:
                return {"props": {p: b for p, (b, _) in changes.items()},
                        "partial": True}
        for label, name, _ in delta.nodes_added:
            if _node_key(label, name) == key:
                return None
    return None


def _current_node(graph, key):
    for (label, name), props in graph.nodes.items():
        if _node_key(label, name) == key:
            return dict(props)
    return None


def _current_edge(graph, key):
    for edge in graph.edges:
        if _edge_identity(edge) == key:
            return dict(edge.props)
    return None


def fork_point(base_dir, source, target, source_graph, target_graph):
    """(fork_sequence, pocket_branch, problem): merge runs between canon
    and a pocket, in either direction; the fork is the pocket's."""
    from .pockets import pocket_row
    if source is None and target is None:
        return None, None, ("Attempted to merge canon into canon. Failed "
                            "due to: a merge runs between canon and a "
                            "pocket — name a pocket on one side.")
    if source is not None and target is not None:
        return None, None, (
            f"Attempted to merge {describe(source)} into "
            f"{describe(target)}. Failed due to: a merge runs between "
            "canon and a pocket in either direction; two branches share "
            "no fork point. Merge each with canon.")
    pocket = source if source is not None else target
    graph = source_graph if source is not None else target_graph
    if pocket_row(graph, pocket) is None:
        return None, None, (
            f"Attempted to merge with {describe(pocket)}. Failed due to: "
            "that branch is a rebuild line, not a pocket (cut with --base "
            "schema-only), so it shares no ground with canon to reconcile "
            "— a rebuild line becomes canon by succession.")
    fork = read_branch_fork(base_dir, pocket)
    if not isinstance(fork, dict) or "canon_sequence" not in fork:
        return None, None, (
            f"Attempted to merge with {describe(pocket)}. Failed due to: "
            "no fork point is on record for it (it was cut before fork "
            "annotations existed). Re-cut the pocket to merge.")
    return int(fork["canon_sequence"]), pocket, None


def prepare(base_dir, source, target, source_graph, target_graph, copy):
    """Reconcile and replay: returns (merged copy, record, report rows)
    or (None, None, problems). `copy` is the target's fresh working
    copy — equal to the target's base — that the disjoint replay lands
    in; contested subjects keep the target's version."""
    fork, _pocket, problem = fork_point(base_dir, source, target,
                                        source_graph, target_graph)
    if problem:
        return None, None, [problem]
    taken = taken_up_rounds(base_dir, target, line_name(source))
    source_rounds = rounds_since(base_dir, source, fork, taken)
    target_rounds = rounds_since(base_dir, target, fork)
    src_nodes, src_edges = set(), set()
    for _s, _h, delta in source_rounds:
        if delta is not None:
            nodes, edges = touched(delta)
            src_nodes |= nodes
            src_edges |= edges
    tgt_nodes, tgt_edges = set(), set()
    for _s, _h, delta in target_rounds:
        if delta is not None:
            nodes, edges = touched(delta)
            tgt_nodes |= nodes
            tgt_edges |= edges
    contested_nodes = src_nodes & tgt_nodes
    contested_edges = src_edges & tgt_edges

    merged = _clone(copy)
    round_rows, replayed = [], {"nodes": 0, "edges": 0}
    unreplayable = []
    for seq, delta_hash, delta in source_rounds:
        row = {"sequence": seq, "id": delta_hash[:12]}
        if delta is None:
            row.update(code="merge-round-skipped",
                       note="no changeset on record (a derived-layer "
                            "refresh or an adoption) — nothing to take up")
            round_rows.append(row)
            continue
        part = filtered(delta, contested_nodes, contested_edges)
        problems = apply_delta(merged, part)
        move_count = 0
        if not problems and delta.moves:
            # a moves-only round is not an empty round: its renames and
            # re-homings ARE the round, performed here in sequence
            # exactly as canonize performed them on the source line
            # (moves are identity operations, never filtered by
            # contest — a contested citizen keeps the target's VALUES
            # while its identity still moves with the source's ruling)
            from .moves import CITIZEN_RENAME, REHOME, RENAME
            from .moves import apply_moves as apply_declared_moves
            from .moves import kernel_names as kernel_names_of
            merged, move_problems = apply_declared_moves(
                merged, delta.moves, kernel_names_of(merged))
            problems = list(move_problems)
            move_count = (
                len(delta.moves.get(RENAME) or {})
                + sum(len(pairs) for pairs in
                      (delta.moves.get(CITIZEN_RENAME) or {}).values())
                + sum(len(names) for targets in
                      (delta.moves.get(REHOME) or {}).values()
                      for names in targets.values()))
        if problems:
            row.update(code="merge-round-unreplayable", problems=problems)
            unreplayable.extend(f"round {seq} ({delta_hash[:12]}): {p}"
                                for p in problems)
        else:
            row.update(code="merge-round-replayed",
                       nodes=len(part.nodes_added) + len(part.nodes_changed)
                       + len(part.nodes_removed),
                       edges=len(part.edges_added) + len(part.edges_changed)
                       + len(part.edges_removed) + len(part.stitch),
                       moves=move_count)
            replayed["nodes"] += row["nodes"]
            replayed["edges"] += row["edges"]
            replayed["moves"] = replayed.get("moves", 0) + move_count
        round_rows.append(row)

    all_rounds = source_rounds + target_rounds
    contested = []
    for key in sorted(contested_nodes, key=str):
        label, name = key
        contested.append({
            "subject": CitizenRef(label, name).row(),
            "base": _base_image(all_rounds, key),
            "yours": _current_node(target_graph, key),
            "theirs": _current_node(source_graph, key),
            "code": "merge-contested"})
    for key in sorted(contested_edges, key=str):
        edge_type, fl, fn, tl, tn = key
        subject = {"kind": "connection", "type": edge_type,
                   "from": {"label": fl, "name": fn},
                   "to": {"label": tl, "name": tn}}
        contested.append({
            "subject": subject,
            "base": _base_image(all_rounds, key, is_edge=True),
            "yours": _current_edge(target_graph, key),
            "theirs": _current_edge(source_graph, key),
            "code": "merge-contested"})
    record = {
        "from": line_name(source), "into": line_name(target),
        "fork_sequence": fork,
        "rounds": [h for _s, h, d in source_rounds if d is not None],
        "round_rows": round_rows,
        "replayed": replayed,
        "contested": contested,
        "unreplayable": unreplayable,
        "already_taken_up": sorted(taken),
    }
    return merged, record, []


def merge_report(base_dir, record, target):
    from .report import record_header, ref_key
    doc = record_header(base_dir, "merge-report", target)
    doc.update(record)
    for row in doc["round_rows"]:
        row["ref"] = ref_key(row["code"])
    for row in doc["contested"]:
        row["ref"] = ref_key(row["code"])
    doc["nothing_to_take_up"] = not doc["rounds"]
    return doc


def contested_advisories(record):
    """The contested list as delta-gate advisories: the copy's version
    lands unless the author changed it — honesty while the owner is
    already looking."""
    from .report import ADVISORY, Verdict
    advisories = []
    for row in record.get("contested") or []:
        subject = row["subject"]
        if subject.get("kind") == "connection":
            ref = None
            who = (f"({subject['from']['label']}) {subject['from']['name']} "
                   f"-[:{subject['type']}]-> ({subject['to']['label']}) "
                   f"{subject['to']['name']}")
        else:
            ref = CitizenRef(subject["label"], subject["name"])
            who = f"({subject['label']}) '{subject['name']}'"
        advisories.append(Verdict(
            code="merge-contested", severity=ADVISORY, subject=ref,
            message=(f"{who} was changed on both lines since the fork "
                     f"(merge from {record.get('from')}) — this round "
                     "lands whatever the working copy holds for it; the "
                     "merge report shows base, yours, and theirs."),
            remedy="Rule it in the working copy before approving, or "
                   "approve the copy's version knowingly.",
            data={"from": record.get("from"),
                  "base": row.get("base"), "yours": row.get("yours"),
                  "theirs": row.get("theirs")}))
    return advisories


def render_report(doc):
    lines = [f"Merge from {doc['from']} into {doc['into']} — fork at canon "
             f"sequence {doc['fork_sequence']}."]
    if doc["nothing_to_take_up"]:
        lines.append("Nothing to take up: every round since the fork is "
                     "already on this line"
                     + (f" ({len(doc['already_taken_up'])} previously "
                        "merged)." if doc["already_taken_up"] else "."))
        return "\n".join(lines)
    for row in doc["round_rows"]:
        if row["code"] == "merge-round-replayed":
            lines.append(f"  taken up   round {row['sequence']} "
                         f"({row['id']}) — {row['nodes']} citizens, "
                         f"{row['edges']} connections replayed")
        elif row["code"] == "merge-round-skipped":
            lines.append(f"  skipped    round {row['sequence']} "
                         f"({row['id']}) — {row['note']}")
        else:
            lines.append(f"  could not  round {row['sequence']} "
                         f"({row['id']}) — " + "; ".join(row["problems"]))
    if doc["contested"]:
        lines.append(f"Contested ({len(doc['contested'])}) — changed on "
                     "both lines, left at this line's version; rule each "
                     "in the working copy:")
        for row in doc["contested"]:
            subject = row["subject"]
            if subject.get("kind") == "connection":
                who = (f"({subject['from']['label']}) "
                       f"{subject['from']['name']} -[:{subject['type']}]-> "
                       f"({subject['to']['label']}) {subject['to']['name']}")
            else:
                who = f"({subject['label']}) {subject['name']}"
            base = row["base"]
            base_text = ("born after the fork" if base is None else
                         f"{base['props']}"
                         + (" (changed properties only)" if base["partial"]
                            else ""))
            lines.append(f"  • {who}\n      base:   {base_text}\n"
                         f"      yours:  {row['yours']}\n"
                         f"      theirs: {row['theirs']}")
    else:
        lines.append("No contested citizens: everything replayed cleanly.")
    if doc["unreplayable"]:
        lines.append("Could not take up:\n  - " + "\n  - ".join(
            doc["unreplayable"]))
    lines.append("Next: rule any contested citizen in the working copy, "
                 "then python -m graph delta, approve, canonize --apply — "
                 "the round lands like any other, and this line's log "
                 "records the rounds taken up.")
    return "\n".join(lines)


def first_differences(a, b, limit=4):
    """The first few ways graph `a` differs from graph `b`, in
    designer-readable lines — what a refused landing shows instead of
    blaming the driver blind."""
    lines = []
    for key in sorted(set(a.nodes) | set(b.nodes), key=str):
        if len(lines) >= limit:
            return lines
        label, name = key
        mine, theirs = a.nodes.get(key), b.nodes.get(key)
        if mine is None:
            lines.append(f"({label}) '{name}' is missing from the copy")
        elif theirs is None:
            lines.append(f"({label}) '{name}' appears only in the copy")
        elif dict(mine) != dict(theirs):
            prop = next(p for p in sorted(set(mine) | set(theirs), key=str)
                        if mine.get(p) != theirs.get(p))
            lines.append(f"({label}) '{name}'.{prop} reads "
                         f"{mine.get(prop)!r}, the replay wrote "
                         f"{theirs.get(prop)!r}")
    a_edges = {_edge_identity(e) for e in a.edges}
    b_edges = {_edge_identity(e) for e in b.edges}
    for identity in sorted(a_edges ^ b_edges, key=str):
        if len(lines) >= limit:
            return lines
        edge_type, fl, fn, tl, tn = identity
        where = "missing from" if identity in b_edges else "only in"
        lines.append(f"({fl}) {fn} -[{edge_type}]-> ({tl}) {tn} is "
                     f"{where} the copy")
    return lines


def serialize_equal(a, b):
    return export_mod.serialize(a) == export_mod.serialize(b)
