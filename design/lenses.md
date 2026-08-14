# Lenses: the visibility system

Status: designed in owner dialogue, slice 1 implemented.
The owner opened with two draft approaches and four target uses; a
deep prior-art survey (Zanzibar/SpiceDB/OpenFGA, Neo4j's own RBAC,
Datomic filtered databases, Dolt/TerminusDB/lakeFS, Postgres RLS,
Cedar/XACML/OPA, and the game-design knowledge record) tested them; the owner
supplied the Griptape Nodes fold-down system as a working reference;
the composite below is what survived. Trace tags: [owner] marks the
owner's rulings; [record] marks conclusions the prior art forced.

## The one-paragraph design (owner-accepted)

Nodes and edges join named VISIBILITY CLASSES — the only
permission-bearing unit, since instances are too many to name;
individuals are size-1 GROUPS, groups nest, and verdicts are authored
on (group × class) pairs — additive allows by default, denies legal
only against flat class sets, posture fixed per lens KIND (knowledge
lenses assume-deny, masking lenses assume-allow) rather than
switchable; a LENS is the fold-down of a subject's groups compiled
into a derived resource set — machine layer, never authored — and is
enforced as a filter at the element-access layer of the in-memory
graph value (traversal never yields a masked element, so edges,
paths, aggregates, and re-derivation stay coherent by construction),
with an EXPLAIN operation that re-evaluates unfolded to name the
blocking group, consumers declaring the lenses they REQUIRE or AFFORD
so misconfiguration refuses at build time, super-admin defined as NO
LENS APPLIED, and lens-scoped EXPORTS as the one place lenses
materialize (the shipped runtime graph); Pocket Universes stay out of
the permission model entirely — they are branches on the existing
scratch/delta/canonize machinery, with permissions owning only branch
READABILITY (creator-only by default), and canonize re-tags class
membership as work becomes canon.

## Why each piece (the dialogue, condensed)

- **Classes, not instances** [record]: the owner's Approach A
  (subject-side ACLs) and Approach B (resource-side sets) are duals;
  every surveyed system authors subject-side and ANSWERS list-shaped
  questions resource-side, compiled (Zanzibar's Leopard index, OPA
  partial evaluation, the owner's own Griptape fold-down). A authors;
  B serves; B is derived, never authored — the project's existing
  authored-vs-machine doctrine applied to permissions.
- **Deny discipline** [record]: deny × nested groups is where the
  record draws hard lines (OpenFGA refuses recursive-membership ×
  exclusion at model-build time; AuthZed: "start with no access and
  build up"). Denies here are leaf verdicts against FLAT classes only.
  The owner's tri-state No-Opinion survives — it is what makes
  "the deny didn't match" and "nothing said anything" distinguishable
  (Neo4j's documented fail-open deny is the cautionary tale).
- **Posture per lens kind, never a global switch** [record + owner]:
  no security system surveyed ships switchable assume-allow (XACML's
  configurable algebra is its least-loved feature; the field drifted
  to Cedar's fixed default-deny) — but the game-design record runs the other
  way (fog of war, roguelike map memory are assume-allow with
  carve-outs). Both are right in their kind: knowledge lenses
  assume-deny; masking lenses assume-allow.
- **Enforcement at the element-access layer** [record]: front-door
  result stripping leaks whatever was computed over hidden data
  (counts, path existence — the Postgres RLS side-channel record);
  query rewriting suits SQL, not arbitrary traversal. Datomic's
  d/filter is the fit: filter the in-memory database VALUE so
  traversal never yields a masked element. Our read path is already
  an immutable GraphData; strip_derived is the ur-lens. Coherence
  rules the approaches missed: an edge is visible only if both
  endpoints are; derived layers RE-DERIVE under the lens, never
  filter through it.
- **Explain from day one** [owner's Griptape lesson + record]: the
  fold loses which-group-blocked; decide on the fold, re-evaluate
  unfolded to explain. Cedar's fixed algebra exists for exactly this
  comprehension property.
- **Super admin = no lens** [record, unanimous]: an enforcement-layer
  bypass (BYPASSRLS, Cedar's implicit default), never a subject
  granted everything — under any-deny-wins a modeled admin loses to
  the first deny, and every new class would have to remember them.
- **Pocket Universes are branches, not permissions** [record + owner]:
  every system whose job is isolated adds-AND-removals with later
  merge is a branch system (TerminusDB does it for a knowledge graph;
  tombstones appear in the record only as internal versioning
  implementation, never as the user-facing permission model — masking
  a removal is intrinsically a deny and imports every deny warning
  into steady state). The scratch round with base pinning and
  delta/canonize IS the branch pattern. Permissions own one small
  thing: who may see that a branch exists and read it (the lakeFS
  stance over Dolt's open reads; creator-only by default). Invitation
  is one authored verdict: (their group × the branch) → allow, read
  or write grade; an invited COLLABORATOR gets no lens, an invited
  PLAYER gets a subject's knowledge lens — branch selects the
  reality, the lens filters within it.
- **The storage contract** [owner concern, ruled]: branch = pinned
  base + delta IS the contract (base.json/delta.json already are it);
  clone, filesystem copy-on-write, and delta-overlay-over-a-shared-
  base are interchangeable implementations. Today's full clone is a
  cache, kept while cheap; the overlay (branches sharing one loaded
  immutable base value, O(delta) each) is the path when canon grows.
- **Neo4j's own RBAC: whole-database gates only** [owner + record]:
  a query-only reader on live canon; per-branch database access for pockets.
  Never label/property/traversal privileges, never DENY rules — the
  record documents static per-DB-user roles, deny-wins composition
  that cannot stack into views, fail-open property denies, and
  planner-invisible performance cliffs. The boundary sentence: Neo4j
  enforces which databases a connection may read or write; the engine
  enforces everything about what is visible within one.
- **Exports are the one materialization** [record]: the shipped
  runtime graph is a lens-scoped export (Unreal's cook: strip
  design-time data at build time, flags on the data). Live lenses
  compute fresh from canon — cached lens views reintroduce stale
  revocation (the New Enemy problem in miniature). The canonical
  backup at graph/export/ is ALWAYS lens-free.

## The keeper walkthrough (the design's acceptance story) [owner]

A keeper named Bramble must know where the hidden Emberstone lies —
but only while the owner works in one workspace branch. Order of
events: cut the branch (readability creator-only — the branch IS the
isolation); author the Emberstone fact and its Emberstone Lore class
membership in the branch; author the grant (Bramble × Emberstone Lore)
→ allow in the branch — the grant is itself branch content, so
"temporary permission" needs no mechanism at all; ask "what does
Bramble know?" inside the branch (the branch selects the reality,
Bramble's folded lens filters within it — she knows Universal + Keeper
knowledge + the Emberstone; other keepers do not); exit the branch
(view returns to canon, where there is nothing to know); land it via
the ordinary delta round (fact, class, grant become canon rows) or
discard the branch clean.

## Slice 1 (built) and what waits

Built: graph/lens.py (declarations, fold, compile, apply, explain,
require — pure logic over the in-memory graph value), the lens-scoped
export, the keeper walkthrough as an executable test, floors for the
coherence and flat-deny rules. Declarations rode a YAML surface until
the residence ceremony landed them as citizens; the file surface
retired in the YAML-cleansing arc — the graph is the only
declaration surface, read by declarations_from_graph.

Built in slice 2 (session activation): compile_lens takes the hats
worn this session — subject as one group or an iterable of groups
(each closed upward through its own containers), and `without=` to
subtract named groups after the fold. "Exit the branch" is a
lens subtraction, no membership edit; an empty active set is honest
assume-deny, never an error.

**The residence ceremony was RULED and landed** (owner: "go for it",
after the Griptape Nodes expressibility check — the
model expresses the owner's node-library permissions system with zero
kernel additions; hierarchy as overlapping memberships, posture as
class-kind choice). At the kernel ceremony: **Visibility Group**
and **Visibility Class** join as concepts — named Visibility Group,
not Group, because boundary rule 6 caught the bare name colliding with
a knowledge base's own domain concept: the kernel never claims a word
a project's domain may need. The edge vocabulary
(MEMBER_OF, IN_CLASS, ALLOWED, DENIED flat-only, INCLUDES, MANAGES) is
admitted by the ceremony's Decision row; specs land with first
consumers. The project ontology binds both labels as
implicit delta-born citizens, the Requirement pattern. The engine
grew declarations_from_graph (one lint, two surfaces), the
fold-touching self-visibility in compile_lens (the A/B/C case: you
see your hats and the doors they open; the roster hides by edge
coherence), and the uniform refusal surface (REDACTED_REFUSAL — one
shared string; candid explain is the curator surface). The residence
round (the judgment masking class as the first Visibility Class
citizen + the ruling Decision rows) rides the ordinary
delta/approve/canonize path.

The meta-rule is fully ruled (all four questions + the deferred
developer tier); belief divergence is parked on the owner's word;
MANAGES enforcement is held for multi-user.

The original proposal, kept for the record:

  Kernel (metaontology.yaml), two concepts by the Procedure precedent:

      Group:
        instance_of: Concept
        doc: A subject of visibility. Individuals are size-1 groups;
          groups nest. The fold of a subject's groups is what a lens
          compiles from.
      Visibility Class:
        instance_of: Concept
        doc: A named set of graph elements that visibility verdicts
          speak about — the only permission-bearing unit. kind is
          knowledge (assume-deny) or masking (assume-allow).

  Ground edge vocabulary (authored, never derived): MEMBER_OF
  (Group → Group, the nesting), IN_CLASS (any element → Visibility
  Class, the membership), ALLOWED / DENIED (Group → Visibility
  Class, the verdicts — denies flat-only, enforced by the lint),
  INCLUDES (Visibility Class → Visibility Class, knowledge
  grant-inheritance). Class kind and the label/type selectors ride as
  properties on the Visibility Class citizen. After the ceremony:
  lenses.yaml's content lands as citizens via an ordinary canon
  round, lens.py grows a from-graph declarations reader beside the
  YAML one, and the intake seal becomes physically enforceable.
- **Belief divergence** [deliberately open]: a lens over canon cannot
  represent a subject believing something now false (the roguelike
  map-memory / Dwarf Fortress rumor record: knowledge is a stale
  copy, not a filter). If wanted, that is per-agent overlay data — a
  different mechanism, deferred by name.
- **The meta-rule**: who may see the visibility declarations
  themselves (who-can-see-who-can-see-what) — one rule, wanted before
  multi-user.
- Physical seal enforcement for intake's sealed-reading phase rides
  this system once declarations live on the graph.
