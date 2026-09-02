"""Kernel migration: the ceremony's other limb. A canon's committed
backup embeds the kernel schema stratum, and when the installed kernel
moves, ``kernel-migrate`` splices the fresh stratum over canon's — the
project stratum and the ground untouched, removals that would orphan
project references refused by name, and the applied migration a
first-class round: a real delta, archived with its inverse, chained in
the event log. The skew finding (``kernel_skew``) is what a consuming
knowledge base hears when its canon was built with a kernel the
installed engine no longer carries: mutating commands refuse on skew,
read commands warn and proceed.
"""

import yaml

from graph import export as export_mod
from graph import kernel_migrate as km
from graph.__main__ import cmd_kernel_migrate, cmd_rederive, cmd_init
from graph.extract import make_edge, strip_derived
from graph.ontology import ARCHETYPE_LABEL, METAONTOLOGY_PATH
from graph.proposal import parse_delta, read_applied_log, verify_applied_log
from graph.restore import read_export

PROJECT_CONCEPT = "Imaginary Widget"
PROJECT_DOC = "Project vocabulary an ordinary gated round declared."


def seeded_kb(tmp_path):
    """A knowledge base born graph-native at the installed kernel, grown
    by one project-layer concept that cites kernel vocabulary."""
    base_dir = tmp_path / "kb"
    base_dir.mkdir()
    assert cmd_init(base_dir) == 0
    export_dir = base_dir / "graph" / "export"
    graph = read_export(export_dir)
    graph.ensure_node(ARCHETYPE_LABEL, PROJECT_CONCEPT, doc=PROJECT_DOC)
    graph.edges.append(make_edge(
        "DECLARED_IN", ARCHETYPE_LABEL, PROJECT_CONCEPT,
        ARCHETYPE_LABEL, "Ontology"))
    graph.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, PROJECT_CONCEPT,
        ARCHETYPE_LABEL, "Concept"))
    export_mod.write_export(graph, export_dir)
    return base_dir


def modified_kernel(tmp_path, version="0.99.0", add=None, drop=None):
    """A next-kernel metaontology: the packaged one with a version bump
    and optional vocabulary changes, written where a test can point."""
    doc = yaml.safe_load(METAONTOLOGY_PATH.read_text(encoding="utf-8"))
    doc["version"] = version
    if add:
        doc["concepts"][add] = "A vocabulary entry minted for this test."
    if drop:
        doc["concepts"].pop(drop)
    path = tmp_path / "metaontology-next.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


def export_bytes(base_dir):
    export_dir = base_dir / "graph" / "export"
    return {p.name: p.read_bytes() for p in sorted(export_dir.iterdir())}


def fake_database(monkeypatch):
    """Stand-in for the live database: load stores the graph, dump
    returns it — the write tail's round-trip check sees byte-identity."""
    store = {}

    def load(graph, config):
        store["graph"] = graph
        return {"loaded_nodes": len(graph.nodes),
                "loaded_edges": len(graph.edges)}

    monkeypatch.setattr("graph.load.load", load)
    monkeypatch.setattr("graph.restore.dump_db",
                        lambda config: store["graph"])
    monkeypatch.setattr("graph.workspace.stamp", lambda *a, **kw: None)


def test_a_matching_kernel_has_nothing_to_migrate(tmp_path, capsys):
    base_dir = seeded_kb(tmp_path)
    before = export_bytes(base_dir)
    assert cmd_kernel_migrate(base_dir) == 0
    assert "nothing to migrate" in capsys.readouterr().out
    assert export_bytes(base_dir) == before


def test_the_dry_run_reports_the_splice_and_writes_nothing(tmp_path,
                                                          capsys):
    base_dir = seeded_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    before = export_bytes(base_dir)
    assert cmd_kernel_migrate(base_dir, metaontology_path=nxt) == 0
    out = capsys.readouterr().out
    assert "-> 0.99.0" in out
    assert "Minted Kernel Concept" in out
    assert "orphan check: clean" in out
    assert "Dry run: nothing written" in out
    assert export_bytes(base_dir) == before


def test_the_splice_moves_only_the_kernel_stratum(tmp_path):
    base_dir = seeded_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    ground = strip_derived(read_export(base_dir / "graph" / "export"))
    seed, _findings = km.fresh_kernel(base_dir, nxt)
    old_nodes, _old_edges = km.kernel_stratum(ground)
    new_nodes, new_edges = km.kernel_stratum(seed)
    spliced, _carried = km.splice(ground, set(old_nodes), new_nodes,
                                  new_edges)
    # the project stratum rides through untouched
    key = (ARCHETYPE_LABEL, PROJECT_CONCEPT)
    assert spliced.nodes[key] == ground.nodes[key]
    project_edges = [e for e in ground.edges
                     if e.from_name == PROJECT_CONCEPT]
    assert all(e in spliced.edges for e in project_edges)
    # the fresh stratum is in, with the anchor at the new identity
    assert (ARCHETYPE_LABEL, "Minted Kernel Concept") in spliced.nodes
    anchor = spliced.nodes[(ARCHETYPE_LABEL, km.KERNEL_ANCHOR)]
    assert anchor["version"] == "0.99.0"
    # and the delta names nothing outside the stratum
    from graph.delta import diff
    changes = diff(ground, spliced)
    assert km.leaks(changes, set(old_nodes) | set(new_nodes)) == []
    changed = {name for _label, name, _c in changes.nodes_changed}
    assert km.KERNEL_ANCHOR in changed
    assert PROJECT_CONCEPT not in changed


def test_an_orphaning_removal_refuses_by_name(tmp_path, capsys):
    base_dir = seeded_kb(tmp_path)
    export_dir = base_dir / "graph" / "export"
    graph = read_export(export_dir)
    graph.edges.append(make_edge(
        "INSTANCE_OF", ARCHETYPE_LABEL, PROJECT_CONCEPT,
        ARCHETYPE_LABEL, "Theme"))
    export_mod.write_export(graph, export_dir)
    nxt = modified_kernel(tmp_path, drop="Theme")
    before = export_bytes(base_dir)
    assert cmd_kernel_migrate(base_dir, apply=True,
                              metaontology_path=nxt) == 1
    err = capsys.readouterr().err
    assert "would orphan project references" in err
    assert f"'{PROJECT_CONCEPT}'" in err and "'Theme'" in err
    assert "gated round first" in err
    assert export_bytes(base_dir) == before


def test_a_clean_removal_migrates_without_refusal(tmp_path, capsys):
    base_dir = seeded_kb(tmp_path)
    nxt = modified_kernel(tmp_path, drop="Theme")
    assert cmd_kernel_migrate(base_dir, metaontology_path=nxt) == 0
    out = capsys.readouterr().out
    assert "leaving (1): Theme" in out


def test_the_applied_migration_is_a_chained_archived_round(
        tmp_path, capsys, monkeypatch):
    base_dir = seeded_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    fake_database(monkeypatch)
    assert cmd_kernel_migrate(base_dir, apply=True,
                              metaontology_path=nxt) == 0
    out = capsys.readouterr().out
    assert "Migrated to kernel 0.99.0" in out
    # the backup now carries the fresh stratum, project layer intact
    after = read_export(base_dir / "graph" / "export")
    assert (ARCHETYPE_LABEL, "Minted Kernel Concept") in after.nodes
    assert after.nodes[(ARCHETYPE_LABEL, PROJECT_CONCEPT)]["doc"] \
        == PROJECT_DOC
    anchor = after.nodes[(ARCHETYPE_LABEL, km.KERNEL_ANCHOR)]
    assert anchor["version"] == "0.99.0"
    # the event log chained one verifiable entry
    entries = read_applied_log(base_dir)
    assert len(entries) == 1
    assert verify_applied_log(base_dir) == []
    # the round is archived whole: delta, inverse, applied record
    _seq, delta_hash, _before, _after_id, _prev, _chain = entries[0]
    archive = base_dir / "graph" / "proposals" / delta_hash[:12]
    delta = parse_delta((archive / "delta.json").read_text())
    assert ("Minted Kernel Concept"
            in {name for _l, name, _p in delta.nodes_added})
    inverse = parse_delta((archive / "inverse.json").read_text())
    assert ("Minted Kernel Concept"
            in {name for _l, name, _p in inverse.nodes_removed})
    import json
    applied = json.loads((archive / "applied.json").read_text())
    assert applied["applied"] == "kernel-migration"
    assert applied["kernel"] == "0.99.0"
    # and a second run finds nothing left to do
    assert cmd_kernel_migrate(base_dir, metaontology_path=nxt) == 0
    assert "nothing to migrate" in capsys.readouterr().out


def test_an_in_flight_round_blocks_the_apply(tmp_path, capsys):
    base_dir = seeded_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    pin = base_dir / "graph" / "proposals" / "current" / "base.json"
    pin.parent.mkdir(parents=True)
    pin.write_text("{}")
    assert cmd_kernel_migrate(base_dir, apply=True,
                              metaontology_path=nxt) == 1
    assert "a round is in flight" in capsys.readouterr().err


def test_the_skew_finding_speaks_only_on_skew(tmp_path):
    base_dir = seeded_kb(tmp_path)
    graph = read_export(base_dir / "graph" / "export")
    assert km.kernel_skew(graph) is None
    anchor = graph.nodes[(ARCHETYPE_LABEL, km.KERNEL_ANCHOR)]
    kernel_version = anchor["version"]
    # a canon built with an older kernel
    anchor["version"] = "0.0.1"
    message = km.kernel_skew(graph)
    assert message is not None
    assert "built with kernel 0.0.1" in message
    assert f"carries kernel {kernel_version}" in message
    assert km.MIGRATE_COMMAND in message
    # same version, different content: a broken kernel ceremony
    anchor["version"] = kernel_version
    anchor["fingerprint"] = "not-the-installed-fingerprint"
    assert "broken kernel ceremony" in (km.kernel_skew(graph) or "")
    # no anchor at all: unverifiable, and the finding says so
    del graph.nodes[(ARCHETYPE_LABEL, km.KERNEL_ANCHOR)]
    assert "no Metaontology anchor" in (km.kernel_skew(graph) or "")


def test_mutating_commands_refuse_on_skew(tmp_path, capsys):
    base_dir = seeded_kb(tmp_path)
    export_dir = base_dir / "graph" / "export"
    graph = read_export(export_dir)
    graph.nodes[(ARCHETYPE_LABEL, km.KERNEL_ANCHOR)]["version"] = "0.0.1"
    export_mod.write_export(graph, export_dir)
    assert cmd_rederive(base_dir) == 1
    err = capsys.readouterr().err
    assert "rederive refused" in err and km.MIGRATE_COMMAND in err
    from graph.__main__ import cmd_canonize
    assert cmd_canonize(base_dir, database=None, apply=True) == 1
    err = capsys.readouterr().err
    assert "--apply refused" in err and km.MIGRATE_COMMAND in err


def test_rederive_proceeds_when_the_kernel_matches(tmp_path, capsys,
                                                   monkeypatch):
    base_dir = seeded_kb(tmp_path)
    fake_database(monkeypatch)
    assert cmd_rederive(base_dir) == 0
    assert "Rederived canon" in capsys.readouterr().out


# -- the enrichment ruling: canon's own knowledge on kernel citizens ----
#    rides the splice; the seed wins only the keys it defines --------------


def enriched_kb(tmp_path):
    """A knowledge base whose canon enriched a kernel citizen: 'Question'
    carries a world-authored spec catalog the kernel never defined, plus
    a doc the seed DOES define (the seed must win that one back)."""
    base_dir = seeded_kb(tmp_path)
    export_dir = base_dir / "graph" / "export"
    graph = read_export(export_dir)
    question = graph.nodes[(ARCHETYPE_LABEL, "Question")]
    question["spec_json"] = '{"catalog": {"asked_by": "text"}}'
    question["doc"] = "a world-reworded doc the kernel will win back"
    export_mod.write_export(graph, export_dir)
    return base_dir


def test_canon_enrichment_rides_the_splice_and_the_seed_wins_its_keys(
        tmp_path):
    base_dir = enriched_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    ground = strip_derived(read_export(base_dir / "graph" / "export"))
    seed, _findings = km.fresh_kernel(base_dir, nxt)
    old_nodes, _old_edges = km.kernel_stratum(ground)
    new_nodes, new_edges = km.kernel_stratum(seed)
    spliced, carried = km.splice(ground, set(old_nodes), new_nodes,
                                 new_edges)
    after = spliced.nodes[(ARCHETYPE_LABEL, "Question")]
    # the world's own key rides through unchanged...
    assert after["spec_json"] == '{"catalog": {"asked_by": "text"}}'
    # ...the seed wins the key it defines...
    assert after["doc"] == new_nodes["Question"]["doc"]
    assert "reworded" not in after["doc"]
    # ...and the carried map names exactly what rode
    assert carried == {"Question": ["spec_json"]}


def test_a_removed_citizens_enrichment_does_not_resurrect(tmp_path):
    base_dir = seeded_kb(tmp_path)
    export_dir = base_dir / "graph" / "export"
    graph = read_export(export_dir)
    graph.nodes[(ARCHETYPE_LABEL, "Theme")]["spec_json"] = "{}"
    export_mod.write_export(graph, export_dir)
    nxt = modified_kernel(tmp_path, drop="Theme")
    ground = strip_derived(read_export(export_dir))
    seed, _findings = km.fresh_kernel(base_dir, nxt)
    old_nodes, _old_edges = km.kernel_stratum(ground)
    new_nodes, new_edges = km.kernel_stratum(seed)
    spliced, carried = km.splice(ground, set(old_nodes), new_nodes,
                                 new_edges)
    assert (ARCHETYPE_LABEL, "Theme") not in spliced.nodes
    assert carried == {}


def test_the_dry_run_names_what_rode(tmp_path, capsys):
    base_dir = enriched_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    assert cmd_kernel_migrate(base_dir, metaontology_path=nxt) == 0
    out = capsys.readouterr().out
    assert "carried (1): Question (spec_json)" in out
    assert "rides the migration unchanged" in out
    assert "orphan check: clean" in out
    assert "Dry run: nothing written" in out


def test_the_applied_migration_keeps_the_enrichment(tmp_path, capsys,
                                                    monkeypatch):
    base_dir = enriched_kb(tmp_path)
    nxt = modified_kernel(tmp_path, add="Minted Kernel Concept")
    fake_database(monkeypatch)
    assert cmd_kernel_migrate(base_dir, apply=True,
                              metaontology_path=nxt) == 0
    after = read_export(base_dir / "graph" / "export")
    question = after.nodes[(ARCHETYPE_LABEL, "Question")]
    assert question["spec_json"] == '{"catalog": {"asked_by": "text"}}'
    assert "reworded" not in question["doc"]
