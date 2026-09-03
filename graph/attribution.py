"""Canon attribution: every draft claim seeks its graph home.

The parity harness proves draft ≡ original; nothing proved draft ⊆
canon — a draft could reach green while much of its prose had no graph
home, leaving canon decorative. This module closes the triangle: every
claim in a draft is attributed against the canon graph, and a claim
that passes parity but has no home is a HOLE IN CANON, detected
automatically. The attribution harness doubles as the canon-
completeness prober, and the graded citations map where canon is still
prose soup.

The source ladder (owner-ruled, 2026-08-11) — the rung rides the
verdict as its confidence, upgradeable by more facts, escalated on
ambiguity:

- ``properties``: the claim matches a citizen's name plus its
  structured property values — the fact is first-class.
- ``receipt``: the claim is found in a citizen's carried sentence
  receipts (from_text) — sentence-grain prose owned by a citizen. A
  row-shaped from_text is never indexed (the row-receipt retirement):
  a table row is presentation, its facts belong in structured
  properties, and skipping it lets the honest homes beneath surface.
- ``prose``: the claim is found only in long-prose properties
  (description / doc / text / body / notes) — the soup rung: an honest
  home, and a named intake debt.
- no rung: no home anywhere.

Verdicts join parity: a homed claim is ATTRIBUTED (at its rung); a
homeless claim that parity proved present in the original is a
CANON GAP (surfaces, never blocks — the owner judges severity from the
report); a homeless claim parity called invented is an UNATTRIBUTED
INVENTION (a named red, presented with the artifact, never hidden).

Strong-form citation: a citation is EARNED when the cited citizen
appears in the drafter's consulted set (from its run trace). The
checker records the flag; re-deriving unearned claims is
orchestration's duty.

Matching is mechanical-but-honest (the judge's own precedent):
normalized containment and token overlap. It reads the citizens'
STRUCTURE, not just their prose — three deepenings that stay strictly
mechanical, no synonyms (that is the ruled-mappings tier, out of
scope):

- **Edge-relation matching (properties rung).** A claim that anchors
  BOTH endpoint names of a ground edge AND speaks the edge type's own
  words (its words split on underscores, lowercased — one must appear)
  attributes first-class to both endpoint citizens: the relationship
  is a structured fact, so naming it is a home. Machine-derived edge
  types attest nothing domain-level and are excluded.
- **Step-lift matching (receipt rung).** A procedure's lifted step
  text is receipt-grain prose the OWNING procedure carries; a claim
  found there attributes at receipt grade citing the procedure (the
  owning procedure is the step name's prefix before the section mark).
- **Paraphrase tolerance (properties rung).** Value matching folds
  mechanical normalizations only: a wrapping-parenthesis strip so a
  name-with-parenthetical's inner words are tokens, ONE delegated
  lemma layer (the attribution charter's rung 1: plural, possessive,
  and verb-form morphology handled by a maintained dictionary
  lemmatizer, unknown tokens passing unchanged — the engine never
  rules on a plural again), and a numeric canon (strip a leading
  plus, strip a trailing point-zero) so a claim naming a citizen plus
  a number homes on the structured value. Number-bearing tokens skip
  the lemma. No spelled-out or signed equivalences — only format and
  morphology.
- **Fact-grain fidelity (properties rung).** Three guards keep number
  claims honest: a numeric value that echoes the citizen's own name
  ("Might 7" whose cap is 7) stays matchable, but only when the claim
  says the number twice — once as the name, once as the value; an
  overlap made only of grammar words ("to") anchors nothing; and a
  citizen's property NAMES are a scored surface, so the citizen that
  owns "max body points" outranks a passer-by that merely shares a
  token.

Tables comprehend into claims: the census reads the draft's own headed
tables as fact-grain claims (see comprehension's table machinery), so
"did every number land?" is answered by this instrument — landed or
not yet landed, an intake question that surfaces and never blocks.

Pure logic, driver-free; canon is read from the committed export.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

import simplemma

from .comprehension import is_row_text, markdown_table_claims
from .judge import claims_of, normalize
from .ontology import UNAUTHORABLE_EDGE_TYPES
from .refs import CitizenRef

PROPERTIES = "properties"
RECEIPT = "receipt"
PROSE = "prose"
RUNGS = (PROPERTIES, RECEIPT, PROSE)

ATTRIBUTED = "attributed"
CANON_GAP = "canon-gap"
INVENTION = "unattributed-invention"

# best sentence-overlap at or above this counts as a textual home
ATTRIBUTION_FLOOR = 0.5

# receipt-grain text: sentence quotes a citizen carries
RECEIPT_TEXT_PROPS = ("from_text",)
# long-prose homes: the soup rung
PROSE_PROPS = ("description", "doc", "text", "body", "notes")
# provenance metadata — matching these attests nothing about content
METADATA_PROPS = frozenset({
    "source", "grade", "source_path", "approved_hash", "approved_in",
    "pr", "issue",
    "decided_by", "decided_on", "scope", "medium", "rank", "origin",
    "fingerprint", "version", "tag"})

# which structural surface a match fired on — carried on the row so the
# report can show WHY a claim found its home
EV_VALUE = "value"      # citizen name + a structured value (rung 1)
EV_EDGE = "edge"        # both endpoints of a ground edge + its type words
EV_STEP = "step"        # a procedure's lifted step text (rung 2)
EV_RECEIPT = "receipt"  # a citizen's carried from_text sentence (rung 2)
EV_PROSE = "prose"      # a long-prose home (rung 3, the soup)

# the section mark that separates a step's owning-procedure name from its
# ordinal (e.g. "Calculate Point Maximums §1" -> "Calculate Point Maximums")
_STEP_SECTION_MARK = "§"
# a bare number, optionally signed, optionally decimal
_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

# grammar words that anchor nothing on their own (the weak-anchor
# guard): a rung-1 overlap consisting only of these is no home — a
# surface form like "Modifier to X" must not home a claim on the
# strength of the word "to"
_FUNCTION_WORDS = frozenset(
    "a an and are as at by for from in is it of on or the to with".split())


@dataclass
class Attribution:
    """One claim's verdict against canon."""
    claim: str
    verdict: str               # attributed | canon-gap | unattributed-invention
    rung: "str | None" = None  # properties | receipt | prose (attributed only)
    citizens: list = field(default_factory=list)  # [(label, name)]
    score: float = 0.0         # best match strength at the winning rung
    earned: "bool | None" = None  # strong form: cited citizen in the
    #                            drafter's consulted set (None = no
    #                            trace supplied)
    nearest: list = field(default_factory=list)   # gap aid: [(label, name)]
    evidence: list = field(default_factory=list)  # which surfaces matched:
    #                            value | edge | step | receipt | prose

    def row(self, kb=None, branch=None):
        doc = {"claim": self.claim, "verdict": self.verdict,
               "score": round(self.score, 3)}
        if self.rung:
            doc["rung"] = self.rung
        if self.evidence:
            doc["evidence"] = list(self.evidence)
        if self.citizens:
            doc["citizens"] = [CitizenRef(label, name).row(kb=kb,
                                                           branch=branch)
                               for label, name in self.citizens]
        if self.earned is not None:
            doc["earned"] = self.earned
        if self.nearest:
            doc["nearest"] = [CitizenRef(label, name).row(kb=kb,
                                                          branch=branch)
                              for label, name in self.nearest]
        return doc


@lru_cache(maxsize=None)
def _lemma(token):
    """Rung 1 of the attribution charter: morphology is DELEGATED to a
    maintained lemmatizer, never ruled case by case again — plurals
    (irregulars included), possessives, verb forms all fold through
    one dictionary layer, and a token the dictionary does not know
    passes through unchanged (conservative by construction: false
    homes are worse than misses). Number-bearing tokens never enter
    the lemma at all — the numeric canon below owns them, so '-2'
    stays '-2' and no signed equivalence arrives through a back
    door."""
    if any(ch.isdigit() for ch in token):
        return token
    return simplemma.lemmatize(token, lang="en")


def _canon(token):
    """Mechanical token canon for structured matching (rung 1 only):
    strip wrapping parentheses/brackets so "(cut)" tokenizes as
    "cut", pass the token through the delegated lemma layer (plural,
    possessive, verb-form morphology — one layer, no fold pile), then
    normalize a number's format — drop a leading plus, drop a trailing
    point-zero — so "+2" and "2", "3.0" and "3" home together. No
    signed or spelled-out equivalence: "-2" stays "-2", "minus" stays
    a word. Idempotent; an unknown plain token is returned
    unchanged."""
    token = _lemma(token.strip("()[]"))
    if _NUMBER.match(token):
        if token.startswith("+"):
            token = token[1:]
        if token.endswith(".0"):
            token = token[:-2]
    return token


def _canon_set(tokens):
    return {_canon(t) for t in tokens if t}


# the guard set closes under the lemma: claim tokens arrive lemmatized
# ("is"/"are"/"was" all fold to "be"), so the grammar words must too
_FUNCTION_WORDS = frozenset(_FUNCTION_WORDS
                            | {_lemma(w) for w in _FUNCTION_WORDS})


def _tokens(text):
    return set(normalize(text).split())


def _jaccard(a, b):
    """Token-set overlap (the judge's measure, set-shaped)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class CanonIndex:
    """The canon graph pre-chewed for matching: per citizen, the rungs'
    surfaces — canonical name+value tokens, carried receipt sentences,
    lifted step text (attached to the owning procedure), prose
    sentences — plus the ground-edge relation index, all built once and
    matched many times."""

    def __init__(self, graph):
        self.entries = []
        proc_of_entry = {}          # procedure name -> its entry (for lift)
        step_lifts = {}             # procedure name -> [lifted sentences]
        for (label, name), props in sorted(
                graph.nodes.items(), key=lambda item: (item[0][0],
                                                       str(item[0][1]))):
            if name is None:
                continue
            props = props or {}
            name_tokens = _tokens(str(name))
            is_step = label == "Step"
            value_tokens = set()
            prop_words = set()
            receipt_sentences = []
            prose_sentences = []
            for key, value in props.items():
                if key in METADATA_PROPS or value is None:
                    continue
                if is_step and key in ("text", "condition"):
                    # a step's carried program text is receipt-grain
                    # prose the OWNING procedure attests — lifted to it,
                    # not a home on the step itself
                    owner = str(name).split(_STEP_SECTION_MARK)[0].strip()
                    step_lifts.setdefault(owner, []).extend(
                        s for s in (normalize(t) for t in
                                    claims_of(str(value))) if s)
                elif key in RECEIPT_TEXT_PROPS:
                    if is_row_text(value):
                        # a table row is not a sentence — the
                        # row-receipt retirement: rows are presentation,
                        # never a carried quote, so they index as
                        # nothing and the honest homes beneath them
                        # (structured properties, prose props) surface
                        continue
                    receipt_sentences += [normalize(s) for s in
                                          claims_of(str(value))]
                elif key in PROSE_PROPS:
                    prose_sentences += [normalize(s) for s in
                                        claims_of(str(value))]
                elif isinstance(value, bool):
                    # Y/N flags carry no citable token, but the flag's
                    # NAME is still a word surface the citizen owns
                    prop_words |= {w for w in key.lower().split("_") if w}
                else:
                    value_tokens |= _tokens(str(value))
                    prop_words |= {w for w in key.lower().split("_") if w}
            name_canon = _canon_set(name_tokens)
            # a value that echoes the citizen's own name stays a value —
            # numeric ("Might 7" whose cap is 7) and word alike (a name
            # carrying the value word in parentheses). The say-it-twice
            # multiplicity guard at the anchor is what keeps a bare name
            # mention from attesting content; no token is subtracted.
            entry = {
                "key": (label, str(name)),
                "name_canon": name_canon,
                "value_canon": _canon_set(value_tokens),
                "prop_canon": _canon_set(prop_words),
                "receipts": [s for s in receipt_sentences if s],
                "step_lifts": [],
                "prose": [s for s in prose_sentences if s],
            }
            self.entries.append(entry)
            if label == "Procedure":
                proc_of_entry[str(name)] = entry
        # attach each procedure's lifted step text to the procedure's own
        # entry (receipt rung, cited AS the procedure). The step name's
        # prefix names its procedure; a lift whose procedure has no node
        # gets a synthesized citizen so the receipt is never orphaned.
        for owner, sentences in step_lifts.items():
            entry = proc_of_entry.get(owner)
            if entry is None:
                entry = {"key": ("Procedure", owner), "name_canon":
                         _canon_set(_tokens(owner)), "value_canon": set(),
                         "prop_canon": set(),
                         "receipts": [], "step_lifts": [], "prose": []}
                self.entries.append(entry)
            entry["step_lifts"].extend(sentences)

        # ground edges only: machine-derived types (and the ASSIGNS_*
        # projection family) attest nothing domain-level, so they never
        # make a claim a home
        self.edges = []
        for edge in graph.edges:
            etype = edge.type
            if etype in UNAUTHORABLE_EDGE_TYPES or etype.startswith("ASSIGNS_"):
                continue
            from_canon = _canon_set(_tokens(str(edge.from_name)))
            to_canon = _canon_set(_tokens(str(edge.to_name)))
            if not from_canon or not to_canon:
                continue
            self.edges.append({
                "from_key": (edge.from_label, str(edge.from_name)),
                "to_key": (edge.to_label, str(edge.to_name)),
                "from_canon": from_canon,
                "to_canon": to_canon,
                # the type's own words fold through the same canon the
                # claim's tokens do — the lemma layer is symmetric,
                # never one-sided
                "type_words": {_canon(w) for w in etype.lower().split("_")
                               if w},
            })

    def _text_matches(self, claim_norm, claim_tokens, surfaces):
        """Best sentence-overlap per citizen across the named surfaces.
        `surfaces` is [(entry_key, evidence)]; the evidence of the
        winning surface rides each match as (score, key, evidence)."""
        matches = []
        for entry in self.entries:
            best, best_ev = 0.0, None
            for surface_key, evidence in surfaces:
                for sentence in entry[surface_key]:
                    if claim_norm and (claim_norm in sentence
                                       or sentence in claim_norm):
                        score = 1.0
                    else:
                        score = _jaccard(claim_tokens,
                                         set(sentence.split()))
                    if score > best:
                        best, best_ev = score, evidence
            if best >= ATTRIBUTION_FLOOR:
                matches.append((best, entry["key"], best_ev))
        return matches

    def attribute(self, claim, consulted=None):
        """One claim against the ladder: first rung with a match wins;
        every matching citizen at that rung is cited; the best score
        rides as confidence. No rung → verdict left to the census
        (gap vs invention is parity's call, not this function's)."""
        claim_norm = normalize(claim)
        claim_tokens = set(claim_norm.split())
        claim_list = [t for t in (_canon(tok)
                                  for tok in claim_norm.split()) if t]
        claim_canon = set(claim_list)
        # rung 1 — the structured/first-class home, from two surfaces:
        #  (value) the citizen's name anchored in the claim PLUS one of
        #          its structured values — a name alone attests subject,
        #          not content, and is no home;
        #  (edge)  both endpoint names of a ground edge anchored AND the
        #          edge type's own words spoken — the relationship is a
        #          structured fact, so both endpoints are homes.
        # Two guards keep the anchor honest: a numeric value that also
        # spells the citizen's name homes only when the claim says the
        # number twice (once as the name, once as the value — "The Cap
        # of Might 7 is 7"), and an overlap made only of grammar words
        # is no home at all. Matched property-name words join the
        # scored surface so the owning citizen outranks passers-by.
        matches = []
        counts = Counter(claim_list)
        for entry in self.entries:
            if not entry["name_canon"] or \
                    not entry["name_canon"] <= claim_canon:
                continue
            overlap = entry["value_canon"] & claim_canon
            overlap -= {t for t in overlap & entry["name_canon"]
                        if counts[t] < 2}
            if not overlap - _FUNCTION_WORDS:
                continue
            surface = (entry["name_canon"] | entry["value_canon"]
                       | (entry["prop_canon"] & claim_canon))
            matches.append((_jaccard(claim_canon, surface),
                            entry["key"], EV_VALUE))
        for edge in self.edges:
            if not (edge["from_canon"] <= claim_canon
                    and edge["to_canon"] <= claim_canon):
                continue
            if not (edge["type_words"] & claim_canon) - _FUNCTION_WORDS:
                continue
            score = _jaccard(claim_canon, edge["from_canon"]
                             | edge["to_canon"] | edge["type_words"])
            matches.append((score, edge["from_key"], EV_EDGE))
            matches.append((score, edge["to_key"], EV_EDGE))
        rung = PROPERTIES if matches else None
        if not matches:
            matches = self._text_matches(
                claim_norm, claim_tokens,
                [("receipts", EV_RECEIPT), ("step_lifts", EV_STEP)])
            rung = RECEIPT if matches else None
        if not matches:
            matches = self._text_matches(claim_norm, claim_tokens,
                                         [("prose", EV_PROSE)])
            rung = PROSE if matches else None
        if not matches:
            nearest = sorted(
                ((max((_jaccard(claim_tokens, set(s.split())) for s in
                       entry["receipts"] + entry["step_lifts"]
                       + entry["prose"]), default=0.0), entry["key"])
                 for entry in self.entries),
                reverse=True)[:3]
            return Attribution(claim=claim, verdict=CANON_GAP,
                               nearest=[key for score, key in nearest
                                        if score > 0])
        # one citizen may be reached by several surfaces — keep its best
        # score and union the evidence that reached it
        agg = {}
        for score, key, evidence in matches:
            best, evs = agg.get(key, (0.0, set()))
            agg[key] = (max(best, score), evs | {evidence})
        ranked = sorted(agg.items(), key=lambda kv: kv[1][0], reverse=True)
        citizens = [key for key, _ in ranked[:3]]
        evidence = sorted({ev for key in citizens for ev in agg[key][1]})
        earned = None
        if consulted is not None:
            earned = any(key in consulted for key in citizens)
        return Attribution(claim=claim, verdict=ATTRIBUTED, rung=rung,
                           citizens=citizens, score=ranked[0][1][0],
                           earned=earned, evidence=evidence)


def census_claims(draft_text):
    """The claim census: the draft's sentence-grain prose claims plus
    fact-grain claims from its own headed tables (tables comprehend
    into claims — each cell one fact in the domain's terms, censused by
    the same instrument as prose). A `{{csv:}}` embed reference is
    structure, never a claim; a headerless table names no properties
    and stays structure too."""
    prose_lines = [line for line in draft_text.splitlines()
                   if not line.lstrip().startswith("|")
                   and "{{csv:" not in line]
    return (claims_of("\n".join(prose_lines))
            + [normalize(row["sentence"])
               for row in markdown_table_claims(draft_text)])


def census(draft_text, graph, invented=(), consulted=None):
    """Every draft claim attributed. `invented` is parity's verdict —
    the normalized claims the judge called INVENTED; a homeless claim
    splits on it: invented → the named red; otherwise → a canon gap
    (parity proved it present in the original, so the hole is the
    graph's). Returns [Attribution] in draft order."""
    index = CanonIndex(graph)
    invented = {normalize(text) for text in invented}
    results = []
    for claim in census_claims(draft_text):
        verdict = index.attribute(claim, consulted=consulted)
        if verdict.verdict == CANON_GAP and \
                normalize(claim) in invented:
            verdict.verdict = INVENTION
        results.append(verdict)
    return results


def render_census(results):
    """The attribution section of the scorecard, owner-facing."""
    lines = ["## Canon attribution — every claim seeks its graph home",
             ""]
    if not results:
        lines += ["No prose claims to attribute.", ""]
        return "\n".join(lines)
    by_rung = {rung: 0 for rung in RUNGS}
    gaps = [r for r in results if r.verdict == CANON_GAP]
    inventions = [r for r in results if r.verdict == INVENTION]
    unearned = [r for r in results if r.earned is False]
    for result in results:
        if result.verdict == ATTRIBUTED:
            by_rung[result.rung] += 1
    attributed = sum(by_rung.values())
    lines += [f"**{len(results)} claims: {attributed} attributed "
              f"({by_rung[PROPERTIES]} first-class · "
              f"{by_rung[RECEIPT]} carried receipts · "
              f"{by_rung[PROSE]} prose-only, the soup) · "
              f"{len(gaps)} canon gaps · "
              f"{len(inventions)} unattributed inventions**", ""]
    if inventions:
        lines += ["### Unattributed inventions (red — presented, "
                  "never hidden)", ""]
        lines += [f"- ⚠ {r.claim}" for r in inventions] + [""]
    if gaps:
        lines += ["### Canon gaps (the original says it; the graph has "
                  "no home for it — intake debts, shipping does not "
                  "stop)", ""]
        for r in gaps:
            near = ("; nearest: " + ", ".join(
                        f"({label}) {name}" for label, name in r.nearest)
                    if r.nearest else "")
            lines.append(f"- {r.claim}{near}")
        lines.append("")
    soup = [r for r in results
            if r.verdict == ATTRIBUTED and r.rung == PROSE]
    if soup:
        lines += ["### Prose-only homes (attributed, and a named debt: "
                  "these facts are still soup)", ""]
        lines += [f"- {r.claim} — "
                  + ", ".join(f"({label}) {name}"
                              for label, name in r.citizens)
                  for r in soup[:20]]
        if len(soup) > 20:
            lines.append(f"- … and {len(soup) - 20} more (see the "
                         "debts file)")
        lines.append("")
    if unearned:
        lines += [f"### Unearned citations ({len(unearned)} — correct "
                  "but the trace never consulted the citizen; "
                  "re-derivation owed)", ""]
    return "\n".join(lines)
