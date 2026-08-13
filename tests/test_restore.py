"""The restore path: the export is the backup, and read_export must
invert write_export exactly. The database half of the drill runs live;
everything provable without a driver is proved here."""

import pytest

from graph.export import serialize, write_export
from graph.extract import GraphData, make_edge
from graph.restore import read_export, verify_against_backup


def small_graph():
    graph = GraphData()
    graph.ensure_node("Knack", "Ember Toss", knack_class="Reactive", rank=2)
    graph.ensure_node("Knack", "Frost Nip", surface_forms=["Frost Nips"])
    graph.edges.append(make_edge("SWAPS_WITH", "Knack", "Ember Toss",
                                 "Knack", "Frost Nip", {"trigger": "dusk"}))
    return graph


def test_read_export_inverts_write_export(tmp_path):
    graph = small_graph()
    write_export(graph, tmp_path)
    back = read_export(tmp_path)
    assert back.nodes == graph.nodes
    assert back.edges == graph.edges
    # and the round trip is byte-stable, not just structurally equal
    assert serialize(back) == serialize(graph)


def test_missing_backup_names_the_file(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        read_export(tmp_path)
    assert "nodes.jsonl is missing" in str(exc.value)


def test_verify_names_the_first_difference(tmp_path):
    graph = small_graph()
    write_export(graph, tmp_path)
    drifted = read_export(tmp_path)
    drifted.nodes[("Knack", "Ember Toss")]["rank"] = 9
    problems = verify_against_backup(drifted, tmp_path)
    assert len(problems) == 1
    assert "nodes.jsonl" in problems[0]
    assert "First difference at line" in problems[0]
