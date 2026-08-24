---
name: agentic-intake
description: Drive a full graph-native intake end to end — recon, plan gate, scratch authoring via MCP, delta review, canonize, drain to zero. Use when the submitter hands over a source (doc, table, notes) and says "intake this" / "let's ingest X", for any data-plane intake. For classification interviews alone use ontology-intake; for procedure-shaped sources use procedure-intake inside this flow.
---

# Agentic intake

The end-to-end workflow over the intake pipeline (design:
the engine's agentic-etl design record (design/ in the engine repo; graph/engine_docs/design/ inside an installed engine package)). The human appears exactly
twice — the **plan gate** and the **diff gate** — and everything between
is agent + machine loops. Boundary doctrine applies throughout:
@../../../design/ontology-doctrine.md.

**The invariant:** you author artifacts; only approved artifacts touch
canon; derived layers are never authored by anyone. Your write access is
the `neo4j-scratch` MCP connection ONLY — live is query-only, always.

**The source artifact is inviolable.** The engine never edits the
submitter's material — not a typo, not a heading, and never an *offer*
to edit it. Findings about the source (spelling, ambiguity,
contradiction) surface as suggestions or Question rows for the author
to rule; a ruled correction rides the ingestion with its own Decision
row while the file stays untouched — a source's variant spelling of a
canonical term is absorbed as an alias, never edited in place. Only
the author touches the artifact.

**Tables sit one notch looser, by written rule (owner-ruled): the
engine PROPOSES table changes and edits a data file only under
explicit owner dictation, recorded verbatim in a Decision row.**
Everything else lands graph-side and the file simply lags canon —
lagging sources are legitimate, silent table edits are not. The
destination is full table inviolability once every instrument reads
canon instead of sources; until then, dictation-with-receipt is the
only door. **File deletions are the strictest dictation class**: a
deletion lands only on an own-words imperative from the owner
("delete it"), never on agreement-by-number to a recommendation —
agreement is a sufficient receipt for edits, one grade too weak for
destroying a file. **Dictated table edits are CSV-aware**: a phrase
replacement that introduces a comma into an unquoted cell corrupts
the row silently. After every table edit, verify every row's column
count and run the corpus build — post-flip, the graph suite does not
read the tables; only the corpus build does, and a green suite proves
nothing about them.

## The flow

### 1. Recon (read-only; no human) — sealed reading FIRST
**The reading is sealed before the mapping opens** (owner-ruled): read
and comprehend the artifact ON ITS OWN TERMS — structure, vocabulary,
fact-grain claims, its own internal contradictions — BEFORE any canon
query. A reader whose head is full of canon assimilates the artifact
to existing categories before it has finished speaking, harmonizes
contradictions it should surface, and misses genuine deviations; the
kernel (metaontology structure) may inform the reading, project canon
may not. Only when comprehension is complete does the mapping open:
each artifact-local claim judged against canon — same-as / extends /
new / contradicts — every mapping a recorded Opinion with confidence,
low confidence batching to the owner's question sheet. (Held as
discipline — the lens system that will enforce it physically is
designed and built (the engine's lens module and its lenses design record (design/ in the engine repo; graph/engine_docs/design/ inside an installed engine package)); the seal
becomes physical when the declarations take graph residence at the
owner's gate.)

Open the reading room first: `python -m graph comprehend <artifact>`
fingerprints the source and builds its structure (section tree, bodies,
order, embedded-table refs) in the comprehension workspace, filing the
flat archive under `graph/comprehension/`. Canon is the subject matter,
never the document — the artifact's insides live here, not as canon
citizens; artifact quirks
(duplicate headings, odd nesting) are absorbed silently, never surfaced
to the submitter. Then read the source cold. Identify — by **semantic
comprehension, never word search** — every entity, relationship, and
rule it asserts, whatever the casing discipline. Resolve pronouns and indirect references; ambiguity
that survives multiple passes becomes an owner question, never a guess.
Resolve every candidate through the graph (read-only Cypher + the term
index; `python -m graph terms` is the mechanical backstop, not the
method). Check the stub worklist (`MATCH (s:Archetype {stub: true})`) and
prior Judgment rows — the term may already be a known-open item. Bucket
findings: *relates-to* / *introduces* / *uncertain*, with grades.
**A machinery risk you can verify during recon is a recon task, not a
risk to carry into the round**: read the code or run the tool now, and
if the gap is real, its ask joins the owner's collated sheet as a
numbered question. A "named risk" in the plan that a five-minute read
would have settled resurfaces later as a mid-round interjection — the
costlier shape.

### 2. The plan gate (the approver)
Present the what's-this-about proposal, **leading with the implications
preview**: what the approver GETS, what they LOSE or change, what it
AFFORDS later — each with a concrete example from the corpus. Then the
interview, per ontology-intake's discipline (three tiers; scenario
questions; the owner names everything and rules everything —
explicitly, never by silence). The interview arrives as ONE collated
question sheet — every question batched with its cited evidence,
named tension, consequences, and a recommendation; serial pinging is
not a permitted shape (see that skill's interview step).
Procedure-shaped content inside the source
follows procedure-intake at this point. Nothing has been written
anywhere.

### 3. Schema is ground on the graph — and changes by ceremony
The schema stratum (the concept citizens and their edges) is ground
truth on the graph itself: post-bootstrap machinery reads it from the
graph, never from a schema file, and the schema anchor's version
auto-stamps from the event-log sequence at apply. **Schema changes
ride the schema ceremony**: an owner-gated round may add a new
DECLARED concept (the Archetype arrives WITH its DECLARED_IN edge, and
usually INSTANCE_OF into its parent), edit a schema row's doc text, or
remove an UNREFERENCED schema row — the delta report itemizes these
under its marked ceremony section, and the owner's approval of that
round IS the ceremony ruling. Everything else on the stratum — new
labels, spec/catalog changes, renames, referenced removals — still
refuses by name (data moves underneath those; they ride the migration
charter) and PARKS as a Question at the plan gate for the owner to
rule and sequence; it never blocks the fact-plane work that doesn't
need it, and it is never worked around with a lesser encoding. Facts
whose schema doesn't exist yet wait with their Question.

### 4. Scratch authoring (agent + machine)
Reset scratch first (`python -m graph restore --database scratch`) — stale
scratch produces phantom diffs. **The standing first authoring move is
clearing the previous round's debts**: stamp that round's shipped PR
link onto its Judgment rows, and land any edges it deferred under
marker rows whose endpoints now exist in canon. A round that skips the
opening move leaves the debt to compound — one round of lag is the
design; two is a backlog. Then author **ground facts** through the
`neo4j-scratch` MCP connection, the way agents naturally work: create,
query your own work, fix, iterate.
- MATCH existing endpoints, MERGE only the new node/relationship (a
  whole-path MERGE duplicates existing nodes and trips the uniqueness
  constraint).
- Every non-obvious fact carries its receipt as properties: `from_text`
  (verbatim source quote), `source` (where), `grade: 'agent-proposed'`.
  Receipts are review evidence — canonize deliberately never renders
  them into files.
- NEVER write derived edge types (INSTANCE_OF, projections, MENTIONS,
  lift edges, KNOWN_AT…) or machine labels (Archetype/Step/Outcome) —
  the delta lint rejects them with the reason.
- **Identity stays single-label; membership is multi.** Each citizen is
  keyed and exported by exactly one roster label — its home, its
  catalog, its source — and that never changes. But a citizen may be
  declared a member of more than one concept: author a ground
  `DECLARED_MEMBER_OF` edge FROM the citizen TO a Concept Archetype,
  carrying a required `basis` rationale, and derivation folds it into
  the citizen's `INSTANCE_OF`. So a gem its roster makes a Treasure can
  ALSO be declared a Tool while a sibling gem on the same roster is not
  — an overlap no longer needs the shared-catalog-vocabulary workaround.
  The edge only ADDS membership and never re-homes the citizen: its
  target must be a subject-matter Concept (never a Facet, never another
  label's Archetype), and `INSTANCE_OF` itself stays never-authored —
  the fold computes it.
- A concept Archetype born by THIS round's schema edit does not exist
  in scratch (scratch is cut pre-schema from the backup) — anchor
  Judgment ABOUT edges for brand-new labels to value citizens instead.
  The same constraint blocks DOMAIN ground edges: an edge whose target
  citizen is born by this round's schema edit cannot be authored in
  scratch at all. Declare exactly those edges in the round's STITCH
  file — `graph/proposals/current/stitch.json`, a JSON list of
  connections in the proposal document's edge shape (type, from_label,
  from_name, to_label, to_name, optional props). They ride the same
  approval and land in the same apply, after re-derivation births
  their endpoints; the delta report itemizes them under "Stitch" and
  refuses any that don't genuinely need it. Never re-point a deferred
  edge at a lesser endpoint that happens to exist. (Marker-row
  deferrals from earlier rounds still land at the opening move; new
  rounds use the stitch.)
- Provenance URLs on Judgment rows: take the repo from `gh repo view`,
  never guess the owner (a guessed owner once landed in a whole batch
  of rows and forced a correction round).

### 5. Delta + self-review (agent + machine)
`python -m graph delta` — the itemized, linted changeset
(graph/reports/delta.md). Read it against your own plan: every
surprise is either fixed in scratch or demoted to the uncertain bucket.
Lint violations are yours to fix before the approver ever sees the
report. Then `python -m graph canonize` (dry run) — confirm everything
renders deterministically; a REVIEW-REQUIRED item at this stage means a
schema ruling was missed: go back to step 3 (or the plan gate if it is a
genuinely new decision).

### 6. The diff gate (the approver)
Present the delta report — and offer the Bloom walk on scratch (the
proposal is explorable as a graph before it exists in canon). The
approver resolves the uncertain bucket: rule, "give it a go" (back to
step 4), or park as Judgment citizens. Approval here is approval of the
exact changeset.

**Mid-round refactor pressure is never round scope.** A tempting
rename, a structural cleanup the round doesn't need — park it as a
Judgment row routed via HAS_DISCIPLINE / HAS_AUDIENCE to the project's
Discipline and Audience citizens. The kernel declares those two
classes only; each project's values are its own, disclosed by the team
or discerned from real cases — the first round that needs a value
proposes it at the escalation gate like any new vocabulary. Parked
pressure is design input for a later phase, never scope creep.

### 7. Approve, canonize + drain to zero (machine)
When the approver rules "approved" at the diff gate, record it:
`python -m graph approve` (the record names the human; the proposal's
content hash is frozen — apply replays exactly what was reviewed, and
refuses by name if scratch or the base moved after approval). Then
`python -m graph canonize --apply` — GRAPH-NATIVE since the flip:
no file is edited. Apply verifies the live database still
matches the backup, applies the pinned changeset to the ground layer,
re-derives every machine layer, loads canon, re-exports the backup FROM
the database, and writes the EVENT LOG (chained entry in
`graph/proposals/applied.log` + the delta's inverse) — all one command,
refusing collated and writing nothing on any failure. Then the ritual:
pytest → commit the export + round archive + applied.log line in one
change set. The next round cuts scratch fresh
(`python -m graph restore --database scratch`). `load` and
`export --from-sources` are bootstrap scaffolding only.

### 8. Bookkeeping (same standards as any round)
Judgment rows for parked items (they can flow through scratch + canonize
too), the ontology TODO block, the glossary stage (classify every
unresolved-term hit; shrink the stub worklist), skills updated with any
lesson learned in-session — **stated timelessly and domain-neutrally**:
no issue numbers, no dates, no project vocabulary; the rule stands on
its own, with an agnostic example where one earns its keep. PR
provenance lands via the NEXT round's standing opening move (step 4) —
the shipped PR's link cannot exist before ship, so the stamp is always
one round behind by design. Definition
of Done applies: tests, docs, skills ride along.

## Gate conduct

- **Lead with an example** at every built-work gate: the command, the
  expected output, one thing to break. Explanation after, never instead.
- **Rulings ride chat, not review-panel comments.** Inline plan-panel
  comments have been lost in transit — anything not in the chat or a
  file does not exist. Number every question on the collated sheet so
  the owner can rule tersely by number; if panel comments arrive
  anyway, echo them back in chat before acting on them.
- **State the database picture** at every gate and demo: which database
  currently shows what (live = branch state during a round; merged main
  returns on reconcile).
- **End every gate with the Question harvest line**: "N new Questions
  filed this round — rule any now, or all park."
- **Churn is healthy** — mid-gate rulings are adversarial review
  working. At a THIRD substantive ruling in one gate, OFFER a follow-on
  round split; the approver decides. Never engineer the churn away.

## Round scope (owner-ruled)

**The submitter chooses the round's scope at the start of every
sitting** — one chapter, a subsystem batch, a paragraph; the machinery
imposes no cadence. Open a campaign session by asking what this
round's scope is (default: a subsystem batch). Inside a
batch, the per-chapter loop runs agent-side; the submitter sits one
plan gate and one collated diff gate. The owner is trialing the
breakdowns firsthand in clean sessions; when multi-submitter arrives,
cadence becomes a per-person graph-resident preference.

## The convergence loop

When a draft must reach parity with a source (chapter regeneration, the
book campaign), run the loop — never hand-polish toward a quiet judge:

1. **Cold draft, fenced**: every draft sentence traces to a graph
   record you can name. Canon gaps stay red on purpose — smuggling
   source text into the draft hides real thinness. State the fence's
   honesty limits aloud (prior exposure is discipline, not amnesia; the
   judge is the objective check).
2. **Judge, then burn down only what needs no one's judgment**
   (findings are ROWS in the reading room — query the open set
   beside its sections, update statuses as you resolve; the prose
   report is a rendering, not the record): a
   finding is agent-resolvable ONLY when its fix is fully determined by
   the graph and rulings already on record — presentation-form
   mismatches, rewording a draft sentence toward the source where the
   graph already holds the fact, deleting the draft's own inventions.
   Any fix that would add, drop, or bend meaning is not yours; it goes
   to the gate. When in doubt, escalate. The goal is that the human
   never sees finding 3 of 64 — and never misses one that was theirs
   to rule.
3. **One collated escalation gate**: everything needing a human word,
   grouped by resolution channel — canon gaps (become intake), flavor
   (verbatim-carried or Approved Omission), examples (per the
   standing examples Decision on the graph), harness defects (their
   own issues, with a one-line
   engine ask). Each group states what each answer does.
4. **Rulings recorded by identity** (Decision rows, Approved Omission
   rows), then regenerate and re-judge. Converged parity = zero
   UNAPPROVED differences — the report may stay non-empty forever, so
   long as every line carries a ruling.

Standing rules the loop rides on:

- **Every PASS names its judged surface.** A green scorecard once
  lied because prose inside procedure-cited sections was unjudged.
  Unjudged space is either zero or declared aloud in the same breath
  as the verdict.
- **Verify presentation artifacts in the audience's renderer.** A
  diagram verified in VS Code shipped unreadable on GitHub three times.
  The acceptance test is the renderer the audience actually uses.
- **Question triage at phase boundaries**: every retro/phase-cut
  sitting opens with the carried Questions — rule some, park the rest,
  never let the list grow silently.

## Gate voice

- **Shape: asks first, decisions second, elucidation last.** Every gate
  opens with **"here are the asks"** — a numbered list of exactly what
  the approver must do or rule on — then **"here are the decisions I
  made"** — judgment calls already taken — then the context and
  reasoning for whoever wants them. Never a storytelling lead-in: the
  reader must tell at a glance what needs them versus what is handled.
- **The narratives' five voice rules govern gate presentations BY
  DEFAULT, for every submitter — including the owner.** Machinery
  vocabulary (proposal ids, version numbers, command names, Cypher)
  appears only below a marked "the machinery, for the record" fold, or
  when the submitter asks in kind. The owner's stated preference
  (plain gates, machinery on request) is recorded by identity against
  the empathic-presentation Question.
- **Self-check BEFORE SENDING any gate — run the list per gate, every
  gate; the same-message rule has now failed two independent sessions
  when left to memory:**
  1. Asks → decisions → elucidation, in that order?
  2. Does every question grid carry its FULL context **in this same
     message** — the decision, the evidence, each option's
     consequences, a recommendation? The approver must be able to rule
     from this message alone; context living two messages back is a
     defect.
  2b. Is the context CITED, not paraphrased? Quote the actual sources
     verbatim — the artifact's sentences, the graph record's own text,
     the tracker item's words — each labeled with where it lives, then
     name the tension between them explicitly, then pros/cons per
     option in prose. Narrative ABOUT the sources is not context; an
     approver who cannot see the raw material cannot rule. And if the
     approver rejects a grid or asks for context, the next message is
     evidence and prose only — re-offering a grid immediately, however
     enriched, reads as hammering; let them rule in their own words.
  3. One re-read in the submitter's domain terms only — any sentence
     needing the machinery glossary gets rewritten or moved below the
     fold.
  4. Are answers to the submitter's direct questions in the turn's
     FINAL message — never only in between-tool status text, which the
     submitter may never see?

## Mapping and drafting lessons

- **Design-intent prose sorts five ways at intake — never into one
  "philosophy" bucket.** Premise (the world's terms), authorial intent
  (what the work is for), REQUIREMENTS (binding directives, checkable
  where worded so — kernel Judgment citizens), theses (claims about how
  the system behaves — several verifiable), and rationales (why a
  mechanic is shaped so — these attach to their mechanic as doc-notes,
  never stand alone). Premise/intent/theses home under the kernel Theme
  concept; requirements become Requirement rows; the sort question is a
  standing intake habit beside Units and ladder-direction.
- **A worked example gets a disambiguation question at intake, never a
  silent default: "preserve this exact example word-for-word, or treat
  it as one illustration the system may regenerate from the mechanic?"**
  The two fates have different homes (a carry-verbatim row vs. a
  regenerable render), and only the owner knows whether the example's
  particular wording is the point.
- **A forward reference in source prose ("described later", "see the
  end of this chapter") gets a disambiguation question at intake: is the
  ordering intentional?** If yes, the ordering is a claim to carry; if
  no, the reference is glue a regeneration may replace with a better
  cross-reference. Never decide silently in either direction.
- **Normalizing stored text must never lose information.** If a
  registry keys by a normalized form (case-folded, whitespace-collapsed),
  the original bytes are stored beside the key — normalization is for
  matching only. A store that cannot reproduce its input verbatim is
  distorting it.
- **A carried-verbatim row's name key is the whitespace-collapsed,
  lowercased passage** (`" ".join(text.split()).lower()` — trailing
  punctuation KEPT), with the original bytes in its text property. This
  is NOT the judge's sentence normalization (which strips trailing
  punctuation); confusing the two produces rows the matcher silently
  never finds. Read an existing row and mirror it exactly.
- **Scope notes are predictions, not boundaries.** When a source
  changes, recon verifies the FULL citation set — every program and
  citizen citing that source — never just the subset the plan
  predicted. A citation the plan missed, found at recon, is a
  footnote; found mid-round, it is an interjection.
- **A relationship the source states in a column may already be canon —
  check under its DECLARED edge-type name before authoring it.** When the
  schema maps a source column to an edge type, a bootstrap load may have
  already materialized those edges; re-authoring them duplicates or trips
  a uniqueness constraint. Read the edge type's exact name from the schema
  and query for it — never probe with a guessed name and conclude "absent"
  from a miss (a guessed name returns zero while the real edges sit under
  the declared one). The same holds for template-instance bindings and
  per-member value tags: verify what the load already carried before
  proposing to add it, so the round authors only the genuinely-new.
- **Give every new label its `doc:` string AT MAPPING TIME, drawn
  verbatim from the chapter.** Chapter prose without a canon home keeps
  regenerations red and forces a second schema round. The label `doc:`
  is the canon home for section-level prose; Theme citizens home thesis
  sentences; Quote citizens home quoted material with attribution.
- **Procedure nodes are ground facts**: they enter canon through
  scratch + delta carrying body (the full approved YAML text),
  completeness, closures, inputs/outputs, source, source_path (mirror
  an existing transcribed Procedure node). `rederive` alone never adds
  them — it lifts Steps/Outcomes FROM the ground body at derivation.
- **A program file approved in a prior round does not prove its citizen
  landed.** A round has shipped approved program files while forgetting
  their ground nodes, and the gap surfaced only when a later round went
  looking. During recon (and again at delta self-review), diff the
  schema's approved-program file list against the working graph's
  procedure citizens; any file without a citizen is prior-round debt —
  land it with the opening move, and file the finding as its own issue.
- **Chapter drafts of procedure-cited sections must embed the rendered
  program** (`python -m graph generate "<name>"`) — the roundtrip's
  procedure tier judges the rendering's claims, not just the prose.
- **Cold-draft formatting**: the claim splitter treats `*` bullets as
  paragraph continuations (only `-`/`+`/`1.` start units) — separate a
  lead-in line from a `*` bullet block with a blank line or their
  claims merge and the lead-in reads as omitted.
- **Quote program text that carries YAML-active characters.** An
  unquoted scalar silently truncates at ` #` (an inline citation eats
  the rest of its sentence) and breaks the parse at `: ` (a colon-space
  mid-sentence reads as a nested mapping). Provenance lives on Judgment
  rows, not in body text; quote any step that needs punctuation.
  Validation carries a tripwire for the silent case (a ` #` tail that
  vanished in parsing is flagged with its line number), and `generate`
  remains the eyes-on check.
- **Program bodies sync from their approved files — never by hand.**
  After editing a program file, `python -m graph delta --sync-bodies`
  rewrites the working graph's copy from the file; every delta run
  verifies the sync across the whole working graph and refuses by name
  when a body drifted. The paste-and-hash ritual is retired. A
  chapter-spanning program lists every section it draws from
  (`specified_in.section` takes a list); receipts check against all of
  them.
- **A concept rename re-points its ground anchors in the same
  changeset.** Ground edges anchored to a machine node survive
  re-derivation only while the concept stays declared — a rename
  orphans them silently. Query the machine node's incoming ground
  edges before renaming; re-point them to citizens that survive (the
  machine layer is never authored by hand, so a vanished endpoint
  cannot be recreated from scratch).
- **Answer keys**: cells meaning "no value exists here" beyond the
  global empty markers (a project's special glyphs) are declared per
  key with `skip_values:` — never patched into the engine's
  EMPTY_MARKERS.

## Cautions

- **Two gates, always.** No matter how mechanical the intake looks, the
  plan gate and diff gate are never skipped or merged.
- Branch from `origin/main` explicitly; issue-first; no commits without
  explicit per-ship authorization in the current conversation.
- Reports are the user interface: anything you surface to a human
  follows the error doctrine (Attempted X / context Y / failed due to Z,
  collated, with remedies).
- **Gate presentations are human prose, not pipeline prose**: lead
  with what changes in the CORPUS's terms — "each rank in the ladder
  gets its behavior sentence attached" — one plain sentence per fact.
  Delta/canonize/node/edge vocabulary stays in the linked reports;
  the approver should never need the machinery glossary to approve their
  own content.
- Draft-then-verify discipline: claims about what the machinery will
  derive are tested against the machinery (run the tools), not asserted.
  **A dry run proves only the stages it actually executes** — a
  verification that lives in the apply alone (re-derivation, a
  completeness census) can refuse a round the dry run waved through.
  Never present a dry run as evidence that findings "don't block";
  either run the blocking stage or state aloud which stages the dry
  run skipped.
- If the source is quirky-formatted, write the normalized canonical
  intermediate (approver-approved, hash-pinned) rather than proposing
  engine parsers — the kernel does not grow per artifact.
- **Engine asks are parser-era scaffolding.** The named one-line
  machinery ask (`skip_values` set the model: shape + blast radius,
  its own test, lands only on an explicit yes) is the CURRENT
  correct form when an artifact wants a primitive the engine lacks.
  It sunsets with the fixed parsers: once agents read artifacts
  natively, a novel table shape is a comprehension problem, and the
  destination CX never surfaces engine internals to a submitter at
  all. Prefer shapes that need no engine change; never work around a
  missing primitive with a lesser default.
- **Engine additions speak no project vocabulary.** Docstrings,
  comments, and test names inside engine code draw their examples from
  an imaginary domain, never from the host project's — the
  vocabulary-leak test enforces it, and a leak found at review is a
  rewrite, not an exemption.
