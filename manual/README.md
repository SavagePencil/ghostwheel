# The manual — the engine's own knowledge base

This directory is a knowledge base like any other the engine serves —
except its subject is the engine itself. It was seeded with
`python -m graph init manual` (the first knowledge base born
graph-native: no `ontology.yaml`, no sources), and it grows the same
way every knowledge base grows: scratch authoring, `delta`, the
owner's ruling at the diff gate, `canonize --apply`.

The engine-as-corpus campaign fills it: the engine's design records and
conduct procedures become citizens here, and `python -m graph docs`
learns to render from this canon. Until that campaign's flip, the
packaged markdown under `graph/engine_docs/` remains what `docs`
serves; everything in this directory is additive.

Round databases (canon and scratch) are configured by a local `.env`
in this directory, which never commits — see the engine README for the
config keys. `graph/export/` here is this knowledge base's committed
backup; `graph/proposals/` will hold its rounds and chained event log.
