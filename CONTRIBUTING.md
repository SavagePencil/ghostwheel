# Contributing to Ghostwheel

Thank you for your interest. Ghostwheel is a working engine with live
consumers that pin exact release tags, so changes move deliberately.

## The ground rules

- **Everything rides a pull request.** Nothing lands on `main` directly —
  feature branch, PR, owner review and merge. The size of a change never
  exempts it from review.
- **Tests ride with every change.** Refusals are tested from both sides:
  what is permitted lands, and what is refused refuses by name.
- **Errors follow the form** "Attempted X with context Y. Failed due to Z"
  — plus what to do instead. Collate every error before reporting; never
  stop at the first.
- **The engine stays domain-neutral.** Code, tests, docs, commit messages,
  and issues draw their examples from imaginary domains (the storybook
  corpus in this repo, or inventions of your own). The engine must stay
  meaningful to a knowledge base that has never heard of yours.
- **The kernel (`graph/metaontology.yaml`) changes only by owner ceremony**
  — explicit ruling, semver bump, and ledger line in one change set, with
  every shipped canon migrated (`python -m graph kernel-migrate`).
- **Behavior-bearing changes start with an issue** and a plan the owner
  rules before code. A plain defect with a failing test that reproduces it
  may be fixed directly. Releases are exact git tags; consumers pin them.

## Getting set up

See `README.md` → Development. `make hooks` once per clone installs the
pre-commit gate (it blocks commits on a red suite); `make test` runs the
full suite with no database needed.

## License

By contributing, you agree that your contributions are licensed under the
Apache License 2.0 (see `LICENSE`), per its Section 5.
