"""Kernel migration: the ceremony's other limb.

A canon's committed backup embeds the kernel schema stratum — the
citizens the metaontology declares, their schema edges, and the
Metaontology anchor carrying the kernel's version and content
fingerprint. When the installed engine's kernel moves, that embedded
stratum does not move with it: ``rederive`` reconstructs the schema
FROM the graph, so it faithfully rebuilds against the stale kernel and
is structurally incapable of noticing the skew.

This module is the kernel-side sibling of rederive. It recomputes the
kernel stratum from the installed metaontology and splices it over
canon's — the project stratum and the ground untouched — refusing when
a removed kernel name would orphan project references. The CLI applies
the splice as a first-class round: a real delta, archived with its
inverse, chained in the event log, so history stays replayable and
invertible with no hole at the migration.

The skew finding lives here too: ``kernel_skew`` interrogates a
canon's Metaontology anchor against the installed kernel, the check a
consuming knowledge base runs before trusting its backup. Mutating
commands refuse on skew (building more canon on a stale kernel deepens
it); read commands warn and proceed.
"""

import hashlib
from pathlib import Path

from .extract import GraphData
from .ontology import ARCHETYPE_LABEL, METAONTOLOGY_PATH

KERNEL_ANCHOR = "Metaontology"
MIGRATE_COMMAND = "python -m graph kernel-migrate"


def kernel_stratum(graph):
    """The kernel-declared subset of a graph: citizens DECLARED_IN the
    Metaontology layer plus the Metaontology anchor itself, and every
    edge LEAVING one of them. Returns ({name: props}, {outbound edges}).
    References flow project -> kernel, so inbound edges belong to the
    project stratum and are not part of the kernel's identity."""
    kernel = {edge.from_name for edge in graph.edges
              if edge.type == "DECLARED_IN"
              and edge.from_label == ARCHETYPE_LABEL
              and edge.to_label == ARCHETYPE_LABEL
              and edge.to_name == KERNEL_ANCHOR}
    kernel.add(KERNEL_ANCHOR)
    nodes = {name: dict(props)
             for (label, name), props in graph.nodes.items()
             if label == ARCHETYPE_LABEL and name in kernel}
    edges = {edge for edge in graph.edges
             if edge.from_label == ARCHETYPE_LABEL
             and edge.from_name in kernel}
    return nodes, edges


def fresh_kernel(base_dir, metaontology_path=None):
    """The kernel stratum the installed engine would seed today.
    Returns (schema graph | None, findings) — None only when the
    metaontology itself is unreadable (the findings say why)."""
    from .extract import Extractor, schema_only
    from .ontology import kernel_ontology
    ontology, findings = kernel_ontology(base_dir, metaontology_path)
    if ontology is None:
        return None, findings
    extractor = Extractor(ontology)
    extractor.build_metamodel()
    return schema_only(extractor.graph), findings


def installed_kernel_identity(metaontology_path=None):
    """(version, fingerprint) of the installed metaontology file."""
    from .ontology import load_metaontology
    path = Path(metaontology_path or METAONTOLOGY_PATH)
    _kernel, meta, _findings = load_metaontology(path)
    try:
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        fingerprint = None
    return meta.get("version"), fingerprint


def kernel_skew(base, metaontology_path=None):
    """Interrogate a canon's Metaontology anchor against the installed
    kernel. Returns None when they match, else a designer-facing
    message naming both sides and the remedy."""
    version, fingerprint = installed_kernel_identity(metaontology_path)
    anchor = base.nodes.get((ARCHETYPE_LABEL, KERNEL_ANCHOR))
    if anchor is None:
        return ("This canon carries no Metaontology anchor, so the "
                "kernel it was built with cannot be verified against "
                f"the installed engine (kernel {version}). Run "
                f"{MIGRATE_COMMAND} to migrate the canon.")
    canon_version = anchor.get("version")
    canon_fingerprint = anchor.get("fingerprint")
    if canon_version == version and canon_fingerprint == fingerprint:
        return None
    if canon_version == version:
        return ("This canon was built with kernel "
                f"{canon_version}, and the installed engine names the "
                "same version — but their content fingerprints differ, "
                "which means the kernel changed without its version "
                f"moving (a broken kernel ceremony). Run "
                f"{MIGRATE_COMMAND} to migrate the canon, and give the "
                "kernel change its missing version bump.")
    return (f"This canon was built with kernel {canon_version}; the "
            f"installed engine carries kernel {version}. Run "
            f"{MIGRATE_COMMAND} to migrate the canon.")


def orphaned_references(ground, removed_names, old_names):
    """Ground edges that would dangle if the removed kernel names left:
    anything pointing AT a removed name from outside the old kernel
    stratum (edges leaving the old stratum leave with it). Sorted, so
    the refusal reads stably."""
    orphans = [edge for edge in ground.edges
               if edge.to_label == ARCHETYPE_LABEL
               and edge.to_name in removed_names
               and not (edge.from_label == ARCHETYPE_LABEL
                        and edge.from_name in old_names)]
    return sorted(orphans, key=lambda e: (e.from_label, str(e.from_name),
                                          e.type, str(e.to_name)))


def splice(ground, old_names, seed_nodes, seed_edges):
    """A copy of the ground with the old kernel stratum swapped for the
    seed's: old kernel citizens and their outbound edges out, fresh ones
    in; every project node, project edge, and ground fact untouched.

    Merge-with-visibility (the enrichment ruling): the seed wins every
    key it defines — the kernel owns its identity — but a canon-side
    key the seed does NOT define is the world's own enrichment of a
    kernel citizen, and it rides the splice unchanged. A removed
    citizen's enrichment is not resurrected (the orphan check upstream
    already ruled on the removal). Returns (spliced, carried) where
    carried = {citizen name: sorted canon-only keys that rode} — the
    report names what rode rather than re-diffing."""
    spliced = GraphData()
    carried = {}
    for (label, name), props in ground.nodes.items():
        if label == ARCHETYPE_LABEL and name in old_names:
            continue
        spliced.ensure_node(label, name, **props)
    for name, props in seed_nodes.items():
        merged = dict(props)
        if name in old_names:
            old_props = ground.nodes.get((ARCHETYPE_LABEL, name)) or {}
            extras = {key: value for key, value in old_props.items()
                      if key not in props}
            if extras:
                merged.update(extras)
                carried[name] = sorted(extras)
        spliced.ensure_node(ARCHETYPE_LABEL, name, **merged)
    for edge in ground.edges:
        if edge.from_label == ARCHETYPE_LABEL and edge.from_name in old_names:
            continue
        spliced.edges.append(edge)
    spliced.edges.extend(seed_edges)
    return spliced, carried


# -- the rename rule: the migration charter's first data-moving op ---------
#
# A kernel ceremony may rename what it declares (the bracket sweep). The
# metaontology's `renamed` map (old -> new) drives a mechanical rewrite
# of the canon BEFORE the splice: every citizen under an old label is
# relabeled, every edge endpoint re-pointed, every Archetype row named
# for an old name renamed with its DECLARED_IN / INSTANCE_OF / ladder
# edges, every project spec's concept bindings, subtypes, and
# relationship targets rewritten, and the attribution ledger's refs
# rewritten at apply. A project label that already uses a NEW name
# refuses by name — nothing else is unmappable. A project-declared row
# whose name is renamed onto a kernel concept is ADOPTED: its file-era
# spec retires, its extra concept bindings survive as declared
# memberships on each of its citizens, and the splice then brings the
# kernel's own row.

ADOPTION_BASIS = ("adopted at the kernel ceremony from the retired spec of "
                  "project label '{label}' (kernel {version})")


def _rewrite_spec(spec, renames):
    """A project spec with every renamed concept name rewritten: concept
    bindings, subtypes, and relationship targets."""
    def one(value):
        if isinstance(value, str):
            return renames.get(value, value)
        if isinstance(value, list):
            return [one(v) for v in value]
        return value
    out = dict(spec)
    for key in ("concept", "subtypes"):
        if key in out:
            out[key] = one(out[key])
    rels = out.get("relationships")
    if isinstance(rels, list):
        out["relationships"] = [
            dict(rel, to=one(rel.get("to"))) if isinstance(rel, dict)
            and "to" in rel else rel for rel in rels]
    return out


def rename_problems(ground, renames):
    """Refusals, collated: a NEW name already in use by the canon for
    something that is not the renamed row — a citizen label or an
    Archetype row a project declared under the bracketed name."""
    problems = []
    for old, new in sorted(renames.items()):
        holds_old = ((ARCHETYPE_LABEL, old) in ground.nodes
                     or any(label == old for label, _ in ground.nodes))
        holds_new = ((ARCHETYPE_LABEL, new) in ground.nodes
                     or any(label == new for label, _ in ground.nodes))
        if holds_old and holds_new:
            problems.append(
                f"Attempted to rename '{old}' to '{new}'. Failed due to: "
                f"this canon already holds '{new}' as well — the two "
                "would collapse into one. Retire or rename the project's "
                f"own '{new}' through an ordinary gated round first.")
    return problems


def apply_renames(ground, renames, version="?"):
    """A copy of the ground with the renames applied, plus the adoption
    records: [{label, new, citizens, retired_spec_keys, memberships}]
    for each project-declared row renamed onto a kernel name."""
    import json

    from .extract import make_edge
    from .ontology import MEMBERSHIP_EDGE_TYPE, is_concept_archetype
    active = {old: new for old, new in renames.items()
              if (ARCHETYPE_LABEL, old) in ground.nodes
              or any(label == old for label, _ in ground.nodes)}
    if not active:
        return ground, []
    declared_by_project = {
        edge.from_name for edge in ground.edges
        if edge.type == "DECLARED_IN" and edge.from_label == ARCHETYPE_LABEL
        and edge.to_label == ARCHETYPE_LABEL and edge.to_name == "Ontology"}
    renamed = GraphData()
    adoptions = []
    memberships = []
    for (label, name), props in ground.nodes.items():
        new_label = active.get(label, label)
        new_name = name
        new_props = dict(props)
        if label == ARCHETYPE_LABEL and name in active:
            new_name = active[name]
            if name in declared_by_project:
                spec = json.loads(new_props.pop("spec_json", "{}") or "{}")
                bindings = spec.get("concept") or []
                bindings = [bindings] if isinstance(bindings, str) else list(bindings)
                extra = [b for b in bindings
                         if (ARCHETYPE_LABEL, b) in ground.nodes
                         and b not in ("Provenance", "Judgment", "Concept",
                                       "Facet")]
                # a binding survives as a declared membership only where
                # the pattern admits one — a subject-matter (Concept-
                # rooted) target; any other binding retires with the
                # spec, named in the report, never dropped in silence
                kept = [b for b in extra if is_concept_archetype(ground, b)]
                dropped = [b for b in extra if b not in kept]
                citizens = sorted(str(n) for (l, n) in ground.nodes
                                  if l == name)
                for concept in kept:
                    for citizen in citizens:
                        memberships.append(make_edge(
                            MEMBERSHIP_EDGE_TYPE, new_name, citizen,
                            ARCHETYPE_LABEL, concept,
                            {"basis": ADOPTION_BASIS.format(
                                label=name, version=version)}))
                adoptions.append({"label": name, "new": new_name,
                                  "citizens": len(citizens),
                                  "retired_spec_keys": sorted(spec),
                                  "memberships": kept,
                                  "bindings_dropped": dropped})
        elif label == ARCHETYPE_LABEL and "spec_json" in new_props:
            try:
                spec = json.loads(new_props["spec_json"])
            except ValueError:
                spec = None
            if isinstance(spec, dict):
                rewritten = _rewrite_spec(spec, active)
                if rewritten != spec:
                    new_props["spec_json"] = json.dumps(rewritten,
                                                        sort_keys=True)
        renamed.ensure_node(new_label, new_name, **new_props)
    adopted = {a["label"] for a in adoptions}
    for edge in ground.edges:
        if edge.type == "DECLARED_IN" and edge.from_label == ARCHETYPE_LABEL \
                and edge.from_name in adopted:
            continue  # the kernel's own DECLARED_IN arrives with the splice
        from_label = active.get(edge.from_label, edge.from_label)
        to_label = active.get(edge.to_label, edge.to_label)
        from_name = (active.get(edge.from_name, edge.from_name)
                     if edge.from_label == ARCHETYPE_LABEL else edge.from_name)
        to_name = (active.get(edge.to_name, edge.to_name)
                   if edge.to_label == ARCHETYPE_LABEL else edge.to_name)
        renamed.edges.append(make_edge(edge.type, from_label, from_name,
                                       to_label, to_name, dict(edge.props)))
    renamed.edges.extend(memberships)
    return renamed, adoptions


def rewrite_attribution_labels(base_dir, renames, branch=None):
    """Rewrite the attribution ledger's citizen refs under the renames.
    Returns the number of rows changed; the ledger is the current
    record the census audits, so it moves with the canon."""
    import json

    from .proposal import attribution_log_path
    path = attribution_log_path(base_dir, branch)
    if not path.exists():
        return 0
    changed = 0
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        refs = row.get("citizens") or []
        new_refs = []
        for ref in refs:
            label, name = ref[0], ref[1]
            new_label = renames.get(label, label)
            new_name = (renames.get(name, name) if label == ARCHETYPE_LABEL
                        else name)
            new_refs.append([new_label, new_name])
        if new_refs != [list(r) for r in refs]:
            changed += 1
            row["citizens"] = new_refs
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def installed_renames(metaontology_path=None):
    """The installed kernel's `renamed` map (old -> new)."""
    from .ontology import load_metaontology
    _kernel, meta, _findings = load_metaontology(
        Path(metaontology_path or METAONTOLOGY_PATH))
    return dict(meta.get("renamed") or {})


def relabel_census(ground, renames):
    """[(old name, citizens relabeled)] for every rename this canon
    actually carries — an Archetype row under the old name, or citizens
    under the old label."""
    census = []
    for old in sorted(renames):
        count = sum(1 for label, _ in ground.nodes if label == old)
        if count or (ARCHETYPE_LABEL, old) in ground.nodes:
            census.append((old, count))
    return census


def leaks(delta, kernel_names, relabeled_labels=(), adopted=()):
    """The splice's post-condition, checked rather than trusted: every
    item in the migration delta must name a kernel citizen (old or
    new) — or, under the rename rule, a citizen leaving an old label
    or arriving under its new one, an edge touching such a citizen, a
    project row whose spec was rewritten for the rename, or a declared
    membership an adoption wrote. Returns the violations — non-empty
    means the splice touched something it had no business touching,
    and nothing may be written."""
    relabeled = set(relabeled_labels)
    adopted = set(adopted)
    problems = []
    for label, name, _payload in delta.nodes_added + delta.nodes_removed:
        if label in relabeled:
            continue
        if label != ARCHETYPE_LABEL or name not in kernel_names:
            problems.append(f"node ({label}, '{name}')")
    for label, name, changes in delta.nodes_changed:
        if label == ARCHETYPE_LABEL and name in kernel_names:
            continue
        if label == ARCHETYPE_LABEL and relabeled \
                and set(changes) <= {"spec_json"}:
            continue  # a project spec rewritten for the rename
        problems.append(f"node ({label}, '{name}')")
    edges = (delta.edges_added + delta.edges_removed
             + [edge for edge, _changes in delta.edges_changed])
    for edge in edges:
        if edge.from_label in relabeled or edge.to_label in relabeled:
            continue
        if edge.from_label == ARCHETYPE_LABEL and (
                edge.from_name in relabeled or edge.to_name in relabeled
                or edge.from_name in adopted):
            continue
        if edge.from_label != ARCHETYPE_LABEL \
                or edge.from_name not in kernel_names:
            problems.append(f"edge ({edge.from_label}, '{edge.from_name}') "
                            f"-{edge.type}-> ({edge.to_label}, "
                            f"'{edge.to_name}')")
    return problems
