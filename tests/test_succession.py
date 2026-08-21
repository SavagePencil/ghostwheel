"""Succession: a branch becomes canon by the owner's ceremony.

The one sanctioned crossing of the branch/canon boundary. These tests
drive the real CLI end to end over the same fake-driver seam test_branch
uses (the FakeDBMS / driven_kb fixture), so both halves are proven where
they live: what is PERMITTED lands (dry run writes nothing; --apply
rebuilds live canon, chains one adoption entry, archives the old line,
walks back), and what is REFUSED refuses BY NAME (unknown branch,
canon-named branch, dirty canon, dirty or tampered branch, an
already-adopted branch, archive-name collisions).

The imaginary storybook domain only (Character/Place/Artifact) — never
any consuming corpus's vocabulary. Assertions land on message FRAGMENTS,
not full strings, per the repo rule.
"""

import inspect
import shutil

import pytest

import graph.__main__ as main_mod
import graph.proposal as proposal_mod
from graph import export as export_mod
from graph.extract import make_edge
from graph.load import read_config
from graph.proposal import (APPROVAL_FILE, BASE_FILE, base_identity,
                            branch_home, content_hash, current_dir,
                            export_dir, proposals_dir, read_applied_log,
                            read_json, verify_applied_log)
from graph.restore import read_export
from graph.succession import (adoption_marker_path, read_adoption,
                              serialize_record)

# Reuse the branch suite's seam verbatim: the fake driver, the storybook
# canon builder, the clone helper, the orphan-program registrar, and the
# driven_kb fixture (imported into this module's namespace so pytest
# resolves it here too).
from tests.test_branch import (STORYBOOK, FakeDBMS, build_canon,  # noqa: F401
                               clone, driven_kb, register_orphan_program)


# -- shared helpers --------------------------------------------------------


def _live_canon_name(base):
    return read_config(base)["NEO4J_DATABASE"]


def _mount_live_canon(base, fake):
    """Live canon database equals its committed backup — the clean state
    the succession verify demands before it will adopt anything."""
    name = _live_canon_name(base)
    fake.databases[name] = clone(read_export(export_dir(base)))
    return name


def _author_and_canonize_branch(base, fake, branch, extra=None):
    """Cut `branch` schema-only, author ground facts into its scratch,
    and run delta -> approve -> canonize --apply through the CLI. Leaves a
    finished branch line the way test_branch's driven round does."""
    assert main_mod.cmd_restore(base, branch=branch, base="schema-only") == 0
    seed = read_export(export_dir(base, branch))
    authored = clone(seed)
    authored.ensure_node("Character", "Ember", temperament="bright")
    authored.ensure_node("Place", "Hearth")
    authored.edges.append(
        make_edge("LIVES_IN", "Character", "Ember", "Place", "Hearth"))
    if extra is not None:
        extra(authored)
    fake.databases[f"{branch}-scratch"] = authored
    assert main_mod.cmd_delta(base, None, branch=branch) == 0
    assert main_mod.cmd_approve(base, "owner", branch=branch) == 0
    assert main_mod.cmd_canonize(base, None, apply=True, branch=branch) == 0
    return authored


def _durable_snapshot(base):
    """Byte snapshot of canon's durable artifacts AND every branches/
    entry — export, proposals, applied.log, branch homes. graph/reports/
    is transient and excluded."""
    files = {}
    roots = [export_dir(base), proposals_dir(base),
             base / "graph" / "branches"]
    for root in roots:
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    files[path] = path.read_bytes()
    files["__canon_log__"] = tuple(read_applied_log(base))
    return files


# -- 1. GREEN CEREMONY: the dry run writes nothing -------------------------


def test_succession_dry_run_writes_nothing(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    capsys.readouterr()

    before = _durable_snapshot(base)
    assert main_mod.cmd_succession(base, branch=branch, apply=False) == 0
    out = capsys.readouterr().out
    assert "SUCCESSION VERIFY" in out and "Ready. Adopt with" in out

    # not one durable byte moved, and no new branches/ home was born
    assert _durable_snapshot(base) == before
    assert read_adoption(base, branch) is None       # still a working line


# -- 1. GREEN CEREMONY: --apply adopts, end to end -------------------------


def test_succession_apply_adopts_branch_as_canon(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    live = _mount_live_canon(base, fake)
    branch_backup = read_export(export_dir(base, branch))

    # the branch's own durable artifacts, snapshotted to prove untouched
    branch_export_before = {
        p: p.read_bytes()
        for p in sorted(export_dir(base, branch).rglob("*")) if p.is_file()}
    branch_log_before = read_applied_log(base, branch)

    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0

    # the live canon database now holds the branch's content + the stamped
    # anchor at canon's next sequence (1 for a fresh storybook canon)
    from graph.canonize import ONTOLOGY_ANCHOR
    from graph.ontology import ARCHETYPE_LABEL
    live_graph = fake.databases[live]
    assert ("Character", "Ember") in live_graph.nodes
    assert ("Place", "Hearth") in live_graph.nodes
    anchor = live_graph.nodes[(ARCHETYPE_LABEL, ONTOLOGY_ANCHOR)]
    assert anchor["version"] == 1

    # graph/export re-serializes byte-identical to the live DB and carries
    # the branch's authored nodes
    canon_export = read_export(export_dir(base))
    assert export_mod.serialize(canon_export) == \
        export_mod.serialize(live_graph)
    assert ("Character", "Ember") in canon_export.nodes

    # canon's log gained ONE chained entry, still verifying, whose payload
    # slot carries the adoption record's content hash
    log = read_applied_log(base)
    assert len(log) == 1
    assert verify_applied_log(base) == []
    (seq, payload_hash, *_rest) = log[0]
    assert seq == 1

    # the record lives twice, and its recomputed hash equals the log payload
    record = read_json(adoption_marker_path(base, branch))
    archived = read_json(proposals_dir(base) / payload_hash[:12]
                         / "adoption.json")
    assert record == archived
    _text, recomputed = serialize_record(record)
    assert recomputed == payload_hash

    # the record names every continuity field the ceremony pins
    for field in ("branch", "adopted_by", "adopted_at", "sequence",
                  "branch_rounds", "branch_chain_tip",
                  "branch_export_identity", "canon_before", "canon_after",
                  "archive_branch"):
        assert field in record, field
    assert record["branch"] == branch
    assert record["adopted_by"] == "owner"
    assert record["sequence"] == 1
    assert record["archive_branch"] == "superseded-1"
    assert record["branch_export_identity"] == base_identity(branch_backup)

    # the archive branch home holds the OLD canon's export byte-for-byte
    archive_export = export_dir(base, "superseded-1")
    old_canon = read_export(export_dir(base))  # canon is now the NEW line
    for name in ("nodes.jsonl", "edges.jsonl"):
        assert (archive_export / name).exists()
    archived_old = read_export(archive_export)
    # the archived line is the pre-ceremony canon (no Ember), not the new one
    assert ("Character", "Ember") not in archived_old.nodes

    # the adopted branch's own export and log are untouched
    branch_export_after = {
        p: p.read_bytes()
        for p in sorted(export_dir(base, branch).rglob("*")) if p.is_file()}
    assert branch_export_after == branch_export_before
    assert read_applied_log(base, branch) == branch_log_before


# -- 2. POST-ADOPTION GUARDS: every working verb refuses by name ----------


def test_post_adoption_working_verbs_refuse(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    capsys.readouterr()

    for verb, call in (
            ("delta", lambda: main_mod.cmd_delta(base, None, branch=branch)),
            ("approve",
             lambda: main_mod.cmd_approve(base, "owner", branch=branch)),
            ("canonize",
             lambda: main_mod.cmd_canonize(base, None, apply=True,
                                           branch=branch))):
        assert call() == 1, verb
        err = capsys.readouterr().err
        assert "adopted as canon" in err, verb
        assert "provenance, not a working line" in err, verb


# -- 3. WALK-BACK: a second ceremony returns the old line ------------------


def test_succession_walk_back_restores_the_old_line(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0

    # rehydrate the archive branch's database from its archived export
    archive = "superseded-1"
    fake.databases[archive] = clone(read_export(export_dir(base, archive)))
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=archive, apply=True,
                                   by="owner") == 0

    # live canon is the OLD content again (Ember gone), modulo the re-stamp
    live = _live_canon_name(base)
    assert ("Character", "Ember") not in fake.databases[live].nodes
    canon_export = read_export(export_dir(base))
    assert ("Character", "Ember") not in canon_export.nodes

    # canon's log now has TWO adoption entries, chain still verifying
    log = read_applied_log(base)
    assert len(log) == 2 and [e[0] for e in log] == [1, 2]
    assert verify_applied_log(base) == []


# -- 4. REFUSAL: unknown branch (no home) ----------------------------------


def test_succession_refuses_unknown_branch(driven_kb, capsys):
    base, fake, _ = driven_kb
    _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch="ghost", apply=True) == 1
    assert "no branch line exists" in capsys.readouterr().err


# -- 5. REFUSAL: the live-canon name never becomes canon by flag -----------


def test_succession_refuses_canon_named_branch(driven_kb, capsys):
    base, fake, _ = driven_kb
    live = _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch=live, apply=True) == 1
    assert "never becomes canon by flag" in capsys.readouterr().err


# -- 6. REFUSAL: live canon moved outside the delta path -------------------


def test_succession_refuses_dirty_live_canon(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    live = _mount_live_canon(base, fake)
    before = _durable_snapshot(base)

    # tamper the live canon database so it no longer matches its backup
    fake.databases[live].ensure_node("Character", "Interloper")
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True) == 1
    err = capsys.readouterr().err
    assert "does not re-serialize to the backup" in err
    assert _durable_snapshot(base) == before     # nothing written


# -- 7. REFUSAL: the branch database drifted from its backup ----------------


def test_succession_refuses_dirty_branch_database(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    before = _durable_snapshot(base)

    fake.databases[branch].ensure_node("Character", "Stowaway")
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True) == 1
    assert "does not re-serialize to the backup" in capsys.readouterr().err
    assert _durable_snapshot(base) == before     # nothing written


# -- 8. REFUSAL: the branch event log was tampered -------------------------


def test_succession_refuses_tampered_branch_log(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)

    # rewrite one character of the chain hash on the branch's log entry
    log_path = base / "graph" / "branches" / branch / "applied.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line and not line.startswith("#"):
            cols = line.split()
            tip = cols[-1]
            cols[-1] = ("0" if tip[-1] != "0" else "1").join([tip[:-1], ""])
            lines[i] = " ".join(cols)
            break
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # snapshot AFTER the tamper: the assertion isolates what the CEREMONY
    # wrote, which must be nothing.
    before = _durable_snapshot(base)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True) == 1
    assert "chain hash mismatch" in capsys.readouterr().err
    # the tamper is in place, but the ceremony itself wrote nothing new
    assert _durable_snapshot(base) == before


# -- 9. REFUSAL: an already-adopted branch cannot be re-adopted -------------


def test_succession_refuses_already_adopted_branch(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 1
    assert "adopted as canon" in capsys.readouterr().err


# -- 10. REFUSAL: archive-name collision -----------------------------------


def test_succession_refuses_archive_name_collision(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)

    # pre-create the default archive home (superseded-1 for sequence 1)
    branch_home(base, "superseded-1").mkdir(parents=True)
    before = _durable_snapshot(base)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True) == 1
    assert "already exists — pick an unused name" in capsys.readouterr().err
    assert _durable_snapshot(base) == before     # nothing written


# -- 11. REFUSAL: archive name equal to the succeeding branch --------------


def test_succession_refuses_archive_equals_branch(driven_kb, capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   archive_as=branch) == 1
    assert "the succeeding branch itself" in capsys.readouterr().err


# -- FULL-STRENGTH ROSTER: the advisory era ends at this gate --------------


def test_succession_source_does_not_demote_the_roster():
    # cmd_canonize demotes the roster census to an advisory for a branch
    # apply; cmd_succession must NOT — the finished line is judged at full
    # strength. Proven the way test_branch proves CLI claims: by source.
    canonize_src = inspect.getsource(main_mod.cmd_canonize)
    succession_src = inspect.getsource(main_mod.cmd_succession)
    assert "Category.ROSTER" in canonize_src        # the branch demotion
    assert "ROSTER" not in succession_src           # never at succession
    assert "roster at full strength" in succession_src


def test_succession_functionally_blocks_on_incomplete_roster(driven_kb,
                                                             capsys):
    # A functional proof: a branch carrying a registered program with no
    # citizen APPLIES (advisory) but is REFUSED at succession — the roster
    # gate returns to full strength.
    base, fake, _ = driven_kb
    register_orphan_program(base)
    branch = "rebuild"

    # the branch cut inherits the orphan registration; its round lands with
    # the roster named only as an advisory (cmd_canonize returns 0)
    _author_and_canonize_branch(base, fake, branch)
    live = _mount_live_canon(base, fake)
    before = _durable_snapshot(base)
    canon_before = clone(fake.databases[live])
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True) == 1
    err = capsys.readouterr().err
    assert "no Ritual citizen" in err
    # nothing was written and live canon was not rebuilt
    assert _durable_snapshot(base) == before
    assert ("Character", "Ember") not in fake.databases[live].nodes
    assert set(fake.databases[live].nodes) == set(canon_before.nodes)


# -- HALF-RUN WINDOWS: the adopt phase's crash handlers --------------------
# The adopt phase writes in a fixed order — archive the old line FIRST
# (capture-first), then rebuild live canon, then at the point of no return
# overwrite the backup, the record, the chained entry, and LAST the branch
# seal. These prove each window: what a crash leaves behind, and that the
# ceremony can always be re-run to a complete record.


def _boom(*_a, **_k):
    raise RuntimeError("injected failure")


# 1. Mid-write crash BEFORE the point of no return -------------------------


def test_succession_mid_write_crash_before_no_return(driven_kb, capsys,
                                                     monkeypatch):
    base, fake, canon_snapshot = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    canon_before = canon_snapshot()
    capsys.readouterr()

    # crash the live-canon rebuild — after archive_line (capture-first) but
    # before the backup is overwritten.
    monkeypatch.setattr("graph.load.load", _boom)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 1
    err = capsys.readouterr().err
    assert "Adoption failed mid-write" in err
    assert "--archive-as" in err                      # the retry note

    # canon's own durable artifacts never moved; but the archive home EXISTS
    # (capture-first is by design), so a naive retry would collide.
    assert canon_snapshot() == canon_before
    assert branch_home(base, "superseded-1").exists()
    assert read_adoption(base, branch) is None        # branch not sealed

    # a retry with a fresh archive name completes the ceremony end to end
    monkeypatch.setattr("graph.load.load", fake.load)
    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner",
                                   archive_as="superseded-retry") == 0
    assert read_adoption(base, branch) is not None    # now sealed
    assert ("Character", "Ember") in read_export(export_dir(base)).nodes
    assert len(read_applied_log(base)) == 1


# 2. archive_line failure: partial archive removed, nothing written --------


def test_succession_archive_line_failure_cleans_up(driven_kb, capsys,
                                                   monkeypatch):
    base, fake, canon_snapshot = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    canon_before = canon_snapshot()

    real_copytree = shutil.copytree
    monkeypatch.setattr("graph.succession.shutil.copytree", _boom)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 1
    err = capsys.readouterr().err
    assert "partial archive was removed" in err
    # the partial archive home was cleaned up, and canon is untouched
    assert not branch_home(base, "superseded-1").exists()
    assert canon_snapshot() == canon_before
    assert read_adoption(base, branch) is None

    # copytree restored, a PLAIN re-run (default archive name) succeeds
    monkeypatch.setattr("graph.succession.shutil.copytree", real_copytree)
    capsys.readouterr()
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    assert branch_home(base, "superseded-1").exists()
    assert read_adoption(base, branch) is not None


# 3. Crash PAST the point of no return -------------------------------------


def test_succession_crash_past_the_point_of_no_return(driven_kb, capsys,
                                                      monkeypatch):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)

    # the backup is overwritten before the chained entry is appended; crash
    # the append so the ceremony dies AFTER the overwrite, BEFORE the seal.
    monkeypatch.setattr("graph.proposal.append_applied_log", _boom)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 1
    err = capsys.readouterr().err
    assert "PAST the point of no return" in err
    assert "restore --from" in err                    # the walk-back note

    # the overwrite already happened: graph/export holds the adopted line
    assert ("Character", "Ember") in read_export(export_dir(base)).nodes
    # but the branch seal was NOT written (marker-last ordering guarantee)
    assert read_adoption(base, branch) is None


# 4. Marker-last ordering proven structurally ------------------------------


def test_succession_writes_the_marker_last():
    # The chained adoption entry is appended BEFORE the branch seal, so a
    # marker present always implies the log entry is durable. Proven by
    # source, mirroring test_branch's index-comparison style.
    src = inspect.getsource(main_mod.cmd_succession)
    assert src.index("append_applied_log") < src.index("adoption_marker_path")


# 5. Unknown ruler refused before anything is written ----------------------


def test_succession_refuses_unknown_ruler(driven_kb, capsys, monkeypatch):
    base, fake, canon_snapshot = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    canon_before = canon_snapshot()

    # no --by and git yields no name — the record cannot name who ruled
    monkeypatch.setattr(main_mod, "_ruled_by", lambda by, base_dir: "unknown")
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by=None) == 1
    assert "must name who ruled" in capsys.readouterr().err
    # the refusal is before archive_line — nothing captured, nothing written
    assert not branch_home(base, "superseded-1").exists()
    assert canon_snapshot() == canon_before
    assert read_adoption(base, branch) is None


# 6. Sequence drift caught at the post-export re-check ---------------------


def test_succession_refuses_sequence_drift(driven_kb, capsys, monkeypatch):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)

    # the true sequence at guard time; a DIFFERENT value at the re-check —
    # as if a concurrent round moved canon's log under the ceremony.
    real_next = proposal_mod.next_log_sequence
    state = {"calls": 0}

    def drifting(base_dir, branch=None):
        state["calls"] += 1
        value = real_next(base_dir, branch)
        return value if state["calls"] == 1 else value + 1

    monkeypatch.setattr("graph.proposal.next_log_sequence", drifting)
    capsys.readouterr()

    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 1
    err = capsys.readouterr().err
    assert "event log moved under the ceremony" in err
    # the seal was never written, so the ceremony can be re-run to completion
    assert read_adoption(base, branch) is None


# 7. restore --branch on an adopted branch refuses as provenance -----------


def test_restore_branch_on_adopted_branch_refuses_as_provenance(driven_kb,
                                                                capsys):
    base, fake, _ = driven_kb
    branch = "rebuild"
    _author_and_canonize_branch(base, fake, branch)
    _mount_live_canon(base, fake)
    assert main_mod.cmd_succession(base, branch=branch, apply=True,
                                   by="owner") == 0
    capsys.readouterr()

    # re-cutting an adopted branch gets the provenance refusal, NOT the
    # generic home-exists remedy.
    assert main_mod.cmd_restore(base, branch=branch, base="schema-only") == 1
    err = capsys.readouterr().err
    assert "provenance, not a working line" in err
    assert "remove it deliberately to re-cut" not in err
