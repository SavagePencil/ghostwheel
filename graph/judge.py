"""The claim-diff judge: the functional-parity bar's primary instrument.

A standalone organ with a fixed contract — texts in, verdicts
out — consumed by the round-trip harness and reused verbatim as
the exam's objective grader (Phase 3). The bar (the grading-bar ruling):
no factual data lost, omitted unapproved, or mistranslated — structure,
wording, and format free to improve. Verdict vocabulary:

- MATCHED            — the claim survives regeneration
- OMITTED_APPROVED   — absent, and an Approved Omission row covers it
                       (an editorial choice on the record; passes forever)
- OMITTED_UNAPPROVED — absent with no ruling behind it: RED
- INVENTED           — the regeneration asserts what the original never
                       did: always RED
- DISTORTED          — present on both sides but the content moved: RED

v0 is deliberately mechanical-but-honest: claims are normalized
declarative sentences; exact-normalized equality is MATCHED; the best
token-overlap pairing above a threshold is DISTORTED (both sides shown);
the rest fall to omitted/invented. Early runs will over-flag rewordings
as distorted — that is where the convergence loop and the approver's
spot-checks (D13) enter. A smarter matcher may replace the internals
later; the fixtures pin this contract, not the smarts.

Approved omissions are graph citizens (Judgment stratum, label
"[Approved Omission]", source data/approved-omissions.csv); the judge
consults the same rows the graph holds.
"""

import re
from dataclasses import dataclass, field

MATCHED = "matched"
OMITTED_APPROVED = "omitted-approved"
OMITTED_UNAPPROVED = "omitted-unapproved"
INVENTED = "invented"
DISTORTED = "distorted"

RED_VERDICTS = (OMITTED_UNAPPROVED, INVENTED, DISTORTED)

# best token-overlap (Jaccard) at or above this pairs two claims as one
# DISTORTED claim rather than an omitted + invented pair
DISTORTION_FLOOR = 0.5

# A period ends a sentence unless it closes a known abbreviation —
# "A vs. B" is one claim, not two fragments.
_SENTENCE_END = re.compile(
    r"(?<=[.!?])(?<!\bvs\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)\s+")
_MARKUP = re.compile(r"[*_`#>|]")
_HORIZONTAL_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
# a markdown link or image: the text survives the fold as prose, the
# target never does (a pointer is not wording)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# a unit that is nothing but links (a table of contents entry, a
# navigation list item, a bare image) — structure pointing at content,
# asserting nothing
_PURE_LINKS = re.compile(r"^\s*(?:!?\[[^\]]*\]\([^)]*\)\s*[,;:]?\s*)+$")
_LIST_MARKER = re.compile(r"^\s*(?:[-+*]|\d+\.)\s+(.*)$")


@dataclass
class Verdict:
    verdict: str
    original: str = ""      # the original claim ("" for INVENTED)
    regenerated: str = ""   # the regeneration's claim ("" for omissions)

    @property
    def red(self):
        return self.verdict in RED_VERDICTS

    def row(self):
        """The verdict as a record: its verdict IS its code, with the
        designer-facing ref beside it and both claims as particulars."""
        from .report import ref_key
        return {"code": self.verdict, "ref": ref_key(self.verdict),
                "red": self.red, "original": self.original,
                "regenerated": self.regenerated}


@dataclass
class Scorecard:
    verdicts: list = field(default_factory=list)

    def count(self, verdict):
        return sum(1 for v in self.verdicts if v.verdict == verdict)

    @property
    def red(self):
        return [v for v in self.verdicts if v.red]

    @property
    def passed(self):
        return not self.red

    def rows(self):
        return [v.row() for v in self.verdicts]

    def report(self, title="Claim-diff verdict"):
        """The scorecard as one record: counts per verdict, the pass
        flag, and every verdict as a row — the prose report renders
        from this."""
        return {"kind": "claim-diff-report", "title": title,
                "passed": self.passed,
                "counts": {verdict: self.count(verdict)
                           for verdict in (MATCHED, DISTORTED,
                                           OMITTED_UNAPPROVED,
                                           OMITTED_APPROVED, INVENTED)},
                "verdicts": self.rows()}


def claims_of(text):
    """Prose -> normalized declarative claims, one per sentence.

    Headings are structure, not claims — dropped. Hard-wrapped lines
    rejoin within their paragraph (a sentence broken across lines is one
    claim); a list item starts a new unit. Markup folds, whitespace
    collapses, case and trailing punctuation normalize — wording
    survives, formatting does not (the bar frees formatting). A link
    folds to its text (the target is a pointer, never wording), and a
    unit that is nothing but links — a table-of-contents entry, a
    navigation bullet, a bare image — is structure pointing at content
    and asserts nothing: no claim."""
    units = []
    current = []

    def flush():
        if current:
            units.append(" ".join(current))
            current.clear()

    for raw_line in text.splitlines():
        if re.match(r"^\s*#{1,6}\s", raw_line) or \
                _HORIZONTAL_RULE.match(raw_line):
            flush()
            continue  # headings and dividers are structure, never claims
        # the list marker is read on the RAW line, before any fold, so a
        # star bullet is a list item like a dash bullet (the fold would
        # otherwise eat the star and glue the item to its neighbour)
        marker = _LIST_MARKER.match(raw_line)
        content = marker.group(1) if marker else raw_line
        if _PURE_LINKS.match(content):
            flush()
            continue  # a pure link points at content; it asserts nothing
        line = _MARKUP.sub("", _LINK.sub(r"\1", content)).strip()
        if not line:
            flush()
            continue
        if marker:
            flush()
        current.append(line)
    flush()

    claims = []
    for unit in units:
        for sentence in _SENTENCE_END.split(unit):
            normalized = normalize(sentence)
            if normalized:
                claims.append(normalized)
    return claims


def normalize(sentence):
    """The comparison key: case, whitespace, and trailing punctuation
    fold away — and so does link markup, the same fold extraction
    applies. The rule this encodes: any fold that lands in extraction
    must land here too, because extraction changes a claim's IDENTITY
    and recorded provenance is keyed by that identity. A claim recorded
    under an older grain (its brackets intact) and the same claim read
    today (its link folded) must compare equal, or a record would go
    stale when nothing but the extractor moved."""
    words = _LINK.sub(r"\1", sentence).strip().rstrip(".!?").split()
    return " ".join(word.lower() for word in words)


def _overlap(a, b):
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def judge(original_text, regenerated_text, approved_omissions=()):
    """The organ's contract: two prose texts and the approved-omission
    claims; out comes the scorecard. approved_omissions entries are
    matched after the same normalization the claims get."""
    originals = claims_of(original_text)
    regenerated = claims_of(regenerated_text)
    approved = {normalize(entry) for entry in approved_omissions}

    remaining = list(regenerated)
    verdicts = []
    unmatched_originals = []
    for claim in originals:
        if claim in remaining:
            remaining.remove(claim)
            verdicts.append(Verdict(MATCHED, claim, claim))
        else:
            unmatched_originals.append(claim)

    # pair leftovers by best token overlap: content that moved is ONE
    # distorted claim, not an omission plus an invention
    for claim in list(unmatched_originals):
        best, best_score = None, 0.0
        for candidate in remaining:
            score = _overlap(claim, candidate)
            if score > best_score:
                best, best_score = candidate, score
        if best is not None and best_score >= DISTORTION_FLOOR:
            remaining.remove(best)
            unmatched_originals.remove(claim)
            verdicts.append(Verdict(DISTORTED, claim, best))

    for claim in unmatched_originals:
        if claim in approved:
            verdicts.append(Verdict(OMITTED_APPROVED, claim))
        else:
            verdicts.append(Verdict(OMITTED_UNAPPROVED, claim))
    for claim in remaining:
        verdicts.append(Verdict(INVENTED, regenerated=claim))
    return Scorecard(verdicts)


def render_report(scorecard, title="Claim-diff verdict"):
    """The human-facing verdict: counts first, every red named — a
    rendering of the scorecard's record (Scorecard.report)."""
    doc = scorecard.report(title) if isinstance(scorecard, Scorecard) \
        else scorecard
    counts = doc["counts"]
    lines = [f"# {doc['title']}", ""]
    lines.append(
        f"**{counts[MATCHED]} matched · "
        f"{counts[DISTORTED]} distorted · "
        f"{counts[OMITTED_UNAPPROVED]} omitted (unapproved) · "
        f"{counts[OMITTED_APPROVED]} omitted (approved) · "
        f"{counts[INVENTED]} invented**")
    lines.append("")
    if doc["passed"]:
        lines += ["PASS — every claim accounted for.", ""]
        return "\n".join(lines)
    lines += ["FAIL — the differences, named:", ""]
    for row in doc["verdicts"]:
        if not row["red"]:
            continue
        if row["code"] == DISTORTED:
            lines.append(f"- DISTORTED — original: \"{row['original']}\" "
                         f"→ regenerated: \"{row['regenerated']}\"")
        elif row["code"] == OMITTED_UNAPPROVED:
            lines.append(f"- OMITTED (no approval on record): "
                         f"\"{row['original']}\" — approve the omission "
                         "(a row in data/approved-omissions.csv) or "
                         "restore the content")
        else:
            lines.append(f"- INVENTED (the original never says this): "
                         f"\"{row['regenerated']}\"")
    lines.append("")
    return "\n".join(lines)
