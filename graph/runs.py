"""Run-scoped judgment graphs: a run's trace as an archived graph (the run-graph archive).

Spine phase 1 of the agentic approach (design:
graph/design/agentic-approach.md — run-scoped judgment graphs). A run is
one casting of agents against a brief. Its trace IS a graph: Question /
Answer / Decision / Opinion rows carrying decided_by (the agent that
judged) and a confidence grade — the same Judgment vocabulary canon
uses, scoped to the run and epistemically junior. Agent judgments are
Opinions until the owner ratifies one; ratification happens through the
ordinary scratch → delta → approve ceremony, and the promoted canon row
cites the run id as provenance.

Lifecycle (precedent: the reading room, graph/comprehension.py):

- BUILD: rows accumulate on a Run in memory while the run works.
- ARCHIVE: at run end, small flat JSONL files under graph/runs/<run-id>/
  filed with the round's reports, kept with the record — inspectable forever,
  canon never.
- Deletion tolerance: canon never references archive internals. A
  ratified row carries the run id and the judgment's own content, so
  total archive loss leaves canon intact (the reading room's rule).

Identity: a run's id is its start timestamp plus a short content hash
of the brief — the timestamp is passed in by the caller (testable,
deterministic), never taken here.

Judgments can anchor to spans (the span-anchor mechanism): an anchor is (artifact
fingerprint, start, end, quoted text) — the quote is the durable half,
re-locating the span when the artifact moves. An artifact's MARGIN is
its anchored judgments in span order: the floor census, read in place;
render_margin presents artifact and margin together (markdown now; a
future UI overlay renders the same rows). Archiving with the artifact
bytes supplied refuses any anchor whose quote is not really there.

Pure logic throughout — no driver. The run graph lives in memory and in
its archive; loading an archive into a workspace database for Cypher
inspection can ride later if a trace ever needs querying.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

QUESTION = "question"
ANSWER = "answer"
DECISION = "decision"
OPINION = "opinion"
KINDS = (QUESTION, ANSWER, DECISION, OPINION)

ARCHIVE_RUN = "run.json"
ARCHIVE_ROWS = "judgments.jsonl"


@dataclass
class Run:
    """One casting of agents against a brief: identity + judgment rows."""
    id: str
    brief: str
    started: str  # ISO-ish display metadata; identity lives in the id
    rows: list = field(default_factory=list)  # dicts, insertion order

    def row(self, name):
        for row in self.rows:
            if row["name"] == name:
                return row
        return None


def run_id(brief, started):
    """<compact timestamp>-<short brief hash>: sortable by start time,
    collision-proofed by content."""
    stamp = "".join(ch for ch in started if ch.isdigit())
    digest = hashlib.sha256(brief.encode("utf-8")).hexdigest()[:8]
    return f"{stamp}-{digest}"


def new_run(brief, started):
    """Open a run. `started` is supplied by the caller (e.g.
    datetime.now().strftime('%Y-%m-%d %H:%M:%S')) — passing it in keeps
    this module deterministic and the id reproducible in tests."""
    if not brief or not brief.strip():
        raise ValueError(
            "Attempted to open a run with an empty brief. Failed because "
            "the brief is the run's identity and its instructions — "
            "supply the text the agents were actually given.")
    return Run(id=run_id(brief, started), brief=brief, started=started)


def _check_anchor(run, name, anchor):
    """The span-anchor mechanism: an anchor ties a judgment to (artifact, span). The quoted
    text is the durable half — offsets are hints that must agree with
    it, and relocation by quote survives artifact edits."""
    required = ("artifact", "start", "end", "text")
    missing = [key for key in required
               if not isinstance(anchor, dict) or key not in anchor]
    if missing:
        raise ValueError(
            f"Attempted to anchor '{name}' on run {run.id}. Failed "
            f"because the anchor is missing {', '.join(missing)} — an "
            "anchor is {artifact fingerprint, start, end, text (the "
            "exact quoted span)}.")
    if not str(anchor["artifact"]).strip():
        raise ValueError(
            f"Attempted to anchor '{name}' on run {run.id}. Failed "
            "because the artifact fingerprint is empty — the anchor "
            "must name the artifact the span lives in.")
    if not anchor["text"]:
        raise ValueError(
            f"Attempted to anchor '{name}' on run {run.id}. Failed "
            "because the quoted text is empty — the quote is what "
            "re-locates the span if the artifact moves; an offset-only "
            "anchor cannot survive an edit.")
    start, end = anchor["start"], anchor["end"]
    if not (isinstance(start, int) and isinstance(end, int)
            and 0 <= start < end):
        raise ValueError(
            f"Attempted to anchor '{name}' on run {run.id} at "
            f"[{start}, {end}). Failed because the offsets are not a "
            "sane span — start and end are character offsets with "
            "0 <= start < end.")
    if end - start != len(anchor["text"]):
        raise ValueError(
            f"Attempted to anchor '{name}' on run {run.id} at "
            f"[{start}, {end}) with a {len(anchor['text'])}-character "
            "quote. Failed because the span length and the quote "
            "disagree — end must equal start plus the quote's length.")


def add_row(run, kind, name, text, decided_by, confidence=None, about=None,
            anchor=None):
    """Record one judgment on the run's trace.

    kind: question | answer | decision | opinion. decided_by names the
    agent that made the judgment — every judgment has an author. about
    threads a row to an earlier one (an Answer to its Question, a
    Decision to the Question it settles) and must name an existing row.
    anchor (the span-anchor mechanism) optionally ties the judgment to a span: {artifact:
    fingerprint, start, end, text: the exact quoted span}.
    """
    if kind not in KINDS:
        raise ValueError(
            f"Attempted to record a '{kind}' row on run {run.id}. Failed "
            f"because the trace holds only {', '.join(KINDS)} — pick the "
            "kind that matches what was judged.")
    if not name or not str(name).strip():
        raise ValueError(
            f"Attempted to record a {kind} without a name on run "
            f"{run.id}. Failed because every judgment row needs a name "
            "to be cited by — give it one.")
    if run.row(name) is not None:
        raise ValueError(
            f"Attempted to record '{name}' twice on run {run.id}. Failed "
            "because row names are the trace's citations and must be "
            "unique — pick a new name, or thread a follow-up to the "
            "existing row with about.")
    if not decided_by or not str(decided_by).strip():
        raise ValueError(
            f"Attempted to record '{name}' with no author on run "
            f"{run.id}. Failed because every judgment names the agent "
            "that made it (decided_by) — anonymous judgments cannot be "
            "weighed or ratified.")
    if about is not None and run.row(about) is None:
        raise ValueError(
            f"Attempted to thread '{name}' to '{about}' on run {run.id}. "
            "Failed because no row by that name exists yet — record the "
            "row it responds to first.")
    if anchor is not None:
        _check_anchor(run, name, anchor)
    row = {"kind": kind, "name": name, "text": text,
           "decided_by": decided_by}
    if confidence is not None:
        row["confidence"] = confidence
    if about is not None:
        row["about"] = about
    if anchor is not None:
        row["anchor"] = {"artifact": anchor["artifact"],
                         "start": anchor["start"], "end": anchor["end"],
                         "text": anchor["text"]}
    run.rows.append(row)
    return row


def promotion(run, name):
    """The self-contained package for ratifying one row into canon.

    Ratification itself is the ordinary ceremony (scratch → delta →
    approve — the owner's authority, not this module's); this helper
    only guarantees the citation is right: the promoted row carries the
    run id as provenance plus the judgment's full content, and nothing
    that points into the archive — so canon survives archive loss.
    """
    row = run.row(name)
    if row is None:
        raise ValueError(
            f"Attempted to promote '{name}' from run {run.id}. Failed "
            "because the trace holds no row by that name — check the "
            "archive's judgments file for what the run actually "
            "recorded.")
    package = {"run": run.id, "kind": row["kind"], "text": row["text"],
               "proposed_by": row["decided_by"]}
    if "confidence" in row:
        package["confidence"] = row["confidence"]
    return package


# -- the margin (the span-anchor mechanism): anchored judgments, read in place ------------------


def locate(anchor, artifact_text):
    """The anchor's span in the artifact AS IT NOW READS. The quote is
    authoritative: if the recorded offsets still hold the quote they
    stand; otherwise the quote re-locates (nearest occurrence to the
    recorded start — an edit above the span moves offsets, not
    meaning). Returns (start, end), or None if the quote is gone."""
    quote = anchor["text"]
    start, end = anchor["start"], anchor["end"]
    if artifact_text[start:end] == quote:
        return (start, end)
    occurrences = []
    idx = artifact_text.find(quote)
    while idx != -1:
        occurrences.append(idx)
        idx = artifact_text.find(quote, idx + 1)
    if not occurrences:
        return None
    best = min(occurrences, key=lambda i: abs(i - start))
    return (best, best + len(quote))


def margin(run, fingerprint, artifact_text=None):
    """One artifact's margin: the run's anchored judgments in span
    order — the floor census, read in place. Returns [(row, span)];
    span is relocated against artifact_text when given (a row whose
    quote is gone carries span None and sorts last — surfaced, never
    dropped)."""
    entries = []
    for row in run.rows:
        anchor = row.get("anchor")
        if anchor is None or anchor["artifact"] != fingerprint:
            continue
        span = ((anchor["start"], anchor["end"])
                if artifact_text is None else locate(anchor, artifact_text))
        entries.append((row, span))
    return sorted(entries,
                  key=lambda e: (e[1] is None, e[1] or (0, 0)))


def verify_anchors(run, artifacts):
    """The span-anchor mechanism: every anchored judgment whose artifact bytes are supplied
    ({fingerprint: text}) must hold a quote that actually appears
    there. Problems collate; an anchor into an unsupplied artifact is
    not checkable and passes silently (supply the bytes to check it)."""
    problems = []
    for row in run.rows:
        anchor = row.get("anchor")
        if anchor is None or anchor["artifact"] not in artifacts:
            continue
        if locate(anchor, artifacts[anchor["artifact"]]) is None:
            problems.append(
                f"'{row['name']}' anchors to a span of artifact "
                f"{anchor['artifact'][:12]} reading "
                f"{anchor['text']!r}, but that text does not appear in "
                "the artifact — the quote was mistranscribed, or the "
                "anchor names the wrong artifact.")
    return problems


def render_margin(artifact_text, entries):
    """The presented artifact with its margin: ⟦n⟧ markers at each
    span's end, the annotations beneath — markdown now; a future UI
    overlay renders the same rows. entries is margin()'s output."""
    numbered = [(n, row, span)
                for n, (row, span) in enumerate(entries, start=1)]
    text = artifact_text
    for n, _, span in sorted((e for e in numbered if e[2] is not None),
                             key=lambda e: e[2][1], reverse=True):
        text = text[:span[1]] + f"⟦{n}⟧" + text[span[1]:]
    lines = [text, "", "---", "", "## Margin", ""]
    for n, row, span in numbered:
        grade = (f", confidence {row['confidence']}"
                 if "confidence" in row else "")
        where = ("" if span is not None
                 else " — SPAN NOT FOUND in the artifact as it now reads")
        lines.append(f"⟦{n}⟧ {row['kind']} by {row['decided_by']}{grade}"
                     f"{where}: {row['text']}")
        lines.append(f"    > {row['anchor']['text']}")
    return "\n".join(lines) + "\n"


# -- archive: small flat files, batch-importable, custody-friendly --------


def serialize(run):
    """Run -> {filename: content}. Deterministic: same Run, same bytes —
    archives diff cleanly and rebuild identically."""
    header = {"id": run.id, "brief": run.brief, "started": run.started,
              "format": "run-trace-v0"}
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True)
             for row in run.rows]
    return {
        ARCHIVE_RUN: json.dumps(header, ensure_ascii=False, indent=2,
                                sort_keys=True) + "\n",
        ARCHIVE_ROWS: "\n".join(lines) + ("\n" if lines else ""),
    }


def parse_archive(files):
    """{filename: content} -> Run (inverse of serialize)."""
    header = json.loads(files[ARCHIVE_RUN])
    rows = [json.loads(line)
            for line in files[ARCHIVE_ROWS].splitlines() if line]
    return Run(id=header["id"], brief=header.get("brief", ""),
               started=header.get("started", ""), rows=rows)


def write_archive(run, base_dir, artifacts=None):
    """File the trace under <base_dir>/<run-id>/. Returns paths written.
    Supply artifacts ({fingerprint: text}) to verify every checkable
    anchor before anything is filed — a quote that does not appear in
    its artifact refuses the archive whole (the span-anchor mechanism)."""
    if artifacts:
        problems = verify_anchors(run, artifacts)
        if problems:
            raise ValueError(
                "Attempted to archive the run's trace with anchored "
                "judgments that do not match their artifacts. Failed "
                "due to:\n  - " + "\n  - ".join(problems))
    directory = Path(base_dir) / run.id
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, content in serialize(run).items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def read_archive(directory):
    directory = Path(directory)
    return parse_archive({
        ARCHIVE_RUN: (directory / ARCHIVE_RUN).read_text(encoding="utf-8"),
        ARCHIVE_ROWS: (directory / ARCHIVE_ROWS).read_text(
            encoding="utf-8"),
    })
