"""Shared spec and ontology semantics, checked over graph-built
ontologies: the schema lives on the graph, ontology_from_graph is the
one way any command reads it back, and check_ontology guards the spec
shapes a gated round could land. Each test authors the schema stratum
directly (Archetype rows carrying spec_json, DECLARED_IN edges, the
Ontology/Metaontology anchors), reconstructs, and checks."""

import json
import textwrap

from graph.extract import GraphData, make_edge
from graph.ontology import (ARCHETYPE_LABEL, ERROR, check_ontology,
                            ontology_from_graph)

MINI_CSV = {
    "data/things.csv": """\
        Thing,Kind,Friends
        Rock,Mineral,Stick
        Stick,Wood,Rock
        """,
}

DEFAULT_ENUMS = {"Kind": {"values": ["Mineral", "Wood"]}}
DEFAULT_DEFAULTS = {"split": "comma", "on_missing": "placeholder"}
KERNEL = ("Concept", "Facet", "Ordered")


def errors_of(findings):
    return [f for f in findings if f.severity == ERROR]


def write_files(base, files):
    for relpath, content in files.items():
        path = base / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")


def thing_spec(**over):
    """The reference label spec: a csv-sourced catalog with one enum
    property and one plain relationship."""
    spec = {"source": "data/things.csv", "key": "Thing",
            "catalog": {"kind": {"type": "enum:Kind", "doc": "what it is"}},
            "properties": {"kind": {"column": "Kind"}},
            "relationships": [
                {"type": "FRIENDS_WITH", "to": "Thing", "column": "Friends"}]}
    spec.update(over)
    return spec


def rel(**over):
    entry = {"type": "FRIENDS_WITH", "to": "Thing", "column": "Friends"}
    entry.update(over)
    return entry


def schema_graph(labels=None, enums=DEFAULT_ENUMS, defaults=DEFAULT_DEFAULTS,
                 kernel=KERNEL):
    """A schema stratum authored the graph-native way: anchors, kernel
    rows declared in the Metaontology layer, label rows carrying their
    spec_json embeddings declared in the Ontology layer."""
    g = GraphData()
    g.ensure_node(ARCHETYPE_LABEL, "Ontology",
                  enums_json=json.dumps(enums, sort_keys=True),
                  defaults_json=json.dumps(defaults, sort_keys=True),
                  version=1)
    g.ensure_node(ARCHETYPE_LABEL, "Metaontology", version="0.0.0")
    for name in kernel:
        g.ensure_node(ARCHETYPE_LABEL, name)
        g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, "Metaontology"))
    for label, spec in (labels or {}).items():
        g.ensure_node(ARCHETYPE_LABEL, label,
                      spec_json=json.dumps(spec, sort_keys=True))
        g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                 ARCHETYPE_LABEL, "Ontology"))
    return g


def checked(tmp_path, labels=None, files=MINI_CSV, graph=None, **kw):
    """Reconstruct an Ontology from a graph-built schema and run the
    checker over it; returns (ontology, findings)."""
    write_files(tmp_path, files or {})
    graph = graph if graph is not None else schema_graph(labels=labels, **kw)
    ontology = ontology_from_graph(graph, tmp_path)
    return ontology, check_ontology(ontology)


def test_a_clean_label_spec_reconstructs_and_checks_clean(tmp_path):
    ontology, findings = checked(tmp_path, {"Thing": thing_spec()})
    assert ontology is not None
    assert errors_of(findings) == []
    assert "Thing" in ontology.nodes


def test_unknown_parser(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[rel(parser="nope")])})
    assert any("unknown parser 'nope'" in f.detail for f in errors_of(findings))


def test_missing_column(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(properties={"kind": {"column": "Colour"}})})
    assert any("column 'Colour' not in data/things.csv" in f.detail
               for f in errors_of(findings))


def test_property_not_in_catalog(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(properties={"kind": {"column": "Kind"},
                                        "rogue": {"column": "Kind"}})})
    assert any("not declared in catalog" in f.detail for f in errors_of(findings))


def test_missing_source_file(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(source="data/nothing.csv")})
    assert any("source file not found" in f.detail for f in errors_of(findings))


def test_unknown_target_label(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[rel(to="Nobody")])})
    assert any("unknown target label 'Nobody'" in f.detail
               for f in errors_of(findings))


def test_prerequisites_missing_targets_refused_by_name(tmp_path):
    # Omitting the clause targets used to crash derivation far from the
    # misdeclaration; both must be refused where they were written.
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            {"type": "NEEDS", "to": "Thing", "parser": "prerequisites"}])})
    details = [f.detail for f in errors_of(findings)]
    assert any("prerequisites needs 'staged_to'" in d for d in details)
    assert any("prerequisites needs 'named_to'" in d for d in details)
    assert any("prerequisites needs a 'column'" in d for d in details)


def test_prerequisites_targets_must_be_declared_labels(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(type="NEEDS", parser="prerequisites",
                staged_to="Nobody", named_to="Thing")])})
    assert any("unknown target label 'Nobody'" in f.detail
               for f in errors_of(findings))


def test_prerequisites_stage_enum_must_be_declared(tmp_path):
    # A stage_enum naming no declared enum used to silently disable
    # stage checking — the typo is refused by name where it was written.
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(type="NEEDS", parser="prerequisites",
                staged_to="Thing", named_to="Thing", stage_enum="Kindd")])})
    assert any("unknown enum 'Kindd' in 'stage_enum'" in f.detail
               for f in errors_of(findings))


def test_prerequisites_declared_stage_enum_validates_clean(tmp_path):
    # The other side: a declared enum passes, and omitting stage_enum
    # remains a legal declaration (stage checking declined on purpose,
    # not by typo).
    for extra in ({"stage_enum": "Kind"}, {}):
        ontology, findings = checked(tmp_path, {
            "Thing": thing_spec(relationships=[
                rel(type="NEEDS", parser="prerequisites",
                    staged_to="Thing", named_to="Thing", **extra)])})
        assert ontology is not None
        assert errors_of(findings) == []


def test_prerequisites_any_target_requires_report(tmp_path):
    # Mirrors the `to: any` rule: label-agnostic resolution has no label
    # to create a placeholder in.
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(type="NEEDS", parser="prerequisites",
                staged_to="any", named_to="Thing")])})
    assert any("staged_to: any requires on_missing: report" in f.detail
               for f in errors_of(findings))


def test_prerequisites_named_any_target_requires_report(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(type="NEEDS", parser="prerequisites",
                staged_to="Thing", named_to="any")])})
    assert any("named_to: any requires on_missing: report" in f.detail
               for f in errors_of(findings))


def test_prerequisites_fully_declared_validates_clean(tmp_path):
    ontology, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(type="NEEDS", parser="prerequisites",
                staged_to="Thing", named_to="Thing")])})
    assert ontology is not None
    assert errors_of(findings) == []


def test_bad_on_missing(tmp_path):
    _, findings = checked(tmp_path, {"Thing": thing_spec()},
                          defaults={"split": "comma",
                                    "on_missing": "explode"})
    assert any("on_missing" in f.detail for f in errors_of(findings))


def test_unmatched_property_must_be_in_catalog(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(on_missing="report", unmatched_property="ghost")])})
    assert any("unmatched_property 'ghost' not in catalog" in f.detail
               for f in errors_of(findings))


def test_unknown_concept_binding(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(concept="Ghost Concept")})
    assert any("'Ghost Concept' is not a declared concept" in f.detail
               for f in errors_of(findings))


def test_unknown_instance_of_target(tmp_path):
    # A declared concept whose tower parent is not itself a declared
    # concept — the reconstructed spec must be refused by name.
    g = schema_graph({"Thing": thing_spec()})
    g.ensure_node(ARCHETYPE_LABEL, "Widget")
    g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Widget",
                             ARCHETYPE_LABEL, "Ontology"))
    g.ensure_node(ARCHETYPE_LABEL, "Nowhere")  # never declared anywhere
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Widget",
                             ARCHETYPE_LABEL, "Nowhere"))
    _, findings = checked(tmp_path, graph=g)
    assert any("instance_of 'Nowhere' is not a declared concept" in f.detail
               for f in errors_of(findings))


def test_subtypes_accepted_on_concepts(tmp_path):
    # a citizen kind under a declared concept: the SUBTYPE_OF edge
    # reconstructs as the concept spec's subtypes list, a known key
    g = schema_graph({"Thing": thing_spec()})
    g.ensure_node(ARCHETYPE_LABEL, "Widget")
    g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Widget",
                             ARCHETYPE_LABEL, "Ontology"))
    g.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Widget",
                             ARCHETYPE_LABEL, "Concept"))
    g.edges.append(make_edge("SUBTYPE_OF", "Thing", "Rock",
                             ARCHETYPE_LABEL, "Widget"))
    ontology, findings = checked(tmp_path, graph=g)
    assert ontology.concepts["Widget"]["subtypes"] == ["Rock"]
    assert not any("unknown key 'subtypes'" in f.detail
                   for f in errors_of(findings))


def test_subtypes_must_be_a_list_of_names(tmp_path):
    # the checker's spec-shape rule, exercised directly: a concept spec
    # whose subtypes is not a list of citizen names is refused
    ontology, _ = checked(tmp_path, {"Thing": thing_spec()})
    ontology.concepts["Widget"] = {"instance_of": "Concept",
                                   "subtypes": "Rock"}
    findings = check_ontology(ontology)
    assert any("'subtypes' must be a list of citizen names" in f.detail
               for f in errors_of(findings))


def test_subtypes_accepted_on_labels(tmp_path):
    # the kind-of link's PARENT may be a label-backed home, not only a
    # plain concept (a Beast catalog whose kinds include a Winged Beast
    # concept)
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(subtypes=["Rock"])})
    assert not any("unknown key 'subtypes'" in f.detail
                   for f in errors_of(findings))


def test_label_subtypes_must_be_a_list_of_names(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(subtypes="Rock")})
    assert any("'subtypes' must be a list of citizen names" in f.detail
               for f in errors_of(findings))


def test_archetype_label_reserved(tmp_path):
    _, findings = checked(tmp_path, {"Archetype": thing_spec()})
    assert any("reserved label" in f.detail for f in errors_of(findings))


def test_ordered_requires_ordered_facet(tmp_path):
    # With a kernel that lacks the Ordered facet, ordered: true on a
    # label must be a hard error.
    _, findings = checked(tmp_path, {"Thing": thing_spec(ordered=True)},
                          kernel=("Concept", "Facet"))
    assert any("'Ordered'" in f.detail for f in errors_of(findings))


def test_new_project_root_is_info_not_error(tmp_path):
    g = schema_graph({"Thing": thing_spec()})
    g.ensure_node(ARCHETYPE_LABEL, "Vibe")
    g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Vibe",
                             ARCHETYPE_LABEL, "Ontology"))
    _, findings = checked(tmp_path, graph=g)
    assert errors_of(findings) == []
    assert any("new ROOT 'Vibe'" in f.detail for f in findings)


def test_markdown_source_missing_file(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(),
        "Doc": {"source": ["docs/ghost.md"]}})
    assert any("source file not found: docs/ghost.md" in f.detail
               for f in errors_of(findings))


def test_reader_inferred_from_extension(tmp_path):
    files = dict(MINI_CSV)
    files["docs/notes.md"] = "## A Heading\n\nBody.\n"
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(),
        "Doc": {"source": ["docs/notes.md"]}}, files=files)
    assert errors_of(findings) == []


def test_unknown_reader_and_uninferrable_extension(tmp_path):
    files = dict(MINI_CSV)
    files["data/blob.xyz"] = "opaque"
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(),
        "Blob": {"source": "data/blob.xyz"},
        "Weird": {"source": "data/blob.xyz", "reader": "sheep_entrails"}},
        files=files)
    details = [f.detail for f in errors_of(findings)]
    assert any("cannot infer a reader" in d for d in details)
    assert any("unknown reader 'sheep_entrails'" in d for d in details)


def test_markdown_reader_rejects_key(tmp_path):
    files = dict(MINI_CSV)
    files["docs/notes.md"] = "## A Heading\n\nBody.\n"
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(),
        "Doc": {"source": ["docs/notes.md"], "key": "Heading"}}, files=files)
    assert any("key is only used by the csv_rows reader" in f.detail
               for f in errors_of(findings))


def test_csv_reader_rejects_multiple_files(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(
            source=["data/things.csv", "data/things.csv"])})
    assert any("csv_rows reader takes a single source file" in f.detail
               for f in errors_of(findings))


def test_from_column_requires_pieces(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            {"type": "FRIENDS_WITH", "from_column": "From"}])})
    details = [f.detail for f in errors_of(findings)]
    assert any("from_column needs a source file" in d for d in details)
    assert any("from_column needs a target column" in d for d in details)
    assert any("from_column needs a 'to' label" in d for d in details)


def test_from_column_validates_columns(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[
            rel(source="data/things.csv", from_column="Thing",
                prop_columns={"how": "Ghost"})])})
    assert any("column 'Ghost' not in data/things.csv" in f.detail
               for f in errors_of(findings))


def test_rel_parser_enum_matches_registries():
    """The RelParser enum is the single source of parser names: every
    grammar in the registry must be an enum value (grammars are hosted,
    not contained), and the graph-state handlers exist only as enum
    members."""
    from graph import grammars
    from graph.ontology import KNOWN_REL_PARSERS, RelParser

    # Parser names are bare; render/judge-only INVERTERS are registered
    # under a dotted suffix (<parser>.table / <parser>.cell) and are not
    # parser names — exclude them from the enum contract.
    registered = {name for name in grammars._REGISTRY
                  if name != "classify_clause" and "." not in name}
    # The engine ships NO grammars — whatever is registered arrived from
    # a consuming corpus (here, the suite's storybook grammar module).
    # The contract is one-way: every registered bare name must be an
    # enum value; the enum may name parsers no corpus registers.
    assert registered <= KNOWN_REL_PARSERS
    assert RelParser.SIZE_MATRIX.value in KNOWN_REL_PARSERS


def test_to_any_requires_report(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": thing_spec(relationships=[rel(to="any")])})
    assert any("to: any requires on_missing: report" in f.detail
               for f in errors_of(findings))


# -- property_tables: a second CSV keyed by the label's names ------------------

TABLE_CSV = {
    "data/things.csv": """\
        Thing,Kind,Friends
        Rock,Mineral,Stick
        Stick,Wood,Rock
        """,
    "data/weights.csv": """\
        Thing,Weight
        Rock,2.5
        Stick,0.5
        """,
}


def table_spec(table_over=None, **over):
    table = {"source": "data/weights.csv", "key": "Thing",
             "properties": {"weight": {"column": "Weight"}}}
    table.update(table_over or {})
    spec = thing_spec(
        catalog={"kind": {"type": "enum:Kind", "doc": "what it is"},
                 "weight": {"type": "float", "doc": "how heavy"}},
        relationships=[], property_tables=[table])
    spec.update(over)
    return spec


def test_property_table_checks_clean(tmp_path):
    ontology, findings = checked(tmp_path, {"Thing": table_spec()},
                                 files=TABLE_CSV)
    assert ontology is not None
    assert errors_of(findings) == []


def test_property_table_missing_source(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": table_spec({"source": "data/nothing.csv"})},
        files=TABLE_CSV)
    assert any("source file not found: data/nothing.csv" in f.detail
               for f in errors_of(findings))


def test_property_table_bad_key_column(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": table_spec({"key": "Object"})}, files=TABLE_CSV)
    assert any("key column 'Object' not in data/weights.csv" in f.detail
               for f in errors_of(findings))


def test_property_table_prop_not_in_catalog(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": table_spec({"properties": {"heft": {"column": "Weight"}}})},
        files=TABLE_CSV)
    assert any("not declared in catalog" in f.detail
               for f in errors_of(findings))


def test_property_table_unknown_key_rejected(tmp_path):
    _, findings = checked(tmp_path, {
        "Thing": table_spec({"bogus": 1})}, files=TABLE_CSV)
    assert any("unknown key 'bogus'" in f.detail for f in errors_of(findings))
