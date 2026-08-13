"""Visibility lenses: who may see which graph elements.

Visibility classes are the only permission-bearing unit — graph
elements join classes; per-element rules never scale. Groups nest, and
an individual is a size-1 group. Verdicts are authored on
(group x class): allows are additive; denies are legal only against
FLAT classes (never a class that includes: others — the ruled rule).
Posture is fixed per lens kind, never a free switch: knowledge classes
assume DENY (an element in a knowledge class is visible only through a
grant; an element in no knowledge class is not knowledge-gated and
stays visible — universal mechanics), masking classes assume ALLOW
(their elements stay until a lens names the class as a mask).

A lens is the fold of a subject's groups compiled into resolved
hidden-element sets — a machine layer, never authored. Enforcement
happens at the element-access layer of the in-memory GraphData:
apply_lens returns a NEW graph that never yields a hidden element, so
edges, paths, and aggregates stay coherent (an edge survives only if
both its endpoints do — strip_derived in graph/extract.py is the
ur-lens precedent). The caller re-derives machine layers over the
lensed graph afterward; this module never derives. Super admin is NO
lens applied — an enforcement bypass, never a subject granted
everything.

explain() re-evaluates unfolded, naming the class, the deciding
verdict or posture, and the grant that WOULD open a blocked element —
the fold-down's known loss, designed in from day one. require() is a
consumer's build-time declaration check, not a framework.

Declarations live on the graph as Visibility Group / Visibility Class
citizens, read with declarations_from_graph (the visibility lens design is where they reside; the file
surface retired at the declaration-surface retirement). A plain mapping is the in-memory form. Pure
logic throughout — no driver.
"""

from dataclasses import dataclass

from .extract import GraphData

KNOWLEDGE = "knowledge"
MASKING = "masking"
CLASS_KINDS = (KNOWLEDGE, MASKING)
ALLOW = "allow"
DENY = "deny"
VERDICT_WORDS = (ALLOW, DENY)

# The kernel's visibility citizens (the visibility lens design is where they reside). Named Visibility
# Group, not Group — boundary rule 6 caught the bare name colliding
# with a project's own domain vocabulary (a consuming project had already claimed the bare name).
GROUP_LABEL = "Visibility Group"
CLASS_LABEL = "Visibility Class"

# Q2 (owner-ruled): subject-facing refusals are uniform and name
# nothing — indistinguishable from the thing not existing. Surfaces
# reuse this exact string so no wording variant becomes an oracle.
REDACTED_REFUSAL = "Nothing by that name that you can see."

_SECTIONS = ("groups", "classes", "membership", "verdicts")


@dataclass(frozen=True)
class Declarations:
    """The validated declaration surface: who is grouped how, which
    classes exist, which elements join them, and the authored
    verdicts. Everything downstream reads only this."""
    groups: dict        # group -> tuple of member group names
    classes: dict       # class -> {kind, labels, types, includes}
    node_members: dict  # class -> frozenset of (label, name)
    edge_members: dict  # class -> frozenset of
    #                     (type, from label, from name, to label, to name)
    verdicts: tuple     # of (group, class, verdict word) triples


def _cycle_in(names, neighbors_of):
    """First cycle found in a name -> neighbors mapping, as the list of
    names closing the loop, or None."""
    visiting, done = set(), set()

    def visit(name, trail):
        if name in done:
            return None
        if name in visiting:
            return trail[trail.index(name):] + [name]
        visiting.add(name)
        for nxt in neighbors_of(name):
            found = visit(nxt, trail + [name])
            if found:
                return found
        visiting.discard(name)
        done.add(name)
        return None

    for name in names:
        found = visit(name, [])
        if found:
            return found
    return None


def load_declarations(source, origin=None):
    """Validate one declaration surface.

    Accepts an already-validated Declarations (returned as-is) or a
    plain mapping. Declarations live on the graph as citizens (the declaration-surface retirement
    retired the file surface — read them with declarations_from_graph);
    a mapping is the in-memory form. Every validation problem is
    collated into one refusal — never a fix-one-fail-again loop.
    """
    if isinstance(source, Declarations):
        return source
    if isinstance(source, dict):
        data = source
        origin = origin or "the supplied declarations"
    else:
        raise ValueError(
            "Attempted to load visibility declarations from "
            f"{source!r}. Failed due to: declarations live on the "
            "graph as Visibility Group / Visibility Class citizens — "
            "read them with declarations_from_graph(graph), or supply "
            "an in-memory mapping. The file surface is retired.")
    if not isinstance(data, dict):
        raise ValueError(
            f"Attempted to load the visibility declarations from "
            f"{origin}. Failed due to: the root must be a mapping "
            f"holding the sections {', '.join(_SECTIONS)}.")

    problems = []
    for section in data:
        if section not in _SECTIONS:
            problems.append(
                f"unrecognized section '{section}' — the declarations "
                f"hold only {', '.join(_SECTIONS)}")

    # -- groups: nesting via members; an individual is a size-1 group --
    groups = {}
    for name, spec in (data.get("groups") or {}).items():
        spec = spec or {}
        if not isinstance(spec, dict):
            problems.append(
                f"group '{name}' must be a mapping — empty for a leaf "
                "(an individual is a size-1 group), or with members: "
                "listing the groups it contains")
            continue
        groups[name] = tuple(str(m) for m in spec.get("members") or ())
    for name, members in groups.items():
        for member in members:
            if member not in groups:
                problems.append(
                    f"group '{name}' lists an unknown member group "
                    f"'{member}' — every member must itself be declared "
                    "under groups:")
    cycle = _cycle_in(groups, lambda g: [m for m in groups.get(g, ())
                                         if m in groups])
    if cycle:
        problems.append(
            "group membership runs in a circle: "
            + " -> ".join(cycle)
            + " — break the loop; a group can never contain itself")

    # -- classes: the only permission-bearing unit ---------------------
    classes = {}
    for name, spec in (data.get("classes") or {}).items():
        spec = spec or {}
        if not isinstance(spec, dict):
            problems.append(
                f"class '{name}' must be a mapping with at least kind:")
            continue
        kind = spec.get("kind")
        if kind not in CLASS_KINDS:
            problems.append(
                f"class '{name}' has kind '{kind}' — every class "
                f"declares kind: {' or '.join(CLASS_KINDS)}")
        classes[name] = {
            "kind": kind,
            "labels": tuple(str(l) for l in spec.get("labels") or ()),
            "types": tuple(str(t) for t in spec.get("types") or ()),
            "includes": tuple(str(i) for i in spec.get("includes") or ()),
        }
    for name, spec in classes.items():
        for parent in spec["includes"]:
            if parent not in classes:
                problems.append(
                    f"class '{name}' includes an unknown class "
                    f"'{parent}' — every included class must be declared "
                    "under classes:")
        if spec["includes"] and spec["kind"] == MASKING:
            problems.append(
                f"class '{name}' is a masking class with includes: — "
                "grant-inheritance belongs to knowledge classes only; "
                "a mask names each masking class directly")
        if spec["kind"] == KNOWLEDGE:
            for parent in spec["includes"]:
                if classes.get(parent, {}).get("kind") == MASKING:
                    problems.append(
                        f"knowledge class '{name}' includes the masking "
                        f"class '{parent}' — grant-inheritance is "
                        "defined between knowledge classes only; a "
                        "masking class is applied by naming it in a "
                        "mask, never granted")
    cycle = _cycle_in(classes,
                      lambda c: [p for p in classes.get(c, {})
                                 .get("includes", ()) if p in classes])
    if cycle:
        problems.append(
            "class includes: run in a circle: "
            + " -> ".join(cycle)
            + " — break the loop; a class can never include itself")

    # -- membership: explicit element keys per class -------------------
    node_members, edge_members = {}, {}
    for cls, entry in (data.get("membership") or {}).items():
        if cls not in classes:
            problems.append(
                f"membership names an unknown class '{cls}' — declare "
                "it under classes: first")
            continue
        entry = entry or {}
        if not isinstance(entry, dict):
            problems.append(
                f"membership for '{cls}' must be a mapping with nodes: "
                "and/or edges:")
            continue
        nodes = set()
        for key in entry.get("nodes") or []:
            if not (isinstance(key, (list, tuple)) and len(key) == 2):
                problems.append(
                    f"membership for '{cls}' holds a node key {key!r} — "
                    "a node key is [label, name]")
                continue
            nodes.add((str(key[0]), str(key[1])))
        edges = set()
        for key in entry.get("edges") or []:
            if not (isinstance(key, (list, tuple)) and len(key) == 5):
                problems.append(
                    f"membership for '{cls}' holds an edge key {key!r} — "
                    "an edge key is [type, from label, from name, "
                    "to label, to name]")
                continue
            edges.add(tuple(str(part) for part in key))
        if nodes:
            node_members[cls] = frozenset(nodes)
        if edges:
            edge_members[cls] = frozenset(edges)

    # -- verdicts: (group x class), allow additive, deny flat-only -----
    verdicts = []
    for index, entry in enumerate(data.get("verdicts") or [], start=1):
        if not isinstance(entry, dict):
            problems.append(
                f"verdict {index} must be a mapping with group, class, "
                "and verdict")
            continue
        group = entry.get("group")
        cls = entry.get("class")
        word = entry.get("verdict")
        if group not in groups:
            problems.append(
                f"verdict {index} names an unknown group '{group}'")
        if cls not in classes:
            problems.append(
                f"verdict {index} names an unknown class '{cls}'")
        if word not in VERDICT_WORDS:
            problems.append(
                f"verdict {index} rules '{word}' — a verdict is "
                f"{' or '.join(VERDICT_WORDS)}")
        if cls in classes:
            if classes[cls]["kind"] == MASKING:
                problems.append(
                    f"verdict {index} targets the masking class '{cls}' "
                    "— verdicts govern knowledge classes; masking is "
                    "applied by naming the class in a lens's mask")
            elif word == DENY and classes[cls]["includes"]:
                problems.append(
                    f"verdict {index} denies '{cls}', which includes "
                    f"{', '.join(repr(i) for i in classes[cls]['includes'])}"
                    " — denies are legal only against FLAT classes; "
                    "deny each included class directly instead")
        if group in groups and cls in classes and word in VERDICT_WORDS:
            verdicts.append((group, cls, word))

    if problems:
        raise ValueError(
            f"Attempted to load the visibility declarations from "
            f"{origin}. Failed due to:\n  - " + "\n  - ".join(problems))
    return Declarations(groups=groups, classes=classes,
                        node_members=node_members,
                        edge_members=edge_members,
                        verdicts=tuple(verdicts))


def declarations_from_graph(graph):
    """The declaration surface read FROM canon citizens (the visibility lens design
    residence): Visibility Group / Visibility Class nodes; MEMBER_OF,
    ALLOWED, DENIED, INCLUDES, IN_CLASS edges. Produces the same
    validated Declarations the YAML surface does — one lint, two
    surfaces. Edge-elements join classes by selectors (types:) or the
    YAML surface only: an edge cannot point at an edge, so IN_CLASS
    carries node membership alone."""
    data = {"groups": {}, "classes": {}, "membership": {}, "verdicts": []}
    for (label, name), props in sorted(graph.nodes.items(),
                                       key=lambda i: (i[0][0],
                                                      str(i[0][1]))):
        props = props or {}
        if label == GROUP_LABEL:
            data["groups"][str(name)] = {}
        elif label == CLASS_LABEL:
            spec = {"kind": props.get("kind")}
            for selector in ("labels", "types"):
                value = props.get(selector)
                if value:
                    spec[selector] = (list(value)
                                      if isinstance(value, (list, tuple))
                                      else [value])
            data["classes"][str(name)] = spec
    for edge in sorted(set(graph.edges),
                       key=lambda e: (e.type, str(e.from_name),
                                      str(e.to_name))):
        if edge.type == "MEMBER_OF" and edge.from_label == GROUP_LABEL \
                and edge.to_label == GROUP_LABEL:
            data["groups"].setdefault(str(edge.to_name), {}) \
                .setdefault("members", []).append(str(edge.from_name))
        elif edge.type in ("ALLOWED", "DENIED") \
                and edge.from_label == GROUP_LABEL \
                and edge.to_label == CLASS_LABEL:
            data["verdicts"].append(
                {"group": str(edge.from_name),
                 "class": str(edge.to_name),
                 "verdict": ALLOW if edge.type == "ALLOWED" else DENY})
        elif edge.type == "INCLUDES" \
                and edge.from_label == CLASS_LABEL \
                and edge.to_label == CLASS_LABEL:
            data["classes"].setdefault(
                str(edge.from_name), {"kind": None}) \
                .setdefault("includes", []).append(str(edge.to_name))
        elif edge.type == "IN_CLASS" and edge.to_label == CLASS_LABEL:
            data["membership"].setdefault(str(edge.to_name), {}) \
                .setdefault("nodes", []) \
                .append([edge.from_label, str(edge.from_name)])
    return load_declarations(
        data, origin="the graph's visibility citizens")


def fold(declarations, subject):
    """The subject's transitive group set, subject included. Groups
    nest by listing member groups, so a verdict authored on any folded
    group binds the subject. An individual is a size-1 group."""
    decls = load_declarations(declarations)
    if subject not in decls.groups:
        raise ValueError(
            f"Attempted to fold the groups of '{subject}'. Failed due "
            "to: no group by that name is declared — an individual is "
            "declared as a size-1 group under groups:.")
    containers = {}
    for group, members in decls.groups.items():
        for member in members:
            containers.setdefault(member, set()).add(group)
    folded, frontier = {subject}, [subject]
    while frontier:
        for parent in containers.get(frontier.pop(), ()):
            if parent not in folded:
                folded.add(parent)
                frontier.append(parent)
    return frozenset(folded)


# -- compilation: declarations + one graph -> resolved hidden sets ------


@dataclass(frozen=True)
class Lens:
    """Resolved hidden-element sets for one (subject, mask) pair,
    compiled against one graph — a machine layer, never authored. An
    empty lens (no subject, no mask) is the identity: super admin is
    no lens applied."""
    subject: object
    mask: tuple
    hidden_nodes: frozenset  # of (label, name)
    hidden_edges: frozenset  # of Edge

    @property
    def is_identity(self):
        return not self.hidden_nodes and not self.hidden_edges


def _node_classes(decls, key):
    """Every class a node key belongs to: labels: selectors plus
    explicit membership."""
    classes = {name for name, spec in decls.classes.items()
               if key[0] in spec["labels"]}
    classes |= {name for name, members in decls.node_members.items()
                if key in members}
    return classes


def _edge_classes(decls, identity):
    """Every class an edge identity (type, from label, from name,
    to label, to name) belongs to: types: selectors plus explicit
    membership. Edge membership is never inferred from endpoint
    labels — an edge joins a class explicitly or by its type."""
    classes = {name for name, spec in decls.classes.items()
               if identity[0] in spec["types"]}
    classes |= {name for name, members in decls.edge_members.items()
                if identity in members}
    return classes


def _includes_closure(decls, cls):
    """Every class transitively included by cls (grant-inheritance
    downward: being allowed cls includes these)."""
    closure, frontier = set(), [cls]
    while frontier:
        for parent in decls.classes[frontier.pop()]["includes"]:
            if parent not in closure:
                closure.add(parent)
                frontier.append(parent)
    return closure


def _granted(decls, folded):
    """The classes the folded groups hold allows on, closed over
    includes: — being allowed a class INCLUDES every class it
    includes, transitively."""
    granted = {cls for grp, cls, word in decls.verdicts
               if word == ALLOW and grp in folded}
    for cls in tuple(granted):
        granted |= _includes_closure(decls, cls)
    return frozenset(granted)


def _denied(decls, folded):
    return frozenset(cls for grp, cls, word in decls.verdicts
                     if word == DENY and grp in folded)


def _hidden(decls, classes, subject, granted, denied, masked):
    """One element's fate under the compiled lens. Masking first
    (assume-allow: removed only when masked); then knowledge
    (assume-deny: an element in any knowledge class needs a grant and
    no deny; an element in none is not knowledge-gated)."""
    if classes & masked:
        return True
    if subject is None:
        return False
    knowledge = {cls for cls in classes
                 if decls.classes[cls]["kind"] == KNOWLEDGE}
    if not knowledge:
        return False
    if knowledge & denied:
        return True
    return not (knowledge & granted)


def compile_lens(declarations, graph, subject=None, mask=(), without=()):
    """Compile the resolved lens for a subject and/or a mask against
    one graph. subject=None with an empty mask is the identity lens —
    no lens applied. The mask may only name masking classes; knowledge
    access is granted by verdicts, never switched off here.

    Session activation: subject may be one group name (the
    normal fold) or an iterable of group names — the hats worn this
    session, each closed upward through its own containers. `without`
    subtracts named groups AFTER the fold: "me, minus Pocket
    Universe-1234" is subject='me', without=('pocket-universe-1234',).
    An empty active set hides every knowledge-gated element — honest
    assume-deny, never an error."""
    decls = load_declarations(declarations)
    mask = tuple(mask)
    without = tuple(without)
    unknown = [name for name in without if name not in decls.groups]
    if unknown:
        raise ValueError(
            "Attempted to compile a lens without the group(s) "
            f"{', '.join(repr(n) for n in unknown)}. Failed due to: no "
            "such group is declared — a subtracted group must exist, or "
            "the subtraction silently protects nothing.")
    problems = []
    for name in mask:
        if name not in decls.classes:
            problems.append(f"the mask names an unknown class '{name}'")
        elif decls.classes[name]["kind"] != MASKING:
            problems.append(
                f"the mask names '{name}', a "
                f"{decls.classes[name]['kind']} class — only masking "
                "classes may be masked; knowledge access is granted by "
                "verdicts, not switched off here")
    if problems:
        raise ValueError(
            f"Attempted to compile a lens with the mask "
            f"({', '.join(mask)}). Failed due to:\n  - "
            + "\n  - ".join(problems))
    granted = denied = frozenset()
    if subject is not None:
        if isinstance(subject, str):
            folded = fold(decls, subject)
        else:
            names = tuple(subject)
            folded = frozenset().union(
                *(fold(decls, name) for name in names)) \
                if names else frozenset()
            subject = names
        folded = frozenset(folded) - frozenset(without)
        granted = _granted(decls, folded)
        denied = _denied(decls, folded)
    masked = frozenset(mask)
    folded_set = folded if subject is not None else frozenset()

    def _vocab_hidden(key):
        # Q1 (owner-ruled — the A/B/C case): under a subject lens the
        # visibility vocabulary shows only what the fold touches —
        # your groups, and the classes your keys open. Other groups
        # and classes do not exist for you. No-lens and mask-only
        # lenses see the whole vocabulary.
        if subject is None:
            return False
        label, name = key
        if label == GROUP_LABEL:
            return name not in folded_set
        if label == CLASS_LABEL:
            return name not in granted
        return False

    hidden_nodes = frozenset(
        key for key in graph.nodes
        if _vocab_hidden(key)
        or _hidden(decls, _node_classes(decls, key), subject, granted,
                   denied, masked))
    hidden_edges = frozenset(
        edge for edge in graph.edges
        if _hidden(decls,
                   _edge_classes(decls, (edge.type, edge.from_label,
                                         edge.from_name, edge.to_label,
                                         edge.to_name)),
                   subject, granted, denied, masked))
    return Lens(subject=subject, mask=mask, hidden_nodes=hidden_nodes,
                hidden_edges=hidden_edges)


def apply_lens(graph, lens):
    """A NEW GraphData holding only what the lens permits: hidden
    nodes gone, and an edge kept only if BOTH its endpoints survive
    AND the edge itself is not hidden (coherence rule 1 — a lensed
    graph never yields a hidden element, so paths and aggregates stay
    coherent). Never mutates the input. Machine layers are NOT
    recomputed here: the caller re-derives over the lensed graph
    afterward, exactly as after strip_derived."""
    lensed = GraphData()
    for key, props in graph.nodes.items():
        if key not in lens.hidden_nodes:
            lensed.nodes[key] = dict(props)
    lensed.edges = [
        edge for edge in graph.edges
        if edge not in lens.hidden_edges
        and (edge.from_label, edge.from_name) in lensed.nodes
        and (edge.to_label, edge.to_name) in lensed.nodes]
    return lensed


# -- explain: the unfolded re-evaluation, in owner-facing prose ---------


def _would_open(decls, cls, subject, deny_lifted=False):
    """The grant that WOULD open a blocked class for the subject."""
    includers = sorted(name for name in decls.classes
                       if cls in _includes_closure(decls, name))
    via = (" (or on " + ", ".join(f"'{name}'" for name in includers)
           + ", which includes it)") if includers else ""
    tail = (" once the deny is lifted." if deny_lifted else ".")
    return (f"An allow on '{cls}'{via} for any of '{subject}''s "
            f"groups would open it{tail}")


def _opening_grant(decls, folded, cls):
    """The (group, allowed class) pair that opens cls for the folded
    groups — a direct allow first, else one that reaches cls through
    includes. None if nothing opens it."""
    for grp, allowed, word in decls.verdicts:
        if word == ALLOW and grp in folded and allowed == cls:
            return grp, allowed
    for grp, allowed, word in decls.verdicts:
        if word == ALLOW and grp in folded \
                and cls in _includes_closure(decls, allowed):
            return grp, allowed
    return None


def explain(declarations, subject, element_key, candid=True):
    """Why one element is visible or hidden to a subject — the
    unfolded re-evaluation, in owner-facing prose. element_key is a
    node key (label, name) or an edge key (type, from label, from
    name, to label, to name). The trace names the class(es) the
    element belongs to, the verdict or posture that decided, and — on
    a block — the grant that WOULD open it."""
    decls = load_declarations(declarations)
    key = tuple(element_key)
    if len(key) == 2:
        described = f"The {key[0]} node '{key[1]}'"
        classes = _node_classes(decls, key)
    elif len(key) == 5:
        described = (f"The {key[0]} edge from {key[1]} '{key[2]}' to "
                     f"{key[3]} '{key[4]}'")
        classes = _edge_classes(decls, key)
    else:
        raise ValueError(
            f"Attempted to explain visibility for the element {key!r}. "
            "Failed due to: an element key is [label, name] for a node "
            "or [type, from label, from name, to label, to name] for "
            "an edge.")
    folded = granted = denied = frozenset()
    if subject is not None:
        folded = fold(decls, subject)
        granted = _granted(decls, folded)
        denied = _denied(decls, folded)
    if not candid:
        # Q2 (owner-ruled): candid explanations are a privilege carried
        # by the vocabulary grant; this is the subject-facing surface —
        # one uniform refusal that names nothing, indistinguishable
        # from the thing not existing (the smaller-world stance).
        if subject is not None:
            if len(key) == 2 and key[0] == GROUP_LABEL \
                    and key[1] not in folded:
                return REDACTED_REFUSAL
            if len(key) == 2 and key[0] == CLASS_LABEL \
                    and key[1] not in granted:
                return REDACTED_REFUSAL
            if classes and _hidden(decls, classes, subject, granted,
                                   denied, frozenset()):
                return REDACTED_REFUSAL
        return "Visible."
    if not classes:
        return (f"{described} belongs to no visibility class — it is "
                "not knowledge-gated, so every subject sees it.")
    lines = [described + " belongs to the visibility class(es): "
             + ", ".join(f"'{cls}' ({decls.classes[cls]['kind']})"
                         for cls in sorted(classes)) + "."]
    if subject is not None:
        lines.append(f"'{subject}' folds to the group(s): "
                     + ", ".join(sorted(folded)) + ".")
    denied_classes = sorted(
        c for c in classes
        if any(word == DENY and grp in folded and target == c
               for grp, target, word in decls.verdicts))
    for cls in sorted(classes):
        spec = decls.classes[cls]
        if spec["kind"] == MASKING:
            lines.append(
                f"- '{cls}' is a masking class: assumed visible; its "
                f"elements disappear only under a lens whose mask "
                f"names '{cls}'.")
            continue
        if subject is None:
            lines.append(
                f"- '{cls}' is a knowledge class (assume-deny); with "
                "no subject there is no knowledge lens to apply.")
            continue
        deny_group = next((grp for grp, c, word in decls.verdicts
                           if word == DENY and grp in folded
                           and c == cls), None)
        if deny_group is not None:
            lines.append(
                f"- '{cls}': HIDDEN — the deny for group "
                f"'{deny_group}' on '{cls}' removes its elements (a "
                "deny overrides any allow). "
                + _would_open(decls, cls, subject, deny_lifted=True))
            continue
        # honesty: a deny on ANY of the element's other knowledge
        # classes keeps the element hidden no matter what opens THIS
        # class — the trace must never promise a grant that would not
        # actually reveal the element
        co_denied = [c for c in denied_classes if c != cls]
        caveat = ("" if not co_denied else
                  " Even so, the deny on "
                  + ", ".join(f"'{c}'" for c in co_denied)
                  + " keeps this element hidden until lifted.")
        opener = _opening_grant(decls, folded, cls)
        if opener:
            grp, via = opener
            how = (f"the allow for group '{grp}' on '{cls}'"
                   if via == cls else
                   f"the allow for group '{grp}' on '{via}', which "
                   f"includes '{cls}'")
            lines.append(f"- '{cls}': OPEN — {how}." + caveat)
        else:
            lines.append(
                f"- '{cls}': HIDDEN — knowledge classes assume deny, "
                f"and no folded group holds an allow that reaches "
                f"'{cls}'. " + _would_open(decls, cls, subject)
                + caveat)
    if subject is not None:
        hidden = _hidden(decls, classes, subject, granted, denied,
                         frozenset())
        lines.append(f"Under '{subject}''s lens this element is "
                     + ("HIDDEN." if hidden else "visible."))
    return "\n".join(lines)


# -- require: a consumer's build-time declaration check -----------------


def require(declarations, consumer_name, required_classes):
    """A consumer declares the visibility classes its lenses require;
    a missing declaration refuses at BUILD time, naming every missing
    class at once — a misconfigured consumer never runs half-lensed.
    This is a declaration check, not a framework. Returns the
    validated tuple."""
    decls = load_declarations(declarations)
    required = tuple(required_classes)
    missing = [name for name in required if name not in decls.classes]
    if missing:
        raise ValueError(
            f"Attempted to build '{consumer_name}', which requires the "
            "visibility class(es) "
            + ", ".join(f"'{name}'" for name in required)
            + ". Failed due to: no declaration exists for "
            + ", ".join(f"'{name}'" for name in missing)
            + " — declare the class(es) under classes:, or drop the "
            "requirement.")
    return required
