from graph.ontology import ERROR, load_ontology

MINI_CSV = {
    "data/things.csv": """\
        Thing,Kind,Friends
        Rock,Mineral,Stick
        Stick,Wood,Rock
        """,
}

VALID_ONTOLOGY = """\
    version: 1
    enums:
      Kind: { values: [Mineral, Wood] }
    defaults: { split: comma, on_missing: placeholder }
    nodes:
      Thing:
        source: data/things.csv
        key: Thing
        catalog:
          kind: { type: "enum:Kind", doc: "what it is" }
        properties:
          kind: { column: Kind }
        relationships:
          - { type: FRIENDS_WITH, to: Thing, column: Friends }
    """


def errors_of(findings):
    return [f for f in findings if f.severity == ERROR]


def test_valid_ontology_loads(make_repo):
    base, path = make_repo(MINI_CSV, VALID_ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []
    assert "Thing" in ontology.nodes


def test_unknown_top_level_key(make_repo):
    base, path = make_repo(
        MINI_CSV, VALID_ONTOLOGY.replace("version: 1", "version: 1\n    bogus: 1"))
    _, findings = load_ontology(path, base)
    assert any("unknown top-level key 'bogus'" in f.detail
               for f in errors_of(findings))


def test_unknown_parser(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: FRIENDS_WITH, to: Thing, column: Friends, parser: nope }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("unknown parser 'nope'" in f.detail for f in errors_of(findings))


def test_missing_column(make_repo):
    bad = VALID_ONTOLOGY.replace("column: Kind }", "column: Colour }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("column 'Colour' not in data/things.csv" in f.detail
               for f in errors_of(findings))


def test_property_not_in_catalog(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "properties:\n", "properties:\n          rogue: { column: Kind }\n")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("not declared in catalog" in f.detail for f in errors_of(findings))


def test_missing_source_file(make_repo):
    bad = VALID_ONTOLOGY.replace("data/things.csv", "data/nothing.csv")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("source file not found" in f.detail for f in errors_of(findings))


def test_unknown_target_label(make_repo):
    bad = VALID_ONTOLOGY.replace("to: Thing", "to: Nobody")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("unknown target label 'Nobody'" in f.detail
               for f in errors_of(findings))


def test_prerequisites_missing_targets_refused_by_name(make_repo):
    # Omitting the clause targets used to crash extraction far from the
    # misdeclaration; both must be refused where they were written.
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: NEEDS, to: Thing, parser: prerequisites }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    details = [f.detail for f in errors_of(findings)]
    assert any("prerequisites needs 'staged_to'" in d for d in details)
    assert any("prerequisites needs 'named_to'" in d for d in details)
    assert any("prerequisites needs a 'column'" in d for d in details)


def test_prerequisites_targets_must_be_declared_labels(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: NEEDS, to: Thing, column: Friends, parser: prerequisites, "
        "staged_to: Nobody, named_to: Thing }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("unknown target label 'Nobody'" in f.detail
               for f in errors_of(findings))


def test_prerequisites_any_target_requires_report(make_repo):
    # Mirrors the `to: any` rule: label-agnostic resolution has no label
    # to create a placeholder in.
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: NEEDS, to: Thing, column: Friends, parser: prerequisites, "
        "staged_to: any, named_to: Thing }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("staged_to: any requires on_missing: report" in f.detail
               for f in errors_of(findings))


def test_prerequisites_fully_declared_validates_clean(make_repo):
    good = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: NEEDS, to: Thing, column: Friends, parser: prerequisites, "
        "staged_to: Thing, named_to: Thing }")
    base, path = make_repo(MINI_CSV, good)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []


def test_bad_on_missing(make_repo):
    bad = VALID_ONTOLOGY.replace("on_missing: placeholder",
                                 "on_missing: explode")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("on_missing" in f.detail for f in errors_of(findings))


def test_validate_refuses_extraction_over_a_broken_ontology(make_repo):
    # Extraction over a misdeclared ontology used to crash far from the
    # cause; run() must return the collated refusals with no graph.
    from graph.validate import run
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: NEEDS, to: Thing, column: Friends, parser: prerequisites }")
    base, path = make_repo(MINI_CSV, bad)
    _, graph, findings = run(base, path)
    assert graph is None
    assert any("prerequisites needs 'staged_to'" in f.detail
               for f in errors_of(findings))
    assert any("extraction skipped" in f.detail for f in findings)


def test_validate_extracts_when_the_ontology_is_clean(make_repo):
    from graph.validate import run
    base, path = make_repo(MINI_CSV, VALID_ONTOLOGY)
    _, graph, findings = run(base, path)
    assert graph is not None
    assert errors_of(findings) == []


def test_unmatched_property_must_be_in_catalog(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: FRIENDS_WITH, to: Thing, column: Friends, "
        "on_missing: report, unmatched_property: ghost }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("unmatched_property 'ghost' not in catalog" in f.detail
               for f in errors_of(findings))


def test_unknown_concept_binding(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "source: data/things.csv",
        "source: data/things.csv\n        concept: Ghost Concept")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("'Ghost Concept' is not a declared concept" in f.detail
               for f in errors_of(findings))


def test_unknown_instance_of_target(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "nodes:",
        "concepts:\n      Widget: { instance_of: Nowhere }\n    nodes:")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("instance_of 'Nowhere' is not a declared concept" in f.detail
               for f in errors_of(findings))


def test_subtypes_accepted_on_concepts(make_repo):
    good = VALID_ONTOLOGY.replace(
        "nodes:",
        "concepts:\n      Widget: { subtypes: [Rock] }\n    nodes:")
    base, path = make_repo(MINI_CSV, good)
    _, findings = load_ontology(path, base)
    assert not any("unknown key 'subtypes'" in f.detail
                   for f in errors_of(findings))


def test_subtypes_must_be_a_list_of_names(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "nodes:",
        "concepts:\n      Widget: { subtypes: Rock }\n    nodes:")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("'subtypes' must be a list of citizen names" in f.detail
               for f in errors_of(findings))


def test_subtypes_accepted_on_labels(make_repo):
    # the kind-of link's PARENT may be a label-backed home, not only a
    # plain concept (a Beast catalog whose kinds include a Winged Beast
    # concept)
    good = VALID_ONTOLOGY.replace(
        "      Thing:", "      Thing:\n        subtypes: [Rock]")
    base, path = make_repo(MINI_CSV, good)
    _, findings = load_ontology(path, base)
    assert not any("unknown key 'subtypes'" in f.detail
                   for f in errors_of(findings))


def test_label_subtypes_must_be_a_list_of_names(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "      Thing:", "      Thing:\n        subtypes: Rock")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("'subtypes' must be a list of citizen names" in f.detail
               for f in errors_of(findings))


def test_archetype_label_reserved(make_repo):
    bad = VALID_ONTOLOGY.replace("      Thing:", "      Archetype:")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("reserved label" in f.detail for f in errors_of(findings))


def test_ordered_requires_ordered_facet(make_repo):
    # With a stripped kernel that lacks the Ordered facet, ordered: true
    # must be a hard error.
    bad = VALID_ONTOLOGY.replace(
        "source: data/things.csv",
        "source: data/things.csv\n        ordered: true")
    base, path = make_repo(MINI_CSV, bad)
    stripped = base / "stripped-metaontology.yaml"
    stripped.write_text("roots:\n  Concept:\n  Facet:\n", encoding="utf-8")
    _, findings = load_ontology(path, base, metaontology_path=stripped)
    assert any("'Ordered'" in f.detail for f in errors_of(findings))


def test_kernel_names_cannot_be_redeclared(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "nodes:", "concepts:\n      Facet: {}\n    nodes:")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("provided by the engine metaontology" in f.detail
               for f in errors_of(findings))


def test_project_facet_escape_hatch(make_repo):
    good = VALID_ONTOLOGY.replace(
        "nodes:", "facets:\n      Squishy: \"how squishable it is\"\n    nodes:")
    base, path = make_repo(MINI_CSV, good)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []
    assert ontology.concepts["Squishy"]["instance_of"] == "Facet"
    assert "squishable" in ontology.concepts["Squishy"]["doc"]


def test_new_project_root_is_info_not_error(make_repo):
    rooty = VALID_ONTOLOGY.replace(
        "nodes:", "concepts:\n      Vibe: {}\n    nodes:")
    base, path = make_repo(MINI_CSV, rooty)
    _, findings = load_ontology(path, base)
    assert errors_of(findings) == []
    assert any("new ROOT 'Vibe'" in f.detail for f in findings)


def test_markdown_source_missing_file(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "nodes:",
        "nodes:\n      Doc:\n        source: [docs/ghost.md]\n")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("source file not found: docs/ghost.md" in f.detail
               for f in errors_of(findings))


def test_reader_inferred_from_extension(make_repo):
    files = dict(MINI_CSV)
    files["docs/notes.md"] = "## A Heading\n\nBody.\n"
    good = VALID_ONTOLOGY.replace(
        "nodes:", "nodes:\n      Doc:\n        source: [docs/notes.md]\n")
    base, path = make_repo(files, good)
    _, findings = load_ontology(path, base)
    assert errors_of(findings) == []


def test_unknown_reader_and_uninferrable_extension(make_repo):
    files = dict(MINI_CSV)
    files["data/blob.xyz"] = "opaque"
    bad = VALID_ONTOLOGY.replace(
        "nodes:",
        "nodes:\n"
        "      Blob:\n        source: data/blob.xyz\n"
        "      Weird:\n        source: data/blob.xyz\n"
        "        reader: sheep_entrails\n")
    base, path = make_repo(files, bad)
    _, findings = load_ontology(path, base)
    details = [f.detail for f in errors_of(findings)]
    assert any("cannot infer a reader" in d for d in details)
    assert any("unknown reader 'sheep_entrails'" in d for d in details)


def test_markdown_reader_rejects_key(make_repo):
    files = dict(MINI_CSV)
    files["docs/notes.md"] = "## A Heading\n\nBody.\n"
    bad = VALID_ONTOLOGY.replace(
        "nodes:",
        "nodes:\n      Doc:\n        source: [docs/notes.md]\n"
        "        key: Heading\n")
    base, path = make_repo(files, bad)
    _, findings = load_ontology(path, base)
    assert any("key is only used by the csv_rows reader" in f.detail
               for f in errors_of(findings))


def test_csv_reader_rejects_multiple_files(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "source: data/things.csv",
        "source: [data/things.csv, data/things.csv]")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("csv_rows reader takes a single source file" in f.detail
               for f in errors_of(findings))


def test_from_column_requires_pieces(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: FRIENDS_WITH, from_column: From }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    details = [f.detail for f in errors_of(findings)]
    assert any("from_column needs a source file" in d for d in details)
    assert any("from_column needs a target column" in d for d in details)
    assert any("from_column needs a 'to' label" in d for d in details)


def test_from_column_validates_columns(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: FRIENDS_WITH, to: Thing, source: data/things.csv, "
        "from_column: Thing, column: Friends, "
        "prop_columns: { how: Ghost } }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
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


def test_to_any_requires_report(make_repo):
    bad = VALID_ONTOLOGY.replace(
        "{ type: FRIENDS_WITH, to: Thing, column: Friends }",
        "{ type: FRIENDS_WITH, to: any, column: Friends }")
    base, path = make_repo(MINI_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("to: any requires on_missing: report" in f.detail
               for f in errors_of(findings))


def test_unreadable_yaml(tmp_path):
    path = tmp_path / "ontology.yaml"
    path.write_text("nodes: [unclosed", encoding="utf-8")
    ontology, findings = load_ontology(path, tmp_path)
    assert ontology is None
    assert errors_of(findings)


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

TABLE_ONTOLOGY = """\
    version: 1
    enums:
      Kind: { values: [Mineral, Wood] }
    defaults: { split: comma, on_missing: placeholder }
    nodes:
      Thing:
        source: data/things.csv
        key: Thing
        catalog:
          kind:   { type: "enum:Kind", doc: "what it is" }
          weight: { type: float, doc: "how heavy" }
        properties:
          kind: { column: Kind }
        property_tables:
          - source: data/weights.csv
            key: Thing
            properties:
              weight: { column: Weight }
    """


def test_property_table_loads_clean(make_repo):
    base, path = make_repo(TABLE_CSV, TABLE_ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    assert errors_of(findings) == []


def test_property_table_missing_source(make_repo):
    bad = TABLE_ONTOLOGY.replace("data/weights.csv", "data/nothing.csv")
    base, path = make_repo(TABLE_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("source file not found: data/nothing.csv" in f.detail
               for f in errors_of(findings))


def test_property_table_bad_key_column(make_repo):
    bad = TABLE_ONTOLOGY.replace("key: Thing\n            properties",
                                 "key: Object\n            properties")
    base, path = make_repo(TABLE_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("key column 'Object' not in data/weights.csv" in f.detail
               for f in errors_of(findings))


def test_property_table_prop_not_in_catalog(make_repo):
    bad = TABLE_ONTOLOGY.replace("weight: { column: Weight }",
                                 "heft: { column: Weight }")
    base, path = make_repo(TABLE_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("not declared in catalog" in f.detail
               for f in errors_of(findings))


def test_property_table_unknown_key_rejected(make_repo):
    bad = TABLE_ONTOLOGY.replace("- source: data/weights.csv",
                                 "- source: data/weights.csv\n"
                                 "            bogus: 1")
    base, path = make_repo(TABLE_CSV, bad)
    _, findings = load_ontology(path, base)
    assert any("unknown key 'bogus'" in f.detail for f in errors_of(findings))
