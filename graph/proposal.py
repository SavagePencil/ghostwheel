"""The proposal lifecycle: pinned base, delta identity, approval freeze.

Closes the review-then-apply gap (the review-then-apply gate, the R1 down-payment): what the
human approved is frozen by content hash, and apply replays only that.

- CUT: when scratch is created the round starts — base.json pins the
  content identity of the source-derived base (a hash of the
  deterministic serialization) plus the git ref for humans.
- PROPOSE: `delta` writes the machine-readable changeset (delta.json,
  canonical form); its sha256 IS the proposal's id. If the base has
  moved since the cut (sources edited mid-round), delta WARNS and keeps
  drafting — apply is where drift becomes a refusal.
- APPROVE: `approve` records {delta_hash, base_hash, by, at} — run by
  the submitter or an agent on their behalf; the record names the
  human. (Future escalation routing for protected classes of change is
  an open Question citizen.)
- APPLY: `canonize --apply` refuses without an approval record, refuses
  if the base moved (re-load and re-review — the whole shebang
  re-baselines), refuses if scratch has drifted from the approved
  changeset (divergence NAMED item by item), and otherwise applies
  exactly the pinned artifact.
- ARCHIVE: on success the round's artifacts move to
  graph/proposals/<id12>/ — git-tracked, the durable audit trail.

Pure logic (canonical serialization, hashing, divergence naming) is
driver-free and unit-tested; file I/O helpers take explicit paths.
"""

import hashlib
import json
from pathlib import Path

from .delta import Delta
from .extract import make_edge

PROPOSALS = "proposals"
CURRENT = "current"
BASE_FILE = "base.json"
DELTA_FILE = "delta.json"
APPROVAL_FILE = "approval.json"
APPLIED_FILE = "applied.json"
INVERSE_FILE = "inverse.json"
STITCH_FILE = "stitch.json"
ATTRIBUTION_FILE = "attribution.json"


# -- canonical delta document ---------------------------------------------


def _edge_doc(edge):
    return {"type": edge.type,
            "from_label": edge.from_label, "from_name": edge.from_name,
            "to_label": edge.to_label, "to_name": edge.to_name,
            "props": dict(edge.props)}


def _edge_from_doc(doc):
    return make_edge(doc["type"], doc["from_label"], doc["from_name"],
                     doc["to_label"], doc["to_name"], doc.get("props"))


def serialize_delta(delta):
    """Delta -> canonical JSON text. Deterministic (diff() sorts every
    class), so the same changeset always hashes to the same id."""
    doc = {
        "nodes_added": [[l, n, p] for l, n, p in delta.nodes_added],
        "nodes_removed": [[l, n, p] for l, n, p in delta.nodes_removed],
        "nodes_changed": [[l, n, {k: list(v) for k, v in c.items()}]
                          for l, n, c in delta.nodes_changed],
        "edges_added": [_edge_doc(e) for e in delta.edges_added],
        "edges_removed": [_edge_doc(e) for e in delta.edges_removed],
        "edges_changed": [[_edge_doc(e), {k: list(v) for k, v in c.items()}]
                          for e, c in delta.edges_changed],
    }
    if delta.stitch:
        # The stitch mechanism: present only when the round declares one, so every
        # pre-stitch round's archived document still hashes to the id
        # its event-log entry recorded
        doc["stitch"] = [_edge_doc(e) for e in delta.stitch]
    if delta.attribution:
        # Recorded attribution (the provenance-recording rung): present
        # only when the round declares links, so every earlier round's
        # archived document still hashes to its recorded id. Riding
        # inside the approved bytes puts each link under the approval's
        # tamper coverage and in front of the diff gate.
        doc["attribution"] = sorted(
            (attribution_row(r) for r in delta.attribution),
            key=lambda r: (r["source"], r["locator"], r["claim"]))
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1)


# the keys an attribution row may carry: the claim's home in its source
# (path, content-addressed locator, the sentence itself as the
# re-locating quote) and the citizens it attests; surface and grade are
# historical color from the judgment that proposed the link
_ATTRIBUTION_REQUIRED = ("source", "locator", "claim", "citizens")
_ATTRIBUTION_OPTIONAL = ("surface", "grade")


def attribution_row(doc):
    """One claim→citizen link in canonical form. Raises ValueError on a
    row that cannot be recorded as written — collated by the caller."""
    if not isinstance(doc, dict):
        raise ValueError(
            f"a link must be an object, not a {type(doc).__name__}")
    for key in _ATTRIBUTION_REQUIRED:
        if key not in doc:
            raise ValueError(f"a link is missing its '{key}'")
    citizens = doc["citizens"]
    if (not isinstance(citizens, list) or not citizens
            or not all(isinstance(c, (list, tuple)) and len(c) == 2
                       and all(isinstance(part, str) and part
                               for part in c)
                       for c in citizens)):
        raise ValueError(
            "a link's 'citizens' must be a non-empty list of "
            "[kind, name] pairs")
    for key in ("source", "locator", "claim"):
        if not isinstance(doc[key], str) or not doc[key].strip():
            raise ValueError(f"a link's '{key}' must be non-empty text")
    row = {"source": doc["source"], "locator": doc["locator"],
           "claim": doc["claim"],
           "citizens": [[c[0], c[1]] for c in citizens]}
    for key in _ATTRIBUTION_OPTIONAL:
        if doc.get(key):
            row[key] = str(doc[key])
    return row


def parse_delta(text):
    doc = json.loads(text)
    delta = Delta()
    delta.nodes_added = [(l, n, p) for l, n, p in doc["nodes_added"]]
    delta.nodes_removed = [(l, n, p) for l, n, p in doc["nodes_removed"]]
    delta.nodes_changed = [(l, n, {k: tuple(v) for k, v in c.items()})
                           for l, n, c in doc["nodes_changed"]]
    delta.edges_added = [_edge_from_doc(d) for d in doc["edges_added"]]
    delta.edges_removed = [_edge_from_doc(d) for d in doc["edges_removed"]]
    delta.edges_changed = [(_edge_from_doc(d), {k: tuple(v)
                                                for k, v in c.items()})
                           for d, c in doc["edges_changed"]]
    delta.stitch = [_edge_from_doc(d) for d in doc.get("stitch", [])]
    delta.attribution = [dict(d) for d in doc.get("attribution", [])]
    return delta


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def base_identity(graph):
    """The base's content identity: hash over the deterministic
    serialization (the same bytes `export` writes)."""
    from . import export as export_mod
    digest = hashlib.sha256()
    for filename, content in sorted(export_mod.serialize(graph).items()):
        digest.update(filename.encode("utf-8"))
        digest.update(content.encode("utf-8"))
    return digest.hexdigest()


def invert_delta(delta):
    """The delta's inverse — the undo record made executable (the reversible event log).
    Every class inverts mechanically because removals and changes carry
    full before-images (the before-image capture): adds become removals, removals restore
    from their before-images, changes flip before/after."""
    inverse = Delta()
    inverse.nodes_removed = [(label, name, dict(props))
                             for label, name, props in delta.nodes_added]
    inverse.nodes_added = [(label, name, dict(props))
                           for label, name, props in delta.nodes_removed]
    inverse.nodes_changed = [
        (label, name, {prop: (after, before)
                       for prop, (before, after) in changes.items()})
        for label, name, changes in delta.nodes_changed]
    # stitched edges are additions once landed — the undo removes them
    inverse.edges_removed = list(delta.edges_added) + list(delta.stitch)
    inverse.edges_added = list(delta.edges_removed)
    inverse.edges_changed = []
    for edge, changes in delta.edges_changed:
        before_props = dict(edge.props)
        for prop, (before, _) in changes.items():
            if before is None:
                before_props.pop(prop, None)
            else:
                before_props[prop] = before
        before_edge = make_edge(edge.type, edge.from_label, edge.from_name,
                                edge.to_label, edge.to_name, before_props)
        inverse.edges_changed.append(
            (before_edge, {prop: (after, before)
                           for prop, (before, after) in changes.items()}))
    return inverse


def apply_delta(graph, delta):
    """Apply a delta to a GraphData IN PLACE — the pure applier the
    event-log replay check and the walk-back ride on (the graph-native
    driver applier is this, spoken in Cypher). Preconditions verify
    against before-images; problems collate; NOTHING is applied unless
    everything can be (verify-all before apply-any)."""
    problems = []
    edges = list(graph.edges)
    for label, name, props in delta.nodes_added:
        if (label, name) in graph.nodes:
            problems.append(f"cannot add ({label}) '{name}' — it already "
                            "exists; the base moved under the log entry")
    for label, name, before in delta.nodes_removed:
        current = graph.nodes.get((label, name))
        if current is None:
            problems.append(f"cannot remove ({label}) '{name}' — it is "
                            "not present")
        elif dict(current) != dict(before):
            problems.append(f"cannot remove ({label}) '{name}' — its "
                            "properties changed since the before-image")
    for label, name, changes in delta.nodes_changed:
        current = graph.nodes.get((label, name))
        if current is None:
            problems.append(f"cannot edit ({label}) '{name}' — it is "
                            "not present")
            continue
        for prop, (before, _) in changes.items():
            if current.get(prop) != before:
                problems.append(
                    f"cannot edit ({label}) '{name}'.{prop} — it reads "
                    f"{current.get(prop)!r}, the log says {before!r}")
    for edge in delta.edges_removed:
        if edge not in edges:
            problems.append(f"cannot remove ({edge.from_name})-"
                            f"[:{edge.type}]->({edge.to_name}) — no such "
                            "connection with those properties")
    def pre_state(edge, changes):
        props = dict(edge.props)
        for prop, (pre, _) in changes.items():
            if pre is None:
                props.pop(prop, None)
            else:
                props[prop] = pre
        return make_edge(edge.type, edge.from_label, edge.from_name,
                         edge.to_label, edge.to_name, props)

    for target_edge, changes in delta.edges_changed:
        if pre_state(target_edge, changes) not in edges:
            problems.append(f"cannot re-edit ({target_edge.from_name})-"
                            f"[:{target_edge.type}]->"
                            f"({target_edge.to_name}) — its current "
                            "properties do not match the log")
    if problems:
        return problems

    for label, name, props in delta.nodes_added:
        graph.ensure_node(label, name, **dict(props))
    for label, name, _ in delta.nodes_removed:
        del graph.nodes[(label, name)]
    for label, name, changes in delta.nodes_changed:
        node = graph.nodes[(label, name)]
        for prop, (_, after) in changes.items():
            if after is None:
                node.pop(prop, None)
            else:
                node[prop] = after
    for edge in delta.edges_removed:
        edges.remove(edge)
    edges.extend(delta.edges_added)
    for target_edge, changes in delta.edges_changed:
        edges[edges.index(pre_state(target_edge, changes))] = target_edge
    graph.edges = edges
    return []


def file_era_executed(delta):
    """The subset of a delta the FILE-ERA apply actually executes:
    removals (nodes and edges) are manual approver acts canonize never
    writes, so pre-flip they are logged-but-pending. The replay check
    compares the executed subset; the archived delta and inverse stay
    complete. Post-flip the graph-native applier executes everything and
    this distinction retires."""
    executed = Delta()
    executed.nodes_added = list(delta.nodes_added)
    executed.nodes_changed = list(delta.nodes_changed)
    executed.edges_added = list(delta.edges_added)
    executed.edges_changed = list(delta.edges_changed)
    return executed


def ground_identity(graph):
    """The GROUND truth's content identity: the serialization with the
    machine-recomputed layers excluded (derived edge types; machine
    labels). The event log replays ground facts identically; derived
    layers are deterministic functions recomputed from them."""
    from .canonize import RECEIPT_PROPS
    from .extract import GraphData
    from .ontology import UNAUTHORABLE_EDGE_TYPES, UNAUTHORABLE_LABELS
    ground = GraphData()
    for (label, name), props in graph.nodes.items():
        if label not in UNAUTHORABLE_LABELS:
            ground.ensure_node(label, name,
                               **{k: v for k, v in props.items()
                                  if k not in RECEIPT_PROPS})
    ground.edges = [
        make_edge(edge.type, edge.from_label, edge.from_name,
                  edge.to_label, edge.to_name,
                  {k: v for k, v in edge.props if k not in RECEIPT_PROPS})
        for edge in graph.edges
        if edge.type not in UNAUTHORABLE_EDGE_TYPES
        and edge.from_label not in UNAUTHORABLE_LABELS
        and edge.to_label not in UNAUTHORABLE_LABELS
        and not edge.type.startswith("ASSIGNS_")]
    return base_identity(ground)


def divergence(pinned, current):
    """What changed between the approved changeset and scratch-now —
    named item by item, so a refusal is actionable. Empty = frozen."""
    problems = []
    for section in ("nodes_added", "nodes_removed", "nodes_changed",
                    "edges_added", "edges_removed", "edges_changed",
                    "stitch", "attribution"):
        pinned_items = {json.dumps(item, ensure_ascii=False, sort_keys=True,
                                   default=list)
                        for item in json.loads(
                            serialize_delta(pinned)).get(section, [])}
        current_items = {json.dumps(item, ensure_ascii=False, sort_keys=True,
                                    default=list)
                         for item in json.loads(
                             serialize_delta(current)).get(section, [])}
        for item in sorted(current_items - pinned_items):
            problems.append(f"{section}: scratch now proposes {item} — "
                            "this was never reviewed")
        for item in sorted(pinned_items - current_items):
            problems.append(f"{section}: the reviewed item {item} is no "
                            "longer in scratch")
    return problems


def apply_stitch(graph, stitch):
    """The stitch mechanism: land the stitch on the re-derived graph IN MEMORY — after
    derivation has birthed the round's new citizens, before anything is
    written. Verify every endpoint exists and every connection is new;
    problems collate and NOTHING lands unless everything can
    (verify-all before apply-any, apply_delta's doctrine)."""
    problems = []
    for edge in stitch:
        for label, name, side in ((edge.from_label, edge.from_name, "from"),
                                  (edge.to_label, edge.to_name, "to")):
            if (label, name) not in graph.nodes:
                problems.append(
                    f"cannot stitch ({edge.from_name})-[:{edge.type}]->"
                    f"({edge.to_name}) — its {side} endpoint ({label}) "
                    f"'{name}' does not exist even after re-derivation. "
                    "Is the schema edit that births it part of this "
                    "round?")
        if edge in graph.edges:
            problems.append(
                f"cannot stitch ({edge.from_name})-[:{edge.type}]->"
                f"({edge.to_name}) — that connection already exists; "
                "the stitch entry is stale, remove it from the stitch "
                "file.")
    if problems:
        return problems
    graph.edges.extend(stitch)
    return []


# -- branches: independent lines of truth within a KB ---------------------
# A branch is a line of truth WITHIN a knowledge base — its own base,
# authoring ceremony, and chained log, hard-isolated from live canon.
# Live canon is the unnamed default line (branch=None): its homes keep
# today's exact paths, byte-unchanged. A named branch lives under
# graph/branches/<name>/ with its own export, proposals, and applied.log.
# (The future composition layer above branches — a KB-mounting manifest
# role, issue #6 — is never a filesystem home here.)


def branch_home(base_dir, branch):
    """A named branch's filesystem home. The default line has no single
    home — its paths are the legacy graph/ ones — so this is for named
    branches only."""
    return Path(base_dir) / "graph" / "branches" / branch


def export_dir(base_dir, branch=None):
    """The branch's committed backup directory. Default line: graph/export
    (unchanged). Named branch: graph/branches/<name>/export."""
    if branch is None:
        return Path(base_dir) / "graph" / "export"
    return branch_home(base_dir, branch) / "export"


def proposals_dir(base_dir, branch=None):
    """The branch's proposals directory (current/ + archived rounds).
    Default line: graph/proposals (unchanged). Named branch:
    graph/branches/<name>/proposals."""
    if branch is None:
        return Path(base_dir) / "graph" / PROPOSALS
    return branch_home(base_dir, branch) / PROPOSALS


RESERVED_SCRATCH = "scratch"
RESERVED_SUFFIX = "-scratch"


def branch_name_problems(branch, live_canon_db):
    """The branch-name lint, collated in plain words. A branch name is a
    line-of-truth identity, so it may never be:
      - the live canon database (a branch never becomes canon by flag;
        succession is the owner's ceremony),
      - 'scratch' (the default line's authoring copy — an ordinary round
        would clobber it),
      - any '<name>-scratch' name (those name authoring copies, including
        a branch's own <name>-scratch — never a line of truth).
    Empty list = the name is clean."""
    problems = []
    if not branch:
        problems.append(
            "Attempted a branch operation with no branch name. Failed "
            "due to: name the line of truth with --branch <name>.")
        return problems
    if branch == live_canon_db:
        problems.append(
            f"Attempted to name a branch '{branch}'. Failed due to: that "
            "is the live canon database — a branch is a separate line of "
            "truth and never becomes canon by flag (succession is the "
            "owner's ceremony). Pick another name.")
    if branch == RESERVED_SCRATCH or branch.endswith(RESERVED_SUFFIX):
        problems.append(
            f"Attempted to name a branch '{branch}'. Failed due to: "
            "'scratch' and any '<name>-scratch' name is reserved for "
            "authoring copies, not lines of truth — an ordinary round or "
            "a branch's own authoring copy would collide with it. Pick "
            "another name.")
    return problems


def branch_target_database(branch, live_canon_db):
    """The database a branch round writes to: the branch's name — one
    identity, no aliases — with the branch-name lint applied. Returns
    (target_db, problems); problems is empty when the name is clean, so
    the caller collates it verify-all-before-apply-any."""
    return branch, branch_name_problems(branch, live_canon_db)


def authoring_read_problem(authoring_db, live_canon_db):
    """A branch may never read the live canon database as its authoring
    source — it is hard-isolated from canon on the read side too, not
    only the write side. Returns the error-doctrine refusal, or None."""
    if authoring_db == live_canon_db:
        return (
            f"Attempted to read the live canon database '{authoring_db}' "
            "as a branch round's authoring source. Failed due to: a "
            "branch is hard-isolated from canon — it can never read "
            "canon as its source nor write to it. Name the branch's own "
            "authoring copy (<name>-scratch).")
    return None


# -- round files ----------------------------------------------------------


def current_dir(base_dir, branch=None):
    return proposals_dir(base_dir, branch) / CURRENT


def read_stitch(base_dir, branch=None):
    """The stitch mechanism: the round's declared stitch — ground edges the author files
    at proposals/current/stitch.json (a JSON list in delta.json's
    edge shape) because their endpoints are born by this round's schema
    edit and cannot be authored in scratch. Absent file = no stitch."""
    path = current_dir(base_dir, branch) / STITCH_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        raise ValueError(
            f"Attempted to read the stitch file ({STITCH_FILE}) as a "
            "list of connections. Failed due to: the file holds a "
            f"{type(doc).__name__} instead — write a JSON list of "
            "objects with type, from_label, from_name, to_label, "
            "to_name, and optional props.")
    return [_edge_from_doc(d) for d in doc]


def read_attribution_file(base_dir, branch=None):
    """The round's declared claim→citizen links — the author files them
    at proposals/current/attribution.json (a JSON list of link rows:
    source, locator, claim, citizens, optional surface/grade) beside
    the scratch work that used them. Absent file = a round that records
    no links. Raises ValueError naming every malformed row at once."""
    path = current_dir(base_dir, branch) / ATTRIBUTION_FILE
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, list):
        raise ValueError(
            f"Attempted to read the attribution file ({ATTRIBUTION_FILE}) "
            "as a list of links. Failed due to: the file holds a "
            f"{type(doc).__name__} instead — write a JSON list of "
            "objects with source, locator, claim, citizens, and "
            "optional surface and grade.")
    rows, problems = [], []
    for position, entry in enumerate(doc, start=1):
        try:
            rows.append(attribution_row(entry))
        except ValueError as exc:
            problems.append(f"link {position}: {exc}")
    if problems:
        raise ValueError(
            f"Attempted to read the attribution file ({ATTRIBUTION_FILE}). "
            "Failed due to: " + "; ".join(problems)
            + " — fix each named link, then re-run the delta.")
    return rows


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


APPLIED_LOG = "applied.log"


def applied_log_path(base_dir, branch=None):
    """The chained event log's path. Default line: graph/proposals/
    applied.log (unchanged). Named branch: graph/branches/<name>/
    applied.log — a sibling of proposals/, per the branch home layout."""
    if branch is None:
        return Path(base_dir) / "graph" / PROPOSALS / APPLIED_LOG
    return branch_home(base_dir, branch) / APPLIED_LOG


def read_applied_log(base_dir, branch=None):
    """[(seq, delta_hash, base_before, base_after, prev_chain, chain)] —
    the event log's ordered spine."""
    path = applied_log_path(base_dir, branch)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        seq, delta_hash, base_before, base_after, prev_chain, chain = \
            line.split()
        entries.append((int(seq), delta_hash, base_before, base_after,
                        prev_chain, chain))
    return entries


def next_log_sequence(base_dir, branch=None):
    """The sequence number the NEXT applied round will carry — one past
    the log's last entry (1 for the first round). The project ontology's
    version stamp reads this at apply so a fresh connection's version
    moves with the event log, not with a file (owner ruling, 2026-08-03).
    Computed the same way append_applied_log assigns seq, so the stamp and
    the log entry always agree."""
    entries = read_applied_log(base_dir, branch)
    return entries[-1][0] + 1 if entries else 1


# A branch's fork annotation: a comment line in the branch's own event
# log (comments are chain-inert and the log rides every archive copy),
# recording where CANON's log stood at the cut. This is the fork point
# succession's divergence advisory enumerates from — no sidecar file.
FORK_PREFIX = "# fork "

LOG_HEADER = (
    "# The event log: one chained line per applied round —\n"
    "# seq, delta hash, base identity before/after, predecessor's\n"
    "# chain hash, this entry's chain hash. Rewriting any entry\n"
    "# breaks every later link.\n")


def write_branch_fork(base_dir, branch, record):
    """Annotate a freshly cut branch's event log with its fork record.
    Creates the log (standard header first) when the cut precedes the
    branch's first round — append_applied_log then appends beneath."""
    path = applied_log_path(base_dir, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if path.exists() else LOG_HEADER
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(prefix + FORK_PREFIX + json.dumps(
            record, ensure_ascii=False, sort_keys=True) + "\n")


def read_branch_fork(base_dir, branch):
    """The branch's fork record, or None for a branch cut before fork
    annotations existed (the advisory then degrades honestly)."""
    path = applied_log_path(base_dir, branch)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(FORK_PREFIX):
            try:
                return json.loads(line[len(FORK_PREFIX):])
            except ValueError:
                return None
    return None


# The attribution ledger: the current recorded claim→citizen links,
# folded from each applied round's attribution block — an applied.log
# twin (same home, same archive/succession copy semantics). Rows carry
# the sequence of the round that recorded them; when the same claim is
# recorded again, the later row is the ruling that stands.
ATTRIBUTION_LOG = "attribution.jsonl"


def attribution_log_path(base_dir, branch=None):
    if branch is None:
        return Path(base_dir) / "graph" / PROPOSALS / ATTRIBUTION_LOG
    return branch_home(base_dir, branch) / ATTRIBUTION_LOG


def read_attribution_log(base_dir, branch=None):
    """The line's recorded links, in fold order (later rows supersede
    earlier rows for the same claim — the audit applies that rule)."""
    path = attribution_log_path(base_dir, branch)
    if not path.exists():
        return []
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def append_attribution_log(base_dir, rows, sequence, branch=None):
    """Fold one applied round's links into the ledger, stamped with the
    round's event-log sequence."""
    if not rows:
        return
    path = attribution_log_path(base_dir, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps({**row, "sequence": sequence},
                                    ensure_ascii=False, sort_keys=True)
                         + "\n")


def append_applied_log(base_dir, delta_hash, base_before, base_after,
                       branch=None):
    """One chained entry per applied round: each names its predecessor's
    chain hash, so history is tamper-evident — rewriting any entry
    breaks every later link. Returns the new entry's chain hash."""
    entries = read_applied_log(base_dir, branch)
    seq = next_log_sequence(base_dir, branch)
    prev_chain = entries[-1][5] if entries else "genesis"
    chain = content_hash(
        f"{seq} {delta_hash} {base_before} {base_after} {prev_chain}")
    path = applied_log_path(base_dir, branch)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(LOG_HEADER, encoding="utf-8")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{seq} {delta_hash} {base_before} {base_after} "
                     f"{prev_chain} {chain}\n")
    return chain


def verify_applied_log(base_dir, branch=None):
    """The chain, re-derived and compared — a broken link is named."""
    problems = []
    prev = "genesis"
    for seq, delta_hash, base_before, base_after, prev_chain, chain in \
            read_applied_log(base_dir, branch):
        if prev_chain != prev:
            problems.append(f"entry {seq}: predecessor hash mismatch — "
                            "the log was rewritten above this line")
        expected = content_hash(
            f"{seq} {delta_hash} {base_before} {base_after} {prev_chain}")
        if chain != expected:
            problems.append(f"entry {seq}: chain hash mismatch — this "
                            "line was altered")
        prev = expected
    return problems


def archive_round(base_dir, delta_id, branch=None):
    """Move the current round's artifacts to their durable home,
    proposals/<id12>/. Returns the archive directory."""
    src = current_dir(base_dir, branch)
    dst = proposals_dir(base_dir, branch) / delta_id[:12]
    dst.mkdir(parents=True, exist_ok=True)
    for name in (BASE_FILE, DELTA_FILE, APPROVAL_FILE, APPLIED_FILE,
                 INVERSE_FILE, STITCH_FILE):
        path = src / name
        if path.exists():
            (dst / name).write_text(path.read_text(encoding="utf-8"),
                                    encoding="utf-8")
            path.unlink()
    return dst
