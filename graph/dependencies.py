"""Dependencies and bookmarks: a knowledge base pinning another, and
citing a citizen that lives there (kernel 0.15.0).

A [Knowledge Base Dependency] is another knowledge base this one pins to an edition —
the dependency's committed-backup identity hash and event-log sequence
— with an intent (read, or write). A [Citizen Bookmark] is a citizen that lives
in a dependency: its knowledge base, label, and name there, and the
edition it was resolved against, with exactly one RESOLVES_IN edge to
its [Knowledge Base Dependency]. This knowledge base's own citizens point at a
bookmark through their own relation vocabulary. Where a dependency
lives on disk is settings, never canon.

This module is the delta gate's STRUCTURAL check over the two: required
properties present, the intent one of the two known words, the sequence
a whole number, every touched bookmark resolving in exactly one
dependency that exists in the round's own graph, and a dependency never
removed while a bookmark still resolves in it. Resolution against the
dependency's backup — does the cited citizen exist at the pinned
edition, is the pin behind — is the next rung's verb.
"""

from dataclasses import dataclass
from pathlib import Path

from .extract import GraphData
from .ontology import KERNEL_BOOKMARK_LABEL, KERNEL_DEPENDENCY_LABEL
from .refs import CitizenRef, connection_ref
from .report import Verdict

RESOLVES_IN_EDGE = "RESOLVES_IN"
INTENTS = ("read", "write")
DEPENDENCY_REQUIRED = ("edition", "sequence", "intent")
# The cited citizen's label and name there ride as citizen_label /
# citizen_name: a property literally named `label` would collide with
# the graph's own row shape (label, name, properties) on every read.
BOOKMARK_REQUIRED = ("dependency", "citizen_label", "citizen_name",
                     "edition")


def _touched(delta, label):
    names = {name for lbl, name, _ in delta.nodes_added if lbl == label}
    names |= {name for lbl, name, _ in delta.nodes_changed if lbl == label}
    return names


def _blank(value):
    return value is None or value == ""


def gate_verdicts(delta, scratch):
    """Structural verdicts over the dependencies and bookmarks this
    round touches, judged against the round's own graph (scratch = base
    plus the round, so "exists in the base or the same round" is one
    lookup)."""
    verdicts = []
    dependency, bookmark = KERNEL_DEPENDENCY_LABEL, KERNEL_BOOKMARK_LABEL

    # -- dependencies -------------------------------------------------------
    for name in sorted(_touched(delta, dependency), key=str):
        props = scratch.nodes.get((dependency, name)) or {}
        missing = [prop for prop in DEPENDENCY_REQUIRED
                   if _blank(props.get(prop))]
        if missing:
            verdicts.append(Verdict(
                code="dependency-incomplete",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to pin knowledge base '{name}' as a "
                    f"dependency. Failed due to: the entry lacks "
                    f"{', '.join(missing)} — a dependency is pinned to an "
                    "edition (its backup's identity hash and event-log "
                    "sequence) and declares an intent (read or write). "
                    "Add the missing properties in scratch."),
                remedy="Add the missing properties in scratch.",
                data={"missing": missing}))
        intent = props.get("intent")
        if not _blank(intent) and intent not in INTENTS:
            verdicts.append(Verdict(
                code="dependency-intent-unknown",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to pin knowledge base '{name}' with intent "
                    f"'{intent}'. Failed due to: intent is read or write, "
                    "nothing else — read for a dependency this knowledge "
                    "base only consults, write when a shared activity may "
                    "land rounds there. Set it to one of the two in "
                    "scratch."),
                remedy="Set intent to read or write in scratch.",
                data={"intent": intent}))
        sequence = props.get("sequence")
        if not _blank(sequence) and (isinstance(sequence, bool)
                                     or not isinstance(sequence, int)):
            verdicts.append(Verdict(
                code="dependency-sequence-invalid",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to pin knowledge base '{name}' at sequence "
                    f"{sequence!r}. Failed due to: the sequence is the "
                    "dependency's event-log number at the pinned edition, "
                    "a whole number. Copy it from the dependency's applied "
                    "log."),
                remedy="Set sequence to the dependency's event-log number "
                       "at the pinned edition.",
                data={"sequence": sequence}))

    # -- bookmarks --------------------------------------------------------
    links = {}
    for edge in scratch.edges:
        if edge.type == RESOLVES_IN_EDGE:
            links.setdefault((edge.from_label, edge.from_name), []).append(edge)
    touched = _touched(delta, bookmark)
    for edge in list(delta.edges_added) + list(delta.edges_removed):
        if edge.type == RESOLVES_IN_EDGE and edge.from_label == bookmark:
            touched.add(edge.from_name)
    for name in sorted(touched, key=str):
        key = (bookmark, name)
        if key not in scratch.nodes:
            continue  # a bookmark the round removes has nothing to hold
        props = scratch.nodes[key] or {}
        missing = [prop for prop in BOOKMARK_REQUIRED
                   if _blank(props.get(prop))]
        if missing:
            verdicts.append(Verdict(
                code="bookmark-incomplete",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark '{name}'. Failed due to: the "
                    f"bookmark lacks {', '.join(missing)} — a bookmark "
                    "names the dependency it resolves in, the cited "
                    "citizen's label and name there, and the dependency "
                    "edition it was resolved against. Add the missing "
                    "properties in scratch."),
                remedy="Add the missing properties in scratch.",
                data={"missing": missing}))
        resolved = [edge for edge in links.get(key, [])
                    if edge.to_label == dependency
                    and (dependency, edge.to_name) in scratch.nodes]
        if len(resolved) != 1:
            dangling = [edge.to_name for edge in links.get(key, [])
                        if edge not in resolved]
            if not links.get(key):
                why = "it carries no RESOLVES_IN edge"
            elif len(resolved) > 1:
                why = (f"it carries {len(resolved)} RESOLVES_IN edges "
                       "(exactly one is the rule)")
            else:
                why = ("its RESOLVES_IN edge points at "
                       + ", ".join(f"'{d}'" for d in dangling)
                       + ", which is no dependency in the base or this "
                       "round")
            verdicts.append(Verdict(
                code="bookmark-unresolved",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark '{name}'. Failed due to: {why} "
                    "— a bookmark resolves in exactly one pinned "
                    "dependency. Author one RESOLVES_IN edge to the "
                    "dependency's entry (pin the dependency first if it "
                    "has none)."),
                remedy="Author one RESOLVES_IN edge to the dependency's "
                       "entry.",
                data={"resolved": [edge.to_name for edge in resolved],
                      "dangling": dangling}))
        elif not _blank(props.get("dependency")) and \
                props.get("dependency") != resolved[0].to_name:
            verdicts.append(Verdict(
                code="bookmark-dependency-mismatch",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark '{name}' in dependency "
                    f"'{props.get('dependency')}'. Failed due to: its "
                    f"RESOLVES_IN edge resolves it in "
                    f"'{resolved[0].to_name}' — the dependency named on "
                    "the bookmark and the one it resolves in must agree. "
                    "Fix whichever is wrong."),
                remedy="Make the bookmark's dependency and its RESOLVES_IN "
                       "target agree.",
                data={"dependency": props.get("dependency"),
                      "resolved": resolved[0].to_name}))

    # -- the edge itself, and a dependency still cited ------------------------
    for edge in delta.edges_added:
        if edge.type == RESOLVES_IN_EDGE and (edge.from_label != bookmark
                                              or edge.to_label != dependency):
            verdicts.append(Verdict(
                code="resolves-in-misused",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to author RESOLVES_IN from "
                    f"({edge.from_label}) '{edge.from_name}' to "
                    f"({edge.to_label}) '{edge.to_name}'. Failed due to: "
                    "RESOLVES_IN runs from a bookmark to the dependency it "
                    "lives in, nothing else — a knowledge base's own "
                    "citizens point at a bookmark through their own "
                    "relation vocabulary. Delete the edge in scratch and "
                    "author the intended one."),
                remedy="Delete the edge in scratch and author the "
                       "intended one."))
    removed = {name for lbl, name, _ in delta.nodes_removed
               if lbl == dependency}
    for name in sorted(removed, key=str):
        cited_by = sorted(str(key[1]) for key, edges in links.items()
                          for edge in edges
                          if edge.to_label == dependency
                          and edge.to_name == name and key in scratch.nodes)
        if cited_by:
            verdicts.append(Verdict(
                code="dependency-still-cited",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to unpin knowledge base '{name}'. Failed "
                    f"due to: {len(cited_by)} bookmark(s) still resolve "
                    f"there ({', '.join(cited_by[:5])}"
                    f"{', …' if len(cited_by) > 5 else ''}). Retire those "
                    "bookmarks in the same round, or keep the dependency."),
                remedy="Retire the bookmarks in the same round, or keep "
                       "the dependency.",
                data={"bookmarks": cited_by}))
    return verdicts


# -- reaching a dependency: its checkout on this machine ----------------------
#
# Where a dependency lives on disk is settings, never canon: one line per
# dependency in the pinning knowledge base's .env, GHOSTWHEEL_DEPENDENCY_
# <NAME>=<path>. The engine reads <path>/graph/export and computes what
# is there — identity hash, anchor sequence, declared name. Nothing is
# fetched; trust rides the hash, so the transport is free to change.

SETTINGS_PREFIX = "GHOSTWHEEL_DEPENDENCY_"
REPORT_FILE = "dependencies-report.json"


def settings_key(name):
    """The .env key naming a dependency's checkout: the prefix plus the
    dependency's name in settings shape (upper case, runs of anything
    but letters and digits folded to one underscore)."""
    import re
    return SETTINGS_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_",
                                    str(name)).strip("_").upper()


def dependency_path(config, name):
    value = (config.get(settings_key(name)) or "").strip()
    return Path(value).expanduser() if value else None


@dataclass
class Checkout:
    """A dependency's checkout as it stands on disk."""
    name: str
    path: Path
    identity: str      # the committed backup's identity hash
    sequence: int      # its anchor's event-log sequence (0 before any round)
    kb: str            # the name the checkout declares for itself
    graph: GraphData   # the backup, read


def anchor_sequence(graph):
    from .ontology import ARCHETYPE_LABEL
    from .refs import ONTOLOGY_ANCHOR
    version = (graph.nodes.get((ARCHETYPE_LABEL, ONTOLOGY_ANCHOR))
               or {}).get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        return 0
    return version


def read_dependency(config, name):
    """(Checkout, None) when the dependency's checkout can be read, else
    (None, a designer-facing problem)."""
    from .proposal import base_identity
    from .refs import kb_name
    from .restore import read_export

    path = dependency_path(config, name)
    if path is None:
        return None, (
            f"Attempted to reach dependency '{name}'. Failed due to: no "
            f"path is configured for it — add {settings_key(name)}=<path "
            "to its checkout> to this knowledge base's .env.")
    try:
        graph = read_export(path / "graph" / "export")
    except (FileNotFoundError, ValueError, OSError) as exc:
        return None, (
            f"Attempted to read dependency '{name}' at {path}. Failed due "
            f"to: {exc}. Check the path in .env and that the checkout "
            "carries a committed backup (graph/export).")
    return Checkout(name, path, base_identity(graph), anchor_sequence(graph),
                    kb_name(graph, path), graph), None


def _short(value):
    return str(value or "")[:12] or "none"


def resolution_verdicts(delta, scratch, config):
    """The gate reads the dependency's backup: every [Knowledge Base Dependency] the
    round touches must be pinned at what its checkout holds (identity
    and sequence) and carry the name the checkout declares; every
    [Citizen Bookmark] the round touches — and every bookmark of a dependency
    the round re-pins — must cite a citizen that exists there. A
    dependency the gate cannot reach refuses for the rows that touch
    it: a round may not cite what cannot be checked."""
    verdicts = []
    dependency, bookmark = KERNEL_DEPENDENCY_LABEL, KERNEL_BOOKMARK_LABEL
    touched_deps = {name for name in _touched(delta, dependency)
                    if (dependency, name) in scratch.nodes}
    resolves_in = {}
    for edge in scratch.edges:
        if edge.type == RESOLVES_IN_EDGE and edge.from_label == bookmark \
                and edge.to_label == dependency:
            resolves_in[edge.from_name] = edge.to_name
    touched_bms = {name for name in _touched(delta, bookmark)
                   if (bookmark, name) in scratch.nodes}
    for edge in delta.edges_added:
        if edge.type == RESOLVES_IN_EDGE and edge.from_label == bookmark \
                and (bookmark, edge.from_name) in scratch.nodes:
            touched_bms.add(edge.from_name)
    # a re-pin re-resolves every bookmark living in that dependency
    for name, dep in resolves_in.items():
        if dep in touched_deps and (bookmark, name) in scratch.nodes:
            touched_bms.add(name)
    needed = set(touched_deps)
    needed |= {resolves_in[name] for name in touched_bms
               if name in resolves_in}
    checkouts = {}
    for name in sorted(needed, key=str):
        if (dependency, name) not in scratch.nodes:
            continue  # the structural gate names an unpinned dependency
        checkout, problem = read_dependency(config, name)
        if checkout is None:
            verdicts.append(Verdict(
                code="dependency-unreachable",
                subject=CitizenRef(dependency, name),
                message=(str(problem) + " A round that touches a dependency "
                         "or its bookmarks must be able to read it."),
                remedy=(f"Add {settings_key(name)}=<path> to .env, or "
                        "check the path it names."),
                data={"settings_key": settings_key(name)}))
            continue
        checkouts[name] = checkout
        if name not in touched_deps:
            continue
        props = scratch.nodes[(dependency, name)] or {}
        if checkout.kb != name:
            verdicts.append(Verdict(
                code="dependency-name-mismatch",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to pin dependency '{name}' from its "
                    f"checkout at {checkout.path}. Failed due to: that "
                    f"checkout declares itself '{checkout.kb}' — a "
                    "dependency entry is named for the knowledge base it "
                    "pins. Rename the entry, or point "
                    f"{settings_key(name)} at the right checkout."),
                remedy=(f"Rename the entry, or point {settings_key(name)} "
                        "at the right checkout."),
                data={"declared": checkout.kb, "path": str(checkout.path)}))
        edition, sequence = props.get("edition"), props.get("sequence")
        if edition != checkout.identity or sequence != checkout.sequence:
            verdicts.append(Verdict(
                code="dependency-edition-mismatch",
                subject=CitizenRef(dependency, name),
                message=(
                    f"Attempted to pin dependency '{name}' at edition "
                    f"{_short(edition)} (sequence {sequence}). Failed due "
                    f"to: its checkout at {checkout.path} is at edition "
                    f"{_short(checkout.identity)} (sequence "
                    f"{checkout.sequence}) — check out the ref the pin "
                    "names, or re-pin to what is there (python -m graph "
                    "dependencies prints it)."),
                remedy=("Check out the ref the pin names, or re-pin to the "
                        "checkout's edition and sequence."),
                data={"pinned": {"edition": edition, "sequence": sequence},
                      "checkout": {"edition": checkout.identity,
                                   "sequence": checkout.sequence,
                                   "path": str(checkout.path)}}))
    for name in sorted(touched_bms, key=str):
        dep = resolves_in.get(name)
        if dep is None or dep not in checkouts:
            continue  # unresolved is structural; unreachable named above
        props = scratch.nodes[(bookmark, name)] or {}
        cited = (props.get("citizen_label"), props.get("citizen_name"))
        if _blank(cited[0]) or _blank(cited[1]):
            continue  # the structural gate names an incomplete bookmark
        checkout = checkouts[dep]
        if cited not in checkout.graph.nodes:
            verdicts.append(Verdict(
                code="bookmark-target-missing",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark ({cited[0]}) '{cited[1]}' in "
                    f"dependency '{dep}'. Failed due to: no such citizen "
                    f"in its checkout at {checkout.path} (edition "
                    f"{_short(checkout.identity)}, sequence "
                    f"{checkout.sequence}) — check the label and name, or "
                    "the edition the dependency is pinned at."),
                remedy=("Check the cited label and name, or the edition "
                        "the dependency is pinned at."),
                data={"dependency": dep, "citizen_label": cited[0],
                      "citizen_name": cited[1],
                      "checkout": {"edition": checkout.identity,
                                   "sequence": checkout.sequence}}))
    return verdicts


# -- drift: is a pin behind its checkout? -----------------------------------


def drift_rows(graph, config):
    """One row per [Knowledge Base Dependency] on the graph: its pin, what its checkout
    holds now, and a status — held, behind (the checkout differs from
    the pin), or unreachable."""
    from .report import ref_key

    rows = []
    for (label, name), props in sorted(graph.nodes.items(), key=str):
        if label != KERNEL_DEPENDENCY_LABEL:
            continue
        props = props or {}
        row = {"dependency": name, "intent": props.get("intent"),
               "pinned": {"edition": props.get("edition"),
                          "sequence": props.get("sequence")}}
        checkout, problem = read_dependency(config, name)
        if checkout is None:
            row.update(current=None, status="unreachable",
                       code="dependency-unreachable", problem=str(problem))
        else:
            row["current"] = {"edition": checkout.identity,
                              "sequence": checkout.sequence,
                              "path": str(checkout.path)}
            held = (checkout.identity == props.get("edition")
                    and checkout.sequence == props.get("sequence"))
            row.update(status="held" if held else "behind",
                       code="dependency-held" if held
                       else "dependency-pin-behind")
        row["ref"] = ref_key(row["code"])
        rows.append(row)
    return rows


def drift_advisories(graph, config, skip=()):
    """The behind-pin warning every round hears: an ADVISORY per
    dependency whose checkout differs from its pin or cannot be reached
    (never a refusal — a re-pin round moves the pin). `skip` names
    dependencies already refused by name this round."""
    from .report import ADVISORY

    advisories = []
    for row in drift_rows(graph, config):
        name = row["dependency"]
        if row["status"] == "held" or name in skip:
            continue
        if row["status"] == "unreachable":
            message = row["problem"] + (" Rounds that do not touch it "
                                        "proceed; its bookmarks cannot be "
                                        "re-checked until it is reachable.")
            remedy = f"Add {settings_key(name)}=<path> to .env."
        else:
            pinned, current = row["pinned"], row["current"]
            message = (
                f"Dependency '{name}' is pinned at sequence "
                f"{pinned['sequence']} (edition {_short(pinned['edition'])}) "
                f"but its checkout at {current['path']} is at sequence "
                f"{current['sequence']} (edition "
                f"{_short(current['edition'])}) — the pin is behind. A "
                "re-pin round moves it; every bookmark living there is "
                "re-checked at that gate.")
            remedy = ("Re-pin in a round of its own (edition and sequence "
                      "from python -m graph dependencies), or check out "
                      "the pinned ref.")
        advisories.append(Verdict(
            code=row["code"], severity=ADVISORY, message=message,
            remedy=remedy, subject=CitizenRef(KERNEL_DEPENDENCY_LABEL, name),
            data={"pinned": row["pinned"], "current": row["current"]}))
    return advisories


def dependencies_report(base_dir, rows, branch=None):
    from .report import record_header
    doc = record_header(base_dir, "dependencies-report", branch)
    doc["dependencies"] = rows
    doc["passed"] = all(row["status"] == "held" for row in rows)
    return doc


def render_report(doc):
    rows = doc["dependencies"]
    if not rows:
        return "No dependencies pinned."
    lines = []
    for row in rows:
        pinned = row["pinned"]
        head = (f"{row['status']:<11} {row['dependency']} ({row['intent']}) "
                f"— pinned at sequence {pinned['sequence']} "
                f"(edition {_short(pinned['edition'])})")
        if row["status"] == "unreachable":
            lines.append(f"{head}: {row['problem']}")
        else:
            current = row["current"]
            lines.append(f"{head}; checkout at {current['path']} is at "
                         f"sequence {current['sequence']} (edition "
                         f"{_short(current['edition'])})")
    verdict = ("every pin holds" if doc["passed"]
               else "a pin is behind or its checkout cannot be reached")
    return "\n".join(lines) + f"\nDependencies: {verdict}."
