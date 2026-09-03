"""The receipt staleness guard: sentence-grain carried quotes are
checked against their cited sources — stale quotes surface with a
beneath-verdict (honest home vs only home), sources that no longer
resolve are named, ruling-shaped sources are counted but never nagged,
and the delta gate refuses a freshly authored quote its source does not
contain. Row-shaped from_text is not a receipt and is never swept."""

from graph import receipts as receipts_mod
from graph.delta import Delta
from graph.extract import GraphData
from graph.receipts import (HONEST_HOME, ONLY_HOME, READABLE,
                            SOURCE_GONE, UNVERIFIABLE, render_report,
                            resolve_source, sentence_receipts, sweep)
from graph.report import ADVISORY


def storybook(tmp_path):
    """A little world: two prose sources on disk, citizens carrying
    quotes — one verified, one stale-with-home, one stale-only-home,
    one citing a vanished file, one citing a ruling, one row receipt."""
    (tmp_path / "tales").mkdir()
    (tmp_path / "tales" / "marsh.md").write_text(
        "# The Marsh\n\nThe Bog swallows the unwary at dusk.\n"
        "Wisps light the safe path for a price.\n", encoding="utf-8")
    g = GraphData()
    g.ensure_node("Terrain", "Bog",
                  from_text="The Bog swallows the unwary at dusk.",
                  source="tales/marsh.md § The Marsh")
    g.ensure_node("Beast", "Wisp",
                  description="Wisps trade light for trinkets.",
                  from_text="Wisps once traded light for trinkets.",
                  source="tales/marsh.md § The Marsh")
    g.ensure_node("Knack", "Fen Stride",
                  from_text="Fen Striders cross the deep mire unwetted.",
                  source="tales/marsh.md § The Marsh")
    g.ensure_node("Gem", "Chill",
                  from_text="Chill gems hum near open water.",
                  source="tales/vanished.md § Gems")
    g.ensure_node("Rite", "First Light",
                  from_text="The rite begins at first light.",
                  source="owner ruling at the harvest gate")
    g.ensure_node("Beast", "Ox", wear=3,
                  from_text="| Ox | 3 |",
                  source="tales/marsh.md § The Marsh")
    return g


def test_sentence_receipts_skip_rows():
    g = GraphData()
    g.ensure_node("Beast", "Ox", from_text="| Ox | 3 |")
    g.ensure_node("Terrain", "Bog", from_text="A quote of prose.")
    assert [(r.label, r.name) for r in sentence_receipts(g)] \
        == [("Terrain", "Bog")]


def test_resolve_source_speaks_three_voices(tmp_path):
    (tmp_path / "tales").mkdir()
    (tmp_path / "tales" / "marsh.md").write_text("x", encoding="utf-8")
    assert resolve_source(tmp_path, "tales/marsh.md § The Marsh") \
        == ("tales/marsh.md", READABLE)
    assert resolve_source(tmp_path, "tales/vanished.md § Gems") \
        == ("tales/vanished.md", SOURCE_GONE)
    assert resolve_source(tmp_path, "owner ruling at the harvest gate")[1] \
        == UNVERIFIABLE
    assert resolve_source(tmp_path, "")[1] == UNVERIFIABLE
    # a cite pointing outside the repo (a URL) is a record pointer, not
    # repo bytes — unverifiable by design, never "source gone"
    assert resolve_source(
        tmp_path, "ruling per tracker/thing/9 (https://example.com/x/9)"
    )[1] == UNVERIFIABLE
    # an annotated path still resolves: the parenthetical is a note
    assert resolve_source(tmp_path,
                          "tales/marsh.md (the dusk passages)") \
        == ("tales/marsh.md", READABLE)


def test_sweep_finds_stale_quotes_and_says_what_they_hid(tmp_path):
    result = sweep(tmp_path, storybook(tmp_path))
    by_name = {r.name: r for r in result.receipts}
    # verified: quote still in the source's bytes
    assert not by_name["Bog"].stale
    # stale with the fact living on in a prose prop — the receipt can go
    wisp = by_name["Wisp"]
    assert wisp.stale and wisp.beneath == HONEST_HOME
    # stale with nothing beneath — the receipt was the only home
    stride = by_name["Fen Stride"]
    assert stride.stale and stride.beneath == ONLY_HOME
    # a vanished source is its own voice, not "stale"
    assert by_name["Chill"].kind == SOURCE_GONE
    # a ruling-shaped source is counted, never checked
    assert by_name["First Light"].kind == UNVERIFIABLE
    # the row receipt never enters the sweep at all
    assert "Ox" not in by_name


def test_report_rolls_up_per_source_and_counts_the_quiet_classes(
        tmp_path):
    report = render_report(sweep(tmp_path, storybook(tmp_path)))
    assert "5 carried quotes: 1 verified · 2 stale · 1 source-gone · " \
           "1 unverifiable by design" in report
    assert "## tales/marsh.md — 2 stale quotes" in report
    assert "the receipt can retire" in report
    assert "intake debt" in report
    assert "Sources that no longer resolve" in report
    assert "unverifiable by design and not checked" in report


def test_authoring_an_unfindable_quote_refuses_by_name(tmp_path):
    base = storybook(tmp_path)
    delta = Delta(nodes_added=[
        ("Beast", "Elk",
         {"from_text": "Elks command the river fords by right.",
          "source": "tales/marsh.md § The Marsh"})])
    verdicts = receipts_mod.receipt_verdicts(delta, base, tmp_path)
    assert [v.code for v in verdicts] == ["receipt-unverified"]
    assert "interpretation posing as evidence" in verdicts[0].message
    # the same authoring with a REAL quote passes
    fine = Delta(nodes_added=[
        ("Beast", "Elk",
         {"from_text": "Wisps light the safe path for a price.",
          "source": "tales/marsh.md § The Marsh"})])
    assert receipts_mod.receipt_verdicts(fine, base, tmp_path) == []


def test_unverifiable_and_missing_sources_never_refuse(tmp_path):
    base = storybook(tmp_path)
    delta = Delta(nodes_added=[
        ("Rite", "Last Light",
         {"from_text": "The rite ends at last light.",
          "source": "owner ruling at the harvest gate"}),
        ("Gem", "Ember",
         {"from_text": "Ember gems crack in the cold.",
          "source": "tales/vanished.md § Gems"})])
    assert receipts_mod.receipt_verdicts(delta, base, tmp_path) == []


def test_touching_a_citizen_with_a_stale_receipt_advises(tmp_path):
    base = storybook(tmp_path)
    delta = Delta(nodes_changed=[
        ("Beast", "Wisp", {"description": ("old", "new words")})])
    verdicts = receipts_mod.receipt_verdicts(delta, base, tmp_path)
    assert [v.code for v in verdicts] == ["receipt-stale"]
    assert verdicts[0].severity == ADVISORY
    assert HONEST_HOME.split(" — ")[0] in verdicts[0].message
    # touching a citizen whose quote still verifies says nothing
    quiet = Delta(nodes_changed=[
        ("Terrain", "Bog", {"defense_mod": (None, -2)})])
    assert receipts_mod.receipt_verdicts(quiet, base, tmp_path) == []


def test_a_rewritten_receipt_is_judged_as_authored(tmp_path):
    base = storybook(tmp_path)
    delta = Delta(nodes_changed=[
        ("Terrain", "Bog",
         {"from_text": ("The Bog swallows the unwary at dusk.",
                        "The Bog rewards the brave at dawn.")})])
    verdicts = receipts_mod.receipt_verdicts(delta, base, tmp_path)
    assert [v.code for v in verdicts] == ["receipt-unverified"]


def test_the_cli_sweeps_and_files_the_report(tmp_path, monkeypatch,
                                             capsys):
    from graph import export as export_mod
    from graph.__main__ import main
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    graph = storybook(tmp_path)
    export_mod.write_export(graph, tmp_path / "graph" / "export")
    assert main(["receipts"]) == 0
    out = capsys.readouterr().out
    assert "2 stale" in out
    assert (tmp_path / "graph" / "reports" / "receipts.md").is_file()
