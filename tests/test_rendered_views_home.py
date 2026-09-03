"""The render mappings' canon home.

A label's render-only mappings (rendered_view / rendered_views) ride its
Archetype row BESIDE the embedded spec, as one JSON list — never inside
spec_json, which the loader and deriver read — and reconstruct as the
spec's `rendered_views` list. Editing that prop is a schema-ceremony
class of its own (add, change, remove), linted for shape at the gate.
The table renderer and the round-trip judge's column typing read canon,
so a corpus that retires its bootstrap file loses nothing.

Storybook domain: gadgets, parts, and tiers.
"""

import json
import textwrap

import tests.conftest as conftest
from graph import export as export_mod
from graph.__main__ import cmd_render_tables, cmd_roundtrip
from graph.delta import ceremony_records, diff, lint, render_report
from graph.extract import GraphData, derive, extract, make_edge
from graph.ontology import (ARCHETYPE_LABEL, ERROR, RENDERED_VIEWS_PROP,
                            load_ontology, ontology_from_graph,
                            rendered_views_of, rendered_views_problems)
from graph.report import REF_KEYS
from graph.restore import read_export
from graph.roundtrip import column_aliases, column_types
from tests.test_render_tables import DOC, GIZMOS, ONTOLOGY

_make_repo = getattr(conftest.make_repo, "__wrapped__", conftest.make_repo)

# Part declares one view (the single spelling); Tier declares two (the
# list spelling, one with a name template); Gizmo, a source label,
# declares none.
VIEWED = ONTOLOGY.replace(
    "  Part:\n    values: [Bolt, Spring, Cog]\n    concept: Gadget Concept\n",
    "  Part:\n    values: [Bolt, Spring, Cog]\n    concept: Gadget Concept\n"
    "    aliases: { Sprng: Spring }\n"
    "    rendered_view:\n      source: data/gizmos.csv\n"
    "      key: Gizmo\n"
    "  Tier:\n    values: [Low, High]\n    concept: Gadget Concept\n"
    "    rendered_views:\n"
    "      - { source: data/gizmos.csv, key: Gizmo }\n"
    "      - { source: data/gizmos.csv, key: Gizmo, "
    "name_template: \"Tier {key}\" }\n")


def _build(tmp_path):
    base_dir, path = _make_repo(tmp_path)(
        {"docs/gadgets.md": DOC, "data/gizmos.csv": GIZMOS}, VIEWED)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR]
    return base_dir, ontology, graph


# -- the embedding and its reconstruction ----------------------------------


def test_from_sources_build_embeds_the_views_beside_the_spec(tmp_path):
    _, ontology, graph = _build(tmp_path)
    part = graph.nodes[(ARCHETYPE_LABEL, "Part")]
    assert json.loads(part[RENDERED_VIEWS_PROP]) == \
        rendered_views_of(ontology.nodes["Part"])
    assert "rendered_view" not in part["spec_json"]
    assert '"aliases"' in part["spec_json"]  # the spec itself still rides
    tier = graph.nodes[(ARCHETYPE_LABEL, "Tier")]
    views = json.loads(tier[RENDERED_VIEWS_PROP])
    assert len(views) == 2 and views[1]["name_template"] == "Tier {key}"
    assert RENDERED_VIEWS_PROP not in graph.nodes[(ARCHETYPE_LABEL, "Gizmo")]


def test_reconstruction_hands_the_views_back_as_the_spec_list(tmp_path):
    base_dir, ontology, graph = _build(tmp_path)
    rec = ontology_from_graph(graph, base_dir)
    for label in ("Part", "Tier", "Gizmo"):
        assert rendered_views_of(rec.nodes[label]) == \
            rendered_views_of(ontology.nodes[label]), label
    assert "rendered_view" not in rec.nodes["Part"]
    assert "rendered_views" not in rec.nodes["Gizmo"]


def test_export_and_rederivation_keep_the_views(tmp_path):
    base_dir, _, graph = _build(tmp_path)
    export_dir = base_dir / "graph" / "export"
    export_mod.write_export(graph, export_dir)
    read_back = read_export(export_dir)
    assert read_back.nodes[(ARCHETYPE_LABEL, "Tier")][RENDERED_VIEWS_PROP] \
        == graph.nodes[(ARCHETYPE_LABEL, "Tier")][RENDERED_VIEWS_PROP]
    # re-derivation over the reconstruction reproduces the backup byte
    # for byte — the prop is schema ground, preserved and re-embedded
    # identically, never rebuilt
    rederived, findings = derive(ontology_from_graph(read_back, base_dir),
                                 read_back)
    assert not [f for f in findings if f.severity == ERROR], findings
    assert export_mod.serialize(rederived) == export_mod.serialize(read_back)


# -- the ceremony class -----------------------------------------------------


def _view(**extra):
    return json.dumps([{"source": "data/gizmos.csv", "key": "Gizmo",
                        **extra}], sort_keys=True)


def _base():
    g = GraphData()
    g.ensure_node(ARCHETYPE_LABEL, "Ontology")
    g.ensure_node(ARCHETYPE_LABEL, "Theme", doc="a philosophy statement")
    g.ensure_node(ARCHETYPE_LABEL, "Part", doc="a bit of a gadget",
                  spec_json=json.dumps({"values": ["Bolt"],
                                        "concept": "Gadget Concept"}))
    g.ensure_node(ARCHETYPE_LABEL, "Gizmo",
                  spec_json=json.dumps({"source": "data/gizmos.csv",
                                        "key": "Gizmo"}))
    g.ensure_node(ARCHETYPE_LABEL, "Tier", spec_json=json.dumps({
        "values": ["Low"], "concept": "Gadget Concept"}),
        **{RENDERED_VIEWS_PROP: _view()})
    for name in ("Theme", "Part", "Gizmo", "Tier"):
        g.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, name,
                                 ARCHETYPE_LABEL, "Ontology"))
    return g


def _clone(graph):
    g = GraphData()
    for (label, name), props in graph.nodes.items():
        g.ensure_node(label, name, **dict(props))
    g.edges = list(graph.edges)
    return g


def _round(edit):
    base = _base()
    scratch = _clone(base)
    edit(scratch)
    d = diff(base, scratch)
    return d, base, ceremony_records(d, base)


def test_adding_a_render_mapping_is_ceremony_not_refusal():
    d, base, (items, violations, nodes, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Part")].__setitem__(
            RENDERED_VIEWS_PROP, _view()))
    assert violations == [] and lint(d, base) == []
    assert (ARCHETYPE_LABEL, "Part") in nodes
    [item] = items
    assert "RENDER MAPPING ADDED on 'Part'" in str(item)
    assert "1 view (was 0)" in str(item)
    report = render_report(d, [], items)
    assert "## Schema changes — the ceremony" in report
    assert "render-mapping edits" in report
    assert "⚑ RENDER MAPPING ADDED" in report


def test_changing_and_removing_a_render_mapping_are_ceremony():
    _, _, (items, violations, _, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Tier")].__setitem__(
            RENDERED_VIEWS_PROP, json.dumps([
                {"source": "data/gizmos.csv", "key": "Gizmo"},
                {"source": "data/gizmos.csv", "key": "Gizmo",
                 "name_template": "Tier {key}"}])))
    assert violations == []
    [item] = items
    assert "RENDER MAPPING EDITED on 'Tier'" in str(item)
    assert "2 views (was 1)" in str(item)

    _, _, (items, violations, _, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Tier")].pop(RENDERED_VIEWS_PROP))
    assert violations == []
    [item] = items
    assert "RENDER MAPPING REMOVED on 'Tier'" in str(item)
    assert "0 views (was 1)" in str(item)
    assert item.row()["data"] == {"property": RENDERED_VIEWS_PROP,
                                  "before_views": 1, "after_views": 0}


def test_a_render_mapping_rides_with_a_doc_edit():
    def edit(s):
        s.nodes[(ARCHETYPE_LABEL, "Part")]["doc"] = "a piece of a gadget"
        s.nodes[(ARCHETYPE_LABEL, "Part")][RENDERED_VIEWS_PROP] = _view()
    _, _, (items, violations, _, _) = _round(edit)
    assert violations == []
    assert {i.code for i in items} == {"doc-edit", "render-mapping-edited"}


def test_an_unreadable_render_mapping_refuses_by_name():
    _, _, (items, violations, nodes, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Part")].__setitem__(
            RENDERED_VIEWS_PROP, "{not json"))
    assert items == [] and (ARCHETYPE_LABEL, "Part") not in nodes
    [verdict] = violations
    assert verdict.code == "render-mapping-unreadable"
    assert "does not parse as JSON" in str(verdict)


def test_a_malformed_render_mapping_refuses_with_every_problem_named():
    _, _, (items, violations, _, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Part")].__setitem__(
            RENDERED_VIEWS_PROP, json.dumps([
                {"key": "Gizmo", "colour": "red", "name_template": "Part"}])))
    assert items == []
    [verdict] = violations
    assert verdict.code == "render-mapping-invalid"
    problems = verdict.row()["data"]["problems"]
    assert any("unknown key 'colour'" in p for p in problems)
    assert any("needs a source CSV" in p for p in problems)
    assert any("name_template" in p for p in problems)
    # collated: every problem in one refusal
    assert len(problems) == 3


def test_a_render_mapping_on_a_source_label_or_a_concept_row_refuses():
    # a label that renders from its own row source declares no view
    _, _, (_, violations, _, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Gizmo")].__setitem__(
            RENDERED_VIEWS_PROP, _view()))
    [verdict] = violations
    assert verdict.code == "render-mapping-invalid"
    assert "WITHOUT a row-source" in str(verdict)
    # a concept-only row is not a label at all
    _, _, (_, violations, _, _) = _round(
        lambda s: s.nodes[(ARCHETYPE_LABEL, "Theme")].__setitem__(
            RENDERED_VIEWS_PROP, _view()))
    [verdict] = violations
    assert verdict.code == "render-mapping-invalid"
    assert "not a label" in str(verdict)


def test_a_render_mapping_without_the_base_refuses():
    base = _base()
    scratch = _clone(base)
    scratch.nodes[(ARCHETYPE_LABEL, "Part")][RENDERED_VIEWS_PROP] = _view()
    _, violations, nodes, _ = ceremony_records(diff(base, scratch), None)
    [verdict] = violations
    assert verdict.code == "render-mapping-invalid"
    assert "no base graph" in str(verdict)
    assert (ARCHETYPE_LABEL, "Part") not in nodes


def test_a_born_label_may_arrive_with_its_render_mapping():
    def birth(value):
        def edit(s):
            s.ensure_node(ARCHETYPE_LABEL, "Grade",
                          spec_json=json.dumps({"values": ["Bronze"],
                                                "concept": "Gadget Concept"}),
                          **{RENDERED_VIEWS_PROP: value})
            s.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Grade",
                                     ARCHETYPE_LABEL, "Ontology"))
        return edit
    _, _, (items, violations, nodes, _) = _round(birth(_view()))
    assert violations == [] and (ARCHETYPE_LABEL, "Grade") in nodes
    assert any("NEW LABEL" in str(i) for i in items)
    _, _, (items, violations, nodes, _) = _round(birth("[{"))
    assert items == [] and (ARCHETYPE_LABEL, "Grade") not in nodes
    [verdict] = violations
    assert verdict.code == "render-mapping-unreadable"


def test_the_shape_lint_names_every_defect():
    assert rendered_views_problems("no") == [
        "the render mappings must be a list of view mappings"]
    assert rendered_views_problems([]) == []
    problems = rendered_views_problems(
        [{"source": "a.csv", "labels": [{"colour": "red"}, "x"]}, 7],
        {"key": "K"})
    assert problems == ["view[0].labels[0]: unknown key 'colour'",
                        "view[0].labels[0]: a labels entry needs a label",
                        "view[0].labels[1]: a labels entry must be a mapping",
                        "view[1]: a view must be a mapping"]


def test_render_mapping_codes_carry_designer_safe_refs():
    for code in ("render-mapping-edited", "render-mapping-unreadable",
                 "render-mapping-invalid"):
        assert code in REF_KEYS
        assert "render" not in REF_KEYS[code] and "spec" not in REF_KEYS[code]


# -- the consumers read canon ----------------------------------------------


def test_render_tables_renders_from_canon_with_no_bootstrap_file(tmp_path,
                                                                 capsys):
    from graph import render_tables
    base_dir, ontology, graph = _build(tmp_path)
    expected = render_tables.render_chapter(
        base_dir, "docs/gadgets.md", graph, ontology).draft()
    export_mod.write_export(graph, base_dir / "graph" / "export")
    (base_dir / "graph" / "ontology.yaml").unlink()
    assert cmd_render_tables(base_dir, "docs/gadgets.md", None) == 0
    out = capsys.readouterr().out
    assert "rendered  data/gizmos.csv" in out
    draft = base_dir / "graph" / "reports" / "gadgets-tables-draft.md"
    assert draft.read_text(encoding="utf-8") == expected


def test_column_typing_and_aliases_reconstruct_from_canon(tmp_path):
    base_dir, ontology, graph = _build(tmp_path)
    rec = ontology_from_graph(graph, base_dir)
    assert column_types(rec) == column_types(ontology)
    assert column_aliases(rec) == column_aliases(ontology)
    # the view-typed column is present, proving the views were consulted
    assert ("data/gizmos.csv", "Gizmo") in column_aliases(rec)


def test_roundtrip_says_aloud_when_no_backup_declares_the_columns(tmp_path,
                                                                  capsys):
    base_dir, _ = _make_repo(tmp_path)(
        {"docs/gadgets.md": DOC, "data/gizmos.csv": GIZMOS}, "version: 1")
    draft = base_dir / "draft.md"
    draft.write_text(textwrap.dedent(DOC), encoding="utf-8")
    cmd_roundtrip(base_dir, "docs/gadgets.md", str(draft))
    err = capsys.readouterr().err
    assert "No committed backup to read the table declarations from" in err
    assert "every table column compares byte-exact" in err
