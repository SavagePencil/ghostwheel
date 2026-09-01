---
name: ontology-intake
description: Classify a new artifact (CSV table, doc section, design note) against the existing ontology and grow the project ontology through owner dialogue. Use when mapping an unmapped CSV, ingesting prose rules, or when the submitter says "let's intake/map/classify X".
---

# Dynamic-ontology intake

Scope note: this skill is the CLASSIFICATION AND INTERVIEW discipline —
it powers the plan gate. For a full end-to-end intake (scratch authoring
via MCP, delta review, canonize, drain to zero) use the **agentic-intake**
skill, which invokes this one at its step 2.

Boundary context: `python -m graph docs ontology-doctrine` — **intake grows the
PROJECT layer only.** If the artifact demands something kernel-shaped (a new
root, a new common facet), that is a Judgment moment: raise it as a Question
for design dialogue; never resolve it inline.

The hypothesis this procedure serves (validated on early table
mappings, ~80/20): most of a mapping falls out mechanically; the remainder isn't noise —
it's the artifact's most interesting design questions. Surface them; the
owner answers them; many become Judgment-root material.

## Procedure

1. **Read the artifact cold**, plus any docs that embed or describe it.
2. **Classify against the existing ontology, in three confidence tiers** —
   report all three explicitly. **Verify candidates against the source
   tables by FULL name, never by name fragments** — a fragment query
   misses template instances and long-form names, and a wrong
   "nothing defines this" claim has minted a redundant stub over an
   existing template. When claiming absence, read the table.
   - **Tier 1, mechanical** (would auto-propose): exact column-header matches
     to existing catalogs; cell values resolving to existing node names
     (through aliases); edge shapes already in the vocabulary.
   - **Tier 2, observations** (flag, don't act): near-matches, sibling
     patterns, sentinel values, terminology drift.
   - **Tier 3, genuine owner questions** (the 20%): concept classification,
     facet membership, naming, modeling choices, and **missing engine
     primitives a second consumer already wants** (see the missing-primitive
     rule in Cautions). Never answer these yourself.
3. **Read the facet checklist from the graph**, not from memory:
   instances of the `Facet` archetype (with `doc` explanations). Ask of the
   new concept: ordered? exclusive? stateful? — one question per facet.
   **For every ordered ladder, establish its DIRECTION** (owner rule):
   ascending, descending, or neither — deduce it from the artifact's own
   mechanics where possible, and where it is not clear to deduce, ask
   the owner. Record the answer where the ladder is declared. Rules
   prose saying "above/higher" over a ladder whose direction was never
   pinned is exactly how opposite readings of the same sentence survive
   into play.
4. **Resolve Tier 3 by scenario interview**: pose concrete situations
   from the corpus's own world, engineered so different answers imply
   different classifications. Expect the owner to redirect to
   prose — read the cited docs and come back with findings. Expect judgments
   to flip; that's the process working.

   **The interview is ONE collated question sheet — never a stream.**
   Serial questioning — one ping at a time, context scattered across
   messages, the owner put on the spot — is not a permitted interview
   shape, however urgent a single question feels. Instead: finish the
   recon, compose EVERY owner question, then present them together as
   one sheet the owner reads at their own pace and answers in any
   order. On the sheet, each question is BUILT with its context, not
   dressed at presentation: the evidence quoted verbatim (the
   artifact's sentences, the graph record's own text — each labeled
   with where it lives), the tension between them named explicitly,
   what each answer would do, and a recommendation. A question the
   owner cannot rule on from its entry alone is not ready for the
   sheet — hold it and gather the missing context first. Follow-ups
   spawned by an answer join the NEXT collated sheet (or the diff
   gate), never an immediate counter-question; after a rejected or
   challenged sheet, the next message is evidence and prose only.
   (This mirrors the convergence loop's one-collated-escalation-gate —
   the shape that has never drawn a complaint. agentic-intake's
   gate-voice self-check enforces the same rules at presentation time;
   the discipline starts here, where the questions are made.)
5. **Prose rule (two-stage, protects ETL determinism)**: never have the build
   interpret prose. Extract a structured proposal (table/YAML) from prose
   NOW, with the owner; the approver approves it; the approved artifact goes
   in git; the deterministic ETL consumes only that. Mark all extracted
   content as REQUIRING DESIGNER REVIEW.
6. **File findings as issues** (issue-first convention): data problems,
   terminology drift, rules gaps — one issue per finding class, presenting
   options without deciding them.
7. **Implement only after the owner rules**: ontology.yaml entry
   (concept list, ordered flag, catalog, properties, relationships — with
   `on_missing: placeholder` for name-like columns, `report` +
   `unmatched_property` for prose-like columns), then the maintenance
   loop (see the rebuild-graph skill): validate → rederive (the backup
   re-export rides it; golden in the same change set) → test → restore
   scratch → MCP verify.
8. **Update the TODO block** in ontology.yaml (remove the mapped file, note
   deferred aspects) and record deferred machinery explicitly (e.g.
   "TRANSITIONS_TO awaits docs spike").
9. **The glossary stage**: run `python -m graph terms` after mapping. New
   citizens often resolve old unresolved terms; whatever remains gets
   classified (surface form/alias | stub concept | pending_instance |
   reject), never silenced. When a mapped label absorbs a stub concept's
   territory, graduate its pending_instances into real rows and delete the
   stub — the worklist (`MATCH (s:Archetype {stub: true})`) should shrink
   with every intake.

## Cautions

- **Missing engine primitive = Tier 3 when a second consumer exists.** A gap
  in the engine (no `bool` type, no inverse for an existing edge
  shape, ...) is a Tier 2
  observation *only* if you would genuinely live with the workaround forever.
  The moment a second consumer is visible — another CSV, a TODO-block line —
  it becomes an owner decision: surface the primitive, do not bury a
  text/string workaround in the plan as the default. A column of yes/no
  markers (`Y`/`N`, `✓`, blank-for-false, ...) is a boolean — propose the
  `bool` type, never a `text` flag storing the raw marker. Check what the
  column's truthy/falsy vocabulary actually is; the marker varies by table.
  (Landing the engine change is still gated by the `graph/*.py` bright-line;
  surfacing it in the plan is not.)
- Genuine taxonomy (a citizen is a KIND of a concept, not an instance of
  it) is declared on the concept entry (`subtypes:`) and derived by the
  engine at every rebuild — never authored as ground edges. Activating
  it for a project's first case is a kernel ceremony: explicit owner
  dialogue, recorded as a Decision.
- Placeholder pollution: prose fragments make bad placeholder nodes — use
  `on_missing: report` for mixed-content columns.
- Comma-splitting fragments clauses that contain commas; the report catches
  them — read it.
- The owner rules all naming. Full-text names over abbreviations
  (aliases map the CSV codes). Check docs for canonical terminology before
  proposing names — the docs outrank the README, which outranks the CSVs.
- **Edge naming is STRATIFIED** (owner ruling): (1) kernel/facet
  mechanics (INSTANCE_OF, PRECEDES/FOLLOWS, TRANSITIONS_TO, FULFILLS) stay
  generic — they belong to the facet, not a domain; (2) parallel domain
  systems are domain-explicit, always — two systems with same-shaped
  tiers get HAS_<SYSTEM-A>_TIER and HAS_<SYSTEM-B>_TIER, never one
  shared edge; (3) one system with many participants shares a name
  and splits only if the system splits; (4) with no parallel yet but a
  foreseeable collision, name preemptively-explicit
  (CONSUMES_<RESOURCE> when other consumables are foreseeable). Do
  not propose polymorphic reuse across parallel systems.
- No commits, ever, without explicit authorization in the current
  conversation.
