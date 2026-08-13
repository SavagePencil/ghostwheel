"""CLI: python -m graph {validate|export|load|check|generate|terms|delta|canonize}"""

import argparse
import json
import sys
from pathlib import Path

from . import export as export_mod
from . import validate as validate_mod


def find_base_dir():
    """Repo root = parent of the directory holding this package."""
    return Path(__file__).resolve().parent.parent


def cmd_validate(base_dir, write_files=True):
    _, graph, findings = validate_mod.run(base_dir)
    report_path = base_dir / "graph" / "reports" / "validation.md"
    if write_files:
        validate_mod.write_report(findings, graph, report_path)
    print(f"Validation: {validate_mod.summarize(findings)}")
    if graph is not None:
        print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    if write_files:
        print(f"Report: {report_path.relative_to(base_dir)}")
    if validate_mod.has_errors(findings):
        print("ERRORS present — fix the ontology/source files above.",
              file=sys.stderr)
        return 1, graph
    return 0, graph


def canon_base(base_dir):
    """The base of a round, post-flip: canon's committed backup (the
    export). No database needed to read it; apply verifies the live
    database still matches it before writing anything."""
    from . import restore as restore_mod
    return restore_mod.read_export(base_dir / "graph" / "export")


def cmd_export_lensed(base_dir, mask, out):
    """A lens-scoped materialization: the ONE place lenses
    materialize — the shipped runtime graph. Reads the committed
    backup (never the database), applies the mask, re-derives the
    machine layers under the lens (coherence: derived layers are a
    function of lensed ground, never a filter over old layers), and
    writes a full export elsewhere. The canonical backup at
    graph/export/ is always lens-free and cannot be the target."""
    from . import lens as lens_mod
    from .extract import derive, strip_derived
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph
    from .restore import read_export

    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = base_dir / out_path
    canonical = (base_dir / "graph" / "export").resolve()
    out_resolved = out_path.resolve()
    if out_resolved == canonical or canonical in out_resolved.parents \
            or out_resolved in canonical.parents:
        print("Attempted to write a lens-scoped export over or inside "
              "the canonical backup (graph/export). Failed due to: the "
              "backup is always lens-free — it is what restore and "
              "every round build from. Pick a --out directory outside "
              "it.", file=sys.stderr)
        return 1
    try:
        graph = read_export(base_dir / "graph" / "export")
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Attempted to read the canonical backup for a "
              f"lens-scoped export. Failed due to: {exc}",
              file=sys.stderr)
        return 1
    try:
        declarations = lens_mod.declarations_from_graph(graph)
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    try:
        the_lens = lens_mod.compile_lens(declarations, graph,
                                         mask=tuple(mask))
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    lensed = lens_mod.apply_lens(graph, the_lens)
    # The schema comes from the graph, not ontology.yaml (the schema-delta ceremony): reconstruct
    # it from the committed backup already read above (the full, lens-free
    # canon), so the machine layers re-derive under the lens from ground.
    ontology = ontology_from_graph(graph, base_dir)
    ground = strip_derived(lensed)
    shipped, findings = derive(ontology, ground)
    errors = [f for f in findings if f.severity == SEV_ERROR]
    if errors:
        print("Attempted to re-derive the machine layers under the "
              "lens. Failed due to: the masked elements were "
              "load-bearing — derivation errors below; nothing was "
              "written:", file=sys.stderr)
        for finding in errors:
            print(f"  ⚠ {finding.file} {finding.location}: "
                  f"{finding.detail}", file=sys.stderr)
        return 1
    export_mod.write_export(shipped, out_path)
    print(f"Lens-scoped export: {len(shipped.nodes)} nodes, "
          f"{len(shipped.edges)} edges (canon holds "
          f"{len(graph.nodes)}/{len(graph.edges)}) — masked "
          f"{', '.join(mask)} — written to {out}")
    return 0


def cmd_export(base_dir, from_sources=False):
    if from_sources:
        # bootstrap scaffolding: serialize a from-sources build
        status, graph = cmd_validate(base_dir)
        if status != 0 or graph is None:
            return status
    else:
        # post-flip default: the backup serializes THE DATABASE
        from . import load as load_mod
        from . import restore as restore_mod
        config = load_mod.read_config(base_dir)
        try:
            graph = restore_mod.dump_db(config)
        except Exception as exc:
            print(f"Attempted to export canon from the database "
                  f"('{config['NEO4J_DATABASE']}'). Failed due to: {exc}. "
                  "Is the DBMS running? For a from-sources bootstrap "
                  "export, use --from-sources.", file=sys.stderr)
            return 1
    export_dir = base_dir / "graph" / "export"
    export_mod.write_export(graph, export_dir)
    print(f"Export: {export_dir.relative_to(base_dir)}/"
          f"{{{export_mod.NODES_FILE},{export_mod.EDGES_FILE}}}"
          + ("" if from_sources else " (from the database)"))
    return 0


def cmd_restore(base_dir, database=None, from_dir=None):
    """Rebuild a database from graph/export/ alone, then read it back
    and prove byte-identity with the backup — the D55 drill.
    With --database scratch: clone canon to scratch and pin the round
    (post-flip round cut). With --from <dir> (the visibility lens design): load any
    export — e.g. a lens-scoped materialization — into a WORKSPACE
    database for inspection; requires --database, never targets live
    canon, and cuts no round."""
    from . import load as load_mod  # deferred: needs the neo4j driver
    from . import restore as restore_mod

    if from_dir and not database:
        print("Attempted to restore from a custom export with no "
              "target database. Failed due to: --from loads a "
              "workspace database and must name it with --database — "
              "the live canon database only ever restores from the "
              "canonical backup.", file=sys.stderr)
        return 1
    export_dir = (Path(from_dir) if from_dir else
                  base_dir / "graph" / "export")
    if from_dir and not export_dir.is_absolute():
        export_dir = base_dir / export_dir
    try:
        graph = restore_mod.read_export(export_dir)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    if from_dir and database == config["NEO4J_DATABASE"]:
        print(f"Attempted to load {from_dir} into the live canon "
              f"database ('{database}'). Failed due to: live canon "
              "only ever restores from the canonical backup at "
              "graph/export — pick a workspace database (e.g. "
              "scratch).", file=sys.stderr)
        return 1
    if database:
        config["NEO4J_DATABASE"] = database
    print(f"Restoring {config['NEO4J_URI']} "
          f"(database '{config['NEO4J_DATABASE']}') from the "
          f"{'export' if from_dir else 'backup'} at "
          f"{export_dir} — no sources involved ...")
    try:
        summary = load_mod.load(graph, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:  # driver errors: auth, unreachable, etc.
        print(f"Restore failed: {exc}", file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials?", file=sys.stderr)
        return 1
    print(f"Restored {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges.")
    problems = restore_mod.verify_against_backup(dumped, export_dir)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("DRILL FAILED — the database was rebuilt but does not match "
              "the backup. The backup files are untouched; git holds the "
              "truth.", file=sys.stderr)
        return 1
    print("DRILL PASSED — the database re-serializes byte-identical to "
          "the backup it was restored from.")
    if database and not from_dir:
        # a custom export is an inspection load, never a round cut
        pin_round(base_dir, graph, database)
    return 0


def cmd_verify_seal(base_dir, exam_path):
    """The grading-day handshake (D5): hash a produced exam file
    and check it against the sealed citizen in canon's backup. The
    content is never read as text — only hashed."""
    import hashlib
    import json as json_mod

    path = Path(exam_path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        print(f"Attempted to verify the seal on {exam_path}. Failed due "
              f"to: {exc}.", file=sys.stderr)
        return 1
    nodes_path = base_dir / "graph" / "export" / "nodes.jsonl"
    seals = []
    if nodes_path.exists():
        for line in nodes_path.read_text(encoding="utf-8").splitlines():
            record = json_mod.loads(line)
            if record["label"] == "Sealed Exam":
                seals.append(record)
    if not seals:
        print("Attempted to verify a seal, but canon holds no Sealed "
              "Exam citizens yet. The seal row lands via the delta path "
              "once the exam is authored and hashed.", file=sys.stderr)
        return 1
    for record in seals:
        if record["properties"].get("fingerprint") == digest:
            print(f"SEAL VERIFIED — {path.name} matches "
                  f"'{record['name']}' (sealed "
                  f"{record['properties'].get('sealed_on', '?')} by "
                  f"{record['properties'].get('authored_by', '?')}). "
                  "The file is byte-identical to what was sealed before "
                  "ingest began.")
            return 0
    print(f"SEAL BROKEN — {path.name} hashes to {digest[:16]}…, which "
          "matches no sealed exam. Canon holds:", file=sys.stderr)
    for record in seals:
        print(f"  '{record['name']}': "
              f"{record['properties'].get('fingerprint', '?')[:16]}… "
              f"(sealed {record['properties'].get('sealed_on', '?')})",
              file=sys.stderr)
    print("Either the file changed after sealing, or this is not the "
          "sealed file. Neither is gradeable.", file=sys.stderr)
    return 1


def cmd_rederive(base_dir):
    """Schema-bootstrap maintenance (until the schema inversion): re-derive canon's
    machine layers against the current schema, with the ground layer
    untouched — refuse if re-derivation would change any ground fact.
    Loads the result and re-exports the backup from the database."""
    from . import load as load_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from .extract import derive, strip_derived
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph

    try:
        base = canon_base(base_dir)
    except FileNotFoundError as exc:
        print("Attempted to load the schema from the graph's committed "
              f"backup (graph/export). Failed due to: {exc}. For a "
              "from-sources bootstrap, use the load/validate path.",
              file=sys.stderr)
        return 1
    # The schema is reconstructed FROM the graph (the schema-delta ceremony): the committed
    # backup is the schema of record; ontology.yaml is bootstrap-only.
    ontology = ontology_from_graph(base, base_dir)
    ground = strip_derived(base)
    new_graph, findings = derive(ontology, ground)
    errors = [f for f in findings if f.severity == SEV_ERROR]
    if errors:
        print("rederive refused — derivation errors; nothing was "
              "written:", file=sys.stderr)
        for finding in errors:
            print(f"  ⚠ {finding.file} {finding.location}: "
                  f"{finding.detail}", file=sys.stderr)
        return 1
    if proposal_mod.ground_identity(new_graph) != \
            proposal_mod.ground_identity(base):
        print("rederive refused: re-derivation would change the GROUND "
              "layer — schema edits may only reshape machine layers; a "
              "ground change goes through the delta path.",
              file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    try:
        summary = load_mod.load(new_graph, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:
        print(f"Rederive failed mid-write: {exc}. The backup files are "
              "untouched — python -m graph restore returns the live "
              "database to the last state.", file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        print("Rederive: the database read back differently than what "
              "was written. Backup untouched; python -m graph restore "
              "rolls back.", file=sys.stderr)
        return 1
    export_mod.write_export(dumped, base_dir / "graph" / "export")
    print(f"Rederived canon against the current schema: "
          f"{summary['loaded_nodes']} nodes, {summary['loaded_edges']} "
          "edges; ground layer unchanged; backup re-exported from the "
          "database.")
    return 0


def pin_round(base_dir, graph, database):
    """Cutting a working database starts a round: pin the base's content
    identity so drift under the round is detectable."""
    from . import proposal as proposal_mod
    import subprocess
    try:
        ref = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=base_dir,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        ref = "unknown"
    proposal_mod.write_json(
        proposal_mod.current_dir(base_dir) / proposal_mod.BASE_FILE,
        {"base_hash": proposal_mod.base_identity(graph),
         "git_ref": ref, "database": database})
    print(f"Round cut: base pinned at {ref} "
          f"(graph/proposals/current/base.json)")


def cmd_load(base_dir, database=None):
    from . import load as load_mod  # deferred: needs the neo4j driver

    status, graph = cmd_validate(base_dir)
    if status != 0 or graph is None:
        return status
    config = load_mod.read_config(base_dir)
    if database:
        config["NEO4J_DATABASE"] = database
    print(f"Loading into {config['NEO4J_URI']} "
          f"(database '{config['NEO4J_DATABASE']}') ...")
    try:
        summary = load_mod.load(graph, config)
    except Exception as exc:  # driver errors: auth, unreachable, etc.
        print(f"Load failed: {exc}", file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials? (see .env.example)", file=sys.stderr)
        return 1
    print(f"Loaded {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges")
    print("Nodes by label: " + ", ".join(
        f"{label}: {count}"
        for label, count in summary["nodes_by_label"].items()))
    print("Edges by type: " + ", ".join(
        f"{rel}: {count}"
        for rel, count in summary["edges_by_type"].items()))
    if database:
        pin_round(base_dir, graph, database)
    return 0


def parse_check(text, fallback_name=""):
    """Split a check file's // header into (description, expect_empty).

    A line `// expect: empty` marks the check as an ASSERTION: rows mean the
    check fails and `graph check` exits non-zero. Checks without the
    directive are informational finding reports.
    """
    comment_lines = [line.removeprefix("//").strip()
                     for line in text.splitlines() if line.startswith("//")]
    expect_empty = any(line.lower().startswith("expect: empty")
                       for line in comment_lines)
    description = " ".join(
        line for line in comment_lines
        if not line.lower().startswith("expect:")) or fallback_name
    return description, expect_empty


def cmd_check(base_dir):
    from . import load as load_mod  # deferred: needs the neo4j driver
    from neo4j import GraphDatabase

    checks_dir = base_dir / "graph" / "cypher" / "checks"
    check_files = sorted(checks_dir.glob("*.cypher"))
    if not check_files:
        print(f"No checks found in {checks_dir}", file=sys.stderr)
        return 2
    config = load_mod.read_config(base_dir)
    finding_rows = 0
    failed_assertions = []
    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    try:
        with driver, driver.session(
                database=config["NEO4J_DATABASE"]) as session:
            for path in check_files:
                text = path.read_text(encoding="utf-8")
                description, expect_empty = parse_check(text, path.stem)
                rows = list(session.run(text))
                if expect_empty:
                    status = "PASS" if not rows else "FAIL"
                    if rows:
                        failed_assertions.append(path.stem)
                    print(f"\n== {path.stem}: {status} (assertion; "
                          f"{len(rows)} rows)")
                else:
                    finding_rows += len(rows)
                    print(f"\n== {path.stem}: {len(rows)} findings")
                print(f"   {description}")
                for row in rows[:20]:
                    print(f"   {dict(row)}")
                if len(rows) > 20:
                    print(f"   ... and {len(rows) - 20} more")
    except Exception as exc:
        print(f"Check run failed: {exc}", file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials? (see .env.example)", file=sys.stderr)
        return 1
    print(f"\nChecks complete: {len(check_files)} checks, "
          f"{len(failed_assertions)} failed assertions, "
          f"{finding_rows} finding rows (informational)")
    if failed_assertions:
        print(f"FAILED: {', '.join(failed_assertions)} — expected empty; "
              "rows indicate an ETL/graph integrity bug.", file=sys.stderr)
        return 1
    return 0


def cmd_corpus(base_dir):
    """Re-check every owner-blessed floor (the regression corpus): each floor's guard
    must still exist in the suite and still pass. Reds name the
    blessing they break; a vanished guard is a red, never a silence."""
    from . import corpus as corpus_mod

    floors = corpus_mod.load_floors(corpus_mod.floors_path(base_dir))
    if not floors:
        print(corpus_mod.render_report([], [], []))
        return 0
    collected = corpus_mod.collect_guards(base_dir)
    if not collected:
        print("Attempted to re-collect the corpus's guards with pytest. "
              "Failed due to: the collection returned nothing — the "
              "test suite itself is not runnable here; fix that before "
              "trusting any floor.", file=sys.stderr)
        return 1
    missing = corpus_mod.missing_guards(floors, collected)
    failures = corpus_mod.run_floors(base_dir, floors, collected)
    print(corpus_mod.render_report(floors, missing, failures))
    return 1 if (missing or failures) else 0


def cmd_delta(base_dir, database, sync_bodies=False):
    """The agentic changeset: diff the scratch database against the
    canon base (the export backup), lint additions against the machine
    layers, and
    write the reviewable report (see graph/design/agentic-etl.md)."""
    from . import delta as delta_mod
    from . import load as load_mod

    from . import proposal as proposal_mod

    try:
        base = canon_base(base_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    config["NEO4J_DATABASE"] = database
    if sync_bodies:
        try:
            synced, problems = delta_mod.sync_bodies(config, base_dir)
        except Exception as exc:
            print(f"cannot sync bodies in '{database}': {exc}",
                  file=sys.stderr)
            return 1
        for name in synced:
            print(f"body synced from its approved file: {name}")
        for problem in problems:
            print(f"body sync problem: {problem}", file=sys.stderr)
        if not synced and not problems:
            print("bodies already in sync with their approved files.")
    try:
        scratch = delta_mod.read_graph(config)
    except Exception as exc:
        print(f"cannot read '{database}': {exc}", file=sys.stderr)
        print("Has the scratch database been created/loaded? "
              "(python -m graph load --database scratch)", file=sys.stderr)
        return 1
    changes = delta_mod.diff(base, scratch)
    stitch_problem = None
    try:
        changes.stitch = proposal_mod.read_stitch(base_dir)
    except (ValueError, KeyError) as exc:
        stitch_problem = (
            "Attempted to read the round's stitch file "
            f"(graph/proposals/current/{proposal_mod.STITCH_FILE}). "
            f"Failed due to: {exc}")
    violations = delta_mod.lint(changes)
    if stitch_problem:
        violations.append(stitch_problem)
    violations += delta_mod.lint_stitch(changes, scratch)
    violations += delta_mod.body_sync_violations(scratch, base_dir)
    # The orphan-procedure check: a registered procedure file with no citizen in scratch is
    # invisible to the body-sync scan (which walks existing nodes) — the
    # roster check names it before the round reaches canonize.
    from .extract import procedure_roster_findings
    from .ontology import ontology_from_graph
    # The schema is reconstructed FROM canon's backup (the schema-delta ceremony): `base` is the
    # committed graph read above; ontology.yaml is bootstrap-only now.
    ontology = ontology_from_graph(base, base_dir)
    if ontology is not None:
        violations += [f.detail
                       for f in procedure_roster_findings(ontology, scratch)]
    # The stitch mechanism: preview the stitch's landing against the graph this round
    # will actually produce (changeset applied, machine layers
    # re-derived) — the diff gate must never approve a connection that
    # stitches to nothing
    if changes.stitch and ontology is not None:
        from .extract import derive, strip_derived
        preview = strip_derived(base)
        if not proposal_mod.apply_delta(preview, changes):
            derived_preview, _ = derive(ontology, preview)
            violations += proposal_mod.apply_stitch(derived_preview,
                                                    changes.stitch)
    report = delta_mod.render_report(changes, violations)
    report_path = base_dir / "graph" / "reports" / "delta.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report: {report_path.relative_to(base_dir)}")
    # the proposal document: the machine-readable changeset whose hash
    # IS the proposal's id — what `approve` freezes and apply replays
    delta_text = proposal_mod.serialize_delta(changes)
    delta_path = proposal_mod.current_dir(base_dir) / proposal_mod.DELTA_FILE
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text(delta_text, encoding="utf-8")
    delta_id = proposal_mod.content_hash(delta_text)
    print(f"Proposal id: {delta_id[:12]} "
          f"({delta_path.relative_to(base_dir)})")
    base_pin = proposal_mod.current_dir(base_dir) / proposal_mod.BASE_FILE
    if base_pin.exists():
        pinned = proposal_mod.read_json(base_pin)
        if pinned.get("base_hash") != proposal_mod.base_identity(base):
            print("WARNING: the base has moved under this round — the "
                  "sources changed since scratch was cut. Drafting may "
                  "continue, but apply will refuse: re-cut scratch "
                  "(python -m graph load --database scratch) to "
                  "re-baseline and re-review.", file=sys.stderr)
    return 1 if violations else 0


def cmd_canonize(base_dir, database, apply):
    """Apply the approved delta to canon — graph-native. The dry
    run shows the changeset and freeze status; --apply verifies
    everything, applies the pinned changeset to the ground layer in
    memory, re-derives every machine layer, loads the result into the
    live database, re-exports the backup from it, and appends the
    chained event log. No file is edited; the graph is primary."""
    from . import canonize as canonize_mod
    from . import delta as delta_mod
    from . import load as load_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from .extract import derive, strip_derived
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph

    try:
        base = canon_base(base_dir)
    except FileNotFoundError as exc:
        print("Attempted to load the schema from the graph's committed "
              f"backup (graph/export). Failed due to: {exc}. For a "
              "from-sources bootstrap, use the load/validate path.",
              file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    live_database = config["NEO4J_DATABASE"]
    config = dict(config)
    config["NEO4J_DATABASE"] = database
    try:
        scratch = delta_mod.read_graph(config)
    except Exception as exc:
        print(f"cannot read '{database}': {exc}", file=sys.stderr)
        return 1
    changes = delta_mod.diff(base, scratch)
    try:
        changes.stitch = proposal_mod.read_stitch(base_dir)
    except (ValueError, KeyError) as exc:
        print("REFUSED: the round's stitch file is unreadable — "
              f"{exc}", file=sys.stderr)
        return 1
    violations = delta_mod.lint(changes)
    violations += delta_mod.lint_stitch(changes, scratch)
    if violations:
        print("REFUSED: the delta has ground-facts lint violations — "
              "fix scratch first (python -m graph delta):", file=sys.stderr)
        for violation in violations:
            print(f"  ⚠ {violation}", file=sys.stderr)
        return 1

    current = proposal_mod.current_dir(base_dir)
    approval_path = current / proposal_mod.APPROVAL_FILE
    delta_path = current / proposal_mod.DELTA_FILE
    if not apply:
        counts = (f"{len(changes.nodes_added)} added, "
                  f"{len(changes.nodes_changed)} changed, "
                  f"{len(changes.nodes_removed)} removed nodes; "
                  f"{len(changes.edges_added)} added, "
                  f"{len(changes.edges_changed)} changed, "
                  f"{len(changes.edges_removed)} removed edges")
        if changes.stitch:
            counts += (f"; {len(changes.stitch)} stitched (land after "
                       "re-derivation)")
        print(f"Changeset vs canon: {counts}")
        print("Approval on record: "
              + ("yes" if approval_path.exists() else
                 "no — review at the diff gate, then python -m graph "
                 "approve"))
        print("Dry run — python -m graph canonize --apply applies the "
              "approved changeset to the live graph.")
        return 0

    # --- the approval freeze: apply replays only what was approved ------
    if not approval_path.exists():
        print("--apply refused: no approval on record for this round. "
              "Review the delta at the diff gate, then record the "
              "approval (python -m graph approve).", file=sys.stderr)
        return 1
    approval = proposal_mod.read_json(approval_path)
    pinned_text = delta_path.read_text(encoding="utf-8") \
        if delta_path.exists() else None
    if pinned_text is None or \
            proposal_mod.content_hash(pinned_text) != approval["delta_hash"]:
        print("--apply refused: the proposal document is missing or does "
              "not match the approved hash — the round's artifacts were "
              "tampered with after approval. Re-run python -m graph "
              "delta and re-review.", file=sys.stderr)
        return 1
    if approval.get("base_hash") and \
            approval["base_hash"] != proposal_mod.base_identity(base):
        print("--apply refused: the base has moved since approval — "
              "canon's backup changed under the round. Re-cut scratch "
              "(python -m graph restore --database scratch), re-review, "
              "and re-approve.", file=sys.stderr)
        return 1
    drift = proposal_mod.divergence(
        proposal_mod.parse_delta(pinned_text), changes)
    if drift:
        print("--apply refused: scratch has moved since approval — the "
              "divergence, named:", file=sys.stderr)
        for problem in drift:
            print(f"  ⚠ {problem}", file=sys.stderr)
        print("Re-review (python -m graph delta) and re-approve.",
              file=sys.stderr)
        return 1

    # --- the live database must still equal the backup it came from ----
    live_config = dict(config)
    live_config["NEO4J_DATABASE"] = live_database
    try:
        live = restore_mod.dump_db(live_config)
    except Exception as exc:
        print(f"--apply refused: cannot read the live database "
              f"('{live_database}'): {exc}", file=sys.stderr)
        return 1
    live_drift = restore_mod.verify_against_backup(
        live, base_dir / "graph" / "export")
    if live_drift:
        print("--apply refused: the live database no longer matches the "
              "backup it was restored from — canon moved outside the "
              "delta path:", file=sys.stderr)
        for problem in live_drift:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1

    # --- apply the PINNED artifact to the ground layer, then re-derive -
    pinned_delta = proposal_mod.parse_delta(pinned_text)
    ground = strip_derived(base)
    problems = proposal_mod.apply_delta(ground, pinned_delta)
    if problems:
        print("--apply refused — preconditions failed; nothing was "
              "written:", file=sys.stderr)
        for problem in problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1
    # The schema is reconstructed FROM canon's backup (the schema-delta ceremony): `base` is the
    # committed graph; ontology.yaml is bootstrap-only now.
    ontology = ontology_from_graph(base, base_dir)
    new_graph, derive_findings = derive(ontology, ground)
    derive_errors = [f for f in derive_findings if f.severity == SEV_ERROR]
    if derive_errors:
        print("--apply refused — re-derivation reported errors; nothing "
              "was written:", file=sys.stderr)
        for finding in derive_errors:
            print(f"  ⚠ {finding.file} {finding.location}: "
                  f"{finding.detail}", file=sys.stderr)
        return 1
    # The stitch mechanism: the stitch lands IN MEMORY, after re-derivation births the
    # round's new citizens and before anything is written — same
    # verify-all-before-apply-any window as everything above
    stitch_problems = proposal_mod.apply_stitch(new_graph,
                                                pinned_delta.stitch)
    if stitch_problems:
        print("--apply refused — the stitch cannot land; nothing was "
              "written:", file=sys.stderr)
        for problem in stitch_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1

    # --- stamp the version anchor: the project ontology's version IS the
    # event-log sequence, so a fresh connection's version moves with the
    # graph, not with a file (the schema-delta ceremony, owner ruling 2026-08-03); restamp the
    # fingerprint from the ground schema stratum too. Verify-all before
    # apply-any: a missing anchor collates here, nothing written.
    version = proposal_mod.next_log_sequence(base_dir)
    stamp_problems = canonize_mod.stamp_ontology_anchor(new_graph, version)
    if stamp_problems:
        print("--apply refused — the version anchor cannot be stamped; "
              "nothing was written:", file=sys.stderr)
        for problem in stamp_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1

    # --- write: load canon, re-export the backup FROM the database -----
    try:
        summary = load_mod.load(new_graph, live_config)
        dumped = restore_mod.dump_db(live_config)
    except Exception as exc:
        print(f"Apply failed mid-write: {exc}. The backup files are "
              "untouched — python -m graph restore returns the live "
              "database to the last applied state.", file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        print("EVENT LOG NOT WRITTEN — the database read back differently "
              "than what was written (driver round-trip fault). The "
              "backup files are untouched; python -m graph restore "
              "returns the live database to the last applied state.",
              file=sys.stderr)
        return 1
    export_mod.write_export(dumped, base_dir / "graph" / "export")

    # --- the event log: inverse, chained entry, archive ----------------
    inverse_text = proposal_mod.serialize_delta(
        proposal_mod.invert_delta(pinned_delta))
    (current / proposal_mod.INVERSE_FILE).write_text(inverse_text,
                                                     encoding="utf-8")
    base_before = approval.get("base_hash") or \
        proposal_mod.base_identity(base)
    base_after = proposal_mod.base_identity(dumped)
    chain = proposal_mod.append_applied_log(
        base_dir, approval["delta_hash"], base_before, base_after)
    proposal_mod.write_json(current / proposal_mod.APPLIED_FILE,
                            {"delta_hash": approval["delta_hash"],
                             "base_after": base_after,
                             "applied": "graph-native",
                             "chain": chain})
    archive = proposal_mod.archive_round(base_dir, approval["delta_hash"])
    print(f"Applied to canon: {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges now live; backup re-exported "
          "from the database.")
    print(f"Round archived: {archive.relative_to(base_dir)} — event log "
          f"entry chained ({chain[:12]}), inverse recorded.")
    print("Ritual: pytest, commit the export + round archive; the next "
          "round cuts scratch with python -m graph restore --database "
          "scratch.")
    return 0


def cmd_approve(base_dir, by):
    """Record the diff-gate approval against the current proposal's
    content hash. Run by the submitter — or an agent on their behalf;
    the record names the human. Apply replays only what this froze."""
    from . import proposal as proposal_mod

    current = proposal_mod.current_dir(base_dir)
    delta_path = current / proposal_mod.DELTA_FILE
    if not delta_path.exists():
        print("Attempted to record an approval, but no proposal document "
              "exists for this round. Run python -m graph delta first — "
              "the approval freezes exactly what that wrote.",
              file=sys.stderr)
        return 1
    delta_text = delta_path.read_text(encoding="utf-8")
    delta_id = proposal_mod.content_hash(delta_text)
    base_pin = current / proposal_mod.BASE_FILE
    base_hash = (proposal_mod.read_json(base_pin).get("base_hash")
                 if base_pin.exists() else None)
    if not by:
        import subprocess
        try:
            by = subprocess.run(
                ["git", "config", "user.name"], cwd=base_dir,
                capture_output=True, text=True, timeout=10,
            ).stdout.strip() or "unknown"
        except Exception:
            by = "unknown"
    proposal_mod.write_json(current / proposal_mod.APPROVAL_FILE,
                            {"delta_hash": delta_id, "base_hash": base_hash,
                             "by": by})
    print(f"Approval recorded: proposal {delta_id[:12]} by {by}. "
          "Apply will replay exactly this changeset "
          "(python -m graph canonize --apply).")
    return 0


def _procedure_citations(base_dir):
    """{artifact relpath: {cited headings}} and {artifact: [(name, spec)]}
    from the procedure files — the comprehension and round-trip
    machinery's view of which sections carry approved programs."""
    from . import procedures as procedures_mod
    cited, specs = {}, {}
    for proc_path in sorted((base_dir / "data" / "procedures").glob("*.yaml")):
        spec, errors = procedures_mod.parse_procedure(
            proc_path.read_text(encoding="utf-8"))
        if spec is None or errors:
            continue  # validate reports these; comprehension stays quiet
        artifact, sections, _ = procedures_mod.specified_in_of(spec)
        if artifact and sections:
            cited.setdefault(artifact, set()).update(sections)
            specs.setdefault(artifact, []).append(
                (str(spec["procedure"]).strip(), spec))
    return cited, specs


def cmd_comprehend(base_dir, artifacts, recall, dispose):
    """The reading room: build comprehension for artifacts, batch-recall
    archives, or dispose of the live room. Errors collate; no partial
    silence."""
    from . import comprehension
    from . import load as load_mod

    if not artifacts and not recall and not dispose:
        print("Attempted to run comprehend with nothing to do. Give it "
              "artifact files to read, --recall <archive dirs>, or "
              "--dispose.", file=sys.stderr)
        return 2

    # procedure-cited sections classify as procedure spans (the content-class taxonomy)
    cited, _ = _procedure_citations(base_dir)

    readings, problems = [], []
    for relpath in artifacts or []:
        path = base_dir / relpath
        try:
            data = path.read_bytes()
        except OSError as exc:
            problems.append(f"Attempted to read artifact {relpath}. "
                            f"Failed due to: {exc}.")
            continue
        from . import roundtrip as roundtrip_mod
        readings.append((relpath,
                         comprehension.read_artifact(
                             data, title=Path(relpath).name,
                             origin=str(relpath),
                             cited_sections=cited.get(relpath, set()),
                             carried_texts=roundtrip_mod
                             .carried_passages_for(base_dir, relpath))))
    for directory in recall or []:
        try:
            readings.append((directory,
                             comprehension.read_archive(base_dir / directory)))
        except (OSError, KeyError, ValueError) as exc:
            problems.append(f"Attempted to recall archive {directory}. "
                            f"Failed due to: {exc}. If the archive was "
                            "deleted, re-run comprehend on the original "
                            "artifact — structure recomputes identically.")
    if problems:
        print("Nothing was loaded — every problem collated below:\n  - "
              + "\n  - ".join(problems), file=sys.stderr)
        return 1

    config = load_mod.read_config(base_dir)
    driver = comprehension.room_session(config)
    try:
        comprehension.ensure_room(driver)
        if dispose:
            comprehension.dispose(driver)
            print("Reading room wiped. The filed archives are the record; "
                  "--recall re-imports any of them.")
        for origin, reading in readings:
            comprehension.load_reading(driver, reading)
            if origin in (artifacts or []):
                # graph/comprehension/ is git-tracked (like graph/export/)
                # — ordinary git recovery is the first line of
                # deleted-archive defense
                archive_dir = (base_dir / "graph" / "comprehension"
                               / f"{Path(origin).stem}-{reading.short}")
                comprehension.write_archive(reading, archive_dir)
                print(f"Read {origin} — {len(reading.sections)} sections, "
                      f"fingerprint {reading.short}; archive filed at "
                      f"{archive_dir.relative_to(base_dir)}")
            else:
                print(f"Recalled {origin} — {reading.title}, "
                      f"{len(reading.sections)} sections")
        if readings:
            print("\nThe room now holds:")
            for row in comprehension.room_report(driver):
                census = row.get("class_census") or []
                summary = ", ".join(
                    f"{census.count(c)} {c}"
                    for c in ("table", "procedure", "rule-prose",
                              "verbatim-carried") if c in census)
                carried = row.get("carried_fraction") or 0.0
                print(f"  {row['title']} ({str(row['fingerprint'])[:12]}) — "
                      f"{row['sections']} sections, "
                      f"deepest level {row['deepest']}"
                      + (f"; classes: {summary}" if summary else "")
                      + f"; carried-verbatim: {carried:.0%}")
    except Exception as exc:  # driver errors: auth, unreachable, etc.
        print(f"Attempted to reach the comprehension workspace database. "
              f"Failed due to: {exc}. Is the Neo4j DBMS running?",
              file=sys.stderr)
        return 1
    finally:
        driver.close()
    return 0


def cmd_roundtrip(base_dir, scope, draft, book=False):
    """The parity harness: original vs draft at the
    functional-parity bar, one scorecard, real exit status — no human in
    the comparison step. The cold DRAFT is produced elsewhere (the M1
    regeneration loop); this judges it. --book judges the WHOLE
    submitted artifact as one unit (the canon-attribution pass): procedure citations union
    across the roster, canon rows apply across every scope, one
    scorecard with sections as drill-down."""
    from . import roundtrip as roundtrip_mod

    problems = []
    if not (base_dir / scope).exists():
        problems.append(f"Attempted to round-trip {scope}. Failed due to: "
                        "no such artifact in the repo.")
    if not Path(draft).exists():
        problems.append(f"Attempted to judge draft {draft}. Failed due "
                        "to: no such file.")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    cited, specs = _procedure_citations(base_dir)
    # Not repointed to the graph by design: the parity harness reads the
    # original-era YAML because it consumes the render-only rendered_view/
    # rendered_views mappings, deliberately NOT embedded on the graph. It
    # retires at succession, not at the inversion.
    from . import ontology as ontology_mod
    ontology, _ = ontology_mod.load_ontology(
        base_dir / "graph" / "ontology.yaml", base_dir)
    if book:
        cited_sections = set().union(*cited.values()) if cited else set()
        cited_specs = [pair for pairs in specs.values() for pair in pairs]
        canon_scope = roundtrip_mod.ALL_SCOPES
    else:
        cited_sections = cited.get(scope, set())
        cited_specs = specs.get(scope, [])
        canon_scope = None
    result = roundtrip_mod.run(
        base_dir, scope, draft,
        cited_sections=cited_sections,
        cited_specs=cited_specs,
        ontology=ontology, canon_scope=canon_scope)
    report = roundtrip_mod.render_report(result)
    report_path = base_dir / "graph" / "reports" / "roundtrip.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report: {report_path.relative_to(base_dir)}")

    # attribution debts: gaps and soup-rung homes, one row each
    # — the intake worklist a census produces as a byproduct (issue
    # filing stays with the orchestrator)
    if result.attribution:
        from . import attribution as attribution_mod
        debts = [r.row() for r in result.attribution
                 if r.verdict == attribution_mod.CANON_GAP
                 or (r.verdict == attribution_mod.ATTRIBUTED
                     and r.rung == attribution_mod.PROSE)]
        debts_path = base_dir / "graph" / "reports" / \
            "attribution-debts.jsonl"
        debts_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True)
                    + "\n" for row in debts), encoding="utf-8")
        print(f"Attribution: {len(result.attribution)} claims censused; "
              f"{len(debts)} debts filed at "
              f"{debts_path.relative_to(base_dir)}")

    # findings are ROWS: archived beside the artifact's reading,
    # loaded into the room beside the sections they judge
    from . import comprehension
    from . import load as load_mod
    rows = result.findings_rows()
    archive_dir = (base_dir / "graph" / "comprehension"
                   / f"{Path(scope).stem}-{result.fingerprint[:12]}")
    comprehension.write_findings_archive(archive_dir, rows)
    print(f"Findings: {len(rows)} rows filed at "
          f"{archive_dir.relative_to(base_dir)}/"
          f"{comprehension.FINDINGS_FILE}")
    try:
        config = load_mod.read_config(base_dir)
        driver = comprehension.room_session(config)
        try:
            comprehension.ensure_room(driver)
            data = (base_dir / scope).read_bytes()
            reading = comprehension.read_artifact(
                data, title=Path(scope).name, origin=scope,
                cited_sections=cited.get(scope, set()),
                carried_texts=roundtrip_mod.carried_passages_for(
                    base_dir, scope))
            comprehension.load_reading(driver, reading)
            comprehension.load_findings(driver, result.fingerprint, rows)
            print("Room: findings landed beside their sections "
                  "(workspace database).")
        finally:
            driver.close()
    except Exception as exc:
        print(f"Room not updated (judging is unaffected): {exc}",
              file=sys.stderr)
    return 0 if result.passed else 1


def cmd_render_tables(base_dir, scope, out):
    """Render a chapter's {{csv:}} tables AS MARKDOWN FROM THE GRAPH — the
    table-only draft the round-trip judge grades (the table-rendering tier). Values
    come from citizen properties and edges (the committed backup, DB-free),
    never from the CSV; only the embed path and column order are read from
    the artifact. Tables the generic inverter cannot render are reported as
    mapping gaps with a proposed declaration shape, never silently skipped."""
    from . import ontology as ontology_mod
    from . import render_tables

    if not (base_dir / scope).exists():
        print(f"Attempted to render the tables of {scope}. Failed due to: "
              "no such artifact in the repo.", file=sys.stderr)
        return 2
    # Not repointed to the graph by design: column typing consumes the
    # render-only rendered_view/rendered_views mappings, deliberately NOT
    # embedded on the graph. It retires at succession, not at the inversion.
    ontology, findings = ontology_mod.load_ontology(
        base_dir / "graph" / "ontology.yaml", base_dir)
    if ontology is None:
        for finding in findings:
            print(f"{finding.severity}: {finding.detail}", file=sys.stderr)
        return 1
    try:
        graph = render_tables.load_backup(base_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    chapter = render_tables.render_chapter(base_dir, scope, graph, ontology)

    if out:
        out_path = Path(out)
    else:
        out_path = (base_dir / "graph" / "reports"
                    / f"{Path(scope).stem}-tables-draft.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(chapter.draft(), encoding="utf-8")

    rendered = [t for t in chapter.tables if t.rendered]
    print(f"Rendered {len(rendered)}/{len(chapter.tables)} embedded "
          f"table(s) of {scope} from the graph:")
    for table in chapter.tables:
        if table.rendered:
            print(f"  rendered  {table.relpath}  (:{table.label})")
        else:
            print(f"  GAP       {table.relpath}  — {table.gap}")
    try:
        print(f"Draft: {out_path.relative_to(base_dir)}")
    except ValueError:
        print(f"Draft: {out_path}")
    if chapter.gaps:
        print("\nMapping gaps — a PROPOSED declaration shape for each "
              "(not applied to the ontology):")
        for table in chapter.gaps:
            print(f"\n--- {table.relpath} ---")
            print(table.proposal)
        print("\nRule the declaration shape at the gate, then intake grows "
              "the project ontology.")
    return 0


def cmd_generate(base_dir, procedure_name):
    """The prose-generation experiment (secret-goal probe): render an approved
    program back into rulebook-style markdown for the approver's comparison
    against the authored section. Measures the gap; never replaces docs."""
    from . import ontology as ontology_mod
    from . import procedures as procedures_mod
    from .restore import read_export

    # Procedure sources ride the graph now (the schema-delta ceremony): reconstruct the schema
    # from canon's committed backup; ontology.yaml is bootstrap-only.
    try:
        graph = read_export(base_dir / "graph" / "export")
    except (FileNotFoundError, ValueError, OSError) as exc:
        print("Attempted to load the schema from the graph's committed "
              f"backup (graph/export). Failed due to: {exc}. For a "
              "from-sources bootstrap, use the load/validate path.",
              file=sys.stderr)
        return 1
    ontology = ontology_mod.ontology_from_graph(graph, base_dir)
    available = []
    for spec in ontology.nodes.values():
        if ontology_mod.node_reader(spec) != ontology_mod.Reader.PROCEDURE_YAML:
            continue
        for relpath in ontology_mod.source_files_of(spec):
            text = (base_dir / relpath).read_text(encoding="utf-8")
            proc_spec, errors = procedures_mod.parse_procedure(text)
            if proc_spec is None or errors:
                for location, detail in errors:
                    print(f"{relpath} {location}: {detail}", file=sys.stderr)
                continue
            name = str(proc_spec["procedure"]).strip()
            available.append(name)
            if name == procedure_name:
                print(procedures_mod.render_markdown(proc_spec), end="")
                return 0
    print(f"No procedure named '{procedure_name}'. "
          f"Available: {', '.join(available) or 'none'}", file=sys.stderr)
    return 1


def canon_term_index(base_dir):
    """Build the glossary's term index over CANON — the committed backup,
    written from the database — never the from-sources build, which cannot
    see citizens born by graph rounds (the graph-round sweep read every
    graph-born citizen as unresolved forever). Returns
    (extractor, error_message): exactly one of the pair is None."""
    from .extract import Extractor
    from .ontology import ontology_from_graph

    try:
        graph = canon_base(base_dir)
    except FileNotFoundError as exc:
        return None, (
            "Attempted to load the schema from the graph's committed "
            f"backup (graph/export). Failed due to: {exc}. For a "
            "from-sources bootstrap, use the load/validate path.")
    # The term index's concepts/surface_forms/prose_files come from the
    # graph now (the schema-delta ceremony): reconstruct the schema from the committed backup.
    ontology = ontology_from_graph(graph, base_dir)
    extractor = Extractor.__new__(Extractor)
    extractor.ontology = ontology
    extractor.graph = graph
    extractor.findings = []
    extractor.note = lambda *args, **kwargs: None
    extractor.term_index = Extractor.build_term_index(extractor)
    return extractor, None


def cmd_terms(base_dir):
    """The glossary sweep: scan every declared prose section body for
    capitalized terms the term index cannot resolve, and print a
    consolidated candidate list for the owner to classify (surface form |
    stub concept | local | reject). Rerun after any intake — the list should
    trend empty. The index reads canon (the committed backup), so citizens
    born by graph rounds resolve like any other. The swept file set is
    the ontology's declared prose (markdown) sources; sources declared
    non-prose are skipped by declaration, never by filename."""
    from . import parsers

    extractor, error = canon_term_index(base_dir)
    if error:
        print(error, file=sys.stderr)
        return 1

    # Ruled rejects are Judgment citizens on canon (the Decision rows
    # carrying rejected_term) — read with the rest of the graph ontology
    # since the migration round landed; the YAML bridge is retired.
    rejects = set(extractor.ontology.rejected_terms)
    sightings = {}        # term -> {file stems}
    counts = {}           # term -> occurrences
    rejects_seen = set()  # rejected terms still present in the docs
    for relpath in extractor.ontology.prose_files():
        path = base_dir / relpath
        text = path.read_text(encoding="utf-8")
        for heading, body in parsers.markdown_sections(text):
            for term in extractor.unresolved_terms_in(body):
                if term in rejects:
                    rejects_seen.add(term)
                    continue  # ruled non-vocabulary at a glossary sitting
                sightings.setdefault(term, set()).add(path.stem)
                counts[term] = counts.get(term, 0) + 1
    stale = sorted(rejects - rejects_seen)
    if not sightings:
        print("No unresolved terms — the glossary covers the docs"
              + (f" ({len(rejects_seen)} ruled reject(s) suppressed)."
                 if rejects_seen else "."))
    else:
        print(f"{len(sightings)} unresolved term(s) across docs/ "
              "(classify each: surface form | stub concept | local | "
              "reject):\n")
        width = max(len(t) for t in sightings)
        for term in sorted(sightings, key=lambda t: (-counts[t], t)):
            files = ", ".join(sorted(sightings[term]))
            print(f"  {term:<{width}}  ×{counts[term]:<3} {files}")
        if rejects_seen:
            print(f"\n({len(rejects_seen)} ruled reject(s) suppressed.)")
    if stale:
        print(f"\n{len(stale)} rejected term(s) no longer appear in the "
              "docs — retire them from rejected_terms in "
              "graph/ontology.yaml:")
        for term in stale:
            print(f"  {term}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ghostwheel",
        description="Derive, validate, and load the project's derived graph.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate",
                   help="parse sources against the ontology; write "
                        "graph/reports/validation.md (no DB needed)")
    export_parser = sub.add_parser(
        "export",
        help="serialize the live database to graph/export/ — the backup "
             "is written FROM canon (post-flip default)")
    export_parser.add_argument(
        "--from-sources", action="store_true",
        help="bootstrap scaffolding: serialize a from-sources build "
             "instead of the database (no DB needed)")
    export_parser.add_argument(
        "--mask", action="append", default=[],
        help="lens-scoped materialization (the visibility lens design): mask this class "
             "(repeatable; a Visibility Class citizen on the graph) "
             "and write elsewhere — requires --out; the canonical "
             "backup is always lens-free")
    export_parser.add_argument(
        "--out",
        help="target directory for a lens-scoped export (never "
             "graph/export)")
    load_parser = sub.add_parser(
        "load",
        help="BOOTSTRAP scaffolding: validate, then wipe and reload Neo4j "
             "from the sources. Post-flip, canon round-trips through "
             "restore/canonize instead (connection from .env)")
    load_parser.add_argument(
        "--database", default=None,
        help="override the target database (e.g. 'scratch' — rebuilding "
             "sources into scratch IS copy-base-to-scratch in the derived "
             "era; created if missing)")
    restore_parser = sub.add_parser(
        "restore",
        help="wipe a database and rebuild it from graph/export/ alone, "
             "then verify the restored state re-serializes byte-identical "
             "to the backup (the D55 drill; with --database scratch: the "
             "post-flip round cut — clone canon and pin the base)")
    verify_seal = sub.add_parser(
        "verify-seal",
        help="grading-day handshake: hash an exam file and check it "
             "against the Sealed Exam citizen in canon's backup (the "
             "content is hashed, never read)")
    verify_seal.add_argument("exam", help="path to the produced exam file")
    sub.add_parser(
        "rederive",
        help="schema-bootstrap maintenance (until the schema inversion): re-derive "
             "canon's machine layers against the current ontology.yaml, "
             "ground layer untouched, backup re-exported from the "
             "database")
    restore_parser.add_argument(
        "--database", default=None,
        help="target database override (e.g. 'scratch' — cuts a round: "
             "clone of canon, base pinned)")
    restore_parser.add_argument(
        "--from", dest="from_dir", default=None,
        help="load a CUSTOM export directory (e.g. a lens-scoped "
             "materialization) into a workspace database for "
             "inspection — requires --database, never live canon, "
             "cuts no round (the visibility lens design)")
    sub.add_parser("check",
                   help="run the canned Cypher checks in graph/cypher/checks/ "
                        "against the live database")
    render_parser = sub.add_parser(
        "render-tables",
        help="render a chapter's {{csv:}} tables AS MARKDOWN FROM THE GRAPH "
             "(the table-only draft the round-trip judge grades); mapping "
             "gaps are reported with a proposed declaration shape (no DB "
             "needed — reads the committed backup)")
    render_parser.add_argument(
        "--scope", required=True,
        help="the chapter whose tables to render (e.g. docs/03-chapter.md)")
    render_parser.add_argument(
        "--out", default=None,
        help="where to write the draft (default: "
             "graph/reports/<chapter>-tables-draft.md)")
    generate = sub.add_parser(
        "generate",
        help="render an approved procedure back into rulebook-style markdown "
             "(prose-generation experiment; no DB needed)")
    generate.add_argument("procedure", help="Procedure name, e.g. 'Awaken a Gryphon'")
    sub.add_parser("terms",
                   help="scan all docs for capitalized terms the glossary "
                        "cannot resolve (owner consolidation list)")
    sub.add_parser(
        "corpus",
        help="re-check every owner-blessed floor (the regression corpus): each guard "
             "must still exist and still pass; reds name the blessing "
             "they break")
    delta_parser = sub.add_parser(
        "delta",
        help="diff the scratch database against canon's backup: "
             "the agentic changeset, linted and itemized")
    delta_parser.add_argument(
        "--database", default="scratch",
        help="the working database to diff (default: scratch)")
    delta_parser.add_argument(
        "--sync-bodies", action="store_true",
        help="before diffing, update program-carrying nodes' body from "
             "their approved files (the file is the truth; replaces the "
             "manual paste-and-hash ritual)")
    canonize_parser = sub.add_parser(
        "canonize",
        help="apply the approved delta to the live graph — verify all, "
             "re-derive, re-export the backup, chain the event log "
             "(dry run by default; --apply writes)")
    canonize_parser.add_argument(
        "--database", default="scratch",
        help="the working database to canonize from (default: scratch)")
    canonize_parser.add_argument(
        "--apply", action="store_true",
        help="write the deterministic edits to the source files")
    roundtrip_parser = sub.add_parser(
        "roundtrip",
        help="judge a regenerated draft against the original at the "
             "functional-parity bar: one scorecard, exit nonzero on any "
             "red (no human in the comparison)")
    roundtrip_parser.add_argument(
        "--scope", required=True,
        help="the original artifact (e.g. docs/03-chapter.md)")
    roundtrip_parser.add_argument(
        "--draft", required=True,
        help="the regenerated chapter to judge")
    roundtrip_parser.add_argument(
        "--book", action="store_true",
        help="judge the WHOLE submitted artifact as one unit (the canon-attribution pass): "
             "procedure citations union across the roster, canon rows "
             "apply across every scope, one scorecard")
    approve_parser = sub.add_parser(
        "approve",
        help="record the diff-gate approval against the current "
             "proposal's content hash — apply replays only this")
    approve_parser.add_argument(
        "--by", default=None,
        help="who approved (defaults to git user.name)")
    comprehend_parser = sub.add_parser(
        "comprehend",
        help="build the reading room for an artifact: fingerprint it, "
             "read its structure into the comprehension workspace "
             "database, and file the flat archive with the proposal")
    comprehend_parser.add_argument(
        "artifacts", nargs="*",
        help="artifact file(s) to read (e.g. docs/03-chapter.md)")
    comprehend_parser.add_argument(
        "--recall", nargs="+", metavar="ARCHIVE_DIR", default=None,
        help="batch-import previously filed archives into the room "
             "instead of reading new artifacts")
    comprehend_parser.add_argument(
        "--dispose", action="store_true",
        help="wipe the live reading room (the archives are the record)")
    args = parser.parse_args(argv)

    base_dir = find_base_dir()
    if args.command == "validate":
        status, _ = cmd_validate(base_dir)
        return status
    if args.command == "export":
        if args.mask or args.out:
            if args.from_sources:
                print("Attempted a lens-scoped export from sources. "
                      "Failed due to: --from-sources and --mask/--out "
                      "do not combine — a lens-scoped export always "
                      "reads the committed backup, so the lensed view "
                      "derives from applied canon, never from an "
                      "unapplied build.", file=sys.stderr)
                return 2
            if not (args.mask and args.out):
                print("Attempted a lens-scoped export. Failed due to: "
                      "--mask and --out travel together — name the "
                      "class(es) to mask AND the target directory.",
                      file=sys.stderr)
                return 2
            return cmd_export_lensed(base_dir, args.mask, args.out)
        return cmd_export(base_dir, from_sources=args.from_sources)
    if args.command == "restore":
        return cmd_restore(base_dir, database=args.database,
                           from_dir=args.from_dir)
    if args.command == "rederive":
        return cmd_rederive(base_dir)
    if args.command == "verify-seal":
        return cmd_verify_seal(base_dir, args.exam)
    if args.command == "load":
        return cmd_load(base_dir, database=args.database)
    if args.command == "check":
        return cmd_check(base_dir)
    if args.command == "render-tables":
        return cmd_render_tables(base_dir, args.scope, args.out)
    if args.command == "generate":
        return cmd_generate(base_dir, args.procedure)
    if args.command == "corpus":
        return cmd_corpus(base_dir)
    if args.command == "terms":
        return cmd_terms(base_dir)
    if args.command == "delta":
        return cmd_delta(base_dir, args.database, args.sync_bodies)
    if args.command == "canonize":
        return cmd_canonize(base_dir, args.database, args.apply)
    if args.command == "roundtrip":
        return cmd_roundtrip(base_dir, args.scope, args.draft,
                             book=args.book)
    if args.command == "approve":
        return cmd_approve(base_dir, args.by)
    if args.command == "comprehend":
        return cmd_comprehend(base_dir, args.artifacts, args.recall,
                              args.dispose)
    return 2


if __name__ == "__main__":
    sys.exit(main())
