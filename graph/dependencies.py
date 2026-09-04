"""Dependencies and bookmarks: a knowledge base pinning another, and
citing a citizen that lives there (kernel 0.15.0).

A [Dependency] is another knowledge base this one pins to an edition —
the dependency's committed-backup identity hash and event-log sequence
— with an intent (read, or write). A [Bookmark] is a citizen that lives
in a dependency: its knowledge base, label, and name there, and the
edition it was resolved against, with exactly one RESOLVES_IN edge to
its [Dependency]. This knowledge base's own citizens point at a
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
