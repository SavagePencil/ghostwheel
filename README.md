# Ghostwheel

**Ghostwheel** is a project-agnostic, Neo4j-backed knowledge-graph engine. You
point it at a knowledge base — a rulebook, a manual, a storybook, a catalog —
and it holds that knowledge as a queryable graph of **citizens** (facts,
definitions, procedures, rulings, quotes), grows it through reviewed changes,
and serves it back with citations. Nothing enters the graph without provenance;
nothing changes it without an owner's approval; every applied change is recorded
in a chained, reversible log.

Ghostwheel is deliberately domain-neutral. Its worked examples throughout this
repository use a small storybook knowledge base — **Gems**, **Chapters**,
**Beasts**, and **Grades** — precisely because the engine cares nothing for any
particular subject matter. A child's storybook and a legal code are the same
shape to Ghostwheel.

## What it is

At its heart Ghostwheel keeps a single body of agreed-true knowledge — **canon**
— as a Neo4j graph, and surrounds it with machinery that keeps that graph
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
- **Two ontology layers.** The engine ships a project-agnostic **kernel**
  (`graph/metaontology.yaml`): the four roots — **Concept**, **Facet**,
  **Provenance**, **Judgment** — plus a common facet library (Ordered, Exclusive,
  Stateful, …). Each knowledge base layers its own **project ontology** on top.
  References flow one way, project → kernel; the kernel must stay meaningful for a
  knowledge base that has never heard of yours. See
  `python -m graph docs ontology-doctrine`.
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

### 2. Stand up Neo4j

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
| `init [<dir>] [--name <kb>]` | Seed a new knowledge base, **born graph-native**: write a committed backup holding the kernel's schema stratum alone into `<dir>/graph/export` — no `ontology.yaml`, no sources, no database. `--name` declares the knowledge base's own name on its Ontology anchor (default: the directory's basename), so identity travels with the backup; an existing canon adopts a name through an ordinary gated round. Writes the knowledge base's own `.env` when none exists, naming its canon database `<kb>` and its working copy `<kb>-scratch`, so several knowledge bases share one DBMS without colliding (an existing `.env` is kept as-is). Everything else grows through gated rounds. Refuses a directory that already holds a knowledge base. |
| `validate` | Parse the sources/schema against the ontology; write a consistency report to `graph/reports/validation.md`. No database needed. |
| `export` | Write a deterministic snapshot of canon to `graph/export/`. Commit it alongside any graph change. No database needed. |
| `restore` | Rebuild the database from `graph/export/` alone, then verify it re-serializes byte-identical. |
| `restore --database scratch` | Cut an authoring round: clone canon into a working database and pin the base. `delta`/`canonize` read the same name by default — set `NEO4J_SCRATCH_DATABASE` in `.env` to give a KB its own working-copy name when several share one DBMS. |
| `load` | **Bootstrap scaffolding**: validate, then wipe and reload the database from the source files. |
| `delta` | Diff `scratch` against canon's backup: a linted, itemized changeset. Its content hash is the proposal's identity. |
| `approve` | Record the diff-gate approval against the proposal's content hash. |
| `canonize` | Show the approved changeset and freeze status (dry run). |
| `canonize --apply` | Apply the pinned changeset to the graph, re-derive the machine layers, re-export the backup, and chain the event log. Refuses by name, before any write, when the event log's head disagrees with the backup it would build on (a lost log line, a backup the log never described) — as do `kernel-migrate --apply` and the succession gates. |
| `kernel-migrate` | Migrate this canon's embedded kernel stratum to the installed engine's kernel (dry run: report the splice and the orphan check, write nothing). Refuses when a removed kernel name would orphan project references — repoint those through an ordinary gated round first. |
| `kernel-migrate --apply` | Perform the splice as a first-class round: project stratum and ground untouched (checked, not assumed), the delta archived with its inverse, the event log chained, the backup re-exported. Mutating commands refuse on kernel skew until this runs; read commands warn. |
| `rederive` | The derived-layer refresh after an engine change or a schema ceremony: re-derive canon's machine layers from the committed backup against the schema the graph carries. Dry run by default — prints what leaves and arrives (the owner's gate report); refuses on the chain-head guard, kernel skew, derivation errors, or a ground change. |
| `rederive --apply` | Perform the refresh as a first-class round: anchor stamped with the next sequence, database loaded and read back byte-identical, backup re-exported, the round's record (`rederive.json`: the engine that re-derived, and the diff) chained into the event log and archived. |
| `receipt <file>…` | The **floor receipt** for any artifact — whole-file fingerprint, size, and the medium its bytes declare (never its extension) — printed to paste onto the citizen the artifact is about, and recorded at `graph/reports/receipt-report.json`. A non-text artifact (an image, a PDF, audio) enters canon this way: cited by fingerprint with an observation of what it shows; the reading room refuses it plainly, receipt in hand. At the diff gate, a citizen whose name is a file under the knowledge base must carry that file's fingerprint — a stale or mistyped receipt refuses by name. |
| `corpus` | Re-check every owner-blessed floor; reds name the blessing they break. |
| `answer-keys` | Re-run every answer key on canon: each program held to its approved table (transitions, thresholds, worked-example recomputes), read from the committed backup and the tables on disk — no database needed. A drift or an uncheckable key fails by name; `graph/reports/answer-keys-report.json` lands beside the prose. |
| `terms` | List the knowledge base's own domain terms — every citizen's doc, read from the graph. |
| `docs [<record>]` | Print an engine record — design records (`ontology-doctrine`, `agentic-etl`, …) and conduct records (the skills' full procedures, e.g. `agentic-intake`); bare `docs` lists them. Every record is assembled from the manual's packaged canon. Needs no knowledge base — the records live once, as citizens, and are pulled, never vendored. |
| `generate "<name>"` | Render a citizen (e.g. a procedure) back into prose from the graph — measured against the authored text, never a replacement. |
| `export --mask judgment --out dist/runtime` | Lens-scoped export: ship a runtime graph with the design-time stratum stripped. |
| `restore --from dist/runtime --database scratch` | Inspect any export in a workspace database (never live canon; no round cut). |
| `restore --branch <name> --base schema-only` | Cut a **branch**: an independent line of truth within this KB, born from canon's schema stratum alone, with its own home, backup, and pinned base. |
| `delta --branch <name>` | Diff the branch's authoring copy (`<name>-scratch`) against the branch's own base. |
| `approve --branch <name>` | Record the diff-gate approval for the branch's current round. |
| `canonize --branch <name> --apply` | Apply the branch's approved changeset to the branch's own database, backup, and log — never live canon (a hard guard refuses if they collide). |
| `succession --branch <name>` | Verify a branch's fitness to become canon (dry run, writes nothing): byte-identity drills on both lines, both event-log chains, roster at full strength, whole-line lint. |
| `succession --branch <name> --apply` | The owner's adoption ceremony: archive the outgoing canon as a branch, rebuild live canon from the branch's line, re-export the backup, and chain the adoption entry naming who ruled, when, and which line was adopted. |

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
   asserts — a Gem, a Beast, the edge that says this Beast guards that Gem — each
   carrying its **receipt** (the verbatim quote and source pointer). Authors never
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
   a walkable view of just the new and changed elements. `approve` records the
   ruling against the proposal's hash.
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

A *branch* is one line within one KB. It is not a *world*: a world is a future
composition layer — a KB whose citizens mount other KBs — and a *Pocket
Universe* correlates branches across several KBs at one collated gate (see the
governing taxonomy in issue #6). This slice builds the branch, the atom.

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

The full boundary rules — references flow one way, new vocabulary is born in the
project layer, facets are promoted to the kernel only by earning the
many-projects test — are in
`python -m graph docs ontology-doctrine`. Consuming knowledge
bases import that doctrine into their own instructions so it is standing context
for all work.

## Rules as programs (procedures)

Knowledge with process structure — a step-by-step resolution, a cascade of
effects — can live on the graph as an approved **program**: a
`(:Procedure)-[:FIRST_STEP]->(:Step)` chain. Programs exist for **comprehension,
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
under the lens. Lenses materialize in exactly one place — a lens-scoped export
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
a source and say "intake this." The agent recons it, brings you the plan
(implications first, then the questions only you can answer), authors ground
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
the packaged-docs mirror test) is green; it also runs the local trace
check when that local-only tool is present, and skips it with a notice
otherwise.

## License

[Add your license here]
