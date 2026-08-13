"""The claim-diff judge: the functional-parity bar's verdict vocabulary,
pinned by fixtures. The contract these tests define is what the round-trip
harness consumes and the exam grader reuses."""

from graph.judge import (DISTORTED, INVENTED, MATCHED, OMITTED_APPROVED,
                         OMITTED_UNAPPROVED, claims_of, judge,
                         render_report)

ORIGINAL = """\
Each Beast that is neither Weary nor Spent takes a turn.

Grade checks happen at the end of the chapter. Failures carry over to
the next chapter.

The Awakening of a Gryphon takes 2 turns.
"""


def test_reworded_structure_still_matches():
    # the bar frees structure, wording of the ATOMS held: same sentences
    # in different order, different markup, one list re-formatted
    regenerated = """\
## Turns

- Grade checks happen at the end of the chapter.
- **Each Beast that is neither Weary nor Spent takes a turn.**

The Awakening of a Gryphon takes 2 turns. Failures carry over to the
next chapter.
"""
    card = judge(ORIGINAL, regenerated)
    assert card.passed
    assert card.count(MATCHED) == 4


def test_invention_is_always_red():
    regenerated = ORIGINAL + "\nA hidden door always opens.\n"
    card = judge(ORIGINAL, regenerated)
    assert not card.passed
    [red] = card.red
    assert red.verdict == INVENTED
    assert "hidden door" in red.regenerated


def test_unapproved_omission_is_red_and_approval_clears_it():
    regenerated = ORIGINAL.replace(
        "The Awakening of a Gryphon takes 2 turns.\n", "")
    card = judge(ORIGINAL, regenerated)
    assert [v.verdict for v in card.red] == [OMITTED_UNAPPROVED]
    # the same run with the omission approved passes forever after
    approved = judge(ORIGINAL, regenerated,
                     approved_omissions=[
                         "The Awakening of a Gryphon takes 2 turns."])
    assert approved.passed
    assert approved.count(OMITTED_APPROVED) == 1


def test_distortion_pairs_both_sides():
    regenerated = ORIGINAL.replace("takes 2 turns", "takes 5 turns")
    card = judge(ORIGINAL, regenerated)
    [red] = card.red
    assert red.verdict == DISTORTED
    assert "2 turns" in red.original and "5 turns" in red.regenerated


def test_unrelated_content_is_not_paired_as_distortion():
    regenerated = ORIGINAL.replace(
        "The Awakening of a Gryphon takes 2 turns.",
        "Lanterns flicker along the harbor wall.")
    card = judge(ORIGINAL, regenerated)
    verdicts = sorted(v.verdict for v in card.red)
    assert verdicts == [INVENTED, OMITTED_UNAPPROVED]


def test_claims_normalize_markup_case_and_lists():
    text = "- **Frost** settles for 1 turn!\n"
    assert claims_of(text) == ["frost settles for 1 turn"]


def test_report_names_every_red():
    regenerated = (ORIGINAL
                   .replace("takes 2 turns", "takes 5 turns")
                   + "\nA hidden door always opens.\n")
    report = render_report(judge(ORIGINAL, regenerated))
    assert "FAIL" in report
    assert "DISTORTED" in report and "5 turns" in report
    assert "INVENTED" in report and "hidden door" in report


def test_empty_regeneration_omits_everything():
    card = judge(ORIGINAL, "")
    assert card.count(OMITTED_UNAPPROVED) == len(claims_of(ORIGINAL))
    assert not card.passed


def test_abbreviations_do_not_split_sentences():
    # "a Contest vs. Frost" is one claim, not a fragment pair
    claims = claims_of("The Gryphon is tested through a Contest vs. "
                       "Frost at the end of the chapter.")
    assert claims == ["the gryphon is tested through a contest vs. "
                      "frost at the end of the chapter"]


def test_horizontal_rules_are_structure_not_claims():
    claims = claims_of("A real claim.\n\n---\n\nAnother claim.")
    assert claims == ["a real claim", "another claim"]
