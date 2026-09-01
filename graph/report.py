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
  optional fields omitted when empty. Citizens are referenced as
  ``{"label": …, "name": …}`` objects; connections nest one on each end.
"""

import json
from dataclasses import dataclass, field

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
    # ceremony items
    "new-concept": "new-concept",
    "new-label": "new-catalog",
    "doc-edit": "description-edit",
    "alias-added": "spelling-added",
    "removed-concept": "removed-concept",
}


def ref_key(code):
    """The designer-facing reference number for a verdict code — falls
    back to the code itself so a ref always exists."""
    return REF_KEYS.get(code, code)


@dataclass(frozen=True)
class NodeRef:
    """A citizen, by its graph identity. ``name`` may be None when the
    verdict is precisely that the node has no name yet."""
    label: str
    name: object = None

    def row(self):
        return {"kind": "node", "label": self.label, "name": self.name}


@dataclass(frozen=True)
class EdgeRef:
    """A connection, by type and endpoints."""
    type: str
    source: NodeRef
    target: NodeRef

    def row(self):
        return {"kind": "edge", "type": self.type,
                "from": {"label": self.source.label,
                         "name": self.source.name},
                "to": {"label": self.target.label,
                       "name": self.target.name}}


def edge_ref(edge):
    """EdgeRef from an extract.Edge (or anything edge-shaped)."""
    return EdgeRef(edge.type,
                   NodeRef(edge.from_label, edge.from_name),
                   NodeRef(edge.to_label, edge.to_name))


@dataclass
class Verdict:
    """One lint result: something the round may not do (refusal) or
    should hear about (advisory)."""
    code: str
    message: str
    severity: str = REFUSAL
    remedy: str = ""
    subject: "NodeRef | EdgeRef | None" = None
    data: dict = field(default_factory=dict)

    def __str__(self):
        return self.message

    def row(self):
        doc: dict = {"code": self.code, "severity": self.severity,
                     "ref": ref_key(self.code),
                     "message": self.message}
        if self.remedy:
            doc["remedy"] = self.remedy
        if self.subject is not None:
            doc["subject"] = self.subject.row()
        if self.data:
            doc["data"] = dict(self.data)
        return doc


@dataclass
class CeremonyItem:
    """One permitted schema change, itemized for the gate — approval of
    the round carrying these IS the ceremony ruling."""
    code: str
    message: str
    subject: "NodeRef | None" = None
    data: dict = field(default_factory=dict)

    def __str__(self):
        return self.message

    def row(self):
        doc: dict = {"code": self.code,
                     "ref": ref_key(self.code),
                     "message": self.message}
        if self.subject is not None:
            doc["subject"] = self.subject.row()
        if self.data:
            doc["data"] = dict(self.data)
        return doc


@dataclass
class DeltaReport:
    """The delta gate's report model: the changeset plus everything the
    gate says about it. Both renderers read only this."""
    delta: object                     # delta.Delta
    verdicts: list = field(default_factory=list)    # Verdict (refusals)
    ceremony: list = field(default_factory=list)    # CeremonyItem
    advisories: list = field(default_factory=list)  # Verdict (advisory)


def _advisories_tail(report):
    """The advisories section, appended after the report body (it renders
    for empty and non-empty changesets alike)."""
    if not report.advisories:
        return ""
    return (
        "\n## Advisories — the branch's roster, for the record\n\n"
        "These registered program files have no citizen on this "
        "branch yet. A branch mid-rebuild is incomplete by design, "
        "so these do not block its rounds — the roster check "
        "returns to full strength when the branch stands for "
        "succession.\n\n"
        + "".join(f"- {advisory}\n" for advisory in report.advisories))


def render_markdown(report):
    """The prose the approver reads — every line born from the model.
    Lint verdicts first; when the round carries schema-stratum changes
    within the ceremony's classes, they get their own marked section —
    the owner's approval of a round whose report carries that section IS
    the schema ceremony."""
    delta = report.delta
    lines = ["# Delta report — scratch vs source-derived base", ""]
    if delta.empty:
        # An empty changeset still renders the advisories tail below —
        # on a branch, roster gaps must reach the approver's surface
        # even when scratch matches the base exactly.
        lines += ["Scratch matches the base exactly — no proposal present.",
                  ""]
        return "\n".join(lines) + _advisories_tail(report)
    lines += [f"**Summary:** {len(delta.nodes_added)} nodes added · "
              f"{len(delta.nodes_changed)} changed · "
              f"{len(delta.nodes_removed)} removed · "
              f"{len(delta.edges_added)} edges added · "
              f"{len(delta.edges_changed)} changed · "
              f"{len(delta.edges_removed)} removed"
              + (f" · {len(delta.stitch)} stitched"
                 if delta.stitch else ""), ""]
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
                  "aliases, unreferenced removals); "
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
    return "\n".join(lines) + _advisories_tail(report)


def render_json(report, proposal_id=None):
    """The same report as machine-readable rows: summary counts, verdict
    and ceremony records, advisories. The changeset's own rows live in
    the proposal document (delta.json) — this report references it by id
    rather than repeating it. Not part of the frozen artifacts: the
    report is a rendering, re-derivable from the pinned changeset and
    base."""
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
        doc["summary"] = summary
    if proposal_id:
        doc["proposal_id"] = proposal_id
    if report.verdicts:
        doc["verdicts"] = [v.row() for v in report.verdicts]
    if report.ceremony:
        doc["ceremony"] = [i.row() for i in report.ceremony]
    if report.advisories:
        doc["advisories"] = [v.row() for v in report.advisories]
    return json.dumps(doc, ensure_ascii=False, sort_keys=True,
                      indent=2) + "\n"
