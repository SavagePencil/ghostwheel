"""A boolean claim reads through the intake's own lens.

A tick mark is a rendering decision based on a bool, not an embedded
fact: the intake's own parser turned those cells into booleans, so
attribution reads them back through the same lens — a fact-grain
claim whose terminal token parses as a boolean value-matches the
exactly-named citizen's stored bool, first-class from the live graph,
no ledger required. The parsed value must AGREE with the stored one
(a tick against a stored False surfaces as an honest gap, never a
silent pass), the full-name anchor keeps a neighbor from stealing the
home, and a recorded ledger row still outranks the matcher entirely.

Storybook domain: the kettles of Hearth, ticked honestly.
"""

from graph.attribution import (ATTRIBUTED, CANON_GAP, PROPERTIES,
                               CanonIndex, RECORDED, census)
from tests.test_branch import build_canon


def _canon():
    canon = build_canon()
    canon.ensure_node("Tool", "Hearth Kettle",
                      brews_tea=True, holds_embers=False)
    canon.ensure_node("Tool", "Kettle", brews_tea=True)
    canon.ensure_node("Tool", "Ladle", weight=1)
    return canon


def test_a_tick_claim_attributes_first_class_with_no_ledger():
    index = CanonIndex(_canon())
    verdict = index.attribute("The Brews Tea of Tool Hearth Kettle is ✓.")
    assert verdict.verdict == ATTRIBUTED
    assert verdict.rung == PROPERTIES
    assert verdict.citizens[0] == ("Tool", "Hearth Kettle")
    assert "bool" in verdict.evidence


def test_the_fully_named_citizen_outranks_its_neighbor():
    # the wrong-home shape: a neighbor whose name is contained in the
    # subject's must never outrank the citizen the claim names whole
    index = CanonIndex(_canon())
    verdict = index.attribute("The Brews Tea of Tool Hearth Kettle is ✓.")
    assert verdict.citizens[0] == ("Tool", "Hearth Kettle")


def test_the_tick_and_the_stored_bool_must_agree():
    index = CanonIndex(_canon())
    # ✓ against a stored False: an honest gap, never a silent pass
    disagree = index.attribute(
        "The Holds Embers of Tool Hearth Kettle is ✓.")
    assert disagree.verdict == CANON_GAP
    # the explicit false mark against the stored False attributes
    agree = index.attribute("The Holds Embers of Tool Hearth Kettle is ✗.")
    assert agree.verdict == ATTRIBUTED
    assert agree.citizens[0] == ("Tool", "Hearth Kettle")
    assert "bool" in agree.evidence


def test_the_lens_is_the_intakes_own():
    index = CanonIndex(_canon())
    for mark in ("Y", "TRUE", "✔", "yes"):
        verdict = index.attribute(
            f"The Brews Tea of Tool Hearth Kettle is {mark}.")
        assert verdict.verdict == ATTRIBUTED, mark
        assert "bool" in verdict.evidence, mark
    # a terminal token the lens does not read never fires the arm
    off = index.attribute("The Brews Tea of Tool Hearth Kettle is warm.")
    assert off.verdict == CANON_GAP


def test_a_truth_word_off_the_value_seat_never_fires():
    index = CanonIndex(_canon())
    verdict = index.attribute(
        "The true brews tea of Tool Hearth Kettle is warm.")
    assert verdict.verdict == CANON_GAP


def test_census_reads_a_tick_table_and_the_ledger_still_wins():
    canon = _canon()
    draft = ("# Tools of the Hearth\n\n"
             "| Tool | Brews Tea |\n"
             "| --- | --- |\n"
             "| Hearth Kettle | ✓ |\n")
    [verdict] = census(draft, canon)
    assert verdict.verdict == ATTRIBUTED
    assert verdict.rung == PROPERTIES
    assert verdict.citizens[0] == ("Tool", "Hearth Kettle")
    # a recorded row for the same claim never meets the matcher
    link = {"claim": "The Brews Tea of Tool Hearth Kettle is ✓.",
            "citizens": [("Tool", "Kettle")], "source": "the-tale"}
    [recorded] = census(draft, canon, links=[link])
    assert recorded.verdict == RECORDED
    assert recorded.citizens == [("Tool", "Kettle")]


def test_a_numeric_claim_still_rides_the_value_arm():
    index = CanonIndex(_canon())
    verdict = index.attribute("The Weight of Tool Ladle is 1.")
    assert verdict.verdict == ATTRIBUTED
    assert verdict.citizens[0] == ("Tool", "Ladle")
    assert "value" in verdict.evidence
