"""Ghostwheel: the project-agnostic graph engine.

The graph is primary. A knowledge base's canon lives in its database
and its committed backup; the schema is the graph's own stratum; every
change lands through owner-gated rounds. Source files, where a corpus
keeps them, are bootstrap provenance for the from-sources path only.
See `python -m graph --help`.
"""
