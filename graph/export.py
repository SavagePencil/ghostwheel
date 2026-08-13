"""Deterministic text serialization of the graph — committed to git.

Same graph -> byte-identical files, so `git diff` reads as a semantic graph
diff and the test suite can use the export as a golden snapshot. Rules that
make this work (and keep it reusable for the future export-from-DB):
stable sort order, sorted JSON keys, name-based keys only — never internal
Neo4j ids.
"""

import json
from pathlib import Path

NODES_FILE = "nodes.jsonl"
EDGES_FILE = "edges.jsonl"


def node_lines(graph):
    for (label, name) in sorted(graph.nodes):
        record = {"label": label, "name": name,
                  "properties": graph.nodes[(label, name)]}
        yield json.dumps(record, sort_keys=True, ensure_ascii=False)


def edge_lines(graph):
    records = []
    for edge in graph.edges:
        records.append({
            "type": edge.type,
            "from": {"label": edge.from_label, "name": edge.from_name},
            "to": {"label": edge.to_label, "name": edge.to_name},
            "properties": dict(edge.props),
        })
    keyed = [(json.dumps(r, sort_keys=True, ensure_ascii=False), r) for r in records]
    for line, _ in sorted(keyed, key=lambda pair: (
            pair[1]["type"], pair[1]["from"]["label"], pair[1]["from"]["name"],
            pair[1]["to"]["label"], pair[1]["to"]["name"], pair[0])):
        yield line


def serialize(graph):
    """Returns {filename: content} for the export directory."""
    return {
        NODES_FILE: "\n".join(node_lines(graph)) + "\n",
        EDGES_FILE: "\n".join(edge_lines(graph)) + "\n",
    }


def write_export(graph, export_dir):
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in serialize(graph).items():
        (export_dir / filename).write_text(content, encoding="utf-8")
