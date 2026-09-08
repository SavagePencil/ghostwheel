"""The Finding fleet and the parity report join the record shape.

Findings (derivation / roster / sweep) carry a verdict code — their
category, unless a site earned a finer one — and a standalone remedy,
and render as rows; the two string-collapse boundaries (the delta
gate's roster findings, the succession gate's re-derivation findings)
pass the findings through typed. The parity judge's scorecard and the
round-trip scorecard likewise render from their own rows, byte-stable
against goldens captured from the renderers before the change, with a
JSON record beside the prose.
"""

import json
import tempfile
from pathlib import Path

import tests.conftest as conftest
from graph.extract import GraphData, procedure_roster_findings
from graph.judge import (DISTORTED, INVENTED, MATCHED, OMITTED_APPROVED,
                         OMITTED_UNAPPROVED, judge)
from graph.judge import render_report as render_judge
from graph.ontology import ERROR, WARNING, Category, Finding
from graph.report import REF_KEYS, record_path
from graph.roundtrip import (ROUNDTRIP_REPORT_FILE, RoundFinding,
                             roundtrip_report)
from graph.roundtrip import render_report as render_roundtrip
from graph.succession import checklist_report
from tests.test_judge import ORIGINAL
from tests.test_roundtrip import GOOD_DRAFT, SMUGGLED_DOC, corpus, judge_draft

GOLDEN = Path(__file__).resolve().parent / "golden"
_make_repo = getattr(conftest.make_repo, "__wrapped__", conftest.make_repo)


def golden(name):
    return (GOLDEN / name).read_text(encoding="utf-8")


# -- the Finding record ----------------------------------------------------


def test_a_finding_s_category_is_its_code_unless_it_earned_a_finer_one():
    plain = Finding(WARNING, Category.UNPARSED_CELL, "data/herbs.csv",
                    "row 5", "kept verbatim")
    row = plain.row()
    assert row["code"] == "unparsed-cell" and row["ref"] == "kept-as-written"
    assert row["message"] == "kept verbatim" and "remedy" not in row
    assert row["severity"] == "warning" and row["category"] == "unparsed-cell"
    finer = Finding(ERROR, Category.ROSTER, "programs/x.yaml", "-",
                    "the file shipped without its node.",
                    code="roster-gap", remedy="Land the citizen.")
    row = finer.row(kb="storybook", branch="rebuild")
    assert row["code"] == "roster-gap" and row["ref"] == "missing-entry"
    assert row["remedy"] == "Land the citizen."
    assert row["kb"] == "storybook" and row["branch"] == "rebuild"
    # positional construction from before the record shape still works
    assert Finding("info", "overlay", "f", "l", "d").row()["ref"] == \
        "overlay-problem"


def test_every_category_has_a_designer_safe_ref():
    for category in Category:
        assert str(category) in REF_KEYS, category


def test_the_roster_gap_is_the_roster_category_s_earned_code():
    # a registered program file with no citizen to match: the roster
    # census names it with the roster category's one earned finer code
    from graph.ontology import ontology_from_graph
    from tests.test_branch import STORYBOOK, build_canon
    canon = build_canon()
    canon.ensure_node(
        "Archetype", "Ritual",
        spec_json=json.dumps({"key": "Ritual", "reader": "procedure_yaml",
                              "source": ["data/rituals/first-light.yaml"]},
                             sort_keys=True))
    ontology = ontology_from_graph(canon, STORYBOOK)
    assert ontology is not None
    [finding] = procedure_roster_findings(ontology, GraphData())
    assert finding.category == Category.ROSTER
    assert finding.code == "roster-gap"
    assert finding.remedy == "Land the citizen through the delta path."
    assert finding.row()["ref"] == "missing-entry"
    assert finding.detail.endswith(finding.remedy)  # detail byte-stable


# -- the typed pass-throughs ------------------------------------------------


def test_succession_checklist_carries_findings_as_rows(tmp_path):
    finding = Finding(ERROR, Category.ROSTER, "programs/x.yaml", "-",
                      "shipped without its node.", code="roster-gap",
                      remedy="Land the citizen.")
    gates = [("backup readable", "canon-backup-unreadable", []),
             ("re-derivation clean", "rederivation-error",
              ["programs/x.yaml -: shipped without its node."], [finding])]
    doc = checklist_report(tmp_path, "rebuild", gates, True, [])
    clean, derive = doc["gates"]
    assert clean["status"] == "pass" and "findings" not in clean
    assert derive["status"] == "fail"
    assert derive["problems"] == ["programs/x.yaml -: shipped without its "
                                  "node."]
    [row] = derive["findings"]
    assert row["code"] == "roster-gap" and row["remedy"] == "Land the citizen."
    assert row["branch"] == "rebuild"


# -- the judge renders from its rows ---------------------------------------


def test_judge_report_is_byte_stable_and_rows_carry_refs():
    regenerated = (ORIGINAL.replace("takes 2 turns", "takes 3 turns")
                   .replace("Failures carry over to\nthe next chapter.\n", "")
                   + "\nGryphons never sleep.\n")
    card = judge(ORIGINAL, regenerated)
    assert render_judge(card) == golden("judge-report.md")
    doc = card.report()
    assert doc["kind"] == "claim-diff-report" and not doc["passed"]
    assert doc["counts"][DISTORTED] == 1
    assert doc["counts"][INVENTED] == 1
    refs = {row["code"]: row["ref"] for row in doc["verdicts"]}
    assert refs[DISTORTED] == "changed-meaning"
    assert refs[INVENTED] == "never-said"
    assert refs[MATCHED] == "kept"
    assert all(row["red"] == (row["code"] in
                              (DISTORTED, INVENTED, OMITTED_UNAPPROVED))
               for row in doc["verdicts"])
    # the renderer accepts the record itself
    assert render_judge(doc) == golden("judge-report.md")
    for code in (MATCHED, OMITTED_APPROVED, OMITTED_UNAPPROVED, INVENTED,
                 DISTORTED):
        assert code in REF_KEYS


# -- the round-trip scorecard renders from its rows ------------------------


def _judged(draft, doc=None):
    tmp = Path(tempfile.mkdtemp())
    kwargs = {"doc": doc} if doc else {}
    return judge_draft(_make_repo(tmp), draft, **kwargs)


def test_roundtrip_markdown_is_byte_stable_against_the_captured_goldens():
    red = _judged(GOOD_DRAFT.replace("| +3 | Wary |\n", "")
                  .replace("may take a turn", "may take two turns"))
    assert render_roundtrip(red) == golden("roundtrip-report-red.md")
    smuggled = _judged(GOOD_DRAFT, SMUGGLED_DOC)
    assert render_roundtrip(smuggled) == golden("roundtrip-report-smuggled.md")
    green = _judged(GOOD_DRAFT)
    assert render_roundtrip(green) == golden("roundtrip-report-green.md")


def test_roundtrip_record_carries_tiers_findings_and_surface():
    result = _judged(GOOD_DRAFT, SMUGGLED_DOC)
    doc = roundtrip_report(result)
    assert doc["kind"] == "roundtrip-report" and not doc["passed"]
    assert doc["scope"] == result.scope and doc["fingerprint"]
    prose = next(t for t in doc["tiers"] if t["tier"] == "rule-prose")
    assert not prose["passed"] and prose["checked"] >= 1
    [row] = prose["findings"]
    assert row["code"] == "omitted" and row["ref"] == "left-out"
    assert row["kind"] == "omitted" and row["id"]  # the archive keys survive
    assert "bold beasts" in row["original"]
    assert doc["surface"].startswith("Judged surface:")
    assert "census" not in doc  # no canon backup in this repo


def test_roundtrip_cli_files_the_record(tmp_path, monkeypatch, capsys):
    import graph.__main__ as main_mod
    base_dir, cited, specs = corpus(_make_repo(tmp_path))
    draft = base_dir / "draft.md"
    draft.write_text(GOOD_DRAFT, encoding="utf-8")
    # the reading room is a database; the CLI tolerates its absence
    monkeypatch.setattr("graph.comprehension.room_session",
                        lambda config: (_ for _ in ()).throw(
                            RuntimeError("no room here")))
    main_mod.cmd_roundtrip(base_dir, "docs/bestiary.md", str(draft))
    out = capsys.readouterr().out
    assert "Round-trip parity scorecard" in out
    record = json.loads(record_path(base_dir, ROUNDTRIP_REPORT_FILE)
                        .read_text(encoding="utf-8"))
    assert record["kind"] == "roundtrip-report"
    assert record["scope"] == "docs/bestiary.md" and record["fingerprint"]
    assert {t["tier"] for t in record["tiers"]} >= {"rule-prose"}
    # the screen and the record agree on the verdict
    assert ("**PASS**" in out) == record["passed"]


def test_every_round_finding_kind_has_a_designer_safe_ref():
    import inspect
    import re

    import graph.roundtrip as roundtrip_module
    kinds = set(re.findall(r'kind="([a-z-]+)"',
                           inspect.getsource(roundtrip_module)))
    assert kinds >= {"omitted", "distorted", "invented", "cell-loss"}
    assert kinds <= set(REF_KEYS), sorted(kinds - set(REF_KEYS))
    row = RoundFinding("rule-prose", "cell-loss", "a value vanished").row()
    assert row["code"] == "cell-loss" and row["ref"] == "value-lost"
