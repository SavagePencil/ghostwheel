---
name: graph-query
description: Answer questions about the corpus's values, rules, and structure by querying the Neo4j graph via MCP instead of grepping source files. Use for "what does X do", "which members of a catalog...", "what kind of thing is...", consistency lookups, and metamodel questions.
---

# Querying the rules graph

Boundary context: `python -m graph docs ontology-doctrine`

## Posture

- **Graph first, files second.** The graph is canon
  (the flip): it holds the normalized names, values, and the metamodel —
  one query beats a grep across dozens of source files, and the source
  files may legitimately lag canon. Fall back to docs only for prose
  the graph doesn't hold yet, or when the graph is unavailable.
- **Read-only, always.** Use `mcp__neo4j__read_neo4j_cypher`. The live
  connection rides a read-only database user (writing is physically
  impossible) and the write tool is denied by settings; canon changes
  flow only through the delta path (agentic-intake skill).
- Worked, verified queries live in `graph/cypher/cookbook.md` — start there
  and adapt.

## Idioms that matter (each learned the hard way)

- **Ordered collect**: `collect(x ORDER BY ...)` is invalid; sort before
  aggregating: `WITH c ORDER BY c.rank RETURN collect(c.name)`.
- **Post-aggregation ORDER BY** can't see pre-aggregation variables; project
  them into the `WITH` first.
- **Placeholders skew counts.** Real entities: `WHERE n.placeholder IS NULL`.
  Placeholder nodes are queryable dangling references — often the answer IS
  the placeholder (that's a data finding, cite the issue if one exists).
- **Ladders**: compare with `rank` (`a.rank > b.rank`), traverse with
  `PRECEDES`/`FOLLOWS` (single hop = adjacent tier).
- **"What kind of thing is X"**: full chain via
  `MATCH p=(v {name:$x})-[:INSTANCE_OF*]->(top) WHERE NOT (top)-[:INSTANCE_OF]->() RETURN [n IN nodes(p)|n.name]`.
- **The facet menu is data**: instances of the `Facet` archetype, with `doc`
  properties explaining each.
- **Matrix-edge semantics live in the cookbook**, beside the worked
  query — which party's number a matrix cell holds is a per-edge fact;
  check there before interpreting a modifier.

## When answering

Lead with the answer, cite counts precisely (say when placeholders are
included/excluded), and if a query surfaces something inconsistent, report it
as a finding — don't fix data unasked.
