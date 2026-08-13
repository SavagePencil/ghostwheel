# Ghostwheel engine workflow. See README "Quickstart" for setup.
PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest

.PHONY: validate export restore check corpus test

validate:        ## consistency report (no DB needed)
	$(PYTHON) -m graph validate

export:          ## deterministic snapshot -> graph/export/ (no DB needed)
	$(PYTHON) -m graph export

restore:         ## rebuild the database from graph/export/ alone, then verify byte-identical re-serialization
	$(PYTHON) -m graph restore

check:           ## run canned Cypher checks against the live DB
	$(PYTHON) -m graph check

corpus:          ## re-check every owner-blessed floor
	$(PYTHON) -m graph corpus

test:            ## full test suite (includes the golden-snapshot test)
	$(PYTEST) -q
