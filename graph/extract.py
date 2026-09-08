"""Turn the CSV sources into a typed graph, as directed by the ontology.

The output is an in-memory GraphData (nodes keyed by (label, name), a flat
edge list) plus Findings for everything that didn't resolve cleanly. Nothing
here crashes on messy cell content: unmatched references become placeholder
nodes or report entries per the ontology's on_missing policy.
"""

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import grammars, parsers, procedures
from .ontology import (ANY_LABEL, ARCHETYPE_LABEL, ENUM_TYPE_PREFIX, ERROR,
                       WARNING, INFO, Category, Finding, KERNEL_PROCEDURE_LABEL,
                       MEMBERSHIP_EDGE_TYPE,
                       OnMissing, ORDERED_CONCEPT, OUTCOME_LABEL, PropType,
                       Reader, RelParser, RENDERED_VIEWS_PROP, STEP_LABEL,
                       concept_bindings, is_concept_archetype, node_reader,
                       rendered_views_of, source_files_of)


@dataclass(frozen=True)
class Edge:
    type: str
    from_label: str
    from_name: str
    to_label: str
    to_name: str
    props: tuple  # sorted (key, value) pairs, hashable for dedup/sort


def make_edge(rel_type, from_label, from_name, to_label, to_name, props=None):
    return Edge(rel_type, from_label, from_name, to_label, to_name,
                tuple(sorted((props or {}).items())))


def assigns_edge_type(resolved_label):
    """The ASSIGNS_<LABEL> edge type an assignment to `resolved_label`
    projects. Parallel value-domain systems are domain-explicit
    (stratified naming rule 2): ASSIGNS_<the resolved label in
    UPPER_SNAKE>. The SAME transform serves both assignment paths —
    transcribed become-steps and attested assigns declarations — so an
    assertion cannot claim an edge the derivation would not compute."""
    snake = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", resolved_label).upper()
    return f"ASSIGNS_{snake}"


@dataclass
class GraphData:
    nodes: dict = field(default_factory=dict)   # (label, name) -> props dict
    edges: list = field(default_factory=list)

    def ensure_node(self, label, name, **props):
        node = self.nodes.setdefault((label, name), {})
        node.update(props)
        return node


class Extractor:
    def __init__(self, ontology):
        self.ontology = ontology
        self.graph = GraphData()
        self.findings = []
        self.enums = {}
        self.source_order = {}    # label -> value names in source order
        self.section_bodies = {}  # (label, name) -> markdown body text
        self.pending_procedures = []  # (label, spec dict, relpath) awaiting lift

    def note(self, severity, category, file, location, detail):
        self.findings.append(Finding(severity, category, file, location, detail))

    # -- helpers -------------------------------------------------------------

    def read_rows(self, relpath):
        with open(self.ontology.base_dir / relpath, newline="",
                  encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def read_raw_rows(self, relpath):
        with open(self.ontology.base_dir / relpath, newline="",
                  encoding="utf-8") as handle:
            return list(csv.reader(handle))

    def resolve_alias(self, label, raw_name):
        aliases = self.ontology.nodes.get(label, {}).get("aliases") or {}
        target = aliases.get(raw_name, raw_name)
        if isinstance(target, list):
            # A list-valued alias is glossary vocabulary (one alias names
            # both its Grades, the glossary sitting) — deliberately ambiguous, so a CSV
            # cell may not ride it; the cell keeps its raw name and the
            # dangling-reference check reports it for an explicit ruling.
            return raw_name
        return target

    def append_unmatched(self, label, name, prop, clause):
        node = self.graph.nodes.get((label, name))
        if node is None or not prop:
            return
        existing = node.get(prop)
        node[prop] = f"{existing}. {clause}" if existing else clause

    # -- passes ---------------------------------------------------------------

    def ladder_of(self, label):
        """Ladder order from the rank ground props (placeholders carry
        no rank and stay off the ladder)."""
        ranked = sorted(
            (props["rank"], name)
            for (node_label, name), props in self.graph.nodes.items()
            if node_label == label and "rank" in props)
        return [name for _, name in ranked]

    def derive_markdown_rels(self):
        """Derive-era: markdown-section labels re-derive PART_OF and
        MENTIONS from the graph — bodies live on the nodes."""
        for label, spec in self.ontology.nodes.items():
            if not isinstance(spec, dict) or \
                    node_reader(spec) != Reader.MARKDOWN_SECTIONS:
                continue
            for (node_label, name), props in self.graph.nodes.items():
                if node_label == label and "body" in props:
                    self.section_bodies[(label, name)] = props["body"]
            for rel in spec.get("relationships") or []:
                match rel.get("parser"):
                    case RelParser.PART_OF:
                        self.rel_part_of(label, rel)
                    case RelParser.MENTIONS:
                        self.rel_mentions(label, rel)

    def derive_effect_references(self):
        """Derive-era: Effect REFERENCES edges re-derive from each
        Effect node's own condition prop (the node is ground; the
        deterministic scan is machinery)."""
        for label, spec in self.ontology.nodes.items():
            if not isinstance(spec, dict):
                continue
            for rel in spec.get("relationships") or []:
                if rel.get("parser") != RelParser.EFFECTS_TABLE:
                    continue
                effect_label = rel["effect_label"]
                candidates = {}
                for (node_label, name) in self.graph.nodes:
                    if node_label not in (ARCHETYPE_LABEL, effect_label):
                        candidates.setdefault(name, []).append(node_label)
                for (node_label, name), props in sorted(
                        self.graph.nodes.items()):
                    condition = props.get("condition")
                    if node_label != effect_label or not condition:
                        continue
                    for hit in parsers.mention_matches(condition,
                                                       candidates):
                        for target_label in candidates[hit]:
                            self.graph.edges.append(make_edge(
                                "REFERENCES", effect_label, name,
                                target_label, hit))

    def rebuild_pending_procedures(self):
        """Derive-era worklist: reconstruct each procedure's spec from
        the body its own node carries — the graph is the source now. A
        program label needs only its READER to qualify: one that still
        registers files lifts the bodies its citizens carry from them,
        and one that registers none (graph-resident program bodies —
        the files released, the body a ground prop on each citizen)
        lifts exactly the same way."""
        for label, spec in self.ontology.nodes.items():
            if not isinstance(spec, dict) or \
                    node_reader(spec) != Reader.PROCEDURE_YAML:
                continue
            for (node_label, name), props in sorted(self.graph.nodes.items()):
                if node_label != label or not props.get("body"):
                    continue
                proc_spec, errors = procedures.parse_procedure(props["body"])
                relpath = props.get("source_path", f"{label}: {name}")
                for location, detail in errors:
                    self.note(ERROR, Category.PROCEDURE, relpath,
                              location, detail)
                if proc_spec is None or errors:
                    continue
                self.note_truncation_tails(props["body"], proc_spec, relpath)
                self.pending_procedures.append((label, proc_spec, relpath))

    def rel_part_of(self, label, rel):
        """(section)-[:PART_OF]->(container named by the section's linking
        prop). The prop is the relationship's `column` (default `file`,
        the from-sources shape); a graph-native prose label points at its
        containing citizen through an ordinary ground prop instead."""
        prop = rel.get("column", "file")
        for (node_label, name), props in list(self.graph.nodes.items()):
            if node_label != label or prop not in props:
                continue
            self.link(rel, label, name, rel["to"], props[prop],
                      props[prop], name)

    def rel_mentions(self, label, rel):
        """(section)-[:MENTIONS]->(node) for every known node name appearing
        verbatim in the section body. Deterministic exact matching."""
        skip_labels = {label, "Archetype"}
        candidates = {}
        for (node_label, name) in self.graph.nodes:
            if node_label not in skip_labels:
                candidates.setdefault(name, []).append(node_label)
        for (node_label, name), body in self.section_bodies.items():
            if node_label != label:
                continue
            for hit in parsers.mention_matches(body, candidates):
                for target_label in candidates[hit]:
                    self.graph.edges.append(make_edge(
                        rel["type"], label, name, target_label, hit))

    def resolve_any(self, raw_target, prefer=None):
        """Label-agnostic name resolution for `to: any` relationships.

        Accepts an optional "Label: Name" qualifier (only honored when the
        prefix is a declared label, so names containing ': ' stay safe —
        ': ' is the one reserved qualifier syntax). With `prefer` (a set of
        labels), a unique match among THOSE labels wins before the bare
        name is tried across every label — an artifact citation resolves
        among artifact kinds, so a location row or any other machinery row
        sharing the name never competes. Returns (label, name) on a unique
        match, or (None, reason) otherwise; an ambiguity names the labels
        matched and both remedies.
        """
        qualifier, sep, rest = raw_target.partition(": ")
        if sep and (qualifier in self.ontology.nodes
                    or qualifier == ARCHETYPE_LABEL
                    or (ARCHETYPE_LABEL, qualifier) in self.graph.nodes):
            if (qualifier, rest.strip()) in self.graph.nodes:
                return qualifier, rest.strip()
            return None, f"no {qualifier} named '{rest.strip()}'"
        if prefer:
            preferred = [(node_label, name)
                         for (node_label, name) in self.graph.nodes
                         if name == raw_target and node_label in prefer]
            if len(preferred) == 1:
                return preferred[0]
            if len(preferred) > 1:
                labels = ", ".join(sorted(m[0] for m in preferred))
                return None, (f"'{raw_target}' is ambiguous ({labels}) — "
                              f"qualify it as 'Label: {raw_target}', or "
                              "rename one of them")
        matches = [(node_label, name)
                   for (node_label, name) in self.graph.nodes
                   if name == raw_target]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            return None, f"no node named '{raw_target}'"
        labels = ", ".join(sorted(m[0] for m in matches))
        return None, (f"'{raw_target}' is ambiguous ({labels}) — qualify "
                      f"it as 'Label: {raw_target}', or rename one of them")

    def artifact_labels(self):
        """[Artifact] and every kind of it through the taxonomy — the
        labels an artifact citation resolves among first."""
        from .ontology import KERNEL_ARTIFACT_LABEL
        kinds = {KERNEL_ARTIFACT_LABEL}
        grew = True
        while grew:
            grew = False
            for edge in self.graph.edges:
                if edge.type == "SUBTYPE_OF" \
                        and edge.from_label == ARCHETYPE_LABEL \
                        and edge.to_label == ARCHETYPE_LABEL \
                        and edge.to_name in kinds \
                        and edge.from_name not in kinds:
                    kinds.add(edge.from_name)
                    grew = True
        return kinds

    def link(self, rel, from_label, from_name, to_label, raw_target,
             file, location, props=None):
        """Resolve one target reference and emit an edge per policy."""
        if to_label == ANY_LABEL:
            resolved_label, detail = self.resolve_any(raw_target)
            if resolved_label is None:
                self.note(WARNING, Category.DANGLING_REF, file, location,
                          f"{from_label} '{from_name}' -> {rel['type']}: "
                          f"{detail}; edge dropped")
                self.append_unmatched(from_label, from_name,
                                      rel.get("unmatched_property"),
                                      raw_target)
                return
            to_label, raw_target = resolved_label, detail
        target = self.resolve_alias(to_label, raw_target)
        target_spec = self.ontology.nodes.get(to_label, {})
        exists = (to_label, target) in self.graph.nodes
        if not exists and target_spec.get("implicit"):
            self.graph.ensure_node(to_label, target)
            exists = True
            # a birth is never silent: the gate itemizes every citizen
            # born by reference, by label and name
            self.findings.append(Finding(
                INFO, Category.DANGLING_REF, "canon",
                f"{to_label}: {target}",
                f"'{target}' ({to_label}) was born by reference — no "
                f"citizen held that name, and '{to_label}' is declared "
                f"to birth one when referenced (reached from "
                f"'{from_name}' ({from_label})).",
                code="citizen-born-by-reference",
                remedy="Author the citizen properly if it deserves more "
                       "than a name, or fix the reference."))
        if not exists:
            policy = rel.get("on_missing", self.ontology.default_on_missing)
            classify = grammars.get_optional("classify_clause")
            hint = classify(raw_target) if classify else None
            hint = f" ({hint})" if hint else ""
            if policy == OnMissing.PLACEHOLDER:
                self.graph.ensure_node(to_label, target, placeholder=True)
                self.note(WARNING, Category.DANGLING_REF, file, location,
                          f"{from_label} '{from_name}' -> {rel['type']} -> "
                          f"{to_label} '{target}' does not exist; "
                          f"placeholder created{hint}")
            else:
                self.note(WARNING, Category.DANGLING_REF, file, location,
                          f"{from_label} '{from_name}' -> {rel['type']} -> "
                          f"{to_label} '{target}' does not exist; edge "
                          f"dropped{hint}")
                self.append_unmatched(from_label, from_name,
                                      rel.get("unmatched_property"), raw_target)
                return
        self.graph.edges.append(make_edge(
            rel["type"], from_label, from_name, to_label, target,
            {**(rel.get("props") or {}), **(props or {})}))

    def link_procedures(self):
        """Plug each pending procedure into the rest of the graph, per tier.

        All tiers: (Procedure)-[:SPECIFIED_IN]->(source), with the
        approved_hash tripwire (WARNING when the approved body has changed).
        Programmed: the Step lift — FIRST_STEP/NEXT/CASE/THEN/OTHERWISE
        chains, (case)-[:MATCHES]->(value), step-level REFERENCES — plus the
        DERIVED signature projection: (:Outcome) nodes (HAS_POSSIBLE_OUTCOME/ENDS_AT/
        ASSIGNS/MUTATES) and Procedure-level READS/MUTATES/CALLS rollups.
        Signed: the same signature edges emitted from the ASSERTED sections.
        Referenced: nothing further. Runs after build_relationships so
        implicit nodes exist to resolve against."""
        self.term_index = self.build_term_index()
        for label, proc_spec, relpath in self.pending_procedures:
            proc_name = str(proc_spec["procedure"]).strip()
            body = self.link_specified_in(label, proc_name, proc_spec,
                                          relpath)
            self.verify_receipts(proc_name, proc_spec, body, relpath)
            self.scan_unresolved_terms(proc_name, proc_spec, body, relpath)
            completeness = procedures.effective_completeness(proc_spec)
            level_node = str(completeness).capitalize()
            if (ARCHETYPE_LABEL, level_node) in self.graph.nodes:
                self.graph.edges.append(make_edge(
                    "KNOWN_AT", label, proc_name, ARCHETYPE_LABEL, level_node))
            match completeness:
                case procedures.Completeness.TRANSCRIBED:
                    self.link_program(label, proc_name, proc_spec, relpath)
                case procedures.Completeness.ATTESTED:
                    self.link_attested(label, proc_name, proc_spec, relpath)
                # cited: the node, KNOWN_AT, and SPECIFIED_IN are all there is
        self.link_native_procedures()

    def link_native_procedures(self):
        """The graph-native half of the procedure linkage: a Procedure
        citizen with no registered source file declares its completeness
        as a ground prop (known_at, naming a Completeness value) and
        carries its body as prose citizens PART_OF it. Derivation turns
        the declaration into the kernel edges — KNOWN_AT to the named
        level, SPECIFIED_IN to each contained prose citizen (the
        citation for a self-specified procedure). File-registered
        procedures never enter here."""
        filed = {str(spec["procedure"]).strip()
                 for _, spec, _ in self.pending_procedures}
        levels = {e.from_name for e in self.graph.edges
                  if e.type == "INSTANCE_OF"
                  and e.from_label == ARCHETYPE_LABEL
                  and e.to_label == ARCHETYPE_LABEL
                  and e.to_name == "Completeness"}
        contained = {}
        for edge in self.graph.edges:
            if edge.type == "PART_OF":
                contained.setdefault((edge.to_label, edge.to_name),
                                     []).append(edge)
        for (label, name), props in sorted(
                self.graph.nodes.items(),
                key=lambda item: (item[0][0], str(item[0][1]))):
            if label != KERNEL_PROCEDURE_LABEL or name in filed:
                continue
            level = str(props.get("known_at", "")).strip()
            if level:
                if level in levels:
                    self.graph.edges.append(make_edge(
                        "KNOWN_AT", label, name, ARCHETYPE_LABEL, level))
                else:
                    self.note(
                        WARNING, Category.DANGLING_REF, "graph",
                        f"{label} '{name}'",
                        f"known_at names '{level}', which is not a "
                        "Completeness value; edge dropped")
            for edge in contained.get((label, name), []):
                self.graph.edges.append(make_edge(
                    "SPECIFIED_IN", label, name,
                    edge.from_label, edge.from_name))

    def build_term_index(self):
        """The glossary IS the graph (the glossary-is-the-graph ruling): one index
        mapping every surface form -> the citizen(s) it names. Surfaces are
        canonical names, deterministic plural variants (parsers.name_variants),
        and explicit surface_forms: from label/concept declarations. Steps
        and Outcomes are structure, not vocabulary — excluded."""
        index = {}

        def add(surface, label, name):
            index.setdefault(surface, set()).add((label, name))

        for (node_label, name) in self.graph.nodes:
            if node_label in (STEP_LABEL, OUTCOME_LABEL):
                continue
            for variant in parsers.name_variants(name):
                add(variant, node_label, name)
        # Label aliases are value-level surface forms (the owner's
        # original hypothesis: the glossary is Concepts with aliases) —
        # "Threatened" resolves to "Threatened (per Threat)". A target
        # may be a LIST when one surface genuinely names several
        # citizens (one alias naming two Grades, ruled at the glossary sitting) —
        # ambiguous-but-resolving.
        for label, spec in self.ontology.nodes.items():
            if not isinstance(spec, dict):
                continue
            for alias, target in (spec.get("aliases") or {}).items():
                targets = target if isinstance(target, list) else [target]
                for one in targets:
                    if (label, one) in self.graph.nodes:
                        for variant in parsers.name_variants(alias):
                            add(variant, label, one)
        explicit = []
        for label, spec in self.ontology.nodes.items():
            if isinstance(spec, dict):
                explicit += [(form, label)
                             for form in spec.get("surface_forms") or []]
                # known future value citizens of a partially-populated label
                explicit += [(name, label)
                             for name in spec.get("pending_instances") or []]
        for concept, spec in self.ontology.concepts.items():
            explicit += [(form, concept)
                         for form in (spec or {}).get("surface_forms") or []]
            # known future citizens of an unmapped system: their terms
            # resolve to the stub that will own them
            explicit += [(name, concept)
                         for name in (spec or {}).get("pending_instances")
                         or []]
        for form, owner in explicit:
            others = {t for t in index.get(form, set())
                      if t != (ARCHETYPE_LABEL, owner)}
            if others:
                names = ", ".join(sorted(f"{l} '{n}'" for l, n in others))
                self.note(WARNING, Category.ONTOLOGY, str(self.ontology.path),
                          owner, f"surface form '{form}' also names {names} — "
                          "ambiguous; consider renaming")
            if (ARCHETYPE_LABEL, owner) in self.graph.nodes:
                for variant in parsers.name_variants(form):
                    add(variant, ARCHETYPE_LABEL, owner)
        return index

    def note_truncation_tails(self, text, proc_spec, relpath):
        """The silent-truncation tripwire: a ' #' tail that
        vanished in parsing is either a deliberate comment or an eaten
        sentence — surface it either way; quoting the line settles it."""
        for lineno, tail in procedures.truncation_findings(text, proc_spec):
            self.note(WARNING, Category.PROCEDURE, relpath, f"line {lineno}",
                      f"a ' #' tail did not survive YAML parsing: "
                      f"'{tail}' — if this is program text, quote the "
                      "line (an unquoted scalar stops at ' #'); if it is "
                      "a comment, end the sentence before it or move it "
                      "to its own line")

    def artifact_section_body(self, artifact, section, relpath, context):
        """A file-span citation's body: read the artifact's bytes and find
        the section heading (canon holds no section citizens — spans
        resolve against the immutable source directly)."""
        path = self.ontology.base_dir / artifact
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.note(WARNING, Category.PROCEDURE, relpath, context,
                      f"specified_in artifact '{artifact}' is not "
                      f"readable ({exc}) — the citation cannot be verified")
            return None
        for heading, body in parsers.markdown_sections(text):
            if heading == section:
                return body
        self.note(WARNING, Category.PROCEDURE, relpath, context,
                  f"specified_in names section '{section}' but no such "
                  f"heading exists in {artifact} — the citation cannot "
                  "be verified")
        return None

    def lost_citation(self, label, proc_name, relpath, cited, detail):
        """A citation that resolves to nothing, or to several: never a
        dropped edge with a warning. An ERROR by name — the derived
        connection would leave because the facts cannot re-derive it, a
        lost fact rather than a departure — which every apply, rederive,
        and kernel migration refuses on, and the delta gate previews."""
        self.findings.append(Finding(
            ERROR, Category.DANGLING_REF, relpath,
            f"{label} '{proc_name}' specified_in",
            f"Attempted to resolve the citation '{cited}' that ({label}) "
            f"'{proc_name}' specifies itself in. Failed due to: {detail}. "
            "The SPECIFIED_IN connection would be lost — a fact the round "
            "cannot re-derive, not a departure — so nothing lands until "
            "the citation resolves to exactly one citizen.",
            code="derived-edge-lost",
            remedy="Qualify the citation as 'Label: name', or rename the "
                   "colliding citizen."))

    def link_specified_in(self, label, proc_name, proc_spec, relpath):
        """SPECIFIED_IN edge + approved_hash tripwire. Returns the resolved
        source body text (for receipts and the term tripwire), or None.

        A file-span citation may list SEVERAL sections (the multi-section citation rule — a
        chapter-spanning program): receipts check against all of their
        bodies, and approved_hash covers the bodies joined in the listed
        order. The edge carries the span list in its section prop
        (single-section citations serialize exactly as before)."""
        artifact, sections, approved_hash = \
            procedures.specified_in_of(proc_spec)
        if not sections and not artifact:
            return None
        if artifact:
            # file-span citation: verify against the bytes; the edge (with
            # the span as edge detail) lands on the artifact's citizen
            bodies = [b for b in
                      (self.artifact_section_body(artifact, s, relpath,
                                                  proc_name)
                       for s in sections)
                      if b is not None]
            body = "\n\n".join(bodies) if bodies else None
            resolved_label, detail = self.resolve_any(
                artifact, prefer=self.artifact_labels())
            if resolved_label is None:
                self.lost_citation(label, proc_name, relpath, artifact, detail)
            else:
                self.graph.edges.append(make_edge(
                    "SPECIFIED_IN", label, proc_name, resolved_label,
                    detail, {"section": " + ".join(sections)}))
        else:
            section = sections[0] if sections else ""
            resolved_label, detail = self.resolve_any(section)
            if resolved_label is None:
                self.lost_citation(label, proc_name, relpath, section, detail)
                return None
            self.graph.edges.append(make_edge(
                "SPECIFIED_IN", label, proc_name, resolved_label, detail))
            body = self.section_bodies.get((resolved_label, detail))
            if body is None:
                node = self.graph.nodes.get((resolved_label, detail)) or {}
                body = node.get("description") or node.get("doc")
        if artifact:
            cited = (f"section '{sections[0]}' of {artifact}"
                     if len(sections) == 1 else
                     f"sections '{' + '.join(sections)}' of {artifact}")
        else:
            cited = f"{resolved_label} '{detail}'"
        if not approved_hash:
            return body
        if body is None:
            self.note(WARNING, Category.PROCEDURE, relpath, "specified_in",
                      f"approved_hash given but {cited} has no readable "
                      "body to verify against")
        elif hashlib.sha256(body.encode("utf-8")).hexdigest() != approved_hash:
            self.note(WARNING, Category.PROCEDURE, relpath, "specified_in",
                      f"'{proc_name}' was approved against a body of "
                      f"{cited} that has since changed — "
                      "re-verify the procedure, then re-approve the hash")
        return body

    def verify_receipts(self, proc_name, proc_spec, body, relpath):
        """from_text receipts: every quote an authored fact carries must
        appear verbatim in the resolved source body (whitespace-normalized —
        YAML folding collapses line breaks). A receipt that can't be found
        is an interpretation posing as evidence."""
        receipts = procedures.receipts_of(proc_spec)
        if not receipts:
            return
        if body is None:
            self.note(WARNING, Category.PROCEDURE, relpath, proc_name,
                      "from_text receipts given but the specified_in source "
                      "has no readable body to check them against")
            return
        haystack = " ".join(body.split())
        for location, quote in receipts:
            if " ".join(quote.split()) not in haystack:
                self.note(WARNING, Category.PROCEDURE, relpath, location,
                          f"from_text receipt not found in the source: "
                          f"'{quote}' — the claim has no evidence behind it")

    def unresolved_terms_in(self, body, locals_=()):
        """Candidate terms in a prose body that the term index cannot
        resolve. Resolution: index hit (canonical, surface form, or plural
        variant) | declared local | word/compound of known vocabulary.
        Shared by the procedure scan and `python -m graph terms`."""
        index = self.term_index
        known_words = set()
        for surface in index:
            known_words.update(re.findall(r"[A-Za-z]+", surface))
        local_surfaces = set()
        for local in locals_:
            local_surfaces |= parsers.name_variants(str(local).strip())
        unresolved = set()
        for term in parsers.capitalized_runs(body):
            if term.endswith("'s"):
                term = term[:-2]  # possessives are not distinct terms
            if not term or term in index or term in local_surfaces:
                continue
            words = term.split()
            if len(words) == 1 and term in known_words:
                continue  # a word of some known surface ("Point")
            if len(words) > 1 and all(w in index for w in words):
                continue  # compound of whole citizens ("Bright Spark")
            unresolved.add(term)
        return unresolved

    def scan_unresolved_terms(self, proc_name, proc_spec, body, relpath):
        """Capitalized terms in the source that the glossary cannot resolve:
        exactly where misreadings hide (the Truename lesson). INFO findings —
        classify each as a surface form, a stub concept, or a local; never
        silence one."""
        if body is None:
            return
        unresolved = self.unresolved_terms_in(
            body, proc_spec.get("locals") or [])
        if unresolved:
            self.note(INFO, Category.UNRESOLVED_TERM, relpath, proc_name,
                      "capitalized source term(s) the glossary cannot "
                      f"resolve: {', '.join(sorted(unresolved))} — classify "
                      "each (surface form | stub concept | local); "
                      "misreadings hide here")

    def link_program(self, label, proc_name, proc_spec, relpath):
        # Split the term index by target kind: step text referencing a VALUE
        # citizen (any surface form) gets REFERENCES; concept-level surfaces
        # feed the Archetype READS projection below.
        value_surfaces = {}
        archetype_surfaces = {}
        for surface, targets in self.term_index.items():
            values = {t for t in targets if t[0] != ARCHETYPE_LABEL}
            concepts = {t for t in targets if t[0] == ARCHETYPE_LABEL}
            if values:
                value_surfaces[surface] = values
            if concepts:
                archetype_surfaces[surface] = concepts
        lifted = procedures.lift(proc_spec)
        for step in lifted.steps:
            props = {"kind": step.kind, "text": step.text}
            if step.condition:
                props["condition"] = step.condition
            self.graph.ensure_node(STEP_LABEL, step.name, **props)
        if lifted.first_step:
            self.graph.edges.append(make_edge(
                procedures.FIRST_STEP, label, proc_name,
                STEP_LABEL, lifted.first_step))
        for edge_type, from_name, to_name in lifted.edges:
            self.graph.edges.append(make_edge(
                edge_type, STEP_LABEL, from_name, STEP_LABEL, to_name))
        case_labels = set()
        for case_name, case_value in lifted.cases:
            resolved_label, detail = self.resolve_any(case_value)
            if resolved_label is None:
                self.note(WARNING, Category.DANGLING_REF, relpath,
                          case_name, f"case '{case_value}': {detail}; "
                          "ON edge dropped")
                continue
            self.graph.edges.append(make_edge(
                "MATCHES", STEP_LABEL, case_name, resolved_label, detail))
            case_labels.add(resolved_label)
        refs_by_step = {}
        kind_by_step = {step.name: step.kind for step in lifted.steps}
        referenced = set()
        for step in lifted.steps:
            if step.kind == "case":  # cases already point via MATCHES
                continue
            for hit in parsers.mention_matches(step.text, value_surfaces):
                for target_label, target in value_surfaces[hit]:
                    if target == proc_name:
                        continue
                    edge = make_edge("REFERENCES", STEP_LABEL, step.name,
                                     target_label, target)
                    if edge in referenced:
                        continue  # two surface forms of one citizen in a step
                    referenced.add(edge)
                    self.graph.edges.append(edge)
                    refs_by_step.setdefault(step.name, []).append(
                        (target_label, target))

        # Derived signature rollups (closed by construction — see the
        # *_closed node props): guard text feeds READS, mutation verbs feed
        # MUTATES, call steps feed CALLS (to fellow procedure nodes).
        projected = set()

        def project(edge):
            if edge not in projected:
                projected.add(edge)
                self.graph.edges.append(edge)

        for step_name, refs in refs_by_step.items():
            kind = kind_by_step[step_name]
            for target_label, target in refs:
                # compute observes what it sums — READS, never MUTATES
                if kind in ("when", "branch", "compute"):
                    project(make_edge("READS", label, proc_name,
                                      target_label, target))
                if kind in procedures.MUTATION_VERBS:
                    project(make_edge("MUTATES", label, proc_name,
                                      target_label, target))
                if kind == "call" and target_label == label:
                    project(make_edge("CALLS", label, proc_name,
                                      target_label, target))
        # A branch observes the CONCEPT it switches on (the victim's State),
        # not one named value — project that read to the label's Archetype.
        # Concept-level reads resolve the PROJECT layer only: a step that
        # happens to say a kernel facet's name ("Ordered", "Completeness")
        # observes no kernel machinery, so no READS ever points into it.
        kernel = self.ontology.kernel_names
        for case_label in case_labels:
            if (ARCHETYPE_LABEL, case_label) in self.graph.nodes \
                    and case_label not in kernel:
                project(make_edge("READS", label, proc_name,
                                  ARCHETYPE_LABEL, case_label))
        # A compute step likewise observes CONCEPTS ("modifiers due to State
        # or Situations" names label words, not value citizens) — resolve its
        # text through the term index's concept surfaces, so plural and
        # surface-form spellings project the same READS as canonical names.
        for step in lifted.steps:
            if step.kind != "compute":
                continue
            for hit in parsers.mention_matches(step.text, archetype_surfaces):
                for _, target in archetype_surfaces[hit]:
                    if target in kernel:
                        continue
                    project(make_edge("READS", label, proc_name,
                                      ARCHETYPE_LABEL, target))

        for outcome, bound in procedures.bind_outcomes(proc_spec,
                                                       lifted).items():
            outcome_name = f"{proc_name}: {outcome}"
            props = {"guarantee": bound["guarantee"]}
            if bound["notes"]:
                props["doc"] = ". ".join(bound["notes"])
            self.graph.ensure_node(OUTCOME_LABEL, outcome_name, **props)
            project(make_edge("HAS_POSSIBLE_OUTCOME", label, proc_name,
                              OUTCOME_LABEL, outcome_name))
            for terminal in bound["terminal_steps"]:
                project(make_edge("ENDS_AT", OUTCOME_LABEL, outcome_name,
                                  STEP_LABEL, terminal))
            for step_name in bound["trail_steps"]:
                kind = kind_by_step[step_name]
                for target_label, target in refs_by_step.get(step_name, []):
                    if kind == "become":
                        project(make_edge(assigns_edge_type(target_label),
                                          OUTCOME_LABEL, outcome_name,
                                          target_label, target))
                    elif kind in procedures.MUTATION_VERBS:
                        project(make_edge("MUTATES", OUTCOME_LABEL,
                                          outcome_name, target_label, target))

    def link_attested(self, label, proc_name, proc_spec, relpath):
        """Asserted signature: the same edge vocabulary as the derived
        projection, emitted from the approved declarations instead of a
        body. Closure booleans landed on the node at build time."""
        section_edges = {"reads": "READS", "consults": "CONSULTS",
                         "mutates": "MUTATES"}
        for section, edge_type in section_edges.items():
            for raw in (proc_spec.get(section) or {}).get("known") or []:
                self.link_asserted(label, proc_name, edge_type, raw,
                                   relpath, section)
        for outcome, entry in (proc_spec.get("possible_outcomes")
                               or {}).items():
            entry = entry or {}
            outcome_name = f"{proc_name}: {outcome}"
            props = {"guarantee": entry.get("guarantee", "")}
            if entry.get("description"):
                props["doc"] = entry["description"]
            self.graph.ensure_node(OUTCOME_LABEL, outcome_name, **props)
            self.graph.edges.append(make_edge(
                "HAS_POSSIBLE_OUTCOME", label, proc_name, OUTCOME_LABEL, outcome_name))
            # `assigns:` derives its edge type from the resolved target's
            # label (edge_type=None) exactly as the transcribed become-step
            # does; `mutates:` is always MUTATES.
            for raw in entry.get("assigns") or []:
                self.link_asserted(OUTCOME_LABEL, outcome_name, None,
                                   raw, relpath,
                                   f"possible_outcomes.{outcome}")
            for raw in entry.get("mutates") or []:
                self.link_asserted(OUTCOME_LABEL, outcome_name, "MUTATES",
                                   raw, relpath,
                                   f"possible_outcomes.{outcome}")
        # An attested procedure without a hash tripwire is drift waiting
        # to happen — surface it, softly.
        if not procedures.specified_in_of(proc_spec)[2]:
            self.note(INFO, Category.PROCEDURE, relpath, proc_name,
                      "attested procedure has no approved_hash — asserted "
                      "signature can drift from its prose body silently")

    def link_asserted(self, from_label, from_name, edge_type, raw_target,
                      relpath, location):
        """Resolve one asserted target and emit its edge. edge_type=None
        derives the type from the resolved label (assigns_edge_type) — the
        assignment path, where the domain is whatever the target names."""
        resolved_label, detail = self.resolve_any(str(raw_target).strip())
        if resolved_label is None:
            self.note(WARNING, Category.DANGLING_REF, relpath, location,
                      f"{from_name} -> {edge_type or 'assignment'}: "
                      f"{detail}; edge dropped")
            return
        if edge_type is None:
            edge_type = assigns_edge_type(resolved_label)
        self.graph.edges.append(make_edge(
            edge_type, from_label, from_name, resolved_label, detail))

    def seed_archetypes(self):
        """Create the Archetype nodes early (before relationships) so that
        "Archetype: X" targets — e.g. Judgment rows ABOUT a concept — can
        resolve. build_metamodel later re-ensures them (idempotent) and adds
        the INSTANCE_OF tower."""
        for concept, spec in self.ontology.concepts.items():
            spec = spec or {}
            props = {"doc": spec["doc"].strip()} if spec.get("doc") else {}
            self.graph.ensure_node(ARCHETYPE_LABEL, concept, **props)
        for label, spec in self.ontology.nodes.items():
            if isinstance(spec, dict) and concept_bindings(spec):
                props = {"doc": spec["doc"].strip()} \
                    if spec.get("doc") else {}
                self.graph.ensure_node(ARCHETYPE_LABEL, label, **props)

    def build_metamodel(self):
        """The Archetype tower: concepts become nodes, values point up.

        (Ruby:Gem)-[:INSTANCE_OF]->(Gem:Archetype)
          -[:INSTANCE_OF]->(Gameplay Concept:Archetype)
          -[:INSTANCE_OF]->(Concept:Archetype)
        Ordered labels additionally get rank properties, bidirectional
        PRECEDES/FOLLOWS ladder edges, and INSTANCE_OF -> the Ordered facet.
        """
        def instance_edge(from_label, from_name, to_name):
            self.graph.edges.append(make_edge(
                "INSTANCE_OF", from_label, from_name,
                ARCHETYPE_LABEL, to_name))

        def declared_in(name, layer):
            # DECLARED_IN: which schema layer declared this citizen —
            # the two-layer doctrine made queryable (the self-description round)
            self.graph.edges.append(make_edge(
                "DECLARED_IN", ARCHETYPE_LABEL, name,
                ARCHETYPE_LABEL, layer))

        for concept, spec in self.ontology.concepts.items():
            spec = spec or {}
            declared_in(concept,
                        "Metaontology"
                        if concept in self.ontology.kernel_names
                        else "Ontology")
            props = {"doc": spec["doc"].strip()} if spec.get("doc") else {}
            if spec.get("stub"):
                # recognized-but-unmodeled: the queryable intake worklist
                props["stub"] = True
            if spec.get("temporal"):
                # a Segment Scheme that is a time axis — queryable, so an
                # agent can ask "which scheme is this corpus's clock?"
                props["temporal"] = True
            if spec.get("recursive"):
                # a segment type whose instances nest within their own
                # type (Sections hold sub-Sections) — queryable, and the
                # nesting check relaxes same-type PART_OF for it
                props["recursive"] = True
            self.graph.ensure_node(ARCHETYPE_LABEL, concept, **props)
            parent = spec.get("instance_of")
            if parent:
                instance_edge(ARCHETYPE_LABEL, concept, parent)
            # Genuine taxonomy (`subtypes:`) is emitted in the second
            # pass below, once every concept node exists — a kernel kind
            # may be declared after the concept it is a kind of.
        # Archetype-level ladders (e.g. Completeness: Cited < Attested <
        # Transcribed) — same Ordered treatment value labels get. A
        # SECOND pass, after every concept node exists: a ladder is free
        # to be declared above its members (the kernel's own Completeness
        # is), and the member filter below must see them all — inside the
        # first loop it silently dropped any member declared later.
        for concept, spec in self.ontology.concepts.items():
            spec = spec or {}
            # Genuine taxonomy: `subtypes:` names citizens that are KINDS
            # of this concept. Targets may be citizens born only by delta,
            # so a from-sources build drops them as dangling; derivation
            # over canon emits them.
            for sub in spec.get("subtypes") or []:
                sub_label, detail = self.resolve_any(sub)
                if sub_label is None:
                    self.note(WARNING, Category.DANGLING_REF,
                              str(self.ontology.path), f"concepts.{concept}",
                              f"subtype {detail}; SUBTYPE_OF edge dropped")
                else:
                    self.graph.edges.append(make_edge(
                        "SUBTYPE_OF", sub_label, detail,
                        ARCHETYPE_LABEL, concept))
            if spec.get("ordered") and spec.get("values"):
                instance_edge(ARCHETYPE_LABEL, concept, ORDERED_CONCEPT)
                ladder = [value for value in spec["values"]
                          if (ARCHETYPE_LABEL, value) in self.graph.nodes]
                for rank, value in enumerate(ladder):
                    self.graph.nodes[(ARCHETYPE_LABEL, value)]["rank"] = rank
                for lower, higher in zip(ladder, ladder[1:]):
                    self.graph.edges.append(make_edge(
                        "PRECEDES", ARCHETYPE_LABEL, lower,
                        ARCHETYPE_LABEL, higher))
                    self.graph.edges.append(make_edge(
                        "FOLLOWS", ARCHETYPE_LABEL, higher,
                        ARCHETYPE_LABEL, lower))

        # Self-description (the self-description round, per the schema-on-graph ruling): the
        # graph answers "what metaontology were you built with, and
        # what's your ontology?" — two schema-anchor citizens carrying
        # version + content fingerprint, rooted under Provenance (they
        # are knowledge-carriers: the schema's own artifacts). The
        # metaontology YAML remains the seed file; these citizens are
        # what a fresh connection interrogates.
        for rank, (name, identity_path, version) in enumerate((
                ("Metaontology", self.ontology.meta.get("path"),
                 self.ontology.meta.get("version")),
                ("Ontology", str(self.ontology.path),
                 (self.ontology.raw or {}).get("version")))):
            props = {"doc": f"The {name.lower()} this graph was built "
                            "with — version and content fingerprint.",
                     "rank": rank}  # load order: kernel beneath domain
            if version is not None:
                props["version"] = version
            if name == "Ontology":
                # The version-tag ruling: the optional free-text tag rides the anchor so a
                # fresh connection can read it; the ledger holds numbers
                tag = (self.ontology.raw or {}).get("tag")
                if tag:
                    props["tag"] = tag
            if identity_path:
                try:
                    props["fingerprint"] = hashlib.sha256(
                        Path(identity_path).read_bytes()).hexdigest()
                except OSError:
                    pass  # unreadable seed already surfaced at load
            self.graph.ensure_node(ARCHETYPE_LABEL, name, **props)
            instance_edge(ARCHETYPE_LABEL, name, "Provenance")
            instance_edge(ARCHETYPE_LABEL, name, "[Schema Layer]")

        for label, spec in self.ontology.nodes.items():
            concepts = concept_bindings(spec)
            if not concepts:
                continue
            props = {"doc": spec["doc"].strip()} if spec.get("doc") else {}
            self.graph.ensure_node(ARCHETYPE_LABEL, label, **props)
            if label not in self.ontology.kernel_names and \
                    label not in self.ontology.concepts:
                # labels are project-declared — unless the label IS a
                # concept's binding (kernel: Procedure, the Judgment
                # quartet; project: a same-named concept like Verbatim):
                # then the citizen is already layered by the concept loop
                declared_in(label, "Ontology")
            for concept in concepts:
                if concept != label:  # a kernel binding is not its own instance
                    instance_edge(ARCHETYPE_LABEL, label, concept)
            # Genuine taxonomy with a label-backed parent: `subtypes:` on
            # a node label names citizens that are KINDS of it, same as
            # on a concept entry (a Beast catalog whose kinds include the
            # Winged Beast concept). Same dangling rule: delta-born
            # targets drop in a from-sources build, derivation over
            # canon emits them.
            for sub in spec.get("subtypes") or []:
                sub_label, detail = self.resolve_any(sub)
                if sub_label is None:
                    self.note(WARNING, Category.DANGLING_REF,
                              str(self.ontology.path), f"nodes.{label}",
                              f"subtype {detail}; SUBTYPE_OF edge dropped")
                else:
                    self.graph.edges.append(make_edge(
                        "SUBTYPE_OF", sub_label, detail,
                        ARCHETYPE_LABEL, label))
            if spec.get("ordered"):
                instance_edge(ARCHETYPE_LABEL, label, ORDERED_CONCEPT)
        # Embed BEFORE the instance rows fold declared memberships: the
        # concept-vs-label discriminator (is_concept_archetype) reads
        # spec_json, which this embed sets — the fold must never run on a
        # schema stratum that has not been embedded yet.
        embed_schema_stratum(self.ontology, self.graph)
        self.derive_instance_metamodel()

    def derive_instance_metamodel(self):
        """The instance-level metamodel rows — the only metamodel
        stratum that still re-derives since the inversion: every
        citizen of a concept-bound label gets INSTANCE_OF -> its label's
        Archetype, and Ordered labels get their value-ladder edges from
        the rank ground props. The schema stratum above (Archetype
        citizens, the tower, DECLARED_IN, SUBTYPE_OF, Archetype-level
        ladders) is ground — preserved by strip_derived, never rebuilt
        here."""
        for label, spec in self.ontology.nodes.items():
            if not isinstance(spec, dict) or not concept_bindings(spec):
                continue
            for (node_label, name) in list(self.graph.nodes):
                if node_label == label:
                    self.graph.edges.append(make_edge(
                        "INSTANCE_OF", label, name, ARCHETYPE_LABEL, label))
            if spec.get("ordered"):
                ladder = self.ladder_of(label)
                for lower, higher in zip(ladder, ladder[1:]):
                    self.graph.edges.append(make_edge(
                        "PRECEDES", label, lower, label, higher))
                    self.graph.edges.append(make_edge(
                        "FOLLOWS", label, higher, label, lower))
        # Every citizen whose label has a schema row is a direct instance
        # of that row — a kernel concept's own label (a [Decision], a
        # [File Location]) and a world's concept used as a label (a
        # re-homed row under a declared kind) alike; concept-bound project
        # labels were handled above. A declared label means membership,
        # for every declared label; the fold below then climbs from it.
        from .ontology import MACHINE_LABELS
        declared_labels = {name for (label, name) in self.graph.nodes
                           if label == ARCHETYPE_LABEL
                           and name not in self.ontology.nodes
                           and name not in MACHINE_LABELS}
        for (node_label, name) in list(self.graph.nodes):
            if node_label in declared_labels and node_label != ARCHETYPE_LABEL:
                self.graph.edges.append(make_edge(
                    "INSTANCE_OF", node_label, name, ARCHETYPE_LABEL,
                    node_label))
        # The taxonomy-membership rule: a citizen's INSTANCE_OF folds up
        # its label's SUBTYPE_OF chain — a row of a kind is an instance of
        # every concept that kind is a kind of. Concept-level SUBTYPE_OF
        # only (Archetype -> Archetype); cycles are refused at the schema
        # ceremony, and a walk guards against one regardless.
        parents = {}
        for edge in self.graph.edges:
            if edge.type == "SUBTYPE_OF" and edge.from_label == ARCHETYPE_LABEL \
                    and edge.to_label == ARCHETYPE_LABEL:
                parents.setdefault(edge.from_name, set()).add(edge.to_name)
        if parents:
            folded = []
            for (node_label, name) in list(self.graph.nodes):
                if node_label == ARCHETYPE_LABEL or node_label not in parents:
                    continue
                seen, frontier = set(), list(parents.get(node_label, ()))
                while frontier:
                    ancestor = frontier.pop()
                    if ancestor in seen:
                        continue
                    seen.add(ancestor)
                    folded.append(make_edge("INSTANCE_OF", node_label, name,
                                            ARCHETYPE_LABEL, ancestor))
                    frontier.extend(parents.get(ancestor, ()))
            self.graph.edges.extend(folded)
        self.fold_declared_memberships()

    def fold_declared_memberships(self):
        """Fold each authored DECLARED_MEMBER_OF ground edge into the
        citizen's derived INSTANCE_OF — the declared-membership pattern's
        second input to membership (a citizen's final membership is the
        UNION of its roster binding and its authored declarations). Runs
        after the roster rows above, and identically in extract() (a
        from-sources build carries no such edges — a no-op) and derive()
        (over canon, where authored memberships live), so the two stay a
        fixpoint.

        Per authored edge (citizen -> target Archetype):
        - target missing or not a Concept-rooted Archetype: DROP with a
          WARNING (second belt behind the delta lint — a canon that
          drifted, or a from-sources build whose target is not yet born);
        - target already roster-reachable from the citizen's label through
          the tower: SKIP with an INFO naming the redundancy (the tower
          stays the single home for roster-implied membership);
        - otherwise EMIT (citizen)-[:INSTANCE_OF]->(target). Dedup is
          automatic (edges are hashable, deduped at load/export)."""
        authored = [edge for edge in self.graph.edges
                    if edge.type == MEMBERSHIP_EDGE_TYPE]
        for edge in authored:
            citizen, target = edge.from_name, edge.to_name
            if edge.from_label == ARCHETYPE_LABEL:
                # Second belt behind the lint: an Archetype-sourced edge
                # would induce an Archetype->Archetype INSTANCE_OF, which
                # classifies as schema GROUND — a fabricated tower edge
                # that survives the strip and corrupts the fixpoint.
                self.note(
                    WARNING, Category.DANGLING_REF, str(self.ontology.path),
                    f"{citizen} -[:{MEMBERSHIP_EDGE_TYPE}]-> {target}",
                    f"a {MEMBERSHIP_EDGE_TYPE} edge runs FROM the Archetype "
                    f"'{citizen}' — that is the tower/roster shape, not an "
                    "authored membership; the edge is ignored and no "
                    "INSTANCE_OF is derived from it.")
                continue
            if not is_concept_archetype(self.graph, target):
                self.note(
                    WARNING, Category.DANGLING_REF, str(self.ontology.path),
                    f"{citizen} -[:{MEMBERSHIP_EDGE_TYPE}]-> {target}",
                    f"{citizen} declares membership in {target}, which is "
                    "not an existing Concept-rooted Archetype; the "
                    "membership edge is dropped and no INSTANCE_OF is "
                    "derived from it.")
                continue
            if target in self.tower_reachable(edge.from_label):
                self.note(
                    INFO, Category.ONTOLOGY, str(self.ontology.path),
                    f"{citizen} -[:{MEMBERSHIP_EDGE_TYPE}]-> {target}",
                    f"{citizen} is already an instance of {target} through "
                    f"its {edge.from_label} binding; the declared membership "
                    "is redundant and adds no INSTANCE_OF.")
                continue
            self.graph.edges.append(make_edge(
                "INSTANCE_OF", edge.from_label, citizen,
                ARCHETYPE_LABEL, target))

    def tower_reachable(self, label):
        """Every Archetype name reachable from `label`'s Archetype through
        the INSTANCE_OF tower (Archetype -> Archetype) — the concepts a
        citizen of `label` is roster-implied to be an instance of. Empty
        when `label` is not a concept-bound label (no Archetype, no tower)."""
        reachable = set()
        frontier = [label]
        while frontier:
            current = frontier.pop()
            for edge in self.graph.edges:
                if (edge.type == "INSTANCE_OF"
                        and edge.from_label == ARCHETYPE_LABEL
                        and edge.from_name == current
                        and edge.to_label == ARCHETYPE_LABEL
                        and edge.to_name not in reachable):
                    reachable.add(edge.to_name)
                    frontier.append(edge.to_name)
        return reachable


def strip_derived(graph):
    """A copy holding only the ground layer: machine-materialized nodes
    out, derived edges out — but ground edges that merely touch a
    machine node (a Judgment ABOUT a concept) stay, because derive
    recreates their endpoints. The schema stratum (the schema inversion) is GROUND:
    Archetype citizens, the tower, DECLARED_IN, SUBTYPE_OF, and
    Archetype-level ladders all survive the strip — they are authored
    truth, not derivation. Every ground prop, receipts included,
    survives. derive() rebuilds exactly what this removes."""
    from .ontology import MACHINE_LABELS, is_derived_edge
    ground = GraphData()
    for (label, name), props in graph.nodes.items():
        if label not in MACHINE_LABELS:
            ground.ensure_node(label, name, **dict(props))
    ground.edges = [
        edge for edge in graph.edges if not is_derived_edge(edge)]
    return ground


def schema_only(graph):
    """A copy holding ONLY the schema stratum: the Archetype citizens and
    their schema edges (DECLARED_IN, SUBTYPE_OF, and the schema-level
    INSTANCE_OF/PRECEDES/FOLLOWS FROM an Archetype). No ground facts, no
    machine layers — the seed a fresh branch is grown from.

    The complement view to strip_derived, over the same stratum
    predicates: strip_derived keeps the schema stratum PLUS ground; this
    keeps the schema stratum ALONE. Because is_derived_edge maps a
    stratified edge from an Archetype to the schema side, the kept edge
    set is exactly DECLARED_IN + SUBTYPE_OF + Archetype-level ladders —
    every one with both endpoints an Archetype citizen."""
    from .ontology import SCHEMA_LABELS, is_derived_edge
    seed = GraphData()
    for (label, name), props in graph.nodes.items():
        if label in SCHEMA_LABELS:
            seed.ensure_node(label, name, **dict(props))
    seed.edges = [
        edge for edge in graph.edges
        if edge.from_label in SCHEMA_LABELS
        and edge.to_label in SCHEMA_LABELS
        and not is_derived_edge(edge)]
    return seed


def embed_schema_stratum(ontology, graph):
    """Ride the ontology.yaml specs the derive-era passes still need onto
    the schema stratum as verbatim whole-spec embeddings (the schema inversion, the
    inversion's migration substance, the ontology-embedding precedent). Additive
    only — every embedded value comes straight from the loaded ontology,
    so a from-sources build (this runs at the end of build_metamodel) and
    the one-time migration over the committed backup produce identical
    props; extract() and derive() stay a fixpoint.

    - each label Archetype citizen gets its nodes.<label> spec as spec_json
      (sorted keys), minus the render-only keys rendered_view /
      rendered_views: those are loader- AND derive-inert (the extractor
      ignores them), so they ride BESIDE the spec instead — the row's
      rendered_views_json, one JSON list of every view the label
      declares. The loader and deriver never read that prop, which is
      what keeps a render-mapping change inert; render_tables, the
      round-trip judge's column typing, and a corpus's instruments read
      it back through ontology_from_graph. A label declaring no view
      carries no such prop.
    - each concept Archetype gets its surface_forms / pending_instances —
      the term-index inputs that are not otherwise ground on the graph
      (doc/stub/temporal/recursive already ride as props, subtypes as
      SUBTYPE_OF edges, ordered/values as the tower + rank props);
    - the Ontology anchor gets the whole enums and defaults sections plus
      the sorted non-prose sources.

    Returns the same graph, mutated in place.
    """
    for label, spec in ontology.nodes.items():
        if not (isinstance(spec, dict) and concept_bindings(spec)):
            continue
        node = graph.nodes.get((ARCHETYPE_LABEL, label))
        if node is not None:
            embedded = {key: value for key, value in spec.items()
                        if key not in ("rendered_view", "rendered_views")}
            node["spec_json"] = json.dumps(embedded, sort_keys=True)
            views = rendered_views_of(spec)
            if views:
                node[RENDERED_VIEWS_PROP] = json.dumps(views, sort_keys=True)
    for concept, spec in ontology.concepts.items():
        spec = spec or {}
        node = graph.nodes.get((ARCHETYPE_LABEL, concept))
        if node is None:
            continue
        if spec.get("surface_forms"):
            node["surface_forms"] = list(spec["surface_forms"])
        if spec.get("pending_instances"):
            node["pending_instances"] = list(spec["pending_instances"])
    anchor = graph.nodes.get((ARCHETYPE_LABEL, "Ontology"))
    if anchor is not None:
        anchor["enums_json"] = json.dumps(ontology.enums, sort_keys=True)
        anchor["defaults_json"] = json.dumps(ontology.defaults, sort_keys=True)
        anchor["non_prose_sources"] = sorted(ontology.non_prose_sources())
    return graph


def procedure_roster_findings(ontology, graph):
    """Every procedure program file the schema registers must have its
    citizen in the graph being checked. Re-derivation lifts a
    procedure's steps and outcomes from a body already on the graph — it
    never adds the procedure node itself, so a file that shipped without
    its citizen stays invisible (its steps and links simply absent) until
    this roster check names it. Matched by source_path: the citizen a
    file produces carries the file's path. One ERROR per orphaned file,
    per the error doctrine.

    The roster is a completeness census of a FINISHED line: a branch
    mid-rebuild has not yet absorbed the registered programs by design,
    so branch-scoped applies treat these findings as advisory (the
    Category.ROSTER tag is what lets them). The check returns to full
    strength when a branch stands for succession."""
    registered = []
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict) or \
                node_reader(spec) != Reader.PROCEDURE_YAML:
            continue
        for relpath in source_files_of(spec):
            registered.append((label, relpath))
    present = {(label, props.get("source_path"))
               for (label, _name), props in graph.nodes.items()
               if props and props.get("source_path")}
    findings = []
    for label, relpath in registered:
        if (label, relpath) not in present:
            findings.append(Finding(
                ERROR, Category.ROSTER, relpath, "-",
                f"Attempted to verify the procedure roster with "
                f"{len(registered)} registered program files. Failed: "
                f"{relpath} has no {label} citizen — the file shipped "
                "without its node. Land the citizen through the delta "
                "path.",
                # the roster category's one earned finer code: a gap is
                # a registered file with no citizen, and the delta gate
                # already speaks this code
                code="roster-gap",
                remedy="Land the citizen through the delta path."))
    return findings


def gate_roster_findings(scratch, base_dir):
    """The roster as the delta gate runs it: against the schema the
    round itself carries (reconstructed from scratch), so a round that
    releases a program label's files — every citizen carrying its body,
    the registration leaving the spec — is not accused of shipping files
    without their citizens by the schema it is retiring."""
    from .ontology import ontology_from_graph
    ontology = ontology_from_graph(scratch, base_dir)
    return procedure_roster_findings(ontology, scratch)


def derive(ontology, graph):
    """Recompute every derived layer over an existing graph — the
    post-flip half of extraction (build reads sources once, at
    bootstrap; derive reads the graph, after every applied delta).
    extract() and derive() share one derivation codepath, so applying
    a delta and re-deriving equals what a from-sources build would
    have produced. Returns (GraphData, findings)."""
    extractor = Extractor(ontology)
    extractor.graph = strip_derived(graph)
    extractor.rebuild_pending_procedures()
    extractor.derive_markdown_rels()
    extractor.derive_effect_references()
    extractor.link_procedures()
    # The schema stratum is ground since the inversion: derive
    # never rebuilds Archetype citizens or their edges — seed_archetypes
    # and build_metamodel run only in the from-sources bootstrap. Only
    # the instance-level metamodel re-derives here.
    extractor.derive_instance_metamodel()
    extractor.findings.extend(
        procedure_roster_findings(ontology, extractor.graph))
    # an unknown label is not nothing: a citizen whose label has no
    # schema row gets no membership and its derived connections would
    # silently vanish — refuse by name instead
    extractor.findings.extend(orphan_citizen_findings(extractor.graph))
    # a spec's declared reader must be a kind the engine knows — an
    # unknown one would mean bodies that silently never lift
    extractor.findings.extend(unknown_reader_findings(extractor.graph))
    return extractor.graph, extractor.findings


def unknown_reader_findings(graph):
    """ERROR per schema row whose spec declares a reader the engine
    does not know. The yaml loader once validated this; post-closure
    the schema stratum is the only declaration surface, and an unknown
    reader would mean the label's citizens' bodies silently never lift
    — silence reading as held."""
    import json as json_mod

    from .ontology import Reader
    known = sorted(str(kind) for kind in Reader)
    findings = []
    for (label, name), props in sorted(graph.nodes.items()):
        if label != ARCHETYPE_LABEL or not props.get("spec_json"):
            continue
        try:
            spec = json_mod.loads(props["spec_json"])
        except ValueError:
            continue  # a malformed embedding has its own reconstruction fate
        reader = spec.get("reader") if isinstance(spec, dict) else None
        if not reader or reader in known:
            continue
        findings.append(Finding(
            ERROR, Category.ONTOLOGY, "canon", f"label {name}",
            f"Attempted to read '{name}''s program bodies with reader "
            f"'{reader}'. Failed due to: no such reader — the label's "
            "citizens' bodies would never lift, and the engine never "
            "treats a citizen as nothing. Declare a known reader "
            f"({', '.join(known)}) or remove the reader from the spec.",
            code="label-reader-unknown",
            remedy="Declare a known reader, or remove the reader from "
                   "the spec."))
    return findings


def orphan_citizen_findings(graph):
    """ERROR per citizen label that has no Archetype row and is neither
    a machine label nor the schema stratum itself — the lesser default
    (treat it as nothing) is exactly what the bright line forbids."""
    from .ontology import MACHINE_LABELS, SCHEMA_LABELS
    from .workspace import WORKSPACE_LABEL
    declared = {name for (label, name) in graph.nodes
                if label == ARCHETYPE_LABEL}
    orphans = {}
    for (label, name) in graph.nodes:
        if label in SCHEMA_LABELS or label in MACHINE_LABELS \
                or label == WORKSPACE_LABEL or label in declared:
            continue
        orphans.setdefault(label, []).append(str(name))
    findings = []
    for label in sorted(orphans):
        names = sorted(orphans[label])
        sample = ", ".join(f"'{n}'" for n in names[:3])
        findings.append(Finding(
            ERROR, Category.ONTOLOGY, "canon", f"label {label}",
            f"Attempted to derive over {len(names)} citizen"
            f"{'s' if len(names) != 1 else ''} under '{label}' ({sample}"
            f"{', …' if len(names) > 3 else ''}). Failed due to: no schema "
            f"row declares '{label}' — an unknown label would mean no "
            "membership and silently dropped connections, and the engine "
            "never treats a citizen as nothing. Declare the label (a "
            "label birth at the ceremony) or move the citizens under one "
            "that exists (a declared move).",
            code="citizen-label-undeclared",
            remedy="Declare the label, or move the citizens under one that "
                   "exists."))
    return findings
