"""Wipe-and-reload the derived graph into Neo4j.

Only module that imports the neo4j driver, so validate/export stay
database-free. Connection settings come from environment variables, falling
back to the .env file in the repo root (see .env.example). The load is a full
rebuild: everything in the target database is deleted first — safe because
the graph is entirely derived from the sources in git.
"""

import os
from pathlib import Path
from typing import LiteralString, cast

DEFAULTS = {
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "",
    "NEO4J_DATABASE": "neo4j",
    # Empty = the engine-wide default working-copy name ("scratch").
    # A KB sharing a DBMS with others names its own here.
    "NEO4J_SCRATCH_DATABASE": "",
}

BATCH_SIZE = 500


def read_config(base_dir):
    """Merge .env file values with the environment (environment wins)."""
    config = dict(DEFAULTS)
    env_file = Path(base_dir) / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            config[key.strip()] = value.strip()
    for key in DEFAULTS:
        if os.environ.get(key):
            config[key] = os.environ[key]
    return config


def batched(items, size=BATCH_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def vouched(query):
    """A dynamically built Cypher string, vouched for: every dynamic
    piece is a label or relationship-type name from the graph's own
    validated data, never outside input — which is what the driver's
    LiteralString guard exists to ask about."""
    return cast(LiteralString, query)


def ensure_database(driver, database):
    """Create the target database if the DBMS supports it (Desktop DBMSes
    are Enterprise, so CREATE DATABASE works); fall back to a clear message
    when it does not. No-op for the default database."""
    if database == "neo4j":
        return
    try:
        with driver.session(database="system") as session:
            session.run(f"CREATE DATABASE `{database}` IF NOT EXISTS")
            session.run(f"START DATABASE `{database}`")
    except Exception as exc:
        raise RuntimeError(
            f"Attempted to create the '{database}' database in the DBMS. "
            f"Failed due to: {exc}. Create it manually in Neo4j Desktop "
            "and retry."
        ) from exc


def load(graph, config):
    """Wipe the database and load nodes then edges. Returns count summary."""
    from neo4j import GraphDatabase  # deferred: only load needs the driver

    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    database = config["NEO4J_DATABASE"]

    node_rows = {}
    for (label, name), props in graph.nodes.items():
        node_rows.setdefault(label, []).append({"name": name, "props": props})

    edge_rows = {}
    for edge in sorted(set(graph.edges), key=lambda e: (
            e.type, e.from_label, e.from_name, e.to_label, e.to_name, e.props)):
        key = (edge.type, edge.from_label, edge.to_label)
        edge_rows.setdefault(key, []).append({
            "from": edge.from_name, "to": edge.to_name,
            "props": dict(edge.props)})

    with driver:
        driver.verify_connectivity()
        ensure_database(driver, database)
        with driver.session(database=database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            for label in sorted(node_rows):  # actual labels incl. Archetype
                session.run(vouched(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{label}`) "
                    "REQUIRE n.name IS UNIQUE"))
            for label, rows in node_rows.items():
                for batch in batched(rows):
                    session.run(vouched(
                        f"UNWIND $rows AS row CREATE (n:`{label}` "
                        "{name: row.name}) SET n += row.props"),
                        rows=batch)
            for (rel_type, from_label, to_label), rows in edge_rows.items():
                for batch in batched(rows):
                    session.run(vouched(
                        "UNWIND $rows AS row "
                        f"MATCH (a:`{from_label}` {{name: row.from}}) "
                        f"MATCH (b:`{to_label}` {{name: row.to}}) "
                        f"CREATE (a)-[r:`{rel_type}`]->(b) "
                        "SET r += row.props"),
                        rows=batch)
            counts = session.run(
                "MATCH (n) WITH count(n) AS nodes "
                "MATCH ()-[r]->() RETURN nodes, count(r) AS edges").single()

    node_summary = {label: len(rows) for label, rows in sorted(node_rows.items())}
    edge_summary = {rel_type: sum(len(r) for (t, _, _), r in edge_rows.items()
                                  if t == rel_type)
                    for rel_type in sorted({t for t, _, _ in edge_rows})}
    return {
        "loaded_nodes": counts["nodes"] if counts else 0,
        "loaded_edges": counts["edges"] if counts else 0,
        "nodes_by_label": node_summary,
        "edges_by_type": edge_summary,
    }
