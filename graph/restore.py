"""Restore the database from the export serialization — the backup path
(the restore drill, a D55 flip criterion).

The committed export is the graph's backup artifact; this module is its
restore. `read_export` parses the JSONL back into the same shape the
extractor produces, `load` rebuilds the database from it, and `dump_db`
reads the database back out so the drill can prove the restored state
re-serializes byte-identical to the backup it came from. No sources, no
CSVs — the whole point is that this path works after the scaffolding
retires.
"""

import json
from pathlib import Path

from . import export as export_mod
from .extract import GraphData, make_edge


def read_export(export_dir):
    """Parse graph/export/*.jsonl back into a GraphData."""
    export_dir = Path(export_dir)
    graph = GraphData()
    nodes_path = export_dir / export_mod.NODES_FILE
    edges_path = export_dir / export_mod.EDGES_FILE
    for path in (nodes_path, edges_path):
        if not path.exists():
            raise FileNotFoundError(
                f"Attempted to restore from the backup at {export_dir}. "
                f"Failed due to: {path.name} is missing. Run "
                "'python -m graph export' first, or recover the file "
                "from wherever this knowledge base keeps its history.")
    for line in nodes_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue  # a zero-row file serializes as a lone newline
        record = json.loads(line)
        graph.nodes[(record["label"], record["name"])] = record["properties"]
    for line in edges_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        graph.edges.append(make_edge(
            record["type"],
            record["from"]["label"], record["from"]["name"],
            record["to"]["label"], record["to"]["name"],
            record["properties"]))
    return graph


def dump_db(config):
    """Read the live database back into a GraphData — the drill's
    verification eye. Name-keyed like everything else; internal ids
    never leave the driver."""
    from neo4j import GraphDatabase  # deferred: only DB paths need it

    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    graph = GraphData()
    with driver:
        with driver.session(database=config["NEO4J_DATABASE"]) as session:
            for record in session.run(
                    "MATCH (n) RETURN labels(n) AS labels, "
                    "properties(n) AS props"):
                labels = record["labels"]
                if len(labels) != 1:
                    raise RuntimeError(
                        "Attempted to read the database back for "
                        "verification. Failed due to: a node carries "
                        f"{len(labels)} labels ({labels}) where the loader "
                        "only ever writes one — the database holds writes "
                        "this pipeline did not make.")
                props = dict(record["props"])
                name = props.pop("name", None)
                graph.nodes[(labels[0], name)] = props
            for record in session.run(
                    "MATCH (a)-[r]->(b) RETURN type(r) AS type, "
                    "labels(a)[0] AS from_label, a.name AS from_name, "
                    "labels(b)[0] AS to_label, b.name AS to_name, "
                    "properties(r) AS props"):
                graph.edges.append(make_edge(
                    record["type"], record["from_label"],
                    record["from_name"], record["to_label"],
                    record["to_name"], dict(record["props"])))
    from .workspace import strip as strip_workspace
    return strip_workspace(graph)


def verify_against_backup(dumped, export_dir):
    """Serialize the dumped database state and compare byte-for-byte with
    the backup files. Returns collated problems (empty = drill passed)."""
    export_dir = Path(export_dir)
    problems = []
    for filename, content in export_mod.serialize(dumped).items():
        backup = (export_dir / filename).read_text(encoding="utf-8")
        if content != backup:
            got_lines = content.splitlines()
            want_lines = backup.splitlines()
            detail = ""
            for index, (want, got) in enumerate(
                    zip(want_lines, got_lines), start=1):
                if want != got:
                    detail = (f" First difference at line {index}: "
                              f"backup has {want[:80]!r}, database "
                              f"re-serialized as {got[:80]!r}.")
                    break
            else:
                detail = (f" Line counts differ: backup {len(want_lines)}, "
                          f"database {len(got_lines)}.")
            problems.append(
                f"{filename}: the restored database does not re-serialize "
                f"to the backup.{detail}")
    return problems
