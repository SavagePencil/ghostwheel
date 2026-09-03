"""The receipt staleness guard: a carried quote must still be true of
its source, and when it is not, the owner hears WHICH problem it hides.

Sentence-grain ``from_text`` receipts are review evidence a citizen
carries — a verbatim quote from the cited source. Sources move; a quote
that no longer appears in the source's current bytes is STALE. Stale is
an honesty problem, never a build break (receipts are deliberately
never rendered into files), and a stale receipt may be hiding either of
two very different things, so every stale finding carries a
BENEATH-VERDICT: re-attribute the quote against canon with the receipt
surface suppressed —

- **honest home beneath**: the facts live in structured properties or
  prose props; the receipt can simply retire.
- **the receipt is the only home**: the quote was the fact's sole
  residence in canon — intake debt hiding behind evidence that no
  longer exists.

Three voices, so nothing drowns and nothing nags what it cannot check:

- ``stale``      — source readable, quote gone (with beneath-verdict)
- ``source-gone``— the cited path does not resolve to a readable file
- ``unverifiable``— the source is a ruling or dictation, not a file:
                    counted, never nagged (evidence by fiat is the
                    owner's own record)

Findings roll up PER SOURCE ARTIFACT: a source whose receipts go stale
wholesale reads as one line with counts, not a nag per citizen. That
rollup boundary is where the artifact-lifecycle marker will plug in
when it exists (a superseded source's rollup becomes "historical —
attests the superseded text" and falls silent); until then the rollup
alone keeps the report readable.

Matching is the verify_receipts rule: whitespace-normalized containment
in the source's current bytes. Row-shaped from_text is not a receipt at
all (the row-receipt retirement) and is never swept here.

Pure logic over the committed export plus source files; DB-free.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .comprehension import is_row_text
from .judge import claims_of
from .report import ADVISORY, Verdict
from .refs import CitizenRef

# how a `source` prop separates its file path from a section heading
SECTION_MARK = "§"

HONEST_HOME = "honest home beneath — the receipt can retire"
ONLY_HOME = ("the receipt is the only home — intake debt hides "
             "behind it")

READABLE = "readable"
SOURCE_GONE = "source-gone"
UNVERIFIABLE = "unverifiable"


@dataclass
class Receipt:
    """One sentence-grain carried quote and where it claims to be from."""
    label: str
    name: str
    quote: str
    source: str            # the source prop verbatim
    relpath: str = ""      # the file part, when the source names one
    kind: str = READABLE   # readable | source-gone | unverifiable
    stale: bool = False
    beneath: str = ""      # the beneath-verdict, for stale receipts


@dataclass
class Sweep:
    receipts: list = field(default_factory=list)   # [Receipt]

    @property
    def stale(self):
        return [r for r in self.receipts if r.stale]

    @property
    def verified(self):
        return [r for r in self.receipts
                if r.kind == READABLE and not r.stale]


def sentence_receipts(graph):
    """Every sentence-grain from_text in the graph, with its cited
    source. Row-shaped receipts are not receipts (the retirement)."""
    receipts = []
    for (label, name), props in sorted(
            graph.nodes.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        quote = (props or {}).get("from_text")
        if not quote or is_row_text(quote):
            continue
        receipts.append(Receipt(label=label, name=str(name),
                                quote=str(quote),
                                source=str((props or {}).get("source")
                                           or "")))
    return receipts


def resolve_source(base_dir, source):
    """(relpath, kind): the file a source prop cites, and whether it can
    be checked. The path part is the text before the section mark, with
    a trailing parenthetical annotation stripped ("data/x.csv (the four
    rows)" cites data/x.csv). A resolvable file is READABLE; a
    path-looking cite that does not resolve is SOURCE-GONE; a cite that
    points outside the repo (a URL) or names no file at all (a ruling,
    a dictation, a conversation) is UNVERIFIABLE by design."""
    text = (source or "").split(SECTION_MARK)[0].strip()
    if not text or "://" in text:
        return text, UNVERIFIABLE
    candidates = [text]
    trimmed = re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()
    if trimmed and trimmed != text:
        candidates.append(trimmed)
    for candidate in candidates:
        try:
            if (Path(base_dir) / candidate).is_file():
                return candidate, READABLE
        except OSError:
            pass
    if "/" in text or Path(text).suffix:
        return text, SOURCE_GONE
    return text, UNVERIFIABLE


def quote_in(quote, body):
    """The verify_receipts rule: whitespace-normalized containment."""
    return " ".join(str(quote).split()) in " ".join(str(body).split())


def beneath_verdict(graph, quote):
    """What a stale receipt was hiding: attribute the quote's sentences
    against canon with the whole receipt surface suppressed. Every
    sentence homed -> the honest home was there all along; any sentence
    homeless -> the receipt was its only residence."""
    from .attribution import CANON_GAP, CanonIndex
    from .extract import GraphData
    bare = GraphData()
    for (label, name), props in graph.nodes.items():
        kept = {k: v for k, v in (props or {}).items() if k != "from_text"}
        bare.ensure_node(label, name, **kept)
    bare.edges = list(graph.edges)
    index = CanonIndex(bare)
    sentences = claims_of(str(quote)) or [str(quote)]
    for sentence in sentences:
        if index.attribute(sentence).verdict == CANON_GAP:
            return ONLY_HOME
    return HONEST_HOME


def sweep(base_dir, graph):
    """The whole canon's receipts checked against their sources."""
    base_dir = Path(base_dir)
    bodies = {}
    result = Sweep(receipts=sentence_receipts(graph))
    for receipt in result.receipts:
        receipt.relpath, receipt.kind = resolve_source(base_dir,
                                                       receipt.source)
        if receipt.kind != READABLE:
            continue
        if receipt.relpath not in bodies:
            try:
                bodies[receipt.relpath] = (
                    base_dir / receipt.relpath).read_text(encoding="utf-8")
            except OSError:
                receipt.kind = SOURCE_GONE
                continue
        if not quote_in(receipt.quote, bodies[receipt.relpath]):
            receipt.stale = True
            receipt.beneath = beneath_verdict(graph, receipt.quote)
    return result


def render_report(result):
    """The owner-facing sweep report: rollups per source artifact, every
    stale receipt named with its beneath-verdict, the unverifiable and
    source-gone classes counted rather than nagged."""
    lines = ["# Receipt sweep — every carried quote checked against "
             "its source", ""]
    if not result.receipts:
        lines += ["No sentence-grain receipts in canon — nothing to "
                  "check.", ""]
        return "\n".join(lines)
    lines += [f"**{len(result.receipts)} carried quotes: "
              f"{len(result.verified)} verified · "
              f"{len(result.stale)} stale · "
              f"{len([r for r in result.receipts if r.kind == SOURCE_GONE])}"
              " source-gone · "
              f"{len([r for r in result.receipts if r.kind == UNVERIFIABLE])}"
              " unverifiable by design**", ""]
    by_source = {}
    for receipt in result.stale:
        by_source.setdefault(receipt.relpath or receipt.source,
                             []).append(receipt)
    for source, receipts in sorted(by_source.items()):
        lines += [f"## {source} — {len(receipts)} stale quote"
                  + ("s" if len(receipts) != 1 else ""), ""]
        for r in receipts:
            shown = " ".join(r.quote.split())
            if len(shown) > 90:
                shown = shown[:90] + "…"
            lines.append(f"- ({r.label}) **{r.name}** — \"{shown}\" — "
                         f"{r.beneath}")
        lines.append("")
    gone = [r for r in result.receipts if r.kind == SOURCE_GONE]
    if gone:
        lines += ["## Sources that no longer resolve", ""]
        for r in gone:
            lines.append(f"- ({r.label}) **{r.name}** cites "
                         f"'{r.relpath or r.source}' — no such file; "
                         "the artifact moved, or its cite needs fixing")
        lines.append("")
    unverifiable = [r for r in result.receipts if r.kind == UNVERIFIABLE]
    if unverifiable:
        lines += [f"({len(unverifiable)} quote"
                  + ("s cite" if len(unverifiable) != 1 else " cites")
                  + " rulings or dictation rather than files — evidence "
                  "by the owner's own record, unverifiable by design and "
                  "not checked.)", ""]
    return "\n".join(lines)


# -- the delta gate's checks ------------------------------------------------


def receipt_verdicts(delta, base, base_dir):
    """The gate-side guards, over what the round touches:

    - REFUSAL (receipt-unverified): a round AUTHORS a sentence-grain
      from_text whose quote cannot be found in its cited readable
      source — new evidence must be real evidence ("an interpretation
      posing as evidence"). Sources that are missing or unverifiable
      by design do not refuse: only a provable fabrication does.
    - ADVISORY (receipt-stale): a round touches a citizen whose
      EXISTING receipt is stale — the moment the owner is already
      looking is the moment to say so, with the beneath-verdict.
    """
    base_dir = Path(base_dir)
    verdicts = []
    bodies = {}

    def body_of(relpath):
        if relpath not in bodies:
            try:
                bodies[relpath] = (base_dir / relpath).read_text(
                    encoding="utf-8")
            except OSError:
                bodies[relpath] = None
        return bodies[relpath]

    def authored(label, name, quote, source):
        relpath, kind = resolve_source(base_dir, source)
        if kind != READABLE:
            return
        body = body_of(relpath)
        if body is None or quote_in(quote, body):
            return
        shown = " ".join(str(quote).split())
        if len(shown) > 80:
            shown = shown[:80] + "…"
        verdicts.append(Verdict(
            code="receipt-unverified",
            subject=CitizenRef(label, name),
            message=(
                f"({label}) '{name}' carries a quote its cited source "
                f"does not contain — \"{shown}\" is not in {relpath}. "
                "A receipt that can't be found is an interpretation "
                "posing as evidence. Quote the source verbatim, or "
                "drop the receipt."),
            remedy="Quote the source verbatim, or drop the receipt."))

    for label, name, props in delta.nodes_added:
        quote = (props or {}).get("from_text")
        if quote and not is_row_text(quote):
            authored(label, name, quote, (props or {}).get("source") or "")

    for label, name, changes in delta.nodes_changed:
        node = (base.nodes.get((label, name)) or {}) if base else {}
        if "from_text" in changes:
            _before, after = changes["from_text"]
            if after and not is_row_text(after):
                source = changes.get("source", (None, node.get("source")))[1]
                authored(label, name, after, source or "")
            continue  # a rewritten receipt is judged as authored, above
        quote = node.get("from_text")
        if not quote or is_row_text(quote):
            continue
        relpath, kind = resolve_source(base_dir, node.get("source") or "")
        if kind != READABLE:
            continue
        body = body_of(relpath)
        if body is None or quote_in(quote, body):
            continue
        beneath = beneath_verdict(base, quote)
        shown = " ".join(str(quote).split())
        if len(shown) > 80:
            shown = shown[:80] + "…"
        verdicts.append(Verdict(
            code="receipt-stale",
            severity=ADVISORY,
            subject=CitizenRef(label, name),
            message=(
                f"({label}) '{name}' is being changed while its carried "
                f"quote is stale — \"{shown}\" no longer appears in "
                f"{relpath}; {beneath}. Retire or re-quote the receipt "
                "while you are here."),
            remedy="Retire or re-quote the receipt in this round."))
    return verdicts
