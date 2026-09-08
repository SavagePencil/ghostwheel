"""Ontology-declared answer keys: the generic derivation check that
replaced the hand-coded pytest functions. Fixture-driven over
self-contained imaginary corpora — a new procedure earns its fidelity
net by adding a declaration, nobody hand-writes a test.

The keys live on canon: each is an Answer Key citizen carrying its kind
and table as props, the rest of its declaration as JSON, and one CHECKS
edge to the Procedure it holds still. Program bodies are graph-resident;
the approved tables stay on disk and are read from the knowledge base's
own directory."""

import json

from graph.answer_keys import CHECKS_EDGE, KEY_JSON_PROP, canon_check
from graph.extract import GraphData, make_edge
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_ANSWER_KEY_LABEL,
                            KERNEL_PROCEDURE_LABEL, ontology_from_graph)

PROGRAM = """\
procedure: Wilt
possible_outcomes:
  Wilted:
    ends: done wilting
    guarantee: cannot-fail
steps:
  - branch on: the target's Vigor
    cases:
      Fresh:
        - when: Rot > 10
          then:
            - become: Limp
        - stop: done wilting
      Limp:
        - when: Rot > 5
          then:
            - become: Dozed
        - stop: done wilting
"""

TABLES = {
    "data/wilt-transitions.csv": (
        "From Vigor,To Vigor\nFresh,Limp\nLimp,Dozed\n"),
    "data/wilt-thresholds.csv": (
        "Vigor,Rot Needed\nFresh,10\nLimp,5\nDozed,N/A\n"),
}

SUBJECTS = {"Vigor": ["Fresh", "Limp", "Dozed"]}

PROGRAMS = {"Wilt": PROGRAM}

# the fixture's two declarations, as canon citizens: {name: (procedure,
# props)} — the kind and table ride as plain props, the rest as JSON
GOOD_KEYS = {
    "Wilt walks its ladder": ("Wilt", {
        "derives": "transitions", "table": "data/wilt-transitions.csv",
        KEY_JSON_PROP: json.dumps({"from_column": "From Vigor",
                                   "to_column": "To Vigor"})}),
    "Wilt holds its thresholds": ("Wilt", {
        "derives": "thresholds", "table": "data/wilt-thresholds.csv",
        KEY_JSON_PROP: json.dumps({"key_column": "Vigor",
                                   "value_column": "Rot Needed",
                                   "condition_pattern": "Rot > {value}"})}),
}


def write_tables(base_dir, tables):
    for relpath, content in tables.items():
        path = base_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_graph(subjects=SUBJECTS, programs=PROGRAMS, keys=None):
    """The corpus as canon holds it: subject labels declared with the
    Exclusive+Stateful facets, program bodies riding their Procedure
    citizens, and (optionally) Answer Key citizens with CHECKS edges."""
    from graph.kernel_migrate import installed_kernel_identity
    graph = GraphData()
    graph.ensure_node(ARCHETYPE_LABEL, "Ontology")
    version, fingerprint = installed_kernel_identity()
    graph.ensure_node(ARCHETYPE_LABEL, "Metaontology",
                      version=version, fingerprint=fingerprint)
    for label, values in subjects.items():
        graph.ensure_node(ARCHETYPE_LABEL, label, spec_json=json.dumps(
            {"concept": ["Tale Concept", "Exclusive", "Stateful"]},
            sort_keys=True))
        graph.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                     ARCHETYPE_LABEL, "Ontology"))
        for value in values:
            graph.ensure_node(label, value)
    graph.ensure_node(ARCHETYPE_LABEL, KERNEL_PROCEDURE_LABEL)
    for name, body in programs.items():
        graph.ensure_node(KERNEL_PROCEDURE_LABEL, name, body=body)
    add_keys(graph, keys or {})
    return graph


def add_keys(graph, keys):
    for name, (procedure, props) in keys.items():
        graph.ensure_node(KERNEL_ANSWER_KEY_LABEL, name, **props)
        graph.edges.append(make_edge(
            CHECKS_EDGE, KERNEL_ANSWER_KEY_LABEL, name,
            KERNEL_PROCEDURE_LABEL, procedure))
    return graph


def findings_for(tmp_path, tables=None, keys=GOOD_KEYS, subjects=SUBJECTS,
                 programs=PROGRAMS):
    write_tables(tmp_path, tables or TABLES)
    graph = build_graph(subjects, programs, keys)
    rows = canon_check(graph, ontology_from_graph(graph, tmp_path), tmp_path)
    return [f for row in rows for f in row["problems"]]


def test_faithful_program_verifies_clean(tmp_path):
    assert findings_for(tmp_path) == []


def test_table_row_the_program_lost_is_named(tmp_path):
    tables = dict(TABLES)
    tables["data/wilt-transitions.csv"] += "Dozed,Fresh\n"  # nobody derives this
    [finding] = findings_for(tmp_path, tables)
    assert "no longer derives the approved transition Dozed → Fresh" \
        in finding.detail


def test_transition_nobody_approved_is_named(tmp_path):
    tables = dict(TABLES)
    tables["data/wilt-transitions.csv"] = "From Vigor,To Vigor\nFresh,Limp\n"
    [finding] = findings_for(tmp_path, tables)
    assert "derives Limp → Dozed" in finding.detail
    assert "no such row" in finding.detail


def test_threshold_drift_is_named(tmp_path):
    tables = dict(TABLES)
    tables["data/wilt-thresholds.csv"] = (
        "Vigor,Rot Needed\nFresh,12\nLimp,5\nDozed,N/A\n")
    [finding] = findings_for(tmp_path, tables)
    assert "case 'Fresh'" in finding.detail
    assert '"Rot > 12"' in finding.detail


def test_empty_marker_threshold_is_no_threshold(tmp_path):
    # Dozed,N/A raises nothing: the bottom rung has nowhere to go
    assert findings_for(tmp_path) == []


def test_skip_values_declares_no_threshold_markers(tmp_path):
    # A key may declare cell values that mean "no threshold exists"
    # beyond the global empty markers (the ♾️ cells). Without the
    # declaration the ♾️ row demands an absurd branch; with it, silence.
    tables = dict(TABLES)
    tables["data/wilt-thresholds.csv"] = (
        "Vigor,Rot Needed\nFresh,10\nLimp,5\nDozed,+♾️\n")
    [finding] = findings_for(tmp_path, tables)
    assert "no branch case for 'Dozed'" in finding.detail
    keys = dict(GOOD_KEYS)
    keys["Wilt holds its thresholds"] = ("Wilt", {
        "derives": "thresholds", "table": "data/wilt-thresholds.csv",
        KEY_JSON_PROP: json.dumps({"key_column": "Vigor",
                                   "value_column": "Rot Needed",
                                   "condition_pattern": "Rot > {value}",
                                   "skip_values": ["+♾️"]})})
    assert findings_for(tmp_path, tables, keys=keys) == []


def test_unknown_procedure_is_an_error(tmp_path):
    keys = dict(GOOD_KEYS)
    keys["Wilt walks its ladder"] = (
        "Bloom", keys["Wilt walks its ladder"][1])
    [finding] = findings_for(tmp_path, keys=keys)
    assert finding.severity == "error"
    assert "no transcribed procedure named 'Bloom'" in finding.detail


def test_declaration_typo_is_an_error(tmp_path):
    keys = dict(GOOD_KEYS)
    keys["Wilt walks its ladder"] = ("Wilt", {
        "derives": "transitions", "table": "data/wilt-transitions.csv",
        KEY_JSON_PROP: json.dumps({"from_colun": "From Vigor",
                                   "to_column": "To Vigor"})})
    problems = findings_for(tmp_path, keys=keys)
    assert any("unknown answer-key field" in f.detail for f in problems)


BLOOM = """\
procedure: Bloom
possible_outcomes:
  Bloomed:
    ends: done blooming
    guarantee: cannot-fail
steps:
  - branch on: the garden's Mood
    cases:
      Grey:
        - become: Bright
        - stop: done blooming
      Bright:
        - stop: done blooming
"""


def test_second_stateful_concept_derives_without_subjects(tmp_path):
    # A SECOND Exclusive+Stateful concept (Mood) is discovered from the
    # facets exactly as Vigor is — its ladder derives with no subjects
    # declared on either key. Both ladders verify clean, proving candidate
    # subjects come from the declarations, not a per-key list.
    tables = dict(TABLES)
    tables["data/mood-transitions.csv"] = "From Mood,To Mood\nGrey,Bright\n"
    keys = dict(GOOD_KEYS)
    keys["Bloom walks its ladder"] = ("Bloom", {
        "derives": "transitions", "table": "data/mood-transitions.csv",
        KEY_JSON_PROP: json.dumps({"from_column": "From Mood",
                                   "to_column": "To Mood"})})
    drift = findings_for(
        tmp_path, tables, keys=keys,
        subjects={**SUBJECTS, "Mood": ["Grey", "Bright"]},
        programs={**PROGRAMS, "Bloom": BLOOM})
    assert drift == [], [f.detail for f in drift]


FREEZE = """\
procedure: Freeze
possible_outcomes:
  Frozen:
    ends: done freezing
    guarantee: cannot-fail
steps:
  - branch on: the target's Vigor
    cases:
      Fresh:
        - stop: done freezing
      Limp:
        - stop: done freezing
"""


def test_subject_branch_that_derives_nothing_is_loud(tmp_path):
    # Freeze branches on Vigor (a tracked Exclusive+Stateful subject) but
    # names no become — it derives zero transitions. The old walker would
    # attest nothing in silence; now it is a named finding.
    keys = dict(GOOD_KEYS)
    keys["Freeze walks its ladder"] = ("Freeze", {
        "derives": "transitions", "table": "data/wilt-transitions.csv",
        KEY_JSON_PROP: json.dumps({"from_column": "From Vigor",
                                   "to_column": "To Vigor"})})
    drift = findings_for(tmp_path, keys=keys,
                         programs={**PROGRAMS, "Freeze": FREEZE})
    assert any("branches on a tracked subject but derives no transitions"
               in f.detail and "Freeze" in f.detail for f in drift), \
        [f.detail for f in drift]


# --- derives: recompute — worked examples as checks ---------------------

SCORE_PROGRAM = """\
procedure: Score the Entry
possible_outcomes:
  Scored:
    ends: scored
    guarantee: read-only
locals: [Total Score, Base Score, Bonus, Acclaim]
steps:
  - compute: Total Score = (Base Score + Bonus) × (1 + Acclaim)
  - stop: scored
"""

RECOMPUTE_TABLES = {
    "data/sweet_recipes.csv": (
        "Recipe,Score Dice,Traits\n"
        'Tart,2-7 (1d6+1),Benefits from Flair\n'),
    "data/savory_recipes.csv": (
        "Recipe,Score Dice,Traits\n"
        'Gruel,1-3 (1d3),Benefits from Flair\n'),
    "data/flair_table.csv": "Flair,Score Boost\n3,-2\n16,+2\n",
    "data/ribbons.csv": (
        "Ribbon,Boost\nGolden,\nRibbon of X,+1x\n"
        "Dim,-.75x\nGrim,-.75x\n"),
    "data/ribbon_templates.csv": (
        "Ribbon Instance,Template\nGolden,Ribbon of X\n"),
    "data/scored_examples.csv": (
        "Example,Recipe,Entry Kind,Judge Roll,Bonus Contributions,"
        "Suppressed Contributions,Acclaim Contributions,"
        "Expected Base Score,Expected Bonus,Expected Acclaim,"
        "Expected Total Score\n"
        "First Tasting,Tart,sweet,3,Flair 16=+2,,Ribbon Golden=+1x,"
        "4,2,1,12\n"
        'Humble Gruel,Gruel,savory,1,Flair 3=-2,,'
        '"Ribbon Dim=-.75x; Ribbon Grim=-.75x",1,-2,-1,0\n'),
}

RECOMPUTE_DECLARATION = {
    "result": {
        "formula": "(Base Score + Bonus) * (1 + Acclaim)",
        "expected_column": "Expected Total Score",
        "floor": 0,
    },
    "components": {
        "Base Score": {
            "given_column": "Judge Roll",
            "expected_column": "Expected Base Score",
            "lookup": {
                "select_by": "Entry Kind",
                "key_from": "Recipe",
                "variants": {
                    "sweet": {"table": "data/sweet_recipes.csv",
                              "key_column": "Recipe",
                              "value_column": "Score Dice",
                              "parse": "dice_flat"},
                    "savory": {"table": "data/savory_recipes.csv",
                               "key_column": "Recipe",
                               "value_column": "Score Dice",
                               "parse": "dice_flat"},
                },
            },
        },
        "Bonus": {
            "pairs_column": "Bonus Contributions",
            "suppressed_column": "Suppressed Contributions",
            "expected_column": "Expected Bonus",
            "pair_lookups": {
                "Flair": {
                    "table": "data/flair_table.csv",
                    "key_column": "Flair",
                    "value_column": "Score Boost",
                    "gate": {
                        "property": "Benefits from Flair",
                        "lookup": {
                            "select_by": "Entry Kind",
                            "key_from": "Recipe",
                            "variants": {
                                "sweet": {"table": "data/sweet_recipes.csv",
                                          "key_column": "Recipe",
                                          "value_column": "Traits"},
                                "savory": {"table": "data/savory_recipes.csv",
                                           "key_column": "Recipe",
                                           "value_column": "Traits"},
                            },
                        },
                    },
                },
            },
        },
        "Acclaim": {
            "pairs_column": "Acclaim Contributions",
            "expected_column": "Expected Acclaim",
            "floor": -1,
            "pair_lookups": {
                "Ribbon": {
                    "table": "data/ribbons.csv",
                    "key_column": "Ribbon",
                    "value_column": "Boost",
                    "parse": "multiplier",
                    "template_fallback": {
                        "table": "data/ribbon_templates.csv",
                        "key_column": "Ribbon Instance",
                        "value_column": "Template"},
                },
            },
        },
    },
}

RECOMPUTE_KEYS = {
    "The scored examples recompute": ("Score the Entry", {
        "derives": "recompute", "table": "data/scored_examples.csv",
        KEY_JSON_PROP: json.dumps(RECOMPUTE_DECLARATION)}),
}


def recompute_findings(tmp_path, tables=None, keys=RECOMPUTE_KEYS,
                       program=SCORE_PROGRAM):
    return findings_for(tmp_path, tables or RECOMPUTE_TABLES, keys=keys,
                        subjects={}, programs={"Score the Entry": program})


def test_recompute_faithful_examples_verify_clean(tmp_path):
    # covers: variant lookup + dice flat, gated pair, template fallback,
    # component floor (-1.5 → -1), result floor (-1 × 0 → 0)
    assert recompute_findings(tmp_path) == []


def test_recompute_drifted_table_value_is_named(tmp_path):
    tables = dict(RECOMPUTE_TABLES)
    tables["data/flair_table.csv"] = "Flair,Score Boost\n3,-2\n16,+3\n"
    problems = recompute_findings(tmp_path, tables)
    assert any("claims Flair 16 contributes +2" in f.detail and
               "now says 3" in f.detail for f in problems)
    # the drifted contribution also breaks the sums downstream, by name
    assert any("recomputed Bonus = 3" in f.detail for f in problems)


def test_recompute_wrong_asserted_total_is_named(tmp_path):
    tables = dict(RECOMPUTE_TABLES)
    tables["data/scored_examples.csv"] = tables[
        "data/scored_examples.csv"].replace("4,2,1,12", "4,2,1,13")
    [finding] = recompute_findings(tmp_path, tables)
    assert "recomputes to 12" in finding.detail
    assert "asserts 13" in finding.detail


def test_recompute_lost_gate_is_named(tmp_path):
    tables = dict(RECOMPUTE_TABLES)
    tables["data/sweet_recipes.csv"] = (
        "Recipe,Score Dice,Traits\nTart,2-7 (1d6+1),\n")
    problems = recompute_findings(tmp_path, tables)
    assert any("no longer bears Benefits from Flair" in f.detail
               for f in problems)


def test_recompute_broken_suppression_is_named(tmp_path):
    tables = dict(RECOMPUTE_TABLES)
    tables["data/scored_examples.csv"] = tables[
        "data/scored_examples.csv"].replace(
        "First Tasting,Tart,sweet,3,Flair 16=+2,,",
        "First Tasting,Tart,sweet,3,,Flair 16,").replace(
        "4,2,1,12", "4,0,1,8")
    problems = recompute_findings(tmp_path, tables)
    assert any("is NOT applied" in f.detail and
               "now bears Benefits from Flair" in f.detail
               for f in problems)


def test_recompute_formula_drift_is_named(tmp_path):
    program = SCORE_PROGRAM.replace(
        "(Base Score + Bonus) × (1 + Acclaim)",
        "(Base Score + Bonus) × Acclaim")
    problems = recompute_findings(tmp_path, program=program)
    assert any("no longer appears in 'Score the Entry'" in f.detail
               for f in problems)


def test_recompute_malformed_declaration_is_an_error(tmp_path):
    keys = {"The scored examples recompute": ("Score the Entry", {
        "derives": "recompute", "table": "data/scored_examples.csv",
        KEY_JSON_PROP: "{}"})}
    [finding] = recompute_findings(tmp_path, keys=keys)
    assert finding.severity == "error"
    assert "needs components" in finding.detail
