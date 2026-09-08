"""The schema inversion's proof: the graph alone is enough to run a
round. The committed backup carries the schema stratum plus the verbatim
spec embeddings the derive passes need, so an Ontology is reconstructed
from the graph — no file consulted — and derivation over that
reconstruction lands byte-identically back on the backup.

Two fidelity surfaces:
  1. ontology_from_graph recovers exactly what the graph embeds — label
     specs verbatim from spec_json, concepts from the Archetype props and
     the tower/taxonomy edges, kernel names from the Metaontology layer,
     enums/defaults/version from the anchors.
  2. derive(ontology_from_graph(export), export) == export,
     byte-identical — the graph is a self-sufficient input to a round.

The fixture canon is the committed storybook export (a corpus the engine
has no built-in vocabulary for); the direct-construction tests author
their own miniature schema stratum in memory the way a gated round would
land it.
"""

import json

import pytest

from graph import export as export_mod
from graph.extract import GraphData, derive, make_edge
from graph.ontology import (ARCHETYPE_LABEL, ERROR, METAONTOLOGY_PATH,
                            load_metaontology, ontology_from_graph,
                            rendered_views_of)
from tests.test_branch import build_canon, storybook_ontology

# rendered_view / rendered_views are derive-inert render-only mappings;
# they ride each label row BESIDE its spec (rendered_views_json) and
# reconstruct as the spec's list form, so spec-for-spec comparison folds
# the two spellings out and compares the views as one list.
RENDER_ONLY = ("rendered_view", "rendered_views")


def _without_render_only(spec):
    folded = {key: value for key, value in spec.items()
              if key not in RENDER_ONLY}
    views = rendered_views_of(spec)
    if views:
        folded["rendered_views"] = views
    return folded


@pytest.fixture(scope="module")
def export():
    return build_canon()


@pytest.fixture(scope="module")
def reconstructed():
    return storybook_ontology()


# -- surface 1: reconstruction recovers exactly what the graph embeds -------


def test_nodes_reconstruct_spec_for_spec_from_the_embeddings(
        export, reconstructed):
    embedded = {name: json.loads(props["spec_json"])
                for (label, name), props in export.nodes.items()
                if label == ARCHETYPE_LABEL and "spec_json" in props}
    assert set(reconstructed.nodes) == set(embedded)
    mismatches = {
        name: (embedded[name], reconstructed.nodes[name])
        for name in embedded
        if _without_render_only(embedded[name])
        != _without_render_only(reconstructed.nodes[name])}
    assert not mismatches, mismatches


def test_concepts_reconstruct_from_props_and_tower(reconstructed):
    concepts = reconstructed.concepts
    # a kernel ladder: ordered via the ->Ordered edge, values in rank order
    assert concepts["Completeness"]["ordered"] is True
    assert concepts["Completeness"]["values"] == \
        ["Cited", "Attested", "Transcribed"]
    # the tower: instance_of from the Archetype-level INSTANCE_OF edge
    assert concepts["Story Concept"]["instance_of"] == "Concept"
    assert concepts["Cited"]["instance_of"] == "Completeness"
    # docs ride as props and come back on the spec
    assert "doc" in concepts["Theme"]
    # a recursive segment type keeps its marker
    assert concepts["Page"].get("recursive") is True
    # the anchors themselves are neither concept nor label
    assert "Ontology" not in concepts and "Metaontology" not in concepts
    assert "Ontology" not in reconstructed.nodes


def test_kernel_names_reconstruct_from_the_metaontology_layer(
        export, reconstructed):
    declared = {e.from_name for e in export.edges
                if e.type == "DECLARED_IN" and e.to_name == "Metaontology"}
    assert reconstructed.kernel_names == declared
    # and they are exactly what the packaged kernel declares — the graph
    # was built with this metaontology and reports its identity
    kernel, meta, _findings = load_metaontology(METAONTOLOGY_PATH)
    assert reconstructed.kernel_names == set(kernel)
    assert reconstructed.meta["version"] == meta.get("version")


def test_enums_and_defaults_reconstruct_from_the_anchor(
        export, reconstructed):
    anchor = export.nodes[(ARCHETYPE_LABEL, "Ontology")]
    assert reconstructed.enums == json.loads(anchor["enums_json"])
    assert reconstructed.defaults == json.loads(anchor["defaults_json"])


def test_declaration_derived_views_reconstruct(reconstructed):
    # non_prose_sources() and prose_files() are what the coverage sweeps
    # drive from — proof the reconstruction feeds them the storybook's
    # declarations: one markdown member of the file-valued [Artifact]
    # roster, nothing marked non-prose.
    assert reconstructed.non_prose_sources() == set()
    assert reconstructed.prose_files() == ["docs/tale.md"]


def test_meta_version_reconstructs(export, reconstructed):
    # The metaontology identity the graph was built with (stable kernel
    # version), read back from the Metaontology anchor.
    anchor = export.nodes[(ARCHETYPE_LABEL, "Metaontology")]
    assert reconstructed.meta["version"] == anchor["version"]


def test_version_and_tag_round_trip_through_the_anchor(export, reconstructed):
    # The graph's own anchor is the live value for the schema version and
    # display tag; the reconstruction reads exactly it.
    anchor = export.nodes[(ARCHETYPE_LABEL, "Ontology")]
    assert reconstructed.raw.get("version") == anchor.get("version")
    assert reconstructed.raw.get("tag") == anchor.get("tag")


# -- surface 2: the graph alone re-derives the backup ----------------------


def test_graph_alone_rederives_backup_byte_identical(export, reconstructed):
    # THE prize: no schema file in sight — reconstruct the schema from
    # the backup and re-derive; land byte-for-byte back on the backup.
    rederived, findings = derive(reconstructed, export)
    errors = [f for f in findings if f.severity == ERROR]
    assert not errors, errors
    assert export_mod.serialize(rederived) == export_mod.serialize(export), (
        "derivation over the graph-reconstructed ontology disagrees with "
        "the backup")


# -- directly authored embeddings round-trip through the reconstruction ----
#
# A miniature schema stratum built the way a gated round lands it: a
# plain label citizen (spec_json), a concept carrying surface_forms, a
# both-concept-and-label citizen (in BOTH dicts), and an Archetype-level
# ordered ladder (values reconstruction).

GADGET_SPEC = {"source": "data/gadgets.csv", "key": "Gadget",
               "concept": "Gizmo Concept",
               "catalog": {"power": {"type": "int", "doc": "oomph"}},
               "properties": {"power": {"column": "Power"}}}
WIDGET_SPEC = {"values": ["Left Widget", "Right Widget"],
               "concept": "Widget"}


def _declare(g, name, layer="Ontology", **props):
    g.ensure_node(ARCHETYPE_LABEL, name, **props)
    g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                             ARCHETYPE_LABEL, layer))


def mini_schema():
    g = GraphData()
    g.ensure_node(ARCHETYPE_LABEL, "Ontology", version=1,
                  enums_json="{}", defaults_json=json.dumps(
                      {"split": "comma", "on_missing": "placeholder"},
                      sort_keys=True))
    g.ensure_node(ARCHETYPE_LABEL, "Metaontology", version="0.0.0")
    for kernel in ("Concept", "Facet", "Ordered"):
        _declare(g, kernel, layer="Metaontology")
    _declare(g, "Gizmo Concept")
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Gizmo Concept",
                             ARCHETYPE_LABEL, "Concept"))
    _declare(g, "Contraption", stub=True,
             surface_forms=["Contraptions", "Doohickey"],
             doc="A recognized-but-unmodeled gizmo.")
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Contraption",
                             ARCHETYPE_LABEL, "Gizmo Concept"))
    # the ordered ladder: Grade + its ranked members
    _declare(g, "Grade", doc="A quality ladder.")
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Grade",
                             ARCHETYPE_LABEL, "Gizmo Concept"))
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Grade",
                             ARCHETYPE_LABEL, "Ordered"))
    for rank, member in enumerate(("Bronze", "Silver")):
        _declare(g, member, rank=rank)
        g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, member,
                                 ARCHETYPE_LABEL, "Grade"))
    # a plain label and a both-concept-and-label citizen
    _declare(g, "Gadget", spec_json=json.dumps(GADGET_SPEC, sort_keys=True))
    _declare(g, "Widget", spec_json=json.dumps(WIDGET_SPEC, sort_keys=True))
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Widget",
                             ARCHETYPE_LABEL, "Gizmo Concept"))
    return g


def test_directly_authored_embeddings_round_trip(tmp_path):
    rec = ontology_from_graph(mini_schema(), tmp_path)
    # labels recover spec-for-spec from their embeddings
    assert set(rec.nodes) == {"Gadget", "Widget"}
    assert rec.nodes["Gadget"] == GADGET_SPEC
    assert rec.nodes["Widget"] == WIDGET_SPEC
    # concepts recover from props and the tower
    assert rec.concepts["Contraption"] == {
        "instance_of": "Gizmo Concept", "stub": True,
        "doc": "A recognized-but-unmodeled gizmo.",
        "surface_forms": ["Contraptions", "Doohickey"]}
    # the both-concept-and-label citizen lands in BOTH dicts
    assert "Widget" in rec.nodes and "Widget" in rec.concepts
    assert rec.concepts["Widget"]["instance_of"] == "Gizmo Concept"
    # and the ordered ladder's values come back in rank order
    assert rec.concepts["Grade"]["ordered"] is True
    assert rec.concepts["Grade"]["values"] == ["Bronze", "Silver"]
    # kernel names come from the Metaontology layer alone
    assert rec.kernel_names == {"Concept", "Facet", "Ordered"}
    assert rec.defaults == {"split": "comma", "on_missing": "placeholder"}


def test_ordered_label_does_not_fabricate_an_ordered_concept(tmp_path):
    # A name that is both a concept and an ordered LABEL shares one
    # ->Ordered edge; the reconstruction must attribute it to the label
    # side (spec_json) and never fabricate ordered/values on the
    # concept spec.
    g = mini_schema()
    spark_spec = {"source": "data/sparks.csv", "key": "Spark",
                  "concept": "Spark", "ordered": True}
    _declare(g, "Spark", spec_json=json.dumps(spark_spec, sort_keys=True))
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Spark",
                             ARCHETYPE_LABEL, "Gizmo Concept"))
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Spark",
                             ARCHETYPE_LABEL, "Ordered"))
    rebuilt = ontology_from_graph(g, tmp_path)
    assert rebuilt.nodes["Spark"].get("ordered") is True
    concept_spec = rebuilt.concepts.get("Spark", {})
    assert "ordered" not in concept_spec
    assert "values" not in concept_spec
