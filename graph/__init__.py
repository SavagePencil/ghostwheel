"""Derived-graph tooling: the project-agnostic graph engine.

A project's source files (its data tables plus overlay files) are the source
of truth; this package derives a Neo4j graph from them as directed by the
owner-governed graph/ontology.yaml. See `python -m graph --help`.
"""
