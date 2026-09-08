"""The glossary index reads CANON, not a from-sources build.

An index built anywhere else could not see citizens born by graph
rounds, so it would report every graph-born citizen's name as
unresolved forever — the sweep's backlog would inflate with every
round. The property under test: every citizen in the committed backup
resolves through the canon term index by its own name (Steps and
Outcomes are structure, not vocabulary, and are deliberately excluded).

The fixture canon is a self-contained storybook of Knacks and Terrains
constructed the way canon holds it — kernel seed, schema rows, citizens
— derived and written to an on-disk backup, then decorated with the
Judgment citizens (ruled-reject Decisions) a real round would land — so
these properties are exercised without reading any committed canon.
"""

import json

import pytest

from graph import export as export_mod
from graph.__main__ import canon_term_index, cmd_terms
from graph.extract import OUTCOME_LABEL, STEP_LABEL, derive, make_edge
from graph.kernel_migrate import fresh_kernel
from graph.ontology import ARCHETYPE_LABEL, ERROR, ontology_from_graph
from graph.restore import read_export

# A list-valued alias names BOTH its Knacks — a deliberately ambiguous
# surface that resolves in the glossary but must never resolve a data cell.
KNACKS = {"Swap (active)": "Active", "Swap (reactive)": "Reactive",
          "Kindle": "Active"}

# A 1:1 alias (Bog -> the canonical Terrain name) still resolves cells.
TERRAINS = {"Bog (per Depth)": 2, "Ridge": 1}

# Prose in a storybook-rules register: Grubfolk is a ruled reject (it must
# be suppressed where it appears); Kindle/Knack/Swap/Bog all resolve.
TALE = """\
# A Small Tale

The Grubfolk tend the marsh at dusk. A traveler learns the Kindle Knack.
The Swap lets a creature trade places. The Bog slows every traveler.
"""

KNACK_SPEC = {
    "concept": "Gizmo Concept",
    "catalog": {"knack_class": {"type": "text",
                                "doc": "active or reactive"}},
    "aliases": {"Swap": ["Swap (active)", "Swap (reactive)"]},
}
TERRAIN_SPEC = {
    "concept": "Gizmo Concept",
    "catalog": {"defense_mod": {"type": "int", "doc": "shift to defense"}},
    "aliases": {"Bog": "Bog (per Depth)"},
}
CHRONICLE_SPEC = {
    "values": ["docs/tale.md"],
    "fingerprint": True,
    "concept": "Provenance",
}

# Ruled rejects, landed as Judgment citizens (Decision rows carrying the
# machine key rejected_term): Grubfolk appears in the docs (suppressed on
# sight); Wibble and Thistlewick appear nowhere (stale — flagged for
# retirement).
RULED_REJECTS = ("Grubfolk", "Wibble", "Thistlewick")
SEEN_REJECT = "Grubfolk"


def _declare(graph, label, spec):
    graph.ensure_node(ARCHETYPE_LABEL, label,
                      spec_json=json.dumps(spec, sort_keys=True))
    graph.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                 ARCHETYPE_LABEL, "Ontology"))


def _build_terms_canon(root):
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "tale.md").write_text(TALE, encoding="utf-8")

    seed, findings = fresh_kernel(root)
    assert seed is not None, findings
    seed.ensure_node(ARCHETYPE_LABEL, "Gizmo Concept")
    seed.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL,
                                "Gizmo Concept", ARCHETYPE_LABEL, "Ontology"))
    seed.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL,
                                "Gizmo Concept", ARCHETYPE_LABEL, "Concept"))
    _declare(seed, "Knack", KNACK_SPEC)
    _declare(seed, "Terrain", TERRAIN_SPEC)
    _declare(seed, "Chronicle", CHRONICLE_SPEC)
    for name, knack_class in KNACKS.items():
        seed.ensure_node("Knack", name, knack_class=knack_class)
    for name, defense_mod in TERRAINS.items():
        seed.ensure_node("Terrain", name, defense_mod=defense_mod)
    seed.ensure_node("Chronicle", "docs/tale.md", fingerprint=True)
    # The Decision's NAME never embeds the ruled term — a reject rides as
    # the machine key on a generically-named ruling, so the term stays out
    # of the glossary's known vocabulary and is genuinely unresolved (then
    # suppressed) when it surfaces in prose.
    for index, term in enumerate(RULED_REJECTS, start=1):
        seed.nodes[("[Decision]", f"Glossary sitting: ruling {index}")] = \
            {"rejected_term": term}

    graph, derive_findings = derive(ontology_from_graph(seed, root), seed)
    assert not [f for f in derive_findings if f.severity == ERROR], \
        derive_findings
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
