"""Recorded attribution: the census audits the record, never re-guesses.

The provenance-recording rung: a round may declare claim→citizen links
in an attribution file beside its scratch work; the delta embeds them
(so the approval's hash covers them and the diff gate shows them being
ruled), canonize folds the approved links into the line's attribution
ledger (an applied.log twin), and a claim with a recorded link never
meets the lexical matcher — the census verifies the record instead.
A record that no longer verifies is a NAMED finding: the source moved
(link-stale) or canon moved (link-broken), never a silent re-guess.
Lexical matching survives only at the frontier — claims no round has
recorded.
"""

import json

import pytest

import graph.__main__ as main_mod
from graph.attribution import (ATTRIBUTED, CANON_GAP, EV_RECORD,
                               LINK_BROKEN, LINK_STALE, RECORDED,
                               audit_link, census, link_index,
                               render_census)
from graph.delta import Delta, attribution_verdicts
from graph.extract import GraphData, make_edge
from graph.proposal import (ATTRIBUTION_FILE, append_attribution_log,
                            attribution_log_path, attribution_row,
                            content_hash, current_dir, divergence,
                            export_dir, parse_delta,
                            read_attribution_file, read_attribution_log,
                            read_applied_log, serialize_delta)
from graph.report import REF_KEYS
from graph.restore import read_export

# the driven CLI harness (imported into this module's namespace so
# pytest resolves the fixture here too)
from tests.test_branch import (STORYBOOK, FakeDBMS, build_canon,  # noqa: F401
                               clone, driven_kb)
from tests.test_succession import (_author_and_canonize_branch,
                                   _mount_live_canon)


def _link(claim="The Falchion reach is martial.",
          citizens=(("Blade", "Falchion"),),
          source="artifacts/blades.csv", locator="abc123:1.2", **extra):
    row = {"source": source, "locator": locator, "claim": claim,
           "citizens": [list(c) for c in citizens]}
    row.update(extra)
    return row


# -- the delta block: canonical rows under the approval's hash -------------


def test_attribution_rides_the_document_and_the_hash():
    delta = Delta()
    text_without = serialize_delta(delta)
    delta.attribution = [_link()]
    text_with = serialize_delta(delta)
    # the approval hash covers the links; earlier archived rounds keep
    # their recorded ids (the key appears only when declared)
    assert content_hash(text_with) != content_hash(text_without)
    assert '"attribution"' in text_with
    assert '"attribution"' not in text_without
    assert parse_delta(text_with).attribution == [_link()]
    assert parse_delta(text_without).attribution == []


def test_attribution_rows_serialize_canonically():
    delta = Delta()
    delta.attribution = [_link(claim="B second", locator="abc123:2.1"),
                         _link(claim="A first", locator="abc123:1.1",
                               grade="high", surface="value")]
    doc = json.loads(serialize_delta(delta))
    assert [r["claim"] for r in doc["attribution"]] == ["A first",
                                                        "B second"]
    assert doc["attribution"][0]["grade"] == "high"
    # identical content in a different order hashes identically
    swapped = Delta()
    swapped.attribution = list(reversed(delta.attribution))
    assert content_hash(serialize_delta(swapped)) == \
        content_hash(serialize_delta(delta))


def test_attribution_row_names_every_defect():
    with pytest.raises(ValueError, match="missing its 'claim'"):
        attribution_row({"source": "s", "locator": "l",
                         "citizens": [["A", "x"]]})
    with pytest.raises(ValueError, match="citizens"):
        attribution_row(_link(citizens=()))
    with pytest.raises(ValueError, match="'locator' must be non-empty"):
        attribution_row(_link(locator="  "))
    with pytest.raises(ValueError, match="must be an object"):
        attribution_row(["not", "a", "dict"])


def test_a_links_only_round_is_a_real_proposal():
    delta = Delta()
    assert delta.empty
    delta.attribution = [_link()]
    assert not delta.empty


def test_attribution_divergence_is_named():
    pinned = Delta()
    pinned.attribution = [_link()]
    frozen = Delta()
    frozen.attribution = [_link()]
    assert divergence(pinned, frozen) == []
    problems = " | ".join(divergence(pinned, Delta()))
    assert "attribution" in problems and "no longer in scratch" in problems


# -- the round file --------------------------------------------------------


def test_read_attribution_file_reads_the_declared_links(tmp_path):
    assert read_attribution_file(tmp_path) == []
    path = current_dir(tmp_path) / ATTRIBUTION_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([_link()]), encoding="utf-8")
    [row] = read_attribution_file(tmp_path)
    assert row["citizens"] == [["Blade", "Falchion"]]
    path.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON list"):
        read_attribution_file(tmp_path)


def test_read_attribution_file_collates_every_bad_link(tmp_path):
    path = current_dir(tmp_path) / ATTRIBUTION_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(
        [{"source": "s"}, _link(), {"locator": "l"}]), encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        read_attribution_file(tmp_path)
    message = str(caught.value)
    assert "link 1" in message and "link 3" in message


# -- the lint: a link to nowhere refuses by name ---------------------------


def test_link_to_a_missing_citizen_refuses_by_name():
    base = GraphData()
    base.ensure_node("Blade", "Falchion")
    delta = Delta()
    delta.attribution = [_link(),
                         _link(claim="The Sabre reach is long.",
                               citizens=(("Blade", "Sabre"),))]
    verdicts = attribution_verdicts(delta, base)
    [verdict] = verdicts
    assert verdict.code == "attribution-home-missing"
    assert "Sabre" in str(verdict)


def test_a_citizen_born_this_round_is_a_valid_home():
    base = GraphData()
    delta = Delta()
    delta.nodes_added = [("Blade", "Falchion", {})]
    delta.attribution = [_link()]
    assert attribution_verdicts(delta, base) == []


def test_a_malformed_row_in_the_changeset_refuses():
    delta = Delta()
    delta.attribution = [{"claim": "orphan row"}]
    [verdict] = attribution_verdicts(delta, GraphData())
    assert verdict.code == "attribution-row-malformed"


def test_every_attribution_code_has_a_designer_safe_ref():
    for code in ("attribution-file-unreadable", "attribution-row-malformed",
                 "attribution-home-missing"):
        assert code in REF_KEYS


# -- the ledger: an applied.log twin ---------------------------------------


def test_ledger_appends_stamped_rows_and_reads_them_back(tmp_path):
    assert read_attribution_log(tmp_path) == []
    append_attribution_log(tmp_path, [_link()], sequence=3)
    append_attribution_log(tmp_path, [_link(claim="Another.")], sequence=4)
    rows = read_attribution_log(tmp_path)
    assert [r["sequence"] for r in rows] == [3, 4]
    assert rows[0]["citizens"] == [["Blade", "Falchion"]]
    # empty folds write nothing — no ledger is born for a linkless round
    append_attribution_log(tmp_path / "other", [], sequence=1)
    assert not attribution_log_path(tmp_path / "other").exists()


def test_link_index_later_rows_supersede():
    early = _link(citizens=(("Blade", "Falchion"),))
    late = _link(citizens=(("Blade", "Sabre"),))
    index = link_index([early, late])
    assert index[next(iter(index))]["citizens"] == [["Blade", "Sabre"]]


# -- the audit: three voices, never a silent re-guess ----------------------


def _canon():
    graph = GraphData()
    graph.ensure_node("Blade", "Falchion", reach="martial")
    graph.ensure_node("Herb", "Nightbell", hue="pale")
    return graph


def test_a_recorded_claim_never_meets_the_matcher():
    graph = _canon()
    links = [_link(claim="The Falchion reach is martial.")]
    sources = {"artifacts/blades.csv":
               ["The Falchion reach is martial."]}
    [result] = census("The Falchion reach is martial.", graph,
                      links=links, source_claims=sources.get)
    assert result.verdict == RECORDED
    assert result.evidence == [EV_RECORD]
    assert result.attested is True
    assert result.citizens == [("Blade", "Falchion")]


def test_a_moved_source_is_a_named_event():
    graph = _canon()
    links = [_link(claim="The Falchion reach is martial.")]
    sources = {"artifacts/blades.csv":
               ["The Falchion reach is sweeping now."]}
    [result] = census("The Falchion reach is martial.", graph,
                      links=links, source_claims=sources.get)
    assert result.verdict == LINK_STALE
    assert result.attested is False


def test_a_vanished_citizen_is_a_broken_link():
    graph = GraphData()  # canon moved: the Falchion is gone
    links = [_link(claim="The Falchion reach is martial.")]
    [result] = census("The Falchion reach is martial.", graph,
                      links=links)
    assert result.verdict == LINK_BROKEN


def test_an_unconsultable_source_is_counted_never_nagged():
    graph = _canon()
    links = [_link(claim="The Falchion reach is martial.")]
    # no resolver at all, and a resolver that cannot reach the source:
    # both count the link recorded with attestation unknown
    [without] = census("The Falchion reach is martial.", graph,
                       links=links)
    [unreachable] = census("The Falchion reach is martial.", graph,
                           links=links, source_claims=lambda source: None)
    assert without.verdict == RECORDED and without.attested is None
    assert unreachable.verdict == RECORDED and unreachable.attested is None


def test_unrecorded_claims_still_reach_the_lexical_frontier():
    graph = _canon()
    links = [_link(claim="The Falchion reach is martial.")]
    draft = ("The Falchion reach is martial. "
             "The Nightbell hue is pale. "
             "The Ghostroot is a rumor.")
    results = census(draft, graph, links=links)
    verdicts = {r.claim: r.verdict for r in results}
    # census claims arrive normalized (lowercased, unpunctuated)
    assert verdicts["the falchion reach is martial"] == RECORDED
    assert verdicts["the nightbell hue is pale"] == ATTRIBUTED
    assert verdicts["the ghostroot is a rumor"] == CANON_GAP


def test_render_census_leads_with_the_recorded_split():
    graph = _canon()
    links = [_link(claim="The Falchion reach is martial."),
             _link(claim="The Nightbell is a pale herb.",
                   citizens=(("Herb", "Nightbell"),),
                   source="artifacts/herbs.csv"),
             _link(claim="The Ghostroot wards the door.",
                   citizens=(("Herb", "Ghostroot"),),
                   source="artifacts/herbs.csv")]
    sources = {"artifacts/blades.csv":
               ["The Falchion reach is martial."],
               "artifacts/herbs.csv": ["The Nightbell blooms at dusk.",
                                       "The Ghostroot wards the door."]}
    draft = ("The Falchion reach is martial. "
             "The Nightbell is a pale herb. "
             "The Ghostroot wards the door.")
    text = render_census(census(draft, graph, links=links,
                                source_claims=sources.get))
    assert "1 claims recorded by provenance" in text
    assert "1 moved sources" in text and "1 broken links" in text
    assert "### Moved sources" in text
    assert "the nightbell is a pale herb" in text
    assert "### Broken links" in text
    assert "(Herb) Ghostroot" in text


def test_render_census_without_links_is_byte_identical():
    graph = _canon()
    draft = "The Falchion reach is martial. The Ghostroot is a rumor."
    assert render_census(census(draft, graph)) == \
        render_census(census(draft, graph, links=[]))
    assert "recorded by provenance" not in render_census(census(draft,
                                                                graph))


def test_audit_link_verifies_every_citizen():
    graph = _canon()
    row = _link(citizens=(("Blade", "Falchion"), ("Herb", "Ghostroot")))
    assert audit_link(row, graph).verdict == LINK_BROKEN


# -- the round, driven through the CLI -------------------------------------


def _declare_links(base, branch, rows):
    path = current_dir(base, branch) / ATTRIBUTION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_a_recorded_round_folds_into_the_ledger(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    link = _link(claim="Ember lives in the Hearth.",
                 citizens=(("Character", "Ember"),),
                 source="artifacts/tale.md", locator="fefe12:1.1")

    def declare(_authored):
        _declare_links(base, branch, [link])

    _author_and_canonize_branch(base, fake, branch, extra=declare)
    out = capsys.readouterr().out
    # the gate showed the link being ruled, and the delta counted it
    assert "Recorded attribution" in out
    assert "1 attribution links recorded" in out
    assert "Ember lives in the Hearth." in out
    # the approved link folded into the branch's ledger, stamped with
    # the round's sequence
    [row] = read_attribution_log(base, branch)
    assert row["citizens"] == [["Character", "Ember"]]
    assert row["sequence"] == read_applied_log(base, branch)[-1][0]
    # canon's own ledger never moved
    assert not attribution_log_path(base).exists()


def test_a_link_to_nowhere_refuses_at_the_gate(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    assert main_mod.cmd_restore(base, branch=branch,
                                base="schema-only") == 0
    fake.databases[f"{branch}-scratch"] = clone(
        read_export(export_dir(base, branch)))
    _declare_links(base, branch,
                   [_link(claim="A ghost claim.",
                          citizens=(("Character", "Nobody"),))])
    assert main_mod.cmd_delta(base, None, branch=branch) == 1
    out = capsys.readouterr().out
    assert "no such citizen exists" in out
    # the refusal holds at apply too, against the same declared file
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 1
    err = capsys.readouterr().err
    assert "no such citizen exists" in err
    assert not attribution_log_path(base, branch).exists()


def test_the_adoption_carries_the_ledger_and_archives_the_old(driven_kb,
                                                              capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    link = _link(claim="Ember lives in the Hearth.",
                 citizens=(("Character", "Ember"),),
                 source="artifacts/tale.md", locator="fefe12:1.1")

    def declare(_authored):
        _declare_links(base, branch, [link])

    _author_and_canonize_branch(base, fake, branch, extra=declare)
    _mount_live_canon(base, fake)
    # a pre-adoption row in canon's ledger: the superseded line's link,
    # which must survive only in the archive
    append_attribution_log(base, [_link(claim="An old-line claim.")],
                           sequence=1)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    adoption_sequence = read_applied_log(base)[-1][0]
    rows = read_attribution_log(base)
    assert [r["claim"] for r in rows] == ["Ember lives in the Hearth."]
    assert rows[0]["sequence"] == adoption_sequence
    # the superseded ledger survives in the archive branch
    archive = f"superseded-{adoption_sequence}"
    [archived] = read_attribution_log(base, archive)
    assert archived["claim"] == "An old-line claim."
    # and the archive's rounds dir carries no stray ledger copy
    from graph.proposal import proposals_dir
    assert not (proposals_dir(base, archive)
                / attribution_log_path(base).name).exists()
