"""Members and bookmarks: a knowledge base mounting another, and citing
a citizen that lives there (kernel 0.15.0).

A [Member] is a knowledge base this one mounts, pinned to an edition —
the member's committed-backup identity hash and event-log sequence —
with an intent (read, or write). A [Bookmark] is a citizen that lives
in a member: its knowledge base, label, and name there, and the edition
it was resolved against, with exactly one IN_MEMBER edge to its
[Member]. This knowledge base's own citizens point at a bookmark
through their own relation vocabulary. Where a member lives on disk is
settings, never canon.

This module is the delta gate's STRUCTURAL check over the two: required
properties present, the intent one of the two known words, the sequence
a whole number, every touched bookmark mounted on exactly one member
that exists in the round's own graph, and a member never removed while
a bookmark still points at it. Resolution against the member's backup —
does the cited citizen exist at the pinned edition, is the pin stale —
is the next rung's verb.
"""

from .ontology import KERNEL_BOOKMARK_LABEL, KERNEL_MEMBER_LABEL
from .refs import CitizenRef, connection_ref
from .report import Verdict

IN_MEMBER_EDGE = "IN_MEMBER"
INTENTS = ("read", "write")
MEMBER_REQUIRED = ("edition", "sequence", "intent")
# The cited citizen's label and name there ride as citizen_label /
# citizen_name: a property literally named `label` would collide with
# the graph's own row shape (label, name, properties) on every read.
BOOKMARK_REQUIRED = ("member", "citizen_label", "citizen_name", "edition")


def _touched(delta, label):
    names = {name for lbl, name, _ in delta.nodes_added if lbl == label}
    names |= {name for lbl, name, _ in delta.nodes_changed if lbl == label}
    return names


def _blank(value):
    return value is None or value == ""


def gate_verdicts(delta, scratch):
    """Structural verdicts over the members and bookmarks this round
    touches, judged against the round's own graph (scratch = base plus
    the round, so "exists in the base or the same round" is one
    lookup)."""
    verdicts = []
    member, bookmark = KERNEL_MEMBER_LABEL, KERNEL_BOOKMARK_LABEL

    # -- members ----------------------------------------------------------
    for name in sorted(_touched(delta, member), key=str):
        props = scratch.nodes.get((member, name)) or {}
        missing = [prop for prop in MEMBER_REQUIRED if _blank(props.get(prop))]
        if missing:
            verdicts.append(Verdict(
                code="member-incomplete",
                subject=CitizenRef(member, name),
                message=(
                    f"Attempted to mount knowledge base '{name}' as a "
                    f"member. Failed due to: the entry lacks "
                    f"{', '.join(missing)} — a member is pinned to an "
                    "edition (its backup's identity hash and event-log "
                    "sequence) and declares an intent (read or write). "
                    "Add the missing properties in scratch."),
                remedy="Add the missing properties in scratch.",
                data={"missing": missing}))
        intent = props.get("intent")
        if not _blank(intent) and intent not in INTENTS:
            verdicts.append(Verdict(
                code="member-intent-unknown",
                subject=CitizenRef(member, name),
                message=(
                    f"Attempted to mount knowledge base '{name}' with "
                    f"intent '{intent}'. Failed due to: intent is read or "
                    "write, nothing else — read for a member this "
                    "knowledge base only consults, write when a shared "
                    "activity may land rounds there. Set it to one of the "
                    "two in scratch."),
                remedy="Set intent to read or write in scratch.",
                data={"intent": intent}))
        sequence = props.get("sequence")
        if not _blank(sequence) and (isinstance(sequence, bool)
                                     or not isinstance(sequence, int)):
            verdicts.append(Verdict(
                code="member-sequence-invalid",
                subject=CitizenRef(member, name),
                message=(
                    f"Attempted to pin knowledge base '{name}' at sequence "
                    f"{sequence!r}. Failed due to: the sequence is the "
                    "member's event-log number at the pinned edition, a "
                    "whole number. Copy it from the member's applied log."),
                remedy="Set sequence to the member's event-log number at "
                       "the pinned edition.",
                data={"sequence": sequence}))

    # -- bookmarks --------------------------------------------------------
    links = {}
    for edge in scratch.edges:
        if edge.type == IN_MEMBER_EDGE:
            links.setdefault((edge.from_label, edge.from_name), []).append(edge)
    touched = _touched(delta, bookmark)
    for edge in list(delta.edges_added) + list(delta.edges_removed):
        if edge.type == IN_MEMBER_EDGE and edge.from_label == bookmark:
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
                    "names the member knowledge base, the cited citizen's "
                    "label and name there, and the member edition it was "
                    "resolved against. Add the missing properties in "
                    "scratch."),
                remedy="Add the missing properties in scratch.",
                data={"missing": missing}))
        mounted = [edge for edge in links.get(key, [])
                   if edge.to_label == member
                   and (member, edge.to_name) in scratch.nodes]
        if len(mounted) != 1:
            dangling = [edge.to_name for edge in links.get(key, [])
                        if edge not in mounted]
            if not links.get(key):
                why = "it carries no IN_MEMBER edge"
            elif len(mounted) > 1:
                why = (f"it carries {len(mounted)} IN_MEMBER edges "
                       "(exactly one is the rule)")
            else:
                why = ("its IN_MEMBER edge points at "
                       + ", ".join(f"'{d}'" for d in dangling)
                       + ", which is no member in the base or this round")
            verdicts.append(Verdict(
                code="bookmark-unmounted",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark '{name}'. Failed due to: {why} "
                    "— a bookmark lives in exactly one mounted member. "
                    "Author one IN_MEMBER edge to the member's entry "
                    "(mount the member first if it has none)."),
                remedy="Author one IN_MEMBER edge to the member's entry.",
                data={"mounted": [edge.to_name for edge in mounted],
                      "dangling": dangling}))
        elif not _blank(props.get("member")) and \
                props.get("member") != mounted[0].to_name:
            verdicts.append(Verdict(
                code="bookmark-member-mismatch",
                subject=CitizenRef(bookmark, name),
                message=(
                    f"Attempted to bookmark '{name}' in member "
                    f"'{props.get('member')}'. Failed due to: its IN_MEMBER "
                    f"edge mounts it on '{mounted[0].to_name}' — the "
                    "member named on the bookmark and the member it is "
                    "mounted on must agree. Fix whichever is wrong."),
                remedy="Make the bookmark's member and its IN_MEMBER "
                       "target agree.",
                data={"member": props.get("member"),
                      "mounted": mounted[0].to_name}))

    # -- the edge itself, and a member still cited --------------------------
    for edge in delta.edges_added:
        if edge.type == IN_MEMBER_EDGE and (edge.from_label != bookmark
                                            or edge.to_label != member):
            verdicts.append(Verdict(
                code="in-member-misused",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to author IN_MEMBER from ({edge.from_label}) "
                    f"'{edge.from_name}' to ({edge.to_label}) "
                    f"'{edge.to_name}'. Failed due to: IN_MEMBER runs from a "
                    "bookmark to the member it lives in, nothing else — a "
                    "knowledge base's own citizens point at a bookmark "
                    "through their own relation vocabulary. Delete the "
                    "edge in scratch and author the intended one."),
                remedy="Delete the edge in scratch and author the "
                       "intended one."))
    removed_members = {name for lbl, name, _ in delta.nodes_removed
                       if lbl == member}
    for name in sorted(removed_members, key=str):
        cited_by = sorted(str(key[1]) for key, edges in links.items()
                          for edge in edges
                          if edge.to_label == member and edge.to_name == name
                          and key in scratch.nodes)
        if cited_by:
            verdicts.append(Verdict(
                code="member-still-cited",
                subject=CitizenRef(member, name),
                message=(
                    f"Attempted to unmount knowledge base '{name}'. Failed "
                    f"due to: {len(cited_by)} bookmark(s) still live there "
                    f"({', '.join(cited_by[:5])}"
                    f"{', …' if len(cited_by) > 5 else ''}). Retire those "
                    "bookmarks in the same round, or keep the member."),
                remedy="Retire the bookmarks in the same round, or keep "
                       "the member.",
                data={"bookmarks": cited_by}))
    return verdicts
