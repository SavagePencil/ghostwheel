"""The birth ceremony: `init` seeds a knowledge base born graph-native —
a committed backup holding the kernel's schema stratum alone, no
ontology.yaml, no sources, no database. Everything else grows through
gated rounds. Like `docs`, it opens no existing knowledge base: it must
work from a bare directory with no base in sight.
"""

from graph.__main__ import find_base_dir, main
from graph.ontology import (METAONTOLOGY_PATH, SCHEMA_LABELS,
                            is_derived_edge, load_metaontology,
                            ontology_from_graph)
from graph.restore import read_export


def _no_base_anywhere(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GHOSTWHEEL_BASE", raising=False)


def _export_bytes(base):
    export = base / "graph" / "export"
    return {p.name: p.read_bytes() for p in sorted(export.iterdir())}


def test_init_seeds_a_kernel_only_backup(capsys, tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    base = tmp_path / "newborn"
    assert main(["init", str(base)]) == 0
    graph = read_export(base / "graph" / "export")
    assert graph.nodes and graph.edges
    # The seed is the schema stratum alone — the shape a schema-only
    # branch cut is born from: schema citizens, no derived edges.
    assert all(label in SCHEMA_LABELS for (label, _name) in graph.nodes)
    assert not any(is_derived_edge(edge) for edge in graph.edges)


def test_init_defaults_to_the_current_directory(tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "graph" / "export" / "nodes.jsonl").is_file()


def test_the_seed_reconstructs_the_kernel_and_nothing_else(
        tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    base = tmp_path / "newborn"
    assert main(["init", str(base)]) == 0
    graph = read_export(base / "graph" / "export")
    ontology = ontology_from_graph(graph, base)
    kernel, meta, _findings = load_metaontology(METAONTOLOGY_PATH)
    assert ontology.kernel_names == set(kernel)
    assert set(ontology.concepts) == set(kernel)
    assert not ontology.nodes  # the project layer is born empty
    assert ontology.meta.get("version") == meta.get("version")


def test_init_is_deterministic(tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    first, second = tmp_path / "one", tmp_path / "two"
    assert main(["init", str(first)]) == 0
    assert main(["init", str(second)]) == 0
    assert _export_bytes(first) == _export_bytes(second)


def test_base_dir_discovery_finds_the_newborn(tmp_path, monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    base = tmp_path / "newborn"
    assert main(["init", str(base)]) == 0
    monkeypatch.chdir(base)
    assert find_base_dir() == base


def test_init_refuses_an_existing_knowledge_base(capsys, tmp_path,
                                                 monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    base = tmp_path / "newborn"
    assert main(["init", str(base)]) == 0
    before = _export_bytes(base)
    assert main(["init", str(base)]) == 1
    err = capsys.readouterr().err
    assert "already lives there" in err
    assert _export_bytes(base) == before  # the backup is untouched


def test_init_refuses_a_bootstrap_style_base(capsys, tmp_path,
                                             monkeypatch):
    _no_base_anywhere(monkeypatch, tmp_path)
    base = tmp_path / "from-sources"
    (base / "graph").mkdir(parents=True)
    (base / "graph" / "ontology.yaml").write_text("nodes: {}\n",
                                                  encoding="utf-8")
    assert main(["init", str(base)]) == 1
    err = capsys.readouterr().err
    assert "ontology.yaml" in err
    assert not (base / "graph" / "export").exists()
