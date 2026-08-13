---
name: procedure-intake
description: Assess a procedure (source prose describing a process, an in-world resolution, an external tool operation) and produce the right approved artifact for its Completeness level — a full program (transcribed), an asserted signature (attested), or a bare reference (cited). Use when the submitter says "let's intake/program/transcribe procedure X" or when a source section describes a process.
---

# Procedure intake

Scope note: when a procedure-shaped source arrives as part of a broader
intake, the **agentic-intake** skill drives the overall flow and this
skill governs the procedure content at its plan gate (step 2).

Boundary context: @../../../design/ontology-doctrine.md — Procedure, the
Completeness vocabulary, Step, and Outcome are ENGINE machinery
(graph/metaontology.yaml); the procedures themselves are project artifacts
(data/procedures/*.yaml). Program vocabulary grows by owner approval, never by
improvisation.

## The Completeness ruling comes first

**Read the menu from the graph, not from memory** (levels are doc-bearing
Ordered citizens):

```cypher
MATCH (level:Archetype)-[:INSTANCE_OF]->(:Archetype {name: 'Completeness'})
RETURN level.rank, level.name, level.doc ORDER BY level.rank
```

Then apply the two-axis test **with the owner, before extracting
anything**:

1. Does an agent need the inner workings? (An in-world character
   reasoning "how does this work for me?" — yes. Selecting a tool
   from a catalog — no.)
2. Do we own the source? (Our corpus — yes. A third-party tool's
   docs — no.)

Both yes → **transcribed** (full YAML program; signature derived).
Inner workings no, or source not ours → **attested** (asserted signature +
prose link + `approved_hash`) or **cited** (name + link).
The failure mode is defaulting to maximum completeness because you can.
Don't.

## Procedure

1. **Read the source cold** (doc section, catalog entry, external doc).
2. **Author/derive discipline** — propose ONLY what must be authored:
   - `inputs` (required/optional + `when_absent` defaults). Inputs are
     caller-supplied; things the procedure observes are READS — derived,
     never authored for transcribed procedures.
   - **Every non-obvious authored fact carries a `from_text:` receipt** — a
     verbatim quote of the source sentence it was extracted from. The
     extractor verifies the quote appears in the source; review reads claim
     beside evidence. An interpretation without a receipt is an
     unfalsifiable paraphrase — a plausible-reading extraction once
     inverted the source's meaning entirely; the receipt would have
     collapsed it on contact.
   - `possible_outcomes` names + guarantees (`read-only` / `cannot-fail` /
     `fails-clean` / `fails-with-side-effects`). Guarantees are rules facts the
     body cannot reveal — always ask the owner ("does a failed X leave
     the cost paid?").
   - `completeness`, `specified_in` + `approved_hash` (sha256 of the source body,
     computed the way the extractor compares it: DocSection body or the
     node's description property).
   NEVER hand-write reads/consults/mutates/calls for a transcribed
   procedure — the projection derives them, and hand-written copies drift.
3. **Draft-then-plan** — author the candidate YAML in the scratchpad
   DURING planning and run `python -m graph validate` and
   `python -m graph generate` against it (add the draft to a scratch
   ontology copy if needed). The plan quotes ACTUAL tool output — a plan
   containing untested claims about what the machinery will derive is not
   ready to present. (Both cold-test misses were machinery assumptions
   not traced through code.)
4. **Assess by scenario dry-run** — the extraction method IS the interview:
   walk boundary cases with the owner ("the resource exactly equals
   the cost — which branch?"). Adjudications become guards. Expect the prose to blur
   at least one boundary; that blur is the artifact's most valuable find.
5. **The owner names everything — and rules everything, explicitly.**
   Outcome names are the vocabulary in-world agents will enumerate:
   propose candidates
   from stop prose; the owner rules. **Ask outcome name and guarantee
   TOGETHER, as separate answers — a ruling on the name is not a ruling on
   the guarantee, and nothing is ever inferred from silence** (a
   header-flagged proposal relies on the approver rereading the file).
   Same stop text in two branches = same outcome (deliberate); distinct
   prose joining one outcome uses the inline `stop: {outcome:, note:}`
   form. Carry the source's terminal sentence whole into stop prose,
   including onward-flow clauses — a dropped trailing clause has been
   the late-found extraction gap more than once.
6. **Grammar discipline** — match every `when:` condition against the
   approved grammar (see data/procedures/README.md). Anything new is a
   grammar-extension PROPOSAL for the owner, not a free-form condition.
   Prefer two `when`s over inventing an `or`.
7. **Bijection and closure audits** before presenting (largely already
   done if step 3 ran the tools against the draft):
   - every stop claimed by exactly one outcome; every outcome claims ≥1
     stop (`python -m graph validate` enforces this)
   - every declared input used in the body; every non-graph name in the
     body either an input or flagged
   - attested level: every section explicitly `closed: true/false`, with
     "what evidence would close this?" asked per open section
8. **Generation-diff fidelity check** — `python -m graph generate "<name>"`
   and diff against the source prose. The render covers the WHOLE
   signature (inputs, outputs, precondition, steps) — an authored input
   the source never states shows up as an invention. Source facts missing
   from the render are extraction gaps; rendered facts missing from the
   source are inventions. Do not present until inventions are zero.
9. **Answer-key hunting** — does an approved fact table exist that the
   program should reproduce (a transition table, an effects matrix)?
   Wire a walk-derivation test (`walk_transitions` == the relevant rows).
   If no table exists, ask whether the derived facts should become one.
   **Numeric worked examples are recompute candidates**: an example
   that asserts numbers can become a fixture row whose every asserted
   value is recomputed from the approved tables (`derives: recompute`),
   only the random inputs taken on faith — and recomputing examples
   during RECON, before any extraction, has surfaced real
   source-vs-data contradictions; treat it as a recon step, not just a
   test artifact.
10. **The glossary stage** — read the unresolved-term report
   (`unresolved-term` section of graph/reports/validation.md; the sweep
   command is `python -m graph terms`). Every hit gets CLASSIFIED, never
   silenced: a surface form or alias of an existing citizen | a stub
   concept (recognized-but-unmodeled; check the worklist first:
   `MATCH (s:Archetype {stub: true})`) | a pending_instance of a stub or
   label | a program `locals:` entry. The glossary IS the graph — terms
   resolve to citizens, and an unmapped system a program consults should
   be a stub concept, not a textual workaround. Read the source anyway.
11. **Unknowns exit as Judgment citizens** — load-bearing open questions
   become data/questions.csv rows (ABOUT the procedure), never resolved
   inline. Model the prose literally; record the gap.

Then landing: the approved YAML enters canon as a ground Procedure node
through the delta path (agentic-intake skill); derivation lifts
Steps/Outcomes from the body. **Before the new file's first delta, diff
its top-level key-set against an approved file of the same completeness
level** — a stray key the reader does not expect is refused at apply,
and the check is free at authoring time where the refusal costs a full
approve-apply cycle. Verify via MCP (HAS_POSSIBLE_OUTCOME
table, CALLS trace, outcome assignment edges, KNOWN_AT levels).

## Cautions

- Do not invent cases the prose does not define — when a corner has no
  case, model the absence and mark it with a comment.
- Guarantees and outcome names are DESIGNER decisions; a plausible draft
  is a proposal, marked REQUIRES DESIGNER REVIEW.
- Before promising any derived edge, name the projection arm that emits
  it — the scanner contract lives in the Transcribed doc string (on the
  graph) and data/procedures/README.md; expectations about projections
  are claims to dry-run, not hopes.
- No probabilities, ever (owner ruling). Uncertainty is open/closed
  closure + Judgment adjudication.
- Two-stage approval protects determinism: extract now, the approver
  approves, the ETL consumes only the approved artifact.
- No commits without explicit authorization in the current conversation.
