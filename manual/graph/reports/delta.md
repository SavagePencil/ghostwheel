# Delta report — scratch vs source-derived base

**Summary:** 1 nodes added · 0 changed · 0 removed · 0 edges added · 0 changed · 0 removed

## Ground-facts lint

Clean — every addition is a ground fact.

## Nodes added

- (Decision) **Dependencies and bookmarks enter the kernel (0.15.0)** — decided_by: 'James Clarendon', decided_on: '2026-09-04', doc: "Kernel ceremony ruling: a knowledge base gains the vocabulary to pin another knowledge base and to cite a citizen that lives there. [Dependency] pins another knowledge base to an edition (its committed backup's identity hash and event-log sequence) with a read or write intent; [Bookmark] names a citizen in a dependency (its knowledge base, label, name, and the edition it was resolved against) with exactly one RESOLVES_IN edge to that dependency. Both are Provenance-rooted machinery, bracketed because a designer never authors either as subject matter — and named dependency, not member, because a pinned edition of another knowledge base is precisely a dependency, while membership is the kernel's word for a citizen belonging to a concept. Where a dependency lives on disk is settings, never canon, and a knowledge base's own citizens point at a bookmark through their own relation vocabulary. Any knowledge base holding dependency entries plays the world role — a role, never a type; init --world seeds the same knowledge base plus the dependency settings block, and the first gated round pins the dependencies. The delta gate checks their shape; resolution against the dependency's backup, the behind-pin advisory, and the drift query are the next rung. Additive; kernel 0.14.0 -> 0.15.0, delivered to existing knowledge bases by kernel-migrate."
