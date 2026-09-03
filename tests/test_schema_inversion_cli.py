"""Track B of the schema inversion: the round machinery runs from the
graph's committed backup, not ontology.yaml.

Proof strategy. The DB-free commands (export-lensed, generate, terms) run
end to end against a fixture backup with `load_ontology` POISONED — if any
of them still reached for the YAML schema, the poison would fire. The
DB-bound commands (rederive, delta, canonize) cannot run without a live
Neo4j in the unit suite, so their repoint is proven by source inspection:
they name `ontology_from_graph` and never `load_ontology`. The parity
paths (roundtrip, render-tables) read the graph too: the render mappings
they consume ride each label row beside its spec. The canonize
version-stamp wiring is proven present and correctly ordered.

The fixture backup is a from-sources build of a small imaginary corpus —
a Gem catalog, a cited Program, a prose Chronicle — decorated with the
Judgment citizens (ruled-reject Decisions) and a masking Visibility Class
a real round would land, then serialized to an on-disk backup. No
committed canon is read.
"""

import inspect
from pathlib import Path

import pytest

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.__main__ import (canon_term_index, cmd_export_lensed, cmd_generate,
                            cmd_terms)
from graph.extract import extract
from graph.ontology import ERROR, load_ontology

# -- the fixture backup ----------------------------------------------------

GEMS = """\
Gem,Power
Ruby,3
Onyx,5
"""

# A cited procedure: a name and a description, everything else open — the
# lightest Completeness level, enough for `generate` to render.
PROCEDURE = """\
procedure: The Awakening of a Gryphon
completeness: cited
description: A cited stub — the tale names it but its innards live elsewhere.
"""

# Prose: Grubfolk is a ruled reject (suppressed on sight); Gem resolves to
# its catalog label.
TALE = """\
# A Small Tale

The Grubfolk tend the marsh at dusk. A Gem glows softly in the dark.
"""

ONTOLOGY = """\
version: 1
concepts:
  Gizmo Concept: { instance_of: Concept }
nodes:
  Gem:
    source: data/gems.csv
    key: Gem
    concept: Gizmo Concept
    catalog:
      power: { type: int, doc: "oomph" }
    properties:
      power: { column: Power }
  Program:
    source: data/procedures/awakening.yaml
    reader: procedure_yaml
    concept: Procedure
  Chronicle:
    values: [docs/tale.md]
    fingerprint: true
    concept: Provenance
"""

RULED_REJECTS = ("Grubfolk", "Wibble", "Thistlewick")
# A masking Visibility Class over the Gem label — what `export --mask`
# hides in a lens-scoped materialization.
MASK_CLASS = "hidden"


def _build_canon(root):
    (root / "data" / "procedures").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "graph").mkdir(parents=True, exist_ok=True)
    (root / "data" / "gems.csv").write_text(GEMS, encoding="utf-8")
    (root / "data" / "procedures" / "awakening.yaml").write_text(
        PROCEDURE, encoding="utf-8")
    (root / "docs" / "tale.md").write_text(TALE, encoding="utf-8")
    (root / "graph" / "ontology.yaml").write_text(ONTOLOGY, encoding="utf-8")

    ontology, findings = load_ontology(root / "graph" / "ontology.yaml", root)
    assert ontology is not None, findings
    assert not [f for f in findings if f.severity == ERROR], findings
    graph, extract_findings = extract(ontology)
    assert not [f for f in extract_findings if f.severity == ERROR], \
        extract_findings

    # The masking Visibility Class rides as a kernel citizen (the lens reads
    # its declarations from the graph, not a file).
    graph.nodes[("Visibility Class", MASK_CLASS)] = {
        "kind": "masking", "labels": ["Gem"]}
    # Ruled rejects as Judgment citizens — the machine key on a
    # generically-named ruling (the term is kept out of citizen names so it
    # stays genuinely unresolved when it surfaces in prose).
    for index, term in enumerate(RULED_REJECTS, start=1):
        graph.nodes[("Decision", f"Glossary sitting: ruling {index}")] = \
            {"rejected_term": term}
    export_mod.write_export(graph, root / "graph" / "export")
    return root


@pytest.fixture(scope="module")
def canon(tmp_path_factory):
    return _build_canon(tmp_path_factory.mktemp("inversion_canon"))


def _poison_load_ontology(monkeypatch):
    """Make any post-bootstrap reach for ontology.yaml an explicit failure."""
    def boom(*args, **kwargs):
        raise AssertionError(
            "load_ontology was called — this command must reconstruct the "
            "schema from the graph, not read ontology.yaml")
    monkeypatch.setattr("graph.ontology.load_ontology", boom)


# -- the DB-free commands run from the backup alone ------------------------


def test_export_lensed_runs_from_the_graph(canon, monkeypatch, tmp_path):
    _poison_load_ontology(monkeypatch)
    out = tmp_path / "runtime"
    assert cmd_export_lensed(canon, [MASK_CLASS], str(out)) == 0
    assert (out / "nodes.jsonl").exists()


def test_generate_runs_from_the_graph(canon, monkeypatch, capsys):
    _poison_load_ontology(monkeypatch)
    assert cmd_generate(canon, "The Awakening of a Gryphon") == 0
    assert capsys.readouterr().out.strip()


def test_terms_runs_from_the_graph(canon, monkeypatch, capsys):
    _poison_load_ontology(monkeypatch)
    assert cmd_terms(canon) == 0
    capsys.readouterr()  # drain


def test_canon_term_index_builds_from_the_graph(canon, monkeypatch):
    _poison_load_ontology(monkeypatch)
    extractor, error = canon_term_index(canon)
    assert error is None and extractor is not None, error
    assert extractor.term_index


# -- rejected terms are Judgment citizens (the bridge is retired) ----------


def test_rejected_terms_flow_from_the_decision_rows(canon):
    # The migration round landed one ruled-reject Decision per term;
    # the reconstructed ontology reads them from canon — no YAML.
    from graph.ontology import ontology_from_graph
    from graph.restore import read_export
    graph = read_export(canon / "graph" / "export")
    rejects = set(ontology_from_graph(graph, canon).rejected_terms)
    assert set(RULED_REJECTS) <= rejects


def test_terms_suppresses_ruled_rejects_with_no_yaml_read(canon, monkeypatch,
                                                          capsys):
    # Poison the schema loader AND still suppress the ruled rejects:
    # the suppression rides the Decision rows on canon.
    _poison_load_ontology(monkeypatch)
    assert cmd_terms(canon) == 0
    out = capsys.readouterr().out
    for ruled_reject in RULED_REJECTS:
        assert f"  {ruled_reject} " not in out


# -- the DB-bound repoints, proven by source inspection --------------------

REPOINTED = ("cmd_rederive", "cmd_delta", "cmd_canonize",
             "cmd_export_lensed", "cmd_generate", "canon_term_index",
             # the parity paths joined once the render mappings gained
             # their canon home (a label row's rendered_views_json)
             "cmd_roundtrip", "cmd_render_tables")


@pytest.mark.parametrize("fn_name", REPOINTED)
def test_repointed_commands_read_the_graph_not_yaml(fn_name):
    src = inspect.getsource(getattr(main_mod, fn_name))
    assert "ontology_from_graph" in src, fn_name
    assert "load_ontology" not in src, (
        f"{fn_name} still reads ontology.yaml via load_ontology")



# -- the canonize version-stamp wiring is present and ordered --------------


def test_canonize_stamps_the_version_after_stitch_before_write():
    src = inspect.getsource(main_mod.cmd_canonize)
    assert "next_log_sequence" in src and "stamp_ontology_anchor" in src
    stitch = src.index("apply_stitch")
    stamp = src.index("stamp_ontology_anchor(new_graph")
    write = src.index("load_mod.load(new_graph")
    # verify-all before apply-any: the stamp lands after the stitch and
    # before anything is written to the database.
    assert stitch < stamp < write


def test_corpus_grammar_hook_loads_registrations(tmp_path, capsys):
    # A knowledge base supplies its grammars via a grammars.py at its
    # root — the hook imports it and @register fills the registry. A
    # broken module refuses by name without killing the CLI.
    from graph import grammars
    from graph.__main__ import load_corpus_grammars
    (tmp_path / "grammars.py").write_text(
        "from graph.grammars import register\n"
        "@register('leaf_charts')\n"
        "def leaf_charts(rows):\n"
        "    return [], []\n", encoding="utf-8")
    load_corpus_grammars(tmp_path)
    assert grammars.get_optional("leaf_charts") is not None
    del grammars._REGISTRY["leaf_charts"]

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "grammars.py").write_text("raise ValueError('boom')\n",
                                        encoding="utf-8")
    load_corpus_grammars(broken)
    err = capsys.readouterr().err
    assert "Attempted to load the corpus grammar module" in err
    assert "boom" in err


def test_find_base_dir_resolves_a_kb_from_cwd_env_and_refusal(tmp_path,
                                                              monkeypatch):
    # An installed engine lives apart from any knowledge base: it must
    # find the opened base from the environment or by walking up from
    # the working directory — and refuse by name from nowhere.
    from graph.__main__ import find_base_dir
    kb = tmp_path / "kb"
    (kb / "graph" / "export").mkdir(parents=True)
    nested = kb / "docs" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)
    assert find_base_dir() == kb.resolve()

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("GHOSTWHEEL_BASE", str(kb))
    assert find_base_dir() == kb.resolve()

    monkeypatch.setenv("GHOSTWHEEL_BASE", str(elsewhere))
    with pytest.raises(SystemExit, match="not a knowledge base root"):
        find_base_dir()

    monkeypatch.delenv("GHOSTWHEEL_BASE")
    with pytest.raises(SystemExit, match="no ancestor carries"):
        find_base_dir()
