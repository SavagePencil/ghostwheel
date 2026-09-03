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
                       applied_log_path, attribution_log_path, parse_delta,
                       proposals_dir, read_applied_log, read_branch_fork,
                       read_json)

# The adoption record, twice: adoption.json archived with canon's rounds
# (the ceremony's durable side), adopted.json in the branch home (the
# marker the working-round guards read). Beside the record: the
# divergence summary — the superseded line's post-fork rounds, so a
# carry-forward round starts from an enumerated worklist instead of a
# hand-rolled export diff.
ADOPTION_FILE = "adoption.json"
ADOPTION_MARKER = "adopted.json"
DIVERGENCE_FILE = "divergence.json"


def post_fork_rounds(base_dir, branch):
    """(fork_known, rounds): the rounds the line being superseded
    applied AFTER this branch's fork — the rulings that will NOT ride
    the adoption. rounds = [(sequence, delta_hash)]. A branch cut
    before fork annotations existed has no fork point on record:
    (False, []) — the advisory degrades honestly."""
    fork_record = read_branch_fork(base_dir, branch)
    if not isinstance(fork_record, dict) or "canon_sequence" not in fork_record:
        return False, []
    fork = fork_record["canon_sequence"]
    return True, [(seq, delta_hash)
                  for seq, delta_hash, *_rest in read_applied_log(base_dir)
                  if seq > fork]


def divergence_summary(base_dir, rounds):
    """One row per post-fork round: sequence, id, and the delta's
    summary counts read from the archived round dir (None when the
    archive holds no readable changeset — an adoption entry, or a
    pruned round)."""
    rows = []
    for seq, delta_hash in rounds:
        row = {"sequence": seq, "id": delta_hash[:12]}
        delta_path = (proposals_dir(base_dir) / delta_hash[:12]
                      / "delta.json")
        try:
            delta = parse_delta(delta_path.read_text(encoding="utf-8"))
            row["summary"] = {
                "nodes_added": len(delta.nodes_added),
                "nodes_changed": len(delta.nodes_changed),
                "nodes_removed": len(delta.nodes_removed),
                "edges_added": len(delta.edges_added),
                "edges_changed": len(delta.edges_changed),
                "edges_removed": len(delta.edges_removed),
            }
        except (OSError, ValueError, KeyError):
            row["summary"] = None
        rows.append(row)
    return rows


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
    ledger = attribution_log_path(base_dir)
    if ledger.exists():
        shutil.copy2(ledger, attribution_log_path(base_dir,
                                                  archive_branch))
    src_rounds = proposals_dir(base_dir)
    dst_rounds = proposals_dir(base_dir, archive_branch)
    skip = {current_dir(base_dir).name, applied_log_path(base_dir).name,
            attribution_log_path(base_dir).name}
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


# -- the gate checklist as a durable record -------------------------------
#
# The verify phase's pass/warn checklist used to vanish with the scroll
# — a ruling made on evidence that kept no record. Every ceremony run
# (dry and apply alike) now writes the checklist as a report beside the
# other renderings, and an applied adoption archives it beside the
# adoption record. Best-effort, like canonize's refusal record: a
# report that cannot be written never masks the ceremony's own outcome.

CHECKLIST_REPORT_FILE = "succession-report.json"


def checklist_report(base_dir, branch, gates, fork_known, diverged,
                     guard_problems=None):
    """The ceremony's evidence as one document: kind, the lines of
    truth involved, one row per verify gate (PASS rows recorded too —
    a checklist is evidence of what was checked, not only of what
    failed), the divergence advisory's facts, and — when the ceremony
    refused before the gates even ran — the guard's collated problems.
    ``gates`` rows are (label, code, problems) or, when a gate's
    problems are findings, (label, code, problems, findings): the prose
    problems keep the terminal's voice and the findings ride as typed
    rows beside them."""
    from .report import record_header, ref_key
    doc = record_header(base_dir, "succession-report", branch)
    if guard_problems is not None:
        doc["guard"] = {"code": "ceremony-guard",
                        "ref": ref_key("ceremony-guard"),
                        "problems": [str(p) for p in guard_problems]}
        return doc
    rows = []
    for gate in gates:
        label, code, problems = gate[0], gate[1], gate[2]
        findings = gate[3] if len(gate) > 3 else ()
        row = {"gate": label, "code": code, "ref": ref_key(code),
               "status": "pass" if not problems else "fail"}
        if problems:
            row["problems"] = [str(p) for p in problems]
        if findings:
            row["findings"] = [f.row(kb=doc["kb"], branch=branch)
                               for f in findings]
        rows.append(row)
    doc["gates"] = rows
    doc["divergence"] = (
        {"fork_known": True,
         "post_fork_rounds": [{"sequence": seq, "id": delta_hash[:12]}
                              for seq, delta_hash in diverged]}
        if fork_known else {"fork_known": False})
    return doc


def write_checklist_report(base_dir, doc):
    from .report import write_record
    return write_record(base_dir, CHECKLIST_REPORT_FILE, doc)
