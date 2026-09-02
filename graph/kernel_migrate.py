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
    in; every project node, project edge, and ground fact untouched."""
    spliced = GraphData()
    for (label, name), props in ground.nodes.items():
        if label == ARCHETYPE_LABEL and name in old_names:
            continue
        spliced.ensure_node(label, name, **props)
    for name, props in seed_nodes.items():
        spliced.ensure_node(ARCHETYPE_LABEL, name, **props)
    for edge in ground.edges:
        if edge.from_label == ARCHETYPE_LABEL and edge.from_name in old_names:
            continue
        spliced.edges.append(edge)
    spliced.edges.extend(seed_edges)
    return spliced


def leaks(delta, kernel_names):
    """The splice's post-condition, checked rather than trusted: every
    item in the migration delta must name a kernel citizen (old or
    new). Returns the violations — non-empty means the splice touched
    something it had no business touching, and nothing may be written."""
    problems = []
    for label, name, _payload in (delta.nodes_added + delta.nodes_removed
                                  + delta.nodes_changed):
        if label != ARCHETYPE_LABEL or name not in kernel_names:
            problems.append(f"node ({label}, '{name}')")
    edges = (delta.edges_added + delta.edges_removed
             + [edge for edge, _changes in delta.edges_changed])
    for edge in edges:
        if edge.from_label != ARCHETYPE_LABEL \
                or edge.from_name not in kernel_names:
            problems.append(f"edge ({edge.from_label}, '{edge.from_name}') "
                            f"-{edge.type}-> ({edge.to_label}, "
                            f"'{edge.to_name}')")
    return problems
