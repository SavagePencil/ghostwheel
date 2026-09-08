"""The storybook corpus: the engine proving, on every commit, that it
carries, re-derives, comprehends, and round-trips a corpus with zero
built-in vocabulary of its own — the corpus's canon teaches the engine
every word it uses, and the engine reads the rest from the committed
backup's own declarations."""

import textwrap
from pathlib import Path

from graph.comprehension import read_artifact
from graph.extract import derive
from graph.ontology import ERROR, ontology_from_graph
from graph.roundtrip import render_report, run
from tests.test_branch import build_canon

STORYBOOK = Path(__file__).resolve().parent / "fixtures" / "storybook"


def test_storybook_canon_rederives_with_zero_errors():
    canon = build_canon()
    _, findings = derive(ontology_from_graph(canon, STORYBOOK), canon)
    assert not [f for f in findings if f.severity == ERROR], [
        f.detail for f in findings if f.severity == ERROR]
    # citizens, implicit places, fingerprints, and the scheme all arrive
    assert canon.nodes[("Character", "Pip")]["temperament"] == "curious"
    assert ("Place", "The Hollow Oak") in canon.nodes
    assert canon.nodes[("[Artifact]", "docs/tale.md")]["fingerprint"]
    assert canon.nodes[("Archetype", "Page")].get("recursive") is True
    assert any(e.type == "LIVES_IN" and e.to_name == "Lantern Bay"
               for e in canon.edges)


def test_storybook_answers_what_built_it():
    # the corpus self-describes: same kernel seed, its own ontology
    # fingerprint
    canon = build_canon()
    meta = canon.nodes[("Archetype", "Metaontology")]
    proj = canon.nodes[("Archetype", "Ontology")]
    assert "." in str(meta["version"]) and len(meta["fingerprint"]) == 64
    assert len(proj["fingerprint"]) == 64
    assert proj["fingerprint"] != meta["fingerprint"]


def test_storybook_comprehends_with_nesting_and_classes():
    data = (STORYBOOK / "docs" / "tale.md").read_bytes()
    reading = read_artifact(data, title="tale.md")
    by_heading = {s["heading"]: s for s in reading.sections}
    door = by_heading["The Knot Door"]
    assert door["parent"] == by_heading["The Hollow Oak"]["id"]
    bay = by_heading["Lantern Bay"]
    assert [span["class"] for span in bay["spans"]] == \
        ["rule-prose", "table"]


def test_storybook_roundtrips_a_reorganized_faithful_draft(tmp_path):
    draft = tmp_path / "draft.md"
    draft.write_text(textwrap.dedent("""\
        # Tales, Retold

        Maren tends the lamps at Lantern Bay. Pip lives inside The
        Hollow Oak. Every lamp is lit before dark. The oak creaks when
        the wind turns. The door opens only for the curious. A small
        tale for a small corpus.

        | Who   | Where          | Nature    |
        |-------|----------------|-----------|
        | Pip   | The Hollow Oak | curious   |
        | Maren | Lantern Bay    | steadfast |
        """), encoding="utf-8")
    result = run(STORYBOOK, "docs/tale.md", draft)
    assert result.passed, render_report(result)


def test_storybook_roundtrip_catches_a_lost_character(tmp_path):
    draft = tmp_path / "draft.md"
    draft.write_text(textwrap.dedent("""\
        # Tales, Retold

        Pip lives inside The Hollow Oak. Every lamp is lit before dark.
        The oak creaks when the wind turns. The door opens only for the
        curious. A small tale for a small corpus.

        | Who | Where          | Nature  |
        |-----|----------------|---------|
        | Pip | The Hollow Oak | curious |
        """), encoding="utf-8")
    result = run(STORYBOOK, "docs/tale.md", draft)
    assert not result.passed
    report = render_report(result)
    assert "Maren" in report  # the lost character is named, twice over
