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
from .ontology import (ARCHETYPE_LABEL, CONFERS_PROP, DECLARATION_LABELS,
                       DECLINES_EDGE_TYPE, MACHINE_LABELS,
                       MEMBERSHIP_EDGE_TYPE,
                       RENDERED_VIEWS_PROP, SCHEMA_EDGE_TYPES, SCHEMA_LABELS,
                       STRATIFIED_EDGE_TYPES, UNAUTHORABLE_EDGE_TYPES,
                       UNAUTHORABLE_LABELS, Reader, conferred_ancestors,
                       declined_map, is_concept_archetype,
                       is_derived_edge, node_reader, rendered_views_problems)
from .refs import KB_NAME_PROP, CitizenRef, ONTOLOGY_ANCHOR, connection_ref
from .report import CeremonyItem, Verdict


def _confers_view(delta, base):
    """The taxonomy's conferral marks as this round leaves them: base
    links, links born this round, and changed links at their post-round
    properties. kind -> the parents whose links confer."""
    states = {}

    def note(edge):
        if edge.type == "SUBTYPE_OF" \
                and edge.from_label == ARCHETYPE_LABEL \
                and edge.to_label == ARCHETYPE_LABEL:
            states[(str(edge.from_name), str(edge.to_name))] = \
                bool(dict(edge.props).get(CONFERS_PROP))
    for edge in list(base.edges) + list(delta.edges_added):
        note(edge)
    for edge, _changes in delta.edges_changed:
        note(edge)
    marked = {}
    for (kind, parent), confers in states.items():
        if confers:
            marked.setdefault(kind, set()).add(parent)
    return marked


def _conferring_members(delta, base, marked, parent):
    """The citizens whose declared membership reaches `parent` through
    confers-marked taxonomy links (base plus this round), each member's
    own declines honored."""
    declined = declined_map(list(base.edges) + list(delta.edges_added))
    members = []
    for edge in list(base.edges) + list(delta.edges_added):
        if edge.type != MEMBERSHIP_EDGE_TYPE:
            continue
        declines = declined.get((edge.from_label, str(edge.from_name)),
                                set())
        if parent in conferred_ancestors(str(edge.to_name), marked,
                                         declines):
            members.append((edge.from_label, str(edge.from_name)))
    return members


def _decline_verdicts(edge, delta, base):
    """One DECLINES_CONFERRAL connection's shape, collated: it runs
    from a citizen, answers a conferral that actually reaches that
    citizen through some membership's marked links, and carries its
    own required `basis` — symmetric with the membership it answers."""
    prefix = (f"Attempted to author the decline ({edge.from_name})-"
              f"[:{DECLINES_EDGE_TYPE}]->({edge.to_name}). Failed "
              "due to: ")
    verdicts = []
    if edge.from_label == ARCHETYPE_LABEL:
        verdicts.append(Verdict(
            code="membership-decline-unknown",
            subject=connection_ref(edge),
            message=(prefix + "the connection runs FROM a concept — a "
                     "decline is a member's own answer, written from "
                     "the citizen. Point it from the citizen, or "
                     "DELETE it from scratch."),
            remedy="Point it from the citizen, or DELETE it from "
                   "scratch."))
        return verdicts
    basis = dict(edge.props).get("basis")
    if not (basis and str(basis).strip()):
        verdicts.append(Verdict(
            code="decline-basis-missing",
            subject=connection_ref(edge),
            message=(prefix + "the connection carries no `basis` "
                     "rationale — a decline is a hand assertion like "
                     "the membership it answers, so its reason is the "
                     "audit record and is required. Add a `basis` "
                     "naming why this member is the exception, or "
                     "DELETE the connection from scratch."),
            remedy="Add a `basis` naming why this member is the "
                   "exception, or DELETE the connection from scratch."))
    if base is not None:
        marked = _confers_view(delta, base)
        member = (edge.from_label, str(edge.from_name))
        reachable = set()
        for held in list(base.edges) + list(delta.edges_added):
            if held.type == MEMBERSHIP_EDGE_TYPE \
                    and (held.from_label, str(held.from_name)) == member:
                reachable |= set(conferred_ancestors(str(held.to_name),
                                                     marked))
        if str(edge.to_name) not in reachable:
            verdicts.append(Verdict(
                code="membership-decline-unknown",
                subject=connection_ref(edge),
                message=(
                    prefix + f"no membership of ({edge.from_name}) "
                    f"confers ({edge.to_name}) — a decline answers a "
                    "conferral that exists. Remove the connection, or "
                    "declare conferral on the kind's taxonomy link."),
                remedy="Remove the connection, or declare conferral "
                       "on the kind's taxonomy link."))
    return verdicts


def membership_advisories(delta, base):
    """The intent question, asked aloud: a new membership in a kind
    whose taxonomy link does NOT confer a parent leaves that parent
    unanswered — the member does not become one unless the author says
    so. One advisory per unanswered direct parent link; a declined
    parent is already answered."""
    if base is None:
        return []
    marked = _confers_view(delta, base)
    parents = {}
    for edge in list(base.edges) + list(delta.edges_added):
        if edge.type == "SUBTYPE_OF" \
                and edge.from_label == ARCHETYPE_LABEL \
                and edge.to_label == ARCHETYPE_LABEL:
            parents.setdefault(str(edge.from_name), set()).add(
                str(edge.to_name))
    declined = declined_map(list(base.edges) + list(delta.edges_added))
    advisories = []
    for edge in delta.edges_added:
        if edge.type != MEMBERSHIP_EDGE_TYPE:
            continue
        kind = str(edge.to_name)
        declines = declined.get((edge.from_label, str(edge.from_name)),
                                set())
        conferred = set(conferred_ancestors(kind, marked, declines))
        for parent in sorted(parents.get(kind, ())):
            if parent in conferred or parent in declines:
                continue
            advisories.append(Verdict(
                code="membership-intent-open",
                severity=report_mod.ADVISORY,
                subject=connection_ref(edge),
                message=(
                    f"({kind}) is a kind of ({parent}), and membership "
                    f"does not confer it — ({edge.from_name}) does not "
                    f"become an instance of ({parent}) unless you say "
                    "so. If this member is one, declare it directly on "
                    "the citizen; to make it every member's default, "
                    "declare conferral on the kind's taxonomy link."),
                remedy="Declare it directly on the citizen, or declare "
                       "conferral on the kind's taxonomy link.",
                data={"member": str(edge.from_name), "kind": kind,
                      "parent": parent}))
    return advisories


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
    attribution: list = field(default_factory=list)    # claim→citizen link rows (recorded provenance)
    moves: dict = field(default_factory=dict)          # declared renames / re-homings (moves.json)
    merge_moves: list = field(default_factory=list)    # a merge round's replayed moves, per source round in order
    migration: dict = field(default_factory=dict)      # a migration round's record summary (id, direction, counterpart)

    @property
    def empty(self):
        # a links-only round is a real proposal: recording provenance
        # for already-authored citizens changes no ground but is a
        # ruling all the same — and so are a moves-only round and a
        # merge of moves-only rounds
        return not (self.nodes_added or self.nodes_removed
                    or self.nodes_changed or self.edges_added
                    or self.edges_removed or self.edges_changed
                    or self.stitch or self.attribution or self.moves
                    or self.merge_moves or self.migration)


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
    # A line's own declaration rows (a pocket's who-cut-it and who-may-
    # look) are the engine's to write, never scratch's to edit: an edit
    # or removal there never itemizes — the invite verbs are the way —
    # while an authored ADDITION still itemizes so the lint refuses it.
    machine = (lambda key: key[0] in MACHINE_LABELS
               or key[0] in DECLARATION_LABELS)
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
# The render-mapping class: a label row's render mappings (the view
# list beside its spec) may be added, changed, or removed by a gated
# round — the loader and deriver never read the prop, so nothing moves
# underneath. The value is linted for shape at the gate.
CEREMONY_RENDER_PROPS = frozenset({RENDERED_VIEWS_PROP})

_OUT_OF_CLASS = (
    "this schema change is outside the ceremony's classes (new declared "
    "concepts, label births, doc edits, added aliases, render-mapping "
    "edits, source unregistration, removal of unreferenced rows, and the "
    "declared moves — a rename of the world's own label or a re-homing "
    "of citizens under a kind, filed in moves.json) — "
    "any other change to an EXISTING label "
    "or spec moves data underneath it and rides the migration charter. "
    "Propose the change to the owner at the plan gate instead.")


def _render_mapping_verdict(label, name, value, spec_json):
    """The refusal a render-mapping value earns, or None when it is
    well-formed (or absent — a removal). The value must parse as a JSON
    list of view mappings; the label's own embedded spec (spec_json)
    supplies the row-source rule, and a row that carries no spec at all
    is not a label and cannot render through a view."""
    if value is None:
        return None
    if not isinstance(spec_json, str):
        return Verdict(
            code="render-mapping-invalid",
            subject=CitizenRef(label, name),
            message=(
                f"Attempted to set the render mappings on '{name}' "
                f"({label}). Failed due to: the row is not a label (it "
                "carries no spec), and a render mapping belongs on the "
                "label whose table it lays out. Move the mapping to the "
                "label's row, or delete it from scratch."),
            remedy="Move the mapping to the label's row, or delete it "
                   "from scratch.")
    try:
        views = json.loads(value)
        spec = json.loads(spec_json)
    except (ValueError, TypeError):
        return Verdict(
            code="render-mapping-unreadable",
            subject=CitizenRef(label, name),
            message=(
                f"Attempted to set the render mappings on '{name}' "
                f"({label}). Failed due to: the value does not parse as "
                "JSON — the mappings are what the table renderer and the "
                "parity judge read, and they must be a JSON list of view "
                "mappings. Fix the value in scratch."),
            remedy="Fix the value in scratch: a JSON list of view mappings.")
    problems = rendered_views_problems(
        views, spec if isinstance(spec, dict) else None)
    if not problems:
        return None
    return Verdict(
        code="render-mapping-invalid",
        subject=CitizenRef(label, name),
        message=(
            f"Attempted to set the render mappings on '{name}' ({label}). "
            "Failed due to: " + "; ".join(problems) + ". Fix the mapping "
            "in scratch — each view names its source table and key, uses "
            "only the known view keys, and sits on a label without a row "
            "source."),
        remedy="Fix the mapping in scratch.",
        data={"problems": problems})


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


def _source_unregistration(before, after):
    """True when a spec_json change does exactly one thing: drops the
    `source` registration of a program label (reader procedure_yaml),
    leaving the reader explicit so the lift still knows the label — the
    files released, the bodies the citizens carry now the only copy.
    Anything else stays out of class."""
    if not isinstance(before, str) or not isinstance(after, str):
        return False
    try:
        b, a = json.loads(before), json.loads(after)
    except ValueError:
        return False
    if not isinstance(b, dict) or not isinstance(a, dict):
        return False
    if "source" not in b or "source" in a:
        return False
    if node_reader(b) != Reader.PROCEDURE_YAML:
        return False
    released = {key: value for key, value in b.items() if key != "source"}
    return released == a and node_reader(a) == Reader.PROCEDURE_YAML


def _source_release(before, after):
    """True when a spec_json change does exactly one thing: the source
    registration leaves — the node-level `source`, `source` keys inside
    relationship entries, or both — with the reader unchanged (an
    extension-inferred reader survives only by being declared explicitly
    in the same edit; a release never silently changes how bodies read).
    The program-label case (reader procedure_yaml) stays with its own
    class and its body checks. Anything else stays out of class."""
    if not isinstance(before, str) or not isinstance(after, str):
        return False
    try:
        b, a = json.loads(before), json.loads(after)
    except ValueError:
        return False
    if not isinstance(b, dict) or not isinstance(a, dict):
        return False
    if node_reader(b) == Reader.PROCEDURE_YAML:
        return False  # the program-release class owns that road
    # only a derive-meaningful reader must survive the release: a
    # markdown label's containment and mentions derive from its reader,
    # so losing an extension-inferred one would silently change canon;
    # a rows-era reader drives nothing post-closure and may lapse
    if node_reader(b) == Reader.MARKDOWN_SECTIONS \
            and node_reader(a) != Reader.MARKDOWN_SECTIONS:
        return False
    stripped = {key: value for key, value in b.items() if key != "source"}
    rels = stripped.get("relationships")
    if isinstance(rels, list):
        stripped = dict(stripped)
        stripped["relationships"] = [
            ({k: v for k, v in rel.items() if k != "source"}
             if isinstance(rel, dict) else rel)
            for rel in rels]
    reader_declared = dict(stripped)
    if "reader" not in reader_declared and a.get("reader"):
        reader_declared["reader"] = a["reader"]
    return a in (stripped, reader_declared) and a != b


def _released_sources(before):
    """The registrations a release drops, named for the gate."""
    spec = json.loads(before)
    files = spec.get("source")
    files = [] if files is None else (
        [files] if isinstance(files, str) else list(files))
    for rel in spec.get("relationships") or []:
        if isinstance(rel, dict) and rel.get("source"):
            files.append(rel["source"])
    return files


def _citizens_still_needing_files(label_name, delta, base):
    """The citizens under a program label that could NOT live without
    its files after this round: those left without a carried body, or
    still citing a file (source_path). Each is named with its reason;
    the round's own edits and removals are applied before judging."""
    removed = {(label, name) for label, name, _ in delta.nodes_removed}
    changed = {(label, name): changes
               for label, name, changes in delta.nodes_changed}
    after = {}
    if base is not None:
        for (label, name), props in base.nodes.items():
            if label != label_name or (label, name) in removed:
                continue
            props = dict(props or {})
            for prop, (_was, now) in changed.get((label, name), {}).items():
                if now is None:
                    props.pop(prop, None)
                else:
                    props[prop] = now
            after[name] = props
    for label, name, props in delta.nodes_added:
        if label == label_name:
            after[name] = dict(props or {})
    problems = []
    for name, props in sorted(after.items(), key=str):
        if not props.get("body"):
            problems.append(f"'{name}' carries no program body")
        if props.get("source_path"):
            problems.append(f"'{name}' still cites {props['source_path']}")
    return problems


def _alias_target_exists(row_name, target, delta, base):
    """Does the target citizen exist under the row's label — in the
    base, born by this same round, or born under its NEW name by the
    round's own citizen renames? A renamed citizen is born under its
    new name just the same: the graph the round produces holds it (the
    rehome precedent, applied to aliases)."""
    if base is not None and (row_name, target) in base.nodes:
        return True
    if any(label == row_name and name == target
           for label, name, _ in delta.nodes_added):
        return True
    # "rename_citizens" is the moves declaration's third verb (a
    # string here to keep delta free of a moves import)
    pairs = ((delta.moves or {}).get("rename_citizens") or {}) \
        .get(row_name) or {}
    for old_name, new_name in pairs.items():
        if new_name != target:
            continue
        if (base is not None and (row_name, old_name) in base.nodes) \
                or any(label == row_name and name == old_name
                       for label, name, _ in delta.nodes_added):
            return True
    return False


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
    - a SOURCE UNREGISTRATION: a program label (reader procedure_yaml)
      drops its `source` file list and nothing else, permitted when
      every citizen under it — after this round's own edits — carries a
      program body and cites no file; the files are released, the
      bodies are the only copy, nothing moves underneath;
    - a RENDER-MAPPING EDIT: a label row's render mappings (the view
      list beside its spec, CEREMONY_RENDER_PROPS) added, changed, or
      removed — loader- and derive-inert, so nothing moves underneath;
      the value is linted for shape (a JSON list of views, each naming
      its source table, on a label without a row source);
    - an ADDED ALIAS: a spec_json change whose parsed before/after differ
      only by new entries under aliases — each new surface spelling reads
      as a citizen of that label that exists in the base or is born by
      the same round;
    - an UNREFERENCED REMOVAL: a concept row with no spec_json and, in the
      base, no inbound edges (no members, no anchors) and no outbound
      edges beyond its own declaration — verified against the base, so
      base=None refuses removals outright;
    - a TAXONOMY DECLARATION: an authored SUBTYPE_OF into a concept
      Archetype whose endpoints both exist (base or this round) — the
      graph is the taxonomy's declaration, so nothing moves underneath;
      removals and missing endpoints still refuse by name.

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
        # a born label may arrive with its render mappings; they are
        # linted like any render-mapping edit
        verdict = _render_mapping_verdict(
            label, name, props.get(RENDERED_VIEWS_PROP), props.get("spec_json"))
        if verdict is not None:
            violations.append(verdict)
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
        unregistered = "spec_json" in changes and \
            _source_unregistration(*changes["spec_json"])
        released = "spec_json" in changes and not unregistered and \
            _source_release(*changes["spec_json"])
        # KB-name adoption: the one non-doc property edit the ceremony
        # admits, on exactly the Ontology anchor — a knowledge base
        # declaring (or changing) its own name through a gated round.
        # Blanking the name is not in the class: identity may change
        # hands at a gate, never quietly vanish.
        kb_named = ((label, name) == (ARCHETYPE_LABEL, ONTOLOGY_ANCHOR)
                    and bool(changes.get(KB_NAME_PROP, ("", ""))[1]))
        permitted_props = CEREMONY_DOC_PROPS | CEREMONY_RENDER_PROPS \
            | ({"spec_json"} if alias_added or unregistered
               or released else set()) \
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
        if unregistered:
            if base is None:
                violations.append(Verdict(
                    code="source-unregistration-refused",
                    subject=CitizenRef(label, name),
                    message=(
                        f"Attempted to release the program files of "
                        f"'{name}' ({label}) with no base graph to verify "
                        "against. Failed due to: releasing a label's files "
                        "is permitted only when every citizen under it "
                        "carries its own body, which cannot be checked "
                        "without the base."),
                    remedy="Re-run with the base graph available."))
                continue
            needing = _citizens_still_needing_files(name, delta, base)
            if needing:
                violations.append(Verdict(
                    code="source-unregistration-refused",
                    subject=CitizenRef(label, name),
                    message=(
                        f"Attempted to release the program files of "
                        f"'{name}' ({label}). Failed due to: "
                        + "; ".join(needing) + ". Every citizen under the "
                        "label must carry its own program body and cite "
                        "no file before the registration leaves — land "
                        "the bodies and drop source_path in this round, "
                        "or keep the files registered."),
                    remedy="Land every body and drop every source_path in "
                           "this round, or keep the files registered.",
                    data={"citizens": needing}))
                continue
        if RENDERED_VIEWS_PROP in changes:
            now = changes[RENDERED_VIEWS_PROP][1]
            # the label's live spec: the base row's, or this round's own
            # alias-carrying edit of it
            if "spec_json" in changes:
                spec_json = changes["spec_json"][1]
            elif base is not None:
                spec_json = (base.nodes.get((label, name)) or {}).get(
                    "spec_json")
            else:
                spec_json = None
            if now is not None and base is None and "spec_json" not in changes:
                violations.append(Verdict(
                    code="render-mapping-invalid",
                    subject=CitizenRef(label, name),
                    message=(
                        f"Attempted to set the render mappings on '{name}' "
                        f"({label}) with no base graph to verify against. "
                        "Failed due to: a render mapping is checked against "
                        "the label's own spec, which cannot be read without "
                        "the base."),
                    remedy="Re-run with the base graph available."))
                continue
            verdict = _render_mapping_verdict(label, name, now, spec_json)
            if verdict is not None:
                violations.append(verdict)
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
            if prop == "spec_json" and released:
                files = _released_sources(before)
                items.append(CeremonyItem(
                    code="source-released",
                    subject=CitizenRef(label, name),
                    message=(f"SOURCE RELEASED from '{name}' — "
                             f"{len(files)} registration"
                             f"{'s' if len(files) != 1 else ''} leave the "
                             "spec; no verb reads them, and the schema "
                             "keeps only what still means something"),
                    data={"property": prop, "files": files}))
                continue
            if prop == "spec_json" and unregistered:
                files = json.loads(before).get("source")
                files = [files] if isinstance(files, str) else list(files)
                items.append(CeremonyItem(
                    code="source-unregistered",
                    subject=CitizenRef(label, name),
                    message=(f"PROGRAM FILES RELEASED from '{name}' — "
                             f"{len(files)} registered file"
                             f"{'s' if len(files) != 1 else ''} leave the "
                             "spec; every citizen carries its own program "
                             "body from here on"),
                    data={"property": prop, "files": files}))
                continue
            if prop == RENDERED_VIEWS_PROP:
                was_n = len(json.loads(before)) if before else 0
                now_n = len(json.loads(after)) if after else 0
                verb = ("REMOVED" if after is None
                        else "ADDED" if before is None else "EDITED")
                items.append(CeremonyItem(
                    code="render-mapping-edited",
                    subject=CitizenRef(label, name),
                    message=(f"RENDER MAPPING {verb} on '{name}' — the "
                             f"table layout it renders through: {now_n} "
                             f"view{'s' if now_n != 1 else ''} (was "
                             f"{was_n})"),
                    data={"property": prop, "before_views": was_n,
                          "after_views": now_n}))
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

    # A TAXONOMY DECLARATION: an authored SUBTYPE_OF whose target is a
    # concept Archetype and whose endpoints both exist — in the base,
    # or born by this same round. The graph IS the taxonomy's
    # declaration (reconstruction reads these edges back into the
    # specs), so declaring one moves no data underneath: a ceremony
    # act, not a migration. A lost genuine-taxonomy link had no
    # sanctioned way home before this class — reconstruction only
    # re-emits edges that exist, and authoring refused. Removals stay
    # refused toward the migration charter; base=None refuses like the
    # other existence-checked classes (the freeze refusal stands).
    if base is not None:
        born = {(label, name) for label, name, _ in delta.nodes_added}
        for edge in delta.edges_added:
            if edge.type != "SUBTYPE_OF" or id(edge) in permitted_edges \
                    or edge.to_label != ARCHETYPE_LABEL:
                continue
            missing = [
                (lbl, name) for lbl, name in
                ((edge.from_label, edge.from_name),
                 (edge.to_label, edge.to_name))
                if (lbl, name) not in base.nodes and (lbl, name) not in born]
            if missing:
                names = ", ".join(f"({lbl}) '{name}'"
                                  for lbl, name in missing)
                violations.append(Verdict(
                    code="taxonomy-endpoint-missing",
                    subject=connection_ref(edge),
                    message=(
                        f"Attempted to declare ({edge.from_name}) a kind "
                        f"of ({edge.to_name}). Failed due to: {names} "
                        "exists neither in the base nor in this round — "
                        "a taxonomy declaration needs both of its "
                        "citizens. Author the missing citizen in this "
                        "round, or fix the name."),
                    remedy="Author the missing citizen in this round, "
                           "or fix the name."))
                # adjudicated here by name — suppress the generic freeze
                permitted_edges.add(id(edge))
                continue
            permitted_edges.add(id(edge))
            # The taxonomy is a DAG: a declaration that would make a
            # concept a kind of itself, through any chain, refuses.
            parents = {}
            for known in list(base.edges) + list(delta.edges_added):
                if known.type == "SUBTYPE_OF" \
                        and known.from_label == ARCHETYPE_LABEL \
                        and known.to_label == ARCHETYPE_LABEL:
                    parents.setdefault(known.from_name, set()).add(
                        known.to_name)
            if edge.from_label == ARCHETYPE_LABEL:
                seen, frontier = set(), [edge.to_name]
                cycle = False
                while frontier:
                    ancestor = frontier.pop()
                    if ancestor == edge.from_name:
                        cycle = True
                        break
                    if ancestor in seen:
                        continue
                    seen.add(ancestor)
                    frontier.extend(parents.get(ancestor, ()))
                if cycle:
                    violations.append(Verdict(
                        code="taxonomy-cycle",
                        subject=connection_ref(edge),
                        message=(
                            f"Attempted to declare ({edge.from_name}) a "
                            f"kind of ({edge.to_name}). Failed due to: "
                            f"({edge.to_name}) is already a kind of "
                            f"({edge.from_name}) through the taxonomy, so "
                            "the declaration would make a concept a kind "
                            "of itself — a taxonomy has no cycles. Retire "
                            "one of the links."),
                        remedy="Retire one of the taxonomy links."))
                    continue
            # The consequence report: membership folds up the taxonomy
            # at derivation, so the owner rules on what the declaration
            # DOES — how many citizens become instances of the concept.
            if edge.from_label == ARCHETYPE_LABEL:
                kinds = {edge.from_name}
                grew = True
                while grew:
                    grew = False
                    for child, ups in parents.items():
                        if child not in kinds and ups & kinds:
                            kinds.add(child)
                            grew = True
                matches = sum(1 for (lbl, _n) in list(base.nodes) + [
                    (l, n) for l, n, _ in delta.nodes_added] if lbl in kinds)
                consequence = (f"; {matches} citizen"
                               f"{'s' if matches != 1 else ''} of that kind "
                               f"become instances of ({edge.to_name}) at "
                               "derivation")
            else:
                matches = 1
                consequence = (f"; ({edge.from_name}) becomes an instance "
                               f"of ({edge.to_name}) at derivation")
            if dict(edge.props).get(CONFERS_PROP):
                # the link lands already marked: the conferral is part
                # of what the declaration does, counted the same way
                conferring = _conferring_members(
                    delta, base, _confers_view(delta, base),
                    str(edge.to_name))
                consequence += (f"; membership confers it — "
                                f"{len(conferring)} declared member"
                                f"{'' if len(conferring) == 1 else 's'} "
                                "join at derivation")
            items.append(CeremonyItem(
                code="taxonomy-declared",
                subject=connection_ref(edge),
                message=(f"TAXONOMY DECLARED — ({edge.from_name}) is a "
                         f"kind of ({edge.to_name}); the graph carries "
                         "the declaration itself, and reconstruction "
                         "reads it back" + consequence),
                data={"matches": matches, "concept": edge.to_name}))

    # The conferral ceremony: policy is canon content, spoken aloud.
    if base is not None:
        marked = _confers_view(delta, base)
        # a new membership under conferring links: announce what the
        # member becomes, and name the decline road — silence accepts a
        # DECLARED default, so the default is read out where it applies
        declined = declined_map(list(base.edges)
                                + list(delta.edges_added))
        for edge in delta.edges_added:
            if edge.type != MEMBERSHIP_EDGE_TYPE:
                continue
            declines = declined.get(
                (edge.from_label, str(edge.from_name)), set())
            for parent in conferred_ancestors(str(edge.to_name), marked,
                                              declines):
                items.append(CeremonyItem(
                    code="membership-confers",
                    subject=connection_ref(edge),
                    message=(f"MEMBERSHIP CONFERS — ({edge.from_name}) "
                             f"joins ({edge.to_name}), whose declared "
                             f"conferral carries ({parent}): the member "
                             "becomes an instance at derivation; decline "
                             "it on the membership if this member is the "
                             "exception"),
                    data={"member": str(edge.from_name),
                          "kind": str(edge.to_name), "parent": parent}))
        # the mark itself lands or lifts on an existing link: the
        # ceremony counts the citizens that actually confer, so the
        # owner rules on what the declaration really does
        for edge, changes in delta.edges_changed:
            if edge.type != "SUBTYPE_OF" \
                    or set(changes) != {CONFERS_PROP} \
                    or edge.from_label != ARCHETYPE_LABEL \
                    or edge.to_label != ARCHETYPE_LABEL:
                continue
            if bool(dict(edge.props).get(CONFERS_PROP)):
                members = _conferring_members(delta, base, marked,
                                              str(edge.to_name))
                count = len(members)
                message = (f"TAXONOMY CONFERRAL — ({edge.from_name})'s "
                           f"membership now confers ({edge.to_name}): "
                           f"{count} declared member"
                           f"{'' if count == 1 else 's'} become"
                           f"{'s' if count == 1 else ''} an instance of "
                           f"({edge.to_name}) at derivation")
            else:
                count = 0
                message = (f"TAXONOMY CONFERRAL — ({edge.from_name})'s "
                           f"membership no longer confers "
                           f"({edge.to_name}); members keep only what "
                           "they declare directly")
            items.append(CeremonyItem(
                code="taxonomy-confers", subject=connection_ref(edge),
                message=message,
                data={"matches": count, "concept": str(edge.to_name)}))

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
    declared = set()
    if base is not None:
        declared = {name for (label, name) in base.nodes
                    if label == ARCHETYPE_LABEL}
    declared |= {name for label, name, _ in delta.nodes_added
                 if label == ARCHETYPE_LABEL}
    for label, name, _ in delta.nodes_added:
        if label in SCHEMA_LABELS:
            # Schema adds are fully adjudicated by ceremony_records:
            # permitted concepts itemize, everything else already refused.
            pass
        elif label in DECLARATION_LABELS:
            violations.append(Verdict(
                code="declaration-authored",
                subject=CitizenRef(label, name),
                message=(
                    f"'{name}' can't be created as a {label} — a line's "
                    "own declaration (who cut this pocket, who may look) "
                    "is written by the engine at the cut and changed by "
                    "python -m graph branch <name> --invite/--uninvite, "
                    "never authored by hand. Delete the row from scratch."),
                remedy="Delete the row from scratch; use python -m graph "
                       "branch <name> --invite/--uninvite to change a "
                       "declaration."))
        elif base is not None and label not in declared \
                and label not in UNAUTHORABLE_LABELS:
            violations.append(Verdict(
                code="citizen-label-undeclared",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to author '{name}' under '{label}'. Failed "
                    f"due to: no schema row declares '{label}' — an unknown "
                    "label would mean no membership and silently dropped "
                    "connections, and the engine never treats a citizen as "
                    "nothing. Declare the label in this round (a label "
                    "birth at the ceremony), pick a label that exists, or "
                    "declare a move."),
                remedy="Declare the label, pick one that exists, or declare "
                       "a move."))
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
    # the row-receipt retirement: a receipt is a sentence-grain source
    # quote; a table row is presentation, and its facts belong in
    # structured properties — authoring one refuses by name, whether the
    # row arrives on a new citizen or lands on an existing one
    def _row_receipt_verdict(label, name):
        return Verdict(
            code="row-receipt-authored",
            subject=CitizenRef(label, name),
            message=(
                f"({label}) '{name}' carries a table ROW in from_text — "
                "a receipt is a sentence-grain source quote, and a row "
                "is presentation, not a sentence. Store the cell's "
                "facts as structured properties; a quoted sentence may "
                "stay in from_text."),
            remedy="Store the cell's facts as structured properties; "
                   "keep only sentence-grain quotes in from_text.")

    from .comprehension import is_row_text
    from .artifacts import DERIVED_MARKER
    for label, name, props in delta.nodes_added:
        if (props or {}).get(DERIVED_MARKER):
            violations.append(Verdict(
                code="machinery-marker-authored",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to author '{name}' ({label}) carrying "
                    f"the machinery's marker ({DERIVED_MARKER}). Failed "
                    "due to: that marker is the derivation's own "
                    "signature on the boilerplate it writes — a hand "
                    "never writes it, and a hand-authored "
                    "interpretation needs no marker to be kept. Remove "
                    "the property."),
                remedy="Remove the property from the citizen in "
                       "scratch."))
    for label, name, props in delta.nodes_added:
        receipt = (props or {}).get("from_text")
        if receipt and is_row_text(receipt):
            violations.append(_row_receipt_verdict(label, name))
    for label, name, changes in delta.nodes_changed:
        if "from_text" in changes:
            _before, after = changes["from_text"]
            if after and is_row_text(after):
                violations.append(_row_receipt_verdict(label, name))
    # Schema node edits and removals are fully adjudicated by
    # ceremony_records above — permitted classes itemize for the gate,
    # everything else is already refused by name. Schema EDGES outside a
    # permitted concept's own declaration still refuse here.
    # Membership targets are judged against the base PLUS this round's
    # own additions — the taxonomy ceremony's pattern: a subject may be
    # born by the round that declares into it.
    membership_view = None
    if base is not None:
        from .extract import GraphData
        membership_view = GraphData()
        membership_view.nodes = dict(base.nodes)
        for _label, _name, _props in delta.nodes_added:
            membership_view.nodes[(_label, _name)] = dict(_props or {})
        membership_view.edges = list(base.edges) + [
            e for e in delta.edges_added
            if e.from_label == ARCHETYPE_LABEL
            and e.to_label == ARCHETYPE_LABEL]
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
            elif not is_concept_archetype(membership_view, edge.to_name):
                violations.append(Verdict(
                    code="membership-target-not-concept",
                    subject=connection_ref(edge),
                    message=(
                        prefix + f"'{edge.to_name}' is not a Concept-rooted "
                        "Archetype in the base or this round — authored "
                        "membership classifies a citizen against "
                        "Concept-rooted subjects only: a plain concept, or "
                        "a label row that is also a concept (a home with a "
                        "catalog can be a subject too); never a Facet, a "
                        "Provenance-rooted row, or a missing node — and it "
                        "never re-homes the citizen. To undo: point the "
                        "edge at a Concept-rooted Archetype, or DELETE it "
                        "from scratch."),
                    remedy="Point the edge at a Concept-rooted Archetype, "
                           "or DELETE it from scratch."))
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
            if "declines" in dict(edge.props):
                violations.append(Verdict(
                    code="membership-declines-embedded",
                    subject=connection_ref(edge),
                    message=(
                        prefix + "it carries a `declines` property — "
                        "the owner's standing law is \"no embedded "
                        "lists\": a decline is its own connection, "
                        f"({edge.from_name})-[:{DECLINES_EDGE_TYPE}]->"
                        "(the declined concept), with its own `basis`. "
                        "Remove the property and author the "
                        "connection."),
                    remedy="Remove the property and author the "
                           f"{DECLINES_EDGE_TYPE} connection."))
        elif edge.type == DECLINES_EDGE_TYPE:
            violations.extend(_decline_verdicts(edge, delta, base))
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
            if edge.type == "SUBTYPE_OF" \
                    and set(changes) == {CONFERS_PROP} \
                    and edge.from_label == ARCHETYPE_LABEL \
                    and edge.to_label == ARCHETYPE_LABEL:
                # the conferral declaration is the one schema-edge edit
                # a designer makes by hand — adjudicated aloud by the
                # taxonomy ceremony (taxonomy-confers), never frozen
                continue
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
            if "declines" in dict(edge.props):
                violations.append(Verdict(
                    code="membership-declines-embedded",
                    subject=connection_ref(edge),
                    message=(
                        f"Attempted to edit the membership "
                        f"({edge.from_name})-[:{MEMBERSHIP_EDGE_TYPE}]->"
                        f"({edge.to_name}). Failed due to: the edit "
                        "leaves a `declines` property on it — the "
                        "owner's standing law is \"no embedded "
                        "lists\": a decline is its own connection, "
                        f"({edge.from_name})-[:{DECLINES_EDGE_TYPE}]->"
                        "(the declined concept), with its own `basis`. "
                        "Remove the property and author the "
                        "connection."),
                    remedy="Remove the property and author the "
                           f"{DECLINES_EDGE_TYPE} connection."))
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
        elif edge.type == DECLINES_EDGE_TYPE:
            violations.extend(_decline_verdicts(edge, delta, base))
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


def attribution_verdicts(delta, base=None):
    """Recorded-attribution lint: every link the round declares must be
    recordable as written — well-formed, and naming citizens that will
    exist in the graph this round produces (present in the base or born
    by this round's own additions). A link to nowhere refuses by name;
    provenance recorded against a citizen that is not there would be a
    guess wearing a record's clothes."""
    from .proposal import attribution_row
    violations = []
    base_nodes = base.nodes if base is not None else {}
    born = {(label, name) for label, name, _ in delta.nodes_added}
    for position, row in enumerate(delta.attribution, start=1):
        try:
            row = attribution_row(row)
        except ValueError as exc:
            violations.append(Verdict(
                code="attribution-row-malformed",
                message=(
                    f"Attempted to record attribution link {position}. "
                    f"Failed due to: {exc}."),
                remedy="Fix the link in the attribution file, then "
                       "re-run the delta."))
            continue
        for label, name in row["citizens"]:
            if (label, name) in base_nodes or (label, name) in born:
                continue
            violations.append(Verdict(
                code="attribution-home-missing",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to record that the claim "
                    f"\"{row['claim']}\" lives with ({label}) {name}. "
                    "Failed due to: no such citizen exists in the graph "
                    "this round produces — a recorded link must point at "
                    "a real home. Author the citizen in this round, or "
                    "correct the link."),
                remedy="Author the citizen in this round, or correct "
                       "the link in the attribution file."))
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


def fingerprint_verdicts(delta, base_dir):
    """The floor receipt at the gate: a citizen the round adds or
    re-fingerprints, whose name is a file under the knowledge base,
    must carry that file's fingerprint — a stale or mistyped receipt
    refuses by name. A name that is not a file on disk is not judged:
    a fingerprint may cite bytes held elsewhere."""
    import hashlib
    import pathlib

    verdicts = []
    rows = [(label, name, (props or {}).get("fingerprint"))
            for label, name, props in delta.nodes_added]
    rows += [(label, name, changes["fingerprint"][1])
             for label, name, changes in delta.nodes_changed
             if "fingerprint" in changes]
    for label, name, declared in rows:
        if not declared:
            continue
        relative = pathlib.Path(str(name))
        if relative.is_absolute() or ".." in relative.parts:
            continue  # a citizen's name never reaches outside the KB
        path = pathlib.Path(base_dir) / relative
        if not path.is_file():
            continue
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            verdicts.append(Verdict(
                code="fingerprint-file-unreadable",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to check the fingerprint '{name}' cites "
                    f"against the file. Failed due to: the file is not "
                    f"readable ({exc}) — restore the file or cite the "
                    "bytes you meant."),
                remedy="Restore the file or cite the bytes you meant.",
                data={"file": str(name), "declared": declared}))
            continue
        if actual != declared:
            verdicts.append(Verdict(
                code="fingerprint-mismatch",
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to cite {name} by fingerprint on "
                    f"'{name}'. Failed due to: the citizen declares "
                    f"{declared[:12]} but the file's bytes hash to "
                    f"{actual[:12]} — the receipt is stale or mistyped. "
                    f"Run python -m graph receipt {name} and paste its "
                    "fingerprint, or cite the bytes you meant."),
                remedy=(f"Run python -m graph receipt {name} and paste "
                        "its fingerprint, or cite the bytes you meant."),
                data={"file": str(name), "declared": declared,
                      "actual": actual}))
    return verdicts


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
