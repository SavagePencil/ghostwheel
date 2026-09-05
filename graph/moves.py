"""Declared moves — the migration charter's project side, as a round.

A world may rename one of its own labels or concepts, and may re-home
citizens under a kind of what they were. Both move data underneath a
schema row, which the schema ceremony refuses toward the charter; this
module is the charter's first project-side op, shipped the smallest
honest way: the round DECLARES its moves in moves.json beside the
stitch, the proposal embeds them so the approval hash covers them, the
diff gate itemizes each with its counts and refuses by name what cannot
move, and canonize --apply performs them — after the authored changeset
(spoken in the old names, as scratch was cut: a taxonomy declaration
for a renamed concept is authored under the OLD name and the rename
re-points it), before the stitch and re-derivation — through the same
transform kernel-migrate uses for the kernel's own renames. The
inverse is the full ground diff, so a relabel walks back; the
attribution ledger's refs move with the canon they name.

    {"rename": {"Old": "[New]"},
     "rehome": {"[Source]": {"[Kind]": ["citizen", ...]}}}

RENAME: one Archetype row and everything under it — citizens relabeled,
edges re-pointed, spec bindings rewritten. REHOME: the named citizens
leave one label for another that is a SUBTYPE_OF-descendant of it — a
kind of what they were, so no fact is lost and the fold keeps them
instances of the source. Kernel names never move here: a kernel rename
is a kernel ceremony.
"""

from .extract import GraphData, make_edge
from .ontology import ARCHETYPE_LABEL
from .refs import CitizenRef
from .report import CeremonyItem, Verdict

RENAME, REHOME = "rename", "rehome"


def normalize(doc, filename="moves.json"):
    """The declaration in canonical shape, or ValueError in the house
    form."""
    def fail(why):
        raise ValueError(f"Attempted to read the round's moves ({filename}). "
                         f"Failed due to: {why}")
    if not isinstance(doc, dict):
        fail(f"the file holds a {type(doc).__name__}, not an object with "
             "'rename' and/or 'rehome'")
    unknown = sorted(set(doc) - {RENAME, REHOME})
    if unknown:
        fail(f"unknown move kind(s) {', '.join(unknown)} — the kinds are "
             "'rename' (old name -> new name) and 'rehome' (source label -> "
             "{kind label -> [citizen names]})")
    out = {}
    renames = doc.get(RENAME) or {}
    if not isinstance(renames, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and k and v
            for k, v in renames.items()):
        fail("'rename' must map old names to new names (strings)")
    if renames:
        out[RENAME] = {k: renames[k] for k in sorted(renames)}
    rehomes = doc.get(REHOME) or {}
    if not isinstance(rehomes, dict):
        fail("'rehome' must map a source label to {kind label: [names]}")
    clean = {}
    for source, targets in rehomes.items():
        if not isinstance(targets, dict):
            fail(f"'rehome' under '{source}' must map a kind label to a "
                 "list of citizen names")
        clean[source] = {}
        for target, names in targets.items():
            if not isinstance(names, list) or not all(
                    isinstance(n, str) for n in names):
                fail(f"'rehome' {source} -> {target} must list citizen "
                     "names (strings)")
            clean[source][target] = sorted(set(names))
    if clean:
        out[REHOME] = {k: clean[k] for k in sorted(clean)}
    return out


def kernel_names(graph):
    return {edge.from_name for edge in graph.edges
            if edge.type == "DECLARED_IN" and edge.from_label == ARCHETYPE_LABEL
            and edge.to_label == ARCHETYPE_LABEL
            and edge.to_name == "Metaontology"} | {"Metaontology"}


def kinds_of(graph, label, extra_edges=()):
    """Every label that is a SUBTYPE_OF-descendant of `label` — over the
    graph's edges plus any the round itself declares."""
    kinds = set()
    edges = list(graph.edges) + list(extra_edges)
    grew = True
    while grew:
        grew = False
        for edge in edges:
            if edge.type == "SUBTYPE_OF" and edge.from_label == ARCHETYPE_LABEL \
                    and edge.to_label == ARCHETYPE_LABEL \
                    and (edge.to_name == label or edge.to_name in kinds) \
                    and edge.from_name not in kinds:
                kinds.add(edge.from_name)
                grew = True
    return kinds


def _holds(graph, name):
    return (ARCHETYPE_LABEL, name) in graph.nodes \
        or any(label == name for label, _ in graph.nodes)


def _rename_counts(graph, old):
    import json
    citizens = sum(1 for label, _ in graph.nodes if label == old)
    edges = sum(1 for e in graph.edges
                if e.from_label == old or e.to_label == old
                or (e.from_label == ARCHETYPE_LABEL and e.from_name == old)
                or (e.to_label == ARCHETYPE_LABEL and e.to_name == old))
    specs = 0
    for (label, _name), props in graph.nodes.items():
        if label == ARCHETYPE_LABEL and props.get("spec_json"):
            try:
                spec = json.loads(props["spec_json"])
            except ValueError:
                continue
            from .kernel_migrate import _rewrite_spec
            if _rewrite_spec(spec, {old: "\x00"}) != spec:
                specs += 1
    return citizens, edges, specs


def move_records(delta, base):
    """(ceremony items, refusals) for the round's declared moves,
    judged against the base — the graph the moves will act on after
    the authored changeset."""
    items, violations = [], []
    moves = delta.moves or {}
    if not moves:
        return items, violations
    if base is None:
        violations.append(Verdict(
            code="move-unverified",
            message=("Attempted to judge the round's declared moves. Failed "
                     "due to: no base graph — run the round through the "
                     "delta pipeline (python -m graph delta) so the moves "
                     "are checked against canon."),
            remedy="Run the round through the delta pipeline."))
        return items, violations
    kernel = kernel_names(base)
    born = {name for label, name, _ in delta.nodes_added
            if label == ARCHETYPE_LABEL}
    for old, new in (moves.get(RENAME) or {}).items():
        subject = CitizenRef(ARCHETYPE_LABEL, old)
        if old in kernel:
            violations.append(Verdict(
                code="move-kernel-name", subject=subject,
                message=(f"Attempted to rename '{old}' to '{new}'. Failed "
                         f"due to: '{old}' is a kernel name — the kernel "
                         "renames what it declares at a kernel ceremony, "
                         "never in a world's round. Drop the move."),
                remedy="Drop the move; a kernel rename is a kernel ceremony."))
            continue
        if not _holds(base, old) and old not in born:
            violations.append(Verdict(
                code="move-source-missing", subject=subject,
                message=(f"Attempted to rename '{old}' to '{new}'. Failed "
                         f"due to: nothing in this knowledge base is named "
                         f"'{old}' — no schema row, no citizens under it. "
                         "Fix the name or drop the move."),
                remedy="Fix the old name or drop the move."))
            continue
        if _holds(base, new) or new in born or new in kernel:
            violations.append(Verdict(
                code="move-target-held", subject=subject,
                message=(f"Attempted to rename '{old}' to '{new}'. Failed "
                         f"due to: '{new}' is already held — the two would "
                         "collapse into one. Pick another name, or retire "
                         "the holder first."),
                remedy="Pick another new name, or retire the holder first."))
            continue
        citizens, edges, specs = _rename_counts(base, old)
        items.append(CeremonyItem(
            code="project-renamed", subject=subject,
            message=(f"PROJECT RENAME — '{old}' becomes '{new}': the schema "
                     f"row renamed, {citizens} citizen"
                     f"{'s' if citizens != 1 else ''} relabeled, {edges} "
                     f"connection{'s' if edges != 1 else ''} re-pointed, "
                     f"{specs} spec binding{'s' if specs != 1 else ''} "
                     "rewritten; the attribution ledger follows at apply"),
            data={"old": old, "new": new, "citizens": citizens,
                  "edges": edges, "specs": specs}))
    renamed_to = dict(moves.get(RENAME) or {})
    for source, targets in (moves.get(REHOME) or {}).items():
        # a kind this round declares (its edge or its stitch) counts
        kinds = kinds_of(base, source,
                         list(delta.edges_added) + list(delta.stitch or []))
        # the source and kinds may themselves be renamed in this round:
        # a kind named after the rename is judged under its old name
        reverse = {new: old for old, new in renamed_to.items()}
        for target, names in targets.items():
            subject = CitizenRef(ARCHETYPE_LABEL, target)
            target_old = reverse.get(target, target)
            if target_old not in kinds and target not in kinds:
                violations.append(Verdict(
                    code="rehome-not-a-kind", subject=subject,
                    message=(f"Attempted to re-home {len(names)} citizen"
                             f"{'s' if len(names) != 1 else ''} from "
                             f"'{source}' to '{target}'. Failed due to: "
                             f"'{target}' is not a kind of '{source}' (no "
                             "SUBTYPE_OF chain joins them) — a re-homing "
                             "moves citizens under a kind of what they "
                             "were, so no fact is lost. Declare the kind "
                             "first (a taxonomy declaration may ride this "
                             "round's stitch), or drop the move."),
                    remedy="Declare the kind first, or drop the move."))
                continue
            missing = [n for n in names if (source, n) not in base.nodes]
            if missing:
                violations.append(Verdict(
                    code="rehome-citizen-missing", subject=subject,
                    message=(f"Attempted to re-home {len(names)} citizen"
                             f"{'s' if len(names) != 1 else ''} from "
                             f"'{source}' to '{target}'. Failed due to: "
                             f"{', '.join(repr(m) for m in missing[:5])}"
                             f"{', …' if len(missing) > 5 else ''} "
                             f"{'is' if len(missing) == 1 else 'are'} not "
                             f"under '{source}'. Fix the names."),
                    remedy="Fix the citizen names.",
                    data={"missing": missing}))
                continue
            items.append(CeremonyItem(
                code="citizens-rehomed", subject=subject,
                message=(f"RE-HOMED — {len(names)} citizen"
                         f"{'s' if len(names) != 1 else ''} of '{source}' "
                         f"become '{target}' (a kind of '{source}'); their "
                         "properties and connections travel with them, "
                         "and derivation keeps them instances of "
                         f"'{source}' through the taxonomy"),
                data={"source": source, "target": target, "count": len(names),
                      "citizens": names}))
    return items, violations


def apply_moves(ground, moves, kernel):
    """A copy of the ground with the round's moves performed: renames
    through the kernel's own transform (no adoption — a project rename
    keeps its spec), then re-homings. Returns (moved, problems)."""
    from .kernel_migrate import apply_renames
    moved = ground
    problems = []
    renames = moves.get(RENAME) or {}
    if renames:
        moved, _adoptions = apply_renames(moved, renames, "round",
                                          kernel_names=set(kernel))
    rehomes = moves.get(REHOME) or {}
    if rehomes:
        out = GraphData()
        relabel = {}
        for source, targets in rehomes.items():
            for target, names in targets.items():
                for name in names:
                    relabel[(source, name)] = target
        for (label, name), props in moved.nodes.items():
            new_label = relabel.get((label, str(name)), label)
            out.ensure_node(new_label, name, **dict(props))
        for edge in moved.edges:
            fl = relabel.get((edge.from_label, str(edge.from_name)),
                             edge.from_label)
            tl = relabel.get((edge.to_label, str(edge.to_name)), edge.to_label)
            out.edges.append(make_edge(edge.type, fl, edge.from_name, tl,
                                       edge.to_name, dict(edge.props)))
        for (source, name), target in relabel.items():
            if (target, name) not in out.nodes:
                problems.append(f"'{name}' was not under '{source}' to "
                                f"re-home into '{target}'")
        moved = out
    return moved, problems


def rewrite_ledger(base_dir, moves, branch=None):
    """The attribution ledger's refs follow the moves. Returns rows
    changed."""
    import json

    from .kernel_migrate import rewrite_attribution_labels
    from .proposal import attribution_log_path
    changed = rewrite_attribution_labels(base_dir, moves.get(RENAME) or {},
                                         branch)
    rehomes = moves.get(REHOME) or {}
    if not rehomes:
        return changed
    path = attribution_log_path(base_dir, branch)
    if not path.exists():
        return changed
    relabel = {(s, n): t for s, ts in rehomes.items()
               for t, names in ts.items() for n in names}
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        refs = [[relabel.get((r[0], str(r[1])), r[0]), r[1]]
                for r in (row.get("citizens") or [])]
        if refs != [list(r) for r in (row.get("citizens") or [])]:
            changed += 1
            row["citizens"] = refs
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed
