"""Typed report records — facts first, prose as a rendering.

The delta gate's verdicts and ceremony items are born here as records:
a stable code, the subject citizen or connection, the particulars, and
the remedy — with the human sentence carried alongside. Markdown is one
renderer over the model, JSON another; neither invents content the
records don't hold, so any future surface (a lay-voiced gate, a query
room, a UI) reads the facts without parsing prose.

Two conventions this module holds to:

- ``message`` is the complete sentence a human reads, exactly as the
  report has always phrased it; ``remedy`` repeats the actionable tail
  as a standalone field so machines never parse prose for it. A future
  wording pass may de-duplicate; the record shape already permits it.
- Serialized rows follow the house style: plain dicts, snake_case keys,
  optional fields omitted when empty. Citizens and connections are
  referenced through the refs module's structs (CitizenRef /
  ConnectionRef) — one shape on every machine surface, each row
  carrying its knowledge base (and branch, off the default line) when
  the renderer knows the line it is serving.
"""

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .refs import CitizenRef, ConnectionRef

if TYPE_CHECKING:  # delta imports report; the reverse edge is type-only
    from .delta import Delta

REFUSAL = "refusal"
ADVISORY = "advisory"

# The reference-number keys (front-door tenet T10): every verdict code
# maps to the quiet plain-English key a designer sees in an item's
# ⟨subject · ref⟩ reference number. Several codes may share a key —
# the code stays the forensic identity; the key names the problem kind
# in designer-safe words (no machinery vocabulary, ever). Unmapped
# codes fall back to themselves so a ref always exists.
REF_KEYS = {
    # the schema ceremony
    "schema-label-row-authored": "structure-change",
    "schema-edit-out-of-class": "structure-change",
    "schema-label-row-removed": "structure-change",
    "schema-concept-undeclared": "undeclared-concept",
    "schema-label-undeclared": "undeclared-catalog",
    "schema-label-spec-unreadable": "unreadable-catalog-spec",
    "schema-removal-unverified": "unverified-removal",
    "schema-row-referenced": "still-referenced",
    "alias-target-missing": "spelling-target-missing",
    "schema-edge-authored": "structure-change",
    "schema-edge-removed": "structure-change",
    "schema-edge-modified": "structure-change",
    # ground facts
    "machine-label-authored": "machine-made-kind",
    "row-receipt-authored": "row-as-receipt",
    "receipt-unverified": "evidence-not-found",
    "receipt-stale": "evidence-moved",
    "node-unnamed": "unnamed",
    "edge-endpoint-unnamed": "unnamed",
    "derived-edge-authored": "machine-managed-link",
    "derived-edge-modified": "machine-managed-link",
    # declared membership
    "membership-from-archetype": "reversed-membership",
    "membership-unverified": "unverified-membership",
    "membership-target-not-concept": "wrong-membership-target",
    "membership-basis-missing": "missing-reason",
    "membership-basis-blanked": "reason-removed",
    # the stitch
    "stitch-schema-edge": "structure-change",
    "stitch-derived-edge": "machine-managed-link",
    "stitch-endpoint-unnamed": "unnamed",
    "stitch-unneeded": "unneeded",
    "stitch-file-unreadable": "unreadable-file",
    "stitch-landing": "connection-failed",
    # program bodies and the roster
    "body-file-unreadable": "unreadable-file",
    "body-out-of-sync": "out-of-sync",
    "roster-gap": "missing-entry",
    # the taxonomy declaration
    "taxonomy-declared": "kind-of-declared",
    "taxonomy-endpoint-missing": "missing-citizen",
    # recorded attribution (the provenance-recording rung)
    "attribution-file-unreadable": "unreadable-file",
    "attribution-row-malformed": "misrecorded-evidence",
    "attribution-home-missing": "evidence-without-home",
    # the health checks (the durable-record work): every verdict a
    # check surface produces, PASS rows included
    "check-passed": "held",
    "check-failed": "integrity-broken",
    "check-findings": "for-the-record",
    "check-unreachable": "store-unreachable",
    "check-none": "nothing-to-check",
    "floor-held": "held",
    "floor-failed": "approval-broken",
    "floor-guard-missing": "protection-lost",
    "corpus-uncollectable": "suite-not-runnable",
    "seal-verified": "sealed-intact",
    "seal-broken": "seal-broken",
    "seal-none": "nothing-sealed",
    "seal-file-unreadable": "unreadable-file",
    "drill-passed": "backup-faithful",
    "drill-failed": "backup-mismatch",
    "restore-load-failed": "store-unreachable",
    "restore-guard": "cannot-begin",
    "dependency-incomplete": "pin-incomplete",
    "dependency-intent-unknown": "pin-intent-unknown",
    "dependency-sequence-invalid": "pin-sequence-invalid",
    "dependency-still-cited": "pin-still-cited",
    "bookmark-incomplete": "foreign-citation-incomplete",
    "bookmark-unresolved": "foreign-citation-unresolved",
    "bookmark-dependency-mismatch": "foreign-citation-mismatched",
    "resolves-in-misused": "pin-link-misused",
    "dependency-unreachable": "pin-unreachable",
    "dependency-edition-mismatch": "pin-checkout-differs",
    "dependency-name-mismatch": "pin-name-differs",
    "bookmark-target-missing": "foreign-citation-missing",
    "dependency-pin-behind": "pin-behind",
    "dependency-held": "held",
    "declaration-authored": "declaration-engine-written",
    "project-renamed": "renamed",
    "citizens-rehomed": "rehomed",
    "move-unverified": "cannot-judge-without-base",
    "move-kernel-name": "kernel-name-not-yours",
    "move-source-missing": "nothing-by-that-name",
    "move-target-held": "name-already-held",
    "rehome-not-a-kind": "not-a-kind",
    "rehome-citizen-missing": "citizen-not-under-source",
    "moves-file-unreadable": "declaration-unreadable",
    "move-failed": "move-failed",
    "citizen-label-undeclared": "unknown-kind",
    "derived-edges-leaving": "connections-lost",
    "taxonomy-cycle": "kind-of-itself",
    "artifact-edge-misused": "artifact-link-misused",
    "location-kind-unknown": "location-kind-unknown",
    "depicts-target-missing": "depicted-thing-missing",
    "location-incomplete": "location-incomplete",
    "location-shared": "location-shared",
    "file-location-unreadable": "unreadable-file",
    "artifact-fingerprint-mismatch": "cited-bytes-differ",
    "artifact-primary-location": "primary-location",
    "artifact-grade-unknown": "grade-unknown",
    "artifact-grade-parked": "grade-not-yet-built",
    "artifact-grade-unearned": "grade-unearned",
    "artifact-superseded-at-invalid": "superseded-at-invalid",
    "interpretation-intent-missing": "intent-missing",
    "interpretation-about": "interprets-one-artifact",
    "draws-on-undepicted": "draws-on-undepicted",
    "resolver-incomplete": "resolver-incomplete",
    "resolver-kind-unknown": "resolver-kind-unknown",
    "resolver-opens-with": "resolver-opens-with",
    "location-verified": "held",
    "location-stale": "cited-bytes-differ",
    "location-unreadable": "unreadable-file",
    "location-unverified": "not-yet-verified",
    "location-unverifiable": "unverifiable-by-design",
    "merge-contested": "changed-on-both-lines",
    "merge-round-replayed": "taken-up",
    "merge-round-skipped": "nothing-to-take-up",
    "merge-round-unreplayable": "could-not-take-up",
    "branch-pocket": "pocket",
    "branch-line": "working-line",
    "branch-adopted": "adopted",
    "branch-unreadable": "unreadable-backup",
    "receipt-issued": "identity-recorded",
    "receipt-unreadable": "unreadable-file",
    "fingerprint-mismatch": "cited-bytes-differ",
    "fingerprint-file-unreadable": "unreadable-file",
    "receipt-verified": "evidence-found",
    "receipt-source-gone": "evidence-source-gone",
    "receipt-unverifiable": "evidence-by-ruling",
    # the Finding fleet (validation / extraction / derivation): the
    # category is the code unless a site earned a finer one
    "dangling-ref": "unknown-reference",
    "enum-violation": "value-not-allowed",
    "duplicate-key": "duplicate-name",
    "empty-key": "missing-name",
    "unparsed-cell": "kept-as-written",
    "type-conversion": "wrong-value-type",
    "catalog-violation": "catalog-mismatch",
    "overlay": "overlay-problem",
    "ontology": "declaration-problem",
    "unmapped-csv": "unreferenced-file",
    "procedure": "procedure-problem",
    "roster": "missing-entry",
    "unresolved-term": "unknown-term",
    "answer-key": "program-table-drift",
    "derive-error": "cannot-rebuild",
    # the parity judge's verdicts and the round-trip findings' kinds
    "matched": "kept",
    "omitted-approved": "left-out-by-ruling",
    "omitted-unapproved": "left-out",
    "omitted": "left-out",
    "distorted": "changed-meaning",
    "invented": "never-said",
    "cell-loss": "value-lost",
    "additive-cells": "value-added",
    "invented-row": "row-never-said",
    "missing-carried": "carried-text-missing",
    "unreadable-source": "unreadable-file",
    # the succession checklist's gate codes (the durable-checklist work)
    "canon-backup-unreadable": "unreadable-backup",
    "branch-backup-unreadable": "unreadable-backup",
    "canon-database-drift": "moved-outside-the-path",
    "branch-database-drift": "moved-outside-the-path",
    "canon-database-unreadable": "unreadable-line",
    "branch-database-unreadable": "unreadable-line",
    "canon-chain-broken": "broken-history",
    "branch-chain-broken": "broken-history",
    "rederivation-error": "derivation-error",
    "line-facts-unclean": "facts-unresolved",
    "anchor-missing": "anchor-missing",
    "ceremony-guard": "cannot-begin",
    # canonize refusal records (the durable-refusal work)
    "branch-isolation": "wrong-line",
    "backup-unreadable": "unreadable-backup",
    "kernel-skew": "kernel-behind",
    "workspace-identity": "wrong-working-copy",
    "scratch-unreadable": "unreadable-working-copy",
    "ground-facts-lint": "facts-unresolved",
    "approval-missing": "no-approval",
    "proposal-tampered": "tampered-after-approval",
    "base-moved": "base-moved",
    "scratch-drift": "drifted-after-approval",
    "database-unreadable": "unreadable-line",
    "database-drift": "moved-outside-the-path",
    "precondition-failed": "precondition-failed",
    "derive-error": "derivation-error",
    "anchor-unstampable": "anchor-unstampable",
    "database-held-elsewhere": "name-held-elsewhere",
    "write-failed": "write-failed",
    "roundtrip-fault": "readback-mismatch",
    # ceremony items
    "kb-named": "name-declared",
    "new-concept": "new-concept",
    "new-label": "new-catalog",
    "doc-edit": "description-edit",
    "alias-added": "spelling-added",
    # answer keys (the fidelity net between a program and its table)
    "answer-key-held": "held",
    "answer-key-invalid": "check-declaration-invalid",
    "answer-key-unreadable": "check-declaration-unreadable",
    "answer-key-procedure-missing": "checked-program-missing",
    "log-head-diverged": "history-out-of-step",
    "canon-log-head-diverged": "history-out-of-step",
    "branch-log-head-diverged": "history-out-of-step",
    "source-unregistered": "program-files-released",
    "source-unregistration-refused": "program-files-still-needed",
    "render-mapping-edited": "table-layout-edited",
    "render-mapping-unreadable": "table-layout-unreadable",
    "render-mapping-invalid": "table-layout-invalid",
    "removed-concept": "removed-concept",
}


def ref_key(code):
    """The designer-facing reference number for a verdict code — falls
    back to the code itself so a ref always exists."""
    return REF_KEYS.get(code, code)


# -- the record shape's shared plumbing ------------------------------------
#
# Every durable record a command leaves beside graph/reports/ (canonize's
# refusal, succession's checklist, the health checks) opens the same
# way — kind, the line of truth (kb + branch, per the reference rules) —
# and is written the same way: canonical JSON, best-effort, because a
# record that cannot be written must never mask the outcome it describes.

def record_header(base_dir, kind, branch=None):
    from .refs import kb_name_from_export
    doc = {"kind": kind, "kb": kb_name_from_export(base_dir)}
    if branch:
        doc["branch"] = branch
    return doc


def record_path(base_dir, filename):
    from pathlib import Path
    return Path(base_dir) / "graph" / "reports" / filename


def write_record(base_dir, filename, doc):
    """Write one record under graph/reports/. Returns the text written,
    or None when the write failed (best-effort by doctrine)."""
    try:
        path = record_path(base_dir, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, ensure_ascii=False, indent=2,
                          sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8")
        return text
    except OSError:
        return None


def clear_record(base_dir, filename):
    """A clean run retires an outcome-only artifact — the report
    reflects the latest outcome, never a stale one."""
    try:
        record_path(base_dir, filename).unlink(missing_ok=True)
    except OSError:
        pass


@dataclass
class Verdict:
    """One lint result: something the round may not do (refusal) or
    should hear about (advisory)."""
    code: str
    message: str
    severity: str = REFUSAL
    remedy: str = ""
    subject: "CitizenRef | ConnectionRef | None" = None
    data: dict = field(default_factory=dict)

    def __str__(self):
        return self.message

    def row(self, kb=None, branch=None):
        doc: dict = {"code": self.code, "severity": self.severity,
                     "ref": ref_key(self.code),
                     "message": self.message}
        if self.remedy:
            doc["remedy"] = self.remedy
        if self.subject is not None:
            doc["subject"] = self.subject.row(kb=kb, branch=branch)
        if self.data:
            doc["data"] = dict(self.data)
        return doc


@dataclass
class CeremonyItem:
    """One permitted schema change, itemized for the gate — approval of
    the round carrying these IS the ceremony ruling."""
    code: str
    message: str
    subject: "CitizenRef | ConnectionRef | None" = None
    data: dict = field(default_factory=dict)

    def __str__(self):
        return self.message

    def row(self, kb=None, branch=None):
        doc: dict = {"code": self.code,
                     "ref": ref_key(self.code),
                     "message": self.message}
        if self.subject is not None:
            doc["subject"] = self.subject.row(kb=kb, branch=branch)
        if self.data:
            doc["data"] = dict(self.data)
        return doc


@dataclass
class DeltaReport:
    """The delta gate's report model: the changeset plus everything the
    gate says about it. Both renderers read only this."""
    delta: "Delta"
    verdicts: list = field(default_factory=list)    # Verdict (refusals)
    ceremony: list = field(default_factory=list)    # CeremonyItem
    advisories: list = field(default_factory=list)  # Verdict (advisory)


def _advisories_tail(report):
    """The advisories sections, appended after the report body (they
    render for empty and non-empty changesets alike). Roster gaps keep
    their own explanatory frame; every other advisory kind renders
    under a neutral for-the-record section."""
    if not report.advisories:
        return ""
    roster = [a for a in report.advisories
              if getattr(a, "code", "unclassified") in ("roster-gap",
                                                        "unclassified")]
    other = [a for a in report.advisories if a not in roster]
    tail = ""
    if roster:
        tail += (
            "\n## Advisories — the branch's roster, for the record\n\n"
            "These registered program files have no citizen on this "
            "branch yet. A branch mid-rebuild is incomplete by design, "
            "so these do not block its rounds — the roster check "
            "returns to full strength when the branch stands for "
            "succession.\n\n"
            + "".join(f"- {advisory}\n" for advisory in roster))
    if other:
        tail += (
            "\n## Advisories — for the record\n\n"
            "Nothing below blocks this round; each item is something "
            "the owner should hear while already looking.\n\n"
            + "".join(f"- {advisory}\n" for advisory in other))
    return tail


def render_markdown(report):
    """The prose the approver reads — every line born from the model.
    Lint verdicts first; when the round carries schema-stratum changes
    within the ceremony's classes, they get their own marked section —
    the owner's approval of a round whose report carries that section IS
    the schema ceremony."""
    delta = report.delta
    lines = ["# Delta report — scratch vs source-derived base", ""]
    if delta.empty:
        # An empty changeset still renders its refusals and the
        # advisories tail below — a round can refuse without proposing
        # anything (a program body out of sync never enters the delta),
        # and both renderings of the report must say so, not just the
        # JSON. Roster gaps likewise reach the approver's surface even
        # when scratch matches the base exactly.
        lines += ["Scratch matches the base exactly — no proposal present.",
                  ""]
        if report.verdicts:
            lines += ["## Ground-facts lint", "",
                      "The items below cannot become canon as written — "
                      "each says why, and what to do instead. Nothing "
                      "canonizes until they are resolved.", ""]
            lines += [f"- ⚠ {verdict}" for verdict in report.verdicts] + [""]
        return "\n".join(lines) + _advisories_tail(report)
    lines += [f"**Summary:** {len(delta.nodes_added)} nodes added · "
              f"{len(delta.nodes_changed)} changed · "
              f"{len(delta.nodes_removed)} removed · "
              f"{len(delta.edges_added)} edges added · "
              f"{len(delta.edges_changed)} changed · "
              f"{len(delta.edges_removed)} removed"
              + (f" · {len(delta.stitch)} stitched"
                 if delta.stitch else "")
              + (f" · {len(delta.attribution)} attribution links recorded"
                 if delta.attribution else ""), ""]
    lines += ["## Ground-facts lint", ""]
    if report.verdicts:
        lines += ["The items below cannot become canon as written — each "
                  "says why, and what to do instead. Nothing canonizes "
                  "until they are resolved.", ""]
        lines += [f"- ⚠ {verdict}" for verdict in report.verdicts] + [""]
    else:
        lines += ["Clean — every addition is a ground fact.", ""]
    if report.ceremony:
        lines += ["## Schema changes — the ceremony", "",
                  "The rows below change the graph's OWN SCHEMA. They "
                  "are within the ceremony's permitted classes (new "
                  "declared concepts, label births, doc edits, added "
                  "aliases, render-mapping edits, source unregistration, "
                  "taxonomy declarations, unreferenced removals, "
                  "declared moves — renames and re-homings); "
                  "approving this round is the ceremony ruling that "
                  "makes them schema.", ""]
        lines += [f"- ⚑ {item}" for item in report.ceremony] + [""]
    if delta.nodes_added:
        lines += ["## Nodes added", ""]
        for label, name, props in delta.nodes_added:
            detail = ", ".join(f"{k}: {v!r}" for k, v in sorted(props.items()))
            lines.append(f"- ({label}) **{name}**"
                         + (f" — {detail}" if detail else ""))
        lines.append("")
    if delta.nodes_changed:
        lines += ["## Nodes changed (before → after)", ""]
        for label, name, changes in delta.nodes_changed:
            edits = "; ".join(f"{prop}: {b!r} → {a!r}"
                              for prop, (b, a) in sorted(changes.items()))
            lines.append(f"- ({label}) **{name}** — {edits}")
        lines.append("")
    if delta.nodes_removed:
        lines += ["## Nodes removed (with what they held)", ""]
        for label, name, props in delta.nodes_removed:
            detail = ", ".join(f"{k}: {v!r}" for k, v in sorted(props.items()))
            lines.append(f"- ({label}) **{name}**"
                         + (f" — held {detail}" if detail else ""))
        lines.append("")
    if delta.edges_added:
        lines += ["## Edges added", ""]
        for e in delta.edges_added:
            props = ", ".join(f"{k}: {v!r}" for k, v in e.props)
            lines.append(f"- ({e.from_name})-[:{e.type}"
                         + (f" {{{props}}}" if props else "")
                         + f"]->({e.to_name})")
        lines.append("")
    if delta.edges_changed:
        lines += ["## Edges changed (before → after)", ""]
        for e, changes in delta.edges_changed:
            edits = "; ".join(f"{prop}: {b!r} → {a!r}"
                              for prop, (b, a) in sorted(changes.items()))
            lines.append(f"- ({e.from_name})-[:{e.type}]->({e.to_name}) "
                         f"— {edits}")
        lines.append("")
    if delta.edges_removed:
        lines += ["## Edges removed", ""]
        lines += [f"- ({e.from_name})-[:{e.type}]->({e.to_name})"
                  for e in delta.edges_removed] + [""]
    if delta.stitch:
        lines += ["## Stitch — lands after re-derivation", "",
                  "These connections point at citizens born by this "
                  "round's schema edit, so they cannot exist in scratch "
                  "yet. They ride this same approval and land in the "
                  "same apply — verified in memory after re-derivation "
                  "births their endpoints, before anything is written.",
                  ""]
        for e in delta.stitch:
            props = ", ".join(f"{k}: {v!r}" for k, v in e.props)
            lines.append(f"- ({e.from_name})-[:{e.type}"
                         + (f" {{{props}}}" if props else "")
                         + f"]->({e.to_name})")
        lines.append("")
    if delta.attribution:
        lines += ["## Recorded attribution — each claim's home, on the "
                  "record", "",
                  "Approving this round records these claim→citizen "
                  "links as provenance: the census will audit the "
                  "record instead of guessing from words. Each line is "
                  "a claim, where it lives in its source, and the "
                  "citizens it attests.", ""]
        for row in delta.attribution:
            homes = ", ".join(f"({label}) {name}"
                              for label, name in row.get("citizens", []))
            lines.append(f"- \"{row.get('claim', '')}\" "
                         f"[{row.get('source', '')} @ "
                         f"{row.get('locator', '')}] → {homes}")
        lines.append("")
    return "\n".join(lines) + _advisories_tail(report)


def render_json(report, proposal_id=None, kb=None, branch=None):
    """The same report as machine-readable rows: summary counts, verdict
    and ceremony records, advisories. The changeset's own rows live in
    the proposal document (delta.json) — this report references it by id
    rather than repeating it. Not part of the frozen artifacts: the
    report is a rendering, re-derivable from the pinned changeset and
    base. ``kb``/``branch`` name the line of truth being reported on;
    every subject row carries them (per-row addressing, the CitizenRef
    ruling)."""
    delta = report.delta
    doc: dict = {"kind": "delta-report"}
    if delta.empty:
        doc["empty"] = True
    else:
        summary = {"nodes_added": len(delta.nodes_added),
                   "nodes_changed": len(delta.nodes_changed),
                   "nodes_removed": len(delta.nodes_removed),
                   "edges_added": len(delta.edges_added),
                   "edges_changed": len(delta.edges_changed),
                   "edges_removed": len(delta.edges_removed)}
        if delta.stitch:
            summary["stitched"] = len(delta.stitch)
        if delta.attribution:
            summary["attribution_recorded"] = len(delta.attribution)
        doc["summary"] = summary
    if proposal_id:
        doc["proposal_id"] = proposal_id
    if kb:
        doc["kb"] = kb
    if branch:
        doc["branch"] = branch
    if report.verdicts:
        doc["verdicts"] = [v.row(kb=kb, branch=branch)
                           for v in report.verdicts]
    if report.ceremony:
        doc["ceremony"] = [i.row(kb=kb, branch=branch)
                           for i in report.ceremony]
    if report.advisories:
        doc["advisories"] = [v.row(kb=kb, branch=branch)
                             for v in report.advisories]
    return json.dumps(doc, ensure_ascii=False, sort_keys=True,
                      indent=2) + "\n"
