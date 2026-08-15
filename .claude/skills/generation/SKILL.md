---
name: generation
description: Generate artifacts of any medium — documents, images, tables, examples, illustrations — from the graph, with optional owner steering and iteration loops to course-correct. Canon is the only source of facts; steering shapes presentation. Use whenever the owner asks to generate something from canon.
---

# Generation

Every generated artifact is a projection of the graph into a medium.
The graph supplies the facts; the owner may supply steering; the medium
supplies the form. The full design this skill implements is
the engine's agentic-approach design record (design/ in the engine repo; graph/engine_docs/design/ inside an installed engine package) (v3: Virtues, Tenets, Method); this file is the
working procedure.

## The invariants (medium-independent)

1. **Facts come from provenance, only.** Every asserting element — a
   number, a name, a relationship, a depicted attribute — must trace to
   a citizen, or on a cold graph to the source artifact itself. If
   neither holds anything, that is a GAP surfaced to the owner as a
   question, never filled by invention.
2. **Steering shapes presentation, never facts.** Steering that would
   contradict canon gets surfaced, not silently obeyed.
3. **Nothing semantically omitted or distorted** within the request's
   scope; presentation free inside that boundary.
4. **The raw ask + context ride verbatim** into every brief. Derived
   context supplements, never replaces.

## The default path (short; machinery engages only on signals)

1. **Understand as a habit** — the Method runs internally (ask,
   audience, artifacts, person, organization, composition — including
   the standing UNIT question: which axes — structural / temporal /
   spatial — what hierarchy; "none" and "sequence-of" are legal;
   "cannot tell" escalates). Surface to the owner ONLY what is
   genuinely ambiguous, batched into one question sheet, conversation
   available on any line of it.
2. **Work** — one agent per unit of work, with a brief that is a
   constraint-set + provisioned data + model tier (never a persona);
   iterate against the deterministic judge where one exists.
3. **Floor + present** — the honest floor: remaining disagreements
   named and classified (gap / taste / error). Present the COMPLETED
   artifact with the floor census and margin attached — never
   fragments, never diffs.
4. **Iterate / consent** — harvest owner comments (deduce
   defect/taste/question; never demand a format; convert theirs if
   they use one); answer questions first; taste persists as steering.
   Consent is asked when canon mutates or work publishes — not as a
   completion ritual.

Engagement signals that bring machinery in: no deterministic judge →
critique ensemble (weight inversely proportional to judge strength);
mute single-shot generator → composition ensemble ahead of the shot;
units > 1 → shard by unit + a cross-unit coherence expert; repeated
worker/judge disagreement → second opinion; stuck → escalate with work
shown. When a gate engages, review BRIEF CONTENT, not cast topology.
Plan generation is one seeded casting step, never a meta-ensemble.

## Input layers (the evaluator boundary)

The original artifact — and ANY judge finding that quotes it — is
evaluator-internal: it never enters a generator's brief or readable
set. A verdict that quotes the missing content is the answer written
in the margin; feeding it back launders the original into the draft
through the evaluator. Feedback crossing down to a generator is
REDACTED to defect class plus citizen pointers ("a claim carried by
(Beast) the Cinder Fox is missing — consult that citizen"), which forces
the fix through the graph. Generators read canon, the brief, and the
owner's steering — nothing else. Drafters RECORD the citizens they
consult as rows on the run trace: that consulted set is what makes a
citation earned (the engine attribution module's strong form); an unearned-but-
correct claim is re-derived with the citizen provisioned, invisibly —
the trace records both passes.

## The trace and the margin

- Every run records who was cast, what they were told, what they
  cited, what the judge ruled, what escalated. Claims about runs cite
  the trace; recollection is not a source.
- The trace machinery is the engine's runs module (graph.runs): open with new_run(brief,
  started), record judgments with add_row (question / answer /
  decision / opinion — decided_by names the agent, confidence graded
  honestly), and file the archive with write_archive under graph/runs/
  at run end. Ratifying a row into canon goes through the ordinary
  approval ceremony; promotion(run, name) packages the citation.
- Agent judgments made mid-run (mapping choices, low-confidence calls)
  are Opinions with confidence, kept on the run's record and surfaced
  as MARGIN ANNOTATIONS inline in the presented artifact where
  confidence is low or canon was silent. The owner replies in the same
  margin; an owner catch on an UNFLAGGED decision means confidence was
  miscalibrated — record it.
- Annotations anchor to (artifact, span) from day one. The machinery
  is the engine's runs module: pass anchor={artifact, start, end, text} to
  add_row (the exact quote is mandatory — it re-locates the span if
  the artifact moves); margin(run, fingerprint, artifact_text) reads
  the floor census in span order; render_margin presents artifact and
  annotations together; write_archive(run, dir, artifacts) refuses
  any anchor whose quote is not really in its artifact.
- Before saying "done" after any fix round, re-check everything the
  owner previously approved — a fix must not silently break prior
  approvals; a defect class the owner caught once is checked by
  machine thereafter. The machinery is `python -m graph corpus`
  (the engine's corpus module; the KB keeps its ledger at graph/corpus/floors.jsonl): run it
  before any "done" report, and when the owner blesses a new
  expectation or catches an unflagged decision, record the floor
  (record_floor: guard test node id, scope, plain-words expectation,
  provenance) in the same change set as the fix.

## Attribution: every claim seeks its graph home

After parity, the census (the engine's attribution module, wired into the
roundtrip scorecard): every draft claim is attributed against canon on
the graded source ladder — a citizen's structured properties, its
carried receipts, or a long-prose home (the soup rung: attributed AND
a named intake debt). The matcher reads STRUCTURE, not just prose: a
claim that names both endpoints of a ground edge and speaks the edge
type's words homes first-class on both citizens, and a claim found in a
procedure's lifted step text homes at receipt grade citing the
procedure — both mechanical, no synonyms (that stays the ruled-mappings
tier). A homeless claim splits on parity's verdict: if
the original says it, it is a CANON GAP — surfaced with an auto-filed
debt, shipping never stops, at any density; if parity called it
invented, it is an UNATTRIBUTED INVENTION — a red presented WITH the
artifact, named in the margin, never a hidden parked run. The whole
submitted artifact is the judging unit (`python -m graph roundtrip
--book`); sections are internal drill-down. The original remains the
parity reference until the owner explicitly declares succession — no
milestone implies it.

## Presentation is its own check

An evaluator that judges content order-free is blind to placeholder
headers, misordered ladders, misaligned cells, and collapsed table
structure. Rosters with a declared order render in that order; cells
hold their positions under named headers; structure-reflecting
sections (a table of contents) generate LAST. Verify presentation
separately from content parity — human or scripted.

## Cautions

- An example in the source gets the standing disambiguation question
  (preserve verbatim vs. regenerate as illustration) — never a silent
  default. Forward references get the ordering-intentional question.
- A sentence the machine cannot parse is flagged as a QUESTION — "I
  didn't understand this; is it garbled?" — never asserted as a source
  defect ("garbled", "malformed"), and it never blocks work (owner
  ruling: a hard-to-parse sentence may be exactly as intended). The
  incomprehension rides the margin as a low-confidence Opinion; the
  owner's reply threads to it as the Answer.
- Carried-verbatim storage keeps original bytes; normalized forms are
  matching keys only.
- Park, never die: a blocked or disconnected run keeps its state and
  resumes; the owner should never need to say "try again."
