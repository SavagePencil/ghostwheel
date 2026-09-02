"""The record-first report inversion: verdicts and ceremony items are
born as typed records ({code, subject, message, remedy, data}); markdown
is one renderer over the report model and JSON another.

The golden files under tests/fixtures were captured from the renderer
BEFORE the inversion — byte parity against them proves the rewiring
changed structure, not meaning. The legacy string surfaces (lint,
ceremony_classify, lint_stitch, body_sync_violations, render_report)
remain, as renderings of the records.
"""

import json
from pathlib import Path

from graph.delta import (Delta, body_sync_verdicts, ceremony_records,
                         build_report, lint, lint_verdicts, stitch_verdicts)
from graph.extract import GraphData, make_edge
from graph.report import render_json, render_markdown
from tests import delta_report_fixture as fx

FIXTURES = Path(__file__).parent / "fixtures"


def golden(name):
    return (FIXTURES / f"delta-report-{name}.md").read_text(encoding="utf-8")


def rich_report(tmp_path):
    """The rich scenario assembled the record way — no strings anywhere
    until a renderer runs."""
    base, scratch, changes, advisories = fx.rich_materials(tmp_path)
    verdicts = lint_verdicts(changes, base)
    items = ceremony_records(changes, base)[0]
    verdicts += stitch_verdicts(changes, scratch)
    return build_report(changes, verdicts, items, advisories)


# -- parity: the inversion changed structure, not meaning ------------------

def test_record_path_reproduces_the_golden_report(tmp_path):
    assert render_markdown(rich_report(tmp_path)) == golden("rich")


def test_legacy_string_path_reproduces_the_golden_report(tmp_path):
    changes, violations, items, advisories = fx.rich_scenario(tmp_path)
    assert fx.legacy_markdown(changes, violations, items, advisories) \
        == golden("rich")


def test_clean_round_reproduces_its_golden(tmp_path):
    changes, violations, items = fx.clean_scenario(tmp_path)
    assert violations == []
    assert fx.legacy_markdown(changes, violations, items) == golden("clean")


def test_empty_delta_reproduces_its_golden():
    assert render_markdown(build_report(Delta(), [])) == golden("empty")


def test_empty_delta_with_refusals_renders_the_lint_section():
    # A round can refuse without proposing anything — the classic case
    # is a program body out of sync with its approved file, where the
    # node never enters the delta. The markdown must say so, exactly as
    # the JSON rendering always has; a clean empty round stays byte-
    # identical to its own golden (the test above).
    from graph.report import Verdict
    verdicts = [Verdict(
        code="body-out-of-sync",
        message="program body 'Tend the Grove' is out of sync with its "
                "approved file — re-approve the body or restore the "
                "file")]
    rendered = render_markdown(build_report(Delta(), verdicts))
    assert rendered == golden("empty-refused")
    assert "no proposal present" in rendered
    assert "## Ground-facts lint" in rendered
    assert "Tend the Grove" in rendered


def test_empty_delta_refusals_and_advisories_render_together():
    # Both tails at once: the lint section first, the roster advisories
    # after — nothing swallowed by the empty short-circuit.
    from graph.report import Verdict
    verdicts = [Verdict(code="body-out-of-sync", message="a refusal")]
    rendered = render_markdown(build_report(Delta(), verdicts,
                                            advisories=fx.ADVISORIES))
    lint_at = rendered.index("## Ground-facts lint")
    advisories_at = rendered.index("## Advisories — the branch's roster")
    assert lint_at < advisories_at
    for advisory in fx.ADVISORIES:
        assert advisory in rendered


def test_empty_delta_keeps_the_advisories_section():
    # A branch round with nothing authored yet must still surface its
    # roster gaps on the approver's markdown — the empty short-circuit
    # may not swallow the advisories tail. Parity oracle: the pre-model
    # assembly (renderer output + appended section) that cmd_delta used.
    empty = Delta()
    rendered = render_markdown(build_report(empty, [],
                                            advisories=fx.ADVISORIES))
    assert rendered == fx.legacy_markdown(empty, [], [], fx.ADVISORIES)
    assert "no proposal present" in rendered
    assert "## Advisories — the branch's roster" in rendered
    for advisory in fx.ADVISORIES:
        assert advisory in rendered


def test_advisory_strings_wrap_as_advisory_records():
    doc = json.loads(render_json(build_report(
        Delta(), [], advisories=fx.ADVISORIES)))
    assert [a["severity"] for a in doc["advisories"]] == \
        ["advisory"] * len(fx.ADVISORIES)
    assert doc["empty"] is True


def test_legacy_surfaces_still_speak_in_strings(tmp_path):
    # long-standing consumers join and substring-match these lists
    _, violations, items, _ = fx.rich_scenario(tmp_path)
    assert violations and all(isinstance(v, str) for v in violations)
    assert items and all(isinstance(i, str) for i in items)


# -- completeness: prose can only be born from a record --------------------

def test_every_markdown_verdict_has_a_json_record(tmp_path):
    report = rich_report(tmp_path)
    markdown = render_markdown(report)
    doc = json.loads(render_json(report))
    assert markdown.count("- ⚠ ") == len(doc["verdicts"]) == 13
    assert markdown.count("- ⚑ ") == len(doc["ceremony"]) == 3
    assert len(doc["advisories"]) == len(fx.ADVISORIES)


def test_rich_scenario_names_every_refusal_by_code(tmp_path):
    report = rich_report(tmp_path)
    assert {v.code for v in report.verdicts} == {
        "schema-label-row-authored", "schema-concept-undeclared",
        "machine-label-authored", "node-unnamed",
        "schema-edge-removed", "schema-edge-authored",
        "derived-edge-authored", "derived-edge-modified",
        "membership-from-archetype", "membership-target-not-concept",
        "membership-basis-missing", "membership-basis-blanked",
        "stitch-unneeded"}
    assert {i.code for i in report.ceremony} == {
        "new-concept", "doc-edit", "removed-concept"}


# -- the JSON rows: shape, particulars, omissions --------------------------

def test_subjects_carry_the_citizen_ref_shape(tmp_path):
    doc = json.loads(render_json(rich_report(tmp_path)))
    by_code = {v["code"]: v for v in doc["verdicts"]}
    node = by_code["machine-label-authored"]["subject"]
    assert node == {"kind": "citizen", "label": "Step",
                    "name": "Ghost Step"}
    edge = by_code["membership-basis-blanked"]["subject"]
    assert edge["kind"] == "connection" \
        and edge["type"] == "DECLARED_MEMBER_OF"
    assert edge["from"] == {"label": "Object", "name": "Plain Pebble"}
    assert edge["to"] == {"label": "Archetype", "name": "Tool"}


def test_verdict_rows_carry_remedy_and_particulars(tmp_path):
    doc = json.loads(render_json(rich_report(tmp_path)))
    by_code = {v["code"]: v for v in doc["verdicts"]}
    assert by_code["membership-basis-missing"]["remedy"].startswith(
        "Add a `basis` property")
    assert by_code["membership-basis-blanked"]["data"]["changes"] == {
        "basis": ["kept by the gatekeeper", ""]}
    assert all(v["severity"] == "refusal" for v in doc["verdicts"])
    assert all(a["severity"] == "advisory" for a in doc["advisories"])


def test_ceremony_rows_carry_their_particulars(tmp_path):
    doc = json.loads(render_json(rich_report(tmp_path)))
    by_code = {i["code"]: i for i in doc["ceremony"]}
    assert by_code["new-concept"]["data"] == {
        "declared_in": "Chronicle", "instance_of": ["Treasure"],
        "doc": "Old tales carried by wandering scribes"}
    assert by_code["doc-edit"]["data"] == {
        "property": "doc", "before": None,
        "after": "A thing that does work"}
    assert by_code["removed-concept"]["subject"] == {
        "kind": "citizen", "label": "Archetype", "name": "Relic"}


def test_long_doc_edit_is_truncated_in_prose_but_whole_in_data():
    saga = "x" * 150
    items = ceremony_records(Delta(
        nodes_changed=[("Archetype", "Tool", {"doc": (None, saga)})]))[0]
    [item] = items
    assert "…" in str(item) and saga not in str(item)
    assert item.data["after"] == saga


def test_summary_counts_match_the_changeset(tmp_path):
    report = rich_report(tmp_path)
    doc = json.loads(render_json(report))
    assert doc["summary"]["nodes_added"] == len(report.delta.nodes_added)
    assert doc["summary"]["stitched"] == 2
    assert doc["kind"] == "delta-report" and "empty" not in doc


def test_clean_report_json_omits_what_it_does_not_have(tmp_path):
    changes, _, _ = fx.clean_scenario(tmp_path)
    doc = json.loads(render_json(build_report(changes, [])))
    for absent in ("verdicts", "ceremony", "advisories", "empty"):
        assert absent not in doc
    assert "stitched" not in doc["summary"]


def test_empty_delta_json_says_so():
    doc = json.loads(render_json(build_report(Delta(), [])))
    assert doc == {"kind": "delta-report", "empty": True}


def test_proposal_id_rides_the_json_report(tmp_path):
    changes, _, _ = fx.clean_scenario(tmp_path)
    doc = json.loads(render_json(build_report(changes, []),
                                 proposal_id="abc123"))
    assert doc["proposal_id"] == "abc123"


def test_json_rendering_is_deterministic(tmp_path):
    report = rich_report(tmp_path)
    once, twice = render_json(report), render_json(report)
    assert once == twice and once.endswith("\n")


# -- the families the rich scenario does not reach, refused by name --------

def _membership(basis=None):
    props = {"basis": basis} if basis is not None else {}
    return make_edge("DECLARED_MEMBER_OF", "Object", "Golden Key",
                     "Archetype", "Tool", props)


def test_membership_without_a_base_graph_is_unverified():
    [verdict] = lint_verdicts(
        Delta(edges_added=[_membership("opens the door")]), None)
    assert verdict.code == "membership-unverified"
    assert "cannot be verified without the base graph" in str(verdict)


def test_schema_removal_without_a_base_graph_is_unverified():
    violations = ceremony_records(
        Delta(nodes_removed=[("Archetype", "Relic", {})]), None)[1]
    [verdict] = violations
    assert verdict.code == "schema-removal-unverified"
    assert "without the base graph in view" in str(verdict)


def test_referenced_schema_row_removal_counts_its_references(tmp_path):
    _, base = fx.build_base(tmp_path)
    violations = ceremony_records(
        Delta(nodes_removed=[("Archetype", "Tool", {})]), base)[1]
    [verdict] = violations
    assert verdict.code == "schema-row-referenced"
    assert verdict.data["connections"] >= 1
    assert "DECLARED_MEMBER_OF" in verdict.data["kinds"]


def test_out_of_class_schema_edit_names_the_properties():
    violations = ceremony_records(Delta(
        nodes_changed=[("Archetype", "Tool",
                        {"spec_json": ("a", "b")})]))[1]
    [verdict] = violations
    assert verdict.code == "schema-edit-out-of-class"
    assert verdict.data["properties"] == ["spec_json"]


def test_schema_edge_modification_is_refused_with_its_changes():
    edge = make_edge("INSTANCE_OF", "Archetype", "Tool",
                     "Archetype", "Concept")
    [verdict] = lint_verdicts(Delta(edges_changed=[(edge, {"w": (1, 2)})]))
    assert verdict.code == "schema-edge-modified"
    assert verdict.data["changes"] == {"w": [1, 2]}


def test_unnamed_edge_endpoint_is_refused():
    edge = make_edge("KEPT_WITH", "Object", None, "Object", "Golden Key")
    [verdict] = lint_verdicts(Delta(edges_added=[edge]))
    assert verdict.code == "edge-endpoint-unnamed"


def test_stitch_refusals_carry_their_codes():
    schema = make_edge("DECLARED_IN", "Archetype", "Lore",
                       "Source", "Chronicle")
    derived = make_edge("INSTANCE_OF", "Object", "Golden Key",
                        "Archetype", "Tool")
    unnamed = make_edge("KEPT_WITH", "Object", None, "Object", "Golden Key")
    verdicts = stitch_verdicts(
        Delta(stitch=[schema, derived, unnamed]), GraphData())
    assert [v.code for v in verdicts] == [
        "stitch-schema-edge", "stitch-derived-edge",
        "stitch-endpoint-unnamed"]


def test_body_sync_verdicts_name_their_codes(tmp_path):
    scratch = GraphData()
    scratch.ensure_node("Object", "Golden Key",
                        source_path="programs/opening.md", body="turn twice")
    [verdict] = body_sync_verdicts(scratch, tmp_path)
    assert verdict.code == "body-file-unreadable"
    assert verdict.data == {"source_path": "programs/opening.md"}
    path = tmp_path / "programs" / "opening.md"
    path.parent.mkdir(parents=True)
    path.write_text("turn thrice", encoding="utf-8")
    [verdict] = body_sync_verdicts(scratch, tmp_path)
    assert verdict.code == "body-out-of-sync"
    path.write_text("turn twice", encoding="utf-8")
    assert body_sync_verdicts(scratch, tmp_path) == []


def test_every_produced_code_has_a_designer_safe_ref_key():
    # the front-door tenets: reference numbers are plain-English keys with no
    # machinery vocabulary. The coverage set is derived from the
    # producers' SOURCE, not hand-copied — a new code constructed
    # anywhere without a mapping fails here, because the fallback
    # would put the raw code (machinery words and all) on the
    # designer's surface.
    import inspect
    import re

    import graph.__main__ as main_module
    import graph.delta as delta_module
    from graph.report import REF_KEYS, ref_key
    source = inspect.getsource(delta_module) + inspect.getsource(main_module)
    produced = set(re.findall(r'code="([a-z0-9-]+)"', source))
    assert len(produced) >= 30, produced
    # "unclassified" is the documented wrapper fallback for legacy
    # plain-string violations; its own name is designer-tolerable.
    assert produced - set(REF_KEYS) == {"unclassified"}, \
        sorted(produced - set(REF_KEYS))
    machinery = ("stitch", "schema", "archetype", "derived", "lint",
                 "delta", "scratch", "roster", "node", "edge", "label",
                 "database", "graph", "round", "book")
    for key in list(REF_KEYS.values()) + [ref_key("unclassified")]:
        for word in machinery:
            assert word not in key, (key, word)


def test_ref_key_falls_back_to_the_code():
    from graph.report import ref_key
    assert ref_key("membership-basis-missing") == "missing-reason"
    assert ref_key("some-future-code") == "some-future-code"


def test_rows_carry_their_refs(tmp_path):
    doc = json.loads(render_json(rich_report(tmp_path)))
    by_code = {v["code"]: v for v in doc["verdicts"]}
    assert by_code["membership-basis-missing"]["ref"] == "missing-reason"
    assert by_code["machine-label-authored"]["ref"] == \
        "machine-made-kind"
    items = {i["code"]: i for i in doc["ceremony"]}
    assert items["doc-edit"]["ref"] == "description-edit"


def test_lint_wrapper_matches_its_records(tmp_path):
    base, _, changes, _ = fx.rich_materials(tmp_path)
    assert lint(changes, base) == \
        [str(v) for v in lint_verdicts(changes, base)]
