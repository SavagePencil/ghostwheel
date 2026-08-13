"""Ontology-declared answer keys: the generic derivation check that
replaced the hand-coded pytest functions. Fixture-driven over
self-contained imaginary corpora — a new procedure earns its fidelity
net by adding a declaration, nobody hand-writes a test."""

from graph.answer_keys import check
from graph.ontology import Category, load_ontology

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

FILES = {
    "data/vigors.csv": "Vigor\nFresh\nLimp\nDozed\n",
    "data/wilt-transitions.csv": (
        "From Vigor,To Vigor\nFresh,Limp\nLimp,Dozed\n"),
    "data/wilt-thresholds.csv": (
        "Vigor,Rot Needed\nFresh,10\nLimp,5\nDozed,N/A\n"),
    "data/procedures/wilt.yaml": PROGRAM,
}

ONTOLOGY = """\
    version: 1
    concepts:
      Tale Concept: {{ instance_of: Concept }}
    nodes:
      Vigor:
        source: data/vigors.csv
        key: Vigor
        concept: [Tale Concept, Exclusive, Stateful]
      Procedure:
        source: [data/procedures/wilt.yaml]
        reader: procedure_yaml
        concept: Procedure
    answer_keys:
{keys}
    """

GOOD_KEYS = """\
      - procedure: Wilt
        derives: transitions
        table: data/wilt-transitions.csv
        from_column: From Vigor
        to_column: To Vigor
      - procedure: Wilt
        derives: thresholds
        table: data/wilt-thresholds.csv
        key_column: Vigor
        value_column: Rot Needed
        condition_pattern: "Rot > {value}"
"""


def findings_for(make_repo, files=None, keys=GOOD_KEYS):
    base, path = make_repo(files or FILES, ONTOLOGY.format(keys=keys))
    ontology, load_findings = load_ontology(path, base)
    assert ontology is not None, load_findings
    return [f for f in check(ontology)
            if f.category == Category.ANSWER_KEY]


def test_faithful_program_verifies_clean(make_repo):
    assert findings_for(make_repo) == []


def test_table_row_the_program_lost_is_named(make_repo):
    files = dict(FILES)
    files["data/wilt-transitions.csv"] += "Dozed,Fresh\n"  # nobody derives this
    [finding] = findings_for(make_repo, files)
    assert "no longer derives the approved transition Dozed → Fresh" \
        in finding.detail


def test_transition_nobody_approved_is_named(make_repo):
    files = dict(FILES)
    files["data/wilt-transitions.csv"] = "From Vigor,To Vigor\nFresh,Limp\n"
    [finding] = findings_for(make_repo, files)
    assert "derives Limp → Dozed" in finding.detail
    assert "no such row" in finding.detail


def test_threshold_drift_is_named(make_repo):
    files = dict(FILES)
    files["data/wilt-thresholds.csv"] = (
        "Vigor,Rot Needed\nFresh,12\nLimp,5\nDozed,N/A\n")
    [finding] = findings_for(make_repo, files)
    assert "case 'Fresh'" in finding.detail
    assert '"Rot > 12"' in finding.detail


def test_empty_marker_threshold_is_no_threshold(make_repo):
    # Dozed,N/A raises nothing: the bottom rung has nowhere to go
    assert findings_for(make_repo) == []


def test_skip_values_declares_no_threshold_markers(make_repo):
    # A key may declare cell values that mean "no threshold exists"
    # beyond the global empty markers (the ♾️ cells). Without the
    # declaration the ♾️ row demands an absurd branch; with it, silence.
    files = dict(FILES)
    files["data/wilt-thresholds.csv"] = (
        "Vigor,Rot Needed\nFresh,10\nLimp,5\nDozed,+♾️\n")
    [finding] = findings_for(make_repo, files)
    assert "no branch case for 'Dozed'" in finding.detail
    keys = GOOD_KEYS.replace(
        'condition_pattern: "Rot > {value}"',
        'condition_pattern: "Rot > {value}"\n'
        '        skip_values: ["+♾️"]', 1)
    assert findings_for(make_repo, files, keys=keys) == []


def test_unknown_procedure_is_an_error(make_repo):
    keys = GOOD_KEYS.replace("procedure: Wilt", "procedure: Bloom", 1)
    [finding] = findings_for(make_repo, keys=keys)
    assert finding.severity == "error"
    assert "no transcribed procedure named 'Bloom'" in finding.detail


def test_declaration_typo_is_an_error(make_repo):
    keys = GOOD_KEYS.replace("from_column:", "from_colun:", 1)
    problems = findings_for(make_repo, keys=keys)
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


def test_second_stateful_concept_derives_without_subjects(make_repo):
    # A SECOND Exclusive+Stateful concept (Mood) is discovered from the
    # facets exactly as Vigor is — its ladder derives with no subjects
    # declared on either key. Both ladders verify clean, proving candidate
    # subjects come from the declarations, not a per-key list.
    files = dict(FILES)
    files["data/moods.csv"] = "Mood\nGrey\nBright\n"
    files["data/mood-transitions.csv"] = "From Mood,To Mood\nGrey,Bright\n"
    files["data/procedures/bloom.yaml"] = BLOOM
    keys = GOOD_KEYS + (
        "      - procedure: Bloom\n"
        "        derives: transitions\n"
        "        table: data/mood-transitions.csv\n"
        "        from_column: From Mood\n"
        "        to_column: To Mood\n")
    ontology_text = ONTOLOGY.replace(
        "      Procedure:",
        "      Mood:\n"
        "        source: data/moods.csv\n"
        "        key: Mood\n"
        "        concept: [Tale Concept, Exclusive, Stateful]\n"
        "      Procedure:").replace(
        "source: [data/procedures/wilt.yaml]",
        "source: [data/procedures/wilt.yaml, "
        "data/procedures/bloom.yaml]").format(keys=keys)
    base, path = make_repo(files, ontology_text)
    ontology, load_findings = load_ontology(path, base)
    assert ontology is not None, load_findings
    drift = [f for f in check(ontology)
             if f.category == Category.ANSWER_KEY]
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


def test_subject_branch_that_derives_nothing_is_loud(make_repo):
    # Freeze branches on Vigor (a tracked Exclusive+Stateful subject) but
    # names no become — it derives zero transitions. The old walker would
    # attest nothing in silence; now it is a named finding.
    files = dict(FILES)
    files["data/procedures/freeze.yaml"] = FREEZE
    keys = GOOD_KEYS + (
        "      - procedure: Freeze\n"
        "        derives: transitions\n"
        "        table: data/wilt-transitions.csv\n"
        "        from_column: From Vigor\n"
        "        to_column: To Vigor\n")
    ontology_text = ONTOLOGY.replace(
        "source: [data/procedures/wilt.yaml]",
        "source: [data/procedures/wilt.yaml, "
        "data/procedures/freeze.yaml]").format(keys=keys)
    base, path = make_repo(files, ontology_text)
    ontology, load_findings = load_ontology(path, base)
    assert ontology is not None, load_findings
    drift = [f for f in check(ontology)
             if f.category == Category.ANSWER_KEY]
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

RECOMPUTE_FILES = {
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
    "data/procedures/score.yaml": SCORE_PROGRAM,
}

RECOMPUTE_ONTOLOGY = """\
    version: 1
    concepts:
      Tale Concept: {{ instance_of: Concept }}
    nodes:
      Procedure:
        source: [data/procedures/score.yaml]
        reader: procedure_yaml
        concept: Procedure
    answer_keys:
{keys}
    """

RECOMPUTE_KEYS = """\
      - procedure: Score the Entry
        derives: recompute
        table: data/scored_examples.csv
        result:
          formula: "(Base Score + Bonus) * (1 + Acclaim)"
          expected_column: Expected Total Score
          floor: 0
        components:
          Base Score:
            given_column: Judge Roll
            expected_column: Expected Base Score
            lookup:
              select_by: Entry Kind
              key_from: Recipe
              variants:
                sweet:
                  table: data/sweet_recipes.csv
                  key_column: Recipe
                  value_column: Score Dice
                  parse: dice_flat
                savory:
                  table: data/savory_recipes.csv
                  key_column: Recipe
                  value_column: Score Dice
                  parse: dice_flat
          Bonus:
            pairs_column: Bonus Contributions
            suppressed_column: Suppressed Contributions
            expected_column: Expected Bonus
            pair_lookups:
              Flair:
                table: data/flair_table.csv
                key_column: Flair
                value_column: Score Boost
                gate:
                  property: Benefits from Flair
                  lookup:
                    select_by: Entry Kind
                    key_from: Recipe
                    variants:
                      sweet:
                        table: data/sweet_recipes.csv
                        key_column: Recipe
                        value_column: Traits
                      savory:
                        table: data/savory_recipes.csv
                        key_column: Recipe
                        value_column: Traits
          Acclaim:
            pairs_column: Acclaim Contributions
            expected_column: Expected Acclaim
            floor: -1
            pair_lookups:
              Ribbon:
                table: data/ribbons.csv
                key_column: Ribbon
                value_column: Boost
                parse: multiplier
                template_fallback:
                  table: data/ribbon_templates.csv
                  key_column: Ribbon Instance
                  value_column: Template
"""


def recompute_findings(make_repo, files=None, keys=RECOMPUTE_KEYS):
    base, path = make_repo(files or RECOMPUTE_FILES,
                           RECOMPUTE_ONTOLOGY.format(keys=keys))
    ontology, load_findings = load_ontology(path, base)
    assert ontology is not None, load_findings
    return [f for f in check(ontology)
            if f.category == Category.ANSWER_KEY]


def test_recompute_faithful_examples_verify_clean(make_repo):
    # covers: variant lookup + dice flat, gated pair, template fallback,
    # component floor (-1.5 → -1), result floor (-1 × 0 → 0)
    assert recompute_findings(make_repo) == []


def test_recompute_drifted_table_value_is_named(make_repo):
    files = dict(RECOMPUTE_FILES)
    files["data/flair_table.csv"] = "Flair,Score Boost\n3,-2\n16,+3\n"
    problems = recompute_findings(make_repo, files)
    assert any("claims Flair 16 contributes +2" in f.detail and
               "now says 3" in f.detail for f in problems)
    # the drifted contribution also breaks the sums downstream, by name
    assert any("recomputed Bonus = 3" in f.detail for f in problems)


def test_recompute_wrong_asserted_total_is_named(make_repo):
    files = dict(RECOMPUTE_FILES)
    files["data/scored_examples.csv"] = files[
        "data/scored_examples.csv"].replace("4,2,1,12", "4,2,1,13")
    [finding] = recompute_findings(make_repo, files)
    assert "recomputes to 12" in finding.detail
    assert "asserts 13" in finding.detail


def test_recompute_lost_gate_is_named(make_repo):
    files = dict(RECOMPUTE_FILES)
    files["data/sweet_recipes.csv"] = (
        "Recipe,Score Dice,Traits\nTart,2-7 (1d6+1),\n")
    problems = recompute_findings(make_repo, files)
    assert any("no longer bears Benefits from Flair" in f.detail
               for f in problems)


def test_recompute_broken_suppression_is_named(make_repo):
    files = dict(RECOMPUTE_FILES)
    files["data/scored_examples.csv"] = files[
        "data/scored_examples.csv"].replace(
        "First Tasting,Tart,sweet,3,Flair 16=+2,,",
        "First Tasting,Tart,sweet,3,,Flair 16,").replace(
        "4,2,1,12", "4,0,1,8")
    problems = recompute_findings(make_repo, files)
    assert any("is NOT applied" in f.detail and
               "now bears Benefits from Flair" in f.detail
               for f in problems)


def test_recompute_formula_drift_is_named(make_repo):
    files = dict(RECOMPUTE_FILES)
    files["data/procedures/score.yaml"] = SCORE_PROGRAM.replace(
        "(Base Score + Bonus) × (1 + Acclaim)",
        "(Base Score + Bonus) × Acclaim")
    problems = recompute_findings(make_repo, files)
    assert any("no longer appears in 'Score the Entry'" in f.detail
               for f in problems)


def test_recompute_malformed_declaration_is_an_error(make_repo):
    keys = "      - procedure: Score the Entry\n" \
           "        derives: recompute\n" \
           "        table: data/scored_examples.csv\n"
    [finding] = recompute_findings(make_repo, keys=keys)
    assert finding.severity == "error"
    assert "needs components" in finding.detail
