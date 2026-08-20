from graph.extract import extract
from graph.ontology import WARNING, load_ontology

FILES = {
    "data/knacks.csv": """\
        Knack,Knack Class,Spark,Prevented By
        Frost,Reactive,Blazing,
        Bolt,Active,Blazing,Mire
        Blink,Active,Bogus,Utterly Bogus Terrain
        """,
    "data/terrains.csv": """\
        Terrain,Modifier to Defense,Knacks Granted
        Mire,-4,Frost
        Windswept,x9,"Frost, Wisp"
        Frost,-1,
        """,
    "data/sparks.csv": """\
        Spark,Charge Cost
        Faint,2
        Bright,5
        Blazing,10
        """,
    "data/overlays/knacks.yaml": """\
        Frost:
          note: "designer note"
          rogue_prop: 1
        Nobody:
          note: "no such knack"
        """,
    "data/transitions.csv": """\
        From,To,Trigger
        Frost,Bolt,switcheroo
        Nope,Bolt,bad row
        """,
    "data/effects.csv": """\
        Knack,Effect,Terrain,Condition
        Frost,imposes,Mire,
        Bolt,imposes,Mire,target has Windswept
        Frost,zaps,Mire,
        Ghost,imposes,Mire,
        """,
    "data/notes.csv": """\
        Note,About
        clear one,Mire
        fuzzy one,Frost
        qualified one,Knack: Frost
        lost one,Nothingness
        """,
    "docs/guide.md": """\
        ## Overview

        The Frost and Bolt knacks meet the Mire terrain here.
        Frosty is not a mention.

        ## Empty Section
        """,
}

ONTOLOGY = """\
    version: 1
    concepts:
      # Concept/Facet/Provenance/Judgment roots and Ordered/Exclusive/Stateful
      # facets come from the engine's metaontology.
      Craft Concept: { instance_of: Concept }
      Story Concept: { instance_of: Concept }
    facets:
      # Two Segment Schemes (kernel facet): one plain with a recursive
      # fine unit, one temporal.
      Doc Structure:
        instance_of: '[Segment Scheme]'
        ordered: true
        values: [File, Heading]
      File:    { instance_of: Doc Structure }
      Heading: { instance_of: Doc Structure, recursive: true }
      Story Time:
        instance_of: '[Segment Scheme]'
        ordered: true
        temporal: true
        values: [Chapter, Turn]
      Chapter: { instance_of: Story Time }
      Turn:    { instance_of: Story Time }
    defaults: { split: comma, on_missing: placeholder }
    nodes:
      Spark:
        source: data/sparks.csv
        key: Spark
        concept: Craft Concept
        ordered: true
        catalog:
          charge_cost: { type: int, doc: "cost" }
        properties:
          charge_cost: { column: Charge Cost }
      Gem:
        values: [Ruby]
        concept: [Craft Concept, Story Concept]
      Rune:
        implicit: true
      Knack:
        doc: "What a body can do on purpose."
        source: data/knacks.csv
        key: Knack
        concept: Craft Concept
        overlay: data/overlays/knacks.yaml
        catalog:
          knack_class: { type: text, doc: "class" }
          note: { type: text, doc: "overlay note" }
          prevented_by_text: { type: text, doc: "verbatim" }
        properties:
          knack_class: { column: Knack Class }
        relationships:
          - { type: HAS_KNACK_SPARK, to: Spark, column: Spark }
          - { type: PREVENTED_BY, to: Terrain, column: Prevented By,
              on_missing: report, unmatched_property: prevented_by_text }
          - { type: SWAPS_WITH, to: Knack, source: data/transitions.csv,
              from_column: From, column: To,
              prop_columns: { trigger: Trigger } }
          - { type: EFFECTS, parser: effects_table,
              source: data/effects.csv,
              from_column: Knack, verb_column: Effect, column: Terrain,
              condition_column: Condition, to: Terrain,
              effect_label: Effect,
              verbs: [imposes] }
      Effect:
        implicit: true
      Terrain:
        source: data/terrains.csv
        key: Terrain
        catalog:
          defense_mod: { type: int, doc: "mod" }
        properties:
          defense_mod: { column: Modifier to Defense }
        relationships:
          - { type: GRANTS_KNACK, to: Knack, column: Knacks Granted }
      Note:
        source: data/notes.csv
        key: Note
        catalog:
          about_text: { type: text, doc: "unresolved" }
        relationships:
          - { type: ABOUT, to: any, column: About,
              on_missing: report, unmatched_property: about_text }
      Artifact:
        values: [docs/guide.md]
        concept: File
        fingerprint: true
      DocSection:
        source: [docs/guide.md]
        concept: Heading
        catalog:
          heading: { type: text, doc: "heading" }
          file: { type: text, doc: "path" }
        relationships:
          - { type: PART_OF,  to: Artifact, parser: part_of }
          - { type: MENTIONS, parser: mentions }
    """


def run(make_repo):
    base, path = make_repo(FILES, ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None
    graph, extract_findings = extract(ontology)
    return graph, findings + extract_findings


def details(findings, category):
    return [f.detail for f in findings if f.category == category]


def test_nodes_and_properties(make_repo):
    graph, _ = run(make_repo)
    assert graph.nodes[("Knack", "Frost")]["knack_class"] == "Reactive"
    assert graph.nodes[("Spark", "Blazing")]["charge_cost"] == 10
    assert graph.nodes[("Terrain", "Mire")]["defense_mod"] == -4


def test_plain_relationship(make_repo):
    graph, _ = run(make_repo)
    assert any(e.type == "HAS_KNACK_SPARK" and e.from_name == "Frost"
               and e.to_name == "Blazing" for e in graph.edges)


def test_placeholder_policy(make_repo):
    graph, findings = run(make_repo)
    # 'Wisp' knack doesn't exist -> placeholder node + edge + warning
    assert graph.nodes[("Knack", "Wisp")] == {"placeholder": True}
    assert any(e.to_name == "Wisp" for e in graph.edges)
    assert any("Wisp" in d for d in details(findings, "dangling-ref"))


def test_report_policy_keeps_verbatim(make_repo):
    graph, findings = run(make_repo)
    # 'Utterly Bogus Terrain' -> no node, no edge, verbatim property
    assert ("Terrain", "Utterly Bogus Terrain") not in graph.nodes
    assert not any(e.to_name == "Utterly Bogus Terrain" for e in graph.edges)
    assert (graph.nodes[("Knack", "Blink")]["prevented_by_text"]
            == "Utterly Bogus Terrain")
    assert any("Utterly Bogus Terrain" in d
               for d in details(findings, "dangling-ref"))


# The free-text prerequisite case from the source suite (a cell like
# "<Gem> at <grade> or higher" plus a "<property> clause") is DROPPED
# here: it works only because the resident corpus's grammar module parses
# those corpus-specific prose patterns and the extractor hard-wires the
# target labels/enum they resolve to. It cannot be expressed on agnostic
# vocabulary without an engine change, so no successor is authored.


def test_missing_ordered_ref_is_dangling(make_repo):
    graph, findings = run(make_repo)
    # 'Bogus' spark -> dangling ref (Spark nodes come from sparks.csv)
    assert any("'Bogus'" in d for d in details(findings, "dangling-ref"))
    assert graph.nodes[("Spark", "Bogus")] == {"placeholder": True}


def test_type_conversion_warning(make_repo):
    graph, findings = run(make_repo)
    # 'x9' defense mod is not an int -> warning, property omitted
    assert "defense_mod" not in graph.nodes[("Terrain", "Windswept")]
    assert any("x9" in d for d in details(findings, "type-conversion"))


def test_overlay_merge(make_repo):
    graph, findings = run(make_repo)
    assert graph.nodes[("Knack", "Frost")]["note"] == "designer note"
    assert any("rogue_prop" in d for d in details(findings, "catalog-violation"))
    assert any("'Nobody'" in d for d in details(findings, "dangling-ref"))


def test_no_errors_only_warnings(make_repo):
    _, findings = run(make_repo)
    assert all(f.severity in (WARNING, "info") for f in findings)


def edges_of(graph, rel_type):
    return {(e.from_label, e.from_name, e.to_label, e.to_name)
            for e in graph.edges if e.type == rel_type}


class TestProseAndTables:
    def test_doc_sections_created(self, make_repo):
        graph, _ = run(make_repo)
        node = graph.nodes[("DocSection", "guide § Overview")]
        assert node["heading"] == "Overview"
        assert node["file"] == "docs/guide.md"
        assert ("DocSection", "guide § Empty Section") in graph.nodes

    def test_part_of_artifact(self, make_repo):
        graph, _ = run(make_repo)
        assert ("DocSection", "guide § Overview",
                "Artifact", "docs/guide.md") in edges_of(graph, "PART_OF")

    def test_mentions_exact_and_bounded(self, make_repo):
        graph, _ = run(make_repo)
        mentions = edges_of(graph, "MENTIONS")
        source = ("DocSection", "guide § Overview")
        assert (*source, "Knack", "Frost") in mentions
        assert (*source, "Knack", "Bolt") in mentions
        assert (*source, "Terrain", "Mire") in mentions
        # "Frosty" must not match Frost (letter boundary); empty section
        # mentions nothing
        assert not [e for e in mentions
                    if e[:2] == ("DocSection", "guide § Empty Section")]

    def test_edge_table_relationship(self, make_repo):
        graph, findings = run(make_repo)
        swaps = [e for e in graph.edges if e.type == "SWAPS_WITH"]
        assert [(e.from_name, e.to_name, dict(e.props)["trigger"])
                for e in swaps] == [("Frost", "Bolt", "switcheroo")]
        # unknown from-node 'Nope' is reported, row skipped
        assert any("'Nope'" in d for d in details(findings, "dangling-ref"))


class TestEffectsTable:
    def test_every_row_reifies_uniformly(self, make_repo):
        graph, _ = run(make_repo)
        # unconditional rows are Effect nodes too (designer ruling: uniform)
        node = graph.nodes[("Effect", "Frost: imposes Mire")]
        assert node["verb"] == "imposes"
        assert "condition" not in node
        assert ("Knack", "Frost", "Effect", "Frost: imposes Mire") in \
            edges_of(graph, "HAS_EFFECT")
        # no direct verb edges are emitted by the effects table
        assert ("Knack", "Frost", "Terrain", "Mire") not in edges_of(
            graph, "IMPOSES_TERRAIN")

    def test_conditional_row_reifies(self, make_repo):
        graph, _ = run(make_repo)
        node = graph.nodes[("Effect", "Bolt: imposes Mire")]
        assert node["verb"] == "imposes"
        assert node["condition"] == "target has Windswept"
        assert ("Knack", "Bolt", "Effect", "Bolt: imposes Mire") in \
            edges_of(graph, "HAS_EFFECT")
        assert ("Effect", "Bolt: imposes Mire",
                "Terrain", "Mire") in edges_of(graph, "TARGETS")

    def test_condition_references_scanned(self, make_repo):
        graph, _ = run(make_repo)
        refs = edges_of(graph, "REFERENCES")
        assert ("Effect", "Bolt: imposes Mire",
                "Terrain", "Windswept") in refs

    def test_unknown_verb_and_unknown_source_reported(self, make_repo):
        _, findings = run(make_repo)
        assert any("unknown effect verb 'zaps'" in d
                   for d in details(findings, "unparsed-cell"))
        assert any("unknown Knack 'Ghost'" in d
                   for d in details(findings, "dangling-ref"))


class TestAnyResolution:
    def test_unique_name_resolves_across_labels(self, make_repo):
        graph, _ = run(make_repo)
        assert ("Note", "clear one", "Terrain", "Mire") in edges_of(
            graph, "ABOUT")

    def test_ambiguous_name_reports_and_parks(self, make_repo):
        graph, findings = run(make_repo)
        assert not [e for e in edges_of(graph, "ABOUT")
                    if e[:2] == ("Note", "fuzzy one")]
        assert graph.nodes[("Note", "fuzzy one")]["about_text"] == "Frost"
        assert any("ambiguous (Knack, Terrain)" in d
                   for d in details(findings, "dangling-ref"))

    def test_qualifier_disambiguates(self, make_repo):
        graph, _ = run(make_repo)
        assert ("Note", "qualified one", "Knack", "Frost") in edges_of(
            graph, "ABOUT")

    def test_missing_name_reports(self, make_repo):
        graph, findings = run(make_repo)
        assert graph.nodes[("Note", "lost one")]["about_text"] == "Nothingness"
        assert any("no node named 'Nothingness'" in d
                   for d in details(findings, "dangling-ref"))


class TestMetamodel:
    def test_archetype_tower(self, make_repo):
        graph, _ = run(make_repo)
        # kernel roots + library facets arrive from the engine metaontology
        for concept in ["Concept", "Facet", "Provenance", "Judgment",
                        "Ordered", "Exclusive", "Stateful",
                        "Craft Concept"]:
            assert ("Archetype", concept) in graph.nodes
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "Craft Concept", "Archetype", "Concept") in instance
        assert ("Archetype", "Ordered", "Archetype", "Facet") in instance
        # Kernel roots are self-grounded: no outgoing INSTANCE_OF
        for root in ["Concept", "Facet", "Provenance", "Judgment"]:
            assert not [e for e in instance if e[:2] == ("Archetype", root)]

    def test_kernel_docs_become_properties(self, make_repo):
        graph, _ = run(make_repo)
        assert "subject matter" in graph.nodes[("Archetype", "Concept")]["doc"]
        assert "ladder" in graph.nodes[("Archetype", "Ordered")]["doc"]

    def test_label_docs_land_on_the_archetype(self, make_repo):
        # label-level knowledge belongs on the graph, not in YAML comments
        graph, _ = run(make_repo)
        assert graph.nodes[("Archetype", "Knack")]["doc"] == \
            "What a body can do on purpose."

    def test_value_to_label_to_concept_chain(self, make_repo):
        graph, _ = run(make_repo)
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Knack", "Frost", "Archetype", "Knack") in instance
        assert ("Archetype", "Knack", "Archetype", "Craft Concept") in instance

    def test_placeholders_are_instances_too(self, make_repo):
        graph, _ = run(make_repo)
        assert ("Knack", "Wisp", "Archetype", "Knack") in edges_of(
            graph, "INSTANCE_OF")

    def test_subtype_edges(self, make_repo):
        # `subtypes:` on a concept = genuine taxonomy: the named citizens
        # get SUBTYPE_OF edges up to the concept's Archetype. 'Frost' is
        # both a Knack and a Terrain in this fixture, so the qualified
        # form is required; the unknown name drops with a warning.
        ontology_yaml = ONTOLOGY.replace(
            "Story Concept: { instance_of: Concept }",
            "Story Concept: { instance_of: Concept }\n"
            "      Frost Family:\n"
            "        instance_of: Craft Concept\n"
            "        subtypes: ['Knack: Frost', Vanished Thing]")
        base, path = make_repo(FILES, ontology_yaml)
        ontology, findings = load_ontology(path, base)
        assert ontology is not None
        graph, extract_findings = extract(ontology)
        assert ("Knack", "Frost", "Archetype", "Frost Family") in edges_of(
            graph, "SUBTYPE_OF")
        assert any("SUBTYPE_OF edge dropped" in f.detail
                   for f in extract_findings if f.severity == WARNING)

    def test_subtype_edges_on_labels(self, make_repo):
        # `subtypes:` on a node LABEL = the same genuine taxonomy with a
        # label-backed parent: the named citizens get SUBTYPE_OF edges up
        # to the label's Archetype. Unknown names drop with a warning,
        # like the concept-entry form.
        ontology_yaml = ONTOLOGY.replace(
            "        concept: [Craft Concept, Story Concept]",
            "        concept: [Craft Concept, Story Concept]\n"
            "        subtypes: ['Knack: Frost', Vanished Thing]")
        base, path = make_repo(FILES, ontology_yaml)
        ontology, findings = load_ontology(path, base)
        assert ontology is not None
        graph, extract_findings = extract(ontology)
        assert ("Knack", "Frost", "Archetype", "Gem") in edges_of(
            graph, "SUBTYPE_OF")
        assert any("SUBTYPE_OF edge dropped" in f.detail
                   for f in extract_findings if f.severity == WARNING)

    def test_unbound_label_gets_no_archetype(self, make_repo):
        graph, _ = run(make_repo)
        # Terrain has no concept: binding in this fixture
        assert ("Archetype", "Terrain") not in graph.nodes

    def test_ordered_ranks(self, make_repo):
        graph, _ = run(make_repo)
        ranks = {name: props.get("rank")
                 for (label, name), props in graph.nodes.items()
                 if label == "Spark" and not props.get("placeholder")}
        assert ranks == {"Faint": 0, "Bright": 1, "Blazing": 2}
        # placeholder Spark ('Bogus') gets no rank
        assert "rank" not in graph.nodes[("Spark", "Bogus")]

    def test_ladder_edges_bidirectional(self, make_repo):
        graph, _ = run(make_repo)
        precedes = edges_of(graph, "PRECEDES")
        follows = edges_of(graph, "FOLLOWS")
        # the kernel's own Completeness ladder rides along on Archetype nodes
        assert {e for e in precedes if e[0] == "Spark"} == {
            ("Spark", "Faint", "Spark", "Bright"),
            ("Spark", "Bright", "Spark", "Blazing"),
        }
        assert follows == {(fl, fn, tl, tn)
                           for (tl, tn, fl, fn) in precedes}

    def test_concept_list_multi_classification(self, make_repo):
        graph, _ = run(make_repo)
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "Gem", "Archetype", "Craft Concept") in instance
        assert ("Archetype", "Gem", "Archetype", "Story Concept") in instance
        assert ("Gem", "Ruby", "Archetype", "Gem") in instance

    def test_ordered_facet(self, make_repo):
        graph, _ = run(make_repo)
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "Spark", "Archetype", "Craft Concept") in instance
        assert ("Archetype", "Spark", "Archetype", "Ordered") in instance

    def test_segment_scheme_citizen_chain(self, make_repo):
        # scheme -> kernel facet, segment type -> scheme, label -> type
        graph, _ = run(make_repo)
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "[Segment Scheme]",
                "Archetype", "Facet") in instance
        assert ("Archetype", "Doc Structure",
                "Archetype", "[Segment Scheme]") in instance
        assert ("Archetype", "Heading",
                "Archetype", "Doc Structure") in instance
        assert ("Archetype", "DocSection", "Archetype", "Heading") in instance
        assert ("Archetype", "Artifact", "Archetype", "File") in instance

    def test_segment_scheme_ladder_is_coarse_to_fine(self, make_repo):
        graph, _ = run(make_repo)
        assert graph.nodes[("Archetype", "File")]["rank"] == 0
        assert graph.nodes[("Archetype", "Heading")]["rank"] == 1
        assert ("Archetype", "File",
                "Archetype", "Heading") in edges_of(graph, "PRECEDES")

    def test_temporal_scheme_flag_is_queryable(self, make_repo):
        # a time axis says so on its citizen; plain schemes carry no flag
        graph, _ = run(make_repo)
        assert graph.nodes[("Archetype", "Story Time")].get("temporal") is True
        assert "temporal" not in graph.nodes[("Archetype", "Doc Structure")]

    def test_recursive_segment_type_flag_is_queryable(self, make_repo):
        # a self-nesting segment type says so; others carry no flag
        graph, _ = run(make_repo)
        assert graph.nodes[("Archetype", "Heading")].get("recursive") is True
        assert "recursive" not in graph.nodes[("Archetype", "File")]

    def test_artifact_fingerprint_is_the_content_hash(self, make_repo):
        # fingerprint: true stamps the durable identity anchor for
        # artifact + span citations (canon thinning)
        import hashlib
        import textwrap
        graph, _ = run(make_repo)
        expected = hashlib.sha256(
            textwrap.dedent(FILES["docs/guide.md"]).encode("utf-8"))
        assert graph.nodes[("Artifact", "docs/guide.md")]["fingerprint"] \
            == expected.hexdigest()

    def test_graph_answers_what_built_it(self, make_repo):
        # the self-description slice: metaontology + ontology as queryable
        # schema anchors with version and content fingerprint
        graph, _ = run(make_repo)
        import re
        meta = graph.nodes[("Archetype", "Metaontology")]
        assert re.match(r"^\d+\.\d+\.\d+$", meta["version"])  # semver;
        # the exact value is the version ledger's business
        assert len(meta["fingerprint"]) == 64
        proj = graph.nodes[("Archetype", "Ontology")]
        assert proj["version"] == 1  # the mini-repo fixture's own version
        assert len(proj["fingerprint"]) == 64
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "Metaontology",
                "Archetype", "Provenance") in instance
        assert ("Archetype", "Ontology",
                "Archetype", "Provenance") in instance

    def test_every_schema_citizen_declares_its_layer(self, make_repo):
        # the two-layer doctrine, queryable: kernel names point at
        # Metaontology, project vocabulary at Ontology
        graph, _ = run(make_repo)
        declared = edges_of(graph, "DECLARED_IN")
        assert ("Archetype", "Concept",
                "Archetype", "Metaontology") in declared
        assert ("Archetype", "[Segment Scheme]",
                "Archetype", "Metaontology") in declared
        assert ("Archetype", "Craft Concept",
                "Archetype", "Ontology") in declared
        assert ("Archetype", "Doc Structure",
                "Archetype", "Ontology") in declared
        assert ("Archetype", "Knack",
                "Archetype", "Ontology") in declared
        # the layers themselves are typed and ranked (Schema Layer)
        instance = edges_of(graph, "INSTANCE_OF")
        assert ("Archetype", "Metaontology",
                "Archetype", "[Schema Layer]") in instance
        assert ("Archetype", "Ontology",
                "Archetype", "[Schema Layer]") in instance
        assert graph.nodes[("Archetype", "Metaontology")]["rank"] == 0
        assert graph.nodes[("Archetype", "Ontology")]["rank"] == 1
        # nothing kernel-side leaks into the project layer
        assert not [e for e in declared
                    if e[1] in ("Concept", "Facet", "Provenance",
                                "Judgment", "Ordered", "[Segment Scheme]")
                    and e[3] != "Metaontology"]

    def test_no_duplicate_instance_edges(self, make_repo):
        graph, _ = run(make_repo)
        instance_edges = [e for e in graph.edges if e.type == "INSTANCE_OF"]
        assert len(instance_edges) == len(set(instance_edges))


class TestPropertyTables:
    """A second CSV keyed by a label's names contributes properties to
    already-built nodes (the designer's data keeps its shape)."""

    FILES = {
        "data/things.csv": """\
            Thing,Kind
            Rock,Mineral
            Stick,Wood
            """,
        "data/weights.csv": """\
            Thing,Weight
            Rock,2.5
            Stick,—
            Boulder,9.9
            """,
    }
    ONTOLOGY = """\
        version: 1
        nodes:
          Thing:
            source: data/things.csv
            key: Thing
            aliases: { Pebble: Rock }
            catalog:
              kind:   { type: text,  doc: "what it is" }
              weight: { type: float, doc: "how heavy" }
            properties:
              kind: { column: Kind }
            property_tables:
              - source: data/weights.csv
                key: Thing
                properties:
                  weight: { column: Weight }
        """

    def build(self, make_repo, files=None):
        base, path = make_repo(files or self.FILES, self.ONTOLOGY)
        ontology, findings = load_ontology(path, base)
        assert ontology is not None
        graph, extract_findings = extract(ontology)
        return graph, findings + extract_findings

    def test_props_land_on_existing_nodes(self, make_repo):
        graph, _ = self.build(make_repo)
        assert graph.nodes[("Thing", "Rock")]["weight"] == 2.5
        assert graph.nodes[("Thing", "Rock")]["kind"] == "Mineral"

    def test_empty_marker_contributes_nothing(self, make_repo):
        graph, _ = self.build(make_repo)
        assert "weight" not in graph.nodes[("Thing", "Stick")]

    def test_unknown_name_warns_and_skips(self, make_repo):
        graph, findings = self.build(make_repo)
        assert ("Thing", "Boulder") not in graph.nodes
        assert any("property-table row names an unknown Thing 'Boulder'"
                   in f.detail for f in findings if f.severity == WARNING)

    def test_key_resolves_through_aliases(self, make_repo):
        files = dict(self.FILES)
        files["data/weights.csv"] = files["data/weights.csv"].replace(
            "Rock,2.5", "Pebble,2.5")
        graph, _ = self.build(make_repo, files)
        assert graph.nodes[("Thing", "Rock")]["weight"] == 2.5


class TestDerive:
    def test_derive_recomputes_extraction_exactly(self, make_repo):
        # THE split's correctness bar: derive over extract's own output
        # reproduces it byte-for-byte — one derivation codepath, so
        # apply-then-derive equals a from-sources build
        from graph.export import serialize
        from graph.extract import derive, extract, strip_derived
        base, path = make_repo(FILES, ONTOLOGY)
        ontology, _ = load_ontology(path, base)
        built, _ = extract(ontology)
        rederived, findings = derive(ontology, built)
        assert serialize(rederived) == serialize(built)

    def test_strip_keeps_ground_edges_touching_machine_nodes(self, make_repo):
        # a Judgment ABOUT a concept is ground, and so is its Archetype
        # endpoint — edge and endpoint both survive the strip.
        # Instance-level INSTANCE_OF still re-derives and is stripped; the
        # schema tower (Archetype -> Archetype) is ground and stays.
        from graph.extract import strip_derived
        graph, _ = run(make_repo)
        about = [e for e in graph.edges if e.type == "ABOUT"
                 and e.to_label == "Archetype"]
        stripped = strip_derived(graph)
        for edge in about:
            assert edge in stripped.edges
        instance_level = [e for e in stripped.edges
                          if e.type == "INSTANCE_OF"
                          and e.from_label != "Archetype"]
        assert instance_level == []
        assert any(e.type == "INSTANCE_OF"
                   and e.from_label == "Archetype"
                   for e in stripped.edges)

    def test_rank_is_ground_and_survives_the_strip(self, make_repo):
        from graph.extract import strip_derived
        graph, _ = run(make_repo)
        stripped = strip_derived(graph)
        assert stripped.nodes[("Spark", "Faint")]["rank"] == 0


def test_prerequisites_edges_via_registered_grammar(make_repo):
    # The engine holds no prerequisite vocabulary: the rel spec declares
    # where parsed clauses point (staged_to / named_to / stage_enum) and
    # the corpus's registered grammar does the parsing — restores the
    # coverage dropped when the resident grammar left the engine.
    files = {"data/tools.csv":
             'Tool,Requires\n'
             'Drill,"Welding at Novice or higher. Needs: Sharp. '
             'hum quietly first"\n'}
    ontology_src = """\
    version: "1"
    enums:
      Mastery: { values: [Novice, Adept] }
    concepts:
      Craft Concept: { instance_of: Concept }
    nodes:
      Skill:
        values: [Welding]
        concept: Craft Concept
      Trait:
        values: [Sharp]
        concept: Craft Concept
      Tool:
        source: data/tools.csv
        key: Tool
        concept: Craft Concept
        catalog:
          note_text: { type: text, doc: "unmatched remainder" }
        relationships:
          - type: NEEDS
            to: any
            column: Requires
            parser: prerequisites
            staged_to: Skill
            named_to: Trait
            stage_enum: Mastery
            unmatched_property: note_text
    """
    base_dir, path = make_repo(files, ontology_src)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    graph, findings = extract(ontology)
    needs = {(e.to_label, e.to_name): dict(e.props)
             for e in graph.edges if e.type == "NEEDS"}
    assert needs[("Skill", "Welding")] == {"min_stage": "Novice"}
    assert needs[("Trait", "Sharp")] == {}
    assert graph.nodes[("Tool", "Drill")]["note_text"] == "hum quietly first"


def test_prerequisites_stage_outside_declared_enum_warns(make_repo):
    files = {"data/tools.csv":
             'Tool,Requires\nDrill,Welding at Wizardly or higher\n'}
    ontology_src = """\
    version: "1"
    enums:
      Mastery: { values: [Novice, Adept] }
    concepts:
      Craft Concept: { instance_of: Concept }
    nodes:
      Skill:
        values: [Welding]
        concept: Craft Concept
      Tool:
        source: data/tools.csv
        key: Tool
        concept: Craft Concept
        relationships:
          - type: NEEDS
            to: any
            column: Requires
            parser: prerequisites
            staged_to: Skill
            named_to: Skill
            stage_enum: Mastery
    """
    base_dir, path = make_repo(files, ontology_src)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    _, findings = extract(ontology)
    assert any("'Wizardly' not in" in f.detail and "Mastery" in f.detail
               for f in findings)
