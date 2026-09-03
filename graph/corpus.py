"""The regression corpus: owner-approved floors, re-checked
before any "done".

Spine phase 3 of the agentic approach (design:
graph/design/agentic-approach.md §7 — "owner-approved floors are
re-checked before any done"). A FLOOR is one owner-approved expectation
with provenance: the check that guards it (a pytest node id), its
scope, the expectation in plain words, and the approval that made it a
floor (a PR, a Decision row, a run id). The Approved Omission and
Approved Difference rows the owner already rules on are this exact
pattern inside the parity judge; the corpus generalizes it to
everything the owner has ever caught or approved — every calibration
miss becomes a floor by doctrine (tenet 13: every catch becomes a
check).

What the ledger adds over the bare test suite: the tie from each guard
back to the approval that made it, and — what a suite cannot do —
catching the guard itself vanishing. A floor whose test node was
deleted or renamed reports as "the guard is gone", naming the approval
it orphaned, instead of silently ceasing to protect anything.

The ledger is graph/corpus/floors.jsonl — append-only, one floor per
line, git-tracked. `python -m graph corpus` re-checks every floor and
reports in owner-facing language: passed / FAILED (with its
provenance) / GUARD MISSING (with its provenance). Pure logic (ledger, matching,
report) is driver-free and unit-tested; only the collect/run helpers
shell out to pytest.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

FLOORS_FILE = "floors.jsonl"

_NODE_ID = re.compile(r"^tests/[\w./-]+\.py::\w+$")


def floors_path(base_dir):
    return Path(base_dir) / "graph" / "corpus" / FLOORS_FILE


def load_floors(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def save_floors(path, floors):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(floor, ensure_ascii=False, sort_keys=True)
             for floor in floors]
    path.write_text("\n".join(lines) + ("\n" if lines else ""),
                    encoding="utf-8")


def record_floor(floors, check, scope, expectation, provenance):
    """One approval becomes one floor. check is the pytest node id that
    guards the expectation (parameterized variants count as the same
    guard); provenance names the ruling — a PR, a Decision row, a run
    id. Refuses duplicates and empty fields: an unguarded or unowned
    floor protects nothing."""
    for field_name, value in (("check", check), ("scope", scope),
                              ("expectation", expectation),
                              ("provenance", provenance)):
        if not value or not str(value).strip():
            raise ValueError(
                f"Attempted to record a floor with an empty "
                f"{field_name}. Failed because every floor names its "
                "guard, its scope, the expectation in plain words, and "
                "the approval that made it a floor.")
    if not _NODE_ID.match(check):
        raise ValueError(
            f"Attempted to record a floor guarded by '{check}'. Failed "
            "because the guard must be a pytest node id "
            "(tests/<file>.py::<test name>, without parameter "
            "brackets) — that is what the corpus re-collects to prove "
            "the guard still exists.")
    for floor in floors:
        if floor["check"] == check:
            raise ValueError(
                f"Attempted to record a second floor guarded by "
                f"'{check}'. Failed because that guard already backs "
                f"the floor '{floor['expectation']}' "
                f"({floor['provenance']}) — extend that floor's "
                "expectation, or write a new guard for the new "
                "expectation.")
    floor = {"check": check, "scope": scope, "expectation": expectation,
             "provenance": provenance}
    floors.append(floor)
    return floor


# -- guard existence: the corpus re-collects its own guards ----------------


def parse_collected(text):
    """pytest --collect-only -q output -> the set of BASE node ids
    (parameterized variants fold onto their base id)."""
    collected = set()
    for line in text.splitlines():
        line = line.strip()
        if "::" not in line or not line.startswith("tests/"):
            continue
        collected.add(line.split("[", 1)[0])
    return collected


def collect_guards(base_dir):
    """The test suite's live node ids, from pytest itself."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=base_dir, capture_output=True, text=True)
    return parse_collected(result.stdout)


# one row per floor: what was checked and how it came out — held rows
# recorded too, because a corpus verdict is evidence of what was
# re-checked, not only of what broke
FLOOR_HELD = "held"
FLOOR_FAILED = "failed"
FLOOR_GUARD_MISSING = "guard-missing"


def floor_records(floors, collected, failed_ids=()):
    """The corpus verdict as records: one per floor, in ledger order,
    with the floor's own facts (check, expectation, provenance), a
    status, a verdict code with its designer-facing ref, and — for reds
    — the problem sentence the prose report prints."""
    from .report import ref_key
    failed_ids = set(failed_ids)
    records = []
    for floor in floors:
        row = {"check": floor["check"],
               "expectation": floor["expectation"],
               "provenance": floor["provenance"]}
        if floor["check"] not in collected:
            row.update(status=FLOOR_GUARD_MISSING, code="floor-guard-missing",
                       problem=(
                f"the guard {floor['check']} is GONE — it protected "
                f"\"{floor['expectation']}\" (approved at "
                f"{floor['provenance']}). Restore the test or bring "
                "the floor's retirement to the owner; floors are never "
                "silently dropped."))
        elif floor["check"] in failed_ids:
            row.update(status=FLOOR_FAILED, code="floor-failed",
                       problem=(
                f"the floor \"{floor['expectation']}\" FAILED its "
                f"guard ({floor['check']}) — this was approved at "
                f"{floor['provenance']}; the current change breaks a "
                "prior approval. Fix the change, or bring the floor's "
                "supersession to the owner."))
        else:
            row.update(status=FLOOR_HELD, code="floor-held")
        row["ref"] = ref_key(row["code"])
        records.append(row)
    return records


def missing_guards(floors, collected):
    """Floors whose guard no longer exists — each named with the
    approval it orphans. A deleted guard is a red, never a silence."""
    return [row["problem"] for row in floor_records(floors, collected)
            if row["status"] == FLOOR_GUARD_MISSING]


def failed_floor_ids(base_dir, floors, collected):
    """Run every floor whose guard exists; the ids of the guards that
    failed (empty when nothing ran)."""
    checks = [floor["check"] for floor in floors
              if floor["check"] in collected]
    if not checks:
        return set()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no", *checks],
        cwd=base_dir, capture_output=True, text=True)
    return {line.split()[1].split("[", 1)[0]
            for line in result.stdout.splitlines()
            if line.startswith("FAILED ")}


def run_floors(base_dir, floors, collected):
    """Run every floor whose guard exists; return failure lines, each
    tied back to its floor's expectation and provenance."""
    failed_ids = failed_floor_ids(base_dir, floors, collected)
    return [row["problem"]
            for row in floor_records(floors, collected, failed_ids)
            if row["status"] == FLOOR_FAILED]


CORPUS_REPORT_FILE = "corpus-report.json"


def corpus_report(base_dir, records, guard_problem=None):
    """The corpus verdict as one durable record: kind, the line of
    truth, one row per floor — or, when the suite could not be
    re-collected at all, the guard that stopped the re-check."""
    from .report import record_header, ref_key
    doc = record_header(base_dir, "corpus-report")
    if guard_problem is not None:
        doc["guard"] = {"code": "corpus-uncollectable",
                        "ref": ref_key("corpus-uncollectable"),
                        "problem": guard_problem}
        return doc
    doc["floors"] = list(records)
    doc["counts"] = {status: sum(1 for r in records
                                 if r["status"] == status)
                     for status in (FLOOR_HELD, FLOOR_FAILED,
                                    FLOOR_GUARD_MISSING)}
    return doc


def render_report(floors, missing, failures):
    """Owner-facing corpus verdict."""
    lines = ["# Regression corpus — every approved floor, re-checked", ""]
    if not floors:
        lines += ["The corpus is empty — no floors recorded yet.", ""]
        return "\n".join(lines)
    held = len(floors) - len(missing) - len(failures)
    lines += [f"**{len(floors)} floors: {held} held · "
              f"{len(failures)} failed · {len(missing)} guards missing**",
              ""]
    if failures:
        lines += ["## Failed — prior approvals broken", ""]
        lines += [f"- ⚠ {problem}" for problem in failures] + [""]
    if missing:
        lines += ["## Guards missing — protection silently lost", ""]
        lines += [f"- ⚠ {problem}" for problem in missing] + [""]
    if not failures and not missing:
        lines += ["Every floor held — nothing the owner approved has "
                  "been broken.", ""]
    return "\n".join(lines)
