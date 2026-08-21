"""Succession: a branch becomes canon by the owner's ceremony.

The one sanctioned crossing of the branch/canon boundary — never a flag
on an ordinary round (the hard guard refuses those by name). The verify
phase runs every gate and collates every problem, verify-all-before-
apply-any: nothing is written on any failure. The adopt phase captures
the outgoing canon as an archive branch BEFORE anything is overwritten,
so the ceremony can be walked back by a second ceremony.

The owner's continuity rulings (2026-08-20):
- Canon's chained event log continues unbroken: adoption appends ONE
  entry whose payload slot carries the adoption record's content hash.
  The record pins who ruled, when, the branch's chain tip, and the
  adopted export's identity — so lineage is cryptographic and the
  version stamp stays monotonic. The branch's own log survives in its
  archived home.
- The branch home is archived in place, marked by the adoption record;
  any further round on an adopted branch refuses by name.
- The superseded canon is archived as a branch (export + event log +
  archived rounds), rehydratable with restore --from for a walk-back.
"""

import json
import shutil

from .proposal import (branch_home, content_hash, current_dir, export_dir,
                       applied_log_path, proposals_dir, read_json)

# The adoption record, twice: adoption.json archived with canon's rounds
# (the ceremony's durable side), adopted.json in the branch home (the
# marker the working-round guards read).
ADOPTION_FILE = "adoption.json"
ADOPTION_MARKER = "adopted.json"


def adoption_marker_path(base_dir, branch):
    return branch_home(base_dir, branch) / ADOPTION_MARKER


def read_adoption(base_dir, branch):
    """The branch's adoption record, or None while it is a working line."""
    path = adoption_marker_path(base_dir, branch)
    if not path.exists():
        return None
    return read_json(path)


def adopted_branch_problem(base_dir, branch, attempted):
    """The adopted-branch guard: an adopted branch is provenance, not a
    working line. Returns the error-doctrine refusal, or None."""
    record = read_adoption(base_dir, branch)
    if record is None:
        return None
    return (f"Attempted {attempted} on branch '{branch}'. Failed due to: "
            f"this branch was adopted as canon (sequence "
            f"{record.get('sequence', '?')}, ruled by "
            f"{record.get('adopted_by', 'unknown')} at "
            f"{record.get('adopted_at', 'unknown')}) — an adopted branch "
            "is provenance, not a working line. Cut a new branch for new "
            "work.")


def line_lint(branch_graph):
    """Whole-line ground authorability sweep: the branch's full ground
    layer diffed from its own schema stratum, so every ground fact
    stands as an addition and the round lint judges the entire line at
    once — the succession-gate form of "lint clean"."""
    from .delta import diff, lint
    from .extract import schema_only, strip_derived
    schema = schema_only(branch_graph)
    return lint(diff(schema, strip_derived(branch_graph)), schema)


def serialize_record(record):
    """The adoption record's canonical bytes and content hash — the hash
    rides the event-log entry's payload slot, so an auditor recomputing
    it from the archived file must get the same text. Returns
    (text, hash)."""
    text = json.dumps(record, ensure_ascii=False, indent=2,
                      sort_keys=True) + "\n"
    return text, content_hash(text)


def archive_line(base_dir, archive_branch):
    """Capture the outgoing canon into a branch home — export, event
    log, archived rounds (never the transient current/) — before
    anything is overwritten. The copy is both the ceremony's recovery
    point and the walk-back line: rehydrate its database with
    restore --from, then run a second succession."""
    home = branch_home(base_dir, archive_branch)
    shutil.copytree(export_dir(base_dir), export_dir(base_dir,
                                                     archive_branch))
    log = applied_log_path(base_dir)
    if log.exists():
        shutil.copy2(log, applied_log_path(base_dir, archive_branch))
    src_rounds = proposals_dir(base_dir)
    dst_rounds = proposals_dir(base_dir, archive_branch)
    skip = {current_dir(base_dir).name, applied_log_path(base_dir).name}
    if src_rounds.is_dir():
        for entry in sorted(src_rounds.iterdir()):
            if entry.name in skip:
                continue
            if entry.is_dir():
                shutil.copytree(entry, dst_rounds / entry.name)
            else:
                dst_rounds.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, dst_rounds / entry.name)
    return home
