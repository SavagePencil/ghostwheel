"""The kernel ceremony guard: the manual's committed backup embeds the
kernel schema stratum, and this repo ships both — the packaged
metaontology and the manual's canon. A kernel change that does not carry
the manual's migration in the same change set would leave the repo
internally skewed: engine at one kernel, its own knowledge base frozen
at another. This guard is what makes the move-atomically claim real —
it fails the moment the manual's embedded kernel stratum drifts from
the packaged metaontology, in either direction.

The comparison is stratum-scoped, so the manual is free to grow: only
citizens DECLARED_IN the Metaontology layer (plus the Metaontology
anchor itself) and their OUTBOUND edges are held to the seed. Project
citizens may point AT kernel citizens (references flow project ->
kernel); kernel citizens gaining new outbound edges, changed doc text,
or vanishing entirely is kernel drift and fails here — the remedy is a
kernel ceremony whose change set migrates the manual's canon too.
"""

from pathlib import Path

from graph.extract import Extractor, schema_only
from graph.ontology import ARCHETYPE_LABEL, kernel_ontology
from graph.restore import read_export

REPO_ROOT = Path(__file__).resolve().parent.parent
MANUAL_EXPORT = REPO_ROOT / "manual" / "graph" / "export"


def _kernel_stratum(graph):
    """The kernel-declared subset of a graph: nodes named DECLARED_IN
    the Metaontology layer plus the Metaontology anchor, and every edge
    leaving one of them."""
    kernel = {edge.from_name for edge in graph.edges
              if edge.type == "DECLARED_IN"
              and edge.from_label == ARCHETYPE_LABEL
              and edge.to_label == ARCHETYPE_LABEL
              and edge.to_name == "Metaontology"}
    kernel.add("Metaontology")
    nodes = {name: props
             for (label, name), props in graph.nodes.items()
             if label == ARCHETYPE_LABEL and name in kernel}
    edges = {edge for edge in graph.edges
             if edge.from_label == ARCHETYPE_LABEL
             and edge.from_name in kernel}
    return nodes, edges


def _fresh_seed(tmp_path):
    ontology, _findings = kernel_ontology(tmp_path / "seed")
    extractor = Extractor(ontology)
    extractor.build_metamodel()
    return schema_only(extractor.graph)


def test_the_manual_kernel_matches_the_packaged_metaontology(tmp_path):
    manual = read_export(MANUAL_EXPORT)
    seed = _fresh_seed(tmp_path)
    manual_nodes, manual_edges = _kernel_stratum(manual)
    seed_nodes, seed_edges = _kernel_stratum(seed)
    assert manual_nodes == seed_nodes, (
        "The manual's embedded kernel citizens differ from the packaged "
        "metaontology — a kernel change must migrate manual/graph/export "
        "in the same change set (re-seed the kernel stratum through the "
        "manual's delta path).")
    assert manual_edges == seed_edges, (
        "The manual's kernel citizens carry different outbound edges "
        "than the packaged metaontology's seed — kernel drift, or a "
        "kernel citizen referencing project vocabulary (references flow "
        "project -> kernel, never back). Migrate the manual's canon in "
        "this change set.")


def test_the_guard_scopes_to_the_kernel_stratum(tmp_path):
    """Growth is not drift: project-layer citizens, and project edges
    pointing AT kernel citizens, must pass untouched — the guard would
    otherwise re-freeze the manual at its seed forever."""
    from graph.extract import make_edge
    seed = _fresh_seed(tmp_path)
    grown_nodes, grown_edges = _kernel_stratum(seed)
    seed.ensure_node(ARCHETYPE_LABEL, "Some Project Concept",
                     doc="project vocabulary, declared by a round")
    seed.edges.append(make_edge(
        "DECLARED_IN", ARCHETYPE_LABEL, "Some Project Concept",
        ARCHETYPE_LABEL, "Ontology"))
    seed.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, "Some Project Concept",
        ARCHETYPE_LABEL, "Concept"))  # project -> kernel reference
    assert _kernel_stratum(seed) == (grown_nodes, grown_edges)
