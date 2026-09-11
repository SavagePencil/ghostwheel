"""CLI: python -m graph {validate|export|load|check|generate|terms|delta|canonize}"""

import argparse
import json
import os
import sys
from pathlib import Path

from . import export as export_mod
from . import refs as refs_mod


def find_base_dir():
    """Resolve the opened knowledge base's root.

    Precedence: the GHOSTWHEEL_BASE environment variable; else walk up
    from the current directory to the first ancestor that looks like a
    knowledge base (it carries graph/export/ — the committed backup IS
    the mark of a knowledge base; the from-sources era is closed);
    else, for a source checkout where the package sits inside the KB
    repo itself, the package's grandparent when IT looks like one.
    Anything else refuses by name — the engine is installed apart from
    any one knowledge base, so it must be told (or shown) which base it
    is opening."""
    env = os.environ.get("GHOSTWHEEL_BASE")
    if env:
        base = Path(env).expanduser().resolve()
        if _looks_like_kb(base):
            return base
        raise SystemExit(
            f"Attempted to open the knowledge base named by "
            f"GHOSTWHEEL_BASE ({base}). Failed due to: no graph/export/ "
            "there — that directory is not a knowledge base root. A new "
            "knowledge base is born with python -m graph init.")
    for candidate in [Path.cwd().resolve(),
                      *Path.cwd().resolve().parents]:
        if _looks_like_kb(candidate):
            return candidate
    checkout = Path(__file__).resolve().parent.parent
    if _looks_like_kb(checkout):
        return checkout
    raise SystemExit(
        f"Attempted to find a knowledge base from {Path.cwd()}. Failed "
        "due to: no ancestor carries graph/export/. Run from inside a "
        "knowledge base, set GHOSTWHEEL_BASE to its root, or give birth "
        "to one with python -m graph init.")


def _looks_like_kb(path):
    return (path / "graph" / "export").is_dir()


def cmd_validate(base_dir, write_files=True):
    """Retired verb: it refuses by name, it does not vanish."""
    del base_dir, write_files
    print("Attempted to validate source files against a bootstrap "
          "schema. Failed due to: the from-sources era is closed — the "
          "schema lives on the graph and changes through gated rounds. "
          "The health verbs are python -m graph check, corpus, and "
          "rederive (dry).", file=sys.stderr)
    return 1, None


def canon_base(base_dir, branch=None):
    """The base of a round, post-flip: the committed backup (the export).
    Default line: canon's graph/export. A named branch reads its own
    backup (graph/branches/<name>/export) — its independent line of
    truth. No database needed to read it; apply verifies the live
    database still matches it before writing anything."""
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    return restore_mod.read_export(proposal_mod.export_dir(base_dir, branch))


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


def cmd_export(base_dir):
    # the backup serializes THE DATABASE — its only source since the flip
    from . import load as load_mod
    from . import restore as restore_mod
    config = load_mod.read_config(base_dir)
    try:
        graph = restore_mod.dump_db(config)
    except Exception as exc:
        print(f"Attempted to export canon from the database "
              f"('{config['NEO4J_DATABASE']}'). Failed due to: {exc}. "
              "Is the DBMS running?", file=sys.stderr)
        return 1
    export_dir = base_dir / "graph" / "export"
    export_mod.write_export(graph, export_dir)
    print(f"Export: {export_dir.relative_to(base_dir)}/"
          f"{{{export_mod.NODES_FILE},{export_mod.EDGES_FILE}}}"
          " (from the database)")
    return 0


def cmd_restore(base_dir, database=None, from_dir=None, branch=None,
                base=None, by=None, invite=None):
    """Rebuild a database from graph/export/ alone, then read it back
    and prove byte-identity with the backup — the D55 drill.
    With --database scratch: clone canon to scratch and pin the round
    (post-flip round cut). With --from <dir> (the visibility lens design): load any
    export — e.g. a lens-scoped materialization — into a WORKSPACE
    database for inspection; requires --database, never targets live
    canon, and cuts no round. With --branch <name> --base schema-only:
    cut a new branch — an independent line of truth within this KB, born
    from canon's schema stratum alone, with its own home, backup, and
    chained log; a branch never becomes canon by flag (succession is the
    owner's ceremony)."""
    from . import load as load_mod  # deferred: needs the neo4j driver
    from . import restore as restore_mod

    if branch is not None or base is not None or by or invite:
        return _restore_branch(base_dir, branch, base, database,
                               by=by, invite=invite)

    def guard(text, **facts):
        # a run refused before any write: the record names the guard
        print(text, file=sys.stderr)
        _file_restore(base_dir, code="restore-guard", status="refused",
                      database=database, from_dir=from_dir,
                      problems=[text], **facts)
        return 1

    if from_dir and not database:
        return guard("Attempted to restore from a custom export with no "
                     "target database. Failed due to: --from loads a "
                     "workspace database and must name it with "
                     "--database — the live canon database only ever "
                     "restores from the canonical backup.")
    export_dir = (Path(from_dir) if from_dir else
                  base_dir / "graph" / "export")
    if from_dir and not export_dir.is_absolute():
        export_dir = base_dir / export_dir
    try:
        graph = restore_mod.read_export(export_dir)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return guard(str(exc))
    if not from_dir:
        from .kernel_migrate import kernel_skew
        skew = kernel_skew(graph)
        if skew:
            print(f"Advisory: {skew}", file=sys.stderr)
    config = load_mod.read_config(base_dir)
    if from_dir and database == config["NEO4J_DATABASE"]:
        return guard(f"Attempted to load {from_dir} into the live canon "
                     f"database ('{database}'). Failed due to: live canon "
                     "only ever restores from the canonical backup at "
                     "graph/export — pick a workspace database (e.g. "
                     "scratch).")
    if database:
        config["NEO4J_DATABASE"] = database
    target = config["NEO4J_DATABASE"]
    # the registry of names is the stamps: a database another knowledge
    # base holds refuses before a byte is written
    from . import proposal as proposal_mod
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(graph, base_dir)
    held, followed = workspace_mod.held_or_followed(
        config, kb, proposal_mod.line_identities(base_dir))
    if held:
        return guard(held)
    if followed:
        print(followed)
    print(f"Restoring {config['NEO4J_URI']} "
          f"(database '{config['NEO4J_DATABASE']}') from the "
          f"{'export' if from_dir else 'backup'} at "
          f"{export_dir} — no sources involved ...")
    try:
        summary = load_mod.load(graph, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:  # driver errors: auth, unreachable, etc.
        text = f"Restore failed: {exc}"
        print(text, file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials?", file=sys.stderr)
        _file_restore(base_dir, code="restore-load-failed",
                      status="failed", database=target, from_dir=from_dir,
                      problems=[text])
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
        _file_restore(base_dir, code="drill-failed", status="failed",
                      database=target, from_dir=from_dir, loaded=summary,
                      problems=problems)
        return 1
    print("DRILL PASSED — the database re-serializes byte-identical to "
          "the backup it was restored from.")
    _file_restore(base_dir, code="drill-passed", status="passed",
                  database=target, from_dir=from_dir, loaded=summary)
    from . import proposal as proposal_mod
    from . import workspace as workspace_mod
    copy_of = (_branch_copy_of(base_dir, export_dir, database, config)
               if from_dir else None)
    role = (("working-copy" if copy_of else "inspection") if from_dir
            else "working-copy" if database else "canon")
    workspace_mod.stamp(config, role,
                        proposal_mod.base_identity(graph),
                        git_ref(base_dir), branch=copy_of, kb=kb)
    if database and (not from_dir or copy_of):
        # a custom export is an inspection load, never a round cut —
        # unless it is a branch's OWN backup entering the branch's OWN
        # authoring copy: that IS the branch's round cut (the very flow
        # the branch-cut guidance prints), and the round gate reads the
        # stamp and base pin this leaves behind.
        pin_round(base_dir, graph, database, branch=copy_of)
    return 0


def _restore_branch(base_dir, branch, base, database, by=None,
                    invite=None):
    """Cut a branch: build its seed from canon's committed backup, write
    the branch's own backup, load it into the branch's database, prove
    byte-identity, and pin the branch round. The branch is a line of
    truth WITHIN this KB — hard-isolated from live canon (its target
    database can never be the canon database) and born from a declared
    base: schema-only (the schema stratum alone — a rebuild line) or
    clone-of-canon (canon's whole graph — a POCKET, declared in-band by
    who cut it and who is invited). Collates every problem before
    touching the DBMS."""
    from . import pockets as retire_mod
    retired = retire_mod.retired_problem(base_dir, branch,
                                         "cut or re-cut a working copy")
    if retired:
        print(retired, file=sys.stderr)
        _file_restore(base_dir, code="restore-guard", status="refused",
                      branch=branch, problems=[retired])
        return 1
    from . import load as load_mod
    from . import pockets as pockets_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from .extract import schema_only

    config = load_mod.read_config(base_dir)
    invite = list(invite or [])
    # Verify-all before apply-any: collate every refusal — the name lint,
    # the base check, the no-alias rule, and the existing-home guard —
    # before writing a single byte.
    problems = list(proposal_mod.branch_name_problems(
        branch, config["NEO4J_DATABASE"]))
    if base not in pockets_mod.BASES:
        problems.append(
            "Attempted to cut a branch with base "
            f"{base!r}. Failed due to: a branch is born from a declared "
            "base — schema-only (the schema stratum alone, a rebuild "
            "line) or clone-of-canon (canon's whole graph, a pocket). "
            "Pass --base schema-only or --base clone-of-canon.")
    if base == pockets_mod.CLONE_OF_CANON and not by:
        problems.append(
            f"Attempted to cut pocket '{branch}' with nobody named as "
            "cutting it. Failed due to: a pocket declares who cut it — "
            "pass --by <who> (and --invite <name> for each person who "
            "may look).")
    if base == pockets_mod.SCHEMA_ONLY and (by or invite):
        problems.append(
            f"Attempted to declare branch '{branch}' a pocket with "
            "--by/--invite. Failed due to: a pocket is a clone of canon; "
            "a schema-only branch is a rebuild line and carries no "
            "declaration. Cut with --base clone-of-canon, or drop "
            "--by/--invite.")
    if database is not None:
        problems.append(
            f"Attempted to cut branch '{branch}' with --database "
            f"'{database}'. Failed due to: a branch's database IS its "
            f"name ('{branch}') — one identity, no aliases. Drop "
            "--database.")
    if branch:
        from . import succession as succession_mod
        home = proposal_mod.branch_home(base_dir, branch)
        adopted = succession_mod.adopted_branch_problem(
            base_dir, branch, "a branch cut")
        if adopted:
            # An adopted branch's home is provenance — the generic
            # home-exists remedy ("remove it to re-cut") must never be
            # suggested for it.
            problems.append(adopted)
        elif home.exists():
            problems.append(
                f"Attempted to cut branch '{branch}'. Failed due to: its "
                f"home ({home.relative_to(base_dir)}) already exists — "
                "cutting again would overwrite its backup, base pin, and "
                "event log, stranding its applied.log and archives on a "
                "vanished base. Deleting a branch home is the owner's own "
                "act; remove it deliberately to re-cut.")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        _file_restore(base_dir, code="restore-guard", status="refused",
                      branch=branch, problems=problems)
        return 1

    target = branch  # a branch's database IS its name — no override
    try:
        canon = restore_mod.read_export(proposal_mod.export_dir(base_dir))
    except (FileNotFoundError, ValueError, OSError) as exc:
        text = ("Attempted to read canon's committed backup to seed branch "
                f"'{branch}'. Failed due to: {exc}.")
        print(text, file=sys.stderr)
        _file_restore(base_dir, code="restore-guard", status="refused",
                      branch=branch, problems=[text])
        return 1

    # the registry of names is the stamps: a branch name another
    # knowledge base already holds on this DBMS refuses before any write
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(canon, base_dir)
    held, followed = workspace_mod.held_or_followed(
        dict(config, NEO4J_DATABASE=target), kb,
        proposal_mod.line_identities(base_dir)
        | proposal_mod.line_identities(base_dir, branch))
    if held:
        print(held, file=sys.stderr)
        _file_restore(base_dir, code="restore-guard", status="refused",
                      branch=branch, problems=[held])
        return 1
    if followed:
        print(followed)
    canon_log = proposal_mod.read_applied_log(base_dir)
    canon_sequence = canon_log[-1][0] if canon_log else 0
    pocket = None
    if base == pockets_mod.CLONE_OF_CANON:
        pocket = pockets_mod.declaration(
            by, invite, proposal_mod.base_identity(canon), canon_sequence)
        seed = pockets_mod.with_declaration(canon, branch, pocket)
    else:
        seed = schema_only(canon)
    branch_export = proposal_mod.export_dir(base_dir, branch)
    # The branch's backup is born at the cut, written FROM the seed — the
    # drill then proves the branch DATABASE re-serializes to it.
    export_mod.write_export(seed, branch_export)
    config["NEO4J_DATABASE"] = target
    if pocket:
        invited = ", ".join(pocket["invited"]) or "nobody yet"
        print(f"Cutting pocket '{branch}' (database '{target}') as a clone "
              f"of canon at sequence {canon_sequence} — {len(canon.nodes)} "
              f"citizens, {len(canon.edges)} connections; cut by {by}, "
              f"invited: {invited} ...")
    else:
        print(f"Cutting branch '{branch}' (database '{target}') from "
              f"canon's schema stratum alone — {len(seed.nodes)} schema "
              f"citizens, {len(seed.edges)} schema edges; no ground facts "
              "...")
    try:
        summary = load_mod.load(seed, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:  # driver errors: auth, unreachable, etc.
        text = f"Branch cut failed: {exc}"
        print(text, file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials?", file=sys.stderr)
        _file_restore(base_dir, code="restore-load-failed",
                      status="failed", database=target, branch=branch,
                      problems=[text])
        return 1
    print(f"Loaded {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges into the branch.")
    drill = restore_mod.verify_against_backup(dumped, branch_export)
    if drill:
        for problem in drill:
            print(problem, file=sys.stderr)
        print("DRILL FAILED — the branch database was built but does not "
              "match its backup. The backup files are untouched.",
              file=sys.stderr)
        _file_restore(base_dir, code="drill-failed", status="failed",
                      database=target, branch=branch, loaded=summary,
                      problems=drill)
        return 1
    print("DRILL PASSED — the branch database re-serializes byte-identical "
          "to its freshly-written backup.")
    _file_restore(base_dir, code="drill-passed", status="passed",
                  database=target, branch=branch, loaded=summary)
    from . import workspace as workspace_mod
    workspace_mod.stamp(config, "branch",
                        proposal_mod.base_identity(seed),
                        git_ref(base_dir), branch=branch, kb=kb,
                        extra=pockets_mod.stamp_facts(pocket) if pocket
                        else None)
    pin_round(base_dir, seed, target, branch)
    # the fork annotation: where canon's log stood at this cut — the
    # fork point succession's divergence advisory enumerates from
    from datetime import datetime, timezone
    proposal_mod.write_branch_fork(base_dir, branch, {
        "base": base,
        "canon_sequence": canon_sequence,
        "canon_chain_tip": canon_log[-1][5] if canon_log else "genesis",
        "cut_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    })
    print(f"Branch '{branch}' cut. Clone its authoring copy "
          f"(python -m graph restore --from "
          f"{branch_export.relative_to(base_dir)} --database "
          f"{_authoring_database(None, branch, config)}), author there, "
          f"then run the round with --branch {branch}.")
    return 0


SEAL_REPORT_FILE = "seal-report.json"
RESTORE_REPORT_FILE = "restore-report.json"


def restore_report(base_dir, code, status, database=None, branch=None,
                   from_dir=None, loaded=None, problems=()):
    """The drill's verdict as a record: which database was rebuilt from
    what, how much landed, and whether it re-serialized faithfully —
    or, for a run refused before any write, the collated guard."""
    from . import report as report_mod
    doc = report_mod.record_header(base_dir, "restore-report", branch)
    doc.update(code=code, ref=report_mod.ref_key(code), status=status)
    if database:
        doc["database"] = database
    if from_dir:
        doc["from"] = str(from_dir)
    if loaded:
        doc["loaded"] = {"nodes": loaded["loaded_nodes"],
                         "edges": loaded["loaded_edges"]}
    if problems:
        doc["problems"] = [str(p) for p in problems]
    return doc


def _file_restore(base_dir, **kwargs):
    from . import report as report_mod
    report_mod.write_record(base_dir, RESTORE_REPORT_FILE,
                            restore_report(base_dir, **kwargs))


def cmd_verify_seal(base_dir, exam_path):
    """The grading-day handshake (D5): hash a produced exam file
    and check it against the sealed citizen in canon's backup. The
    content is never read as text — only hashed."""
    import hashlib
    import json as json_mod
    from . import report as report_mod

    path = Path(exam_path)

    def file_seal(code, status, problem=None, digest=None, matched=None,
                  candidates=()):
        # the handshake's verdict as a record: which file, what it
        # hashed to, what it matched or what canon held instead
        doc = report_mod.record_header(base_dir, "seal-report")
        doc.update(file=str(exam_path), code=code,
                   ref=report_mod.ref_key(code), status=status)
        if digest:
            doc["digest"] = digest
        if problem:
            doc["problem"] = problem
        if matched:
            doc["matched"] = matched
        if candidates:
            doc["candidates"] = list(candidates)
        report_mod.write_record(base_dir, SEAL_REPORT_FILE, doc)

    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        text = (f"Attempted to verify the seal on {exam_path}. Failed due "
                f"to: {exc}.")
        print(text, file=sys.stderr)
        file_seal("seal-file-unreadable", "unreadable", problem=text)
        return 1
    nodes_path = base_dir / "graph" / "export" / "nodes.jsonl"
    seals = []
    if nodes_path.exists():
        for line in nodes_path.read_text(encoding="utf-8").splitlines():
            record = json_mod.loads(line)
            if record["label"] == "Sealed Exam":
                seals.append(record)
    if not seals:
        text = ("Attempted to verify a seal, but canon holds no Sealed "
                "Exam citizens yet. The seal row lands via the delta path "
                "once the exam is authored and hashed.")
        print(text, file=sys.stderr)
        file_seal("seal-none", "nothing-sealed", problem=text,
                  digest=digest)
        return 1
    candidates = [{"name": record["name"],
                   "fingerprint": record["properties"].get("fingerprint",
                                                           "?")[:16],
                   "sealed_on": record["properties"].get("sealed_on", "?")}
                  for record in seals]
    for record in seals:
        if record["properties"].get("fingerprint") == digest:
            print(f"SEAL VERIFIED — {path.name} matches "
                  f"'{record['name']}' (sealed "
                  f"{record['properties'].get('sealed_on', '?')} by "
                  f"{record['properties'].get('authored_by', '?')}). "
                  "The file is byte-identical to what was sealed before "
                  "ingest began.")
            file_seal("seal-verified", "verified", digest=digest,
                      matched={"name": record["name"],
                               "sealed_on": record["properties"].get(
                                   "sealed_on", "?"),
                               "authored_by": record["properties"].get(
                                   "authored_by", "?")})
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
    file_seal("seal-broken", "broken", digest=digest,
              problem=("Either the file changed after sealing, or this "
                       "is not the sealed file. Neither is gradeable."),
              candidates=candidates)
    return 1


def engine_version():
    """The installed engine's version, for records that name what
    derived them; 'unknown' outside an installed package."""
    try:
        from importlib.metadata import version
        return version("ghostwheel")
    except Exception:
        return "unknown"


def derived_diff(base, new_graph):
    """What a re-derivation changes: the edges and machine citizens that
    leave and arrive between two graphs whose ground is identical —
    the report an owner rules a derived-layer refresh on."""
    from .ontology import MACHINE_LABELS
    from .refs import CitizenRef, connection_ref

    def edge_rows(edges):
        return [connection_ref(e).row() for e in edges]

    before, after = set(base.edges), set(new_graph.edges)
    left = sorted(before - after, key=lambda e: (
        e.type, e.from_label, str(e.from_name), e.to_label, str(e.to_name)))
    arrived = sorted(after - before, key=lambda e: (
        e.type, e.from_label, str(e.from_name), e.to_label, str(e.to_name)))
    machine_before = {k: v for k, v in base.nodes.items()
                      if k[0] in MACHINE_LABELS}
    machine_after = {k: v for k, v in new_graph.nodes.items()
                     if k[0] in MACHINE_LABELS}
    gone = sorted(set(machine_before) - set(machine_after), key=str)
    born = sorted(set(machine_after) - set(machine_before), key=str)
    changed = sorted((k for k in set(machine_before) & set(machine_after)
                      if machine_before[k] != machine_after[k]), key=str)
    return {"edges_left": edge_rows(left),
            "edges_arrived": edge_rows(arrived),
            "citizens_left": [CitizenRef(*k).row() for k in gone],
            "citizens_arrived": [CitizenRef(*k).row() for k in born],
            "citizens_changed": [CitizenRef(*k).row() for k in changed]}


def cmd_rederive(base_dir, apply=False):
    """The derived-layer refresh: re-derive canon's machine layers from
    its committed backup against the schema the graph itself carries
    and the INSTALLED engine — the maintenance verb after an engine
    change that moved a derive pass, or a ceremony that reshaped the
    schema. Dry run by default: the derived-layer diff (edges and
    machine citizens leaving and arriving) is the owner's gate report,
    and nothing is written. --apply performs the refresh as a
    first-class round: the anchor stamped with the next sequence, the
    database loaded and read back byte-identical, the backup
    re-exported, the round's record (rederive.json — the engine that
    re-derived, and the diff) chained into the event log and archived.
    The ground layer never moves here; a ground change rides the delta
    path."""
    from . import canonize as canonize_mod
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
              f"backup (graph/export). Failed due to: {exc}. The "
              "committed backup is the knowledge base — restore it from "
              "git, or give birth to a new one with python -m graph init.",
              file=sys.stderr)
        return 1
    from .kernel_migrate import kernel_skew
    skew = kernel_skew(base)
    if skew:
        print(f"rederive refused — {skew}", file=sys.stderr)
        return 1
    out_of_step = proposal_mod.log_head_divergence(base_dir, base)
    if out_of_step:
        print(f"rederive refused — {out_of_step}", file=sys.stderr)
        return 1
    pin = proposal_mod.current_dir(base_dir) / proposal_mod.BASE_FILE
    if pin.exists():
        print("rederive refused — a round is in flight "
              f"({pin.relative_to(base_dir)} pins its base), and the "
              "refresh would move the base underneath it. Finish the "
              "round (canonize --apply) or abandon it, then rerun.",
              file=sys.stderr)
        return 1
    # The schema is reconstructed FROM the graph: the committed backup
    # is the schema of record.
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
    # the anchor's stamp is what a refresh moves; compare everything else
    unstamped = export_mod.serialize(new_graph)
    if unstamped == export_mod.serialize(base):
        print(f"Canon's derived layers already match engine "
              f"{engine_version()} — nothing to refresh, nothing written.")
        return 0
    diff = derived_diff(base, new_graph)
    version = engine_version()
    print(f"Derived-layer refresh against engine {version}:")
    for key, label in (("edges_left", "edges leaving"),
                       ("edges_arrived", "edges arriving"),
                       ("citizens_left", "machine citizens leaving"),
                       ("citizens_arrived", "machine citizens arriving"),
                       ("citizens_changed", "machine citizens changing")):
        rows = diff[key]
        if not rows:
            continue
        print(f"  {label} ({len(rows)}):")
        for row in rows[:20]:
            if "type" in row:
                print(f"    ({row['from']['label']}) {row['from']['name']} "
                      f"-[:{row['type']}]-> ({row['to']['label']}) "
                      f"{row['to']['name']}")
            else:
                print(f"    ({row['label']}) {row['name']}")
        if len(rows) > 20:
            print(f"    … and {len(rows) - 20} more")
    print("  ground layer: unchanged.")
    if not apply:
        print("Dry run: nothing written. Rerun with --apply to refresh "
              "canon as a chained round.")
        return 0
    seq = proposal_mod.next_log_sequence(base_dir)
    stamp_problems = canonize_mod.stamp_ontology_anchor(new_graph, seq)
    if stamp_problems:
        print("rederive refused — the version anchor cannot be stamped; "
              "nothing was written:", file=sys.stderr)
        for problem in stamp_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(new_graph, base_dir)
    held, followed = workspace_mod.held_or_followed(
        config, kb, proposal_mod.line_identities(base_dir))
    if held:
        print(f"rederive refused — {held}", file=sys.stderr)
        return 1
    if followed:
        print(followed)
    try:
        summary = load_mod.load(new_graph, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:
        print(f"Rederive failed mid-write: {exc}. The backup files are "
              "untouched — python -m graph restore returns the live "
              "database to the last state.", file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        print("EVENT LOG NOT WRITTEN — the database read back differently "
              "than what was written (driver round-trip fault). The "
              "backup files are untouched; python -m graph restore "
              "returns the database to the last applied state.",
              file=sys.stderr)
        return 1
    export_mod.write_export(dumped, base_dir / "graph" / "export")
    # --- the event log: the refresh is a first-class round -------------
    from . import report as report_mod
    record = report_mod.record_header(base_dir, "rederive-report")
    record.update(engine=version, sequence=seq, **diff)
    record_text = json.dumps(record, ensure_ascii=False, indent=2,
                             sort_keys=True) + "\n"
    record_hash = proposal_mod.content_hash(record_text)
    current = proposal_mod.current_dir(base_dir)
    current.mkdir(parents=True, exist_ok=True)
    (current / proposal_mod.REDERIVE_FILE).write_text(record_text,
                                                      encoding="utf-8")
    base_before = proposal_mod.base_identity(base)
    base_after = proposal_mod.base_identity(dumped)
    from . import workspace as workspace_mod
    workspace_mod.stamp(config, "canon", base_after, git_ref(base_dir),
                        kb=kb)
    chain = proposal_mod.append_applied_log(
        base_dir, record_hash, base_before, base_after)
    proposal_mod.write_json(current / proposal_mod.APPLIED_FILE,
                            {"delta_hash": record_hash,
                             "base_after": base_after,
                             "applied": "derived-layer-refresh",
                             "engine": version, "chain": chain})
    archive = proposal_mod.archive_round(base_dir, record_hash)
    print(f"Refreshed canon's derived layers against engine {version}: "
          f"{summary['loaded_nodes']} nodes, {summary['loaded_edges']} "
          "edges now live; ground layer unchanged; backup re-exported "
          "from the database.")
    print(f"Round archived: {archive.relative_to(base_dir)} — event log "
          f"entry chained ({chain[:12]}); the refresh's record rides "
          "with it.")
    print("Ritual: pytest, commit the export + round archive + applied.log "
          "line in one change set.")
    return 0


def cmd_kernel_migrate(base_dir, apply=False, metaontology_path=None):
    """Migrate this canon's embedded kernel stratum to the installed
    engine's kernel — the kernel-side sibling of rederive. Dry run by
    default: report the splice and the orphan check, write nothing.
    --apply performs the splice as a first-class round: the delta
    archived with its inverse, the event log chained, the backup
    re-exported from the database. The project stratum and the ground
    stay untouched — checked after the splice, never assumed."""
    from . import canonize as canonize_mod
    from . import delta as delta_mod
    from . import kernel_migrate as km
    from . import load as load_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from .extract import derive, strip_derived
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph

    try:
        base = canon_base(base_dir)
    except FileNotFoundError as exc:
        print("Attempted to load the committed backup (graph/export). "
              f"Failed due to: {exc}. A kernel migration needs an "
              "existing canon; a fresh knowledge base seeds the current "
              "kernel at init.", file=sys.stderr)
        return 1
    out_of_step = proposal_mod.log_head_divergence(base_dir, base)
    if out_of_step:
        print(f"kernel-migrate refused — {out_of_step}", file=sys.stderr)
        return 1
    seed, findings = km.fresh_kernel(base_dir, metaontology_path)
    if seed is None:
        print("Attempted to read the installed engine's kernel. Failed "
              "due to:", file=sys.stderr)
        for finding in findings:
            print(f"  ⚠ {finding.detail}", file=sys.stderr)
        return 1
    version, _fingerprint = km.installed_kernel_identity(metaontology_path)
    ground = strip_derived(base)
    # the rename rule: names this kernel renamed are rewritten across
    # the canon BEFORE the splice — citizens, edges, Archetype rows,
    # spec bindings — and a project row renamed onto a kernel name is
    # adopted; a new name the canon already uses refuses by name
    renames = km.installed_renames(metaontology_path)
    rename_refusals = km.rename_problems(ground, renames)
    if rename_refusals:
        print("kernel-migrate refused — a renamed kernel name collides "
              "with this canon's own; nothing was written:",
              file=sys.stderr)
        for problem in rename_refusals:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1
    pre_rename = ground
    new_nodes, new_edges = km.kernel_stratum(seed)
    ground, adoptions = km.apply_renames(
        ground, renames, str(version),
        kernel_names=set(new_nodes) | set(renames.values()))
    relabeled = km.relabel_census(pre_rename, renames)
    old_nodes, old_edges = km.kernel_stratum(ground)
    if old_nodes == new_nodes and old_edges == new_edges and not relabeled:
        print(f"This canon already carries the installed kernel "
              f"({version}) — nothing to migrate.")
        return 0
    old_names = set(old_nodes)
    removed = old_names - set(new_nodes)
    # an adopted project row is replaced by the kernel's own at the
    # splice — it leaves with the old stratum and arrives with the new
    old_names |= {a["new"] for a in adoptions}
    orphans = km.orphaned_references(ground, removed, old_names)
    if orphans:
        print("kernel-migrate refused — removing these kernel names "
              "would orphan project references; nothing was written:",
              file=sys.stderr)
        for edge in orphans:
            print(f"  ⚠ ({edge.from_label}, '{edge.from_name}') "
                  f"-{edge.type}-> removed kernel name '{edge.to_name}'",
                  file=sys.stderr)
        print("Repoint or retire these references through an ordinary "
              "gated round first, then rerun the migration.",
              file=sys.stderr)
        return 1
    spliced, carried = km.splice(ground, old_names, new_nodes, new_edges)
    # the migration delta is judged against the canon as it WAS: the
    # relabels are its content, and the leak check admits exactly them
    changes = delta_mod.diff(pre_rename, spliced)
    leak = km.leaks(changes, old_names | set(new_nodes) | set(renames)
                    | set(renames.values()),
                    relabeled_labels=set(renames) | set(renames.values()),
                    adopted={a["label"] for a in adoptions}
                    | {a["new"] for a in adoptions})
    if leak:
        print("kernel-migrate refused — the splice reached beyond the "
              "kernel stratum (an engine fault, not a fault in your "
              "canon); nothing was written:", file=sys.stderr)
        for item in leak:
            print(f"  ⚠ {item}", file=sys.stderr)
        return 1
    old_version = old_nodes.get(km.KERNEL_ANCHOR, {}).get(
        "version", "unknown")
    print(f"Kernel migration: {old_version} -> {version}.")
    if relabeled:
        print(f"  renamed ({len(relabeled)}): " + ", ".join(
            f"{old} -> {renames[old]} ({count} citizen"
            f"{'s' if count != 1 else ''} relabeled)"
            for old, count in relabeled))
    for adoption in adoptions:
        keys = ", ".join(adoption["retired_spec_keys"]) or "none"
        members = (", ".join(adoption["memberships"])
                   if adoption["memberships"] else "none")
        print(f"  adopted (1): project label '{adoption['label']}' -> "
              f"{adoption['new']} — {adoption['citizens']} citizens keep "
              f"their rows; the row becomes kernel-declared; its spec "
              f"retires (keys: {keys}); extra concept bindings kept as "
              f"declared memberships: {members}")
        if adoption.get("bindings_dropped"):
            print(f"    binding{'s' if len(adoption['bindings_dropped']) != 1 else ''} to "
                  f"{', '.join(adoption['bindings_dropped'])} retired with "
                  "the spec — not a subject-matter concept, so no declared "
                  "membership can carry it; if this world needs that fact, "
                  "declare it a kind through the taxonomy ceremony.")
    for word, names in (
            ("entering", sorted(set(new_nodes) - old_names)),
            ("leaving", sorted(removed)),
            ("changed", [name for _label, name, _changes
                         in changes.nodes_changed])):
        if names:
            print(f"  {word} ({len(names)}): {', '.join(names)}")
    if carried:
        # enrichment this canon holds that the kernel does not define —
        # carried through the splice unchanged, named for the record
        riders = ", ".join(f"{name} ({', '.join(keys)})"
                           for name, keys in sorted(carried.items()))
        print(f"  carried ({len(carried)}): {riders}")
        print("  (carried = this canon's own knowledge on kernel "
              "citizens, beyond what the kernel defines — it rides "
              "the migration unchanged.)")
    print("  orphan check: clean — no project reference points at a "
          "leaving kernel name.")
    if not apply:
        print("Dry run: nothing written. Rerun with --apply to migrate.")
        return 0
    pin = proposal_mod.current_dir(base_dir) / proposal_mod.BASE_FILE
    if pin.exists():
        print("kernel-migrate refused — a round is in flight "
              f"({pin.relative_to(base_dir)} pins its base), and the "
              "migration would move the base underneath it. Finish the "
              "round (canonize --apply) or abandon it, then rerun.",
              file=sys.stderr)
        return 1
    ontology = ontology_from_graph(spliced, base_dir)
    new_graph, derive_findings = derive(ontology, spliced)
    derive_errors = [f for f in derive_findings if f.severity == SEV_ERROR]
    if derive_errors:
        print("kernel-migrate refused — re-derivation over the migrated "
              "kernel reported errors; nothing was written:",
              file=sys.stderr)
        for finding in derive_errors:
            print(f"  ⚠ {finding.file} {finding.location}: "
                  f"{finding.detail}", file=sys.stderr)
        return 1
    seq = proposal_mod.next_log_sequence(base_dir)
    stamp_problems = canonize_mod.stamp_ontology_anchor(new_graph, seq)
    if stamp_problems:
        print("kernel-migrate refused — the version anchor cannot be "
              "stamped; nothing was written:", file=sys.stderr)
        for problem in stamp_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(new_graph, base_dir)
    held, followed = workspace_mod.held_or_followed(
        config, kb, proposal_mod.line_identities(base_dir))
    if held:
        print(f"kernel-migrate refused — {held}", file=sys.stderr)
        return 1
    if followed:
        print(followed)
    try:
        summary = load_mod.load(new_graph, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:
        print(f"Migration failed mid-write: {exc}. The backup files are "
              "untouched — python -m graph restore returns the live "
              "database to the last state.", file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        print("EVENT LOG NOT WRITTEN — the database read back differently "
              "than what was written (driver round-trip fault). The "
              "backup files are untouched; python -m graph restore "
              "returns the database to the last applied state.",
              file=sys.stderr)
        return 1
    export_mod.write_export(dumped, base_dir / "graph" / "export")
    if relabeled:
        # the attribution ledger is the current record the census
        # audits: its refs move with the canon they name
        rewritten = km.rewrite_attribution_labels(base_dir, renames)
        if rewritten:
            print(f"  attribution ledger: {rewritten} row"
                  f"{'s' if rewritten != 1 else ''} rewritten under the "
                  "renamed labels.")
    # --- the event log: the migration is a first-class round ----------
    delta_text = proposal_mod.serialize_delta(changes)
    delta_hash = proposal_mod.content_hash(delta_text)
    current = proposal_mod.current_dir(base_dir)
    current.mkdir(parents=True, exist_ok=True)
    (current / proposal_mod.DELTA_FILE).write_text(delta_text,
                                                   encoding="utf-8")
    (current / proposal_mod.INVERSE_FILE).write_text(
        proposal_mod.serialize_delta(proposal_mod.invert_delta(changes)),
        encoding="utf-8")
    base_before = proposal_mod.base_identity(base)
    base_after = proposal_mod.base_identity(dumped)
    from . import workspace as workspace_mod
    workspace_mod.stamp(config, "canon", base_after, git_ref(base_dir),
                        kb=kb)
    chain = proposal_mod.append_applied_log(
        base_dir, delta_hash, base_before, base_after)
    proposal_mod.write_json(current / proposal_mod.APPLIED_FILE,
                            {"delta_hash": delta_hash,
                             "base_after": base_after,
                             "applied": "kernel-migration",
                             "kernel": version,
                             "chain": chain})
    archive = proposal_mod.archive_round(base_dir, delta_hash)
    print(f"Migrated to kernel {version}: {summary['loaded_nodes']} "
          f"nodes, {summary['loaded_edges']} edges now live; backup "
          "re-exported from the database.")
    print(f"Round archived: {archive.relative_to(base_dir)} — event log "
          f"entry chained ({chain[:12]}), inverse recorded.")
    print("Ritual: pytest, commit the export + round archive.")
    return 0


def git_ref(base_dir):
    """The repo's short HEAD ref, or 'unknown' outside a checkout —
    provenance for pins and workspace stamps, never load-bearing."""
    import subprocess
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=base_dir,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def pin_round(base_dir, graph, database, branch=None):
    """Cutting a working database starts a round: pin the base's content
    identity so drift under the round is detectable. A named branch pins
    into its own home (graph/branches/<name>/proposals/current)."""
    from . import proposal as proposal_mod
    ref = git_ref(base_dir)
    current = proposal_mod.current_dir(base_dir, branch)
    base_path = current / proposal_mod.BASE_FILE
    proposal_mod.write_json(
        base_path,
        {"base_hash": proposal_mod.base_identity(graph),
         "git_ref": ref, "database": database, "branch": branch})
    # a declaration file already here belongs to a round that was never
    # applied (an applied round's file archives with it): its links
    # would ride THIS round's delta as if declared here — say so
    leftover = current / proposal_mod.ATTRIBUTION_FILE
    if leftover.exists():
        try:
            rows = proposal_mod.read_attribution_file(base_dir, branch)
            count = f"{len(rows)} link{'s' if len(rows) != 1 else ''}"
        except ValueError:
            count = "links"
        print(f"note: {leftover.relative_to(base_dir)} carries {count} "
              "declared by a round that was never applied — this round "
              "will declare them unless you remove or rewrite the file.")
    # a prepared merge belongs to the copy it was replayed into: a fresh
    # copy holds none of it, so the record is discarded, not carried
    stale_moves = current / proposal_mod.MOVES_FILE
    if stale_moves.exists():
        stale_moves.unlink()
        print("note: a moves declaration left by a round that was never "
              "applied was discarded with the previous working copy — "
              "declare the moves again for this round if they still hold.")
    stale_merge = current / proposal_mod.MERGE_FILE
    if stale_merge.exists():
        try:
            source = proposal_mod.read_json(stale_merge).get("from")
        except ValueError:
            source = "another line"
        stale_merge.unlink()
        print(f"note: a merge prepared from {source} was discarded with "
              "the previous working copy — run python -m graph merge "
              "again to take those rounds up into this one.")
    print(f"Round cut: base pinned at {ref} "
          f"({base_path.relative_to(base_dir)})")


def _authoring_database(database, branch, config=None):
    """The authoring copy a round reads. When --database is given it
    wins; next the KB's own settings (NEO4J_SCRATCH_DATABASE — each KB
    on a shared DBMS names its own working copy); otherwise the default
    line reads 'scratch' and a branch reads its own '<name>-scratch' —
    the branch's half of the canon/scratch symmetry."""
    if database is not None:
        return database
    named = (config or {}).get("NEO4J_SCRATCH_DATABASE", "").strip()
    default = named or "scratch"
    return default if branch is None else f"{branch}-{default}"


def _branch_copy_of(base_dir, export_path, database, config):
    """The branch whose round this --from cut serves, or None. A cut is a
    branch's ROUND CUT exactly when it loads the branch's OWN backup into
    the branch's OWN authoring copy — the flow the branch-cut guidance
    prints. Every other --from load is an inspection."""
    from . import proposal as proposal_mod
    if database is None:
        return None
    branches_root = base_dir / "graph" / "branches"
    if not branches_root.is_dir():
        return None
    resolved = Path(export_path).resolve()
    for home in sorted(branches_root.iterdir()):
        if not home.is_dir():
            continue
        name = home.name
        if resolved == proposal_mod.export_dir(base_dir, name).resolve() \
                and database == _authoring_database(None, name, config):
            return name
    return None


def _working_copy_check(base_dir, config, database, branch):
    """The in-band identity gate: before a round trusts its authoring
    copy, ask the database who it is (several KBs can share one DBMS).
    Returns a refusal message or None; a pre-stamp database gets a note
    and passes — only a mismatched identity refuses."""
    from . import proposal as proposal_mod
    from . import workspace as workspace_mod

    base_pin = proposal_mod.current_dir(base_dir, branch) \
        / proposal_mod.BASE_FILE
    pinned_hash = proposal_mod.read_json(base_pin).get("base_hash") \
        if base_pin.exists() else None
    try:
        found = workspace_mod.read_stamp(config)
    except Exception:
        return None  # an unreachable database surfaces at the read proper
    if found is None:
        print(f"note: database '{database}' carries no workspace identity "
              "stamp (cut before stamps existed) — the next cut will "
              "stamp it.")
        return None
    return workspace_mod.identity_problem(found, pinned_hash, database)


def cmd_load(base_dir, database=None):
    """Retired verb: it refuses by name, it does not vanish."""
    del base_dir, database
    print("Attempted to build a database from source files. Failed due "
          "to: the from-sources era is closed — a knowledge base is "
          "born graph-native (python -m graph init) or grows through "
          "gated rounds, and python -m graph restore rebuilds any "
          "database from the committed backup.", file=sys.stderr)
    return 1


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


CHECK_REPORT_FILE = "check-report.json"
CHECK_SAMPLE = 20  # rows shown per check, on screen and on the record


def run_checks(session, check_files):
    """Every check file run against one session, as records: one row
    per check — its description, mode, row count, a capped sample, and
    the verdict (code + designer-facing ref). Pure over the session:
    the CLI prints from these rows and files them, so the screen and
    the record can never disagree."""
    from .report import ref_key
    records = []
    for path in check_files:
        text = path.read_text(encoding="utf-8")
        description, expect_empty = parse_check(text, path.stem)
        rows = list(session.run(text))
        if expect_empty:
            code = "check-passed" if not rows else "check-failed"
            status = "pass" if not rows else "fail"
            mode = "assertion"
        else:
            code, status, mode = "check-findings", "findings", "informational"
        records.append({"check": path.stem, "description": description,
                        "mode": mode, "rows": len(rows),
                        "sample": [dict(row) for row in rows[:CHECK_SAMPLE]],
                        "code": code, "ref": ref_key(code),
                        "status": status})
    return records


def check_report(base_dir, records=None, guard=None):
    from .report import record_header, ref_key
    doc = record_header(base_dir, "check-report")
    if guard is not None:
        code, problem = guard
        doc["guard"] = {"code": code, "ref": ref_key(code),
                        "problem": problem}
        return doc
    doc["checks"] = list(records or [])
    doc["counts"] = {"checks": len(doc["checks"]),
                     "failed": sum(1 for r in doc["checks"]
                                   if r["status"] == "fail"),
                     "findings": sum(r["rows"] for r in doc["checks"]
                                     if r["status"] == "findings")}
    return doc


def cmd_check(base_dir, driver_factory=None):
    """Run every canned check against the live store and record the
    verdicts. ``driver_factory`` (the neo4j driver constructor by
    default) is injectable so the CLI's orchestration is provable
    without a driver installed — the suite is DB-free by doctrine."""
    from . import load as load_mod
    from . import report as report_mod

    def file_check(**kwargs):
        # the durable record beside the screen: what was checked and
        # how it came out, PASS rows included; a run that never reached
        # the store records the guard that stopped it
        report_mod.write_record(base_dir, CHECK_REPORT_FILE,
                                check_report(base_dir, **kwargs))

    checks_dir = base_dir / "graph" / "cypher" / "checks"
    check_files = sorted(checks_dir.glob("*.cypher"))
    if not check_files:
        text = f"No checks found in {checks_dir}"
        print(text, file=sys.stderr)
        file_check(guard=("check-none", text))
        return 2
    config = load_mod.read_config(base_dir)
    if driver_factory is None:
        from neo4j import GraphDatabase  # deferred: only DB access needs it
        driver_factory = GraphDatabase.driver
    try:
        driver = driver_factory(
            config["NEO4J_URI"],
            auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
        with driver, driver.session(
                database=config["NEO4J_DATABASE"]) as session:
            records = run_checks(session, check_files)
    except Exception as exc:
        text = f"Check run failed: {exc}"
        print(text, file=sys.stderr)
        print("Is the Neo4j Desktop DBMS running, and does .env match its "
              "credentials? (see .env.example)", file=sys.stderr)
        file_check(guard=("check-unreachable", text))
        return 1
    for record in records:
        if record["mode"] == "assertion":
            print(f"\n== {record['check']}: {record['status'].upper()} "
                  f"(assertion; {record['rows']} rows)")
        else:
            print(f"\n== {record['check']}: {record['rows']} findings")
        print(f"   {record['description']}")
        for row in record["sample"]:
            print(f"   {row}")
        if record["rows"] > CHECK_SAMPLE:
            print(f"   ... and {record['rows'] - CHECK_SAMPLE} more")
    failed_assertions = [r["check"] for r in records
                         if r["status"] == "fail"]
    finding_rows = sum(r["rows"] for r in records
                       if r["status"] == "findings")
    file_check(records=records)
    print(f"\nChecks complete: {len(check_files)} checks, "
          f"{len(failed_assertions)} failed assertions, "
          f"{finding_rows} finding rows (informational)")
    if failed_assertions:
        print(f"FAILED: {', '.join(failed_assertions)} — expected empty; "
              "rows indicate an ETL/graph integrity bug.", file=sys.stderr)
        return 1
    return 0


def cmd_corpus(base_dir):
    """Re-check every owner-approved floor (the regression corpus): each floor's guard
    must still exist in the suite and still pass. Reds name the
    approval they break; a vanished guard is a red, never a silence."""
    from . import corpus as corpus_mod
    from . import report as report_mod

    def file_corpus(**kwargs):
        report_mod.write_record(base_dir, corpus_mod.CORPUS_REPORT_FILE,
                                corpus_mod.corpus_report(base_dir, **kwargs))

    floors = corpus_mod.load_floors(corpus_mod.floors_path(base_dir))
    if not floors:
        print(corpus_mod.render_report([], [], []))
        file_corpus(records=[])
        return 0
    collected = corpus_mod.collect_guards(base_dir)
    if not collected:
        text = ("Attempted to re-collect the corpus's guards with pytest. "
                "Failed due to: the collection returned nothing — the "
                "test suite itself is not runnable here; fix that before "
                "trusting any floor.")
        print(text, file=sys.stderr)
        file_corpus(records=[], guard_problem=text)
        return 1
    failed_ids = corpus_mod.failed_floor_ids(base_dir, floors, collected)
    records = corpus_mod.floor_records(floors, collected, failed_ids)
    missing = [r["problem"] for r in records
               if r["status"] == corpus_mod.FLOOR_GUARD_MISSING]
    failures = [r["problem"] for r in records
                if r["status"] == corpus_mod.FLOOR_FAILED]
    print(corpus_mod.render_report(floors, missing, failures))
    file_corpus(records=records)
    return 1 if (missing or failures) else 0


def cmd_delta(base_dir, database, sync_bodies=False, branch=None):
    """The agentic changeset: diff the scratch database against the
    base (the export backup), lint additions against the machine
    layers, and write the reviewable report (see design/agentic-etl.md).
    With --branch <name>: the base and round files are the branch's own,
    and the authoring copy defaults to <name>-scratch — the branch's half
    of the ceremony surface."""
    if branch is not None:
        from . import pockets as retire_mod
        retired = retire_mod.retired_problem(base_dir, branch,
                                             "draft a round")
        if retired:
            print(retired, file=sys.stderr)
            return 1
    from . import delta as delta_mod
    from . import load as load_mod

    from . import proposal as proposal_mod

    try:
        base = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    from .kernel_migrate import kernel_skew
    skew = kernel_skew(base)
    if skew:
        print(f"Advisory: {skew}", file=sys.stderr)
    config = load_mod.read_config(base_dir)
    database = _authoring_database(database, branch, config)
    # A branch may never read live canon as its authoring source, and an
    # adopted branch is provenance, not a working line.
    if branch is not None:
        from . import succession as succession_mod
        read_problem = proposal_mod.authoring_read_problem(
            database, config["NEO4J_DATABASE"])
        adopted = succession_mod.adopted_branch_problem(
            base_dir, branch, "a delta round")
        for problem in filter(None, (read_problem, adopted)):
            print(problem, file=sys.stderr)
        if read_problem or adopted:
            return 1
    config["NEO4J_DATABASE"] = database
    identity = _working_copy_check(base_dir, config, database, branch)
    if identity:
        print(identity, file=sys.stderr)
        return 1
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
    from . import report as report_mod

    # A prepared merge's replayed moves were already performed in the
    # copy: the diff runs against the base WITH those moves applied, so
    # a rename never reads as remove+add and its re-pointed derived
    # edges never read as authored — and the moves ride the proposal so
    # the approval hash covers them.
    merge_moves = []
    merge_current = proposal_mod.current_dir(base_dir, branch) / \
        proposal_mod.MERGE_FILE
    diff_base = base
    merge_move_problems = []
    if merge_current.exists():
        try:
            merge_moves = list(proposal_mod.read_json(merge_current)
                               .get("replayed_moves") or [])
        except ValueError:
            merge_moves = []
        if merge_moves:
            from . import moves as merge_moves_mod
            for moved_round in merge_moves:
                diff_base, probs = merge_moves_mod.apply_moves(
                    diff_base, moved_round,
                    merge_moves_mod.kernel_names(diff_base))
                merge_move_problems.extend(probs)
    changes = delta_mod.diff(diff_base, scratch)
    changes.merge_moves = merge_moves
    stitch_problem = None
    try:
        changes.stitch = proposal_mod.read_stitch(base_dir, branch)
    except (ValueError, KeyError) as exc:
        stitch_rel = proposal_mod.current_dir(base_dir,
                                              branch).relative_to(base_dir)
        stitch_problem = report_mod.Verdict(
            code="stitch-file-unreadable",
            message=(
                "Attempted to read the round's stitch file "
                f"({stitch_rel}/{proposal_mod.STITCH_FILE}). "
                f"Failed due to: {exc}"),
            remedy="Fix or remove the stitch file, then re-run the delta.",
            data={"path": f"{stitch_rel}/{proposal_mod.STITCH_FILE}"})
    # declared moves: a rename of the world's own label or a re-homing
    # of citizens under a kind — filed in moves.json, embedded in the
    # proposal so the approval covers them, itemized at the gate
    moves_problem = None
    try:
        changes.moves = proposal_mod.read_moves(base_dir, branch)
    except (ValueError, KeyError) as exc:
        moves_rel = proposal_mod.current_dir(base_dir,
                                             branch).relative_to(base_dir)
        moves_problem = report_mod.Verdict(
            code="moves-file-unreadable", message=str(exc),
            remedy="Fix or remove the moves file, then re-run the delta.",
            data={"path": f"{moves_rel}/{proposal_mod.MOVES_FILE}"})
    # recorded attribution: the round's declared claim→citizen links
    # ride inside the changeset, so the approval covers them and the
    # gate shows them being ruled
    attribution_problem = None
    try:
        changes.attribution = proposal_mod.read_attribution_file(
            base_dir, branch)
    except (ValueError, KeyError) as exc:
        attribution_rel = proposal_mod.current_dir(
            base_dir, branch).relative_to(base_dir)
        attribution_problem = report_mod.Verdict(
            code="attribution-file-unreadable",
            message=str(exc),
            remedy="Fix or remove the attribution file, then re-run "
                   "the delta.",
            data={"path": f"{attribution_rel}/"
                          f"{proposal_mod.ATTRIBUTION_FILE}"})
    violations = delta_mod.lint_verdicts(changes, diff_base)
    ceremony_items = delta_mod.ceremony_records(changes, diff_base)[0]
    from . import moves as moves_mod
    move_items, move_refusals = moves_mod.move_records(changes, diff_base)
    ceremony_items += move_items
    violations += move_refusals
    # the replayed moves itemize as ceremony lines, per source round in
    # order, judged against the base as it evolves — the owner rules on
    # the renames the merge took up, presented as what they are
    if changes.merge_moves:
        evolving = base
        for moved_round in changes.merge_moves:
            stub = delta_mod.Delta()
            stub.moves = moved_round
            merged_items, merged_refusals = moves_mod.move_records(
                stub, evolving)
            ceremony_items += merged_items
            violations += merged_refusals
            evolving, _probs = moves_mod.apply_moves(
                evolving, moved_round, moves_mod.kernel_names(evolving))
        for problem in merge_move_problems:
            violations.append(report_mod.Verdict(
                code="merge-moves-failed",
                message=("Attempted to apply the prepared merge's "
                         f"replayed moves for the gate. Failed due to: "
                         f"{problem}"),
                remedy="Re-cut the copy and merge again."))
    if moves_problem:
        violations.append(moves_problem)
    if stitch_problem:
        violations.append(stitch_problem)
    if attribution_problem:
        violations.append(attribution_problem)
    violations += delta_mod.stitch_verdicts(changes, scratch)
    violations += delta_mod.attribution_verdicts(changes, diff_base)
    violations += delta_mod.body_sync_verdicts(scratch, base_dir)
    # the floor receipt: a cited fingerprint must match its file's bytes
    violations += delta_mod.fingerprint_verdicts(changes, base_dir)
    # dependencies and bookmarks: the shape of a pin and a foreign citation,
    # then the pin against its checkout and the citation against what
    # lives there; every round hears a pin that has fallen behind
    from . import dependencies as dependencies_mod
    violations += dependencies_mod.gate_verdicts(changes, scratch)
    dependency_refusals = dependencies_mod.resolution_verdicts(
        changes, scratch, config)
    violations += dependency_refusals
    dependency_advisories = dependencies_mod.drift_advisories(
        scratch, config,
        skip={v.subject.name for v in dependency_refusals
              if v.subject is not None
              and v.subject.label == dependencies_mod.KERNEL_DEPENDENCY_LABEL})
    # artifacts: locations read, grades earned, depictions and
    # interpretations well-formed, resolvers bound
    from . import artifacts as artifacts_mod
    violations += artifacts_mod.gate_verdicts(changes, scratch, base_dir)
    # the receipt staleness guard: a round that authors a quote its
    # source does not contain refuses; one that touches a citizen whose
    # existing quote went stale hears about it (advisory — honesty,
    # never a build break) while the owner is already looking
    from . import receipts as receipts_mod
    receipt_findings = receipts_mod.receipt_verdicts(changes, base,
                                                     base_dir)
    violations += [v for v in receipt_findings
                   if v.severity != report_mod.ADVISORY]
    receipt_advisories = [v for v in receipt_findings
                          if v.severity == report_mod.ADVISORY]
    # The orphan-procedure check: a registered procedure file with no citizen in scratch is
    # invisible to the body-sync scan (which walks existing nodes) — the
    # roster check names it before the round reaches canonize.
    from .extract import gate_roster_findings
    from .ontology import ontology_from_graph
    # The schema is reconstructed FROM canon's backup (the schema-delta ceremony): `base` is the
    # committed graph read above; ontology.yaml is bootstrap-only now.
    ontology = ontology_from_graph(base, base_dir)
    roster_advisories = []
    if ontology is not None:
        advisory = bool(branch)
        # a typed pass-through: the finding's own code, remedy, and
        # particulars ride into the gate verdict (no string collapse)
        roster_verdicts = [
            report_mod.Verdict(
                code=f.verdict_code, message=f.detail, remedy=f.remedy,
                severity=(report_mod.ADVISORY if advisory
                          else report_mod.REFUSAL),
                data={"file": f.file, "location": f.location,
                      "category": str(f.category)})
            for f in gate_roster_findings(scratch, base_dir)]
        if advisory:
            # A branch mid-rebuild is incomplete by design: the roster
            # census blocks only a finished line. Advisory here; full
            # strength again when the branch stands for succession.
            roster_advisories = roster_verdicts
        else:
            violations += roster_verdicts
        # The answer keys: every key this round touches — the key itself,
        # its CHECKS edge, or the body of the program it holds still — is
        # re-run over the round's own graph. Refusal on the live line,
        # advisory on a branch (a program may land before its table).
        from . import answer_keys as answer_keys_mod
        key_verdicts = answer_keys_mod.gate_verdicts(
            changes, scratch, ontology, base_dir, advisory=advisory)
        if advisory:
            roster_advisories = roster_advisories + key_verdicts
        else:
            violations += key_verdicts
    # The stitch mechanism: preview the stitch's landing against the graph this round
    # will actually produce (changeset applied, machine layers
    # re-derived) — the diff gate must never approve a connection that
    # stitches to nothing
    # The landing preview: the graph this round will actually produce —
    # changeset applied, moves performed, machine layers re-derived. The
    # stitch is checked against it, and every derived connection that
    # LEAVES is itemized: a citizen that vanishes takes its memberships
    # and its resolved citations with it, and the owner rules on that
    # consequence rather than discovering it in a count.
    derived_advisories = []
    if ontology is not None and not violations:
        from .extract import derive, strip_derived
        from .ontology import is_derived_edge
        preview = strip_derived(base)
        if changes.merge_moves:
            for moved_round in changes.merge_moves:
                preview, _ = moves_mod.apply_moves(
                    preview, moved_round, moves_mod.kernel_names(preview))
        if not proposal_mod.apply_delta(preview, changes):
            if changes.moves and not move_refusals:
                preview, _ = moves_mod.apply_moves(
                    preview, changes.moves, moves_mod.kernel_names(base))
            derived_preview, preview_findings = derive(
                ontology_from_graph(preview, base_dir), preview)
            if changes.stitch:
                violations += [
                    report_mod.Verdict(code="stitch-landing", message=problem)
                    for problem in proposal_mod.apply_stitch(
                        derived_preview, changes.stitch)]
            # what re-derivation would refuse at apply refuses here: an
            # unknown label, a citation that resolves to nothing or to
            # several (a lost connection is not a departure) — except the
            # roster on a branch, which stays advisory mid-rebuild
            from .ontology import Category as _Category
            from .ontology import ERROR as _ERROR
            violations += [
                report_mod.Verdict(code=f.verdict_code, message=f.detail,
                                   remedy=f.remedy)
                for f in preview_findings
                if f.severity == _ERROR
                and not (branch and f.category == _Category.ROSTER)]
            # a birth is never silent: every citizen the round's
            # derivation would create by reference is itemized here,
            # an advisory beside the changeset
            derived_advisories += [
                report_mod.Verdict(code=f.code, severity=report_mod.ADVISORY,
                                   message=f.detail, remedy=f.remedy)
                for f in preview_findings
                if f.code == "citizen-born-by-reference"]
            before = {e for e in base.edges if is_derived_edge(e)}
            after = {e for e in derived_preview.edges if is_derived_edge(e)}
            leaving = sorted(before - after,
                             key=lambda e: (e.type, e.from_label,
                                            str(e.from_name), str(e.to_name)))
            by_type = {}
            for edge in leaving:
                by_type.setdefault(edge.type, []).append(edge)
            for edge_type, edges in sorted(by_type.items()):
                sample = "; ".join(
                    f"({e.from_label}) {e.from_name} -> ({e.to_label}) "
                    f"{e.to_name}" for e in edges[:3])
                derived_advisories.append(report_mod.Verdict(
                    code="derived-edges-leaving",
                    severity=report_mod.ADVISORY,
                    message=(f"{len(edges)} derived {edge_type} connection"
                             f"{'s' if len(edges) != 1 else ''} leave with "
                             f"this round ({sample}"
                             f"{'; …' if len(edges) > 3 else ''}) — the "
                             "machine layer re-derives them from the facts "
                             "you changed; if they should stay, the facts "
                             "they hung on must stay."),
                    remedy="Keep the facts those connections hang on, or "
                           "approve their leaving knowingly.",
                    data={"type": edge_type, "count": len(edges),
                          "examples": [
                              {"from": {"label": e.from_label,
                                        "name": e.from_name},
                               "to": {"label": e.to_label,
                                      "name": e.to_name}}
                              for e in edges[:10]]}))
    # one report model, two renderings: the markdown the approver reads
    # and the same facts as records (verdict codes, subject refs,
    # remedies) for machine consumers. The JSON is a rendering, not a
    # frozen artifact — re-derivable from the pinned changeset and base.
    # The markdown lands FIRST: if the changeset later refuses to
    # serialize, the report that names the offending row is already on
    # disk and on screen.
    # a prepared merge: every citizen changed on both lines is named
    # while the owner is already looking — the copy's version lands
    merge_advisories = []
    merge_path = proposal_mod.current_dir(base_dir, branch) / \
        proposal_mod.MERGE_FILE
    if merge_path.exists():
        from . import merge as merge_mod
        try:
            merge_advisories = merge_mod.contested_advisories(
                proposal_mod.read_json(merge_path))
        except ValueError:
            merge_advisories = []
    report_model = delta_mod.build_report(
        changes, violations, ceremony_items,
        roster_advisories + receipt_advisories + dependency_advisories
        + merge_advisories + derived_advisories)
    report = report_mod.render_markdown(report_model)
    reports_dir = base_dir / "graph" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "delta.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report: {report_path.relative_to(base_dir)}")
    # the proposal document: the machine-readable changeset whose hash
    # IS the proposal's id — what `approve` freezes and apply replays
    delta_text = proposal_mod.serialize_delta(changes)
    delta_id = proposal_mod.content_hash(delta_text)
    json_path = reports_dir / "delta-report.json"
    json_path.write_text(
        report_mod.render_json(report_model, proposal_id=delta_id,
                               kb=refs_mod.kb_name(base, base_dir),
                               branch=branch),
        encoding="utf-8")
    print(f"Report records: {json_path.relative_to(base_dir)}")
    delta_path = proposal_mod.current_dir(base_dir, branch) \
        / proposal_mod.DELTA_FILE
    delta_path.parent.mkdir(parents=True, exist_ok=True)
    delta_path.write_text(delta_text, encoding="utf-8")
    print(f"Proposal id: {delta_id[:12]} "
          f"({delta_path.relative_to(base_dir)})")
    base_pin = proposal_mod.current_dir(base_dir, branch) \
        / proposal_mod.BASE_FILE
    if base_pin.exists():
        pinned = proposal_mod.read_json(base_pin)
        if pinned.get("base_hash") != proposal_mod.base_identity(base):
            print("WARNING: the base has moved under this round — the "
                  "sources changed since scratch was cut. Drafting may "
                  "continue, but apply will refuse: re-cut scratch to "
                  "re-baseline and re-review.", file=sys.stderr)
    return 1 if violations else 0


def cmd_canonize(base_dir, database, apply, branch=None):
    """Apply the approved delta to canon — graph-native. The dry
    run shows the changeset and freeze status; --apply verifies
    everything, applies the pinned changeset to the ground layer in
    memory, re-derives every machine layer, loads the result into the
    target database, re-exports the backup from it, and appends the
    chained event log. No file is edited; the graph is primary.
    With --branch <name>: the base, round files, target database, backup,
    and log are all the branch's own — and the hard guard refuses if the
    branch's target database is the KB's live canon (a branch never
    becomes canon by flag; succession is the owner's ceremony)."""
    if branch is not None:
        from . import pockets as retire_mod
        retired = retire_mod.retired_problem(
            base_dir, branch, "canonize a round")
        if retired:
            print(retired, file=sys.stderr)
            return 1
    from . import canonize as canonize_mod
    from . import delta as delta_mod
    from . import load as load_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from .extract import derive, strip_derived
    from .ontology import Category
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph

    config = load_mod.read_config(base_dir)
    database = _authoring_database(database, branch, config)
    live_canon_database = config["NEO4J_DATABASE"]
    def bail(code, message, items=(), remedy="", findings=()):
        # the refusal, twice: the stderr block above it prints exactly
        # as it always has; this leaves the same facts as a durable
        # record (graph/reports/canonize-refusal.json). Findings ride
        # as their own rows beside the prose items — a typed
        # pass-through, never a string collapse.
        from . import report as report_mod
        data = {}
        if items:
            data["items"] = [str(i) for i in items]
        if findings:
            data["findings"] = [f.row() for f in findings]
        canonize_mod.write_refusal_report(
            base_dir, branch,
            [report_mod.Verdict(code=code, message=str(message),
                                remedy=remedy, data=data)])
        return 1

    # The target line's canon database: live canon for the default line;
    # the branch's own database (= its name) for a branch. The hard guard
    # — a branch can NEVER write to live canon, nor read it as its
    # authoring source — is collated and checked FIRST, before the base is
    # even read, so a canon-named or canon-sourced branch never gets there.
    if branch is None:
        target_database, guard = live_canon_database, []
    else:
        target_database, guard = proposal_mod.branch_target_database(
            branch, live_canon_database)
        from . import succession as succession_mod
        read_problem = proposal_mod.authoring_read_problem(
            database, live_canon_database)
        adopted = succession_mod.adopted_branch_problem(
            base_dir, branch, "a canonize round")
        guard = list(guard) + [p for p in (read_problem, adopted) if p]
    if guard:
        header = ("--apply refused — a branch is hard-isolated from canon:"
                  if apply else
                  "REFUSED — a branch is hard-isolated from canon:")
        print(header, file=sys.stderr)
        for problem in guard:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("branch-isolation", header, guard)
    try:
        base = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        text = ("Attempted to load the schema from the committed "
                f"backup ({proposal_mod.export_dir(base_dir, branch).relative_to(base_dir)}). "
                f"Failed due to: {exc}. The committed backup is the "
                "knowledge base — restore it from git, or give birth to "
                "a new one with python -m graph init.")
        print(text, file=sys.stderr)
        return bail("backup-unreadable", text)
    from .kernel_migrate import kernel_skew
    skew = kernel_skew(base)
    if skew:
        # Building more canon on a stale kernel deepens the skew, so the
        # default line refuses to apply. A branch canon has no migration
        # path of its own (it migrates when its line succeeds canon), so
        # mid-rebuild the finding stays advisory.
        if apply and branch is None:
            print(f"--apply refused — {skew}", file=sys.stderr)
            return bail("kernel-skew", skew)
        print(f"Advisory: {skew}", file=sys.stderr)
    # The chain's head against the backup it would build on: an entry
    # chained off a stale predecessor corrupts the tamper-evident chain
    # quietly, so the disagreement refuses by name before any write.
    out_of_step = proposal_mod.log_head_divergence(base_dir, base, branch)
    if out_of_step:
        if apply:
            print(f"--apply refused — {out_of_step}", file=sys.stderr)
            return bail("log-head-diverged", out_of_step,
                        remedy="Restore the log lines the backup describes, "
                               "or the backup the log describes, then rerun.")
        print(f"Advisory: {out_of_step}", file=sys.stderr)
    config = dict(config)
    config["NEO4J_DATABASE"] = database
    identity = _working_copy_check(base_dir, config, database, branch)
    if identity:
        print(("--apply refused: " if apply else "REFUSED: ") + identity,
              file=sys.stderr)
        return bail("workspace-identity", identity)
    try:
        scratch = delta_mod.read_graph(config)
    except Exception as exc:
        text = f"cannot read '{database}': {exc}"
        print(text, file=sys.stderr)
        return bail("scratch-unreadable", text)
    merge_current = proposal_mod.current_dir(base_dir, branch) / \
        proposal_mod.MERGE_FILE
    merge_moves = []
    diff_base = base
    if merge_current.exists():
        try:
            merge_moves = list(proposal_mod.read_json(merge_current)
                               .get("replayed_moves") or [])
        except ValueError:
            merge_moves = []
        if merge_moves:
            from . import moves as merge_moves_mod
            for moved_round in merge_moves:
                diff_base, _probs = merge_moves_mod.apply_moves(
                    diff_base, moved_round,
                    merge_moves_mod.kernel_names(diff_base))
    changes = delta_mod.diff(diff_base, scratch)
    changes.merge_moves = merge_moves
    try:
        changes.stitch = proposal_mod.read_stitch(base_dir, branch)
    except (ValueError, KeyError) as exc:
        text = f"REFUSED: the round's stitch file is unreadable — {exc}"
        print(text, file=sys.stderr)
        return bail("stitch-file-unreadable", text)
    try:
        changes.attribution = proposal_mod.read_attribution_file(
            base_dir, branch)
    except (ValueError, KeyError) as exc:
        text = ("REFUSED: the round's attribution file is unreadable — "
                f"{exc}")
        print(text, file=sys.stderr)
        return bail("attribution-file-unreadable", text)
    # judged against the SAME base the gate judged — the moved one for
    # a merge round — so what the gate admitted, apply lands: a
    # post-approval refusal on an approved diff is the one wrong answer
    violations = delta_mod.lint(changes, diff_base)
    violations += delta_mod.lint_stitch(changes, scratch)
    violations += [str(v)
                   for v in delta_mod.attribution_verdicts(changes,
                                                           diff_base)]
    if violations:
        text = ("REFUSED: the delta has ground-facts lint violations — "
                "fix scratch first (python -m graph delta):")
        print(text, file=sys.stderr)
        for violation in violations:
            print(f"  ⚠ {violation}", file=sys.stderr)
        return bail("ground-facts-lint", text, violations,
                    remedy="Fix scratch first (python -m graph delta).")

    current = proposal_mod.current_dir(base_dir, branch)
    approval_path = current / proposal_mod.APPROVAL_FILE
    delta_path = current / proposal_mod.DELTA_FILE
    target_label = "canon" if branch is None else f"branch '{branch}'"
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
        if changes.attribution:
            counts += (f"; {len(changes.attribution)} attribution links "
                       "recorded")
        print(f"Changeset vs {target_label}: {counts}")
        print("Approval on record: "
              + ("yes" if approval_path.exists() else
                 "no — review at the diff gate, then python -m graph "
                 "approve"))
        print(f"Dry run — python -m graph canonize --apply applies the "
              f"approved changeset to {target_label}.")
        canonize_mod.clear_refusal_report(base_dir)
        return 0

    # --- the approval freeze: apply replays only what was approved ------
    if not approval_path.exists():
        text = ("no approval on record for this round. Review the delta "
                "at the diff gate, then record the approval "
                "(python -m graph approve).")
        print("--apply refused: " + text, file=sys.stderr)
        return bail("approval-missing", text,
                    remedy="Review at the diff gate, then python -m "
                           "graph approve.")
    approval = proposal_mod.read_json(approval_path)
    pinned_text = delta_path.read_text(encoding="utf-8") \
        if delta_path.exists() else None
    if pinned_text is None or \
            proposal_mod.content_hash(pinned_text) != approval["delta_hash"]:
        text = ("the proposal document is missing or does not match "
                "the approved hash — the round's artifacts were tampered "
                "with after approval. Re-run python -m graph delta and "
                "re-review.")
        print("--apply refused: " + text, file=sys.stderr)
        return bail("proposal-tampered", text,
                    remedy="Re-run python -m graph delta and re-review.")
    if approval.get("base_hash") and \
            approval["base_hash"] != proposal_mod.base_identity(base):
        text = ("the base has moved since approval — canon's backup "
                "changed under the round. Re-cut scratch (python -m "
                "graph restore --database scratch), re-review, and "
                "re-approve.")
        print("--apply refused: " + text, file=sys.stderr)
        return bail("base-moved", text,
                    remedy="Re-cut scratch, re-review, re-approve.")
    drift = proposal_mod.divergence(
        proposal_mod.parse_delta(pinned_text), changes)
    if drift:
        text = ("scratch has moved since approval — the divergence, "
                "named:")
        print("--apply refused: " + text, file=sys.stderr)
        for problem in drift:
            print(f"  ⚠ {problem}", file=sys.stderr)
        print("Re-review (python -m graph delta) and re-approve.",
              file=sys.stderr)
        return bail("scratch-drift", text, drift,
                    remedy="Re-review (python -m graph delta) and "
                           "re-approve.")

    # --- the target database must still equal the backup it came from --
    target_export = proposal_mod.export_dir(base_dir, branch)
    target_config = dict(config)
    target_config["NEO4J_DATABASE"] = target_database
    try:
        live = restore_mod.dump_db(target_config)
    except Exception as exc:
        text = (f"cannot read the {target_label} database "
                f"('{target_database}'): {exc}")
        print("--apply refused: " + text, file=sys.stderr)
        return bail("database-unreadable", text)
    live_drift = restore_mod.verify_against_backup(live, target_export)
    if live_drift:
        text = (f"the {target_label} database no longer matches the "
                "backup it was restored from — it moved outside the "
                "delta path:")
        print("--apply refused: " + text, file=sys.stderr)
        for problem in live_drift:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("database-drift", text, live_drift)

    # --- apply the PINNED artifact to the ground layer, then re-derive -
    pinned_delta = proposal_mod.parse_delta(pinned_text)
    ground = strip_derived(base)
    if pinned_delta.merge_moves:
        # a merge round's changeset was diffed against the base WITH
        # the replayed moves applied, so those moves land first — the
        # pinned copy of them, under the approval's hash
        from . import moves as moves_mod
        merge_problems = []
        for moved_round in pinned_delta.merge_moves:
            ground, probs = moves_mod.apply_moves(
                ground, moved_round, moves_mod.kernel_names(ground))
            merge_problems.extend(probs)
        if merge_problems:
            text = ("the merge's replayed moves cannot be performed; "
                    "nothing was written:")
            print("--apply refused — " + text, file=sys.stderr)
            for problem in merge_problems:
                print(f"  ⚠ {problem}", file=sys.stderr)
            return bail("merge-moves-failed", text, merge_problems)
    problems = proposal_mod.apply_delta(ground, pinned_delta)
    if problems:
        text = "preconditions failed; nothing was written:"
        print("--apply refused — " + text, file=sys.stderr)
        for problem in problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("precondition-failed", text, problems)
    # The declared moves land after the authored changeset (spoken in
    # the old names, as scratch was) and before the stitch and
    # re-derivation — the same transform the kernel's renames ride
    if pinned_delta.moves:
        from . import moves as moves_mod
        _items, move_refusals = moves_mod.move_records(pinned_delta,
                                                       strip_derived(base))
        move_problems = [str(v) for v in move_refusals]
        if not move_problems:
            ground, move_problems = moves_mod.apply_moves(
                ground, pinned_delta.moves,
                moves_mod.kernel_names(strip_derived(base)))
        if move_problems:
            text = "the declared moves cannot be performed; nothing was written:"
            print("--apply refused — " + text, file=sys.stderr)
            for problem in move_problems:
                print(f"  ⚠ {problem}", file=sys.stderr)
            return bail("move-failed", text, move_problems)
    # The schema is reconstructed from the POST-apply ground: a ceremony
    # round's schema changes are already in `ground` here, and derive
    # must see the schema the round produces, not the one it started
    # from. For a round with no schema changes the two are identical.
    ontology = ontology_from_graph(ground, base_dir)
    new_graph, derive_findings = derive(ontology, ground)
    derive_errors = [f for f in derive_findings if f.severity == SEV_ERROR]
    if branch:
        # The roster census (every registered program file has its
        # citizen) is a property of a finished line; a branch
        # mid-rebuild fails it by design. Advisory for branch applies —
        # it blocks again when the branch stands for succession.
        roster = [f for f in derive_errors
                  if f.category == Category.ROSTER]
        derive_errors = [f for f in derive_errors
                         if f.category != Category.ROSTER]
        if roster:
            print(f"Advisory: {len(roster)} registered program files "
                  f"have no citizen on branch '{branch}' yet — a "
                  "mid-rebuild branch is incomplete by design; the "
                  "roster check blocks only a finished line and must "
                  "be clean before this branch can succeed canon.")
    if derive_errors:
        text = "re-derivation reported errors; nothing was written:"
        print("--apply refused — " + text, file=sys.stderr)
        items = [f"{f.file} {f.location}: {f.detail}"
                 for f in derive_errors]
        for item in items:
            print(f"  ⚠ {item}", file=sys.stderr)
        return bail("derive-error", text, items, findings=derive_errors)
    # derived connections that leave with this round are named, never
    # discovered in a count
    from .ontology import is_derived_edge
    leaving = {e for e in base.edges if is_derived_edge(e)} - {
        e for e in new_graph.edges if is_derived_edge(e)}
    if leaving:
        by_type = {}
        for edge in leaving:
            by_type[edge.type] = by_type.get(edge.type, 0) + 1
        print("  derived connections leaving with this round: " + ", ".join(
            f"{n} {t}" for t, n in sorted(by_type.items())) + ".")
    # The stitch mechanism: the stitch lands IN MEMORY, after re-derivation births the
    # round's new citizens and before anything is written — same
    # verify-all-before-apply-any window as everything above
    stitch_problems = proposal_mod.apply_stitch(new_graph,
                                                pinned_delta.stitch)
    if stitch_problems:
        text = "the stitch cannot land; nothing was written:"
        print("--apply refused — " + text, file=sys.stderr)
        for problem in stitch_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("stitch-landing", text, stitch_problems)

    # --- stamp the version anchor: the project ontology's version IS the
    # event-log sequence, so a fresh connection's version moves with the
    # graph, not with a file (the schema-delta ceremony, owner ruling 2026-08-03); restamp the
    # fingerprint from the ground schema stratum too. Verify-all before
    # apply-any: a missing anchor collates here, nothing written.
    version = proposal_mod.next_log_sequence(base_dir, branch)
    stamp_problems = canonize_mod.stamp_ontology_anchor(new_graph, version)
    if stamp_problems:
        text = "the version anchor cannot be stamped; nothing was written:"
        print("--apply refused — " + text, file=sys.stderr)
        for problem in stamp_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("anchor-unstampable", text, stamp_problems)
    # --- verification: what the engine read for every file location of
    # the artifacts this round touched is stamped on the location row
    # (fingerprint, size, this round's sequence) and the artifact's own
    # fingerprint and medium — verify-all before apply-any
    from . import artifacts as artifacts_mod
    verify_problems = artifacts_mod.verification_stamp(
        new_graph, base_dir, version,
        artifacts_mod.touched_artifacts(pinned_delta, new_graph))
    if verify_problems:
        text = ("a file location of an artifact this round touches cannot "
                "be read; nothing was written:")
        print("--apply refused — " + text, file=sys.stderr)
        for problem in verify_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return bail("file-location-unreadable", text, verify_problems)

    # --- write: load the target, re-export the backup FROM the database
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(new_graph, base_dir)
    held, followed = workspace_mod.held_or_followed(
        target_config, kb, proposal_mod.line_identities(base_dir, branch))
    if held:
        print("--apply refused — " + held, file=sys.stderr)
        return bail("database-held-elsewhere", held)
    if followed:
        print(followed)
    try:
        summary = load_mod.load(new_graph, target_config)
        dumped = restore_mod.dump_db(target_config)
    except Exception as exc:
        text = (f"Apply failed mid-write: {exc}. The backup files are "
                "untouched — python -m graph restore returns the "
                "database to the last applied state.")
        print(text, file=sys.stderr)
        return bail("write-failed", text)
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        text = ("EVENT LOG NOT WRITTEN — the database read back "
                "differently than what was written (driver round-trip "
                "fault). The backup files are untouched; python -m graph "
                "restore returns the database to the last applied state.")
        print(text, file=sys.stderr)
        return bail("roundtrip-fault", text)
    export_mod.write_export(dumped, target_export)

    # --- the event log: inverse, chained entry, archive ----------------
    # When moves rode, the inverse is the FULL ground diff — the only
    # honest walk-back for a relabel; otherwise the changeset's own
    inverse_delta = (proposal_mod.invert_delta(
        delta_mod.diff(strip_derived(base), strip_derived(dumped)))
                     if pinned_delta.moves or pinned_delta.merge_moves
                     else proposal_mod.invert_delta(pinned_delta))
    inverse_text = proposal_mod.serialize_delta(inverse_delta)
    (current / proposal_mod.INVERSE_FILE).write_text(inverse_text,
                                                     encoding="utf-8")
    base_before = approval.get("base_hash") or \
        proposal_mod.base_identity(base)
    base_after = proposal_mod.base_identity(dumped)
    # the apply wiped the target's old stamp with everything else;
    # re-identify it at its new base
    from . import workspace as workspace_mod
    workspace_mod.stamp(target_config,
                        "canon" if branch is None else "branch",
                        base_after, git_ref(base_dir), branch=branch,
                        kb=kb)
    chain = proposal_mod.append_applied_log(
        base_dir, approval["delta_hash"], base_before, base_after, branch)
    # fold the round's recorded attribution into the line's ledger,
    # stamped with the round's sequence — the approved links become
    # the record the census audits
    if pinned_delta.attribution:
        sequence = proposal_mod.read_applied_log(base_dir, branch)[-1][0]
        proposal_mod.append_attribution_log(
            base_dir, pinned_delta.attribution, sequence, branch)
    if pinned_delta.moves:
        # the ledger's refs move with the canon they name
        from . import moves as moves_mod
        moved_rows = moves_mod.rewrite_ledger(base_dir, pinned_delta.moves,
                                              branch)
        if moved_rows:
            print(f"  attribution ledger: {moved_rows} row"
                  f"{'s' if moved_rows != 1 else ''} follow the moves.")
    # a prepared merge landed with this round: the line's log records
    # the rounds taken up, so a second merge skips them and succession's
    # divergence advisory does not re-list them
    merge_path = current / proposal_mod.MERGE_FILE
    if merge_path.exists():
        try:
            merge_record = proposal_mod.read_json(merge_path)
        except ValueError:
            merge_record = {}
        proposal_mod.write_merged_annotation(base_dir, branch, {
            "from": merge_record.get("from"),
            "fork_sequence": merge_record.get("fork_sequence"),
            "rounds": merge_record.get("rounds") or [],
            "sequence": proposal_mod.read_applied_log(base_dir,
                                                      branch)[-1][0],
            "contested": len(merge_record.get("contested") or [])})
    proposal_mod.write_json(current / proposal_mod.APPLIED_FILE,
                            {"delta_hash": approval["delta_hash"],
                             "base_after": base_after,
                             "applied": "graph-native",
                             "chain": chain})
    archive = proposal_mod.archive_round(base_dir, approval["delta_hash"],
                                         branch)
    print(f"Applied to {target_label}: {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges now live; backup re-exported "
          "from the database.")
    print(f"Round archived: {archive.relative_to(base_dir)} — event log "
          f"entry chained ({chain[:12]}), inverse recorded.")
    ritual_cut = ("python -m graph restore --database scratch"
                  if branch is None else
                  f"python -m graph restore --from "
                  f"{target_export.relative_to(base_dir)} --database "
                  f"{branch}-scratch")
    print("Ritual: pytest, commit the export + round archive; the next "
          f"round cuts scratch with {ritual_cut}.")
    canonize_mod.clear_refusal_report(base_dir)
    return 0


def _ruled_by(by, base_dir):
    """The human a ceremony record names — the given name, or git's."""
    if by:
        return by
    import subprocess
    try:
        return subprocess.run(
            ["git", "config", "user.name"], cwd=base_dir,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def cmd_succession(base_dir, branch, apply, by=None, archive_as=None):
    """The owner's ceremony: a finished branch becomes canon. The dry
    run walks every verify gate and writes nothing; --apply walks the
    same gates, then captures the outgoing canon as an archive branch,
    rebuilds the live canon database from the branch's line, re-exports
    the backup FROM the database, appends the adoption entry to canon's
    chained event log, and — last, so the seal implies the entry is
    durable — marks the branch home adopted. Verify-all-before-apply-
    any: refusals collate, and nothing is written on any failure."""
    from datetime import datetime, timezone

    from . import canonize as canonize_mod
    from . import load as load_mod
    from . import pockets as pockets_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from . import succession as succession_mod
    from .extract import derive, strip_derived
    from .ontology import ERROR as SEV_ERROR
    from .ontology import ontology_from_graph

    config = load_mod.read_config(base_dir)
    live_canon_database = config["NEO4J_DATABASE"]
    refusal = ("--apply refused — the ceremony cannot proceed:" if apply
               else "REFUSED — the ceremony cannot proceed:")

    # --- name and home guards, before any database is read --------------
    problems = list(proposal_mod.branch_name_problems(
        branch, live_canon_database))
    branch_export = proposal_mod.export_dir(base_dir, branch)
    if branch and not (branch_export / "nodes.jsonl").exists():
        problems.append(
            f"Attempted the succession ceremony for branch '{branch}'. "
            "Failed due to: no branch line exists at "
            f"{branch_export.relative_to(base_dir)} — a branch stands "
            "for succession only after it was cut and its rounds "
            "applied (python -m graph restore --branch ... , delta, "
            "approve, canonize --apply --branch ...).")
    adopted = succession_mod.adopted_branch_problem(
        base_dir, branch, "the succession ceremony")
    if adopted:
        problems.append(adopted)
    sequence = proposal_mod.next_log_sequence(base_dir)
    archive_branch = archive_as or f"superseded-{sequence}"
    problems += proposal_mod.branch_name_problems(
        archive_branch, live_canon_database)
    if archive_branch == branch:
        problems.append(
            f"Attempted to archive the outgoing canon as '{archive_branch}'. "
            "Failed due to: that is the succeeding branch itself — the "
            "archive preserves the OLD line; name it differently with "
            "--archive-as.")
    elif proposal_mod.branch_home(base_dir, archive_branch).exists():
        problems.append(
            "Attempted to archive the outgoing canon as branch "
            f"'{archive_branch}'. Failed due to: that branch home already "
            "exists — pick an unused name with --archive-as.")
    if problems:
        print(refusal, file=sys.stderr)
        for problem in problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        succession_mod.write_checklist_report(
            base_dir, succession_mod.checklist_report(
                base_dir, branch, [], False, [],
                guard_problems=problems))
        return 1

    # --- verify phase: every gate runs, every problem collates -----------
    print(f"SUCCESSION VERIFY — branch '{branch}' standing for canon:")
    gates = []  # (gate label, problem list)

    try:
        canon_backup = canon_base(base_dir)
    except FileNotFoundError as exc:
        canon_backup = None
        gates.append(("live canon backup readable",
                      "canon-backup-unreadable", [
            "Attempted to read canon's committed backup (graph/export). "
            f"Failed due to: {exc}."]))
    branch_backup = None
    try:
        branch_backup = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        gates.append(("branch backup readable",
                      "branch-backup-unreadable", [
            f"Attempted to read branch '{branch}''s committed backup. "
            f"Failed due to: {exc}."]))

    if canon_backup is not None:
        live_config = dict(config)
        live_config["NEO4J_DATABASE"] = live_canon_database
        try:
            live = restore_mod.dump_db(live_config)
            gates.append((
                "live canon matches its committed backup (nothing moved "
                "outside the delta path)", "canon-database-drift",
                restore_mod.verify_against_backup(
                    live, proposal_mod.export_dir(base_dir))))
        except Exception as exc:
            gates.append(("live canon database readable",
                          "canon-database-unreadable", [
                "Attempted to read the live canon database "
                f"('{live_canon_database}'). Failed due to: {exc}."]))

    branch_live = None
    if branch_backup is not None:
        branch_config = dict(config)
        branch_config["NEO4J_DATABASE"] = branch
        try:
            branch_live = restore_mod.dump_db(branch_config)
            gates.append((
                "branch database re-serializes byte-identical to its "
                "backup", "branch-database-drift",
                restore_mod.verify_against_backup(branch_live,
                                                  branch_export)))
        except Exception as exc:
            gates.append((f"branch database '{branch}' readable",
                          "branch-database-unreadable", [
                f"Attempted to read the branch database ('{branch}'). "
                f"Failed due to: {exc}. Rehydrate it from the branch's "
                f"backup: python -m graph restore --from "
                f"{branch_export.relative_to(base_dir)} --database "
                f"{branch}."]))

    gates.append(("canon's event-log chain verifies unbroken",
                  "canon-chain-broken",
                  proposal_mod.verify_applied_log(base_dir)))
    gates.append((f"branch '{branch}''s event-log chain verifies unbroken",
                  "branch-chain-broken",
                  proposal_mod.verify_applied_log(base_dir, branch)))
    # each line's log head agrees with the backup it describes: the
    # adoption chains an entry onto canon's log and reads the branch's,
    # so either head out of step refuses before anything moves
    if canon_backup is not None:
        problem = proposal_mod.log_head_divergence(base_dir, canon_backup)
        gates.append(("canon's event log agrees with its backup",
                      "canon-log-head-diverged",
                      [problem] if problem else []))
    if branch_backup is not None:
        problem = proposal_mod.log_head_divergence(base_dir, branch_backup,
                                                   branch)
        gates.append((f"branch '{branch}''s event log agrees with its "
                      "backup", "branch-log-head-diverged",
                      [problem] if problem else []))

    if branch_backup is not None:
        # The advisory era ends at this gate: the roster census and every
        # other derivation error block succession — a finished line only.
        ontology = ontology_from_graph(branch_backup, base_dir)
        _, derive_findings = derive(ontology, strip_derived(branch_backup))
        derive_error_findings = [f for f in derive_findings
                                 if f.severity == SEV_ERROR]
        derive_errors = [f"{f.file} {f.location}: {f.detail}"
                         for f in derive_error_findings]
        # the prose problems keep the terminal's voice; the findings
        # themselves ride the checklist as typed rows
        gates.append(("roster at full strength and re-derivation clean",
                      "rederivation-error", derive_errors,
                      derive_error_findings))
        gates.append(("ground-facts lint clean over the branch's full "
                      "line", "line-facts-unclean",
                      succession_mod.line_lint(
                          pockets_mod.strip_declarations(branch_backup))))
        from .canonize import ONTOLOGY_ANCHOR
        from .ontology import ARCHETYPE_LABEL
        anchor_missing = [] if (
            (ARCHETYPE_LABEL, ONTOLOGY_ANCHOR) in branch_backup.nodes) else [
            f"Attempted to verify the ({ARCHETYPE_LABEL}, "
            f"'{ONTOLOGY_ANCHOR}') version anchor on the branch. Failed "
            "due to: the branch carries no such anchor — every line "
            "carries one as ground schema."]
        gates.append(("the version anchor rides the branch",
                      "anchor-missing", anchor_missing))

    failed = []
    for gate in gates:
        label, gate_problems = gate[0], gate[2]
        mark = "✓" if not gate_problems else "⚠"
        print(f"  {mark} {label}")
        failed.extend(gate_problems)
    # the checklist is evidence whether the ceremony proceeds or not —
    # compute the divergence facts first (read-only, printed later so
    # the terminal's order is unchanged), then write the record
    fork_known, diverged = succession_mod.post_fork_rounds(base_dir,
                                                           branch)
    checklist_text = succession_mod.write_checklist_report(
        base_dir, succession_mod.checklist_report(
            base_dir, branch, gates, fork_known, diverged))
    if failed:
        print(refusal + " nothing was written:", file=sys.stderr)
        for problem in failed:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1

    # The divergence advisory (never a refusal — adopting past
    # divergence is legitimate, but the owner rules with it in view):
    # rounds the line being superseded applied AFTER this branch's fork
    # do not ride the adoption.
    if not fork_known:
        print("  ⚠ advisory — this branch records no fork point (it was "
              "cut before birth records existed): the line being "
              "superseded may carry rounds applied after the fork, and "
              "they cannot be enumerated. After adoption, diff the "
              "successor against the superseded archive to find any "
              "rulings that must carry forward.")
    elif diverged:
        ids = ", ".join(delta_hash[:12] for _seq, delta_hash in diverged)
        plural = "s" if len(diverged) != 1 else ""
        print(f"  ⚠ advisory — the line being superseded carries "
              f"{len(diverged)} round{plural} applied after this "
              f"branch's fork ({ids}): their content does NOT ride the "
              "adoption. Carry-forward is its own gated round against "
              "the superseded archive; the adoption record's "
              f"{succession_mod.DIVERGENCE_FILE} enumerates the "
              "worklist.")
    else:
        print("  ✓ no rounds landed on the line being superseded after "
              "this branch's fork")

    if not apply:
        print(f"Ready. Adopt with: python -m graph succession --branch "
              f"{branch} --apply")
        return 0

    # --- adopt: capture the old line FIRST, then rebuild live canon ------
    ruled_by = _ruled_by(by, base_dir)
    if ruled_by == "unknown":
        print("--apply refused: Attempted the adoption with no named "
              "ruler. Failed due to: --by was not given and git config "
              "user.name is unset — the adoption record must name who "
              "ruled. Pass --by <name>.", file=sys.stderr)
        return 1
    ruled_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    branch_log = proposal_mod.read_applied_log(base_dir, branch)
    canon_before = proposal_mod.base_identity(canon_backup)
    try:
        succession_mod.archive_line(base_dir, archive_branch)
    except Exception as exc:
        import shutil
        shutil.rmtree(proposal_mod.branch_home(base_dir, archive_branch),
                      ignore_errors=True)
        print("Attempted to archive the outgoing canon as branch "
              f"'{archive_branch}'. Failed due to: {exc}. Nothing was "
              "written to live canon, and the partial archive was "
              "removed — re-run the ceremony.", file=sys.stderr)
        return 1

    # The adoption is an event in CANON's line: its sequence stamps the
    # version anchor, so the version a fresh connection reads keeps
    # climbing through the ceremony. A pocket's own declaration never
    # rides in: canon is never a pocket.
    new_graph = pockets_mod.strip_declarations(branch_live)
    stamp_problems = canonize_mod.stamp_ontology_anchor(new_graph, sequence)
    if stamp_problems:
        print("--apply refused — the version anchor cannot be stamped; "
              "live canon was not written (the outgoing line is archived "
              f"at graph/branches/{archive_branch}):", file=sys.stderr)
        for problem in stamp_problems:
            print(f"  ⚠ {problem}", file=sys.stderr)
        return 1
    target_config = dict(config)
    target_config["NEO4J_DATABASE"] = live_canon_database
    retry_note = (
        "The outgoing line was already archived at "
        f"graph/branches/{archive_branch} — re-run the ceremony with "
        "--archive-as <unused name>, or remove that archive deliberately "
        "first.")
    from . import workspace as workspace_mod
    kb = refs_mod.kb_name(new_graph, base_dir)
    held, followed = workspace_mod.held_or_followed(
        target_config, kb, proposal_mod.line_identities(base_dir))
    if held:
        print(f"succession refused — {held}", file=sys.stderr)
        return 1
    if followed:
        print(followed)
    try:
        summary = load_mod.load(new_graph, target_config)
        dumped = restore_mod.dump_db(target_config)
    except Exception as exc:
        print(f"Adoption failed mid-write: {exc}. The backup files are "
              "untouched — python -m graph restore returns the live "
              f"database to the pre-ceremony canon. {retry_note}",
              file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(new_graph):
        print("ADOPTION NOT RECORDED — the database read back differently "
              "than what was written (driver round-trip fault). The "
              "backup files are untouched; python -m graph restore "
              f"returns the live database to the pre-ceremony canon. "
              f"{retry_note}", file=sys.stderr)
        return 1

    # --- the point of no return: overwrite the backup, then the record,
    # then the chained adoption entry, and LAST the branch seal — a
    # marker present always means the adoption entry is durable, and a
    # missing marker means the ceremony may be re-run to completion.
    canon_after = proposal_mod.base_identity(dumped)
    # the adoption wiped canon's old stamp with everything else;
    # re-identify the database at its new base
    workspace_mod.stamp(target_config, "canon", canon_after,
                        git_ref(base_dir), kb=kb)
    record = {
        "branch": branch,
        "adopted_by": ruled_by,
        "adopted_at": ruled_at,
        "sequence": sequence,
        "post_fork_rounds": len(diverged) if fork_known else "unrecorded",
        "branch_rounds": len(branch_log),
        "branch_chain_tip": branch_log[-1][5] if branch_log else "genesis",
        "branch_export_identity": proposal_mod.base_identity(branch_backup),
        "canon_before": canon_before,
        "canon_after": canon_after,
        "archive_branch": archive_branch,
    }
    text, record_hash = succession_mod.serialize_record(record)
    round_dir = proposal_mod.proposals_dir(base_dir) / record_hash[:12]
    # the enumerated worklist for the carry-forward round — computed
    # from the archived round dirs before anything is overwritten
    divergence_rows = (succession_mod.divergence_summary(base_dir,
                                                         diverged)
                       if fork_known and diverged else [])
    try:
        export_mod.write_export(dumped, proposal_mod.export_dir(base_dir))
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / succession_mod.ADOPTION_FILE).write_text(
            text, encoding="utf-8")
        if divergence_rows:
            (round_dir / succession_mod.DIVERGENCE_FILE).write_text(
                json.dumps(divergence_rows, ensure_ascii=False,
                           indent=2, sort_keys=True) + "\n",
                encoding="utf-8")
        if checklist_text:
            # the verify checklist the adoption was ruled on, archived
            # with the round — the ruling keeps its evidence
            (round_dir
             / succession_mod.CHECKLIST_REPORT_FILE).write_text(
                checklist_text, encoding="utf-8")
        if proposal_mod.next_log_sequence(base_dir) != sequence:
            raise RuntimeError(
                "the event log moved under the ceremony (the adoption "
                f"was stamped for sequence {sequence}) — the stamped "
                "version and the log would disagree")
        chain = proposal_mod.append_applied_log(
            base_dir, record_hash, canon_before, canon_after)
        # the adopted line's recorded attribution rides the adoption.
        # Unlike the event log (a chain that continues unbroken), the
        # ledger is current state, like the export: the superseded
        # line's links describe the superseded line, so they survive
        # only in the archive — canon's ledger becomes the branch's
        # rows, re-stamped with the adoption's own sequence (the
        # adoption IS the round that made those links canon).
        branch_links = proposal_mod.read_attribution_log(base_dir, branch)
        canon_ledger = proposal_mod.attribution_log_path(base_dir)
        canon_ledger.unlink(missing_ok=True)
        if branch_links:
            proposal_mod.append_attribution_log(
                base_dir,
                [{k: v for k, v in row.items() if k != "sequence"}
                 for row in branch_links],
                sequence)
        succession_mod.adoption_marker_path(base_dir, branch).write_text(
            text, encoding="utf-8")
    except Exception as exc:
        print("Adoption failed PAST the point of no return: "
              f"{exc}. Live canon and graph/export may already hold the "
              "adopted line; the pre-ceremony canon survives at "
              f"graph/branches/{archive_branch} (rehydrate with python "
              f"-m graph restore --from graph/branches/{archive_branch}"
              f"/export --database {archive_branch} to walk back). If "
              f"the branch home carries no {succession_mod.ADOPTION_MARKER} "
              "marker, the adoption entry may be missing from canon's "
              "event log — re-run the ceremony with --archive-as "
              "<unused name> to finish with a complete record.",
              file=sys.stderr)
        return 1
    print(f"Adoption recorded: sequence {sequence}, ruled by {ruled_by} "
          f"at {ruled_at} — branch '{branch}' "
          f"(chain tip {record['branch_chain_tip'][:12]}, "
          f"{len(branch_log)} rounds adopted).")
    print(f"Live canon rebuilt: {summary['loaded_nodes']} nodes, "
          f"{summary['loaded_edges']} edges now live; graph/export is the "
          "adopted line, re-exported from the database.")
    print(f"Superseded canon archived as branch '{archive_branch}' — "
          "walk-back is a second ceremony: rehydrate with python -m graph "
          f"restore --from graph/branches/{archive_branch}/export "
          f"--database {archive_branch}, then succession --branch "
          f"{archive_branch}.")
    print(f"Event log: adoption entry chained ({chain[:12]}); record "
          f"archived at {round_dir.relative_to(base_dir)}; the branch "
          "home is provenance now (further rounds refuse).")
    print("Ritual: pytest, commit graph/export, graph/branches/, and the "
          "round archive.")
    return 0


def cmd_approve(base_dir, by, branch=None):
    """Record the diff-gate approval against the current proposal's
    content hash. Run by the submitter — or an agent on their behalf;
    the record names the human. Apply replays only what this froze.
    With --branch <name>: approves the branch's own current round."""
    from . import proposal as proposal_mod

    if branch is not None:
        from . import succession as succession_mod
        adopted = succession_mod.adopted_branch_problem(
            base_dir, branch, "an approval")
        if adopted:
            print(adopted, file=sys.stderr)
            return 1
    current = proposal_mod.current_dir(base_dir, branch)
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
    by = _ruled_by(by, base_dir)
    proposal_mod.write_json(current / proposal_mod.APPROVAL_FILE,
                            {"delta_hash": delta_id, "base_hash": base_hash,
                             "by": by})
    print(f"Approval recorded: proposal {delta_id[:12]} by {by}. "
          "Apply will replay exactly this changeset "
          "(python -m graph canonize --apply).")
    return 0


def cmd_receipt(base_dir, files):
    """The floor receipt for any artifact: fingerprint, size, and the
    medium its bytes declare — printed to paste onto the citizen the
    artifact is about, and recorded under graph/reports/. Every file
    is read before anything is reported; an unreadable one collates."""
    from . import comprehension
    from . import report as report_mod

    rows, failed = [], False
    for relpath in files:
        path = Path(relpath)
        if not path.is_absolute():
            path = base_dir / path
        try:
            data = path.read_bytes()
        except OSError as exc:
            failed = True
            text = (f"Attempted to issue a receipt for {relpath}. Failed "
                    f"due to: {exc}.")
            print(text, file=sys.stderr)
            rows.append({"file": str(relpath), "code": "receipt-unreadable",
                         "ref": report_mod.REF_KEYS["receipt-unreadable"],
                         "problem": text})
            continue
        issued = comprehension.receipt(data)
        # the location row this file would be cited at: a [File Location]
        # of an [Artifact], address relative to the knowledge base
        try:
            address = str(path.resolve().relative_to(
                Path(base_dir).resolve()))
        except ValueError:
            address = str(relpath)
        location = {"kind": "[File Location]", "scheme": "file",
                    "address": address, "primary": True}
        print(f"{relpath}: fingerprint {issued['fingerprint']} · "
              f"{issued['bytes']} bytes · {issued['medium']}")
        print(f"  location: ([File Location]) scheme: file · address: "
              f"{address} · primary: true — LOCATED_AT from the [Artifact] "
              "it belongs to")
        rows.append({"file": str(relpath), **issued, "location": location,
                     "code": "receipt-issued",
                     "ref": report_mod.REF_KEYS["receipt-issued"]})
    doc = report_mod.record_header(base_dir, "receipt-report")
    doc["receipts"] = rows
    report_mod.write_record(base_dir, "receipt-report.json", doc)
    return 1 if failed else 0


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
        try:
            readings.append((relpath,
                             comprehension.read_artifact(
                                 data, title=Path(relpath).name,
                                 origin=str(relpath),
                                 cited_sections=cited.get(relpath, set()),
                                 carried_texts=roundtrip_mod
                                 .carried_passages_for(base_dir, relpath))))
        except comprehension.NotTextArtifact as exc:
            # a non-text artifact: its floor receipt is on record in the
            # refusal; the room reads structure, and there is none to read
            problems.append(str(exc))
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
    # The table tier's column typing and aliases come from canon's
    # committed backup (the render mappings ride each label row beside
    # its spec). No backup means nothing declares a column's type, and
    # every table column compares byte-exact — said aloud, never silent.
    from .ontology import ontology_from_graph
    try:
        ontology = ontology_from_graph(canon_base(base_dir), base_dir)
    except (FileNotFoundError, ValueError, OSError) as exc:
        ontology = None
        print("No committed backup to read the table declarations from "
              f"({exc}): every table column compares byte-exact.",
              file=sys.stderr)
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
    # the record the prose renders from, beside it
    from . import report as report_mod
    report_mod.write_record(
        base_dir, roundtrip_mod.ROUNDTRIP_REPORT_FILE,
        roundtrip_mod.roundtrip_report(result, base_dir=base_dir))
    print(report)
    print(f"Report: {report_path.relative_to(base_dir)}")

    # attribution debts: gaps and soup-rung homes, one row each
    # — the intake worklist a census produces as a byproduct (issue
    # filing stays with the orchestrator)
    if result.attribution:
        from . import attribution as attribution_mod
        kb = refs_mod.kb_name_from_export(base_dir)
        debts = [r.row(kb=kb) for r in result.attribution
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
    try:
        graph = render_tables.load_backup(base_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    # The schema — and the render mappings beside it — come from canon's
    # committed backup: a label's rendered_views_json reconstructs as its
    # spec's view list, so no bootstrap file is read.
    ontology = ontology_mod.ontology_from_graph(graph, base_dir)
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
              f"backup (graph/export). Failed due to: {exc}. The "
              "committed backup is the knowledge base — restore it from "
              "git, or give birth to a new one with python -m graph init.",
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
            f"backup (graph/export). Failed due to: {exc}. The "
            "committed backup is the knowledge base — restore it from "
            "git, or give birth to a new one with python -m graph init.")
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


def cmd_docs(record=None):
    """Print an engine record — a design record or a conduct record (a
    skill's full procedure) — assembled from the manual's packaged
    canon. The records live once, as citizens: a knowledge base points
    here instead of vendoring a copy (the copy retirement), and the
    plugin's trigger stubs point here for their instructions (the stub
    model). No base, no database: the canon ships in the package, and
    the command answers from anywhere."""
    from . import records as records_mod

    canon = records_mod.load_canon()
    if canon is None:
        print("Attempted to read the engine's records. Failed due to: "
              "the packaged canon is missing (a broken install). "
              "Reinstall the engine package.", file=sys.stderr)
        return 2
    in_canon = records_mod.records(canon)
    designs = sorted(handle for handle, (label, _) in in_canon.items()
                     if not records_mod.is_conduct(label))
    conduct = sorted(handle for handle, (label, _) in in_canon.items()
                     if records_mod.is_conduct(label))
    if not record:
        print("Engine design records (python -m graph docs <record>):")
        for name in designs:
            print(f"  {name}")
        print("Conduct records — the skills' full procedures:")
        for name in conduct:
            print(f"  {name}")
        return 0
    if record not in in_canon:
        print(f"Attempted to read the engine record '{record}'. "
              "Failed due to: no record in the engine's canon carries "
              "that name. Available: " + ", ".join(designs + conduct),
              file=sys.stderr)
        return 2
    label, name = in_canon[record]
    sys.stdout.write(records_mod.render(canon, label, name))
    return 0


DEPENDENCY_PATH_PREFIX = "GHOSTWHEEL_DEPENDENCY_"
_DEPENDENCY_SETTINGS_BLOCK = (
    "\n"
    "# Dependencies this knowledge base pins — one line per dependency,\n"
    "# naming where that knowledge base's checkout lives on this machine\n"
    "# (its committed backup is read there). Settings, never canon: the\n"
    "# pin itself is a [Knowledge Base Dependency] entry authored in a gated round, at\n"
    "# the dependency's edition.\n"
    f"# {DEPENDENCY_PATH_PREFIX}<name>=/path/to/that/knowledge-base\n")


def cmd_init(target, name=None, world=False):
    """Seed a new knowledge base, born graph-native: no ontology.yaml,
    no sources, no derive path. Writes a committed backup holding the
    kernel's schema stratum alone into <target>/graph/export — the same
    seed shape a schema-only branch cut is born from — so the delta path
    can build everything else through gated rounds. No database needed:
    the first `restore` there brings the DBMS into the story.
    `world` seeds exactly the same knowledge base and adds the
    dependency settings block to its .env plus the next step — a world
    is a role a knowledge base plays by holding [Knowledge Base Dependency] entries,
    authored in a gated round, never a type the seed marks."""
    from .extract import Extractor, schema_only
    from .ontology import ARCHETYPE_LABEL, ERROR, kernel_ontology

    target = Path(target).resolve()
    existing = [marker for marker in
                (target / "graph" / "export",
                 target / "graph" / "ontology.yaml")
                if marker.exists()]
    if existing:
        homes = ", ".join(str(p.relative_to(target)) for p in existing)
        print(f"Attempted to seed a new knowledge base at {target}. "
              f"Failed due to: a knowledge base already lives there "
              f"({homes} exists). Seeding again would overwrite its "
              "committed backup. Removing a knowledge base is the "
              "owner's own act — do it deliberately, then re-run.",
              file=sys.stderr)
        return 1

    ontology, findings = kernel_ontology(target)
    problems = [f for f in findings if f.severity == ERROR]
    if ontology is None or problems:
        for f in problems:
            print(f"{f.file} {f.location}: {f.detail}", file=sys.stderr)
        print("Attempted to seed a new knowledge base from the engine "
              "kernel. Failed due to: the packaged metaontology did not "
              "load cleanly (above) — this is an engine defect, not a "
              "problem with the target directory.", file=sys.stderr)
        return 1

    extractor = Extractor(ontology)
    extractor.build_metamodel()
    seed = schema_only(extractor.graph)
    kb = name or target.name
    seed.ensure_node(ARCHETYPE_LABEL, refs_mod.ONTOLOGY_ANCHOR,
                     **{refs_mod.KB_NAME_PROP: kb})
    export_dir = target / "graph" / "export"
    export_mod.write_export(seed, export_dir)
    print(f"Knowledge base '{kb}' seeded at {target} from the engine "
          f"kernel alone — {len(seed.nodes)} schema citizens, "
          f"{len(seed.edges)} schema edges; no ground facts.")
    # Its own database names from birth: several knowledge bases share
    # one DBMS, so the canon database is the knowledge base's name and
    # the working copy is <name>-scratch — never the engine-wide defaults.
    env_file = target / ".env"
    canon_db = default_database_name(kb)
    scratch_db = f"{canon_db}-scratch"
    env_existed = env_file.exists()
    if env_existed:
        print(f"Settings: {env_file.name} already exists — kept as-is."
              + (f" Add the dependency block by hand:\n"
                 f"{_DEPENDENCY_SETTINGS_BLOCK}" if world else ""))
    else:
        env_file.write_text(
            "# This knowledge base's DBMS settings — fill in the "
            "credentials; keep .env out of source control.\n"
            "NEO4J_URI=bolt://localhost:7687\n"
            "NEO4J_USERNAME=neo4j\n"
            "NEO4J_PASSWORD=changeme\n"
            "\n"
            "# Its own database names: several knowledge bases can share "
            "one DBMS\n# without colliding.\n"
            f"NEO4J_DATABASE={canon_db}\n"
            f"NEO4J_SCRATCH_DATABASE={scratch_db}\n"
            + (_DEPENDENCY_SETTINGS_BLOCK if world else ""),
            encoding="utf-8")
        print(f"Settings written to {env_file.name}: canon database "
              f"'{canon_db}', working copy '{scratch_db}'"
              + (", and the dependency block to fill in" if world else "")
              + " — fill in the DBMS credentials there and keep the file "
              "out of source control.")
    # Born connected: the scaffold and users ride a FRESH birth; an
    # existing settings file stays byte-untouched (its owner's), with
    # the verb named for when they choose.
    if env_existed:
        print("Connections: existing settings kept as-is — python -m "
              "graph connections adds this knowledge base's reader and "
              "writer and the MCP scaffold when you choose.")
    else:
        from . import connections as connections_mod
        connections_mod.scaffold(target, canon_db, scratch_db)
        print(f"Connections scaffold written: {connections_mod.MCP_FILE} "
              "(reader on canon, writer on the working copy, credentials "
              "by environment expansion) and generated passwords in "
              ".env.")
        if cmd_connections(target) != 0:
            print("The DBMS half is deferred — run python -m graph "
                  "connections once the DBMS is reachable.")
    print("Next: python -m graph restore (build its canon database from "
          f"the backup), then restore --database {scratch_db} to cut "
          "the first authoring round"
          + (" — and in that round pin each dependency as a [Knowledge Base Dependency] "
             "entry (its name = that knowledge base's declared name; "
             "edition and sequence from its committed backup; intent read "
             "or write), naming each dependency's path in .env."
             if world else "."))
    return 0


def default_database_name(kb):
    """A knowledge base's default canon database name: its own name,
    in the shape a DBMS accepts (lower case; letters, digits, dots and
    dashes; no leading or trailing dash)."""
    import re
    slug = re.sub(r"[^a-z0-9.-]+", "-", kb.lower()).strip("-.")
    return slug or "canon"


def cmd_connections(base_dir, reset_passwords=False):
    """Born connected: create (idempotently) this knowledge base's
    query-only reader and working-copy writer on the DBMS, and lay the
    project MCP scaffold. Re-runs change nothing unless
    --reset-passwords says so."""
    from . import connections as connections_mod
    from . import load as load_mod
    config = load_mod.read_config(base_dir)
    canon_db = config["NEO4J_DATABASE"]
    scratch_db = (config.get("NEO4J_SCRATCH_DATABASE") or "").strip() \
        or f"{canon_db}-scratch"
    if not reset_passwords:
        problems = connections_mod.adoption_problems(base_dir)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
    creds = connections_mod.scaffold(base_dir, canon_db, scratch_db)
    if reset_passwords:
        creds.update(connections_mod.rotate_passwords(base_dir))
    reader = creds[connections_mod.READER_USERNAME_KEY]
    writer = creds[connections_mod.WRITER_USERNAME_KEY]
    plan = connections_mod.statements(canon_db, scratch_db, creds,
                                      reset=reset_passwords)
    try:
        runner = connections_mod._system_runner(config)
    except Exception as exc:
        print(f"Attempted to reach the DBMS to create '{reader}' and "
              f"'{writer}'. Failed due to: {exc}. Is the DBMS running? "
              "The settings and MCP scaffold are in place — re-run "
              "python -m graph connections when it is up.",
              file=sys.stderr)
        return 1
    try:
        for statement in plan:
            runner.run(statement)
    except Exception as exc:
        text = str(exc)
        if "Unsupported administration command" in text:
            cause = ("this DBMS does not manage users (a community "
                     "edition) — use an Enterprise DBMS, or point the "
                     "settings at one")
        elif "Permission" in text or "Forbidden" in text \
                or "denied" in text.lower():
            cause = ("the admin connection lacks the right to manage "
                     "users — grant it, or have an administrator run "
                     "the statements")
        else:
            cause = f"the DBMS refused: {text}"
        print(f"Attempted to create this knowledge base's reader and "
              f"writer on the DBMS. Failed due to: {cause}. The "
              "settings and MCP scaffold stand, and creation is "
              "idempotent — a re-run converges. The exact statements "
              "(passwords redacted; the real values are in .env), to "
              "run by hand if that is the road:\n  "
              + "\n  ".join(connections_mod.redacted(s) for s in plan),
              file=sys.stderr)
        return 1
    finally:
        close = getattr(runner, "close", None)
        if close:
            close()
    default_reader, default_writer = connections_mod.usernames(canon_db)
    declined = [name for name in (default_reader, default_writer)
                if name not in (reader, writer)]
    if declined:
        names = "' and '".join(declined)
        print(f"Note: the settings name '{reader}'/'{writer}', so the "
              f"default pair was not used. If '{names}' exist from an "
              "earlier run they hold no access, but retire or rotate "
              "them by hand — never leave a stray credential standing:"
              + "".join(f"\n  DROP USER `{name}` IF EXISTS;"
                        for name in declined))
    print(f"Connections ready: '{reader}' answers from '{canon_db}' "
          f"(query-only), '{writer}' authors '{scratch_db}'. The "
          f"project MCP scaffold ({connections_mod.MCP_FILE}) carries "
          "them by environment expansion — a session opened here is "
          "offered both.")
    return 0


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
    if error or extractor is None:
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
              "docs — retire their ruling rows (the Decision citizens "
              "carrying rejected_term) through a gated round:")
        for term in stale:
            print(f"  {term}")
    return 0


def cmd_receipts(base_dir, branch=None):
    """The receipt sweep: every carried quote in the committed backup
    checked against its cited source's current bytes. Stale quotes are
    named with what they were hiding (an honest home beneath, or intake
    debt); sources that no longer resolve are named; ruling-shaped
    sources are counted, never nagged. Report-only — staleness is an
    honesty problem, not a build break, so the exit stays 0."""
    from . import receipts as receipts_mod
    try:
        base = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        print("Attempted to read the committed backup for the receipt "
              f"sweep. Failed due to: {exc}.", file=sys.stderr)
        return 1
    from . import report as report_mod
    from .kernel_migrate import sweep_skew_refusal
    refusal = sweep_skew_refusal(base, "the receipt sweep")
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    result = receipts_mod.sweep(base_dir, base)
    report = receipts_mod.render_report(result)
    reports_dir = base_dir / "graph" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "receipts.md"
    report_path.write_text(report, encoding="utf-8")
    # the same sweep as records beside the prose — one row per quote
    doc = receipts_mod.sweep_report(base_dir, result, branch)
    # artifact locations ride the same sweep: is each file still what
    # the gate verified? Other kinds are unverifiable by design.
    from . import artifacts as artifacts_mod
    doc["locations"] = artifacts_mod.location_rows(base, base_dir)
    report_mod.write_record(base_dir, receipts_mod.RECEIPTS_REPORT_FILE, doc)
    print(report)
    if doc["locations"]:
        counts = {}
        for row in doc["locations"]:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        print("Artifact locations: " + ", ".join(
            f"{n} {status}" for status, n in sorted(counts.items())) + ".")
        for row in doc["locations"]:
            if row["status"] in ("stale", "unreadable"):
                print(f"  ⚠ {row['status']}: '{row['artifact']}' at "
                      f"{row['address']} ({row['kind']})")
    print(f"Report: {report_path.relative_to(base_dir)}")
    return 0


def cmd_answer_keys(base_dir, branch=None):
    """The answer-key sweep: every Answer Key citizen on canon re-run
    against canon's program bodies and the approved tables on disk —
    the fidelity net, DB-free. A program that drifted from its table,
    or a key that cannot be checked, fails the sweep by name (exit 1);
    the record lands beside the prose either way."""
    from . import answer_keys as answer_keys_mod
    from . import report as report_mod
    from .ontology import ontology_from_graph
    try:
        base = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        print("Attempted to read the committed backup for the answer-key "
              f"sweep. Failed due to: {exc}.", file=sys.stderr)
        return 1
    from .kernel_migrate import sweep_skew_refusal
    refusal = sweep_skew_refusal(base, "the answer-key sweep")
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    ontology = ontology_from_graph(base, base_dir)
    rows = answer_keys_mod.canon_check(base, ontology, base_dir)
    doc = answer_keys_mod.answer_keys_report(base_dir, rows, branch)
    report_mod.write_record(base_dir, answer_keys_mod.ANSWER_KEYS_REPORT_FILE,
                            doc)
    print(answer_keys_mod.render_report(doc))
    return 0 if doc["passed"] else 1


def cmd_merge(base_dir, source, target, database=None):
    """Merge — one line takes up another's rounds while both persist.
    Prepares the TARGET's ordinary round: the source's rounds since the
    fork replay into the target's fresh working copy (contested citizens
    — changed on both lines — stay at the target's version and are
    listed base / yours / theirs), merge.json rides the round, and
    delta → approve → canonize --apply land it like any round. Both
    directions between canon and a pocket."""
    from . import pockets as retire_mod
    from . import merge as merge_lines_mod
    for line in (source, target):
        name = merge_lines_mod.resolve_line(line)
        if name is not None:
            retired = retire_mod.retired_problem(base_dir, name, "merge")
            if retired:
                print(retired, file=sys.stderr)
                return 1
    from . import delta as delta_mod
    from . import load as load_mod
    from . import merge as merge_mod
    from . import proposal as proposal_mod
    from . import report as report_mod
    from . import succession as succession_mod
    from . import workspace as workspace_mod

    src, tgt = merge_mod.resolve_line(source), merge_mod.resolve_line(target)
    if src == tgt:
        print(f"Attempted to merge {source} into {target}. Failed due to: "
              "a line cannot take up its own rounds — name a pocket on "
              "one side and canon on the other.", file=sys.stderr)
        return 1
    problems = []
    graphs = {}
    for line in (src, tgt):
        try:
            graphs[line] = canon_base(base_dir, line)
        except FileNotFoundError as exc:
            problems.append(f"Attempted to read {merge_mod.describe(line)}"
                            f"'s committed backup. Failed due to: {exc}.")
    for line in (src, tgt):
        if line is not None:
            adopted = succession_mod.adopted_branch_problem(base_dir, line,
                                                            "a merge")
            if adopted:
                problems.append(adopted)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    from .kernel_migrate import sweep_skew_refusal
    for line in (src, tgt):
        refusal = sweep_skew_refusal(
            graphs[line], f"a merge over {merge_mod.describe(line)}")
        if refusal:
            print(refusal, file=sys.stderr)
            return 1
    source_graph, target_graph = graphs[src], graphs[tgt]
    fork, _pocket, problem = merge_mod.fork_point(
        base_dir, src, tgt, source_graph, target_graph)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    # the target's fresh working copy: what lands is exactly the replay
    # plus the owner's rulings, never a half-authored round
    config = load_mod.read_config(base_dir)
    database = _authoring_database(database, tgt, config)
    if tgt is not None:
        read_problem = proposal_mod.authoring_read_problem(
            database, config["NEO4J_DATABASE"])
        if read_problem:
            print(read_problem, file=sys.stderr)
            return 1
    config["NEO4J_DATABASE"] = database
    identity = _working_copy_check(base_dir, config, database, tgt)
    if identity:
        print(identity, file=sys.stderr)
        return 1
    try:
        copy = delta_mod.read_graph(config)
    except Exception as exc:
        print(f"Attempted to read {merge_mod.describe(tgt)}'s working copy "
              f"('{database}'). Failed due to: {exc}. Cut it first "
              "(python -m graph restore --database <copy>).",
              file=sys.stderr)
        return 1
    if not merge_mod.serialize_equal(copy, target_graph):
        print(f"Attempted to merge into {merge_mod.describe(tgt)}'s working "
              f"copy ('{database}'). Failed due to: the copy already "
              "differs from its base — a merge wants a fresh copy, so what "
              "lands is exactly the rounds taken up plus your rulings. "
              "Re-cut the copy, then merge.", file=sys.stderr)
        return 1
    merged, record, problems = merge_mod.prepare(
        base_dir, src, tgt, source_graph, target_graph, copy)
    if merged is None or record is None:
        print("\n".join(problems), file=sys.stderr)
        return 1
    doc = merge_mod.merge_report(base_dir, record, tgt)
    report_mod.write_record(base_dir, merge_mod.REPORT_FILE, doc)
    if doc["nothing_to_take_up"]:
        print(merge_mod.render_report(doc))
        return 0
    try:
        load_mod.load(merged, config)
        readback = delta_mod.read_graph(config)
    except Exception as exc:
        print(f"Attempted to land the replay in '{database}'. Failed due "
              f"to: {exc}. The copy may be half-written — re-cut it and "
              "merge again.", file=sys.stderr)
        return 1
    if not merge_mod.serialize_equal(readback, merged):
        differences = merge_mod.first_differences(readback, merged)
        print(f"Attempted to land the replay in '{database}'. Failed due "
              "to: the copy read back differently than what was written. "
              "The first differences:\n  " + "\n  ".join(differences)
              + "\nRe-cut the copy and merge again; if the differences "
              "name types or citizens rather than driver noise, report "
              "them.", file=sys.stderr)
        return 1
    workspace_mod.stamp(config, "working-copy",
                        proposal_mod.base_identity(target_graph),
                        git_ref(base_dir), branch=tgt,
                        kb=refs_mod.kb_name(target_graph, base_dir))
    current = proposal_mod.current_dir(base_dir, tgt)
    current.mkdir(parents=True, exist_ok=True)
    proposal_mod.write_json(current / proposal_mod.MERGE_FILE, record)
    print(merge_mod.render_report(doc))
    print(f"Replay landed in '{database}'; the merge record rides the "
          f"round ({(current / proposal_mod.MERGE_FILE).relative_to(base_dir)}"
          f"); report at graph/reports/{merge_mod.REPORT_FILE}.")
    return 0


def cmd_branch(base_dir, branch, invite=None, uninvite=None,
               retire=False, by=None):
    """A pocket's declaration, shown or changed. With --invite/--uninvite
    the [Pocket Universe] row in the branch's backup is rewritten, the branch
    database reloaded from it and read back byte-identical, and the
    identity stamp re-written with the new facts — the line's content
    identity does not move (the declaration is set aside from it), so
    no chain, pin, or round is disturbed. Every problem collates before
    anything is written."""
    from . import load as load_mod
    from . import pockets as pockets_mod
    from . import proposal as proposal_mod
    from . import restore as restore_mod
    from . import succession as succession_mod
    from . import workspace as workspace_mod

    if retire:
        problems = pockets_mod.retirement_problems(base_dir, branch, by)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        record = pockets_mod.write_retirement(base_dir, branch, by)
        # the line's databases drop through the same admin road that
        # creates them — idempotent, deferring plainly when unreachable
        from . import connections as connections_mod
        config = load_mod.read_config(base_dir)
        drops = [f"DROP DATABASE `{branch}` IF EXISTS",
                 f"DROP DATABASE `{branch}-scratch` IF EXISTS"]
        try:
            runner = connections_mod._system_runner(config)
            try:
                for statement in drops:
                    runner.run(statement)
            finally:
                close = getattr(runner, "close", None)
                if close:
                    close()
        except Exception as exc:
            print(f"Note: the line's databases were not dropped ({exc}) "
                  "— run these by hand when the DBMS is up:\n  "
                  + "\n  ".join(drops))
        print(f"Branch '{branch}' retired by {record['retired_by']}'s "
              f"word at {record['retired_at']}: "
              f"{len(record['rounds_taken_up'])} round"
              f"{'s' if len(record['rounds_taken_up']) != 1 else ''} "
              "all taken up by canon, the record standing whole at "
              f"graph/branches/{branch}/, the databases dropped. "
              "The roster lists it under --all.")
        return 0
    invite, uninvite = list(invite or []), list(uninvite or [])
    try:
        graph = restore_mod.read_export(proposal_mod.export_dir(base_dir,
                                                                branch))
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Attempted to read branch '{branch}''s backup. Failed due "
              f"to: {exc}. python -m graph branches lists the branches "
              "this knowledge base has.", file=sys.stderr)
        return 1
    row = pockets_mod.pocket_row(graph, branch)
    if row is None:
        print(f"Attempted to read pocket '{branch}''s declaration. Failed "
              "due to: that branch is a rebuild line, not a pocket — it "
              "was cut with --base schema-only and carries no declaration. "
              "A pocket is cut with --base clone-of-canon --by <who>.",
              file=sys.stderr)
        return 1
    if not invite and not uninvite:
        invited = ", ".join(row.get("invited") or []) or "nobody yet"
        print(f"Pocket '{branch}' — cut by {row.get('cut_by')} "
              f"({row.get('cut_at')}) from canon at sequence "
              f"{row.get('forked_sequence')} (identity "
              f"{str(row.get('forked_from'))[:12]}); invited: {invited}.")
        return 0
    problems = []
    adopted = succession_mod.adopted_branch_problem(base_dir, branch,
                                                    "an invite change")
    if adopted:
        problems.append(adopted)
    current = list(row.get("invited") or [])
    for name in uninvite:
        if name not in current:
            problems.append(
                f"Attempted to withdraw '{name}''s invitation to pocket "
                f"'{branch}'. Failed due to: nobody by that name is "
                f"invited (invited: {', '.join(current) or 'nobody'}).")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    invited = sorted((set(current) | set(invite)) - set(uninvite))
    updated = pockets_mod.clone_graph(graph)
    updated.nodes[(pockets_mod.KERNEL_POCKET_LABEL, branch)] = dict(
        row, invited=invited)
    config = load_mod.read_config(base_dir)
    config["NEO4J_DATABASE"] = branch
    try:
        load_mod.load(updated, config)
        dumped = restore_mod.dump_db(config)
    except Exception as exc:
        print(f"Attempted to rewrite pocket '{branch}''s declaration in "
              f"its database. Failed due to: {exc}. The backup is "
              "untouched.", file=sys.stderr)
        return 1
    if export_mod.serialize(dumped) != export_mod.serialize(updated):
        print(f"Attempted to rewrite pocket '{branch}''s declaration. "
              "Failed due to: the database read back differently than "
              "what was written (driver round-trip fault). The backup is "
              "untouched; python -m graph restore --from its backup "
              "returns the database to it.", file=sys.stderr)
        return 1
    export_mod.write_export(dumped, proposal_mod.export_dir(base_dir, branch))
    workspace_mod.stamp(
        config, "branch", proposal_mod.base_identity(dumped),
        git_ref(base_dir), branch=branch,
        kb=refs_mod.kb_name(dumped, base_dir),
        extra=pockets_mod.stamp_facts(
            updated.nodes[(pockets_mod.KERNEL_POCKET_LABEL, branch)]))
    print(f"Pocket '{branch}' — invited: {', '.join(invited) or 'nobody'}. "
          "Declaration rewritten in the branch's backup and stamp; the "
          "line's identity is unchanged.")
    return 0


def cmd_branches(base_dir, all_lines=False):
    """The pocket roster: every branch of this knowledge base from its
    backup — pocket or rebuild line, cut by whom, invited, sequence,
    adopted — printed and recorded. No DBMS needed."""
    from . import pockets as pockets_mod
    from . import report as report_mod
    from .kernel_migrate import sweep_skew_refusal
    try:
        canon = canon_base(base_dir)
    except FileNotFoundError as exc:
        print("Attempted to read the committed backup for the branch "
              f"roster. Failed due to: {exc}.", file=sys.stderr)
        return 1
    refusal = sweep_skew_refusal(canon, "the branch roster")
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    rows = pockets_mod.branch_rows(base_dir)
    doc = pockets_mod.branches_report(base_dir, rows)
    report_mod.write_record(base_dir, pockets_mod.REPORT_FILE, doc)
    shown = rows if all_lines else \
        [row for row in rows if row.get("status") != "retired"]
    hidden = len(rows) - len(shown)
    text = pockets_mod.render_rows(shown)
    if hidden:
        text += (f"\n({hidden} retired line"
                 f"{'s' if hidden != 1 else ''} hidden — branches --all "
                 "shows them.)")
    print(text)
    return 0


def cmd_dependencies(base_dir, branch=None):
    """The drift query: every [Knowledge Base Dependency] on canon against what its
    checkout holds now — held, behind, or unreachable — printed one per
    line and recorded as dependencies-report.json; exit 1 when any pin
    is behind or cannot be reached, so a later tool can alert on it."""
    from . import dependencies as dependencies_mod
    from . import load as load_mod
    from . import report as report_mod
    try:
        base = canon_base(base_dir, branch)
    except FileNotFoundError as exc:
        print("Attempted to read the committed backup for the dependency "
              f"drift query. Failed due to: {exc}.", file=sys.stderr)
        return 1
    from .kernel_migrate import sweep_skew_refusal
    refusal = sweep_skew_refusal(base, "the dependency drift query")
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    config = load_mod.read_config(base_dir)
    rows = dependencies_mod.drift_rows(base, config)
    doc = dependencies_mod.dependencies_report(base_dir, rows, branch)
    report_mod.write_record(base_dir, dependencies_mod.REPORT_FILE, doc)
    print(dependencies_mod.render_report(doc))
    return 0 if doc["passed"] else 1


def load_corpus_grammars(base_dir):
    """Corpus grammar loading: if the opened knowledge base carries a
    grammars.py at its root, import it — its @register decorators fill
    the registry with the corpus's own parsing rules. The engine ships
    no grammars; this hook is how a consuming corpus supplies its own
    without owning the engine package."""
    hook = Path(base_dir) / "grammars.py"
    if not hook.exists():
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("corpus_grammars", hook)
    if spec is None or spec.loader is None:  # not importable as a module
        print(f"Attempted to load the corpus grammar module ({hook}). "
              "Failed because Python could not build an import spec for "
              "it. Extraction that needs a declared parser will refuse "
              "until it loads.", file=sys.stderr)
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"Attempted to load the corpus grammar module "
              f"({hook}). Failed due to: {exc}. Extraction that needs a "
              "declared parser will refuse until it loads.",
              file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ghostwheel",
        description="Derive, validate, and load the project's derived graph.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate",
                   help="retired — the from-sources era is closed; the "
                        "schema lives on the graph (see check, corpus, "
                        "rederive)")
    export_parser = sub.add_parser(
        "export",
        help="serialize the live database to graph/export/ — the backup "
             "is written FROM canon (post-flip default)")
    export_parser.add_argument(
        "--from-sources", action="store_true",
        help="retired — the backup is written FROM the database; the "
             "from-sources era is closed")
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
        help="retired — the from-sources era is closed; restore rebuilds "
             "any database from the committed backup")
    load_parser.add_argument(
        "--database", default=None,
        help="(retired with the verb)")
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
    merge_parser = sub.add_parser(
        "merge",
        help="merge — one line takes up another's rounds while both "
             "persist: prepares the TARGET's ordinary round (the source's "
             "rounds since the fork replay into the target's fresh working "
             "copy; citizens changed on both lines stay at the target's "
             "version, listed base / yours / theirs), then delta, approve, "
             "canonize --apply as any round. Between canon and a pocket, "
             "either direction.")
    merge_parser.add_argument("--from", dest="source", required=True,
                              metavar="LINE",
                              help="the line whose rounds are taken up "
                                   "('canon' or a pocket's name)")
    merge_parser.add_argument("--into", dest="target", required=True,
                              metavar="LINE",
                              help="the line that takes them up ('canon' "
                                   "or a pocket's name)")
    merge_parser.add_argument("--database", default=None,
                              help="the target's working copy (default: "
                                   "its usual authoring copy)")
    branch_parser = sub.add_parser(
        "branch",
        help="a pocket's declaration: show who cut it and who may look, "
             "or change the invite list (--invite / --uninvite) — the "
             "stamp and the [Pocket Universe] row are rewritten; nothing else "
             "moves, and the line's identity stays put")
    branch_parser.add_argument("name", help="the branch")
    branch_parser.add_argument("--invite", action="append", default=None,
                               metavar="NAME", help="invite a person")
    branch_parser.add_argument("--uninvite", action="append", default=None,
                               metavar="NAME", help="withdraw an invitation")
    branch_parser.add_argument(
        "--retire", action="store_true",
        help="close a spent line by the owner's word: every round taken "
             "up (or none landed), the record stands, the databases "
             "drop, further rounds refuse")
    branch_parser.add_argument(
        "--by", default=None,
        help="who ruled the retirement — recorded in retired.json "
             "(required with --retire)")
    branches_parser = sub.add_parser(
        "branches",
        help="list this knowledge base's branches from their backups — "
             "pocket or rebuild line, cut by whom, invited, sequence, "
             "adopted — recorded at graph/reports/branches-report.json")
    branches_parser.add_argument(
        "--all", action="store_true",
        help="show retired lines too (hidden by default)")
    dependencies_parser = sub.add_parser(
        "dependencies",
        help="the drift query: every pinned dependency against what its "
             "checkout holds now — held, behind, or unreachable — recorded "
             "at graph/reports/dependencies-report.json; exit 1 when any "
             "pin is behind or cannot be reached")
    dependencies_parser.add_argument(
        "--branch", default=None,
        help="read the branch's own backup instead of live canon's")
    receipt_parser = sub.add_parser(
        "receipt",
        help="the floor receipt for any artifact — fingerprint, size, and "
             "the medium its bytes declare — to paste onto the citizen it "
             "is about; recorded at graph/reports/receipt-report.json")
    receipt_parser.add_argument("files", nargs="+",
                                help="artifact files (paths relative to "
                                     "the knowledge base)")
    rederive_parser = sub.add_parser(
        "rederive",
        help="the derived-layer refresh after an engine change or a "
             "schema ceremony: re-derive canon's machine layers from the "
             "committed backup against the schema the graph carries — "
             "dry run by default, printing what leaves and arrives; "
             "--apply performs it as a chained, archived round (ground "
             "untouched; a ground change rides the delta path)")
    rederive_parser.add_argument(
        "--apply", action="store_true",
        help="write the refresh as a round (dry run without it)")
    kernel_parser = sub.add_parser(
        "kernel-migrate",
        help="migrate this canon's embedded kernel stratum to the "
             "installed engine's kernel — dry run by default; --apply "
             "performs the splice as a chained, archived round (project "
             "stratum and ground untouched)")
    kernel_parser.add_argument(
        "--apply", action="store_true",
        help="write the migration (dry run without it)")
    restore_parser.add_argument(
        "--database", default=None,
        help="target database override (e.g. 'scratch' — cuts a round: "
             "clone of canon, base pinned)")
    restore_parser.add_argument(
        "--branch", default=None,
        help="cut a BRANCH — an independent line of truth within this KB "
             "(its own home, backup, and chained log), born from --base. "
             "The branch's database IS its name (one identity, no alias — "
             "--database is refused here); author in its <name>-scratch "
             "copy. A branch never becomes canon by flag; succession is "
             "the owner's ceremony.")
    restore_parser.add_argument(
        "--base", default=None, choices=["schema-only", "clone-of-canon"],
        help="the branch's declared base — 'schema-only' (the schema "
             "stratum alone: a rebuild line) or 'clone-of-canon' (canon's "
             "whole graph: a POCKET, a collaborator's own version, "
             "declared in-band by --by and --invite)")
    restore_parser.add_argument(
        "--by", default=None,
        help="who cuts the pocket (required with --base clone-of-canon)")
    restore_parser.add_argument(
        "--invite", action="append", default=None, metavar="NAME",
        help="a person invited to look at the pocket (repeatable); "
             "declarative here — physical readability is a later rung")
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
    connections_parser = sub.add_parser(
        "connections",
        help="born connected: create this KB's query-only reader and "
             "working-copy writer on the DBMS (idempotent) and lay the "
             "project MCP scaffold")
    connections_parser.add_argument(
        "--reset-passwords", action="store_true",
        help="generate fresh passwords, rewrite .env, and ALTER the "
             "users — never done unasked")
    sub.add_parser("terms",
                   help="scan all docs for capitalized terms the glossary "
                        "cannot resolve (owner consolidation list)")
    receipts_parser = sub.add_parser(
        "receipts",
        help="sweep every carried quote in canon against its cited "
             "source — stale quotes named with what they were hiding "
             "(no DB needed)")
    receipts_parser.add_argument(
        "--branch", default=None,
        help="sweep a branch's own line of truth instead of canon")
    answer_keys_parser = sub.add_parser(
        "answer-keys",
        help="re-run every answer key on canon: each program held to its "
             "approved table, from the committed backup and the tables on "
             "disk (no DB needed); a drift or an uncheckable key fails")
    answer_keys_parser.add_argument(
        "--branch", default=None,
        help="sweep a branch's own line of truth instead of canon")
    docs_parser = sub.add_parser(
        "docs",
        help="print a packaged engine record — design records (the "
             "doctrine and its siblings) and conduct records (the "
             "skills' full procedures) — no knowledge base needed; "
             "bare `docs` lists them")
    docs_parser.add_argument(
        "record", nargs="?", default=None,
        help="record name, e.g. 'ontology-doctrine' or 'agentic-intake'; "
             "omit to list")
    init_parser = sub.add_parser(
        "init",
        help="seed a new knowledge base, born graph-native: write a "
             "committed backup holding the kernel's schema stratum alone "
             "into <target>/graph/export — no ontology.yaml, no sources; "
             "everything else grows through gated rounds")
    init_parser.add_argument(
        "target", nargs="?", default=".",
        help="directory to become the knowledge base root (default: the "
             "current directory)")
    init_parser.add_argument(
        "--world", action="store_true",
        help="seed the same knowledge base and add the dependency "
             "settings block to its .env — a world is a role a knowledge "
             "base plays by holding [Knowledge Base Dependency] entries, authored in its "
             "first gated round")
    init_parser.add_argument(
        "--name", default=None,
        help="the knowledge base's declared name, written onto its "
             "Ontology anchor so it travels with the committed backup "
             "(default: the target directory's basename)")
    sub.add_parser(
        "corpus",
        help="re-check every owner-approved floor (the regression corpus): each guard "
             "must still exist and still pass; reds name the approval "
             "they break")
    delta_parser = sub.add_parser(
        "delta",
        help="diff the scratch database against canon's backup: "
             "the agentic changeset, linted and itemized")
    delta_parser.add_argument(
        "--database", default=None,
        help="the working database to diff (default: scratch, or "
             "<branch>-scratch with --branch)")
    delta_parser.add_argument(
        "--branch", default=None,
        help="diff a BRANCH's authoring copy against the branch's own "
             "base and write to the branch's round files")
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
        "--database", default=None,
        help="the working database to canonize from (default: scratch, "
             "or <branch>-scratch with --branch)")
    canonize_parser.add_argument(
        "--branch", default=None,
        help="apply to a BRANCH's own database, backup, and log — never "
             "live canon (the hard guard refuses if they collide). A "
             "branch never becomes canon by flag; succession is the "
             "owner's ceremony.")
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
    succession_parser = sub.add_parser(
        "succession",
        help="the owner's ceremony: a finished branch becomes canon — "
             "dry-run verifies every gate; --apply archives the outgoing "
             "canon, rebuilds live canon from the branch's line, and "
             "chains the adoption entry")
    succession_parser.add_argument(
        "--branch", required=True,
        help="the branch standing for succession")
    succession_parser.add_argument(
        "--apply", action="store_true",
        help="adopt (default is the verify-only dry run)")
    succession_parser.add_argument(
        "--by", default=None,
        help="who ruled the adoption (defaults to git user.name)")
    succession_parser.add_argument(
        "--archive-as", dest="archive_as", default=None,
        help="branch name that archives the superseded canon "
             "(default: superseded-<sequence>)")
    approve_parser = sub.add_parser(
        "approve",
        help="record the diff-gate approval against the current "
             "proposal's content hash — apply replays only this")
    approve_parser.add_argument(
        "--by", default=None,
        help="who approved (defaults to git user.name)")
    approve_parser.add_argument(
        "--branch", default=None,
        help="approve a BRANCH's own current round")
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

    if args.command == "docs":
        # Opens no knowledge base: it reads the installed engine's own
        # records, from anywhere.
        return cmd_docs(args.record)
    if args.command == "init":
        # Opens no knowledge base either — it births one where none
        # exists, so base-dir discovery cannot precede it.
        return cmd_init(args.target, name=args.name, world=args.world)

    base_dir = find_base_dir()
    load_corpus_grammars(base_dir)
    if args.command == "validate":
        status, _ = cmd_validate(base_dir)
        return status
    if args.command == "export":
        if args.from_sources:
            print("Attempted to serialize a from-sources build. Failed "
                  "due to: the from-sources era is closed — the backup "
                  "is written FROM the database (python -m graph "
                  "export).", file=sys.stderr)
            return 1
        if args.mask or args.out:
            if not (args.mask and args.out):
                print("Attempted a lens-scoped export. Failed due to: "
                      "--mask and --out travel together — name the "
                      "class(es) to mask AND the target directory.",
                      file=sys.stderr)
                return 2
            return cmd_export_lensed(base_dir, args.mask, args.out)
        return cmd_export(base_dir)
    if args.command == "restore":
        return cmd_restore(base_dir, database=args.database,
                           from_dir=args.from_dir, branch=args.branch,
                           base=args.base, by=args.by, invite=args.invite)
    if args.command == "branch":
        return cmd_branch(base_dir, args.name, invite=args.invite,
                          uninvite=args.uninvite, retire=args.retire,
                          by=args.by)
    if args.command == "merge":
        return cmd_merge(base_dir, args.source, args.target,
                         database=args.database)
    if args.command == "branches":
        return cmd_branches(base_dir, all_lines=args.all)
    if args.command == "rederive":
        return cmd_rederive(base_dir, apply=args.apply)
    if args.command == "kernel-migrate":
        return cmd_kernel_migrate(base_dir, args.apply)
    if args.command == "verify-seal":
        return cmd_verify_seal(base_dir, args.exam)
    if args.command == "receipt":
        return cmd_receipt(base_dir, args.files)
    if args.command == "dependencies":
        return cmd_dependencies(base_dir, branch=args.branch)
    if args.command == "load":
        return cmd_load(base_dir, database=args.database)
    if args.command == "connections":
        return cmd_connections(base_dir,
                               reset_passwords=args.reset_passwords)
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
    if args.command == "receipts":
        return cmd_receipts(base_dir, branch=args.branch)
    if args.command == "answer-keys":
        return cmd_answer_keys(base_dir, branch=args.branch)
    if args.command == "delta":
        return cmd_delta(base_dir, args.database, args.sync_bodies,
                         branch=args.branch)
    if args.command == "canonize":
        return cmd_canonize(base_dir, args.database, args.apply,
                            branch=args.branch)
    if args.command == "roundtrip":
        return cmd_roundtrip(base_dir, args.scope, args.draft,
                             book=args.book)
    if args.command == "succession":
        return cmd_succession(base_dir, args.branch, args.apply,
                              by=args.by, archive_as=args.archive_as)
    if args.command == "approve":
        return cmd_approve(base_dir, args.by, branch=args.branch)
    if args.command == "comprehend":
        return cmd_comprehend(base_dir, args.artifacts, args.recall,
                              args.dispose)
    return 2


if __name__ == "__main__":
    sys.exit(main())
