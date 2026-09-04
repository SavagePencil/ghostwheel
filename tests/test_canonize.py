"""Canonize's durable pieces: the schema anchor's version stamp and
fingerprint, and the refusal record — no database needed."""

from graph.extract import GraphData, make_edge

from graph.canonize import schema_fingerprint, stamp_ontology_anchor


def schema_graph():
    """A tiny graph with a schema stratum and one ground fact — enough to
    exercise the anchor stamp and the stratum fingerprint without a DB."""
    g = GraphData()
    g.ensure_node("Terrain", "Frost", defense_mod=-2)        # a ground fact
    # schema stratum: the anchor + a one-concept tower
    g.ensure_node("Archetype", "Ontology", doc="the schema anchor",
                  rank=1, version=7, fingerprint="stale")
    g.ensure_node("Archetype", "Terrain", doc="a domain concept")
    g.edges.append(make_edge("DECLARED_IN", "Archetype", "Terrain",
                             "Archetype", "Ontology"))
    g.edges.append(make_edge("INSTANCE_OF", "Archetype", "Terrain",
                             "Archetype", "Concept"))
    # a citizen's derived shadow — NOT part of the schema stratum
    g.edges.append(make_edge("INSTANCE_OF", "Terrain", "Frost",
                             "Archetype", "Terrain"))
    return g


def test_apply_stamps_version_from_the_log_sequence():
    g = schema_graph()
    assert stamp_ontology_anchor(g, 42) == []
    assert g.nodes[("Archetype", "Ontology")]["version"] == 42
    # the fingerprint moved off its stale value to the stratum's real hash
    fp = g.nodes[("Archetype", "Ontology")]["fingerprint"]
    assert fp != "stale"
    assert fp == schema_fingerprint(g)


def test_second_identical_stamp_is_idempotent():
    g = schema_graph()
    stamp_ontology_anchor(g, 42)
    first = dict(g.nodes[("Archetype", "Ontology")])
    stamp_ontology_anchor(g, 42)
    assert dict(g.nodes[("Archetype", "Ontology")]) == first


def test_schema_fingerprint_is_deterministic_and_order_free():
    g1, g2 = schema_graph(), schema_graph()
    g2.edges = list(reversed(g2.edges))  # insertion order must not matter
    assert schema_fingerprint(g1) == schema_fingerprint(g2)


def test_fingerprint_ignores_anchor_stamps_but_tracks_schema_shape():
    g = schema_graph()
    before = schema_fingerprint(g)
    # bumping the anchor's OWN version/fingerprint must not move the hash
    g.nodes[("Archetype", "Ontology")]["version"] = 999
    g.nodes[("Archetype", "Ontology")]["fingerprint"] = "whatever"
    assert schema_fingerprint(g) == before
    # a real schema edit (a new concept) does move it
    g.ensure_node("Archetype", "Newborn Concept")
    assert schema_fingerprint(g) != before


def test_stamp_preserves_the_free_text_tag():
    g = schema_graph()
    g.nodes[("Archetype", "Ontology")]["tag"] = "a later round"
    stamp_ontology_anchor(g, 5)
    assert g.nodes[("Archetype", "Ontology")]["tag"] == "a later round"


def test_stamp_names_a_missing_anchor():
    g = GraphData()
    g.ensure_node("Terrain", "Frost")
    problems = stamp_ontology_anchor(g, 1)
    assert problems and "version anchor" in problems[0]
    assert "Failed due to" in problems[0]


from graph.canonize import (clear_refusal_report, refusal_report_path,
                            write_refusal_report)


def test_refusal_report_writes_coded_rows(tmp_path):
    from graph.report import Verdict
    from graph import export as export_mod
    g = GraphData()
    g.ensure_node("Terrain", "Bog")
    export_mod.write_export(g, tmp_path / "graph" / "export")
    write_refusal_report(tmp_path, None, [Verdict(
        code="approval-missing", message="no approval on record",
        remedy="approve first", data={"items": ["a", "b"]})])
    import json as json_mod
    doc = json_mod.loads(refusal_report_path(tmp_path).read_text())
    assert doc["kind"] == "canonize-refusal"
    assert doc["kb"]  # the line of truth is named
    row = doc["refusals"][0]
    assert row["code"] == "approval-missing"
    assert row["ref"] == "no-approval"     # designer-safe ref key
    assert row["data"]["items"] == ["a", "b"]
    # a clean run retires the artifact — never a stale report
    clear_refusal_report(tmp_path)
    assert not refusal_report_path(tmp_path).exists()


def test_a_refused_apply_leaves_the_artifact(tmp_path, monkeypatch,
                                             capsys):
    # the smallest real refusal: an apply with no approval on record —
    # stderr prints as it always has AND the record lands beside the
    # round, coded and inspectable
    from graph import export as export_mod
    from graph.__main__ import cmd_canonize, cmd_init
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    assert cmd_init(tmp_path) == 0

    class Quiet:
        def __getattr__(self, name):
            raise AssertionError("no database should be touched")

    # scratch equals the base: dodge the DB by pointing the reader at
    # the export itself
    import graph.__main__ as main_mod
    from graph.restore import read_export
    monkeypatch.setattr(
        "graph.delta.read_graph",
        lambda config: read_export(tmp_path / "graph" / "export"))
    monkeypatch.setattr("graph.__main__._working_copy_check",
                        lambda *a, **k: "")
    assert cmd_canonize(tmp_path, None, apply=True) == 1
    assert "no approval on record" in capsys.readouterr().err
    import json as json_mod
    doc = json_mod.loads(refusal_report_path(tmp_path).read_text())
    assert [r["code"] for r in doc["refusals"]] == ["approval-missing"]
    # and a clean dry run clears it
    assert cmd_canonize(tmp_path, None, apply=False) == 0
    assert not refusal_report_path(tmp_path).exists()
