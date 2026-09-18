"""Graph-native procedures: the procedure linkage unhooked from files.

A Procedure citizen with no registered source file declares its
completeness as a ground prop (`known_at`, naming a Completeness value)
and carries its body as prose citizens PART_OF it. Derivation turns the
declaration into the kernel edges — KNOWN_AT to the named level,
SPECIFIED_IN to each contained prose citizen. A `known_at` naming
something that is not a Completeness value is a collated finding, not
an edge. File-registered procedures never enter this path.
"""

from graph.extract import Extractor, make_edge
from graph.ontology import (ARCHETYPE_LABEL, KERNEL_PROCEDURE_LABEL,
                            Ontology, WARNING)


def _ontology(tmp_path):
    return Ontology(
        path=tmp_path / "graph" / "ontology.yaml", base_dir=tmp_path,
        raw={}, nodes={})


def _extractor(tmp_path):
    extractor = Extractor(_ontology(tmp_path))
    # the kernel Completeness ladder, as the seed ships it
    extractor.graph.ensure_node(ARCHETYPE_LABEL, "Completeness", doc="how much")
    for level in ("Cited", "Attested", "Transcribed"):
        extractor.graph.ensure_node(ARCHETYPE_LABEL, level, doc=level)
        extractor.graph.edges.append(make_edge(
            "INSTANCE_OF", ARCHETYPE_LABEL, level,
            ARCHETYPE_LABEL, "Completeness"))
    extractor.pending_procedures = []
    return extractor


def test_known_at_derives_from_the_declared_prop(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(KERNEL_PROCEDURE_LABEL,
                                "The Maintenance Loop",
                                known_at="Attested")
    extractor.link_native_procedures()
    assert any(e.type == "KNOWN_AT"
               and (e.from_label, e.from_name)
               == (KERNEL_PROCEDURE_LABEL, "The Maintenance Loop")
               and (e.to_label, e.to_name) == (ARCHETYPE_LABEL, "Attested")
               for e in extractor.graph.edges)


def test_specified_in_derives_from_prose_containment(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(KERNEL_PROCEDURE_LABEL,
                                "The Maintenance Loop",
                                known_at="Attested")
    for name in ("The Maintenance Loop", "Failure triage"):
        extractor.graph.ensure_node("[Conduct Section]", name,
                                    body=f"## {name}\n")
        extractor.graph.edges.append(make_edge(
            "PART_OF", "[Conduct Section]", name,
            KERNEL_PROCEDURE_LABEL, "The Maintenance Loop"))
    extractor.link_native_procedures()
    cited = {(e.to_label, e.to_name) for e in extractor.graph.edges
             if e.type == "SPECIFIED_IN"
             and e.from_name == "The Maintenance Loop"}
    assert cited == {("[Conduct Section]", "The Maintenance Loop"),
                     ("[Conduct Section]", "Failure triage")}


def test_an_unknown_completeness_value_is_a_finding_not_an_edge(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(KERNEL_PROCEDURE_LABEL, "Loose Talk",
                                known_at="Rumored")
    extractor.link_native_procedures()
    assert not [e for e in extractor.graph.edges if e.type == "KNOWN_AT"]
    findings = [f for f in extractor.findings
                if f.severity == WARNING and "Rumored" in f.detail]
    assert findings, extractor.findings


def test_a_procedure_without_the_prop_derives_no_known_at(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(KERNEL_PROCEDURE_LABEL, "Quiet One")
    extractor.link_native_procedures()
    assert not [e for e in extractor.graph.edges if e.type == "KNOWN_AT"]
    assert not [f for f in extractor.findings if f.severity == WARNING]


def test_file_registered_procedures_never_enter_the_native_path(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(KERNEL_PROCEDURE_LABEL, "Filed One",
                                known_at="Attested")
    extractor.pending_procedures = [
        (KERNEL_PROCEDURE_LABEL, {"procedure": "Filed One"}, "x.yaml")]
    extractor.link_native_procedures()
    assert not [e for e in extractor.graph.edges
                if e.type in ("KNOWN_AT", "SPECIFIED_IN")]


def test_a_row_under_a_kind_of_procedure_derives_like_a_procedure(tmp_path):
    # The membership fold makes a row of a kind an instance of every
    # concept the kind is a kind of — the native linkage honors the
    # same taxonomy, however deep.
    extractor = _extractor(tmp_path)
    for kind, parent in (("Inspection Rite", KERNEL_PROCEDURE_LABEL),
                         ("Hive Rite", "Inspection Rite")):
        extractor.graph.ensure_node(ARCHETYPE_LABEL, kind, doc=kind)
        extractor.graph.edges.append(make_edge(
            "SUBTYPE_OF", ARCHETYPE_LABEL, kind, ARCHETYPE_LABEL, parent))
    extractor.graph.ensure_node("Hive Rite", "The Spring Opening",
                                known_at="Attested")
    extractor.graph.ensure_node("[Conduct Section]", "Smoker discipline",
                                body="## Smoker discipline\n")
    extractor.graph.edges.append(make_edge(
        "PART_OF", "[Conduct Section]", "Smoker discipline",
        "Hive Rite", "The Spring Opening"))
    extractor.link_native_procedures()
    assert any(e.type == "KNOWN_AT"
               and (e.from_label, e.from_name)
               == ("Hive Rite", "The Spring Opening")
               and (e.to_label, e.to_name) == (ARCHETYPE_LABEL, "Attested")
               for e in extractor.graph.edges)
    assert any(e.type == "SPECIFIED_IN"
               and (e.from_label, e.from_name)
               == ("Hive Rite", "The Spring Opening")
               and (e.to_label, e.to_name)
               == ("[Conduct Section]", "Smoker discipline")
               for e in extractor.graph.edges)


def test_a_stray_known_at_outside_the_procedure_family_stays_inert(tmp_path):
    extractor = _extractor(tmp_path)
    extractor.graph.ensure_node(ARCHETYPE_LABEL, "Tide Table", doc="charts")
    extractor.graph.ensure_node("Tide Table", "Neap Cycle",
                                known_at="Attested")
    extractor.link_native_procedures()
    assert not [e for e in extractor.graph.edges if e.type == "KNOWN_AT"]
    assert not [f for f in extractor.findings if f.severity == WARNING]
