# The engine as corpus

Status: ruled at the stage-3 plan gate (owner, 2026-09-01) and in the
gate dialogues that followed; the campaign is underway in this repo.
The engine's design records and conduct procedures become citizens in
an engine-owned canon, and `python -m graph docs <record>` learns to
render from that canon. The stub model makes the swap invisible: the
plugin's trigger stubs and every consumer of engine knowledge already
go through `docs`, so what changes is what stands behind that command,
and nothing downstream notices.

## A self-world, riding the engine's own version

The engine's knowledge base lives in this repo (`manual/`) and is a
world like any the engine serves — its own canon, its own project
ontology grown through gated rounds, its own chained event log — with
one deliberate difference: **it has no version of its own.** Its
rounds land on this repo's main; a release tag freezes code and canon
together; the packaged export ships inside the wheel the way the
metaontology seed does. A consuming world that pins engine X therefore
gets the conduct and doctrine of X by construction — one pin, no
second version to resolve, no compatibility matrix. Conduct is
documentation of the machinery it operates; desynchronizing them is
the failure mode, not the flexibility.

It is ruled a *self*-world: it moves atomically with engine changes in
the same change set, so it does not count toward the
multiple-consuming-worlds thresholds elsewhere in the doctrine —
though it does, over time, furnish the second-project evidence that
kernel promotions await.

## Born graph-native

The engine's corpus is the first knowledge base **born graph-native**:
`python -m graph init` seeds a committed backup holding the kernel's
schema stratum alone — no `ontology.yaml`, no sources, no derive path,
the same seed shape a schema-only branch cut is born from. Everything
else grows through ordinary gated rounds. The project layer starts
empty, so its first growth is **label births** riding the schema
ceremony ([ontology-doctrine.md](ontology-doctrine.md)); prose
citizens carry their bodies on the graph and their containment
re-derives from declared linking props — the section machinery with no
source file anywhere.

A corpus born this way carries zero YAML and never acquires any: the
bootstrap files other corpora keep as provenance simply never existed
for it.

## What the citizens are

- **Conduct records** (the skills' full procedures) become kernel
  **Procedure** citizens, Completeness ruled per record at its intake
  gate — expected mostly Attested: an asserted signature over a prose
  body that lives on the graph as that record's own section citizens,
  `SPECIFIED_IN` pointing at citizens, not files. A procedure defined
  in an interactive session is legitimate provenance; nothing demands
  a file path.
- **Design records** become section-level citizens — the record an
  ordered container, each section carrying its verbatim body — with
  claim-level promotion only where the source is already enumerated
  (numbered rules, tenet lists, glossaries). Cross-references that
  name sections and invariants become edges.

This is the scoped side of the reading-room thinning
([agentic-etl.md](agentic-etl.md)): here the prose IS the knowledge,
so sections are citizens by design — once the prose lives on the
graph, there is no separate source left to anchor to.

**Machinery marking extends to the project layer.** The customer of
the whole system is the world's designer, and to them this corpus is
entirely under the hood — agents are staff, not customers. Its labels
therefore wear the machinery brackets (the kernel's marking
convention, applied by owner ruling at the layer's first gate); ground
citizens keep their natural names, and the standing
`NOT STARTS WITH '['` filter keeps every such catalog off
customer-facing surfaces by construction.

## The render contract and the flip

`docs` output is **deterministic within a version** — same canon, same
bytes, held by a golden render snapshot — and the stub contract
narrows to: names resolve, descriptions match, output complete. It was
never byte-frozen across versions; records evolve through rounds like
any canon. **Byte-parity with the prose files is the flip criterion,
not a permanent contract**: each record's canon must reassemble to the
exact bytes of its file; when all records pass, `docs` serves canon,
the files and their packaged mirrors retire, and the parity tests
retire with them. Until that flip, the files remain the source of
truth and every step is additive — reverting is simply not flipping.

## What worlds do with the conduct

The engine ships the trunk: tenets, procedures, doctrine — versioned
by the pin. Each world is expected to **tailor the conduct to its own
experience**: the door's voice is learned live from that world's canon
([front-door-tenets.md](front-door-tenets.md)), and a world keeps its
own local skills alongside the engine's. Two worlds at different pins
run different conduct on purpose — skew is a chosen consequence of
pinning, and the pin is the sync mechanism.

## The kernel stays honest

The corpus's canon embeds the kernel's schema stratum, and this repo
ships both — so a guard test holds the embedded kernel byte-equal to
the packaged metaontology: a kernel ceremony physically cannot merge
without migrating the shipped canon in the same change set. The
general migration operation (kernel changes reaching consuming worlds'
canons) is parked in this repo's tracker, awaiting the first kernel
ceremony after a graph-native seed exists — the guard is its forcing
function.
