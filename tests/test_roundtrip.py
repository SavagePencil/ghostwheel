"""The round-trip harness: a reorganized-but-faithful draft passes; every
tier's failure mode reds with the difference named. Runs on a
self-contained storybook corpus — no database needed."""

import textwrap

from graph import comprehension
from graph.procedures import parse_procedure
from graph.roundtrip import judge_tables, render_report, run

DOC = """\
# Bestiary Rules

## Turn Order

In each chapter, each beast may take a turn.

The chapter is complete when all beasts have moved.

## Tempers

{{csv:data/tempers.csv|columns=Temper, Modifier}}

## Settle a Contest

Compare the beasts' tempers.
"""

TEMPERS = """\
Temper,Modifier,Hidden Note
Bold,-2,ignore me
Wary,+3,me too
"""

CONTEST = """\
procedure: Settle a Contest
specified_in:
  artifact: docs/bestiary.md
  section: Settle a Contest
possible_outcomes:
  Contest Settled:
    ends: the contest ends
    guarantee: read-only
steps:
  - compute: the higher temper modifier wins ties
  - stop: the contest ends
"""

# faithful but fully reorganized: sections renamed and merged, table
# restructured with a new column order, sentences reordered — the bar
# frees all of it. (An extra column is free ONLY when the corpus
# accounts for its cells — the additive clause.)
GOOD_DRAFT = """\
# Beasts

The chapter is complete when all beasts have moved. In each chapter, each
beast may take a turn.

| Modifier | Temper |
|----------|--------|
| -2 | Bold |
| +3 | Wary |

Compare the beasts' tempers. Compute the higher temper modifier wins
ties. Stop here — the contest ends.
"""


def corpus(write_files, doc=DOC):
    base_dir = write_files({"docs/bestiary.md": doc,
                            "data/tempers.csv": TEMPERS})
    spec, errors = parse_procedure(CONTEST)
    assert errors == []
    return base_dir, {"docs/bestiary.md": {"Settle a Contest"}}, \
        {"docs/bestiary.md": [("Settle a Contest", spec)]}


def judge_draft(write_files, draft_text, doc=DOC):
    base_dir, cited, specs = corpus(write_files, doc)
    draft = base_dir / "draft.md"
    draft.write_text(textwrap.dedent(draft_text), encoding="utf-8")
    return run(base_dir, "docs/bestiary.md", draft,
               cited_sections=cited["docs/bestiary.md"],
               cited_specs=specs["docs/bestiary.md"])


def test_reorganized_faithful_draft_passes(write_files):
    result = judge_draft(write_files, GOOD_DRAFT)
    assert result.passed, render_report(result)


def test_dropped_table_row_is_cell_loss(write_files):
    draft = GOOD_DRAFT.replace("| +3 | Wary |\n", "")
    result = judge_draft(write_files, draft)
    [table] = [t for t in result.tiers if t.tier == "table"]
    assert not table.passed
    assert "Wary" in str(table.findings[0])
    # the filtered-out column is NOT demanded of the draft
    assert not any("ignore me" in str(f)
                   for t in result.tiers for f in t.findings)


def test_split_row_values_do_not_count(write_files):
    # -2 and Bold present but in DIFFERENT rows: row integrity fails
    draft = GOOD_DRAFT.replace(
        "| -2 | Bold |",
        "| -2 | Calm |\n| 0 | Bold |")
    result = judge_draft(write_files, draft)
    [table] = [t for t in result.tiers if t.tier == "table"]
    assert not table.passed and "Bold" in str(table.findings[0])


def test_moved_value_is_distortion(write_files):
    draft = GOOD_DRAFT.replace("may take a turn", "may take two turns")
    assert draft != GOOD_DRAFT  # the mutation must actually land
    result = judge_draft(write_files, draft)
    [prose] = [t for t in result.tiers if t.tier == "rule-prose"]
    assert any("distorted" in str(f) and "two turns" in str(f)
               for f in prose.findings)


def test_invented_table_row_is_red(write_files):
    # the reverse clause: a row no source table accounts for
    draft = GOOD_DRAFT.replace(
        "| +3 | Wary |",
        "| +3 | Wary |\n| +9 | Zen |")
    assert draft != GOOD_DRAFT
    result = judge_draft(write_files, draft)
    [table] = [t for t in result.tiers if t.tier == "table"]
    assert any("invented table row" in str(f) and "Zen" in str(f)
               for f in table.findings)
    # header rows are structure, never invented data
    assert not any("Temper" in str(f) and "invented" in str(f)
                   for f in table.findings)


def test_extra_rule_is_invented(write_files):
    draft = GOOD_DRAFT + "\nA beast that flees loses its next turn.\n"
    result = judge_draft(write_files, draft)
    [invented] = [t for t in result.tiers if t.tier == "invented"]
    assert any("flees loses its next turn" in str(f)
               for f in invented.findings)


def test_dropped_procedure_step_reds_the_procedure_tier(write_files):
    draft = GOOD_DRAFT.replace(
        "Compute the higher temper modifier wins\nties. ", "")
    result = judge_draft(write_files, draft)
    [proc] = [t for t in result.tiers if t.tier == "procedure"]
    assert not proc.passed
    assert "Settle a Contest" in str(proc.findings[0])


def test_approved_omission_clears_the_red(write_files):
    draft = GOOD_DRAFT.replace(
        "The chapter is complete when all beasts have moved. ", "")
    base_dir, cited, specs = corpus(write_files)
    (base_dir / "data" / "approved-omissions.csv").write_text(
        "Omission,Scope,Decided By,Decided On,Issue,PR,Notes\n"
        "The chapter is complete when all beasts have moved.,"
        "docs/bestiary.md,Maren,2026-07-31,,,reads better without it\n",
        encoding="utf-8")
    draft_path = base_dir / "draft.md"
    draft_path.write_text(textwrap.dedent(draft), encoding="utf-8")
    result = run(base_dir, "docs/bestiary.md", draft_path,
                 cited_sections=cited["docs/bestiary.md"],
                 cited_specs=specs["docs/bestiary.md"])
    assert result.passed, render_report(result)
    [prose] = [t for t in result.tiers if t.tier == "rule-prose"]
    assert prose.approved >= 1


def test_report_names_every_red(write_files):
    draft = (GOOD_DRAFT
             .replace("| +3 | Wary |\n", "")
             .replace("may take a turn", "may take two turns"))
    result = judge_draft(write_files, draft)
    report = render_report(result)
    assert "FAIL" in report
    assert "Wary" in report and "two turns" in report


# -- cited-section prose is judged, and every PASS names its surface


SMUGGLED_DOC = DOC.replace(
    "Compare the beasts' tempers.",
    "Compare the beasts' tempers.\n\n"
    "Bold beasts may never win a contest.")


def test_rule_in_cited_section_prose_is_seen(write_files):
    # the cited-section blind spot: a rule living beside a transcribed
    # procedure must not vanish under a green scorecard
    result = judge_draft(write_files, GOOD_DRAFT, doc=SMUGGLED_DOC)
    assert not result.passed
    prose = next(t for t in result.tiers if t.tier == "rule-prose")
    assert any("bold beasts may never win" in str(f) and
               "§ Settle a Contest" in str(f) for f in prose.findings)


def test_backup_omission_row_clears_cited_prose(write_files):
    import json
    base_dir, cited, specs = corpus(write_files, SMUGGLED_DOC)
    export_dir = base_dir / "graph" / "export"
    export_dir.mkdir(parents=True)
    (export_dir / "nodes.jsonl").write_text(json.dumps(
        {"label": "[Approved Omission]",
         "name": "bold beasts may never win a contest",
         "properties": {"scope": "docs/bestiary.md"}}) + "\n",
        encoding="utf-8")
    draft = base_dir / "draft.md"
    draft.write_text(GOOD_DRAFT, encoding="utf-8")
    result = run(base_dir, "docs/bestiary.md", draft,
                 cited_sections=cited["docs/bestiary.md"],
                 cited_specs=specs["docs/bestiary.md"])
    assert result.passed
    prose = next(t for t in result.tiers if t.tier == "rule-prose")
    assert prose.approved == 1


def test_report_names_its_judged_surface(write_files):
    result = judge_draft(write_files, GOOD_DRAFT)
    report = render_report(result)
    assert "Judged surface:" in report
    assert "unjudged: none." in report


# -- findings are rows -------------------------------------------------


def test_findings_are_rows_with_sections(write_files):
    result = judge_draft(write_files, GOOD_DRAFT, doc=SMUGGLED_DOC)
    rows = result.findings_rows()
    assert rows, "expected at least the smuggled-rule finding"
    smuggled = next(r for r in rows
                    if "bold beasts" in r["original"])
    assert smuggled["tier"] == "rule-prose"
    assert smuggled["kind"] == "omitted"
    assert smuggled["section_heading"] == "Settle a Contest"
    assert smuggled["section_id"]
    assert smuggled["status"] == "open"
    assert smuggled["id"]


def test_finding_identity_is_stable_across_rejudges(write_files):
    first = judge_draft(write_files, GOOD_DRAFT, doc=SMUGGLED_DOC)
    second = judge_draft(write_files, GOOD_DRAFT, doc=SMUGGLED_DOC)
    assert [r["id"] for r in first.findings_rows()] == \
        [r["id"] for r in second.findings_rows()]


def test_findings_archive_round_trips(write_files, tmp_path):
    from graph.comprehension import (read_findings_archive,
                                     write_findings_archive)
    result = judge_draft(write_files, GOOD_DRAFT, doc=SMUGGLED_DOC)
    rows = result.findings_rows()
    write_findings_archive(tmp_path / "arch", rows)
    assert read_findings_archive(tmp_path / "arch") == \
        sorted(rows, key=lambda r: r["id"])


# -- the verbatim-carriage registry ------------------------------------


CARRIED = "the chapter is complete when all beasts have moved"


def run_with_carriage(write_files, draft_text):
    base_dir, cited, specs = corpus(write_files)
    draft = base_dir / "draft.md"
    draft.write_text(textwrap.dedent(draft_text), encoding="utf-8")
    return run(base_dir, "docs/bestiary.md", draft,
               cited_sections=cited["docs/bestiary.md"],
               cited_specs=specs["docs/bestiary.md"],
               carried_texts=[CARRIED])


def test_registered_passage_classes_as_carried(write_files):
    result = run_with_carriage(write_files, GOOD_DRAFT)
    assert result.passed
    carried = next(t for t in result.tiers
                   if t.tier == "verbatim-carried")
    assert carried.checked == 1
    assert "verbatim-carried" in result.surface


def test_paraphrased_carried_passage_reds_byte_carriage(write_files):
    # a paraphrase that would PASS as matched prose must fail carriage:
    # the ruling says word-for-word, and the judge now holds it to that
    draft = GOOD_DRAFT.replace(
        "The chapter is complete when all beasts have moved.",
        "The chapter is over when every beast has moved.")
    assert "chapter is over" in draft
    result = run_with_carriage(write_files, draft)
    carried = next(t for t in result.tiers
                   if t.tier == "verbatim-carried")
    assert any(f.kind == "missing-carried" for f in carried.findings)


def test_registry_reads_verbatim_rows_from_backup(write_files):
    import json
    from graph.roundtrip import carried_passages_for
    base_dir = write_files({"docs/x.md": "# X"})
    export_dir = base_dir / "graph" / "export"
    export_dir.mkdir(parents=True)
    rows = [
        {"label": "Verbatim", "name": "carry me exactly",
         "properties": {"medium": "text", "scope": "docs/x.md"}},
        {"label": "Verbatim", "name": "an image region",
         "properties": {"medium": "image", "scope": "docs/x.md"}},
        {"label": "Verbatim", "name": "someone else's passage",
         "properties": {"medium": "text", "scope": "docs/other.md"}},
    ]
    (export_dir / "nodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert carried_passages_for(base_dir, "docs/x.md") == \
        ["carry me exactly"]


def test_registry_prefers_original_bytes_over_normalized_key(write_files):
    # casing is information: when a row carries the original bytes in its
    # text property, regeneration reads those; the lowercased name stays
    # a matching key only
    import json
    from graph.roundtrip import carried_passages_for
    base_dir = write_files({"docs/x.md": "# X"})
    export_dir = base_dir / "graph" / "export"
    export_dir.mkdir(parents=True)
    rows = [
        {"label": "Verbatim", "name": "pip greets the lantern keeper",
         "properties": {"medium": "text", "scope": "docs/x.md",
                        "text": "Pip greets the Lantern Keeper"}},
        {"label": "Verbatim", "name": "no bytes recorded yet",
         "properties": {"medium": "text", "scope": "docs/x.md"}},
    ]
    (export_dir / "nodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert carried_passages_for(base_dir, "docs/x.md") == \
        ["Pip greets the Lantern Keeper", "no bytes recorded yet"]


# -- the additive clause -----------------------------------------------


def test_smuggled_cell_in_matched_row_is_red(write_files):
    # the catch: a value from nowhere riding a key-matched row
    draft = GOOD_DRAFT.replace("| -2 | Bold |",
                               "| -2 | Bold | rusty |")
    assert "rusty" in draft
    result = judge_draft(write_files, draft)
    [table] = [t for t in result.tiers if t.tier == "table"]
    assert any(f.kind == "additive-cells" and "rusty" in str(f)
               for f in table.findings)


def test_corpus_accounted_extra_cell_stays_free(write_files):
    # restructuring latitude survives: merging a canon-held fact into a
    # table is fine — the corpus accounts for the cell
    draft = GOOD_DRAFT.replace(
        "| +3 | Wary |",
        "| +3 | Wary | each beast may take a turn |")
    result = judge_draft(write_files, draft)
    [table] = [t for t in result.tiers if t.tier == "table"]
    assert not any(f.kind == "additive-cells" for f in table.findings)


# -- type-aware column equivalence -------------------------------------
# Imaginary domain (an engine test speaks no project vocabulary): a table
# with a numeric, a boolean, and an edge-carried multi-value column, judged
# by the kinds a declaration would type them.

TYPED = "K,Num,Flag,Parts\nrow,+2,Y,\"alpha, beta\"\n"
TYPED_KINDS = {("data/typed.csv", "Num"): "int",
              ("data/typed.csv", "Flag"): "bool",
              ("data/typed.csv", "Parts"): "set"}


def _typed_sections(relpath="data/typed.csv"):
    return [{"id": "s", "heading": "H",
             "spans": [{"class": comprehension.TABLE, "table": relpath,
                        "text": "{{csv:%s}}" % relpath}]}]


def _typed_repo(write_files, csv=TYPED):
    base_dir = write_files({"data/typed.csv": csv})
    return base_dir


def test_typed_columns_compare_by_value_not_bytes(write_files):
    base_dir = _typed_repo(write_files)
    # a draft that renders the SAME values in different surface forms:
    # 2 for +2, true for Y, the set in the other order
    draft = "| a | b | c | d |\n|---|---|---|---|\n| row | 2 | true | beta, alpha |\n"
    result = judge_tables(_typed_sections(), base_dir, draft,
                          col_types=TYPED_KINDS)
    assert result.passed, [str(f) for f in result.findings]
    assert result.checked == 1


def test_without_typing_the_same_draft_reds_byte_exact(write_files):
    # the typing is what relaxes equality: byte-exact, +2 != 2
    base_dir = _typed_repo(write_files)
    draft = "| a | b | c | d |\n|---|---|---|---|\n| row | 2 | true | beta, alpha |\n"
    result = judge_tables(_typed_sections(), base_dir, draft)  # no col_types
    assert not result.passed


def test_changed_number_still_reds_under_typing(write_files):
    base_dir = _typed_repo(write_files)
    draft = "| a | b | c | d |\n|---|---|---|---|\n| row | 3 | true | alpha, beta |\n"
    result = judge_tables(_typed_sections(), base_dir, draft,
                          col_types=TYPED_KINDS)
    assert any(f.kind == "cell-loss" for f in result.findings)


def test_dropped_set_element_still_reds_under_typing(write_files):
    base_dir = _typed_repo(write_files)
    draft = "| a | b | c | d |\n|---|---|---|---|\n| row | 2 | Y | alpha |\n"
    result = judge_tables(_typed_sections(), base_dir, draft,
                          col_types=TYPED_KINDS)
    assert any(f.kind == "cell-loss" for f in result.findings)


def test_altered_prose_still_reds_under_typing(write_files):
    # a text column (K) stays byte-exact even when others are typed
    base_dir = _typed_repo(write_files)
    draft = "| a | b | c | d |\n|---|---|---|---|\n| ROW | 2 | Y | alpha, beta |\n"
    result = judge_tables(_typed_sections(), base_dir, draft,
                          col_types=TYPED_KINDS)
    assert any(f.kind == "cell-loss" for f in result.findings)


def test_approved_difference_clears_both_sides(write_files):
    # the owner ruled a corrected rendering: the original's wording is
    # excused from omission/distortion AND the rendering from invention
    import json
    base_dir, cited, specs = corpus(write_files, SMUGGLED_DOC)
    export_dir = base_dir / "graph" / "export"
    export_dir.mkdir(parents=True)
    (export_dir / "nodes.jsonl").write_text(json.dumps(
        {"label": "Approved Difference",
         "name": "Bold beasts may never win a contest.",
         "properties": {"scope": "docs/bestiary.md",
                        "original": "bold beasts may never win a contest"}})
        + "\n", encoding="utf-8")
    draft = base_dir / "draft.md"
    draft.write_text(GOOD_DRAFT, encoding="utf-8")
    result = run(base_dir, "docs/bestiary.md", draft,
                 cited_sections=cited["docs/bestiary.md"],
                 cited_specs=specs["docs/bestiary.md"])
    assert result.passed
    prose = next(t for t in result.tiers if t.tier == "rule-prose")
    assert prose.approved >= 1


def test_difference_matching_is_containment_not_equality():
    # one ruled row covers every claim of a reworked passage
    from graph.roundtrip import (TierResult, RoundFinding,
                                 apply_approved_differences)
    tier = TierResult("rule-prose")
    tier.findings = [
        RoundFinding(tier="rule-prose", kind="omitted", message="m",
                     original="the OLD example's second sentence."),
        RoundFinding(tier="rule-prose", kind="omitted", message="m",
                     original="something genuinely missing"),
    ]
    apply_approved_differences(
        [tier],
        originals=["First sentence. The old example's second sentence. "
                   "Third sentence."],
        renderings=[])
    assert [f.original for f in tier.findings] == \
        ["something genuinely missing"]
    assert tier.approved == 1
