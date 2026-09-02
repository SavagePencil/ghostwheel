"""The delta: scratch database minus source-derived base.

The agentic era's reviewable changeset (design: graph/design/agentic-etl.md
— "the proposal is a graph"). An agent authors ground facts in the scratch
database; this module reads scratch back, diffs it against the base derived
from the sources, lints the additions against the machine layers (derived
edges and labels are never authored by anyone), and renders the itemized
report the approver reviews.

Pure logic (diff/lint/report) is driver-free and unit-tested; only
read_graph touches the neo4j driver.
"""

import json
from dataclasses import dataclass, field

from . import report as report_mod
from .extract import GraphData, make_edge
from .ontology import (ARCHETYPE_LABEL, MACHINE_LABELS, MEMBERSHIP_EDGE_TYPE,
                       SCHEMA_EDGE_TYPES, SCHEMA_LABELS, STRATIFIED_EDGE_TYPES,
                       UNAUTHORABLE_EDGE_TYPES, UNAUTHORABLE_LABELS,
                       is_concept_archetype, is_derived_edge)
from .refs import KB_NAME_PROP, CitizenRef, ONTOLOGY_ANCHOR, connection_ref
from .report import CeremonyItem, Verdict


def _is_schema_edge(edge):
    """Is this connection part of the graph's own schema stratum (the schema inversion)?
    The schema edge types always; the stratified types only when they
    run FROM an Archetype (a concept tower / concept ladder) — a
    stratified edge from a citizen is its re-derived machine shadow, not
    schema. This split decides which refusal message a frozen row gets."""
    return (edge.type in SCHEMA_EDGE_TYPES
            or (edge.type in STRATIFIED_EDGE_TYPES
                and edge.from_label == ARCHETYPE_LABEL))


@dataclass
class Delta:
    nodes_added: list = field(default_factory=list)    # (label, name, props)
    nodes_removed: list = field(default_factory=list)  # (label, name, props before-image)
    nodes_changed: list = field(default_factory=list)  # (label, name, {prop: (before, after)})
    edges_added: list = field(default_factory=list)    # Edge
    edges_removed: list = field(default_factory=list)  # Edge (props are the before-image)
    edges_changed: list = field(default_factory=list)  # (Edge after, {prop: (before, after)})
    stitch: list = field(default_factory=list)         # Edge — lands after re-derivation (the stitch mechanism)

    @property
    def empty(self):
        return not (self.nodes_added or self.nodes_removed
                    or self.nodes_changed or self.edges_added
                    or self.edges_removed or self.edges_changed
                    or self.stitch)


def read_graph(config):
    """Read a database back into GraphData shape (nodes keyed by
    (label, name), Edge list). Nodes without a name property are keyed by
    None and surface in the lint — agents must name what they create."""
    from neo4j import GraphDatabase  # deferred: only DB access needs it

    graph = GraphData()
    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    with driver, driver.session(database=config["NEO4J_DATABASE"]) as session:
        for record in session.run(
                "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"):
            props = dict(record["props"])
            name = props.pop("name", None)
            label = (record["labels"] or ["(unlabeled)"])[0]
            graph.ensure_node(label, name, **props)
        for record in session.run(
                "MATCH (a)-[r]->(b) RETURN labels(a)[0] AS fl, a.name AS fn, "
                "type(r) AS t, properties(r) AS props, "
                "labels(b)[0] AS tl, b.name AS tn"):
            graph.edges.append(make_edge(
                record["t"], record["fl"], record["fn"],
                record["tl"], record["tn"], dict(record["props"])))
    from .workspace import strip as strip_workspace
    return strip_workspace(graph)


def diff(base, scratch):
    """Itemized changeset: what scratch holds that base does not, and vice
    versa. A property edit on an edge is paired into edges_changed (one
    entry, before → after per property) when the pairing is unambiguous —
    exactly one removed and one added edge between the same endpoints with
    the same type; genuinely parallel edges stay as adds/removes. Removals
    carry their full property before-image: the undo record."""
    delta = Delta()
    # Machine-label nodes (Step/Outcome) never itemize as changes or
    # removals: when a rederive moves canon's machine layer mid-round, a
    # scratch cut earlier holds the STALE machine nodes, and the drift
    # would ride the changeset toward a guaranteed apply refusal — the
    # applier works on the machine-stripped ground layer, where those
    # nodes do not exist to verify. Re-derivation owns them at apply.
    # Schema-label nodes (the Archetype stratum) are GROUND since the
    # inversion and DO itemize as changes and removals — the
    # freeze must refuse an authored schema mutation by name, never
    # swallow it into a green apply. Authored machine-label ADDITIONS
    # still itemize so the lint can refuse them.
    machine = (lambda key: key[0] in MACHINE_LABELS)
    for key in sorted(scratch.nodes.keys() - base.nodes.keys(),
                      key=lambda k: (k[0], str(k[1]))):
        delta.nodes_added.append((key[0], key[1], dict(scratch.nodes[key])))
    for key in sorted(base.nodes.keys() - scratch.nodes.keys(),
                      key=lambda k: (k[0], str(k[1]))):
        if machine(key):
            continue
        delta.nodes_removed.append((key[0], key[1], dict(base.nodes[key])))
    for key in sorted(scratch.nodes.keys() & base.nodes.keys(),
                      key=lambda k: (k[0], str(k[1]))):
        if machine(key):
            continue
        before, after = base.nodes[key], scratch.nodes[key]
        changes = {prop: (before.get(prop), after.get(prop))
                   for prop in sorted(set(before) | set(after))
                   if before.get(prop) != after.get(prop)}
        if changes:
            delta.nodes_changed.append((key[0], key[1], changes))
    base_edges, scratch_edges = set(base.edges), set(scratch.edges)
    edge_key = (lambda e: (e.type, e.from_label, str(e.from_name),
                           e.to_label, str(e.to_name), e.props))
    added = sorted(scratch_edges - base_edges, key=edge_key)
    removed = sorted(base_edges - scratch_edges, key=edge_key)
    identity = (lambda e: (e.type, e.from_label, str(e.from_name),
                           e.to_label, str(e.to_name)))
    added_by, removed_by = {}, {}
    for e in added:
        added_by.setdefault(identity(e), []).append(e)
    for e in removed:
        removed_by.setdefault(identity(e), []).append(e)
    paired = set()
    for ident in sorted(added_by.keys() & removed_by.keys()):
        if len(added_by[ident]) != 1 or len(removed_by[ident]) != 1:
            continue  # parallel edges — pairing would be a guess
        before, after = removed_by[ident][0], added_by[ident][0]
        bp, ap = dict(before.props), dict(after.props)
        changes = {prop: (bp.get(prop), ap.get(prop))
                   for prop in sorted(set(bp) | set(ap))
                   if bp.get(prop) != ap.get(prop)}
        delta.edges_changed.append((after, changes))
        paired.update({before, after})
    delta.edges_added = [e for e in added if e not in paired]
    # Machine-derived edges never itemize as bare removals: they are
    # shadows of ground-fact changes (a deleted node takes its INSTANCE_OF
    # with it), and the applier works on the machine-stripped ground layer
    # where they cannot verify — re-derivation owns them at apply. Schema
    # edges (the stratum from an Archetype) are GROUND since the
    # inversion and DO itemize as removals, so the freeze can
    # refuse a schema deletion by name instead of silently discarding
    # it. Authored derived-edge additions and paired modifications still
    # itemize so the lint can refuse them.
    delta.edges_removed = [e for e in removed
                           if e not in paired and not is_derived_edge(e)]
    return delta


# The schema ceremony: property classes an owner-gated round may touch on
# a schema row. Everything else on the schema stratum stays out of class.
CEREMONY_DOC_PROPS = frozenset({"doc"})

_OUT_OF_CLASS = (
    "this schema change is outside the ceremony's classes (new declared "
    "concepts, label births, doc edits, added aliases, removal of "
    "unreferenced rows) — changes to an EXISTING label or spec move data "
    "underneath them and ride the migration charter. "
    "Propose the change to the owner at the plan gate instead.")


def _alias_additions(before, after):
    """The added-alias diff of a spec_json change, or None when the change
    is anything else. Returns the {alias: target} of the NEW alias entries
    when before and after parse as JSON objects differing ONLY by
    additions under ``aliases`` — every existing alias untouched, every
    other spec field identical. Anything else (a removed or retargeted
    alias, any other spec difference, spec_json appearing or vanishing,
    unparseable JSON) returns None and stays out of class."""
    if not isinstance(before, str) or not isinstance(after, str):
        return None
    try:
        b, a = json.loads(before), json.loads(after)
    except ValueError:
        return None
    if not isinstance(b, dict) or not isinstance(a, dict):
        return None
    b_aliases = b.pop("aliases", None) or {}
    a_aliases = a.pop("aliases", None) or {}
    if b != a:
        return None
    if any(alias not in a_aliases or a_aliases[alias] != target
           for alias, target in b_aliases.items()):
        return None
    added = {alias: target for alias, target in a_aliases.items()
             if alias not in b_aliases}
    return added or None


def _alias_target_exists(row_name, target, delta, base):
    """Does the target citizen exist under the row's label — in the base,
    or born by this same round?"""
    if base is not None and (row_name, target) in base.nodes:
        return True
    return any(label == row_name and name == target
               for label, name, _ in delta.nodes_added)


def ceremony_records(delta, base=None):
    """Split the delta's schema-stratum changes into the ceremony's
    permitted classes and out-of-class violations — as records.

    Permitted, itemized for the diff gate (the owner's approval of the
    round IS the ceremony ruling):
    - a new CONCEPT row: an Archetype without spec_json, arriving WITH its
      DECLARED_IN edge (and optionally INSTANCE_OF into a parent concept);
    - a LABEL BIRTH: a new Archetype WITH spec_json, arriving WITH its
      DECLARED_IN edge, when the base holds no ground rows under that
      label — nothing moves underneath, so the migration charter's
      rationale does not bite (changes to an existing label still refuse
      toward the charter; base=None refuses births outright, like
      removals, since emptiness-underneath can't be verified);
    - a DOC EDIT: a schema row change touching only CEREMONY_DOC_PROPS;
    - an ADDED ALIAS: a spec_json change whose parsed before/after differ
      only by new entries under aliases — each new surface spelling reads
      as a citizen of that label that exists in the base or is born by
      the same round;
    - an UNREFERENCED REMOVAL: a concept row with no spec_json and, in the
      base, no inbound edges (no members, no anchors) and no outbound
      edges beyond its own declaration — verified against the base, so
      base=None refuses removals outright.

    Returns (items, violations, permitted_node_keys, permitted_edge_ids):
    items are CeremonyItem records for the report's ceremony section,
    violations are Verdict records; the permitted sets tell
    lint_verdicts() which schema rows to skip its freeze refusals for.
    """
    items, violations = [], []
    permitted_nodes, permitted_edges = set(), set()

    added_concepts = {}
    added_labels = {}
    for label, name, props in delta.nodes_added:
        if label not in SCHEMA_LABELS:
            continue
        if "spec_json" in (props or {}):
            ground_rows = [] if base is None else sorted(
                str(row_name) for (row_label, row_name) in base.nodes
                if row_label == name)
            if base is None:
                violations.append(Verdict(
                    code="schema-label-row-authored",
                    subject=CitizenRef(label, name),
                    message=(
                        f"Attempted to birth '{name}' as a new {label} "
                        "LABEL with no base graph to verify against. "
                        "Failed due to: a label birth is permitted only "
                        "when the base holds no ground rows under that "
                        "label, which cannot be checked without the base."),
                    remedy="Re-run with the base graph available."))
            elif ground_rows:
                shown = ", ".join(ground_rows[:5]) \
                    + ("…" if len(ground_rows) > 5 else "")
                violations.append(Verdict(
                    code="schema-label-row-authored",
                    subject=CitizenRef(label, name),
                    message=(
                        f"Attempted to birth '{name}' as a new {label} "
                        f"LABEL, but the base already holds "
                        f"{len(ground_rows)} ground row"
                        f"{'s' if len(ground_rows) != 1 else ''} under "
                        f"that label ({shown}). Failed due to: "
                        + _OUT_OF_CLASS),
                    remedy="Propose the change to the owner at the plan "
                           "gate instead."))
            else:
                added_labels[(label, name)] = props or {}
        else:
            added_concepts[(label, name)] = props or {}
    declared = {}
    for edge in delta.edges_added:
        if edge.type == "DECLARED_IN" \
                and (edge.from_label, edge.from_name) in (
                    added_concepts.keys() | added_labels.keys()):
            declared[(edge.from_label, edge.from_name)] = edge.to_name
    for key, props in added_labels.items():
        label, name = key
        if key not in declared:
            violations.append(Verdict(
                code="schema-label-undeclared",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to birth '{name}' as a new {label} LABEL "
                    "without declaring it. Failed due to: a born label "
                    "arrives WITH its DECLARED_IN edge in the same round "
                    "— an undeclared schema row would be invisible to the "
                    "schema readers. Add the declaration in scratch, or "
                    "delete the node."),
                remedy="Add the declaration in scratch, or delete the "
                       "node."))
            continue
        try:
            spec = json.loads(props.get("spec_json") or "{}")
            bindings = [str(c) for c in
                        (spec.get("concept") or [])] \
                if isinstance(spec.get("concept"), list) \
                else ([str(spec["concept"])] if spec.get("concept") else [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            violations.append(Verdict(
                code="schema-label-spec-unreadable",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to birth '{name}' as a new {label} LABEL, "
                    "but its spec_json does not parse as a mapping. "
                    "Failed due to: the born label's embedded spec is "
                    "what the schema readers reconstruct from — it must "
                    "be valid JSON. Fix the spec_json in scratch."),
                remedy="Fix the spec_json in scratch."))
            continue
        permitted_nodes.add(key)
        parents = [e.to_name for e in delta.edges_added
                   if e.type == "INSTANCE_OF"
                   and (e.from_label, e.from_name) == key]
        doc = str(props.get("doc", ""))
        item_data = {"declared_in": declared[key]}
        if bindings:
            item_data["concept"] = bindings
        if parents:
            item_data["instance_of"] = [str(p) for p in parents]
        if doc:
            item_data["doc"] = doc
        items.append(CeremonyItem(
            code="new-label",
            subject=CitizenRef(label, name),
            message=(
                f"NEW LABEL '{name}' (born empty) — declared in "
                f"{declared[key]}"
                + (f", binding concept {', '.join(bindings)}"
                   if bindings else "")
                + (f", an instance of {', '.join(map(str, parents))}"
                   if parents else "")
                + (f'; doc: "{doc[:160]}{"…" if len(doc) > 160 else ""}"'
                   if doc else "; no doc text")),
            data=item_data))
        for edge in delta.edges_added:
            if (edge.from_label, edge.from_name) == key \
                    and edge.type in ("DECLARED_IN", "INSTANCE_OF"):
                permitted_edges.add(id(edge))
    for key, props in added_concepts.items():
        label, name = key
        if key not in declared:
            violations.append(Verdict(
                code="schema-concept-undeclared",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to author '{name}' as a new {label} concept "
                    "without declaring it. Failed due to: a ceremony concept "
                    "arrives WITH its DECLARED_IN edge (and usually an "
                    "INSTANCE_OF into its parent concept) in the same round "
                    "— an undeclared schema row would be invisible to the "
                    "schema readers. Add the declaration in scratch, or "
                    "delete the node."),
                remedy="Add the declaration in scratch, or delete the node."))
            continue
        permitted_nodes.add(key)
        parents = [e.to_name for e in delta.edges_added
                   if e.type == "INSTANCE_OF"
                   and (e.from_label, e.from_name) == key]
        doc = str(props.get("doc", ""))
        item_data = {"declared_in": declared[key]}
        if parents:
            item_data["instance_of"] = [str(p) for p in parents]
        if doc:
            item_data["doc"] = doc
        items.append(CeremonyItem(
            code="new-concept",
            subject=CitizenRef(label, name),
            message=(
                f"NEW CONCEPT '{name}' — declared in {declared[key]}"
                + (f", an instance of {', '.join(map(str, parents))}"
                   if parents else "")
                + (f'; doc: "{doc[:160]}{"…" if len(doc) > 160 else ""}"'
                   if doc else "; no doc text")),
            data=item_data))
        for edge in delta.edges_added:
            if (edge.from_label, edge.from_name) == key \
                    and edge.type in ("DECLARED_IN", "INSTANCE_OF"):
                permitted_edges.add(id(edge))

    for label, name, changes in delta.nodes_changed:
        if label not in SCHEMA_LABELS:
            continue
        alias_added = _alias_additions(*changes["spec_json"]) \
            if "spec_json" in changes else None
        # KB-name adoption: the one non-doc property edit the ceremony
        # admits, on exactly the Ontology anchor — a knowledge base
        # declaring (or changing) its own name through a gated round.
        # Blanking the name is not in the class: identity may change
        # hands at a gate, never quietly vanish.
        kb_named = ((label, name) == (ARCHETYPE_LABEL, ONTOLOGY_ANCHOR)
                    and bool(changes.get(KB_NAME_PROP, ("", ""))[1]))
        permitted_props = CEREMONY_DOC_PROPS \
            | ({"spec_json"} if alias_added else set()) \
            | ({KB_NAME_PROP} if kb_named else set())
        out_of_class = sorted(set(changes) - permitted_props)
        if out_of_class:
            violations.append(Verdict(
                code="schema-edit-out-of-class",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to modify '{name}' ({label}) beyond its doc "
                    f"text ({', '.join(out_of_class)}). Failed due to: "
                    + _OUT_OF_CLASS),
                remedy="Propose the change to the owner at the plan gate "
                       "instead.",
                data={"properties": out_of_class}))
            continue
        if alias_added:
            missing = {}
            for alias, target in sorted(alias_added.items()):
                targets = target if isinstance(target, list) else [target]
                absent = [t for t in targets
                          if not _alias_target_exists(name, t, delta, base)]
                if absent:
                    missing[alias] = absent
            if missing:
                for alias, absent in sorted(missing.items()):
                    violations.append(Verdict(
                        code="alias-target-missing",
                        subject=CitizenRef(label, name),
                        message=(
                            f"Attempted to add the alias '{alias}' on "
                            f"'{name}' ({label}). Failed due to: no "
                            + ", ".join(f"'{t}'" for t in absent)
                            + f" citizen exists under '{name}' in the base "
                            "or this round — an alias must read as a "
                            "citizen that exists. Add the citizen in the "
                            "same round, or fix the target."),
                        remedy="Add the target citizen in the same round, "
                               "or fix the alias's target.",
                        data={"alias": alias, "missing": absent}))
                continue
        permitted_nodes.add((label, name))
        for prop, (before, after) in changes.items():
            if prop == "spec_json" and alias_added:
                continue
            if kb_named and prop == KB_NAME_PROP:
                was = f"'{before}'" if before else "unnamed until now"
                items.append(CeremonyItem(
                    code="kb-named",
                    subject=CitizenRef(label, name),
                    message=(f"KB NAMED — this knowledge base declares "
                             f"its name: '{after}' (was {was})"),
                    data={"property": prop, "before": before,
                          "after": after}))
                continue
            b = "(none)" if before is None else f'"{str(before)[:110]}…"' \
                if len(str(before)) > 110 else f'"{before}"'
            a = "(none)" if after is None else f'"{str(after)[:110]}…"' \
                if len(str(after)) > 110 else f'"{after}"'
            items.append(CeremonyItem(
                code="doc-edit",
                subject=CitizenRef(label, name),
                message=f"DOC EDIT on '{name}' — {prop}: {b} → {a}",
                data={"property": prop, "before": before, "after": after}))
        for alias, target in sorted((alias_added or {}).items()):
            reads_as = (", ".join(f"'{t}'" for t in target)
                        if isinstance(target, list) else f"'{target}'")
            plural = "s" if isinstance(target, list) and len(target) > 1 \
                else ""
            items.append(CeremonyItem(
                code="alias-added",
                subject=CitizenRef(label, name),
                message=(f"ALIAS ADDED on '{name}' — '{alias}' reads as "
                         f"the {reads_as} citizen{plural}"),
                data={"alias": alias, "target": target}))

    for label, name, props in delta.nodes_removed:
        if label not in SCHEMA_LABELS:
            continue
        key = (label, name)
        if "spec_json" in (props or {}):
            violations.append(Verdict(
                code="schema-label-row-removed",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to remove '{name}' ({label}), a LABEL row "
                    f"(it carries spec_json). Failed due to: {_OUT_OF_CLASS}"),
                remedy="Propose the change to the owner at the plan gate "
                       "instead."))
            continue
        if base is None:
            violations.append(Verdict(
                code="schema-removal-unverified",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to remove '{name}' ({label}) without the "
                    "base graph in view. Failed due to: a schema removal is "
                    "permitted only when nothing references the row, and "
                    "that can only be verified against the base — run the "
                    "removal through the delta pipeline."),
                remedy="Run the removal through the delta pipeline."))
            continue
        inbound = [e for e in base.edges
                   if (e.to_label, str(e.to_name)) == (label, str(name))]
        stray = [e for e in base.edges
                 if (e.from_label, str(e.from_name)) == (label, str(name))
                 and e.type not in ("DECLARED_IN", "INSTANCE_OF")]
        if inbound or stray:
            kinds = sorted({e.type for e in inbound + stray})
            violations.append(Verdict(
                code="schema-row-referenced",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to remove '{name}' ({label}). Failed due "
                    f"to: the row is still referenced in the base "
                    f"({len(inbound) + len(stray)} connections: "
                    f"{', '.join(kinds)}) — a referenced schema row cannot "
                    "be ceremonially removed; re-point or retire its "
                    "references first, or propose a migration."),
                remedy="Re-point or retire its references first, or "
                       "propose a migration.",
                data={"connections": len(inbound) + len(stray),
                      "kinds": kinds}))
            continue
        permitted_nodes.add(key)
        items.append(CeremonyItem(
            code="removed-concept",
            subject=CitizenRef(label, name),
            message=(f"REMOVED CONCEPT '{name}' — unreferenced in the "
                     "base (no members, no anchors); its declaration "
                     "goes with it")))
        for edge in delta.edges_removed:
            if (edge.from_label, edge.from_name) == key \
                    and edge.type in ("DECLARED_IN", "INSTANCE_OF"):
                permitted_edges.add(id(edge))

    return items, violations, permitted_nodes, permitted_edges


def ceremony_classify(delta, base=None):
    """The ceremony's verdicts as prose lines — a rendering of
    ceremony_records() for callers that read sentences. The records are
    the truth; these are their str() forms."""
    items, violations, permitted_nodes, permitted_edges = \
        ceremony_records(delta, base)
    return ([str(item) for item in items],
            [str(verdict) for verdict in violations],
            permitted_nodes, permitted_edges)


def _changes_data(changes):
    """A changed edge's per-property (before, after) pairs, as verdict
    particulars."""
    return {"changes": {prop: [before, after]
                        for prop, (before, after) in sorted(changes.items())}}


def lint_verdicts(delta, base=None):
    """Ground-facts violations as Verdict records: machine labels or
    derived edge types among the ADDITIONS (the machine's own base-side
    layers are fine — the lint guards what the author wrote, not what the
    derivation computed). Schema-stratum changes route through
    ceremony_records: the permitted classes itemize for the gate instead
    of refusing; everything else on the stratum still refuses by name."""
    (_, violations, ceremony_nodes,
     ceremony_edges) = ceremony_records(delta, base)
    for label, name, _ in delta.nodes_added:
        if label in SCHEMA_LABELS:
            # Schema adds are fully adjudicated by ceremony_records:
            # permitted concepts itemize, everything else already refused.
            pass
        elif label in UNAUTHORABLE_LABELS:
            violations.append(Verdict(
                code="machine-label-authored",
                subject=CitizenRef(label, name),
                message=(
                    f"'{name}' can't be created as a {label} — nodes of that "
                    "kind are built automatically by the system, never by "
                    "hand (machine label). If you meant to propose a new "
                    "concept or step, say so in the plan and the owner "
                    "will place it. To undo: delete the node from scratch, "
                    "or reset scratch entirely (python -m graph load "
                    "--database scratch)."),
                remedy="Delete the node from scratch, or reset scratch "
                       "entirely (python -m graph load --database "
                       "scratch)."))
        if name is None:
            violations.append(Verdict(
                code="node-unnamed",
                subject=CitizenRef(label, None),
                message=(
                    f"a {label} node was created without a name — every "
                    "citizen needs one. Give it a name property or delete it "
                    "from scratch."),
                remedy="Give it a name property or delete it from scratch."))
    # Schema node edits and removals are fully adjudicated by
    # ceremony_records above — permitted classes itemize for the gate,
    # everything else is already refused by name. Schema EDGES outside a
    # permitted concept's own declaration still refuse here.
    for edge in delta.edges_removed:
        if _is_schema_edge(edge) and id(edge) not in ceremony_edges:
            violations.append(Verdict(
                code="schema-edge-removed",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to remove the connection ({edge.from_name})-"
                    f"[:{edge.type}]->({edge.to_name}). Failed due to: "
                    f"{edge.type} links are part of the graph's own schema, "
                    f"and {_OUT_OF_CLASS} To undo: reset scratch entirely "
                    "(python -m graph load --database scratch)."),
                remedy="Reset scratch entirely (python -m graph load "
                       "--database scratch)."))
    for edge in delta.edges_added:
        if _is_schema_edge(edge):
            if id(edge) in ceremony_edges:
                continue
            violations.append(Verdict(
                code="schema-edge-authored",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to author the connection ({edge.from_name})-"
                    f"[:{edge.type}]->({edge.to_name}). Failed due to: "
                    f"{edge.type} links are part of the graph's own schema, "
                    f"and {_OUT_OF_CLASS} To undo: MATCH the "
                    "relationship in scratch and DELETE it, or reset "
                    "scratch."),
                remedy="MATCH the relationship in scratch and DELETE it, "
                       "or reset scratch."))
        elif edge.type in UNAUTHORABLE_EDGE_TYPES or edge.type.startswith("ASSIGNS_"):
            violations.append(Verdict(
                code="derived-edge-authored",
                subject=connection_ref(edge),
                message=(
                    f"the connection ({edge.from_name}) → ({edge.to_name}) "
                    f"can't be added by hand — {edge.type} links are computed "
                    "automatically from the facts, so a manual one would go "
                    "stale the moment the facts change (derived type "
                    f"{edge.type}). If the intent is 'these two should be "
                    "related', that's an owner question — raise it at the "
                    "plan gate. To undo: MATCH the relationship in scratch "
                    "and DELETE it, or reset scratch."),
                remedy="MATCH the relationship in scratch and DELETE it, "
                       "or reset scratch."))
        elif edge.type == MEMBERSHIP_EDGE_TYPE:
            # The declared-membership pattern: an authored ground edge, not
            # schema (_is_schema_edge does not match it) and not derived —
            # so it falls through to here, where its SHAPE is guarded.
            # Collate every fault on the edge.
            prefix = (f"Attempted to author membership ({edge.from_name})-"
                      f"[:{MEMBERSHIP_EDGE_TYPE}]->({edge.to_name}). Failed "
                      "due to: ")
            if edge.from_label == ARCHETYPE_LABEL:
                violations.append(Verdict(
                    code="membership-from-archetype",
                    subject=connection_ref(edge),
                    message=(
                        prefix + "the edge runs FROM an Archetype, which is "
                        "the tower/roster shape, not an authored membership "
                        "— a declared membership is written FROM a citizen. "
                        "To undo: point the edge from the citizen, or MATCH "
                        "it in scratch and DELETE it."),
                    remedy="Point the edge from the citizen, or MATCH it "
                           "in scratch and DELETE it."))
            if base is None:
                violations.append(Verdict(
                    code="membership-unverified",
                    subject=connection_ref(edge),
                    message=(
                        prefix + "the target cannot be verified without the "
                        "base graph — run the round through the delta "
                        "pipeline (python -m graph delta) so the membership "
                        "target is checked against canon."),
                    remedy="Run the round through the delta pipeline "
                           "(python -m graph delta)."))
            elif not is_concept_archetype(base, edge.to_name):
                violations.append(Verdict(
                    code="membership-target-not-concept",
                    subject=connection_ref(edge),
                    message=(
                        prefix + f"'{edge.to_name}' is not an existing "
                        "Concept-rooted Archetype — authored membership "
                        "classifies a citizen against subject-matter "
                        "Concepts only (never a Facet, a label's Archetype, "
                        "or a missing node), and it never re-homes the "
                        "citizen. To undo: point the edge at a Concept "
                        "Archetype, or DELETE it from scratch."),
                    remedy="Point the edge at a Concept Archetype, or "
                           "DELETE it from scratch."))
            basis = dict(edge.props).get("basis")
            if not (basis and str(basis).strip()):
                violations.append(Verdict(
                    code="membership-basis-missing",
                    subject=connection_ref(edge),
                    message=(
                        prefix + "the edge carries no `basis` rationale — a "
                        "declared membership is a hand assertion with no "
                        "source table behind it, so its reason is the audit "
                        "record and is required. To undo: add a `basis` "
                        "property naming why the citizen belongs, or DELETE "
                        "the edge from scratch."),
                    remedy="Add a `basis` property naming why the citizen "
                           "belongs, or DELETE the edge from scratch."))
        if edge.from_name is None or edge.to_name is None:
            violations.append(Verdict(
                code="edge-endpoint-unnamed",
                subject=connection_ref(edge),
                message=(
                    f"a {edge.type} connection touches an unnamed node — "
                    "name the node or remove the connection."),
                remedy="Name the node or remove the connection."))
    for edge, changes in delta.edges_changed:
        if _is_schema_edge(edge):
            violations.append(Verdict(
                code="schema-edge-modified",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to modify the connection ({edge.from_name})-"
                    f"[:{edge.type}]->({edge.to_name}). Failed due to: "
                    f"{edge.type} links are part of the graph's own schema, "
                    f"and {_OUT_OF_CLASS} To undo: restore the "
                    "relationship's properties in scratch, or reset "
                    "scratch."),
                remedy="Restore the relationship's properties in scratch, "
                       "or reset scratch.",
                data=_changes_data(changes)))
        elif edge.type in UNAUTHORABLE_EDGE_TYPES or edge.type.startswith("ASSIGNS_"):
            violations.append(Verdict(
                code="derived-edge-modified",
                subject=connection_ref(edge),
                message=(
                    f"the connection ({edge.from_name}) → ({edge.to_name}) "
                    f"can't be modified by hand — {edge.type} links are "
                    "computed automatically from the facts (derived type "
                    f"{edge.type}). If the underlying fact is wrong, change "
                    "the fact; the link follows. To undo: restore the "
                    "relationship's properties in scratch, or reset "
                    "scratch."),
                remedy="Restore the relationship's properties in scratch, "
                       "or reset scratch.",
                data=_changes_data(changes)))
        elif edge.type == MEMBERSHIP_EDGE_TYPE:
            # An edit must not strip the audit record the add-side lint
            # required: the basis survives every edit.
            basis = dict(edge.props).get("basis")
            if not (basis and str(basis).strip()):
                violations.append(Verdict(
                    code="membership-basis-blanked",
                    subject=connection_ref(edge),
                    message=(
                        f"Attempted to edit the membership ({edge.from_name})-"
                        f"[:{MEMBERSHIP_EDGE_TYPE}]->({edge.to_name}). Failed "
                        "due to: the edit leaves it with no `basis` rationale "
                        "— a declared membership's reason is the audit record "
                        "and is required. To undo: restore or rewrite the "
                        "`basis` property in scratch."),
                    remedy="Restore or rewrite the `basis` property in "
                           "scratch.",
                    data=_changes_data(changes)))
    return violations


def lint(delta, base=None):
    """The lint's verdicts as prose lines — a rendering of
    lint_verdicts() for callers that read sentences. The records are the
    truth; these are their str() forms."""
    return [str(verdict) for verdict in lint_verdicts(delta, base)]


def stitch_verdicts(delta, scratch):
    """The stitch mechanism: the stitch carries ground edges whose endpoint is born by
    this round's schema edit — they cannot be authored in scratch (the
    endpoint does not exist there to point at), so they ride the
    proposal in the stitch file and land at apply, after re-derivation
    births their endpoints. This lint holds the door narrow: a stitch
    edge must genuinely need the stitch."""
    violations = []
    for edge in delta.stitch:
        if _is_schema_edge(edge):
            violations.append(Verdict(
                code="stitch-schema-edge",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to author the stitch connection "
                    f"({edge.from_name})-[:{edge.type}]->({edge.to_name}). "
                    f"Failed due to: {edge.type} links are part of the "
                    "graph's own schema, and the stitch never carries "
                    "schema — a ceremony concept authors its declaration "
                    "directly in scratch, in the same round. "
                    "Remove it from the stitch file."),
                remedy="Remove it from the stitch file."))
            continue
        if edge.type in UNAUTHORABLE_EDGE_TYPES or edge.type.startswith("ASSIGNS_"):
            violations.append(Verdict(
                code="stitch-derived-edge",
                subject=connection_ref(edge),
                message=(
                    f"the stitch connection ({edge.from_name}) → "
                    f"({edge.to_name}) can't be authored — {edge.type} links "
                    "are computed automatically from the facts (derived type "
                    f"{edge.type}); the stitch carries ground facts only. "
                    "Remove it from the stitch file."),
                remedy="Remove it from the stitch file."))
            continue
        if edge.from_name is None or edge.to_name is None:
            violations.append(Verdict(
                code="stitch-endpoint-unnamed",
                subject=connection_ref(edge),
                message=(
                    f"a stitch {edge.type} connection touches an unnamed "
                    "node — name both endpoints in the stitch file."),
                remedy="Name both endpoints in the stitch file."))
            continue
        if (edge.from_label, edge.from_name) in scratch.nodes and \
                (edge.to_label, edge.to_name) in scratch.nodes:
            violations.append(Verdict(
                code="stitch-unneeded",
                subject=connection_ref(edge),
                message=(
                    f"the stitch connection ({edge.from_name})-"
                    f"[:{edge.type}]->({edge.to_name}) doesn't need the "
                    "stitch — both ends already exist in scratch. Author it "
                    "there like any other ground fact and it will ride the "
                    "main changeset."),
                remedy="Author it in scratch like any other ground fact."))
    return violations


def lint_stitch(delta, scratch):
    """The stitch lint's verdicts as prose lines — a rendering of
    stitch_verdicts(). The records are the truth; these are their str()
    forms."""
    return [str(verdict) for verdict in stitch_verdicts(delta, scratch)]


def build_report(delta, verdicts=None, ceremony=None, advisories=None):
    """The delta gate's report model. Accepts records or plain strings
    (strings are wrapped as unclassified records, so long-standing
    callers keep working); both renderers in graph.report read only the
    model this returns."""
    def as_verdict(v, severity=report_mod.REFUSAL):
        if isinstance(v, Verdict):
            return v
        return Verdict(code="unclassified", message=str(v),
                       severity=severity)

    def as_item(item):
        if isinstance(item, CeremonyItem):
            return item
        return CeremonyItem(code="unclassified", message=str(item))

    return report_mod.DeltaReport(
        delta=delta,
        verdicts=[as_verdict(v) for v in (verdicts or [])],
        ceremony=[as_item(i) for i in (ceremony or [])],
        advisories=[as_verdict(a, report_mod.ADVISORY)
                    for a in (advisories or [])])


def render_report(delta, violations, ceremony=None):
    """Human-readable delta report (markdown) — a rendering of the
    report model over the given verdicts. Lint verdicts first; when
    the round carries schema-stratum changes within the ceremony's
    classes, they get their own marked section — the owner's approval of
    a round whose report carries that section IS the schema ceremony."""
    return report_mod.render_markdown(build_report(delta, violations,
                                                   ceremony))


def body_sync_verdicts(scratch, base_dir):
    """Program-body carriage: every node carrying an approved program (body + source_path)
    must match its file byte-for-byte. The WHOLE scratch graph is
    scanned, not just the changeset — the classic failure is editing the
    file and forgetting the paste, which leaves the node out of the
    delta entirely."""
    violations = []
    for (label, name), props in sorted(
            scratch.nodes.items(), key=lambda item: str(item[0])):
        source_path = (props or {}).get("source_path")
        body = (props or {}).get("body")
        if not source_path or body is None:
            continue
        path = base_dir / source_path
        try:
            file_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(Verdict(
                code="body-file-unreadable",
                subject=CitizenRef(label, name),
                message=(
                    f"'{name}' cites {source_path} as its approved program, "
                    f"but the file is not readable ({exc}) — restore the "
                    "file or fix the node's source_path."),
                remedy="Restore the file or fix the node's source_path.",
                data={"source_path": source_path}))
            continue
        if file_text != body:
            violations.append(Verdict(
                code="body-out-of-sync",
                subject=CitizenRef(label, name),
                message=(
                    f"'{name}' carries a program body out of sync with "
                    f"{source_path}. The approved file is the truth — run "
                    "python -m graph delta --sync-bodies to update the "
                    "graph copy from the file."),
                remedy="Run python -m graph delta --sync-bodies to update "
                       "the graph copy from the file.",
                data={"source_path": source_path}))
    return violations


def body_sync_violations(scratch, base_dir):
    """The body-sync verdicts as prose lines — a rendering of
    body_sync_verdicts(). The records are the truth; these are their
    str() forms."""
    return [str(verdict) for verdict in body_sync_verdicts(scratch, base_dir)]


def sync_bodies(config, base_dir):
    """Program-body carriage: write each program-carrying node's body from its approved
    file — the file is the truth; the paste-and-hash ritual retires.
    Returns (synced node names, problem messages)."""
    from neo4j import GraphDatabase  # deferred: only DB access needs it

    synced, problems = [], []
    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    with driver, driver.session(database=config["NEO4J_DATABASE"]) as session:
        rows = session.run(
            "MATCH (n) WHERE n.source_path IS NOT NULL "
            "AND n.body IS NOT NULL "
            "RETURN labels(n)[0] AS label, n.name AS name, "
            "n.source_path AS source_path, n.body AS body").data()
        for row in rows:
            path = base_dir / row["source_path"]
            try:
                file_text = path.read_text(encoding="utf-8")
            except OSError as exc:
                problems.append(
                    f"'{row['name']}': {row['source_path']} is not "
                    f"readable ({exc})")
                continue
            if file_text == row["body"]:
                continue
            session.run(
                "MATCH (n {name: $name}) WHERE labels(n)[0] = $label "
                "AND n.source_path = $source_path SET n.body = $body",
                name=row["name"], label=row["label"],
                source_path=row["source_path"], body=file_text)
            synced.append(row["name"])
    return synced, problems
