# Delta report — scratch vs source-derived base

**Summary:** 6 nodes added · 2 changed · 2 removed · 9 edges added · 3 changed · 4 removed · 2 stitched

## Ground-facts lint

The items below cannot become canon as written — each says why, and what to do instead. Nothing canonizes until they are resolved.

- ⚠ Attempted to birth 'Rune' as a new Archetype LABEL, but the base already holds 1 ground row under that label (Ancient Mark). Failed due to: this schema change is outside the ceremony's classes (new declared concepts, label births, doc edits, added aliases, render-mapping edits, source unregistration, removal of unreferenced rows, and the declared moves — a rename of the world's own label or a re-homing of citizens under a kind, filed in moves.json) — any other change to an EXISTING label or spec moves data underneath it and rides the migration charter. Propose the change to the owner at the plan gate instead.
- ⚠ Attempted to author 'Myth' as a new Archetype concept without declaring it. Failed due to: a ceremony concept arrives WITH its DECLARED_IN edge (and usually an INSTANCE_OF into its parent concept) in the same round — an undeclared schema row would be invisible to the schema readers. Add the declaration in scratch, or delete the node.
- ⚠ a Object node was created without a name — every citizen needs one. Give it a name property or delete it from scratch.
- ⚠ 'Ghost Step' can't be created as a [Step] — nodes of that kind are built automatically by the system, never by hand (machine label). If you meant to propose a new concept or step, say so in the plan and the owner will place it. To undo: delete the node from scratch, or reset scratch entirely (python -m graph load --database scratch).
- ⚠ Attempted to remove the connection (Tool)-[:INSTANCE_OF]->(Concept). Failed due to: INSTANCE_OF links are part of the graph's own schema, and this schema change is outside the ceremony's classes (new declared concepts, label births, doc edits, added aliases, render-mapping edits, source unregistration, removal of unreferenced rows, and the declared moves — a rename of the world's own label or a re-homing of citizens under a kind, filed in moves.json) — any other change to an EXISTING label or spec moves data underneath it and rides the migration charter. Propose the change to the owner at the plan gate instead. To undo: reset scratch entirely (python -m graph load --database scratch).
- ⚠ Attempted to author membership (Object)-[:DECLARED_MEMBER_OF]->(Tool). Failed due to: the edge runs FROM an Archetype, which is the tower/roster shape, not an authored membership — a declared membership is written FROM a citizen. To undo: point the edge from the citizen, or MATCH it in scratch and DELETE it.
- ⚠ Attempted to author membership (Golden Key)-[:DECLARED_MEMBER_OF]->(Ordered). Failed due to: 'Ordered' is not a Concept-rooted Archetype in the base or this round — authored membership classifies a citizen against Concept-rooted subjects only: a plain concept, or a label row that is also a concept (a home with a catalog can be a subject too); never a Facet, a Provenance-rooted row, or a missing node — and it never re-homes the citizen. To undo: point the edge at a Concept-rooted Archetype, or DELETE it from scratch.
- ⚠ Attempted to author membership (Silver Bell)-[:DECLARED_MEMBER_OF]->(Tool). Failed due to: the edge carries no `basis` rationale — a declared membership is a hand assertion with no source table behind it, so its reason is the audit record and is required. To undo: add a `basis` property naming why the citizen belongs, or DELETE the edge from scratch.
- ⚠ Attempted to author the connection (Treasure)-[:INSTANCE_OF]->(Tool). Failed due to: INSTANCE_OF links are part of the graph's own schema, and this schema change is outside the ceremony's classes (new declared concepts, label births, doc edits, added aliases, render-mapping edits, source unregistration, removal of unreferenced rows, and the declared moves — a rename of the world's own label or a re-homing of citizens under a kind, filed in moves.json) — any other change to an EXISTING label or spec moves data underneath it and rides the migration charter. Propose the change to the owner at the plan gate instead. To undo: MATCH the relationship in scratch and DELETE it, or reset scratch.
- ⚠ the connection (Silver Bell) → (Tool) can't be added by hand — INSTANCE_OF links are computed automatically from the facts, so a manual one would go stale the moment the facts change (derived type INSTANCE_OF). If the intent is 'these two should be related', that's an owner question — raise it at the plan gate. To undo: MATCH the relationship in scratch and DELETE it, or reset scratch.
- ⚠ Attempted to edit the membership (Plain Pebble)-[:DECLARED_MEMBER_OF]->(Tool). Failed due to: the edit leaves it with no `basis` rationale — a declared membership's reason is the audit record and is required. To undo: restore or rewrite the `basis` property in scratch.
- ⚠ the connection (Golden Key) → (Object) can't be modified by hand — INSTANCE_OF links are computed automatically from the facts (derived type INSTANCE_OF). If the underlying fact is wrong, change the fact; the link follows. To undo: restore the relationship's properties in scratch, or reset scratch.
- ⚠ the stitch connection (Golden Key)-[:KEPT_WITH]->(Plain Pebble) doesn't need the stitch — both ends already exist in scratch. Author it there like any other ground fact and it will ride the main changeset.

## Schema changes — the ceremony

The rows below change the graph's OWN SCHEMA. They are within the ceremony's permitted classes (new declared concepts, label births, doc edits, added aliases, render-mapping edits, source unregistration, taxonomy declarations, unreferenced removals, declared moves — renames and re-homings); approving this round is the ceremony ruling that makes them schema.

- ⚑ NEW CONCEPT 'Lore' — declared in Chronicle, an instance of Treasure; doc: "Old tales carried by wandering scribes"
- ⚑ DOC EDIT on 'Tool' — doc: (none) → "A thing that does work"
- ⚑ REMOVED CONCEPT 'Relic' — unreferenced in the base (no members, no anchors); its declaration goes with it

## Nodes added

- (Archetype) **Lore** — doc: 'Old tales carried by wandering scribes'
- (Archetype) **Myth**
- (Archetype) **Rune** — spec_json: '{}'
- (Object) **None**
- (Object) **Silver Bell** — from_text: 'rings at dusk'
- ([Step]) **Ghost Step**

## Nodes changed (before → after)

- (Archetype) **Tool** — doc: None → 'A thing that does work'
- (Object) **Plain Pebble** — weight: None → 'light'

## Nodes removed (with what they held)

- (Archetype) **Relic**
- (Object) **Old Rope**

## Edges added

- (Lore)-[:DECLARED_IN]->(Chronicle)
- (Object)-[:DECLARED_MEMBER_OF {basis: 'rosters are not memberships'}]->(Tool)
- (Golden Key)-[:DECLARED_MEMBER_OF {basis: 'sorted on the shelf'}]->(Ordered)
- (Golden Key)-[:DECLARED_MEMBER_OF {basis: 'opens the locked door'}]->(Tool)
- (Silver Bell)-[:DECLARED_MEMBER_OF]->(Tool)
- (Lore)-[:INSTANCE_OF]->(Treasure)
- (Treasure)-[:INSTANCE_OF]->(Tool)
- (Silver Bell)-[:INSTANCE_OF]->(Tool)
- (Silver Bell)-[:KEPT_WITH {why: 'the bell hangs from the key'}]->(Golden Key)

## Edges changed (before → after)

- (Plain Pebble)-[:DECLARED_MEMBER_OF]->(Tool) — basis: 'kept by the gatekeeper' → ''
- (Golden Key)-[:INSTANCE_OF]->(Object) — confidence: None → 'high'
- (Golden Key)-[:KEPT_WITH]->(Plain Pebble) — trigger: 'dawn' → 'dusk'

## Edges removed

- (Relic)-[:DECLARED_IN]->(Ontology)
- (Golden Key)-[:GUARDS]->(Plain Pebble)
- (Relic)-[:INSTANCE_OF]->(Concept)
- (Tool)-[:INSTANCE_OF]->(Concept)

## Stitch — lands after re-derivation

These connections point at citizens born by this round's schema edit, so they cannot exist in scratch yet. They ride this same approval and land in the same apply — verified in memory after re-derivation births their endpoints, before anything is written.

- (Silver Bell)-[:KEPT_WITH {why: 'the saga names the bell'}]->(First Saga)
- (Golden Key)-[:KEPT_WITH]->(Plain Pebble)

## Advisories — the branch's roster, for the record

These registered program files have no citizen on this branch yet. A branch mid-rebuild is incomplete by design, so these do not block its rounds — the roster check returns to full strength when the branch stands for succession.

- the registry names 'rituals/summoning.md' but no citizen on this branch carries it
- the registry names 'rituals/warding.md' but no citizen on this branch carries it
