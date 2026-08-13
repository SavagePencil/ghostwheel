---
name: rebuild-graph
description: Restore, re-derive, validate, and verify the canon Neo4j graph. Use after a schema-bootstrap edit, when a database looks stale or drifted, when the golden test fails, or when a human asks to reload/refresh/reset the graph.
---

# The maintenance loop

Boundary context: @../../../design/ontology-doctrine.md

The graph is canon (the flip); `graph/export/` is its committed backup,
written FROM the database. Source files (CSVs, overlays) are bootstrap
scaffolding and may legitimately lag canon. The verbs, by situation:

1. `python -m graph restore` — rebuild the live database from the
   committed backup alone (no sources involved). DRILL PASSED means the
   database re-serializes byte-identical to the backup. This is the
   reset for a stale or drifted live database, and the routine
   reconcile step after a merge.
2. `python -m graph restore --database scratch` — cut a fresh round:
   scratch becomes a clone of canon with the base pinned. Run it before
   any scratch authoring and after any schema edit.
3. `make validate` — parse sources and schema against the ontology,
   writing `graph/reports/validation.md`. **Errors** block (broken
   ontology or file); **warnings/info** are data findings and never
   block.
4. `python -m graph rederive` — after a schema-bootstrap edit
   (`graph/ontology.yaml`): re-derives the machine layers over the
   unchanged ground facts and re-exports the backup. It refuses,
   collated, if the schema has errors or if ground facts would change —
   ground changes go through the delta path, never through derivation.
5. **Backup coherence is enforced**: any change that alters the graph
   must re-export the backup in the same change set — the golden test
   (`tests/test_golden.py`) proves the backup's derived layers agree
   with what `derive()` recomputes. A golden failure after an
   intentional change isn't an error; it's the reminder.
6. `make check` — canned consistency checks
   (`graph/cypher/checks/*.cypher`) against the live DB. Two species:
   checks headed `// expect: empty` are ASSERTIONS — rows mean an
   integrity bug and the command exits non-zero. The rest are FINDING
   REPORTS — rows are open data questions (candidate Judgments),
   informational by design. A failed assertion blocks; findings never
   do.
7. Spot-verify via MCP (counts per label, a known query from the
   cookbook).

`make test` runs the full pytest suite. Bootstrap-era verbs (`load`,
`export --from-sources`) survive only as scaffolding for building a
graph from sources before canon exists — never part of a normal round.

## Failure triage

- `Connection refused` → Desktop DBMS not running.
- `Unauthorized` → `.env` doesn't match the DBMS credentials (MCP reads
  the same `.env` via its launcher; it needs a reconnect after
  credential fixes). The live connection's user is read-only by design —
  a write refusal on live is the boundary working, not a bug.
- Validation errors naming the ontology → fix `graph/ontology.yaml` (or
  stop and talk to the owner if the fix is semantic).
- Apply refuses because the live database drifted from the backup →
  `python -m graph restore`, then retry.
- New warnings after a data edit → often the point: read them as
  findings, file issues for genuine data problems (issue-first
  convention).

## Canon changes (full flow: the agentic-intake skill)

Canon changes never happen here. Scratch authoring, `python -m graph
delta`, approval, and `python -m graph canonize --apply` (graph-native:
verify-all-before-apply-any, re-derivation, backup re-export, chained
event log) are the agentic-intake skill's territory — this skill only
keeps the databases healthy around that flow. After an apply, the
ritual: pytest → commit the export + round archive + event-log line in
one change set → next round cuts scratch fresh.
