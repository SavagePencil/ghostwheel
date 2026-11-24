# Ghostwheel

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Ghostwheel** keeps the truth of a growing creation — a story, a game, a
manual, a catalog — consistent, remembered, and under its maker's control, so
the thing you finish is the thing you meant.

## The idea, plainly

You have something to say — about patience, maybe, and building things that
last — and you've chosen *The Three Little Pigs* as the way to say it. So you
set out to make your own telling: your pigs, your wolf, your ending; maybe a
picture book, maybe a game. The source material already disagrees with itself
— in the old telling the wolf **eats** the first two pigs; in the modern one
they **escape** to their brother's brick house — and your drafts will
disagree soon enough, as drafts do. Every one of those choices shapes your
message. The work stays *yours* only if something keeps track of what the
story holds true right now, which choices were made on purpose, and why.

Ghostwheel is the tool that keeps track. Hand it your material and it
remembers every fact in the story — each pig, each house, who built what, who
got eaten — and beside every fact, the exact sentence it came from and the
day you chose it. Ask *"why does my book say the pigs escaped?"* and the
answer arrives with the quote, the telling it was taken from, and your
recorded ruling — *the wolf eating them was too dark for the message.*

Nothing changes behind your back. When new material arrives — a newly found
telling, an editor's notes, work from a helper (human or AI) — the proposed
changes are laid out beside what the book already says: here is the new
claim, here is the old one it contradicts, here is everything that would
ripple. You say yes or no. Only then does the book change, and every change
can be undone.

It learns to speak your language, not the other way around. You never fill
out a form of someone else's categories: the words your tale uses — Pigs,
Houses, Straw, the Big Bad Wolf — become the book's own working vocabulary,
asked about in plain questions ("is a Straw House its own kind of thing, or a
House made of straw?") and free to change later when you see your world more
clearly, with every page that used the old word following along.

And once it holds your truth, it works with you. Ask it anything — *which
pig survived in my telling? what does the wolf want?* — and it answers from
the facts you approved, citations attached, never from a guess. Hand it a
half-formed thought — *what if the wolf comes back, reformed?* — and it
proposes: here is what that touches, here is what it contradicts, here is
where your story already leans that way. The ideas are offered; you still
rule.

It can *make* things from that truth, too. A synopsis for the back cover, a
chapter retold for younger readers, a table of the three houses and what
each withstood, a brief for the illustrator naming exactly which characters
appear in the plate — each generated from the approved facts and only the
approved facts, so nothing invented sneaks in; each steered by you, and
regenerated as the story moves.

Even the parts of a story that usually live only in the author's head get
seats of their own. Themes — *patience beats haste*, say — live in the book
as first-class things, tied to the scenes and choices that carry them. Ask
what carries your theme and get a real answer; generate a retelling and the
theme rides along; propose a change and see what it touches — including
which themes it serves or undercuts. The soul of the work is kept with the
same care as its facts, so the storytelling stays whole.

Your collaborators get rooms of their own. An illustrator keeps the paintings
in a collection of their own, where each picture knows which characters it
shows and which version of the story it was painted for — when the story
moves on, the studio hears about it. A co-author drafts a whole alternate
ending in a private copy; you keep the parts you love, and the ending that
loses is archived, never lost.

And different readers can be handed different books. The young-readers
edition simply never shows the wolf's supper — not crossed out, just not
there, with no loose threads where it would have been.

None of this is special to storybooks. A game's rules, a lighthouse-keeping
guild's manual, a legal code — any body of truth that must stay consistent
while many hands grow it — works the same way. The rest of this README is
the machinery underneath, told through the same storybook.

## What it is

**Ghostwheel** is a project-agnostic knowledge-graph engine over a
property-graph database (Neo4j today). You point it at a knowledge base — a
rulebook, a manual, a storybook, a catalog — and it holds that knowledge as a
queryable graph of **citizens** (facts, definitions, procedures, rulings,
quotes), grows it through reviewed changes, and serves it back with citations.
Nothing enters the graph without provenance; nothing changes it without an
owner's approval; every applied change is recorded in a chained, reversible log.

**The worked example, in engine terms.** The Three Little Pigs threads this
README as two knowledge bases: **story** holds the tale; **art-assets** holds
the paintings, pins story at an edition, and cites its Wolf through
bookmarks — when the story moves ahead, the art hears about it at its next
round. The picture book itself is a **world**, which is a role, not a type:
an ordinary knowledge base whose own subject is the knowledge bases it
gathers and how they relate. Nothing is melted together; the members stay
sovereign. The schema, likewise, is grown rather than designed: the intake
interview births the keeper's vocabulary as citizens in the keeper's own
words, and the ontology moves by gated ceremony as understanding deepens
(aliases, label births, declared renames that ripple with their inverses
recorded — see "the ontology moves to fit the user," below). A second voice
recurs alongside: an operations manual — a lighthouse-keeping guild's — where
"Light the Lamp at Dusk" is an approved program and an inspector's ruling is
a cited citizen like any other. (This repository's test fixtures use a third
tiny storybook — **Gems**, **Chapters**, **Beasts**, **Grades** — same
shapes, smaller cast.)

Ghostwheel is a working engine with live consumers: they pin exact release
tags, every change rides a reviewed pull request, and the committed export
makes each graph change reviewable as an ordinary diff.

At its heart Ghostwheel keeps a single body of agreed-true knowledge — **canon**
— as a property graph, and surrounds it with machinery that keeps that graph
honest:

- **Canon is the graph.** The live Neo4j database is primary. A deterministic,
  line-oriented **export** in `graph/export/` is its committed backup, written
  *from* the database and read back into it by `restore`. Because the export is
  deterministic, a graph change reads as a clean diff in code review, and the
  export is the baseline for the golden test.
- **Schema lives on the graph, as ground.** The knowledge base's own vocabulary
  — its categories, labels, catalogs, relationships — are themselves citizens on
  the graph (the **Archetype** stratum), authored truth read back by the engine.
  They are not a config file the graph is generated from; they are part of canon.
  (The storybook's House catalog and its Material ladder — straw < sticks <
  bricks, an Ordered facet — are authored citizens like everything else.) Born
  at intake from the keeper's own words, they move by gated ceremony as the
  keeper's understanding moves — see "the ontology moves to fit the user,"
  below.
- **Two ontology layers.** The engine ships a project-agnostic **kernel**
  (`graph/metaontology.yaml`): the four roots — **Concept**, **Facet**,
  **Provenance**, **Judgment** — plus a common facet library (Ordered, Exclusive,
  Stateful, …). Each knowledge base layers its own **project ontology** on top.
  References flow one way, project → kernel; the kernel must stay meaningful for a
  knowledge base that has never heard of yours. See
  `python -m graph docs ontology-doctrine`.
- **The kernel's citizens wear brackets.** Every kernel-declared label a
  citizen can carry is bracketed — `[Procedure]`, `[Decision]`, `[Question]`,
  `[Artifact]`, `[Step]`, … — because brackets mark machinery AND never
  shadow a word a designer's world might need (a story has decisions and
  artifacts of its own). Roots, facets, and the Metaontology/Ontology anchors
  are Archetype-row vocabulary and stay plain; `Theme` stays plain as designer
  lexicon. In Cypher a bracketed label is backticked: `` MATCH (d:`[Decision]`) ``.
  Every citizen whose label has a schema row is a direct instance of that
  row, and its membership then folds up the label's `SUBTYPE_OF` chain (a
  row of a kind is an instance of every concept that kind is a kind of).
  A kernel ceremony may rename what it declares: the metaontology's `renamed`
  map drives `kernel-migrate`, which relabels every citizen, re-points every
  edge, rewrites project specs and the attribution ledger, adopts a same-named
  project label, and lands it all as one chained round with its inverse.
- **Artifacts are kernel citizens.** An `[Artifact]` is the thing a person
  hands over; WHERE it is lives on `[Artifact Location]` rows behind
  `LOCATED_AT` (scheme, address, one primary; `[File Location]` is the kernel's
  kind, others are a world's own taxonomy). Its grade is Completeness as
  CONTENT HELD (Cited · Attested · Transcribed); verification is the location
  row's own fact, written at apply, never folded into the grade. `DEPICTS`
  names its objective contents; an `[Interpretation]` says what it stands for
  to this world, per intent; a `[Resolver]` binds a location kind to the
  procedure that opens it; `superseded_at` and `SUPERSEDES` retire it as an
  intake ruler — information for the census, never a defect. (The storybook's
  cover painting is an `[Artifact]`: its file row fingerprinted and verified at
  apply, `DEPICTS` naming the Wolf and the brick house it shows — and when the
  art lives in its own **art-assets** knowledge base, `DEPICTS` cites the
  story's Wolf through a `[Citizen Bookmark]` into the pinned dependency.)
- **Changes flow through rounds and a diff gate.** Canon never changes by direct
  edit. An author works in a **scratch** database cloned from canon; the itemized
  changeset — the **delta** — is linted, reviewed, and approved by the owner at a
  **diff gate**; only then does `canonize --apply` replay exactly the approved
  changeset into canon, re-derive the machine layers, re-export the backup, and
  chain the event log. See `python -m graph docs agentic-etl`.
- **Lenses decide who sees what.** Visibility is a first-class layer enforced on
  the in-memory graph value itself, so traversals never yield a hidden element and
  derived layers recompute coherently under a lens. See
  `python -m graph docs lenses`.
- **The database is a backend.** The engine's durable contract is the
  deterministic committed export plus the chained event log; the live database
  is rebuilt from that backup by `restore`, and many verbs read the backup with
  no database at all. The driver-and-Cypher seam is deliberately narrow (8 of
  the engine's 35 modules touch it); Neo4j is the backend today — its
  multi-database isolation and roles are both used — and a future
  property-graph backend (FalkorDB, say) is a contained port behind the same
  contract, not a rewrite.

New here, or wondering what a "floor", "round", or "lens" is? The glossary — a
lay tier and the working vocabulary beneath it — lives in
`python -m graph docs north-star-workflow`. A knowledge
base's own domain terms live on the graph itself (`python -m graph terms`; every
citizen carries its own doc). Carried source quotes stay honest via
`python -m graph receipts` — a DB-free sweep that names every stale quote with
what it was hiding (an honest home beneath, or intake debt), while the delta
gate refuses a freshly authored quote its cited source does not contain.

## Why the package is called `graph`

The distribution is **`ghostwheel`**; the importable Python package is
**`graph`**, and the CLI is reached as `python -m graph` (or the installed
`ghostwheel` console script). Keeping the internal module named `graph` is
deliberate: a knowledge base that consumes the engine imports `graph` and runs
`python -m graph` with zero churn. The product name lives on the outside; the
code keeps the name its consumers already depend on.

## Quickstart

### 1. Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

### 2. Stand up the database (Neo4j today)

The default backend is **Neo4j Desktop 2** — its Explore/Bloom visual tools only
work against a Desktop-managed instance:

1. Create a local DBMS (any name), set a password, and start it.
2. `cp .env.example .env` and fill in the Bolt URI and credentials.

A `docker-compose.yml` offers an alternative scriptable backend for automation
and CI (`docker compose up -d`); the visual Explore tool does not work against
it.

### 3. Point Ghostwheel at your database

`.env` holds the connection. The live canon connection uses the **query-only
reader** credentials (`NEO4J_READER_*`) — canon is written only through the
reviewed delta path, never through an ad-hoc connection.

## Commands

Run as `python -m graph <command>` (or `ghostwheel <command>` once installed).

| Command | What it does |
|---|---|
| `init [<dir>] [--name <kb>] [--world]` | Seed a new knowledge base, **born graph-native**: write a committed backup holding the kernel's schema stratum alone into `<dir>/graph/export` — no `ontology.yaml`, no sources, no database. `--name` declares the knowledge base's own name on its Ontology anchor (default: the directory's basename), so identity travels with the backup; an existing canon adopts a name through an ordinary gated round. Writes the knowledge base's own `.env` when none exists, naming its canon database `<kb>` and its working copy `<kb>-scratch`, so several knowledge bases share one DBMS without colliding (an existing `.env` is kept as-is). `--world` seeds the same knowledge base and adds the dependency settings block to `.env` — a **world** is a role a knowledge base plays by holding `[Knowledge Base Dependency]` entries (another knowledge base pinned at an edition, read or write intent), authored in its first gated round, never a type the seed marks; a `[Citizen Bookmark]` cites a citizen that lives in a dependency (its knowledge base, label, name, and the edition resolved against, with one `RESOLVES_IN` edge), and the knowledge base's own citizens point at bookmarks through their own relations. Both are kernel machinery (0.15.0); the diff gate checks their shape. Everything else grows through gated rounds. Refuses a directory that already holds a knowledge base. |
| `validate` | Parse the sources/schema against the ontology; write a consistency report to `graph/reports/validation.md`. No database needed. |
| `export` | Write a deterministic snapshot of canon to `graph/export/`. Commit it alongside any graph change. No database needed. |
| `restore` | Rebuild the database from `graph/export/` alone, then verify it re-serializes byte-identical. |
| `restore --database scratch` | Cut an authoring round: clone canon into a working database and pin the base. `delta`/`canonize` read the same name by default — set `NEO4J_SCRATCH_DATABASE` in `.env` to give a KB its own working-copy name when several share one DBMS. |
| `load` | **Bootstrap scaffolding**: validate, then wipe and reload the database from the source files. |
| `delta` | Diff `scratch` against canon's backup: a linted, itemized changeset. Its content hash is the proposal's identity. A round may also **declare moves** — `graph/proposals/current/moves.json`, `{"rename": {"Old": "[New]"}, "rehome": {"[Source]": {"[Kind]": ["citizen", …]}}}` — a rename of the world's own label or concept, or a re-homing of citizens under a kind of what they were (the migration charter's project side). The gate previews the round's landing and itemizes every derived connection that would leave (a vanished citizen takes its memberships and resolved citations with it); a citizen under a label no schema row declares refuses by name at the gate and at apply. The gate itemizes each move with its counts and refuses by name a new name already held, a kernel name (a kernel rename is a kernel ceremony), a re-home target that is not a kind of the source, or a citizen not under the source; the proposal embeds the moves so the approval covers them; `canonize --apply` performs them after the changeset (spoken in the old names — a taxonomy declaration for a renamed concept is authored under the old name and the rename re-points it) and before the stitch and re-derivation, rewrites the attribution ledger's refs, and records the inverse as the full ground diff so a relabel walks back. |
| `approve` | Record the diff-gate approval against the proposal's content hash. |
| `canonize` | Show the approved changeset and freeze status (dry run). |
| `canonize --apply` | Apply the pinned changeset to the graph, re-derive the machine layers, re-export the backup, and chain the event log. Refuses by name, before any write, when the event log's head disagrees with the backup it would build on (a lost log line, a backup the log never described) — as do `kernel-migrate --apply` and the succession gates. |
| `kernel-migrate` | Migrate this canon's embedded kernel stratum to the installed engine's kernel (dry run: report the splice and the orphan check, write nothing). Refuses when a removed kernel name would orphan project references — repoint those through an ordinary gated round first. |
| `kernel-migrate --apply` | Perform the splice as a first-class round: project stratum and ground untouched (checked, not assumed), the delta archived with its inverse, the event log chained, the backup re-exported. Mutating commands refuse on kernel skew until this runs, and so does every sweep whose verdict depends on reading canon by a kernel label (`answer-keys`, `dependencies`, `branches`, `merge`, `receipts`) — their rows would not be where the engine looks, and silence would read as held; plain reads (`docs`, `terms`) warn and proceed. |
| `rederive` | The derived-layer refresh after an engine change or a schema ceremony: re-derive canon's machine layers from the committed backup against the schema the graph carries. Dry run by default — prints what leaves and arrives (the owner's gate report); refuses on the chain-head guard, kernel skew, derivation errors, or a ground change. |
| `rederive --apply` | Perform the refresh as a first-class round: anchor stamped with the next sequence, database loaded and read back byte-identical, backup re-exported, the round's record (`rederive.json`: the engine that re-derived, and the diff) chained into the event log and archived. |
| `dependencies [--branch <name>]` | The **drift query**: every `[Knowledge Base Dependency]` on canon against what its checkout holds now (the path named by `GHOSTWHEEL_DEPENDENCY_<NAME>` in `.env`) — `held`, `behind` (the checkout differs from the pin), or `unreachable` — one line each, recorded at `graph/reports/dependencies-report.json`; exit 1 when any pin is behind or cannot be reached, so a later tool can alert on it. The diff gate reads the same backups: a dependency the round touches must be pinned at what its checkout holds and carry the name the checkout declares; a bookmark the round touches (or every bookmark of a dependency the round re-pins) must cite a citizen that exists there; a dependency the gate cannot reach refuses for the rows that touch it and is an advisory otherwise; and every round hears, as an advisory, each pin that has fallen behind — a re-pin is an ordinary one-item round. |
| `receipts` | The DB-free sweep over carried quotes (see above) — and, since kernel 0.17.0, over every **artifact location**: each `[File Location]` re-hashed against the verification the gate recorded (`verified`, `stale`, `unreadable`, `unverified`), every other kind `unverifiable by design`, never a defect. Rows ride `receipts-report.json` under `locations`. |
| `receipt <file>…` | The **floor receipt** for any artifact — whole-file fingerprint, size, and the medium its bytes declare (never its extension) — printed to paste onto the citizen the artifact is about, and recorded at `graph/reports/receipt-report.json`. A non-text artifact (an image, a PDF, audio) enters canon this way: cited by fingerprint with an observation of what it shows; the reading room refuses it plainly, receipt in hand. At the diff gate, a citizen whose name is a file under the knowledge base must carry that file's fingerprint — a stale or mistyped receipt refuses by name. |
| `corpus` | Re-check every owner-blessed floor; reds name the blessing they break. |
| `answer-keys` | Re-run every answer key on canon: each program held to its approved table (transitions, thresholds, worked-example recomputes), read from the committed backup and the tables on disk — no database needed. A drift or an uncheckable key fails by name; `graph/reports/answer-keys-report.json` lands beside the prose. |
| `terms` | List the knowledge base's own domain terms — every citizen's doc, read from the graph. |
| `docs [<record>]` | Print an engine record — design records (`ontology-doctrine`, `agentic-etl`, …) and conduct records (the skills' full procedures, e.g. `agentic-intake`); bare `docs` lists them. Every record is assembled from the manual's packaged canon. Needs no knowledge base — the records live once, as citizens, and are pulled, never vendored. |
| `generate "<name>"` | Render a citizen (e.g. a procedure) back into prose from the graph — measured against the authored text, never a replacement. |
| `export --mask judgment --out dist/runtime` | Lens-scoped export: ship a runtime graph with the design-time stratum stripped. |
| `restore --from dist/runtime --database scratch` | Inspect any export in a workspace database (never live canon; no round cut). |
| `restore --branch <name> --base schema-only` | Cut a **branch**: an independent line of truth within this KB, born from canon's schema stratum alone, with its own home, backup, and pinned base. |
| `restore --branch <name> --base clone-of-canon --by <who> [--invite <name>…]` | Cut a **pocket**: a branch born from canon's whole graph — a collaborator's own version of the knowledge base, hard-isolated from canon like every branch. Its declaration (who cut it, when, who is invited, the canon identity and sequence it forked from) lives in-band and in no file: on the branch database's identity stamp and as a bracketed `[Pocket Universe]` citizen named for the branch in the branch's own graph, so "who cut this, who may look" is a query and the backup carries the answer. The row is engine-written, never authored (the diff gate refuses it), set aside from the line's content identity, and stripped at succession. Readability is declarative here; making it physical is a later rung. |
| `merge --from <line> --into <line>` | **Merge**, the fifth job: one line takes up another's rounds while both persist (`canon` or a pocket's name on either side). Three-way at citizen grain from the pocket's fork point: the source's rounds since the fork are read from its archived proposals; a citizen or connection touched by only one side replays mechanically into the target's **fresh working copy** through the same applier every round rides; one changed on both lines is **contested** — left at the target's version and listed base / yours / theirs in `graph/reports/merge-report.json`. The merge prepares the target's ordinary round: rule contested citizens by ordinary authoring in the copy, then `delta` (each contested citizen rides as an advisory), `approve`, `canonize --apply`. `merge.json` archives with the round, and the target's log gains a merged-from annotation naming the rounds taken up — a second merge skips them, and succession's divergence advisory no longer lists rounds that already rode across. Re-cutting the copy discards a prepared merge, with a note. |
| `branch <name> [--invite <name>…] [--uninvite <name>…]` | Show a pocket's declaration, or change its invite list: the `[Pocket Universe]` row and the stamp are rewritten, the branch database reloaded and read back byte-identical; the line's identity does not move, so no chain, pin, or round is disturbed. |
| `branches` | List this KB's branches from their backups — pocket or rebuild line, cut by whom, invited, sequence, adopted — recorded at `graph/reports/branches-report.json`. No DBMS needed. |
| `delta --branch <name>` | Diff the branch's authoring copy (`<name>-scratch`) against the branch's own base. |
| `approve --branch <name>` | Record the diff-gate approval for the branch's current round. |
| `canonize --branch <name> --apply` | Apply the branch's approved changeset to the branch's own database, backup, and log — never live canon (a hard guard refuses if they collide). |
| `succession --branch <name>` | Verify a branch's fitness to become canon (dry run, writes nothing): byte-identity drills on both lines, both event-log chains, roster at full strength, whole-line lint. |
| `succession --branch <name> --apply` | The owner's adoption ceremony: archive the outgoing canon as a branch, rebuild live canon from the branch's line, re-export the backup, and chain the adoption entry naming who ruled, when, and which line was adopted. A pocket (a clone-of-canon branch) is adopted the same way — the fork point and post-fork worklist cover divergence — and its `[Pocket Universe]` declaration is stripped on the way in: canon is never a pocket. |

The export in `graph/export/` is committed: it makes graph changes reviewable in
diffs and is the baseline for the golden test (`pytest`). If a change alters the
graph, regenerate the export in the same commit.

## The conduct plugin

The engine's skills reach a consuming world as a Claude Code plugin of
**trigger stubs** — each stub carries only the skill's name and its
when-to-use description, and pulls its full instructions from the installed
engine (`python -m graph docs <name>`). Content therefore has exactly one
channel, the pip package: procedure and machinery always arrive together at
the same tag, and nothing is ever vendored or copied into a world's repo.

Install, pinned to the same tag as the pip requirement — from any terminal
(not every environment carries the `/plugin` slash command; the CLI works
everywhere):

```
claude plugin marketplace add https://github.com/SavagePencil/ghostwheel#vX.Y.Z
claude plugin install ghostwheel@ghostwheel
```

(Inside an interactive Claude Code session, `/plugin marketplace add …` and
`/plugin install …` are the same operations, where available.)

A world commits `enabledPlugins` in its `.claude/settings.json` so cloning
prompts the install. Plugin skills are namespaced (`ghostwheel:front-door`),
leaving the world's own `.claude/skills/` entirely to the world. The
plugin's version is locked to the package's by test.

## How canon changes: a round

Canon only ever changes through a **round**, and an owner appears at exactly two
moments — the **plan gate** and the **diff gate**:

1. **Cut scratch.** `restore --database scratch` clones canon into a private
   working database and pins canon's content identity as the base. Mistakes in
   scratch cost nothing. Every database the engine creates carries a
   **workspace-identity stamp** in-band — what it is (canon, working copy,
   branch, inspection), which knowledge base it belongs to, and which base
   it was cut from — and the round machinery checks it: a copy belonging to
   another knowledge base or to a round that has since closed refuses
   plainly instead of diffing into a surreal changeset. The stamps are also
   the DBMS's registry of names: every load reads the target's stamp first,
   and a database another knowledge base holds refuses by name before a
   byte is written — nothing is ever renamed. The stamp describes the
   database, never the canon it holds — every read-back path strips it
   before diffing or exporting.
2. **Author ground facts.** An author (a person or an agent holding
   scratch-only write credentials) creates the nodes and edges the source
   asserts — the second pig, his house of sticks, the `BUILT_FROM` edge between
   them — each
   carrying its **receipt** (the verbatim quote and the telling it came from).
   Authors never
   write the *derived* layers (classification edges, projections, the term index);
   the machine recomputes those, so a hand-written copy can never silently rot.
3. **Delta.** `delta` diffs scratch against the base and emits the itemized
   changeset — every node and edge to create, edit, or delete, each with its
   inverse and receipt — linted so no derived edge can be authored. Its sha256 is
   the proposal's id. Every lint verdict and ceremony item is born as a typed
   record (code, subject ref, message, remedy); the markdown report and
   `graph/reports/delta-report.json` are two renderings of the same facts, so
   downstream tools read verdicts without parsing prose. Every serialized
   citizen rides the one reference shape (`CitizenRef`: kind, label, name,
   plus the knowledge base and branch naming the line of truth it was read
   from) — identity is the (kb, label, name) composite, stable because
   renames are refused under the migration charter.
4. **Diff gate.** The owner reviews the delta: an implications narrative in plain
   prose, each claim beside its evidence, the derived consequences summarized, and
   a walkable view of just the new and changed elements. This is where the two
   tellings meet: the new telling's *the pigs escape* lands beside the standing
   *the wolf eats them*, and the keeper rules which this storybook holds true.
   `approve` records the ruling against the proposal's hash.
5. **Canonize.** `canonize --apply` refuses if there is no approval, if the base
   moved since scratch was cut, or if scratch drifted from what was approved —
   naming the divergence item by item. On success it verifies everything before
   writing anything, re-derives the machine layers, re-exports the backup, and
   appends a chained entry to the event log. The delta *is* the event; its
   recorded inverse is the undo.

## Branches: independent lines of truth

Live canon is the **default line** — the unnamed line of truth every command
works on when no branch is named, and `scratch` is its authoring copy. A
**branch** is an independent line of truth *within the same knowledge base*:
born from a declared base (`--base schema-only` cuts one from the schema stratum
alone — the whole chapter, from nothing), it lives in its own home
(`graph/branches/<name>/{export,proposals,applied.log}`) with its own backup,
its own chained event log, and its own authoring copy (`<name>-scratch`). It runs
the identical round ceremony — `delta`/`approve`/`canonize --apply`, each learning
`--branch <name>` — targeting the branch's own database, and it is
hard-isolated from live canon: a branch-scoped apply can **never** write to the
canon database (the applier refuses by name if they collide). A branch never
becomes canon by a flag; **succession is the owner's ceremony**.

That ceremony is `succession --branch <name>`. The dry run verifies every gate
— live canon still byte-matching its own backup, the branch database
byte-matching the branch's backup, both event-log chains unbroken, the branch
re-deriving clean with the roster census back at full strength, and the
ground-facts lint clean over the branch's whole line — collated,
verify-all-before-apply-any, writing nothing. `--apply` adopts capture-first:
the outgoing canon is archived as a branch (default `superseded-<sequence>`)
before anything is overwritten, the live canon database is rebuilt from the
branch's line with the version anchor stamped to canon's next sequence, the
backup re-exports from the database, and canon's chained log gains one
adoption entry naming who ruled, when, and which line was adopted (the record
pins the branch's chain tip and export identity). An adopted branch is
provenance, not a working line — further rounds on it refuse by name — and
walk-back is a second ceremony on the archived line.

In the storybook: a co-author cuts a pocket to draft the *wolf reforms*
alternate ending — real rounds on their own line, hard-isolated from canon —
and the keeper later merges the rounds worth keeping. The ending that loses
remains an archived line, never a lost file.

A *branch* is one line within one KB. It is not a *world*: a world is a role,
not a type — an ordinary KB whose own subject is the knowledge bases it
gathers (their pins, and how they relate); the step-into composition layer
above the pins is designed, not shipped (the governing taxonomy is issue #6).
In the storybook's terms: **story** is one KB and **art-assets** another,
art-assets pinning story at an edition and citing its citizens through
bookmarks; the picture book is the world over both; and a *Pocket Universe*
would be the alternate ending drafted across story *and* art, landing at one
collated gate. This slice builds the branch, the atom.

## Schema as ground: the two ontology layers

Ghostwheel's schema has two layers with different ownership and change ceremony:

- The **kernel** (`graph/metaontology.yaml`) is project-agnostic — the four
  roots and the common facet library. The membership test for anything in the
  kernel is *"would a children's storybook project need it?"* Changing the kernel
  is a **ceremony**: an explicit owner ruling, a Decision row naming it, and a
  version bump in the same change set. Never a silent side effect of intake.
  A canon's committed backup embeds the kernel stratum it was built with, so
  the ceremony's change set also migrates every canon this repo ships
  (`python -m graph kernel-migrate`; the kernel guard test enforces it), and a
  consuming knowledge base hears the skew finding — *built with kernel X, the
  installed engine carries Y* — until it runs the migration itself.
- The **project ontology** is everything a given knowledge base derived — its
  own labels, catalogs, and relationships, living on the graph as ground
  citizens. This is the owner's daily surface.

**The ontology moves to fit the user.** New domain vocabulary goes in the
project layer, always — and the project layer is grown in dialogue, not
designed up front. At intake, material that doesn't fit the schema becomes a
question only the keeper can answer — *is "Straw House" its own kind, or a
House with a Material?* — and the ruling becomes schema, in the keeper's
words. From there the ontology keeps pace with the keeper's understanding
through ordinary owner-gated **schema ceremonies**: an **alias** absorbs a
new telling's surface spelling ("the Big Bad Wolf" reads as the Wolf —
additions only); a new **label is born** with nothing yet underneath it; a
**taxonomy link** is declared as categories firm up; and when a name itself
must move, a **declared move** (rename, or re-homing citizens under a kind of
what they were) rides a round — every citizen, edge, spec, and attribution
ledger follows, the inverse recorded, the gate itemizing the consequence
before the keeper rules. A change that would silently move data underneath a
label is refused by name: it rides the migration charter instead. The kernel
holds still precisely so your layer can move — a facet is promoted into it
only by earning the many-projects test — and every surface the keeper sees
speaks the keeper's language, learned live from canon, never machinery words.

The full boundary rules — references flow one way, new vocabulary is born in the
project layer, facets are promoted to the kernel only by earning the
many-projects test — are in
`python -m graph docs ontology-doctrine`. Consuming knowledge
bases import that doctrine into their own instructions so it is standing context
for all work.

## Rules as programs (procedures)

Knowledge with process structure — a step-by-step resolution, a cascade of
effects — can live on the graph as an approved **program**: a
`(:Procedure)-[:FIRST_STEP]->(:Step)` chain. The storybook's "The Wolf at the
Door" is one — huff, puff, blow the house down; the house falls and the wolf
enters, or it stands and he tries the chimney — and so is the guild manual's
"Light the Lamp at Dusk". Programs exist for **comprehension,
not execution**: a consumer can ask "how does this work?" and get structure back,
and `python -m graph generate "<name>"` renders a program into prose (an
experiment measured against the authored text, never a replacement). Every
procedure is `KNOWN_AT` a **Completeness** level — `transcribed` (a full program
whose signature is derived from its body), `attested` (an asserted signature plus
a prose body, guarded against drift), or `cited` (name and link only). Only what
cannot be derived is authored.

## Lenses: who sees what

Visibility is a layer, not an afterthought. Nodes and edges join named
**Visibility Classes**; **Visibility Groups** (subjects of sight; individuals
are size-1 groups that nest) are granted or denied access to those classes; a
**lens** is the fold of a subject's groups compiled into what they may see. A
lens is enforced on the in-memory graph value itself, so a traversal never yields
a hidden element, edges never dangle, and derived layers recompute coherently
under the lens. In the storybook, the old telling's ending joins a class the
**young-readers** lens never folds in: a traversal from that seat simply never
yields the wolf's supper, and no edge dangles where it would have been. Lenses
materialize in exactly one place — a lens-scoped export
(the shipped runtime graph). The full design, including the branch-isolation
walkthrough, is in `python -m graph docs lenses`.

## Cypher cookbook and canned checks

- `graph/cypher/cookbook.md` — worked queries (knowledge Q&A, metamodel,
  housekeeping), runnable in Neo4j's Query tool or via an MCP client.
- `graph/cypher/checks/*.cypher` — consistency checks, run with `make check`.
  Two species: checks headed `// expect: empty` are **assertions** (rows mean a
  graph-integrity bug; `make check` exits non-zero); the rest are **finding
  reports** (rows are open questions, informational, expected to drift as the
  knowledge base evolves).

## Agentic intake and generation

Ghostwheel ships agent-facing **skills** (`.claude/skills/`) that drive the
graph-native workflows end to end. An intake is one conversation: hand the agent
a source — the modern telling, say — and say "intake this." The agent recons it, brings you the plan
(implications first, then the questions only you can answer — many of them
ontology questions: where new material doesn't fit the schema, the interview
grows the schema rather than forcing the material), authors ground
facts in scratch with receipts, self-reviews the linted delta, brings you the
changeset, and on your approval canonizes it. You appear exactly twice — the plan
gate and the diff gate. The architecture is in
`python -m graph docs agentic-etl`; the philosophy in
`python -m graph docs agentic-approach`.

## The front door

When the human in the room is the world's **designer** rather than an
engineer, a separate conduct layer — the front door (`front-door` skill)
— owns the conversation. It invokes the jobs (query, intake, generation)
underneath and renders everything the designer sees in the designer's own
language, learned live from canon: no machinery words on any surface, every
pending item rulable from itself alone, every answer cited, every item
carrying a plain-English reference number (`ref` on every verdict and
ceremony record, mapped from its code) that traces to the raw machine
record for forensics.
Its constitution is fifteen owner-ruled tenets:
`python -m graph docs front-door-tenets`.

## MCP

Ghostwheel is designed to be driven by an MCP-connected agent over two
`mcp-neo4j-cypher` connections: the **live** database (query-only by policy —
the write tool is denied) and a **scratch** connection (write-enabled, for the
agentic working copy). Launchers source `.env`, so the same credentials drive
the engine and the MCP servers — no secrets in any committed file. Live content
is applied only through the reviewed delta path (`canonize --apply`) and rebuilt
from backup by `restore`.

## Design records

The engine's design doctrine lives in the manual's canon — read any
record with `python -m graph docs <record>` (bare `docs` lists them):

- `ontology-doctrine` — the two ontology layers and the boundary rules
  between them.
- `agentic-etl` — the persistent-graph intake architecture: rounds, the
  delta lifecycle, the event log, the micro-kernel.
- `agentic-approach` — the philosophy the engine executes through: its
  Virtues, Tenets, and Method.
- `lenses` — the visibility system.
- `north-star-workflow` — the two-lane workflow and the full glossary
  (lay tier and working vocabulary).
- `engine-as-corpus` — the engine's own knowledge base: a self-world
  versioned by the engine's semver, born graph-native, with the flip
  that made this list render from canon.

## The manual

[`manual/`](manual/) is the engine's own knowledge base — the first one
born graph-native (`python -m graph init manual`; kernel schema stratum
alone, no `ontology.yaml`, no sources). The engine-as-corpus campaign
grew it through gated rounds until every design and conduct record
lived there as a citizen — and then the prose files retired (the flip):
canon is the records' only source.

`docs` renders every record from that canon: assembled from its
citizens, each section's body in rank order, a section's claims
following it — the walk that reverses the intake's byte-faithful
slicing. The canon ships inside the package as a mirror of
`manual/graph/export/` at `graph/engine_docs/canon/`, held
byte-identical by the mirror test, and a golden snapshot pins the
render within a version. A record's prose therefore changes the same
way any canon does — a gated round — and a round that moves the
manual's canon refreshes, in the same change set: the canon mirror
(`cp manual/graph/export/*.jsonl graph/engine_docs/canon/`) and the
golden snapshot (`GOLDEN_REGEN=1 pytest tests/test_record_render.py`).
The engine repo's own `.claude/skills/` are the plugin's trigger stubs,
byte for byte — its sessions pull conduct the way every world does.

## Development

```bash
make hooks      # one-time per clone: install the local test gates (pre-commit)
make validate   # consistency report (no DB needed)
make export     # deterministic snapshot -> graph/export/
make restore    # rebuild the DB from the backup, verify byte-identical
make check      # canned Cypher checks against the live DB
make corpus     # re-check every owner-blessed floor
make test       # full test suite (includes the golden-snapshot test)
```

The pre-commit gate blocks a commit unless the full test suite (including
the packaged-docs mirror test) is green; it also runs any optional local
lints when present, and skips them with a notice otherwise.

## License

Ghostwheel is licensed under the Apache License, Version 2.0 — see
[LICENSE](LICENSE). Contributions are accepted under the same terms; see
[CONTRIBUTING.md](CONTRIBUTING.md).
