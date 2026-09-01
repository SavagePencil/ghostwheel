# Two Ontology Layers

<!-- Engine-owned doctrine. Travels with the engine (like metaontology.yaml).
     Consuming knowledge bases import this into their agent instructions so it is
     standing context for ALL work, not an on-demand procedure. -->

The graph schema has two layers with different ownership and change ceremony:

- **Engine metaontology** (`graph/metaontology.yaml`): the project-agnostic
  kernel — the `Archetype` label, `INSTANCE_OF`, the four roots (**Concept**,
  **Facet**, **Provenance**, **Judgment**), and the common facet library
  (Ordered, Exclusive, Stateful, ...). The membership test: *would a kid's
  storybook project need it?* Changes here are cross-project design decisions
  of the highest weight — never made casually, never as a silent side effect
  of intake, always via explicit design dialogue with the owner. That
  dialogue may happen at a round's gate: a kernel ceremony may be declared
  and ruled mid-round when the round's evidence demands it, including a
  conditionally pre-authorized enabling engine change ("only on a real
  refusal, with its own tests"). What makes it a ceremony is the explicit
  owner ruling, a Decision row naming it, and the semver bump + ledger line
  riding the same change set — the dialogue and the record, not the
  calendar.

- **Project ontology** (the graph's own schema stratum): everything
  THIS knowledge base derived — its domain concepts, labels, catalogs,
  relationships, project-specific facets. Since the schema inversion the
  schema lives ON THE GRAPH as ground citizens — the Archetype
  stratum, read by `ontology_from_graph` — and this is the owner's
  daily surface, following the ontology-has-one-owner rules.
  `graph/ontology.yaml` and `data/overlays/` are its bootstrap
  provenance (the from-sources path only). It versions from the
  event-log sequence, auto-stamped on the graph's Ontology anchor at
  apply, with an optional free-text `tag` beside it — semver stays
  with the kernel, whose bumps are ceremony (owner ruling).
  Schema changes ride the SCHEMA CEREMONY: an ordinary owner-gated round may add a new declared concept, birth a new label (a spec-carrying row with nothing yet underneath it), edit a schema row's doc text, add an alias to a label's spec (a new surface spelling reading as an existing citizen — additions only), or remove an unreferenced schema row — itemized under the delta report's marked ceremony section, whose approval IS the ceremony ruling. Changes to an existing label or spec move data underneath them and stay refused: they ride the migration charter.

## Boundary rules

1. **References flow one way**: project → kernel, never kernel → project.
   The kernel must stay meaningful for a knowledge base that has never
   heard of this one.
2. **New domain vocabulary** (categories, labels, relationships) goes in the
   project layer. Always.
3. **New facets are born project-specific** (the project `facets:` section is
   the escape hatch). **Promotion to the engine library is a deliberate,
   separate act** requiring the many-projects test — a facet earns its way in
   by being wanted elsewhere, not by being neat.
4. **New roots are the most ceremonial change in the system.** Validation
   permits them (at info level) precisely so the ceremony is a design
   conversation, not a fight with tooling.
5. **Intake grows the project layer and only ever *proposes* against the
   engine layer.** When intake surfaces something kernel-shaped, that is a
   Judgment moment: raise it as a Question for design dialogue — do not
   resolve it inline.
6. Kernel names cannot be redeclared by projects (enforced by validation).
7. **Prefer graph citizens over prose**: when encoding project knowledge
   and a citizen exists (or should exist) to carry it, put it on the graph
   — doc-bearing archetypes, Judgment rows, glossary entries — not in
   loose files. Prose homes drift; citizens are queryable, and agents are
   taught to read menus from the graph.

## The four roots, one line each

| Root | Holds | Epistemic status |
|---|---|---|
| Concept | subject matter | asserted domain truth |
| Facet | structural vocabulary (how value-spaces behave) | machinery |
| Provenance | artifacts, sources, doc sections | objective |
| Judgment | Questions, Decisions, Answers, Requirements, Opinions | subjective / adjudicated |

Supersession of Judgments is expected, not exceptional — decisions flip as
evidence arrives. Objective/Subjective are deliberately NOT modeled; they can
be added later as parents of Provenance/Judgment if the distinction becomes
load-bearing.
