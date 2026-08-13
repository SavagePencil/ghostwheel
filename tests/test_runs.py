"""Run-scoped judgment graphs: pure logic — build, archive, round-trip,
promotion, and the anchored margin. No driver anywhere; the archive is
the record."""

import pytest

from graph.runs import (add_row, margin, new_run, parse_archive, promotion,
                        read_archive, render_margin, run_id, serialize,
                        write_archive)


def sample_run():
    run = new_run("Draft the chapter and flag anything uncertain.",
                  "2026-08-10 12:00:00")
    add_row(run, "question", "ambiguous ladder order",
            "Does the source order this ladder by rank or alphabetically?",
            decided_by="drafter-1")
    add_row(run, "answer", "ladder order read",
            "The source's own sequence is rank order.",
            decided_by="drafter-1", confidence="high",
            about="ambiguous ladder order")
    add_row(run, "opinion", "heading rewording",
            "The heading reads better in singular; changed with low risk.",
            decided_by="drafter-1", confidence="medium")
    return run


def test_run_id_is_deterministic_and_content_sensitive():
    a = run_id("brief text", "2026-08-10 12:00:00")
    assert a == run_id("brief text", "2026-08-10 12:00:00")
    assert a != run_id("other brief", "2026-08-10 12:00:00")
    assert a != run_id("brief text", "2026-08-10 12:00:01")
    assert a.startswith("20260810120000-")


def test_trace_round_trips_through_the_archive():
    run = sample_run()
    rebuilt = parse_archive(serialize(run))
    assert rebuilt == run
    # deterministic bytes: archives diff cleanly
    assert serialize(rebuilt) == serialize(run)


def test_archive_files_write_and_read_back(tmp_path):
    run = sample_run()
    written = write_archive(run, tmp_path)
    assert sorted(p.name for p in written) == ["judgments.jsonl", "run.json"]
    assert all(p.parent.name == run.id for p in written)
    assert read_archive(tmp_path / run.id) == run


def test_every_judgment_has_an_author_and_a_unique_name():
    run = sample_run()
    with pytest.raises(ValueError, match="no author"):
        add_row(run, "opinion", "anonymous", "text", decided_by="")
    with pytest.raises(ValueError, match="twice"):
        add_row(run, "opinion", "heading rewording", "again",
                decided_by="drafter-2")
    with pytest.raises(ValueError, match="only question, answer"):
        add_row(run, "verdict", "wrong kind", "text",
                decided_by="drafter-1")
    with pytest.raises(ValueError, match="no row by that name"):
        add_row(run, "answer", "orphan", "text", decided_by="drafter-1",
                about="never recorded")
    with pytest.raises(ValueError, match="empty brief"):
        new_run("   ", "2026-08-10 12:00:00")


def test_promotion_cites_the_run_and_is_archive_independent():
    run = sample_run()
    package = promotion(run, "heading rewording")
    # the full content plus the run id — and nothing pointing into the
    # archive, so canon survives archive loss (deletion tolerance)
    assert package == {
        "run": run.id, "kind": "opinion",
        "text": "The heading reads better in singular; changed with "
                "low risk.",
        "proposed_by": "drafter-1", "confidence": "medium"}
    assert "judgments.jsonl" not in str(package)
    with pytest.raises(ValueError, match="no row by that name"):
        promotion(run, "never recorded")


# -- the margin: span anchors, relocation, rendering -----------------------

ARTICLE = "Grade checks happen at chapter end. Knacks carry over to the next chapter."


def anchored_run():
    run = new_run("Draft the summary; anchor every doubt.",
                  "2026-08-10 15:00:00")
    add_row(run, "opinion", "knack wording",
            "Reworded for flow; low risk.", decided_by="drafter-1",
            confidence="high",
            anchor={"artifact": "f" * 64,
                    "start": ARTICLE.index("Knacks carry over to the next chapter."),
                    "end": len(ARTICLE),
                    "text": "Knacks carry over to the next chapter."})
    add_row(run, "question", "chapter scope",
            "Does 'chapter end' include the prologue?", decided_by="drafter-1",
            anchor={"artifact": "f" * 64,
                    "start": ARTICLE.index("Grade checks happen at chapter end."),
                    "end": len("Grade checks happen at chapter end."),
                    "text": "Grade checks happen at chapter end."})
    return run


def test_anchor_validation_refuses_bad_shapes():
    run = new_run("brief", "2026-08-10 15:00:00")
    cases = [
        ({"artifact": "f" * 64, "start": 0, "end": 4}, "missing text"),
        ({"artifact": "", "start": 0, "end": 4, "text": "spam"},
         "fingerprint is empty"),
        ({"artifact": "f" * 64, "start": 4, "end": 4, "text": ""},
         "quoted text is empty"),
        ({"artifact": "f" * 64, "start": 5, "end": 3, "text": "ab"},
         "not a sane span"),
        ({"artifact": "f" * 64, "start": 0, "end": 9, "text": "ab"},
         "quote disagree"),
    ]
    for anchor, why in cases:
        with pytest.raises(ValueError):
            add_row(run, "opinion", f"bad {why}", "text",
                    decided_by="a", anchor=anchor)
    assert run.rows == []  # nothing landed


def test_margin_orders_by_span_and_survives_the_round_trip():
    run = anchored_run()
    entries = margin(run, "f" * 64, ARTICLE)
    assert [row["name"] for row, _ in entries] == \
        ["chapter scope", "knack wording"]  # span order, not insertion
    rebuilt = parse_archive(serialize(run))
    assert margin(rebuilt, "f" * 64, ARTICLE) == entries


def test_quote_relocates_when_the_artifact_moves():
    run = anchored_run()
    edited = "NEW PREFACE. " + ARTICLE  # every offset now stale
    entries = margin(run, "f" * 64, edited)
    (_, span_a), (_, span_b) = entries
    assert edited[span_a[0]:span_a[1]] == \
        "Grade checks happen at chapter end."
    assert edited[span_b[0]:span_b[1]] == "Knacks carry over to the next chapter."
    # a quote that is gone entirely surfaces as span None, sorted last
    entries = margin(run, "f" * 64, "Unrelated text.")
    assert [span for _, span in entries] == [None, None]


def test_archive_refuses_a_lying_anchor(tmp_path):
    run = anchored_run()
    assert write_archive(run, tmp_path, {"f" * 64: ARTICLE})
    add_row(run, "opinion", "fabricated", "text", decided_by="a",
            anchor={"artifact": "f" * 64, "start": 0, "end": 5,
                    "text": "Never"})
    with pytest.raises(ValueError, match="does not appear"):
        write_archive(run, tmp_path, {"f" * 64: ARTICLE})


def test_render_margin_is_pinned():
    run = anchored_run()
    rendered = render_margin(ARTICLE, margin(run, "f" * 64, ARTICLE))
    assert rendered == (
        "Grade checks happen at chapter end.⟦1⟧ "
        "Knacks carry over to the next chapter.⟦2⟧\n"
        "\n---\n\n## Margin\n\n"
        "⟦1⟧ question by drafter-1: Does 'chapter end' include the prologue?\n"
        "    > Grade checks happen at chapter end.\n"
        "⟦2⟧ opinion by drafter-1, confidence high: Reworded for flow; "
        "low risk.\n"
        "    > Knacks carry over to the next chapter.\n")
