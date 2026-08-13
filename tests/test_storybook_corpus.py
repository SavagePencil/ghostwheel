"""The storybook corpus: the engine proving, on every commit, that it
loads, extracts, comprehends, and round-trips a corpus with zero
built-in vocabulary of its own — the corpus teaches the engine every
word it uses, and the engine reads the rest from declarations."""

import textwrap
from pathlib import Path

from graph.comprehension import read_artifact
from graph.extract import extract
from graph.ontology import ERROR, load_ontology
from graph.roundtrip import render_report, run

STORYBOOK = Path(__file__).resolve().parent / "fixtures" / "storybook"


def load_storybook():
    ontology, findings = load_ontology(STORYBOOK / "ontology.yaml", STORYBOOK)
    assert ontology is not None, findings
    graph, extract_findings = extract(ontology)
    return graph, findings + extract_findings


def test_storybook_loads_with_zero_errors():
    graph, findings = load_storybook()
    assert not [f for f in findings if f.severity == ERROR], [
        f.detail for f in findings if f.severity == ERROR]
    # citizens, implicit places, fingerprints, and the scheme all arrive
    assert graph.nodes[("Character", "Pip")]["temperament"] == "curious"
    assert ("Place", "The Hollow Oak") in graph.nodes
    assert graph.nodes[("Artifact", "docs/tale.md")]["fingerprint"]
    assert graph.nodes[("Archetype", "Page")].get("recursive") is True
    assert any(e.type == "LIVES_IN" and e.to_name == "Lantern Bay"
               for e in graph.edges)


def test_storybook_answers_what_built_it():
    # the corpus self-describes: same kernel seed, its own ontology
    # fingerprint
    graph, _ = load_storybook()
    meta = graph.nodes[("Archetype", "Metaontology")]
    proj = graph.nodes[("Archetype", "Ontology")]
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
