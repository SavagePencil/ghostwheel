"""The glossary index reads CANON, not the from-sources build.

The from-sources scaffolding cannot see citizens born by graph rounds,
so an index built from it reports every graph-born citizen's name as
unresolved forever — the sweep's backlog inflates with every round.
The property under test: every citizen in the committed backup resolves
through the canon term index by its own name (Steps and Outcomes are
structure, not vocabulary, and are deliberately excluded).

The fixture canon is a self-contained storybook of Knacks and Terrains
built from sources into an on-disk backup, then decorated with the
Judgment citizens (ruled-reject Decisions) a real round would land — so
these properties are exercised without reading any committed canon.
"""

from pathlib import Path

import pytest

from graph import export as export_mod
from graph.__main__ import canon_term_index, cmd_terms
from graph.extract import OUTCOME_LABEL, STEP_LABEL, extract
from graph.ontology import ERROR, load_ontology
from graph.restore import read_export

# A list-valued alias names BOTH its Knacks — a deliberately ambiguous
# surface that resolves in the glossary but must never resolve a data cell.
KNACKS = """\
Knack,Class
Swap (active),Active
Swap (reactive),Reactive
Kindle,Active
"""

# A 1:1 alias (Bog -> the canonical Terrain name) still resolves cells.
TERRAIN = """\
Terrain,Defense
Bog (per Depth),2
Ridge,1
"""

# Prose in a storybook-rules register: Grubfolk is a ruled reject (it must
# be suppressed where it appears); Kindle/Knack/Swap/Bog all resolve.
TALE = """\
# A Small Tale

The Grubfolk tend the marsh at dusk. A traveler learns the Kindle Knack.
The Swap lets a creature trade places. The Bog slows every traveler.
"""

ONTOLOGY = """\
version: 1
concepts:
  Gizmo Concept: { instance_of: Concept }
nodes:
  Knack:
    source: data/knacks.csv
    key: Knack
    concept: Gizmo Concept
    catalog:
      knack_class: { type: text, doc: "active or reactive" }
    properties:
      knack_class: { column: Class }
    aliases:
      Swap: [Swap (active), Swap (reactive)]
  Terrain:
    source: data/terrain.csv
    key: Terrain
    concept: Gizmo Concept
    catalog:
      defense_mod: { type: int, doc: "shift to defense" }
    properties:
      defense_mod: { column: Defense }
    aliases:
      Bog: Bog (per Depth)
  Chronicle:
    values: [docs/tale.md]
    fingerprint: true
    concept: Provenance
"""

# Ruled rejects, landed as Judgment citizens (Decision rows carrying the
# machine key rejected_term): Grubfolk appears in the docs (suppressed on
# sight); Wibble and Thistlewick appear nowhere (stale — flagged for
# retirement).
RULED_REJECTS = ("Grubfolk", "Wibble", "Thistlewick")
SEEN_REJECT = "Grubfolk"


def _build_terms_canon(root):
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "graph").mkdir(parents=True, exist_ok=True)
    (root / "data" / "knacks.csv").write_text(KNACKS, encoding="utf-8")
    (root / "data" / "terrain.csv").write_text(TERRAIN, encoding="utf-8")
    (root / "docs" / "tale.md").write_text(TALE, encoding="utf-8")
    (root / "graph" / "ontology.yaml").write_text(ONTOLOGY, encoding="utf-8")

    ontology, findings = load_ontology(root / "graph" / "ontology.yaml", root)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR], \
        extract_findings
    # The Decision's NAME never embeds the ruled term — a reject rides as
    # the machine key on a generically-named ruling, so the term stays out
    # of the glossary's known vocabulary and is genuinely unresolved (then
    # suppressed) when it surfaces in prose.
    for index, term in enumerate(RULED_REJECTS, start=1):
        graph.nodes[("[Decision]", f"Glossary sitting: ruling {index}")] = \
            {"rejected_term": term}
    export_mod.write_export(graph, root / "graph" / "export")
    return root


@pytest.fixture(scope="module")
def canon(tmp_path_factory):
    return _build_terms_canon(tmp_path_factory.mktemp("terms_canon"))


def test_canon_term_index_builds(canon):
    extractor, error = canon_term_index(canon)
    assert error is None and extractor is not None, error
    assert extractor.term_index


def test_every_canon_citizen_resolves_by_name(canon):
    extractor, error = canon_term_index(canon)
    assert error is None and extractor is not None, error
    index = extractor.term_index
    missing = [
        (label, name)
        for (label, name) in read_export(canon / "graph" / "export").nodes
        if label not in (STEP_LABEL, OUTCOME_LABEL)
        and (label, name) not in index.get(name, set())
    ]
    assert not missing, (
        "canon citizens invisible to the glossary index: "
        f"{missing[:10]}")


def test_list_alias_resolves_to_every_target(canon):
    # "Swap" names BOTH its Knacks — a list-valued alias lands each target
    # in the index under the one surface.
    extractor, error = canon_term_index(canon)
    assert error is None and extractor is not None, error
    assert {("Knack", "Swap (active)"), ("Knack", "Swap (reactive)")} \
        <= extractor.term_index.get("Swap", set())


def test_list_alias_refuses_csv_cells(canon):
    # A deliberately ambiguous alias may never resolve a data cell — the
    # cell keeps its raw name for the dangling-reference check.
    extractor, error = canon_term_index(canon)
    assert error is None and extractor is not None, error
    assert extractor.resolve_alias("Knack", "Swap") == "Swap"
    # 1:1 aliases still resolve cells as before.
    assert extractor.resolve_alias(
        "Terrain", "Bog") == "Bog (per Depth)"


def test_rejected_terms_suppressed_and_stale_flagged(canon, capsys):
    # Ruled rejects vanish from the sweep; a reject that no longer
    # appears anywhere is flagged for retirement, never silently kept.
    assert cmd_terms(canon) == 0
    out = capsys.readouterr().out
    for ruled_reject in RULED_REJECTS:
        assert f"  {ruled_reject} " not in out
    assert "ruled reject(s) suppressed" in out
    # the two rejects that appear nowhere are flagged as stale
    assert "no longer appear in the docs" in out
    assert "Wibble" in out and "Thistlewick" in out
