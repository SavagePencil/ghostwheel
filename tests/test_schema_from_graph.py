"""The schema inversion's proof: the graph alone is enough to run a
round. A migrated backup carries the schema stratum plus the verbatim
spec embeddings the derive-era passes need, so an Ontology can be
reconstructed from the graph — no ontology.yaml consulted — and
derivation over that reconstruction lands byte-identically back on the
backup.

Two equivalence surfaces:
  1. load_ontology(ontology.yaml) vs ontology_from_graph(read_export) —
     the reconstruction recovers what the loader produces, field for field.
  2. derive(ontology_from_graph(export), export) == export, byte-identical —
     the graph is a self-sufficient input to a round.

The fixture canon is a from-sources build of the storybook corpus: it is
loaded, extracted, serialized to a backup, and read back — so the whole
round trip runs on a corpus the engine has no built-in vocabulary for,
never on any committed canon. A second, in-memory build proves a fresh
extraction emits the embeddings and round-trips through the reconstruction.
"""

from pathlib import Path

import pytest

from graph import export as export_mod
from graph.extract import derive, extract
from graph.ontology import (ARCHETYPE_LABEL, ERROR, load_ontology,
                            ontology_from_graph)
from graph.restore import read_export

STORYBOOK = Path(__file__).resolve().parent / "fixtures" / "storybook"

# rendered_view / rendered_views are loader- AND derive-inert render-only
# mappings; they stay in ontology.yaml (their consumers read them there)
# and are deliberately not embedded on the schema node, so spec-for-spec
# comparison folds them out of both sides.
RENDER_ONLY = ("rendered_view", "rendered_views")


def _without_render_only(spec):
    return {key: value for key, value in spec.items()
            if key not in RENDER_ONLY}


@pytest.fixture(scope="module")
def yaml_ontology():
    ontology, findings = load_ontology(STORYBOOK / "ontology.yaml", STORYBOOK)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    return ontology


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    # Build the fixture backup from sources: load the storybook, extract,
    # serialize to a scratch export directory, and read it back — the same
    # on-disk backup a round would build from, with no committed canon in
    # sight.
    ontology, findings = load_ontology(STORYBOOK / "ontology.yaml", STORYBOOK)
    assert ontology is not None, findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR], \
        extract_findings
    export_dir = tmp_path_factory.mktemp("storybook_export")
    export_mod.write_export(graph, export_dir)
    return read_export(export_dir)


@pytest.fixture(scope="module")
def reconstructed(export):
    return ontology_from_graph(export, STORYBOOK)


# -- surface 1: reconstruction recovers what the loader produces ------------


def test_concepts_reconstruct_spec_for_spec(yaml_ontology, reconstructed):
    assert set(reconstructed.concepts) == set(yaml_ontology.concepts)
    mismatches = {name: (yaml_ontology.concepts[name], reconstructed.concepts[name])
                  for name in yaml_ontology.concepts
                  if yaml_ontology.concepts[name] != reconstructed.concepts[name]}
    assert not mismatches, mismatches


def test_nodes_reconstruct_spec_for_spec(yaml_ontology, reconstructed):
    assert set(reconstructed.nodes) == set(yaml_ontology.nodes)
    mismatches = {
        name: (yaml_ontology.nodes[name], reconstructed.nodes[name])
        for name in yaml_ontology.nodes
        if _without_render_only(yaml_ontology.nodes[name])
        != _without_render_only(reconstructed.nodes[name])}
    assert not mismatches, mismatches


def test_kernel_names_reconstruct(yaml_ontology, reconstructed):
    assert reconstructed.kernel_names == yaml_ontology.kernel_names


def test_enums_and_defaults_reconstruct(yaml_ontology, reconstructed):
    assert reconstructed.enums == yaml_ontology.enums
    assert reconstructed.defaults == yaml_ontology.defaults


def test_declaration_derived_views_reconstruct(yaml_ontology, reconstructed):
    # non_prose_sources() and prose_files() are what the coverage sweeps
    # drive from — proof the reconstruction feeds them the same declarations.
    assert reconstructed.non_prose_sources() == yaml_ontology.non_prose_sources()
    assert reconstructed.prose_files() == yaml_ontology.prose_files()


def test_meta_version_reconstructs(yaml_ontology, reconstructed):
    # The metaontology identity the graph was built with (stable kernel
    # version), read back from the Metaontology anchor.
    assert reconstructed.meta["version"] == yaml_ontology.meta["version"]


def test_version_and_tag_round_trip_through_the_anchor(export, reconstructed):
    # Post-flip, the ontology.yaml version: field is historical bootstrap
    # provenance and may drift behind canon (the graph's own anchor is the
    # live value). So version/tag fidelity is a round-trip claim against
    # the anchor the reconstruction read, not an equality with the file.
    anchor = export.nodes[(ARCHETYPE_LABEL, "Ontology")]
    assert reconstructed.raw.get("version") == anchor.get("version")
    assert reconstructed.raw.get("tag") == anchor.get("tag")


# -- surface 2: the graph alone re-derives the backup ----------------------


def test_graph_alone_rederives_backup_byte_identical(export, reconstructed):
    # THE prize: no ontology.yaml in sight — reconstruct the schema from the
    # backup and re-derive; land byte-for-byte back on the backup.
    rederived, findings = derive(reconstructed, export)
    errors = [f for f in findings if f.severity == ERROR]
    assert not errors, errors
    assert export_mod.serialize(rederived) == export_mod.serialize(export), (
        "derivation over the graph-reconstructed ontology disagrees with "
        "the backup")


# -- a from-sources build emits the embeddings and round-trips -------------

FILES = {
    "data/gadgets.csv": """\
        Gadget,Power
        Sprocket,3
        Flywheel,7
        """,
    "data/grades.csv": """\
        Grade
        Bronze
        Silver
        """,
}

# A minimal corpus exercising: a plain label citizen (spec_json), a concept
# carrying surface_forms, a both-concept-and-label citizen (Widget, in BOTH
# dicts), and an Archetype-level ordered ladder (values reconstruction).
ONTOLOGY = """\
    version: 1
    concepts:
      Gizmo Concept: { instance_of: Concept }
      Contraption:
        instance_of: Gizmo Concept
        stub: true
        surface_forms: [Contraptions, Doohickey]
        doc: "A recognized-but-unmodeled gizmo."
      Widget: { instance_of: Gizmo Concept }
      Grade:
        instance_of: Gizmo Concept
        ordered: true
        values: [Bronze, Silver]
        doc: "A quality ladder."
      Bronze: { instance_of: Grade }
      Silver: { instance_of: Grade }
    defaults: { split: comma, on_missing: placeholder }
    nodes:
      Gadget:
        source: data/gadgets.csv
        key: Gadget
        concept: Gizmo Concept
        catalog:
          power: { type: int, doc: "oomph" }
        properties:
          power: { column: Power }
      Widget:
        values: [Left Widget, Right Widget]
        concept: Widget
    """


@pytest.fixture
def built(make_repo):
    base_dir, path = make_repo(FILES, ONTOLOGY)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR], \
        extract_findings
    return base_dir, ontology, graph


def test_from_sources_build_emits_spec_json(built):
    _, _, graph = built
    gadget = graph.nodes[(ARCHETYPE_LABEL, "Gadget")]
    assert '"key": "Gadget"' in gadget["spec_json"]
    assert '"source": "data/gadgets.csv"' in gadget["spec_json"]
    # a concept's term-index inputs ride as props
    contraption = graph.nodes[(ARCHETYPE_LABEL, "Contraption")]
    assert contraption["surface_forms"] == ["Contraptions", "Doohickey"]


def test_from_sources_build_round_trips_through_reconstruction(built):
    base_dir, ontology, graph = built
    rec = ontology_from_graph(graph, base_dir)
    # nodes and concepts recover spec-for-spec
    assert set(rec.nodes) == set(ontology.nodes)
    for name, spec in ontology.nodes.items():
        assert _without_render_only(rec.nodes[name]) == \
            _without_render_only(spec), name
    assert set(rec.concepts) == set(ontology.concepts)
    for name, spec in ontology.concepts.items():
        assert rec.concepts[name] == spec, name
    # the both-concept-and-label citizen lands in BOTH dicts
    assert "Widget" in rec.nodes and "Widget" in rec.concepts
    # and the ordered ladder's values come back in rank order
    assert rec.concepts["Grade"]["values"] == ["Bronze", "Silver"]
    # re-derivation over the reconstruction reproduces the build
    rederived, _ = derive(rec, graph)
    assert export_mod.serialize(rederived) == export_mod.serialize(graph)


def test_ordered_label_does_not_fabricate_an_ordered_concept(make_repo):
    # A name that is both a concept and an ordered LABEL shares one
    # ->Ordered edge; the reconstruction must attribute it to the label
    # side (spec_json) and never fabricate ordered/values on the
    # concept spec.
    from graph.extract import extract
    from graph.ontology import load_ontology, ontology_from_graph
    files = dict(FILES)
    files["data/sparks.csv"] = "Spark\nFaint\nBright\n"
    ontology_src = ONTOLOGY.replace(
        "      Widget: { instance_of: Gizmo Concept }",
        "      Widget: { instance_of: Gizmo Concept }\n"
        "      Spark: { instance_of: Gizmo Concept }")
    ontology_src = ontology_src.replace(
        "    nodes:",
        "    nodes:\n"
        "      Spark:\n"
        "        source: data/sparks.csv\n"
        "        key: Spark\n"
        "        concept: Spark\n"
        "        ordered: true")
    base_dir, path = make_repo(files, ontology_src)
    ontology, _ = load_ontology(path, base_dir)
    graph, _ = extract(ontology)
    rebuilt = ontology_from_graph(graph, base_dir)
    assert rebuilt.nodes["Spark"].get("ordered") is True
    concept_spec = rebuilt.concepts.get("Spark", {})
    assert "ordered" not in concept_spec
    assert "values" not in concept_spec
