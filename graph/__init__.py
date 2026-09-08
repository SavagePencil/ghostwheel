"""Ghostwheel: the project-agnostic graph engine.

The graph is primary. A knowledge base's canon lives in its database
and its committed backup; the schema is the graph's own stratum; every
change lands through owner-gated rounds. The from-sources era is
closed: a knowledge base is born graph-native (`init`) or ingested
through the front door — nothing bootstraps from files.
See `python -m graph --help`.
"""
