"""Migration — citizens change worlds, verbatim.

Two verbs, one content-addressed record, ordinary pocket rounds. The
record carries every leaving citizen and connection with properties
whole; the source's round removes them and rewrites every staying
reference into a bookmark toward the destination; the destination's
round adds them byte-identical and rewrites every moved reference into
a bookmark back toward the source. Each round rides its own line's
ordinary ritual, and the record rides both proposals under the
approval hash — a swapped record refuses as drift.

The ordering law — arrive, re-pin, then leave — is enforced by the
citation stack's own resolution gate: the emigration's rewritten
references are bookmarks, and a bookmark cannot resolve until the
destination's pinned edition holds the arrivals. Existence is never
lost; the double-existence window in the middle is the record's
business to name; each side's inverse is the recovery road. Cross-KB
atomicity is honestly not promised — that is the world-grain pocket's
future work, not this ceremony's claim.

Derived rows never ride: the machine layer stays home and re-derives
at the destination, where the foreign-name derivation takes over
(the movers' DEPICTS become bookmarked citations).
"""

import hashlib
import json

from .dependencies import RESOLVES_IN_EDGE
from .extract import make_edge
from .ontology import (KERNEL_BOOKMARK_LABEL, KERNEL_DEPENDENCY_LABEL,
                       is_derived_edge)
from .refs import CitizenRef, connection_ref
from .report import ADVISORY, REFUSAL, Verdict

MIGRATION_FILE = "migration.json"
# the machinery's marker on derived rows (the artifact model's): a row
# wearing it is the machine layer and never rides a migration
DERIVED_MARKER = "derived_from"


def _key(label, name):
    return (label, str(name))


def _edge_row(edge):
    return [edge.type, edge.from_label, str(edge.from_name),
            edge.to_label, str(edge.to_name), dict(edge.props)]


def record_id(record):
    """The record's content identity: sha256 of its canonical
    serialization, the id field itself excluded."""
    body = {k: v for k, v in record.items() if k != "id"}
    return hashlib.sha256(json.dumps(
        body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_record(graph, roots, source, destination):
    """(record, problems): the migration record for `roots` and their
    closure — the rows that belong to the movers and nothing else:
    their location rows behind LOCATED_AT, and their hand-authored
    interpretation rows ABOUT them. Derived rows never join. Edges
    partition by who moves: internal (both sides move), outbound (a
    mover references a stayer), inbound (a stayer references a mover).
    Properties ride verbatim."""
    problems = []
    movers = set()
    for label, name in roots:
        key = _key(label, name)
        props = graph.nodes.get(key)
        if props is None:
            problems.append(
                f"Attempted to build a migration record rooted at "
                f"({label}) '{name}'. Failed due to: no such citizen.")
            continue
        if (props or {}).get(DERIVED_MARKER):
            problems.append(
                f"Attempted to root a migration at ({label}) '{name}'. "
                "Failed due to: the row is machine-derived — the machine "
                "layer never rides a migration; it re-derives at the "
                "destination.")
            continue
        movers.add(key)
    if problems:
        return None, problems
    # closure to fixpoint: locations behind LOCATED_AT, hand-authored
    # interpretations ABOUT a mover
    grew = True
    while grew:
        grew = False
        for edge in graph.edges:
            if is_derived_edge(edge):
                continue
            from_key = _key(edge.from_label, edge.from_name)
            to_key = _key(edge.to_label, edge.to_name)
            if edge.type == "LOCATED_AT" and from_key in movers \
                    and to_key not in movers:
                movers.add(to_key)
                grew = True
            elif edge.type == "ABOUT" and to_key in movers \
                    and from_key not in movers:
                if (graph.nodes.get(from_key) or {}).get(DERIVED_MARKER):
                    continue  # the machine layer stays home
                movers.add(from_key)
                grew = True
    citizens = [[label, name, dict(graph.nodes.get((label, name)) or {})]
                for label, name in sorted(movers, key=str)]
    internal, outbound, inbound = [], [], []

    def machine_row(label, name):
        return bool((graph.nodes.get((label, name)) or {})
                    .get(DERIVED_MARKER))
    for edge in graph.edges:
        if is_derived_edge(edge):
            continue
        if machine_row(edge.from_label, edge.from_name) \
                or machine_row(edge.to_label, edge.to_name):
            continue  # the machine layer's edges re-derive; never ride
        from_in = _key(edge.from_label, edge.from_name) in movers
        to_in = _key(edge.to_label, edge.to_name) in movers
        if from_in and to_in:
            internal.append(_edge_row(edge))
        elif from_in:
            outbound.append(_edge_row(edge))
        elif to_in:
            inbound.append(_edge_row(edge))
    record = {
        "source": source, "destination": destination,
        "roots": [[label, str(name)] for label, name in roots],
        "citizens": citizens,
        "connections": sorted(internal, key=str),
        "outbound": sorted(outbound, key=str),
        "inbound": sorted(inbound, key=str),
    }
    record["id"] = record_id(record)
    return record, []


def _bookmark_name(dependency, label, name):
    return f"{dependency}:{label}:{name}"


def _ensure_bookmark(graph, dependency, label, name):
    """The local stand-in for a foreign citizen, minted once: the
    bookmark row and its RESOLVES_IN edge, edition taken from the pin
    as it stands."""
    bm = _bookmark_name(dependency, label, name)
    key = (KERNEL_BOOKMARK_LABEL, bm)
    if key not in graph.nodes:
        pin = graph.nodes.get((KERNEL_DEPENDENCY_LABEL, dependency)) or {}
        graph.ensure_node(KERNEL_BOOKMARK_LABEL, bm,
                          dependency=dependency, citizen_label=label,
                          citizen_name=name,
                          edition=pin.get("edition", ""))
        graph.edges.append(make_edge(RESOLVES_IN_EDGE,
                                     KERNEL_BOOKMARK_LABEL, bm,
                                     KERNEL_DEPENDENCY_LABEL, dependency))
    return bm


def emigrate_stage(graph, record):
    """Stage the source side IN PLACE: the movers leave whole (their
    connections go with them), and every staying citizen's reference to
    a mover is rewritten as a bookmark toward the destination. Every
    problem collates before anything is written."""
    problems = []
    destination = record["destination"]
    movers = {_key(label, name) for label, name, _ in record["citizens"]}
    for label, name, _props in record["citizens"]:
        if _key(label, name) not in {(l, str(n)) for (l, n) in graph.nodes}:
            problems.append(
                f"Attempted to emigrate ({label}) '{name}' to "
                f"'{destination}'. Failed due to: it is not present in "
                "this working copy.")
    if record["inbound"] and (KERNEL_DEPENDENCY_LABEL, destination) \
            not in graph.nodes:
        for row in record["inbound"]:
            etype, fl, fn, tl, tn, _props = row
            problems.append(
                f"Attempted to rewrite ({fl}) '{fn}' -[{etype}]-> "
                f"({tl}) '{tn}' as a citation into '{destination}'. "
                f"Failed due to: no [Knowledge Base Dependency] pin "
                f"toward '{destination}' exists here — pin it first.")
    if problems:
        return problems
    for label, name, _props in record["citizens"]:
        graph.nodes.pop((label, name), None)
    graph.edges = [edge for edge in graph.edges
                   if _key(edge.from_label, edge.from_name) not in movers
                   and _key(edge.to_label, edge.to_name) not in movers]
    for etype, fl, fn, tl, tn, props in record["inbound"]:
        bm = _ensure_bookmark(graph, destination, tl, tn)
        graph.edges.append(make_edge(etype, fl, fn,
                                     KERNEL_BOOKMARK_LABEL, bm, props))
    return []


def immigrate_stage(graph, record):
    """Stage the destination side IN PLACE: the arrivals land verbatim,
    and every moved citizen's reference to a stayer is rewritten as a
    bookmark back toward the source. Every problem collates before
    anything is written."""
    problems = []
    source = record["source"]
    if record["outbound"] and (KERNEL_DEPENDENCY_LABEL, source) \
            not in graph.nodes:
        problems.append(
            f"Attempted to immigrate {len(record['citizens'])} citizens "
            f"from '{source}'. Failed due to: no [Knowledge Base "
            f"Dependency] pin toward '{source}' exists here — the moved "
            "citizens' references to citizens staying there need it. "
            "Pin it first.")
    for label, name, _props in record["citizens"]:
        if (label, name) in graph.nodes:
            problems.append(
                f"Attempted to immigrate ({label}) '{name}' from "
                f"'{source}'. Failed due to: a citizen by that name "
                "already lives here.")
    if problems:
        return problems
    for label, name, props in record["citizens"]:
        graph.ensure_node(label, name, **dict(props))
    for etype, fl, fn, tl, tn, props in record["connections"]:
        graph.edges.append(make_edge(etype, fl, fn, tl, tn, props))
    for etype, fl, fn, tl, tn, props in record["outbound"]:
        bm = _ensure_bookmark(graph, source, tl, tn)
        graph.edges.append(make_edge(etype, fl, fn,
                                     KERNEL_BOOKMARK_LABEL, bm, props))
    return []


def migration_verdicts(delta, base, record):
    """The record against the round. The role is read from the round
    itself: departures mean the source, arrivals the destination. The
    record's own hash is verified first — a proposal whose record no
    longer matches its id refuses as drift."""
    verdicts = []
    if record.get("id") != record_id(record):
        verdicts.append(Verdict(
            code="migration-record-drift", severity=REFUSAL,
            message=("Attempted to judge a round against its migration "
                     "record. Failed due to: the record no longer "
                     "matches its own content id — it changed after it "
                     "was cut. Rebuild the record and re-stage."),
            remedy="Rebuild the record and re-stage the round."))
        return verdicts
    mover_keys = {_key(label, name)
                  for label, name, _ in record["citizens"]}
    removed = {_key(label, name) for label, name, _ in delta.nodes_removed}
    added = {_key(label, name): dict(props)
             for label, name, props in delta.nodes_added}
    short = record["id"][:12]
    if mover_keys & removed:
        missing = sorted(mover_keys - removed, key=str)
        for label, name in missing:
            verdicts.append(Verdict(
                code="migration-closure-broken", severity=REFUSAL,
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to emigrate the record's family "
                    f"({short}). Failed due to: ({label}) '{name}' is in "
                    "the record but does not leave with this round — a "
                    "family never splits. Re-stage the round, or rebuild "
                    "the record."),
                remedy="Re-stage the round, or rebuild the record."))
        if not missing:
            verdicts.append(Verdict(
                code="emigration-declared", severity=ADVISORY,
                message=(
                    f"EMIGRATION — {len(mover_keys)} citizens leave for "
                    f"'{record['destination']}' with "
                    f"{len(record['connections'])} connections among "
                    f"them; {len(record['inbound'])} staying references "
                    f"rewritten as citations; record {short}.")))
    elif mover_keys & set(added):
        drifted = []
        for label, name, props in record["citizens"]:
            arrived = added.get(_key(label, name))
            if arrived is None or arrived != dict(props):
                drifted.append((label, name))
        for label, name in drifted:
            verdicts.append(Verdict(
                code="migration-arrival-mismatch", severity=REFUSAL,
                subject=CitizenRef(label, name),
                message=(
                    f"Attempted to immigrate the record's family "
                    f"({short}). Failed due to: ({label}) '{name}' "
                    "arrives differently than the record carries it — "
                    "an arrival is byte-for-byte or it is not the same "
                    "citizen. Re-stage from the record."),
                remedy="Re-stage the arrivals from the record."))
        if not drifted:
            verdicts.append(Verdict(
                code="immigration-declared", severity=ADVISORY,
                message=(
                    f"IMMIGRATION — {len(mover_keys)} citizens arrive "
                    f"from '{record['source']}' with "
                    f"{len(record['connections'])} connections among "
                    f"them; {len(record['outbound'])} moved references "
                    f"rewritten as citations; record {short}.")))
    else:
        verdicts.append(Verdict(
            code="migration-closure-broken", severity=REFUSAL,
            message=(
                f"Attempted to judge this round against migration record "
                f"{short}. Failed due to: the round neither removes nor "
                "adds any of the record's citizens — the record does not "
                "belong to this round. Remove the record, or stage the "
                "migration."),
            remedy="Remove the record, or stage the migration."))
    return verdicts
