"""Rules-as-programs: parse/lift/walk/render units, completeness matrix,
signature projection, extractor integration, branches-on-subject, and
outcome binding — all over a self-contained storybook corpus (no real
docs, no approved-table answer keys; those belong to a project's own
knowledge base and are checked elsewhere)."""

import hashlib
import textwrap

from graph.extract import extract
from graph.ontology import ERROR, INFO, WARNING, load_ontology
from graph.parsers import markdown_sections
from graph.procedures import (bind_outcomes, branches_on_subject, lift,
                              parse_procedure, render_markdown,
                              walk_transitions)

PROGRAM = """\
procedure: Wilt
specified_in: rules § Overview
inputs:
  beast: who wilts
  ward:
    description: a warding bloom
    required: false
    when_absent: no shelter applies
outputs:
  beast: with Condition and Reserves updated
precondition: the frost arrived
possible_outcomes:
  Shrugged Off:
    ends: still lively
    guarantee: fails-with-side-effects
  Withered:
    ends: drooping
    guarantee: fails-clean
  Lost For Good:
    ends: all gone
    guarantee: fails-with-side-effects
steps:
  - branch on: beast's Condition
    cases:
      Fresh:
        - roll: a vigor check
        - when: Sap > 0
          then:
            - spend: Sap by 1
            - stop: still lively
        - otherwise:
            - become: Weary
            - continue: resolve as Weary
      Weary:
        - when: it is severe
          then:
            - call: Tend for the beast
            - become: Spent
            - stop: { outcome: Lost For Good, note: all gone }
          otherwise:
            - stop: drooping
"""

TEND = """\
procedure: Tend
completeness: cited
specified_in: rules § Overview
description: mends beasts
"""

FILES = {
    "data/conditions.csv": """\
        Condition
        Fresh
        Weary
        Spent
        """,
    "data/reserves.csv": """\
        Reserve
        Sap
        Bounty
        """,
    "docs/rules.md": """\
        ## Overview

        Wilts happen to every Sprite daily in the Bramble Woods.
        A sprite in the Fresh Condition is no safer, and pays their Bounties in Sap

        Sprites endure. The Thicket claims the unwary near the Dread Hollow.
        """,
    "data/procedures/test.yaml": PROGRAM,
    "data/procedures/tend.yaml": TEND,
}

ONTOLOGY = """\
    version: 1
    concepts:
      Tale Concept: { instance_of: Concept }
      Bramble Wood:
        instance_of: Tale Concept
        stub: true
        surface_forms: [Thicket]
        doc: "recognized, unmodeled"
    nodes:
      Condition:
        source: data/conditions.csv
        key: Condition
        concept: [Tale Concept, Exclusive, Stateful]
      Reserve:
        source: data/reserves.csv
        key: Reserve
        concept: Tale Concept
      "[Artifact]":
        values: [docs/rules.md]
      DocSection:
        source: [docs/rules.md]
        catalog:
          heading: { type: text, doc: "heading" }
          file:    { type: text, doc: "path" }
        relationships:
          - { type: PART_OF, to: "[Artifact]", parser: part_of }
      "[Procedure]":
        source: [data/procedures/test.yaml, data/procedures/tend.yaml]
        reader: procedure_yaml
        concept: "[Procedure]"
    """


# -- parse validation ---------------------------------------------------------

def errors_of(text):
    _, errors = parse_procedure(textwrap.dedent(text))
    return " | ".join(detail for _, detail in errors)


def test_parse_clean_program():
    spec, errors = parse_procedure(PROGRAM)
    assert errors == [] and spec is not None
    assert spec["procedure"] == "Wilt"


def test_unknown_top_key_reported():
    assert "'bogus' is not a valid key for a transcribed procedure" in \
        errors_of("""\
        procedure: X
        bogus: y
        steps: [ {stop: done} ]
        """)


def test_unknown_verb_reported():
    assert "unknown action verb 'zap'" in errors_of("""\
        procedure: X
        steps: [ {zap: pow} ]
        """)


def test_when_needs_then():
    assert "needs 'then'" in errors_of("""\
        procedure: X
        steps: [ {when: sunny} ]
        """)


def test_otherwise_must_follow_when():
    assert "must follow a when" in errors_of("""\
        procedure: X
        steps:
          - stop: done
          - otherwise: [ {stop: nope} ]
        """)


def test_action_takes_single_verb():
    assert "single verb key" in errors_of("""\
        procedure: X
        steps: [ {spend: a, become: b} ]
        """)


# -- completeness matrix --------------------------------------------------------

def test_unknown_completeness():
    assert "unknown completeness 'mystic'" in errors_of("""\
        procedure: X
        completeness: mystic
        """)


def test_no_steps_no_completeness():
    assert "needs steps (transcribed) or an explicit" in errors_of("""\
        procedure: X
        """)


def test_attested_forbids_steps():
    assert "'steps' is not a valid key for a attested procedure" in \
        errors_of("""\
        procedure: X
        completeness: attested
        steps: [ {stop: done} ]
        """)


def test_cited_forbids_inputs():
    assert "'inputs' is not a valid key for a cited procedure" in \
        errors_of("""\
        procedure: X
        completeness: cited
        inputs: { a: b }
        """)


def test_transcribed_forbids_asserted_sections():
    assert "'reads' is not a valid key for a transcribed procedure" in \
        errors_of("""\
        procedure: X
        reads: { closed: true }
        steps: [ {stop: done} ]
        """)


def test_attested_sections_and_outcomes_validate():
    text = """\
        procedure: X
        completeness: attested
        reads: { closed: maybe }
        mutates: { bogus: 1 }
        possible_outcomes:
          Done: { guarantee: sideways, ends: nope }
        """
    errs = errors_of(text)
    assert "'closed' must be true or false" in errs
    assert "unknown key 'bogus'" in errs
    assert "unknown guarantee 'sideways'" in errs
    assert "unknown attested-outcome key 'ends'" in errs


# -- inputs -------------------------------------------------------------------

def test_input_mapping_validated():
    errs = errors_of("""\
        procedure: X
        inputs:
          a: { required: false }
          b: { description: fine, bogus: 1 }
        steps: [ {stop: done} ]
        """)
    assert "input mapping needs a description" in errs
    assert "unknown input key 'bogus'" in errs


# -- possible_outcomes bijection ----------------------------------------------

def test_unclaimed_stop_is_error():
    assert "stop not claimed by any possible_outcome" in errors_of("""\
        procedure: X
        possible_outcomes:
          Done: { ends: done, guarantee: fails-clean }
        steps:
          - stop: done
          - stop: surprise ending
        """)


def test_outcome_claiming_nothing_is_error():
    assert "outcome claims no stop" in errors_of("""\
        procedure: X
        possible_outcomes:
          Done:  { ends: done, guarantee: fails-clean }
          Ghost: { ends: never happens, guarantee: fails-clean }
        steps: [ {stop: done} ]
        """)


def test_stop_claimed_twice_is_error():
    assert "claimed by multiple outcomes" in errors_of("""\
        procedure: X
        possible_outcomes:
          Done:  { ends: done, guarantee: fails-clean }
          Again: { ends: done, guarantee: fails-clean }
        steps: [ {stop: done} ]
        """)


def test_outcome_needs_guarantee():
    assert "outcome needs a guarantee" in errors_of("""\
        procedure: X
        possible_outcomes:
          Done: { ends: done }
        steps: [ {stop: done} ]
        """)


def test_tagged_stop_needs_note():
    assert "a tagged stop needs 'note' prose" in errors_of("""\
        procedure: X
        steps: [ {stop: {outcome: Done}} ]
        """)


# -- lift ---------------------------------------------------------------------

def lifted_program():
    spec, errors = parse_procedure(PROGRAM)
    assert not errors
    return spec, lift(spec)


def edge_set(lifted, edge_type):
    return {(f, t) for (etype, f, t) in lifted.edges if etype == edge_type}


def test_lift_step_names_and_kinds():
    _, lifted = lifted_program()
    by_name = {step.name: step for step in lifted.steps}
    assert lifted.first_step == "Wilt §1"
    assert by_name["Wilt §1"].kind == "branch"
    assert by_name["Wilt §1.Fresh"].kind == "case"
    assert by_name["Wilt §1.Fresh.1"].kind == "roll"
    assert by_name["Wilt §1.Fresh.2"].condition == "Sap > 0"
    assert by_name["Wilt §1.Fresh.2.1"].text == "spend Sap by 1"
    assert by_name["Wilt §1.Fresh.2.else.1"].text == "become Weary"
    assert by_name["Wilt §1.Weary.1.1"].kind == "call"
    assert by_name["Wilt §1.Weary.1.3"].outcome == "Lost For Good"
    assert by_name["Wilt §1.Weary.1.else.1"].kind == "stop"


def test_lift_edges():
    _, lifted = lifted_program()
    assert edge_set(lifted, "CASE") == {("Wilt §1", "Wilt §1.Fresh"),
                                        ("Wilt §1", "Wilt §1.Weary")}
    next_edges = edge_set(lifted, "NEXT")
    assert ("Wilt §1.Fresh", "Wilt §1.Fresh.1") in next_edges
    assert ("Wilt §1.Fresh.1", "Wilt §1.Fresh.2") in next_edges
    assert ("Wilt §1.Fresh.2.1", "Wilt §1.Fresh.2.2") in next_edges
    assert edge_set(lifted, "THEN") == {("Wilt §1.Fresh.2", "Wilt §1.Fresh.2.1"),
                                        ("Wilt §1.Weary.1", "Wilt §1.Weary.1.1")}
    # sibling-form (Fresh) and nested-form (Weary) otherwise both hang off
    # the when
    assert edge_set(lifted, "OTHERWISE") == {
        ("Wilt §1.Fresh.2", "Wilt §1.Fresh.2.else.1"),
        ("Wilt §1.Weary.1", "Wilt §1.Weary.1.else.1")}
    assert lifted.cases == [("Wilt §1.Fresh", "Fresh"),
                            ("Wilt §1.Weary", "Weary")]


def test_bind_outcomes_trails():
    spec, lifted = lifted_program()
    bound = bind_outcomes(spec, lifted)
    assert set(bound) == {"Shrugged Off", "Withered", "Lost For Good"}
    gone = bound["Lost For Good"]
    assert gone["guarantee"] == "fails-with-side-effects"
    assert gone["terminal_steps"] == ["Wilt §1.Weary.1.3"]
    assert "Wilt §1.Weary.1.1" in gone["trail_steps"]   # the call
    assert "Wilt §1.Weary.1.2" in gone["trail_steps"]   # the become
    assert bound["Shrugged Off"]["notes"] == ["still lively"]


# -- extractor integration ----------------------------------------------------

def run(make_repo, files=None, ontology=None):
    base, path = make_repo(files or FILES, ontology or ONTOLOGY)
    ontology_obj, findings = load_ontology(path, base)
    assert ontology_obj is not None
    graph, extract_findings = extract(ontology_obj)
    return graph, findings + extract_findings


def edges(graph, edge_type):
    return {(e.from_label, e.from_name, e.to_label, e.to_name)
            for e in graph.edges if e.type == edge_type}


def test_procedure_node_props(make_repo):
    graph, findings = run(make_repo)
    assert not [f for f in findings if f.severity == ERROR]
    node = graph.nodes[("[Procedure]", "Wilt")]
    assert node["precondition"] == "the frost arrived"
    assert node["completeness"] == "transcribed"
    assert "beast: who wilts" in node["inputs"]
    assert ("ward: a warding bloom (optional; when absent: "
            "no shelter applies)") in node["inputs"]
    assert node["reads_closed"] and node["mutates_closed"]
    tend = graph.nodes[("[Procedure]", "Tend")]
    assert tend["completeness"] == "cited"
    assert tend["description"] == "mends beasts"
    assert not tend["reads_closed"]


def test_steps_materialized_and_chained(make_repo):
    graph, _ = run(make_repo)
    assert graph.nodes[("[Step]", "Wilt §1")]["kind"] == "branch"
    assert graph.nodes[("[Step]", "Wilt §1.Fresh.2")]["condition"] == "Sap > 0"
    assert ("[Procedure]", "Wilt", "[Step]", "Wilt §1") in edges(graph, "FIRST_STEP")


def test_cases_plug_into_states(make_repo):
    graph, _ = run(make_repo)
    assert edges(graph, "MATCHES") == {
        ("[Step]", "Wilt §1.Fresh", "Condition", "Fresh"),
        ("[Step]", "Wilt §1.Weary", "Condition", "Weary")}


def test_specified_in_resolves(make_repo):
    graph, _ = run(make_repo)
    spec_edges = edges(graph, "SPECIFIED_IN")
    assert ("[Procedure]", "Wilt", "DocSection", "rules § Overview") in spec_edges
    assert ("[Procedure]", "Tend", "DocSection", "rules § Overview") in spec_edges


# -- artifact + span citations (canon thinning: canon holds no sections) ------

def artifact_cited(section="Overview", approved_hash=None, artifact="docs/rules.md"):
    lines = ["procedure: Spanned",
             "specified_in:",
             f"  artifact: {artifact}",
             f"  section: {section}"]
    if approved_hash:
        lines.append(f"  approved_hash: {approved_hash}")
    lines += ["possible_outcomes:",
              "  Done:",
              "    ends: all done",
              "    guarantee: read-only",
              "steps:",
              "  - stop: all done"]
    return "\n".join(lines) + "\n"


def run_with_spanned(make_repo, yaml_text):
    files = dict(FILES)
    files["data/procedures/spanned.yaml"] = yaml_text
    ontology = ONTOLOGY.replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/spanned.yaml]")
    return run(make_repo, files=files, ontology=ontology)


def test_artifact_span_citation_lands_on_the_artifact(make_repo):
    import hashlib
    import textwrap

    from graph import parsers
    text = textwrap.dedent(FILES["docs/rules.md"])
    body = dict(parsers.markdown_sections(text))["Overview"]
    good = hashlib.sha256(body.encode("utf-8")).hexdigest()
    graph, findings = run_with_spanned(
        make_repo, artifact_cited(approved_hash=good))
    edge = [e for e in graph.edges if e.type == "SPECIFIED_IN"
            and e.from_name == "Spanned"]
    assert [(e.to_label, e.to_name, dict(e.props)["section"])
            for e in edge] == [("[Artifact]", "docs/rules.md", "Overview")]
    # the hash verified against the file's bytes: no drift warning
    assert not [f for f in findings if "has since changed" in f.detail]


def test_artifact_span_hash_drift_trips(make_repo):
    graph, findings = run_with_spanned(
        make_repo, artifact_cited(approved_hash="a" * 64))
    assert any("has since changed" in f.detail
               and "section 'Overview' of docs/rules.md" in f.detail
               for f in findings)


def test_artifact_span_missing_section_warns(make_repo):
    graph, findings = run_with_spanned(
        make_repo, artifact_cited(section="No Such Heading"))
    assert any("no such heading exists in docs/rules.md" in f.detail
               for f in findings)


def test_step_references_scanned(make_repo):
    graph, _ = run(make_repo)
    refs = edges(graph, "REFERENCES")
    assert ("[Step]", "Wilt §1.Fresh.2.1", "Reserve", "Sap") in refs
    assert ("[Step]", "Wilt §1.Fresh.2.else.1", "Condition", "Weary") in refs
    assert ("[Step]", "Wilt §1.Weary.1.2", "Condition", "Spent") in refs
    # case steps point via ON, not REFERENCES
    assert not any(f == "Wilt §1.Fresh" for (_, f, _, _) in refs)


# -- signature projection -----------------------------------------------------

def test_outcome_nodes_projected(make_repo):
    graph, _ = run(make_repo)
    shrug = graph.nodes[("[Outcome]", "Wilt: Shrugged Off")]
    assert shrug["guarantee"] == "fails-with-side-effects"
    assert shrug["doc"] == "still lively"
    assert edges(graph, "HAS_POSSIBLE_OUTCOME") == {
        ("[Procedure]", "Wilt", "[Outcome]", "Wilt: Shrugged Off"),
        ("[Procedure]", "Wilt", "[Outcome]", "Wilt: Withered"),
        ("[Procedure]", "Wilt", "[Outcome]", "Wilt: Lost For Good")}
    assert ("[Outcome]", "Wilt: Shrugged Off", "[Step]", "Wilt §1.Fresh.2.2") in \
        edges(graph, "ENDS_AT")


def test_outcome_effects_derived(make_repo):
    graph, _ = run(make_repo)
    assert ("[Outcome]", "Wilt: Lost For Good", "Condition", "Spent") in \
        edges(graph, "ASSIGNS_CONDITION")
    assert ("[Outcome]", "Wilt: Shrugged Off", "Reserve", "Sap") in \
        edges(graph, "MUTATES")


def test_procedure_rollups_derived(make_repo):
    graph, _ = run(make_repo)
    assert ("[Procedure]", "Wilt", "Reserve", "Sap") in edges(graph, "READS")
    # a branch observes the concept it switches on, not one named value
    assert ("[Procedure]", "Wilt", "Archetype", "Condition") in edges(graph, "READS")
    mutates = edges(graph, "MUTATES")
    assert ("[Procedure]", "Wilt", "Reserve", "Sap") in mutates
    assert ("[Procedure]", "Wilt", "Condition", "Weary") in mutates
    assert ("[Procedure]", "Wilt", "Condition", "Spent") in mutates
    assert edges(graph, "CALLS") == {
        ("[Procedure]", "Wilt", "[Procedure]", "Tend")}


# compute: a calculation step reads what it names — never mutates. The
# Archetype-level scan exists because label words ("modifiers due to
# Condition") are not value citizens. The scan resolves through the term
# index, so PLURAL forms ("Reserves") project the same concept READS as
# canonical names. A fixture asserting only value-citizen READS would pass
# while a real program's label-word expectations silently failed — these
# assertions target that gap.
TALLY = """\
procedure: Tally
specified_in: rules § Overview
possible_outcomes:
  Tallied:
    ends: done tallying
    guarantee: read-only
steps:
  - compute: running total as Sap plus all modifiers due to the target's Condition
  - compute: the grand total across all Reserves entries
  - compute: the Bounties owed against the total
  - stop: done tallying
"""


def test_compute_verb_is_action_not_mutation():
    from graph.procedures import ACTION_VERBS, MUTATION_VERBS
    assert "compute" in ACTION_VERBS
    assert "compute" not in MUTATION_VERBS
    spec, errors = parse_procedure(TALLY)
    assert errors == []
    assert "Compute running total as Sap" in render_markdown(spec)


def test_compute_projects_reads_not_mutates(make_repo):
    files = dict(FILES)
    files["data/procedures/tally.yaml"] = TALLY
    ontology = ONTOLOGY.replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/tally.yaml]")
    graph, findings = run(make_repo, files=files, ontology=ontology)
    assert not [f for f in findings if f.severity == ERROR]
    reads = edges(graph, "READS")
    # a value citizen named in a compute step is read
    assert ("[Procedure]", "Tally", "Reserve", "Sap") in reads
    # a label word resolves via the Archetype scan (candidates exclude them)
    assert ("[Procedure]", "Tally", "Archetype", "Condition") in reads
    # the plural "Reserves" resolves through the term index to Archetype
    # Reserve — plural spellings project concept READS
    assert ("[Procedure]", "Tally", "Archetype", "Reserve") in reads
    # plural VALUE-citizen mentions resolve to the canonical node too
    assert ("[Procedure]", "Tally", "Reserve", "Bounty") in reads
    refs = edges(graph, "REFERENCES")
    assert ("[Step]", "Tally §3", "Reserve", "Bounty") in refs
    # compute never mutates
    assert not [e for e in edges(graph, "MUTATES") if e[1] == "Tally"]


def test_compute_reads_resolve_the_project_layer_only(make_repo):
    # a step that happens to say a kernel facet's name ("Completeness",
    # "Ordered") observes no kernel machinery: concept-level READS land
    # on project concepts only, never on the kernel stratum
    files = dict(FILES)
    files["data/procedures/tally.yaml"] = TALLY.replace(
        "  - compute: the Bounties owed against the total\n",
        "  - compute: the Bounties owed against the total, by Completeness "
        "and Ordered rank\n")
    ontology = ONTOLOGY.replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/tally.yaml]")
    graph, findings = run(make_repo, files=files, ontology=ontology)
    assert not [f for f in findings if f.severity == ERROR]
    reads = edges(graph, "READS")
    assert ("[Procedure]", "Tally", "Archetype", "Condition") in reads
    kernel_reads = [e for e in reads if e[1] == "Tally"
                    and e[2] == "Archetype"
                    and e[3] in ("Completeness", "Ordered")]
    assert kernel_reads == []


def test_known_at_completeness_archetypes(make_repo):
    graph, _ = run(make_repo)
    known = edges(graph, "KNOWN_AT")
    assert ("[Procedure]", "Wilt", "Archetype", "Transcribed") in known
    assert ("[Procedure]", "Tend", "Archetype", "Cited") in known
    # the levels are doc-bearing instances of the Completeness facet
    assert ("Archetype", "Transcribed", "Archetype", "Completeness") in \
        edges(graph, "INSTANCE_OF")
    assert graph.nodes[("Archetype", "Cited")]["doc"]


def test_completeness_ladder_is_ordered(make_repo):
    graph, _ = run(make_repo)
    assert graph.nodes[("Archetype", "Cited")]["rank"] == 0
    assert graph.nodes[("Archetype", "Attested")]["rank"] == 1
    assert graph.nodes[("Archetype", "Transcribed")]["rank"] == 2
    assert ("Archetype", "Cited", "Archetype", "Attested") in \
        edges(graph, "PRECEDES")
    assert ("Archetype", "Transcribed", "Archetype", "Attested") in \
        edges(graph, "FOLLOWS")
    assert ("Archetype", "Completeness", "Archetype", "Ordered") in \
        edges(graph, "INSTANCE_OF")


def test_outcomes_not_in_metamodel(make_repo):
    graph, _ = run(make_repo)
    assert ("Archetype", "[Outcome]") not in graph.nodes
    assert not any(e.from_label == "[Outcome]" for e in graph.edges
                   if e.type == "INSTANCE_OF")


# -- attested completeness ------------------------------------------------------

ATTESTED = """\
procedure: Shield
completeness: attested
specified_in: rules § Overview
description: keeps frost out
inputs:
  subject: who is shielded
reads: { closed: true, known: [Sap] }
mutates: { closed: false, known: [Sap] }
possible_outcomes:
  Shielded:
    guarantee: cannot-fail
    assigns: [Weary]
    mutates: [Sap]
    description: sheltered now
"""


def attested_repo_files():
    files = dict(FILES)
    files["data/procedures/shield.yaml"] = ATTESTED
    ontology = ONTOLOGY.replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/shield.yaml]")
    return files, ontology


def test_attested_asserted_signature(make_repo):
    files, ontology = attested_repo_files()
    graph, findings = run(make_repo, files, ontology)
    assert not [f for f in findings if f.severity == ERROR]
    node = graph.nodes[("[Procedure]", "Shield")]
    assert node["completeness"] == "attested"
    assert node["reads_closed"] and not node["mutates_closed"]
    assert ("[Procedure]", "Shield", "Reserve", "Sap") in edges(graph, "READS")
    assert ("[Procedure]", "Shield", "Reserve", "Sap") in edges(graph, "MUTATES")
    shielded = graph.nodes[("[Outcome]", "Shield: Shielded")]
    assert shielded["guarantee"] == "cannot-fail"
    assert shielded["doc"] == "sheltered now"
    assert ("[Outcome]", "Shield: Shielded", "Condition", "Weary") in \
        edges(graph, "ASSIGNS_CONDITION")
    # no hash tripwire on an attested procedure -> drift risk surfaced softly
    assert any(f.severity == INFO and "no approved_hash" in f.detail
               for f in findings)


SPIRIT_ATTESTED = """\
procedure: Cheer
completeness: attested
specified_in: rules § Overview
description: gladdens the beast
possible_outcomes:
  Gladdened:
    guarantee: cannot-fail
    assigns: [Merry]
    description: at ease now
"""


def test_attested_assigns_a_second_domain(make_repo):
    # An attested outcome that assigns a Spirit — a domain other than the
    # first — derives ASSIGNS_SPIRIT from the resolved target's label, the
    # same transform the transcribed become-step uses. No one domain is
    # baked into the attested grammar.
    files = dict(FILES)
    files["data/spirits.csv"] = "Spirit\nMerry\nGloomy\n"
    files["data/procedures/cheer.yaml"] = SPIRIT_ATTESTED
    ontology = ONTOLOGY.replace(
        "      Reserve:",
        "      Spirit:\n"
        "        source: data/spirits.csv\n"
        "        key: Spirit\n"
        "        concept: Tale Concept\n"
        "      Reserve:").replace(
        "data/procedures/tend.yaml]",
        "data/procedures/tend.yaml, data/procedures/cheer.yaml]")
    graph, findings = run(make_repo, files=files, ontology=ontology)
    assert not [f for f in findings if f.severity == ERROR]
    assert ("[Outcome]", "Cheer: Gladdened", "Spirit", "Merry") in \
        edges(graph, "ASSIGNS_SPIRIT")
    # and it is NOT misfiled under some other domain's edge type
    assert not [e for e in edges(graph, "ASSIGNS_CONDITION")
                if e[1] == "Cheer: Gladdened"]


# -- hash tripwire ------------------------------------------------------------

def hash_repo_files(approved_hash):
    files = dict(FILES)
    files["data/procedures/test.yaml"] = PROGRAM.replace(
        "specified_in: rules § Overview",
        "specified_in:\n"
        "  section: rules § Overview\n"
        f"  approved_hash: {approved_hash}")
    return files


def overview_hash():
    text = textwrap.dedent(FILES["docs/rules.md"])
    body = dict(markdown_sections(text))["Overview"]
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_matching_hash_is_silent(make_repo):
    graph, findings = run(make_repo, hash_repo_files(overview_hash()))
    assert not [f for f in findings if "has since changed" in f.detail]
    assert ("[Procedure]", "Wilt", "DocSection", "rules § Overview") in \
        edges(graph, "SPECIFIED_IN")


def test_stale_hash_warns(make_repo):
    _, findings = run(make_repo, hash_repo_files("f" * 64))
    assert any(f.severity == WARNING and "has since changed" in f.detail
               for f in findings)


def test_numeric_hash_rejected():
    # YAML parses an unquoted all-digit hash as an int — force hex strings
    assert "approved_hash must be a 64-char sha256 hex string" in errors_of("""\
        procedure: X
        specified_in: { section: y, approved_hash: 12345 }
        steps: [ {stop: done} ]
        """)


# -- from_text receipts ---------------------------------------------------------

def receipt_files(quote):
    files = dict(FILES)
    files["data/procedures/test.yaml"] = PROGRAM.replace(
        "    description: a warding bloom\n",
        "    description: a warding bloom\n"
        f"    from_text: {quote}\n")
    return files


def test_valid_receipt_is_silent(make_repo):
    _, findings = run(make_repo, receipt_files("Wilts happen"))
    assert not any("receipt not found" in f.detail for f in findings)


def test_bogus_receipt_warns(make_repo):
    _, findings = run(make_repo, receipt_files("Nothing of the sort"))
    assert any(f.severity == WARNING and "receipt not found" in f.detail
               for f in findings)


# -- unresolved-term tripwire ---------------------------------------------------

def test_unresolved_capitalized_term_flagged(make_repo):
    # "Sprite" is mid-sentence in the source, and neither a graph citizen
    # nor mentioned by the program — the Truename failure class
    _, findings = run(make_repo)
    assert any(f.category == "unresolved-term" and "Sprite" in f.detail
               for f in findings)


def test_terms_touched_by_program_not_flagged(make_repo):
    _, findings = run(make_repo)
    flagged = " ".join(f.detail for f in findings
                       if f.category == "unresolved-term")
    assert "Wilts" not in flagged            # sentence start
    assert "Fresh Condition" not in flagged  # compound of whole graph citizens


def test_multiword_term_flagged_as_a_run(make_repo):
    # single-token scanning would lose "Dread Hollow" to word-level noise
    _, findings = run(make_repo)
    assert any(f.category == "unresolved-term" and "Dread Hollow" in f.detail
               for f in findings)


def test_stub_and_surface_forms_resolve_terms(make_repo):
    graph, findings = run(make_repo)
    flagged = " ".join(f.detail for f in findings
                       if f.category == "unresolved-term")
    # "Bramble Woods" = auto-plural of the stub concept "Bramble Wood"
    assert "Bramble Woods" not in flagged
    # "Thicket" = explicit surface form of the stub
    assert "Thicket" not in flagged
    # the stub is a real, queryable citizen with the worklist marker
    assert graph.nodes[("Archetype", "Bramble Wood")]["stub"] is True
    assert ("Archetype", "Bramble Wood", "Archetype", "Tale Concept") in \
        edges(graph, "INSTANCE_OF")


def test_locals_resolve_terms(make_repo):
    # declare the flagged bigram as a program local -> no longer flagged
    files = dict(FILES)
    files["data/procedures/test.yaml"] = PROGRAM.replace(
        "precondition: the frost arrived",
        "precondition: the frost arrived\nlocals: [Dread Hollow]")
    _, findings = run(make_repo, files=files)
    # locals are PROCEDURE-scoped: Wilt declares the local, so ITS scan is
    # clean; Tend shares the source section without the local and still
    # flags the term (its source contains vocabulary it does not explain)
    wilt_flagged = " ".join(f.detail for f in findings
                            if f.category == "unresolved-term"
                            and f.location == "Wilt")
    assert "Dread Hollow" not in wilt_flagged
    tend_flagged = " ".join(f.detail for f in findings
                            if f.category == "unresolved-term"
                            and f.location == "Tend")
    assert "Dread Hollow" in tend_flagged


def test_pending_instances_resolve_terms(make_repo):
    # a stub's known future citizens resolve to the stub that will own them
    files = dict(FILES)
    files["docs/rules.md"] = files["docs/rules.md"].replace(
        "The Thicket claims the unwary near the Dread Hollow.",
        "The Thicket claims the unwary near the Dread Hollow. "
        "Beware the Wood Wight.")
    ontology = ONTOLOGY.replace(
        "        surface_forms: [Thicket]",
        "        surface_forms: [Thicket]\n"
        "        pending_instances: [Wood Wight]")
    _, findings = run(make_repo, files=files, ontology=ontology)
    flagged = " ".join(f.detail for f in findings
                       if f.category == "unresolved-term")
    assert "Wood Wight" not in flagged
    assert "Dread Hollow" in flagged  # still unknown


def test_pending_instances_require_stub():
    from graph.ontology import load_ontology
    import pathlib
    import tempfile
    import textwrap
    yaml_text = textwrap.dedent("""\
        version: 1
        concepts:
          Tale Concept: { instance_of: Concept }
          Mapped Thing:
            instance_of: Tale Concept
            pending_instances: [Ghost]
        nodes: {}
        """)
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "ontology.yaml"
        path.write_text(yaml_text, encoding="utf-8")
        _, findings = load_ontology(path, tmp)
    assert any("requires" in f.detail and "stub" in f.detail
               for f in findings)


def test_surface_form_collision_warns(make_repo):
    # a surface form claiming an existing citizen's name is ambiguous
    ontology = ONTOLOGY.replace(
        "        surface_forms: [Thicket]",
        "        surface_forms: [Thicket, Sap]")
    _, findings = run(make_repo, ontology=ontology)
    assert any(f.severity == WARNING and "surface form 'Sap'" in f.detail
               and "ambiguous" in f.detail for f in findings)


def test_run_boundaries_and_irregular_plurals(make_repo):
    _, findings = run(make_repo)
    flagged = " ".join(f.detail for f in findings
                       if f.category == "unresolved-term")
    assert "Sap Sprites" not in flagged  # a run never spans a line break
    assert "Sprites" not in flagged      # line-leading word is no signal
    assert "Bounties" not in flagged     # -ies plural resolves to Bounty


# -- errors and reservations --------------------------------------------------

def test_bad_program_reports_and_skips(make_repo):
    bad = dict(FILES)
    bad["data/procedures/test.yaml"] = "procedure: Broken\nsteps: [ {zap: x} ]\n"
    base, path = make_repo(bad, ONTOLOGY)
    ontology, _ = load_ontology(path, base)
    graph, findings = extract(ontology)
    assert any(f.severity == ERROR and f.category == "procedure"
               for f in findings)
    assert ("[Procedure]", "Broken") not in graph.nodes


def test_step_and_outcome_are_reserved_labels(make_repo):
    base, path = make_repo(FILES,
                           ONTOLOGY + "\n      \"[Step]\": { values: [Impostor] }\n"
                                      "      \"[Outcome]\": { values: [Sneaky] }\n")
    _, findings = load_ontology(path, base)
    reserved = [f.detail for f in findings if "engine-reserved" in f.detail]
    assert len(reserved) == 2


def test_walk_resolves_branch_subject_by_surface():
    spec, errors = parse_procedure(textwrap.dedent("""\
        procedure: X
        steps:
          - branch on: the beast's Temper
            cases:
              Calm:
                - become: Cross
                - stop: done
              Cross:
                - stop: done
        """))
    assert not errors, errors
    # a candidate subject that is not this branch's yields nothing
    assert walk_transitions(spec, ["Condition", "Conditions"]) == set()
    # the branch's subject, resolved by the term index, yields the ladder
    assert walk_transitions(spec, ["Temper", "Tempers"]) == \
        {("Calm", "Cross")}
    # resolution is letter-bounded (term index), not substring: a surface
    # that only sits inside another word does not fire — 'Temp' must not
    # match 'Temper'
    assert walk_transitions(spec, ["Temp"]) == set()
    assert branches_on_subject(spec, ["Temper"]) == \
        ["the beast's Temper"]
    assert branches_on_subject(spec, ["Condition"]) == []


# -- rendering (generation machinery) ------------------------------------------

def test_render_markdown_shape():
    spec, _ = parse_procedure(PROGRAM)
    prose = render_markdown(spec)
    assert prose.startswith("### Wilt\n")
    assert "*Precondition:* the frost arrived." in prose
    # the WHOLE signature renders — authored inputs face the generation
    # diff, so an input the source never states shows up as an invention
    assert "**Inputs:**" in prose
    assert "- beast — who wilts" in prose
    assert ("- ward — a warding bloom *(optional; when absent: "
            "no shelter applies)*" in prose)
    assert "**Outputs:**" in prose
    assert "- **Fresh:**" in prose
    assert "  Roll a vigor check." in prose
    assert "  - *Sap > 0:* Spend Sap by 1. Stop here — still lively." in prose
    assert ("  - *It is severe:* Perform the Tend for the beast. "
            "The character becomes Spent. Stop here — all gone. "
            "Otherwise: Stop here — drooping.") in prose


def test_render_top_level_sibling_otherwise():
    # the validator accepts a top-level otherwise as a sibling of the
    # prior when; the renderer must handle the bare {otherwise: [...]} item
    # instead of falling through to value.strip() on a list
    spec, errors = parse_procedure(textwrap.dedent("""\
        procedure: Ramble
        possible_outcomes:
          Wandered: { ends: paths open,  guarantee: fails-clean }
          Blocked:  { ends: paths close, guarantee: fails-with-side-effects }
        steps:
          - when: the gate is open
            then:
              - stop: paths open
          - otherwise:
              - stop: paths close
        """))
    assert errors == []
    prose = render_markdown(spec)
    assert "If the gate is open: Stop here — paths open." in prose
    assert "Otherwise: Stop here — paths close." in prose


# -- procedure-citizen roster tripwire ----------------------------------------

def roster_findings(make_repo, files=None, ontology=None):
    from graph.extract import procedure_roster_findings
    base, path = make_repo(files or FILES, ontology or ONTOLOGY)
    ontology_obj, _ = load_ontology(path, base)
    graph, _ = extract(ontology_obj)
    return ontology_obj, graph, procedure_roster_findings


def test_roster_passes_when_every_file_has_its_citizen(make_repo):
    ontology_obj, graph, check = roster_findings(make_repo)
    assert check(ontology_obj, graph) == []


def test_roster_flags_a_registered_file_without_its_citizen(make_repo):
    ontology_obj, graph, check = roster_findings(make_repo)
    # a re-derivation lifts steps from a body already on the graph and
    # never re-adds the procedure node — drop one to model the file that
    # shipped without its citizen
    del graph.nodes[("[Procedure]", "Tend")]
    findings = check(ontology_obj, graph)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == ERROR
    assert finding.detail == (
        "Attempted to verify the procedure roster with 2 registered "
        "program files. Failed: data/procedures/tend.yaml has no "
        "[Procedure] citizen — the file shipped without its node. Land "
        "the citizen through the delta path.")


def test_derive_refuses_when_a_registered_file_has_no_citizen(make_repo):
    # the roster ERROR rides derive(), which rederive and canonize --apply
    # both refuse on — the canon gate a missed re-derivation slipped past
    from graph.extract import derive
    base, path = make_repo(FILES, ONTOLOGY)
    ontology_obj, _ = load_ontology(path, base)
    graph, _ = extract(ontology_obj)
    del graph.nodes[("[Procedure]", "Tend")]
    _, findings = derive(ontology_obj, graph)
    assert any(f.severity == ERROR
               and "data/procedures/tend.yaml has no [Procedure] citizen"
               in f.detail for f in findings)


# -- precondition receipts (mapping form) --------------------------------


def test_precondition_mapping_form_parses_and_carries_its_receipt():
    spec, errors = parse_procedure(textwrap.dedent("""\
        procedure: X
        precondition:
          text: the frost arrived
          from_text: The frost arrived before the last harvest.
        steps: [ {stop: done} ]
        possible_outcomes:
          Done: { ends: done, guarantee: fails-clean }
        """))
    assert errors == [] and spec is not None
    from graph.procedures import precondition_text, receipts_of
    assert precondition_text(spec) == "the frost arrived"
    assert ("precondition",
            "The frost arrived before the last harvest.") in \
        receipts_of(spec)


def test_precondition_plain_string_still_works():
    spec, errors = parse_procedure(PROGRAM)
    assert errors == [] and spec is not None
    from graph.procedures import precondition_text, receipts_of
    assert precondition_text(spec) == "the frost arrived"
    assert not any(loc == "precondition"
                   for loc, _ in receipts_of(spec))


def test_precondition_bad_forms_refuse_by_name():
    errs = errors_of("""\
        procedure: X
        precondition: { from_text: quote with no text }
        steps: [ {stop: done} ]
        """)
    assert "precondition mapping needs a 'text'" in errs
    errs = errors_of("""\
        procedure: X
        precondition: { text: fine, bogus: 1 }
        steps: [ {stop: done} ]
        """)
    assert "unknown precondition key 'bogus'" in errs
    errs = errors_of("""\
        procedure: X
        precondition: [a, list]
        steps: [ {stop: done} ]
        """)
    assert "must be a string or a {text, from_text} mapping" in errs


def test_precondition_renders_its_text_whichever_form(tmp_path):
    spec, errors = parse_procedure(textwrap.dedent("""\
        procedure: X
        precondition: { text: the frost arrived, from_text: The frost. }
        steps: [ {stop: done} ]
        possible_outcomes:
          Done: { ends: done, guarantee: fails-clean }
        """))
    assert errors == [] and spec is not None
    assert "*Precondition:* the frost arrived." in render_markdown(spec)


# -- approved_in: the archive pointer beside the tripwire ----------------


def test_approved_in_parses_and_lands_on_the_citizen(make_repo):
    program = PROGRAM.replace(
        "specified_in: rules § Overview",
        "specified_in:\n"
        "  artifact: docs/rules.md\n"
        "  section: Overview\n"
        "  approved_in: https://example.test/repo/pull/7\n")
    spec, errors = parse_procedure(program)
    assert errors == [] and spec is not None
    files = dict(FILES); files["data/procedures/test.yaml"] = program
    base, path = make_repo(files, ONTOLOGY)
    ontology, findings = load_ontology(path, base)
    assert ontology is not None, findings
    graph, _ = extract(ontology)
    assert graph.nodes[("[Procedure]", "Wilt")]["approved_in"] \
        == "https://example.test/repo/pull/7"


def test_approved_in_must_be_a_link_shaped_string():
    assert "approved_in must be a commit or PR link" in errors_of("""\
        procedure: X
        specified_in: { artifact: a.md, section: S, approved_in: 7 }
        steps: [ {stop: done} ]
        possible_outcomes:
          Done: { ends: done, guarantee: fails-clean }
        """)
