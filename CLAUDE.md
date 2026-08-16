# Ghostwheel — engine guidelines

Ghostwheel is a domain-agnostic knowledge-graph engine: one engine,
many knowledge bases. It must stay meaningful to a consumer that has
never heard of any other consumer.

## Source control — the hard rules

1. **NEVER run `git commit` or `git push` without explicit
   authorization from the owner in the current conversation.**
   Completing planned work, a green suite, or an approved plan does NOT
   constitute authorization. Stage changes and report what is ready;
   the owner decides when anything ships.
2. **Nothing lands on `main` directly. Every change rides a pull
   request** — feature branch, PR, the owner reviews and merges. This
   includes "small" fixes, doc edits, and skill updates; the size of a
   change never exempts it from review.
3. Releases are exact git tags (consumers pin them); tagging a release
   is a ship and needs its own word.

## Engine discipline

- **No trace of any consumer domain** — code, tests, docs, commit
  messages, and issues draw their examples from imaginary domains.
  `tools/no_trace.py` and its test are the local pre-push habit and are
  NEVER committed (the banned list is itself a trace dictionary).
- **Tests ride with every change**; refusals are tested from both
  sides (what is permitted lands, what is refused refuses by name).
- **Local test gates**: `make hooks` (one-time per clone) installs the
  tracked pre-commit hook, which blocks commits on a red suite and runs
  the trace check when the local-only tool is present.
- **Docs are the one living copy**: design records in `design/` and
  skills in `.claude/skills/` mirror into the package under
  `graph/engine_docs/` — sync the mirror in the same change set (the
  mirror test enforces it).
- **Errors follow the form** "Attempted X with context Y. Failed due
  to Z" — plus what to do instead. Collate, don't stop: gather every
  error before reporting.
- The kernel (`graph/metaontology.yaml`) changes only by owner
  ceremony: explicit ruling, semver bump, and ledger line in the same
  change set.
