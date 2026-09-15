"""Artifacts at the gate (kernel 0.17.0).

An [Artifact] is the thing a person hands over, as canon knows it:
identity is its name; WHERE it is lives on [Artifact Location] rows
behind LOCATED_AT (`scheme`, `address`, `primary`), with
[File Location] the kernel's own kind. Its grade is Completeness as
CONTENT HELD — Cited (name and location only), Attested (a description
and its DEPICTS facts confirmed at the gate), Transcribed (region
receipts, parked) — while VERIFICATION is the location row's own fact
(`verified_fingerprint`, `verified_at_sequence`, `size`), written at
apply for every file location the round touched and read by the
receipts sweep, never folded into the grade. DEPICTS names the
objective contents; an [Interpretation] says what the artifact stands
for to this world, per intent; a [Resolver] binds a location kind to
the procedure that opens it.

This module is the delta gate's check over all of that, and the
apply-time stamp that records what the engine verified.
"""

import hashlib
from pathlib import Path

from .ontology import (ARCHETYPE_LABEL, KERNEL_ARTIFACT_LABEL,
                       KERNEL_ARTIFACT_LOCATION_LABEL, KERNEL_BOOKMARK_LABEL,
                       KERNEL_FILE_LOCATION_LABEL,
                       KERNEL_INTERPRETATION_LABEL, KERNEL_PROCEDURE_LABEL,
                       KERNEL_RESOLVER_LABEL)
from .refs import CitizenRef, connection_ref
from .report import Verdict

LOCATED_AT = "LOCATED_AT"
DEPICTS = "DEPICTS"
SUPERSEDES = "SUPERSEDES"
INTERPRETED_AS = "INTERPRETED_AS"
DRAWS_ON = "DRAWS_ON"
OPENS_WITH = "OPENS_WITH"
ABOUT = "ABOUT"

GRADES = ("Cited", "Attested", "Transcribed")
ROLE_PROP = "role"
PROVENANCE_GRADE_PROP = "provenance_known_at"
EXAMINED_GRADE_PROP = "examined_known_at"
LEGACY_GRADE_PROP = "known_at"


def facet_grades(props):
    """(provenance, examined, legacy_facet): the artifact's two grade
    facets, with a legacy single grade read asymmetrically by what it
    always meant — Cited was metadata-derived (the provenance facet),
    Attested was always eyes-on (the examined facet). The new
    properties win when present; legacy_facet names which facet the
    legacy value was read into, or None."""
    provenance = props.get(PROVENANCE_GRADE_PROP)
    examined = props.get(EXAMINED_GRADE_PROP)
    legacy_facet = None
    if _blank(provenance) and _blank(examined):
        legacy = props.get(LEGACY_GRADE_PROP)
        if not _blank(legacy):
            if legacy == "Attested":
                examined, legacy_facet = legacy, "examined"
            else:
                provenance, legacy_facet = legacy, "provenance"
    return provenance, examined, legacy_facet
ROLES = ("primary", "also-shows")
# the machinery's signature on a derived boilerplate interpretation —
# never authorable by hand; the strip keys on it for the fixpoint
DERIVED_MARKER = "derived_from"
DERIVED_MARKER_VALUE = "primary depiction"
VERIFIED_FINGERPRINT = "verified_fingerprint"
VERIFIED_AT = "verified_at_sequence"
SIZE = "size"


def artifact_labels(graph):
    """[Artifact] and every kind of it through the taxonomy: a citizen
    re-homed under a kind is an artifact to every rule here."""
    kinds = {KERNEL_ARTIFACT_LABEL}
    grew = True
    while grew:
        grew = False
        for edge in graph.edges:
            if edge.type == "SUBTYPE_OF" and edge.from_label == ARCHETYPE_LABEL \
                    and edge.to_label == ARCHETYPE_LABEL \
                    and edge.to_name in kinds and edge.from_name not in kinds:
                kinds.add(edge.from_name)
                grew = True
    return kinds


def location_labels(graph):
    """Every label that is an [Artifact Location] kind: the base and
    everything SUBTYPE_OF it, however deep."""
    kinds = {KERNEL_ARTIFACT_LOCATION_LABEL}
    grew = True
    while grew:
        grew = False
        for edge in graph.edges:
            if edge.type == "SUBTYPE_OF" and edge.from_label == ARCHETYPE_LABEL \
                    and edge.to_label == ARCHETYPE_LABEL \
                    and edge.to_name in kinds and edge.from_name not in kinds:
                kinds.add(edge.from_name)
                grew = True
    return kinds


def _edges(graph, edge_type):
    return [edge for edge in graph.edges if edge.type == edge_type]


def _blank(value):
    return value is None or value == ""


def file_path(base_dir, address):
    """The path a [File Location] names, or None when it reaches outside
    the knowledge base."""
    relative = Path(str(address))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return Path(base_dir) / relative


def touched_artifacts(delta, scratch):
    """The artifacts the round touches, as (label, name) keys — an
    artifact is [Artifact] or any kind of it: added or changed rows, the
    artifact behind any location, depiction, or supersession edge the
    round adds or removes, the artifact behind a location row the round
    touches, and the artifact an added interpretation is ABOUT."""
    artifacts = artifact_labels(scratch)
    keys = {(l, n) for l, n, _ in delta.nodes_added if l in artifacts}
    keys |= {(l, n) for l, n, _ in delta.nodes_changed if l in artifacts}
    kinds = location_labels(scratch)
    touched_rows = {(l, n) for l, n, _ in delta.nodes_added if l in kinds}
    touched_rows |= {(l, n) for l, n, _ in delta.nodes_changed if l in kinds}
    for edge in list(delta.edges_added) + list(delta.edges_removed):
        if edge.type in (LOCATED_AT, DEPICTS, SUPERSEDES) \
                and edge.from_label in artifacts:
            keys.add((edge.from_label, edge.from_name))
        if edge.type == ABOUT and edge.to_label in artifacts:
            keys.add((edge.to_label, edge.to_name))
    for edge in _edges(scratch, LOCATED_AT):
        if (edge.to_label, edge.to_name) in touched_rows \
                and edge.from_label in artifacts:
            keys.add((edge.from_label, edge.from_name))
    return {k for k in keys if k in scratch.nodes}


def gate_verdicts(delta, scratch, base_dir):
    """The artifact rules at the delta gate, collated."""
    verdicts = []
    artifacts = artifact_labels(scratch)
    kinds = location_labels(scratch)
    located = _edges(scratch, LOCATED_AT)
    depicts = _edges(scratch, DEPICTS)
    depicted_by = {}
    for edge in depicts:
        depicted_by.setdefault(edge.from_name, set()).add(
            (edge.to_label, str(edge.to_name)))

    # -- edges only an artifact may author ------------------------------
    for edge in delta.edges_added:
        if edge.type in (LOCATED_AT, DEPICTS, SUPERSEDES) \
                and edge.from_label not in artifacts:
            verdicts.append(Verdict(
                code="artifact-edge-misused",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to author {edge.type} from "
                    f"({edge.from_label}) '{edge.from_name}'. Failed due "
                    f"to: {edge.type} runs from an artifact — what a "
                    "person handed over — nothing else. Delete the edge "
                    "in scratch."),
                remedy="Delete the edge in scratch."))
        elif edge.type == LOCATED_AT and edge.to_label not in kinds:
            verdicts.append(Verdict(
                code="location-kind-unknown",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to locate artifact '{edge.from_name}' at "
                    f"({edge.to_label}) '{edge.to_name}'. Failed due to: "
                    f"'{edge.to_label}' is no location kind — a location "
                    "is an [Artifact Location] row, or a kind declared "
                    "under it through the taxonomy ceremony. Author the "
                    "location as one of those."),
                remedy="Author the location as an [Artifact Location] "
                       "kind."))
        elif edge.type == SUPERSEDES and edge.to_label not in artifacts:
            verdicts.append(Verdict(
                code="artifact-edge-misused",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to record artifact '{edge.from_name}' "
                    f"superseding ({edge.to_label}) '{edge.to_name}'. "
                    "Failed due to: an artifact supersedes an artifact. "
                    "Point the edge at the older artifact."),
                remedy="Point SUPERSEDES at the older artifact."))
        elif edge.type == DEPICTS and (edge.to_label, edge.to_name) \
                not in scratch.nodes:
            verdicts.append(Verdict(
                code="depicts-target-missing",
                subject=connection_ref(edge),
                message=(
                    f"Attempted to record that artifact '{edge.from_name}' "
                    f"depicts ({edge.to_label}) '{edge.to_name}'. Failed "
                    "due to: no such citizen — a depicted thing is a "
                    "citizen of this world (create it here) or a recorded "
                    "omission, never a dangling name."),
                remedy="Create the citizen here, or record the omission."))
        if edge.type == DEPICTS:
            role = dict(edge.props).get(ROLE_PROP)
            if role is not None and role not in ROLES:
                verdicts.append(Verdict(
                    code="depiction-role-unknown",
                    subject=connection_ref(edge),
                    message=(
                        f"Attempted to record that artifact "
                        f"'{edge.from_name}' depicts '{edge.to_name}' "
                        f"with role '{role}'. Failed due to: a depiction "
                        "pairing's role is 'primary' (the blessed "
                        "reference assignment) or 'also-shows' (an "
                        "inventory fact), or absent (a plain fact). Fix "
                        "the role."),
                    remedy="Use role 'primary' or 'also-shows', or drop "
                           "the role."))

    # -- each touched artifact -----------------------------------------------
    for label, name in sorted(touched_artifacts(delta, scratch), key=str):
        props = scratch.nodes.get((label, name)) or {}
        ref = CitizenRef(label, name)
        rows = [e for e in located if (e.from_label, e.from_name) == (label,
                                                                       name)
                and e.to_label in kinds]  # a wrong kind is named above
        primaries = []
        for edge in rows:
            row = scratch.nodes.get((edge.to_label, edge.to_name)) or {}
            missing = [k for k in ("scheme", "address") if _blank(row.get(k))]
            if missing:
                verdicts.append(Verdict(
                    code="location-incomplete",
                    subject=CitizenRef(edge.to_label, edge.to_name),
                    message=(
                        f"Attempted to locate artifact '{name}' at "
                        f"'{edge.to_name}'. Failed due to: the location "
                        f"lacks {', '.join(missing)} — a location names "
                        "its scheme and the address that scheme reads. "
                        "Add them in scratch."),
                    remedy="Add scheme and address in scratch.",
                    data={"missing": missing}))
            if row.get("primary") is True:
                primaries.append(edge.to_name)
            holders = {e.from_name for e in located
                       if (e.to_label, e.to_name) == (edge.to_label,
                                                       edge.to_name)}
            if len(holders) > 1:
                verdicts.append(Verdict(
                    code="location-shared",
                    subject=CitizenRef(edge.to_label, edge.to_name),
                    message=(
                        f"Attempted to locate artifact '{name}' at "
                        f"'{edge.to_name}'. Failed due to: that location "
                        f"row already belongs to {', '.join(sorted(str(h) for h in holders if h != name))} — a location "
                        "row belongs to one artifact. Author a row of "
                        "its own."),
                    remedy="Author a location row of its own."))
            if edge.to_label == KERNEL_FILE_LOCATION_LABEL \
                    and not _blank(row.get("address")):
                path = file_path(base_dir, row["address"])
                data = None
                if path is None:
                    problem = "the address reaches outside the knowledge base"
                else:
                    try:
                        data = path.read_bytes()
                        problem = None
                    except OSError as exc:
                        problem = f"the file is not readable ({exc})"
                if problem:
                    verdicts.append(Verdict(
                        code="file-location-unreadable",
                        subject=CitizenRef(edge.to_label, edge.to_name),
                        message=(
                            f"Attempted to read artifact '{name}' at "
                            f"{row['address']}. Failed due to: {problem} "
                            "— a file location is read at the gate. Fix "
                            "the address, restore the file, or record "
                            "the location under another kind."),
                        remedy="Fix the address, restore the file, or "
                               "use another location kind."))
                elif data is not None and not _blank(props.get("fingerprint")) \
                        and props["fingerprint"] != hashlib.sha256(
                            data).hexdigest():
                    verdicts.append(Verdict(
                        code="artifact-fingerprint-mismatch",
                        subject=ref,
                        message=(
                            f"Attempted to verify artifact '{name}' at "
                            f"{row['address']}. Failed due to: the artifact "
                            f"declares fingerprint "
                            f"{str(props['fingerprint'])[:12]} but the "
                            "file's bytes hash to "
                            f"{hashlib.sha256(data).hexdigest()[:12]} — "
                            "the receipt is stale or mistyped, or the "
                            "file changed. Run python -m graph receipt "
                            f"{row['address']} and paste its fingerprint, "
                            "or record the new bytes as a new artifact "
                            "that SUPERSEDES this one."),
                        remedy="Paste the file's receipt, or record a new "
                               "artifact that supersedes this one.",
                        data={"declared": props["fingerprint"],
                              "actual": hashlib.sha256(data).hexdigest()}))
        if rows and len(primaries) != 1:
            verdicts.append(Verdict(
                code="artifact-primary-location",
                subject=ref,
                message=(
                    f"Attempted to locate artifact '{name}'. Failed due "
                    f"to: {len(primaries)} of its {len(rows)} locations "
                    "carry primary: true — exactly one location is "
                    "primary. Mark one."),
                remedy="Mark exactly one location primary: true.",
                data={"primaries": sorted(str(p) for p in primaries)}))
        provenance, examined, _legacy = facet_grades(props)
        facets = (("what the source says", PROVENANCE_GRADE_PROP,
                   provenance),
                  ("what was examined", EXAMINED_GRADE_PROP, examined))
        for facet_name, prop, grade in facets:
            if _blank(grade):
                continue
            if grade not in GRADES:
                verdicts.append(Verdict(
                    code="artifact-grade-unknown",
                    subject=ref,
                    message=(
                        f"Attempted to grade artifact '{name}''s "
                        f"{facet_name} facet as '{grade}'. Failed due "
                        "to: each facet's grade is Cited, Attested, or "
                        "Transcribed. Set one of the three."),
                    remedy=f"Set {prop} to Cited, Attested, or "
                           "Transcribed.",
                    data={prop: grade}))
            elif grade == "Transcribed":
                verdicts.append(Verdict(
                    code="artifact-grade-parked",
                    subject=ref,
                    message=(
                        f"Attempted to grade artifact '{name}''s "
                        f"{facet_name} facet as Transcribed. Failed due "
                        "to: region-grain receipts are not built yet — "
                        "Attested is the highest grade a facet can hold "
                        "today."),
                    remedy="Grade the facet Attested."))
        if provenance == "Attested":
            checked = any(
                not _blank((scratch.nodes.get(
                    (edge.to_label, edge.to_name)) or {})
                    .get(VERIFIED_FINGERPRINT))
                for edge in located if edge.from_name == name)
            if not checked:
                verdicts.append(Verdict(
                    code="artifact-grade-unearned",
                    subject=ref,
                    message=(
                        f"Attempted to grade artifact '{name}''s "
                        "what-the-source-says facet as Attested. Failed "
                        "due to: no location of it carries the "
                        "verification stamp — an attested chain is a "
                        "CHECKED chain, and the engine has read no "
                        "bytes for this artifact. Land a verified file "
                        "location first, or grade the facet Cited."),
                    remedy="Land a verified file location, or grade the "
                           "facet Cited."))
        if examined == "Attested":
            lacks = []
            if _blank(props.get("description")):
                lacks.append("a description")
            if not depicted_by.get(name):
                lacks.append("at least one DEPICTS fact")
            if lacks:
                verdicts.append(Verdict(
                    code="artifact-grade-unearned",
                    subject=ref,
                    message=(
                        f"Attempted to grade artifact '{name}''s "
                        "what-was-examined facet as Attested. Failed "
                        f"due to: it lacks "
                        f"{' and '.join(lacks)} — Attested means a "
                        "description and its depicted contents are on "
                        "record. Add them in this round, or grade it "
                        "Cited."),
                    remedy="Add the description and DEPICTS facts, or "
                           "grade it Cited.",
                    data={"lacks": lacks}))
        superseded_at = props.get("superseded_at")
        if not _blank(superseded_at) and (isinstance(superseded_at, bool)
                                          or not isinstance(superseded_at,
                                                            int)):
            verdicts.append(Verdict(
                code="artifact-superseded-at-invalid",
                subject=ref,
                message=(
                    f"Attempted to retire artifact '{name}' as an intake "
                    f"ruler at {superseded_at!r}. Failed due to: "
                    "superseded_at is the event-log sequence at which it "
                    "stopped being the ruler — a whole number."),
                remedy="Set superseded_at to a round sequence.",
                data={"superseded_at": superseded_at}))

    # -- interpretations -------------------------------------------------------
    interpretation = KERNEL_INTERPRETATION_LABEL
    touched = {n for l, n, _ in delta.nodes_added if l == interpretation}
    touched |= {n for l, n, _ in delta.nodes_changed if l == interpretation}
    for edge in list(delta.edges_added) + list(delta.edges_removed):
        if edge.type in (ABOUT, INTERPRETED_AS, DRAWS_ON) \
                and edge.from_label == interpretation:
            touched.add(edge.from_name)
    for name in sorted(touched, key=str):
        key = (interpretation, name)
        if key not in scratch.nodes:
            continue
        props = scratch.nodes[key] or {}
        ref = CitizenRef(interpretation, name)
        if _blank(props.get("intent")):
            verdicts.append(Verdict(
                code="interpretation-intent-missing",
                subject=ref,
                message=(
                    f"Attempted to record interpretation '{name}'. Failed "
                    "due to: it carries no intent — an interpretation says "
                    "what an artifact stands for FOR SOME PURPOSE, in this "
                    "world's own words. Add intent in scratch."),
                remedy="Add intent in scratch."))
        abouts = [e for e in scratch.edges if e.type == ABOUT
                  and (e.from_label, e.from_name) == key
                  and e.to_label in artifacts]
        if len(abouts) != 1:
            verdicts.append(Verdict(
                code="interpretation-about",
                subject=ref,
                message=(
                    f"Attempted to record interpretation '{name}'. Failed "
                    f"due to: it is ABOUT {len(abouts)} artifacts — an "
                    "interpretation reads exactly one artifact. Author "
                    "one ABOUT edge to the artifact it interprets."),
                remedy="Author exactly one ABOUT edge to an artifact.",
                data={"about": sorted(str(e.to_name) for e in abouts)}))
            continue
        subject_artifact = abouts[0].to_name
        depicted = depicted_by.get(subject_artifact, set())
        for edge in scratch.edges:
            if edge.type == DRAWS_ON and (edge.from_label,
                                          edge.from_name) == key:
                if (edge.to_label, str(edge.to_name)) not in depicted:
                    verdicts.append(Verdict(
                        code="draws-on-undepicted",
                        subject=connection_ref(edge),
                        message=(
                            f"Attempted to record that interpretation "
                            f"'{name}' draws on ({edge.to_label}) "
                            f"'{edge.to_name}'. Failed due to: artifact "
                            f"'{subject_artifact}' does not depict it — "
                            "an interpretation draws on the artifact's "
                            "depicted contents. Record the DEPICTS fact "
                            "first, or drop the edge."),
                        remedy="Record the DEPICTS fact first, or drop "
                               "the DRAWS_ON edge."))

    # -- resolvers ---------------------------------------------------------
    resolver = KERNEL_RESOLVER_LABEL
    touched = {n for l, n, _ in delta.nodes_added if l == resolver}
    touched |= {n for l, n, _ in delta.nodes_changed if l == resolver}
    for edge in list(delta.edges_added) + list(delta.edges_removed):
        if edge.type == OPENS_WITH and edge.from_label == resolver:
            touched.add(edge.from_name)
    for name in sorted(touched, key=str):
        key = (resolver, name)
        if key not in scratch.nodes:
            continue
        props = scratch.nodes[key] or {}
        ref = CitizenRef(resolver, name)
        lacks = [k for k in ("scheme", "location_kind") if _blank(props.get(k))]
        if lacks:
            verdicts.append(Verdict(
                code="resolver-incomplete",
                subject=ref,
                message=(
                    f"Attempted to declare resolver '{name}'. Failed due "
                    f"to: it lacks {', '.join(lacks)} — a resolver names "
                    "the scheme it opens and the location kind it binds "
                    "to. Add them in scratch."),
                remedy="Add scheme and location_kind in scratch.",
                data={"missing": lacks}))
        elif props.get("location_kind") not in kinds:
            verdicts.append(Verdict(
                code="resolver-kind-unknown",
                subject=ref,
                message=(
                    f"Attempted to bind resolver '{name}' to location "
                    f"kind '{props.get('location_kind')}'. Failed due to: "
                    "no such location kind — bind it to [Artifact "
                    "Location] or a kind declared under it."),
                remedy="Bind location_kind to a declared location kind."))
        opens = [e for e in scratch.edges if e.type == OPENS_WITH
                 and (e.from_label, e.from_name) == key]
        good = [e for e in opens if e.to_label in (KERNEL_PROCEDURE_LABEL,
                                                    KERNEL_BOOKMARK_LABEL)]
        if len(good) != 1 or len(opens) != 1:
            verdicts.append(Verdict(
                code="resolver-opens-with",
                subject=ref,
                message=(
                    f"Attempted to declare resolver '{name}'. Failed due "
                    f"to: it OPENS_WITH {len(opens)} target(s), of which "
                    f"{len(good)} is a procedure — a resolver opens with "
                    "exactly one procedure: a [Procedure] of this "
                    "knowledge base, or a [Citizen Bookmark] into the tool "
                    "knowledge base that owns the how."),
                remedy="Author exactly one OPENS_WITH edge to a "
                       "[Procedure] or a [Citizen Bookmark]."))
    return verdicts


# -- the apply-time stamp: what the engine verified --------------------------


def depicted_subject(scratch, edge):
    """What a DEPICTS target MEANS: (identity, voice). A [Citizen
    Bookmark] target means the FOREIGN citizen the bookmark names —
    identity at (knowledge base, label, name) grain so two rows citing
    one citizen read as one subject — and the voice speaks the foreign
    name with its home, never the bookmark row's machinery name. A
    local target is itself."""
    from .ontology import KERNEL_BOOKMARK_LABEL
    if edge.to_label == KERNEL_BOOKMARK_LABEL:
        props = scratch.nodes.get((edge.to_label, edge.to_name)) or {}
        kb = props.get("dependency")
        label = props.get("citizen_label")
        name = props.get("citizen_name")
        if kb and label and name:
            return ((str(kb), str(label), str(name)),
                    f"({label}) '{name}' (in {kb})")
    return ((None, edge.to_label, str(edge.to_name)),
            f"({edge.to_label}) '{edge.to_name}'")


def depiction_advisories(delta, scratch):
    """The gate calls the correlations out: each NEW primary pairing's
    derived reference interpretation, named while the owner is already
    looking, and a subject gaining a second primary reference — a fact
    worth the eye, never a refusal."""
    from .report import ADVISORY
    advisories = []
    artifacts = artifact_labels(scratch)
    primaries_of = {}
    for edge in _edges(scratch, DEPICTS):
        if dict(edge.props).get(ROLE_PROP) == "primary":
            identity, _voice = depicted_subject(scratch, edge)
            primaries_of.setdefault(identity, set()).add(
                str(edge.from_name))
    seconds_called = set()
    for edge in delta.edges_added:
        if edge.type != DEPICTS or edge.from_label not in artifacts:
            continue
        if dict(edge.props).get(ROLE_PROP) != "primary":
            continue
        subject, voice = depicted_subject(scratch, edge)
        advisories.append(Verdict(
            code="reference-correlated", severity=ADVISORY,
            subject=connection_ref(edge),
            message=(f"correlated: '{edge.from_name}' → {voice} — the "
                     "reference interpretation derives with this "
                     "round."),
            data={"artifact": str(edge.from_name),
                  "subject": [part for part in subject
                              if part is not None]}))
        holders = primaries_of.get(subject, set()) | {str(edge.from_name)}
        if len(holders) > 1 and subject not in seconds_called:
            seconds_called.add(subject)
            names = ", ".join(f"'{h}'" for h in sorted(holders))
            advisories.append(Verdict(
                code="second-primary-reference", severity=ADVISORY,
                subject=connection_ref(edge),
                message=(f"{voice} now has "
                         f"{len(holders)} primary references ({names}) "
                         "— each derives its own interpretation; if one "
                         "should be the reference, make the others "
                         "also-shows."),
                data={"subject": [part for part in subject
                                  if part is not None],
                      "artifacts": sorted(holders)}))
    return advisories


def legacy_grade_advisories(delta, scratch):
    """A round touching an artifact still on the legacy single grade
    hears where that grade now reads — loud, never blocking. Split it
    while you're here."""
    from .report import ADVISORY
    from .refs import CitizenRef
    advisories = []
    facet_words = {"provenance": "what the source says",
                   "examined": "what was examined"}
    for label, name in sorted(touched_artifacts(delta, scratch), key=str):
        props = scratch.nodes.get((label, name)) or {}
        _prov, _exam, legacy_facet = facet_grades(props)
        if legacy_facet is None:
            continue
        legacy = props.get(LEGACY_GRADE_PROP)
        advisories.append(Verdict(
            code="grade-facet-legacy", severity=ADVISORY,
            subject=CitizenRef(label, name),
            message=(f"artifact '{name}' still carries the single grade "
                     f"'{legacy}', read as its "
                     f"{facet_words[legacy_facet]} facet — split it "
                     "while this round is here "
                     f"({PROVENANCE_GRADE_PROP} / "
                     f"{EXAMINED_GRADE_PROP})."),
            data={"legacy": legacy, "reads_as": legacy_facet}))
    return advisories


def sniff_medium(data):
    from .comprehension import sniff_medium as sniff
    return sniff(data)


def verification_stamp(graph, base_dir, sequence, artifacts):
    """Stamp verification onto every [File Location] of the named
    artifacts (as (label, name) keys — [Artifact] or any kind of it) IN
    PLACE — fingerprint, size, the round's sequence — and the artifact's
    own fingerprint and medium from its primary file location (or its
    first). Returns collated problems; nothing is stamped unless every
    file reads (verify-all before apply-any)."""
    plans, problems = [], []
    for key in sorted(artifacts, key=str):
        if key not in graph.nodes:
            continue
        label, name = key
        rows = [e for e in _edges(graph, LOCATED_AT)
                if (e.from_label, e.from_name) == key
                and e.to_label == KERNEL_FILE_LOCATION_LABEL
                and (e.to_label, e.to_name) in graph.nodes]
        read = []
        for edge in rows:
            row = graph.nodes[(edge.to_label, edge.to_name)]
            path = file_path(base_dir, row.get("address"))
            if path is None:
                problems.append(f"'{name}': location '{edge.to_name}' "
                                "reaches outside the knowledge base")
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                problems.append(f"'{name}': location '{edge.to_name}' at "
                                f"{row.get('address')} is not readable "
                                f"({exc})")
                continue
            read.append((edge.to_name, row, data))
        plans.append((key, read))
    if problems:
        return problems
    for key, read in plans:
        node = graph.nodes[key]
        chosen = None
        for row_name, row, data in read:
            digest = hashlib.sha256(data).hexdigest()
            row[VERIFIED_FINGERPRINT] = digest
            row[VERIFIED_AT] = sequence
            row[SIZE] = len(data)
            if chosen is None or row.get("primary") is True:
                chosen = data
        if chosen is not None:
            node["fingerprint"] = hashlib.sha256(chosen).hexdigest()
            node["medium"] = sniff_medium(chosen)
    return []


# -- the receipts sweep's rows: is each location still what was verified? --


def location_rows(graph, base_dir):
    """One row per location on canon, for the receipts sweep: verified
    (the file still hashes to what the gate recorded), stale (it does
    not), unreadable, unverified (a file location no round has verified
    yet), or unverifiable by design (any other kind)."""
    from .report import ref_key
    kinds = location_labels(graph)
    owner = {}
    for edge in _edges(graph, LOCATED_AT):
        owner[(edge.to_label, edge.to_name)] = edge.from_name
    rows = []
    for (label, name), props in sorted(graph.nodes.items(), key=str):
        if label not in kinds:
            continue
        row = {"location": name, "kind": label, "artifact": owner.get(
            (label, name)), "scheme": props.get("scheme"),
               "address": props.get("address"),
               "primary": props.get("primary") is True}
        if label != KERNEL_FILE_LOCATION_LABEL:
            row.update(code="location-unverifiable", status="unverifiable")
        else:
            path = file_path(base_dir, props.get("address"))
            try:
                data = path.read_bytes() if path is not None else None
            except OSError:
                data = None
            recorded = props.get(VERIFIED_FINGERPRINT)
            if data is None:
                row.update(code="location-unreadable", status="unreadable")
            elif _blank(recorded):
                row.update(code="location-unverified", status="unverified")
            elif hashlib.sha256(data).hexdigest() == recorded:
                row.update(code="location-verified", status="verified")
            else:
                row.update(code="location-stale", status="stale",
                           recorded=recorded,
                           actual=hashlib.sha256(data).hexdigest())
        row["ref"] = ref_key(row["code"])
        rows.append(row)
    return rows
