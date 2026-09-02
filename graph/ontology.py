"""Load and sanity-check graph/ontology.yaml — the owner-governed schema.

The ontology is interpreted generically: this module verifies that the file
is coherent (known keys, referenced CSV columns exist, parser names are
registered, properties are declared in the catalog) and reports problems as
Findings rather than crashing wherever possible. Structural problems are
'error' severity: they block loading into Neo4j but never crash validation.
"""

import csv
import enum
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class Severity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Back-compat aliases: the rest of the codebase (and tests) import these.
ERROR = Severity.ERROR
WARNING = Severity.WARNING
INFO = Severity.INFO


class Category(enum.StrEnum):
    """Finding categories — the section keys of the validation report."""
    DANGLING_REF = "dangling-ref"
    ENUM_VIOLATION = "enum-violation"
    DUPLICATE_KEY = "duplicate-key"
    EMPTY_KEY = "empty-key"
    UNPARSED_CELL = "unparsed-cell"
    TYPE_CONVERSION = "type-conversion"
    CATALOG_VIOLATION = "catalog-violation"
    OVERLAY = "overlay"
    ONTOLOGY = "ontology"
    UNMAPPED_CSV = "unmapped-csv"
    PROCEDURE = "procedure"
    ROSTER = "roster"
    UNRESOLVED_TERM = "unresolved-term"
    ANSWER_KEY = "answer-key"


class Reader(enum.StrEnum):
    """Node-origin readers: how a source: file is interpreted."""
    CSV_ROWS = "csv_rows"
    MARKDOWN_SECTIONS = "markdown_sections"
    PROCEDURE_YAML = "procedure_yaml"  # explicit only — never extension-inferred


class RelParser(enum.StrEnum):
    """Named relationship-parser strategies referencable from the ontology."""
    SIZE_MATRIX = "size_matrix"
    PREREQUISITES = "prerequisites"
    STAGED_BLOCKS = "staged_blocks"
    PART_OF = "part_of"
    MENTIONS = "mentions"
    EFFECTS_TABLE = "effects_table"


class OnMissing(enum.StrEnum):
    PLACEHOLDER = "placeholder"
    REPORT = "report"


class PropType(enum.StrEnum):
    TEXT = "text"
    INT = "int"
    BOOL = "bool"
    FLOAT = "float"


ENUM_TYPE_PREFIX = "enum:"


@dataclass
class Finding:
    severity: str
    category: str
    file: str
    location: str
    detail: str


KNOWN_TOP_KEYS = {"version", "tag", "enums", "defaults", "concepts",
                  "facets", "nodes", "answer_keys", "rejected_terms",
                  # where corpus material lives, and which of its prose
                  # sources are indexes rather than prose (the coverage
                  # sweeps read both — no directory or filename is hardcoded)
                  "content_roots", "non_prose_sources"}
KNOWN_META_KEYS = {"version", "roots", "facets", "concepts"}
KNOWN_ENUM_KEYS = {"source", "column", "values", "ordered"}
# ordered+values: an archetype-level ladder (e.g. the engine's Completeness
# levels Cited < Attested < Transcribed) — values name sibling concepts.
# stub: recognized-but-unmodeled concept (queryable intake worklist).
# surface_forms: extra term spellings that resolve to this citizen
# (auto-plurals are generated; list only irregulars/synonyms).
# pending_instances: known FUTURE value citizens of this system — their
# terms resolve to the concept that will own them until it is mapped.
# temporal: a Segment Scheme instance that is a time axis; recursive: a
# segment type whose instances may nest within their own type (see the
# kernel's Segment Scheme facet doc).
# subtypes: names of citizens that are KINDS of this concept — emits
# (citizen)-[:SUBTYPE_OF]->(concept Archetype), the kernel's genuine-
# taxonomy relation (derived at build_metamodel; never authored, and
# distinct from the INSTANCE_OF tower).
KNOWN_CONCEPT_KEYS = {"instance_of", "doc", "ordered", "values",
                      "stub", "surface_forms", "pending_instances",
                      "temporal", "recursive", "subtypes"}

# The engine's own ontology: kernel roots + common facet library. Loaded
# beneath every project ontology.
METAONTOLOGY_PATH = Path(__file__).resolve().parent / "metaontology.yaml"
FACET_ROOT = "Facet"
CONCEPT_ROOT = "Concept"
ANY_LABEL = "any"   # rel `to: any` = label-agnostic target resolution
KNOWN_NODE_KEYS = {"source", "key", "values", "implicit", "aliases", "overlay",
                   "catalog", "properties", "relationships",
                   "concept", "ordered", "reader", "surface_forms",
                   "pending_instances", "property_tables", "fingerprint",
                   "doc", "subtypes", "rendered_view", "rendered_views"}
# rendered_view: a LOADER-INERT render/judge-only mapping (Leg 2, the table-rendering tier) for
# an implicit label whose citizens arrive by delta but whose rendered
# authority is a CSV. Same shape as a source mapping — a csv path, its key
# column, optional name_template ("Level {key}") for citizen-name-vs-key
# mismatches, properties: (catalog prop -> CSV column) and relationships:
# (edge-carried columns). Consumed ONLY by graph/render_tables.py and the
# round-trip judge's column typing; the loader/extractor ignore it entirely.
KNOWN_RENDERED_VIEW_KEYS = {"source", "key", "name_template",
                           "properties", "relationships",
                           # Fix 2/3/5: display template on the key cell, a
                           # `labels:` list of per-label contributors (a
                           # multi-label view), and a `matrix:` grammar name
                           # for whole-table matrix inversions.
                           "display", "labels", "matrix"}
# One contributor of a multi-label rendered_view: a label plus its own maps,
# an optional membership filter (names: explicit subset, or only_with: render
# only citizens carrying at least one of these properties), and its own
# name_template/display.
KNOWN_VIEW_ENTRY_KEYS = {"label", "only_with", "names", "name_template",
                        "display", "properties", "relationships"}
# subtypes: on a node label — same genuine-taxonomy relation as on a
# concept entry, for when the PARENT of a kind-of link is a label-backed
# home rather than a plain concept (a Beast catalog whose kinds include
# the Winged Beast concept). Emits (citizen)-[:SUBTYPE_OF]->(label
# Archetype) at build_metamodel; derived, never authored.
# doc: prose describing the label as a whole, carried onto its Archetype
# node — label-level knowledge belongs on the graph, not in YAML comments.
# fingerprint: true on a values: label whose values are files — each
# citizen gets a content-hash property (the durable identity anchor for
# canon-side artifact + span references).
# property_tables: additional CSVs keyed by the same names, contributing
# properties to this label's existing nodes (one label, many tables —
# the owner's data keeps its shape; the engine understands the links).
KNOWN_PROPERTY_TABLE_KEYS = {"source", "key", "properties"}

# Node-origin readers: how a `source:` file is interpreted. `reader:` names
# one explicitly; otherwise it is inferred from the file extension. Formats
# are ingestion mechanics, never facets — the concept is unchanged by how its
# bytes arrive.
# (.value sets rather than member sets purely so error messages render as
# plain strings.)
KNOWN_READERS = frozenset(reader.value for reader in Reader)
KNOWN_REL_PARSERS = frozenset(parser.value for parser in RelParser)
READER_BY_EXTENSION = {".csv": Reader.CSV_ROWS,
                       ".md": Reader.MARKDOWN_SECTIONS,
                       ".markdown": Reader.MARKDOWN_SECTIONS}
# File suffixes the engine reads as prose (markdown_sections) — the
# glossary sweep's file set is prose, drawn from the declarations.
MARKDOWN_SUFFIXES = frozenset(
    ext for ext, reader in READER_BY_EXTENSION.items()
    if reader == Reader.MARKDOWN_SECTIONS)


def source_files_of(spec):
    """A node spec's source as a list (accepts string or list)."""
    source = spec.get("source")
    if source is None:
        return []
    return [source] if isinstance(source, str) else list(source)


def rendered_views_of(spec):
    """Every rendered_view a node declares: the single `rendered_view:` plus
    any in a `rendered_views:` list (one implicit label may be the render
    anchor of several chapter tables — e.g. one shared baseline
    rides several profile tables at once). Loader-inert, all of
    them (the table-rendering tier)."""
    if not isinstance(spec, dict):
        return []
    views = []
    single = spec.get("rendered_view")
    if isinstance(single, dict):
        views.append(single)
    for view in spec.get("rendered_views") or []:
        if isinstance(view, dict):
            views.append(view)
    return views


def _referenced_tables(obj):
    """Every `table:` file named anywhere in an answer-key spec (they nest
    under components/lookups/variants/gates). Recursive so no level is
    missed."""
    found = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("table"), str):
            found.add(obj["table"])
        for value in obj.values():
            found |= _referenced_tables(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= _referenced_tables(value)
    return found


def node_reader(spec):
    """Resolve a node spec's reader: explicit `reader:` wins (with or
    without a `source:` — a graph-native prose label has no source file;
    its bodies live on the nodes), else inferred from the first source
    file's extension. None if unresolvable."""
    if not isinstance(spec, dict):
        return None
    if spec.get("reader"):
        return spec["reader"]
    if not spec.get("source"):
        return None
    files = source_files_of(spec)
    if files and isinstance(files[0], str):
        return READER_BY_EXTENSION.get(Path(files[0]).suffix.lower())
    return None
ARCHETYPE_LABEL = "Archetype"
STEP_LABEL = "Step"
OUTCOME_LABEL = "Outcome"
# The kernel's own concept label for procedures — ground citizens under
# it may be graph-native (no source file; see link_native_procedures).
KERNEL_PROCEDURE_LABEL = "Procedure"
# Labels the engine materializes itself; projects may not declare them.
RESERVED_LABELS = {ARCHETYPE_LABEL: "used by the metamodel concepts: section",
                   STEP_LABEL: "used by the procedure_yaml lift",
                   OUTCOME_LABEL: "used by the procedure signature projection"}
ORDERED_CONCEPT = "Ordered"
# The machine's own layers (the ground-facts lint, graph/delta.py): edge
# types the derivation computes and labels it materializes. Agents
# authoring ground facts in scratch may never write these — a hand-written
# copy of a derived fact drifts (see graph/design/agentic-etl.md).
MACHINE_LABELS = frozenset({STEP_LABEL, OUTCOME_LABEL})
# The schema stratum (the schema inversion): the citizens and edges that
# ARE the graph's schema — Archetype nodes, the layer boundary, the
# taxonomy. Ground truth since the inversion: strip_derived preserves
# them, derive never rebuilds them, and the graph — not ontology.yaml —
# is what post-bootstrap commands read the schema from. Authoring them
# through the delta path waits on the schema-delta ceremony;
# until it lands the lint refuses them by name (the schema freeze).
SCHEMA_LABELS = frozenset({ARCHETYPE_LABEL})
SCHEMA_EDGE_TYPES = frozenset({"DECLARED_IN", "SUBTYPE_OF"})
# Edge types that exist at BOTH strata, split by endpoints: rows from an
# Archetype (the tower, a concept ladder) are schema ground; rows from a
# citizen (its INSTANCE_OF, a value ladder) re-derive. is_derived_edge
# is the one place that split is decided.
STRATIFIED_EDGE_TYPES = frozenset({"INSTANCE_OF", "PRECEDES", "FOLLOWS"})
DERIVED_EDGE_TYPES = frozenset({
    # docs machinery
    "MENTIONS", "PART_OF",
    # procedure lift
    "FIRST_STEP", "NEXT", "CASE", "THEN", "OTHERWISE", "MATCHES",
    "REFERENCES", "SPECIFIED_IN", "KNOWN_AT",
    # signature projection. The ASSIGNS_<LABEL> family (one edge type per
    # assignable value domain) is derived by the projection and matched by
    # the startswith("ASSIGNS_") guards in delta.py/proposal.py/extract.py
    # — never a literal here, so a second corpus's domains need no edit.
    "READS", "MUTATES", "CALLS", "CONSULTS",
    "HAS_POSSIBLE_OUTCOME", "ENDS_AT",
})
# What ground-fact authoring may never write: the machine layers (they
# re-derive) and, until the schema-delta ceremony, the schema stratum (frozen). These are
# the lint's sets; the strata sets above are the strip/derive boundary.
UNAUTHORABLE_LABELS = MACHINE_LABELS | SCHEMA_LABELS
UNAUTHORABLE_EDGE_TYPES = (DERIVED_EDGE_TYPES | SCHEMA_EDGE_TYPES
                           | STRATIFIED_EDGE_TYPES)

# The declared-membership pattern: an AUTHORED ground edge from a citizen
# to a Concept-rooted Archetype, carrying a required `basis` rationale,
# that derivation folds into the citizen's INSTANCE_OF. It is deliberately
# absent from every UNAUTHORABLE / DERIVED / SCHEMA / STRATIFIED set above
# — that omission is the point: this is the one metamodel-touching edge a
# designer writes by hand. It is plain ground: strip_derived keeps it,
# is_derived_edge returns False for it, and the lint permits it (guarding
# only its shape). The INSTANCE_OF it induces is the derived shadow that
# re-derives; the DECLARED_MEMBER_OF edge itself never does.
MEMBERSHIP_EDGE_TYPE = "DECLARED_MEMBER_OF"


def is_derived_edge(edge):
    """Machine-derived edge? Plain derived types and the ASSIGNS_ family
    always; the stratified types split by endpoints — a row from an
    Archetype is authored schema ground, a row from a citizen re-derives
    (its INSTANCE_OF from its label's binding, its ladder edges from the
    rank ground props)."""
    if edge.type in DERIVED_EDGE_TYPES or edge.type.startswith("ASSIGNS_"):
        return True
    if edge.type in STRATIFIED_EDGE_TYPES:
        return edge.from_label != ARCHETYPE_LABEL
    return False


def is_concept_archetype(graph, name):
    """True iff `name` is an existing Concept-rooted subject-matter
    Archetype — the only legal target of an authored membership
    (DECLARED_MEMBER_OF). Shared by the derivation fold (extract.py) and
    the delta lint (delta.py) so both judge a target the same way.

    A missing node fails. A LABEL Archetype fails: it carries its embedded
    roster spec (spec_json) — it is a home with a catalog, not a subject to
    classify against, and authored membership never re-homes. A Facet
    (rooted at Facet), a Judgment/Provenance anchor — anything whose
    INSTANCE_OF tower does not terminate at the Concept root — fails. Only a
    genuine domain concept passes."""
    node = graph.nodes.get((ARCHETYPE_LABEL, name))
    if node is None:
        return False
    if node.get("spec_json") is not None:
        return False
    # Walk the INSTANCE_OF tower upward (Archetype -> Archetype only); the
    # target is Concept-rooted iff any path reaches the Concept root.
    seen = set()
    frontier = [name]
    while frontier:
        current = frontier.pop()
        if current == CONCEPT_ROOT:
            return True
        if current in seen:
            continue
        seen.add(current)
        for edge in graph.edges:
            if (edge.type == "INSTANCE_OF"
                    and edge.from_label == ARCHETYPE_LABEL
                    and edge.from_name == current
                    and edge.to_label == ARCHETYPE_LABEL):
                frontier.append(edge.to_name)
    return False


def concept_bindings(node_spec):
    """A node's concept: binding as a list (accepts string or list)."""
    concept = node_spec.get("concept")
    if concept is None:
        return []
    if isinstance(concept, str):
        return [concept]
    return list(concept)
KNOWN_REL_KEYS = {"type", "to", "column", "source", "parser", "props",
                  "on_missing", "unmatched_property",
                  # edge-table relationships (each source row = one edge)
                  "from_column", "prop_columns",
                  # effects_table parser (uniformly reified effects)
                  "verb_column", "verbs", "condition_column", "effect_label",
                  # staged_blocks parser column overrides
                  "category_column", "stage_column", "items_column",
                  # prerequisites parser: the corpus declares where its
                  # clauses point (the engine holds no target vocabulary)
                  "staged_to", "named_to", "stage_enum"}
KNOWN_CATALOG_KEYS = {"type", "doc"}
ON_MISSING_VALUES = frozenset(policy.value for policy in OnMissing)
SCALAR_TYPES = frozenset(ptype.value for ptype in PropType)


@dataclass
class Ontology:
    path: Path
    base_dir: Path
    raw: dict
    enums: dict = field(default_factory=dict)      # name -> spec dict
    concepts: dict = field(default_factory=dict)   # name -> spec dict (merged: kernel + project)
    kernel_names: set = field(default_factory=set) # concepts provided by the metaontology
    nodes: dict = field(default_factory=dict)      # label -> spec dict
    defaults: dict = field(default_factory=dict)
    answer_keys: list = field(default_factory=list)  # declared derivation checks (the declared answer keys)
    meta: dict = field(default_factory=dict)         # metaontology identity: {version, path} (the self-description round)
    rejected_terms: list = field(default_factory=list)  # terms ruled non-vocabulary at a glossary sitting; the sweep skips them (the glossary sitting)

    @property
    def default_on_missing(self):
        return self.defaults.get("on_missing", OnMissing.PLACEHOLDER)

    def source_files(self):
        """Every data file the ontology references (for unmapped-CSV checks)."""
        files = set()
        for spec in self.enums.values():
            if spec.get("source"):
                files.add(spec["source"])
        for spec in self.nodes.values():
            if isinstance(spec, dict):
                files.update(source_files_of(spec))
                for rel in spec.get("relationships") or []:
                    if rel.get("source"):
                        files.add(rel["source"])
        return files

    def content_roots(self):
        """Declared directories (repo-relative) where corpus material lives —
        the roots the unmapped-artifact sweep walks. Empty if undeclared."""
        return [r for r in (self.raw.get("content_roots") or [])
                if isinstance(r, str)]

    def non_prose_sources(self):
        """Declared prose sources that are indexes, not prose (a table of
        contents, a glossary listing) — the glossary sweep skips them by
        declaration, never by filename."""
        return {p for p in (self.raw.get("non_prose_sources") or [])
                if isinstance(p, str)}

    def prose_files(self):
        """The glossary sweep's file set, drawn from the declarations: every
        markdown source the ontology names — both source: lists read as
        markdown_sections and the markdown members of file-valued
        (fingerprint) labels — minus any marked non-prose. No directory or
        filename is hardcoded; a corpus with a different layout is swept from
        its own declarations."""
        non_prose = self.non_prose_sources()
        files = set()
        for spec in self.nodes.values():
            if not isinstance(spec, dict):
                continue
            if node_reader(spec) == Reader.MARKDOWN_SECTIONS:
                files.update(source_files_of(spec))
            if spec.get("fingerprint"):
                files.update(
                    value for value in (spec.get("values") or [])
                    if isinstance(value, str)
                    and Path(value).suffix.lower() in MARKDOWN_SUFFIXES)
        return sorted(f for f in files if f not in non_prose)

    def referenced_files(self):
        """Every file any declaration knows — source files, overlays,
        property tables, answer-key tables, and provenance identity lists
        (fingerprint values: the declared roster of corpus files already
        taken in as citizens; owner ruling — a rostered file is covered,
        so the unmapped-artifact sweep stays quiet about it and a NEW
        file, absent from every declaration including the roster, is the
        one that surfaces)."""
        files = set(self.source_files())
        for spec in self.nodes.values():
            if not isinstance(spec, dict):
                continue
            if spec.get("overlay"):
                files.add(spec["overlay"])
            for table in spec.get("property_tables") or []:
                if isinstance(table, dict) and table.get("source"):
                    files.add(table["source"])
            if spec.get("fingerprint"):
                files.update(v for v in spec.get("values") or []
                             if isinstance(v, str))
        for key in self.answer_keys:
            files.update(_referenced_tables(key))
        return files


def read_csv_header(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        for row in reader:
            return row
    return []


def load_metaontology(path):
    """Parse the engine's metaontology. Returns (concepts, meta, findings)
    where meta carries the seed's identity: {version, path} — what the
    graph will answer when asked what it was built with (the self-description round).

    Roots become parentless concept entries; facet-library entries get
    instance_of: Facet. Doc strings ride along as `doc`.
    """
    findings = []
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), "-",
                                f"cannot read metaontology: {exc}"))
        return {}, {}, findings
    if not isinstance(raw, dict):
        findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), "-",
                                "metaontology root must be a mapping"))
        return {}, {}, findings
    for key in raw:
        if key not in KNOWN_META_KEYS:
            findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), key,
                                    f"unknown metaontology key '{key}'"))
    concepts = {}
    for name, doc in (raw.get("roots") or {}).items():
        concepts[name] = {"doc": doc} if doc else {}
    for name, entry in (raw.get("facets") or {}).items():
        # Entries are doc strings, or mappings for structured facets
        # (instance_of override, ordered ladders via ordered+values).
        if isinstance(entry, dict):
            spec = {"instance_of": FACET_ROOT, **entry}
        else:
            spec = {"instance_of": FACET_ROOT}
            if entry:
                spec["doc"] = entry
        concepts[name] = spec
    # Engine-provided concepts (mechanized vocabulary, e.g. Procedure;
    # the Judgment quartet): dict entries may name their root
    # (instance_of: Judgment); doc-string entries root under Concept.
    for name, entry in (raw.get("concepts") or {}).items():
        if isinstance(entry, dict):
            spec = {"instance_of": CONCEPT_ROOT, **entry}
        else:
            spec = {"instance_of": CONCEPT_ROOT}
            if entry:
                spec["doc"] = entry
        concepts[name] = spec
    for root, section in ((FACET_ROOT, "facets"), (CONCEPT_ROOT, "concepts")):
        if root not in concepts and any(
                spec.get("instance_of") == root for spec in concepts.values()):
            findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), section,
                                    f"the {section} section needs a "
                                    f"'{root}' root"))
    meta = {"version": raw.get("version"), "path": str(path)}
    return concepts, meta, findings


def load_ontology(path, base_dir, metaontology_path=None):
    """Parse the project ontology layered over the engine metaontology.

    Returns (Ontology | None, findings). Returns None only when a file is
    unreadable/unparseable.
    """
    kernel, meta, findings = load_metaontology(
        metaontology_path or METAONTOLOGY_PATH)
    if any(f.severity == ERROR for f in findings):
        return None, findings

    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), "-",
                                f"cannot read ontology: {exc}"))
        return None, findings
    if not isinstance(raw, dict):
        findings.append(Finding(ERROR, Category.ONTOLOGY, str(path), "-",
                                "ontology root must be a mapping"))
        return None, findings

    concepts = dict(kernel)
    project_concepts = dict(raw.get("concepts") or {})
    # Project facets: section is the user-defined-facet escape hatch — same
    # shape as the kernel library (name -> doc string or mapping).
    for name, spec in (raw.get("facets") or {}).items():
        if isinstance(spec, dict):
            facet = {**spec, "instance_of": spec.get("instance_of", FACET_ROOT)}
        else:
            facet = {"instance_of": FACET_ROOT}
            if spec:
                facet["doc"] = spec
        project_concepts[name] = facet
    for name, spec in project_concepts.items():
        if name in kernel:
            findings.append(Finding(
                ERROR, Category.ONTOLOGY, str(path), f"concepts.{name}",
                f"'{name}' is provided by the engine metaontology and cannot "
                "be redeclared"))
            continue
        concepts[name] = spec

    ontology = Ontology(path=path, base_dir=Path(base_dir), raw=raw,
                        enums=raw.get("enums") or {},
                        concepts=concepts,
                        kernel_names=set(kernel),
                        nodes=raw.get("nodes") or {},
                        defaults=raw.get("defaults") or {},
                        answer_keys=raw.get("answer_keys") or [],
                        meta=meta,
                        rejected_terms=raw.get("rejected_terms") or [])
    findings.extend(check_ontology(ontology))
    return ontology, findings


def kernel_ontology(base_dir, metaontology_path=None):
    """The kernel layer alone, as an Ontology — the seed of a knowledge
    base born graph-native: no project ontology.yaml, no sources, no
    derive path. Its schema stratum is exactly what the metaontology
    provides; the project layer grows later, on the graph, through
    gated rounds. The Ontology anchor points at the conventional
    bootstrap path, which a graph-native base never materializes.

    Returns (Ontology | None, findings) — None only when the
    metaontology itself is unreadable."""
    kernel, meta, findings = load_metaontology(
        metaontology_path or METAONTOLOGY_PATH)
    if any(f.severity == ERROR for f in findings):
        return None, findings
    base_dir = Path(base_dir)
    ontology = Ontology(path=base_dir / "graph" / "ontology.yaml",
                        base_dir=base_dir, raw={},
                        concepts=dict(kernel),
                        kernel_names=set(kernel),
                        meta=meta)
    findings.extend(check_ontology(ontology))
    return ontology, findings


def ontology_from_graph(graph, base_dir):
    """Reconstruct an Ontology from a graph holding the migrated schema
    stratum (the schema inversion) — the graph alone, no ontology.yaml consulted. The
    inverse of embed_schema_stratum + build_metamodel: labels come back
    from their spec_json embeddings, concepts from their Archetype props
    and the tower/taxonomy edges, and the top-level sections from the
    Ontology/Metaontology anchor props. What derive() consumes is
    reconstructed faithfully; validate/load-only sections the migration
    did not embed (content_roots, answer_keys, rejected_terms) come back
    empty by design.

    Reconstruction sources, per citizen kind:
    - nodes: Archetype nodes carrying spec_json -> json.loads(spec_json).
    - concepts: Archetype nodes that are either concept-only (no spec_json,
      but DECLARED_IN a schema layer) or both-concept-and-label (spec_json
      whose concept binding names the citizen itself, e.g. the kernel's
      Procedure); each spec is rebuilt from node props (doc/stub/temporal/
      recursive/surface_forms/pending_instances), the Archetype->Archetype
      INSTANCE_OF tower (instance_of, and ordered via the ->Ordered edge),
      inbound SUBTYPE_OF edges (subtypes), and inbound INSTANCE_OF from
      member Archetypes ordered by rank (an ordered ladder's values).
    - kernel_names: names DECLARED_IN the Metaontology layer.
    - enums/defaults/non_prose_sources/version/tag: the Ontology anchor's
      embedded props; meta version: the Metaontology anchor's version.

    The anchors themselves (Metaontology, Ontology) are neither concept nor
    label — they carry no spec_json and no DECLARED_IN, so both dicts
    exclude them.
    """
    archetype = {name: props
                 for (label, name), props in graph.nodes.items()
                 if label == ARCHETYPE_LABEL}

    # Tower and taxonomy indexes, Archetype->Archetype only (a citizen's
    # own INSTANCE_OF — from_label != Archetype — is the value stratum,
    # re-derived, and never part of the schema being reconstructed here).
    instance_up = {}      # concept -> [parent archetypes]
    instance_down = {}    # concept -> [member archetypes]
    declared_in = {}      # citizen -> schema layer name
    subtype_sources = {}  # concept -> [citizen names that are its KINDS]
    for edge in graph.edges:
        if edge.from_label != ARCHETYPE_LABEL or edge.to_label != ARCHETYPE_LABEL:
            if edge.type == "SUBTYPE_OF" and edge.to_label == ARCHETYPE_LABEL:
                subtype_sources.setdefault(edge.to_name, []).append(
                    edge.from_name)
            continue
        if edge.type == "INSTANCE_OF":
            instance_up.setdefault(edge.from_name, []).append(edge.to_name)
            instance_down.setdefault(edge.to_name, []).append(edge.from_name)
        elif edge.type == "DECLARED_IN":
            declared_in[edge.from_name] = edge.to_name
        elif edge.type == "SUBTYPE_OF":
            subtype_sources.setdefault(edge.to_name, []).append(edge.from_name)

    nodes = {}
    for name, props in archetype.items():
        if "spec_json" in props:
            nodes[name] = json.loads(props["spec_json"])

    concepts = {}
    for name, props in archetype.items():
        spec_json = props.get("spec_json")
        label_spec = json.loads(spec_json) if spec_json is not None else None
        if label_spec is not None:
            is_concept = name in concept_bindings(label_spec)
        else:
            is_concept = name in declared_in
        if not is_concept:
            continue
        spec = {}
        parents = sorted(t for t in instance_up.get(name, [])
                         if t != ORDERED_CONCEPT)
        if parents:
            spec["instance_of"] = parents[0]
        for prop in ("doc", "stub", "temporal", "recursive"):
            if props.get(prop):
                spec[prop] = props[prop]
        for prop in ("surface_forms", "pending_instances"):
            if props.get(prop):
                spec[prop] = list(props[prop])
        subs = subtype_sources.get(name)
        if subs:
            # Reconstruct in name order: the edges carry no declaration
            # order, and the authored lists are name-sorted.
            spec["subtypes"] = sorted(subs)
        # The ->Ordered edge is emitted for an ordered CONCEPT (an
        # archetype-level ladder) and for an ordered LABEL alike. For a
        # name that is both, attribute the edge to the label side (its
        # spec_json carries ordered) rather than fabricating an ordered
        # concept spec with an empty ladder — a name that is an ordered
        # concept AND an ordered label at once is inexpressible in the
        # single shared edge, and no such collision exists.
        label_side_ordered = bool(label_spec and label_spec.get("ordered"))
        if ORDERED_CONCEPT in instance_up.get(name, []) \
                and not label_side_ordered:
            spec["ordered"] = True
            members = [(archetype[member]["rank"], member)
                       for member in instance_down.get(name, [])
                       if "rank" in archetype.get(member, {})]
            spec["values"] = [member for _, member in sorted(members)]
        concepts[name] = spec

    kernel_names = {name for name, layer in declared_in.items()
                    if layer == "Metaontology"}

    anchor = archetype.get("Ontology", {})
    enums = json.loads(anchor["enums_json"]) if "enums_json" in anchor else {}
    defaults = (json.loads(anchor["defaults_json"])
                if "defaults_json" in anchor else {})
    raw = {"version": anchor.get("version"),
           "non_prose_sources": list(anchor.get("non_prose_sources") or [])}
    if anchor.get("tag"):
        raw["tag"] = anchor["tag"]
    meta = {"version": archetype.get("Metaontology", {}).get("version"),
            "path": str(METAONTOLOGY_PATH)}

    # Rejected terms are Judgment citizens (owner ruling, 2026-08-12):
    # each ruled-reject Decision carries the machine key rejected_term,
    # and the glossary sweep suppresses exactly those.
    rejected_terms = sorted(
        props["rejected_term"]
        for (label, _name), props in graph.nodes.items()
        if label == "Decision" and props.get("rejected_term"))

    return Ontology(
        path=Path(base_dir) / "graph" / "ontology.yaml",
        base_dir=Path(base_dir),
        raw=raw,
        enums=enums,
        concepts=concepts,
        kernel_names=kernel_names,
        nodes=nodes,
        defaults=defaults,
        answer_keys=[],
        meta=meta,
        rejected_terms=rejected_terms)


def check_ontology(ontology):
    findings = []
    fname = str(ontology.path)

    def problem(severity, location, detail):
        findings.append(Finding(severity, Category.ONTOLOGY, fname, location, detail))

    if not (isinstance(ontology.rejected_terms, list)
            and all(isinstance(t, str) for t in ontology.rejected_terms)):
        problem(ERROR, "rejected_terms",
                "'rejected_terms' must be a list of term strings")

    content_roots = ontology.raw.get("content_roots")
    if content_roots is not None and not (
            isinstance(content_roots, list)
            and all(isinstance(r, str) for r in content_roots)):
        problem(ERROR, "content_roots",
                "'content_roots' must be a list of directory paths")
    else:
        for root in content_roots or []:
            if not (ontology.base_dir / root).is_dir():
                problem(WARNING, "content_roots",
                        f"content root '{root}' is not a directory (skipped "
                        "by the unmapped-artifact sweep)")

    non_prose = ontology.raw.get("non_prose_sources")
    if non_prose is not None and not (
            isinstance(non_prose, list)
            and all(isinstance(p, str) for p in non_prose)):
        problem(ERROR, "non_prose_sources",
                "'non_prose_sources' must be a list of source-file paths")
    else:
        for relpath in non_prose or []:
            if not (ontology.base_dir / relpath).exists():
                problem(WARNING, "non_prose_sources",
                        f"non-prose source '{relpath}' does not exist "
                        "(the glossary sweep has nothing to skip)")
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        for alias, target in (spec.get("aliases") or {}).items():
            if not (isinstance(target, str) or (
                    isinstance(target, list)
                    and all(isinstance(t, str) for t in target))):
                problem(ERROR, f"nodes.{label}.aliases.{alias}",
                        "an alias target must be a citizen name or a list "
                        "of citizen names")
    for key in ontology.raw:
        if key not in KNOWN_TOP_KEYS:
            problem(ERROR, key, f"unknown top-level key '{key}'")

    on_missing_default = ontology.defaults.get("on_missing")
    if on_missing_default and on_missing_default not in ON_MISSING_VALUES:
        problem(ERROR, "defaults.on_missing",
                f"defaults.on_missing must be one of {sorted(ON_MISSING_VALUES)}")

    for name, spec in ontology.concepts.items():
        loc = f"concepts.{name}"
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            problem(ERROR, loc, "concept spec must be a mapping")
            continue
        for key in spec:
            if key not in KNOWN_CONCEPT_KEYS:
                problem(ERROR, loc, f"unknown key '{key}'")
        parent = spec.get("instance_of")
        if parent is not None and parent not in ontology.concepts:
            problem(ERROR, loc,
                    f"instance_of '{parent}' is not a declared concept")
        for value in spec.get("values") or []:
            if value not in ontology.concepts:
                problem(ERROR, loc,
                        f"ladder value '{value}' is not a declared concept")
        if spec.get("stub") is not None and \
                not isinstance(spec["stub"], bool):
            problem(ERROR, loc, "'stub' must be true or false")
        if spec.get("surface_forms") is not None and (
                not isinstance(spec["surface_forms"], list)
                or not all(isinstance(f, str) for f in spec["surface_forms"])):
            problem(ERROR, loc, "'surface_forms' must be a list of strings")
        if spec.get("subtypes") is not None and (
                not isinstance(spec["subtypes"], list)
                or not all(isinstance(s, str) for s in spec["subtypes"])):
            problem(ERROR, loc, "'subtypes' must be a list of citizen names")
        if spec.get("pending_instances") is not None:
            if (not isinstance(spec["pending_instances"], list)
                    or not all(isinstance(n, str)
                               for n in spec["pending_instances"])):
                problem(ERROR, loc,
                        "'pending_instances' must be a list of names")
            elif not spec.get("stub"):
                problem(ERROR, loc,
                        "'pending_instances' on a concept requires "
                        "stub: true (a mapped concept has real instances)")
        if (parent is None and name not in ontology.kernel_names):
            findings.append(Finding(
                INFO, Category.ONTOLOGY, fname, loc,
                f"project declares a new ROOT '{name}' — permitted but "
                "ceremonial; consider whether it belongs under an existing "
                "kernel root instead"))

    ordered_labels = [label for label, spec in ontology.nodes.items()
                      if isinstance(spec, dict) and spec.get("ordered")]
    if ordered_labels and ORDERED_CONCEPT not in ontology.concepts:
        problem(ERROR, "concepts",
                f"ordered labels {ordered_labels} need a declared "
                f"'{ORDERED_CONCEPT}' concept")

    for name, spec in ontology.enums.items():
        loc = f"enums.{name}"
        if not isinstance(spec, dict):
            problem(ERROR, loc, "enum spec must be a mapping")
            continue
        for key in spec:
            if key not in KNOWN_ENUM_KEYS:
                problem(ERROR, loc, f"unknown key '{key}'")
        if bool(spec.get("source")) == bool(spec.get("values")):
            problem(ERROR, loc, "enum needs exactly one of source/values")
        elif spec.get("source"):
            source = ontology.base_dir / spec["source"]
            if not source.exists():
                problem(ERROR, loc, f"source file not found: {spec['source']}")
            elif spec.get("column") not in read_csv_header(source):
                problem(ERROR, loc,
                        f"column '{spec.get('column')}' not in {spec['source']}")

    for label, spec in ontology.nodes.items():
        loc = f"nodes.{label}"
        if label in RESERVED_LABELS:
            problem(ERROR, loc,
                    f"'{label}' is an engine-reserved label "
                    f"({RESERVED_LABELS[label]})")
        if not isinstance(spec, dict):
            problem(ERROR, loc, "node spec must be a mapping")
            continue
        for key in spec:
            if key not in KNOWN_NODE_KEYS:
                problem(ERROR, loc, f"unknown key '{key}'")
        concept = spec.get("concept")
        if concept is not None and not isinstance(concept, (str, list)):
            problem(ERROR, f"{loc}.concept",
                    "concept must be a name or a list of names")
        else:
            for name in concept_bindings(spec):
                if name not in ontology.concepts:
                    problem(ERROR, f"{loc}.concept",
                            f"'{name}' is not a declared concept")
        if spec.get("subtypes") is not None and (
                not isinstance(spec["subtypes"], list)
                or not all(isinstance(s, str) for s in spec["subtypes"])):
            problem(ERROR, loc, "'subtypes' must be a list of citizen names")

        origins = sum(1 for k in ("source", "values", "implicit")
                      if spec.get(k))
        if origins != 1:
            problem(ERROR, loc,
                    "node needs exactly one of source / values / implicit")

        header = []
        if spec.get("source"):
            reader = node_reader(spec)
            files = source_files_of(spec)
            if spec.get("reader") and spec["reader"] not in KNOWN_READERS:
                problem(ERROR, loc, f"unknown reader '{spec['reader']}' "
                        f"(known: {sorted(KNOWN_READERS)})")
                reader = None
            elif reader is None:
                problem(ERROR, loc,
                        "cannot infer a reader from the source extension; "
                        "set reader: explicitly")
            missing = [f for f in files
                       if not (ontology.base_dir / f).exists()]
            for relpath in missing:
                problem(ERROR, loc, f"source file not found: {relpath}")
            match reader:
                case Reader.CSV_ROWS if len(files) != 1:
                    problem(ERROR, loc,
                            "the csv_rows reader takes a single source file")
                case Reader.CSV_ROWS if not missing:
                    header = read_csv_header(ontology.base_dir / files[0])
                    if not spec.get("key"):
                        problem(ERROR, loc,
                                "node with a csv source needs a key column")
                    elif spec["key"] not in header:
                        problem(ERROR, loc,
                                f"key column '{spec['key']}' not in {files[0]}")
                case Reader.MARKDOWN_SECTIONS | Reader.PROCEDURE_YAML if \
                        spec.get("key"):
                    problem(ERROR, loc,
                            "key is only used by the csv_rows reader")

        catalog = spec.get("catalog") or {}
        for prop, prop_spec in catalog.items():
            ploc = f"{loc}.catalog.{prop}"
            if not isinstance(prop_spec, dict):
                problem(ERROR, ploc, "catalog entry must be a mapping")
                continue
            for key in prop_spec:
                if key not in KNOWN_CATALOG_KEYS:
                    problem(ERROR, ploc, f"unknown key '{key}'")
            ptype = prop_spec.get("type", "text")
            if ptype not in SCALAR_TYPES:
                if ptype.startswith("enum:"):
                    if ptype.split(":", 1)[1] not in ontology.enums:
                        problem(ERROR, ploc, f"unknown enum in type '{ptype}'")
                else:
                    problem(ERROR, ploc, f"unknown type '{ptype}'")

        for prop, mapping in (spec.get("properties") or {}).items():
            ploc = f"{loc}.properties.{prop}"
            if prop not in catalog:
                problem(ERROR, ploc, "property not declared in catalog")
            column = (mapping or {}).get("column")
            if not column:
                problem(ERROR, ploc, "property mapping needs a column")
            elif header and column not in header:
                problem(ERROR, ploc,
                        f"column '{column}' not in {spec.get('source')}")

        for index, table in enumerate(spec.get("property_tables") or []):
            tloc = f"{loc}.property_tables[{index}]"
            if not isinstance(table, dict):
                problem(ERROR, tloc, "property table must be a mapping")
                continue
            for key in table:
                if key not in KNOWN_PROPERTY_TABLE_KEYS:
                    problem(ERROR, tloc, f"unknown key '{key}'")
            for needed in ("source", "key", "properties"):
                if not table.get(needed):
                    problem(ERROR, tloc, f"property table needs '{needed}'")
            if table.get("source"):
                tpath = ontology.base_dir / table["source"]
                if not tpath.exists():
                    problem(ERROR, tloc,
                            f"source file not found: {table['source']}")
                else:
                    theader = read_csv_header(tpath)
                    if table.get("key") and table["key"] not in theader:
                        problem(ERROR, tloc, f"key column '{table['key']}' "
                                f"not in {table['source']}")
                    for prop, mapping in (table.get("properties")
                                          or {}).items():
                        if prop not in catalog:
                            problem(ERROR, f"{tloc}.{prop}",
                                    "property not declared in catalog")
                        column = (mapping or {}).get("column")
                        if not column:
                            problem(ERROR, f"{tloc}.{prop}",
                                    "property mapping needs a column")
                        elif column not in theader:
                            problem(ERROR, f"{tloc}.{prop}",
                                    f"column '{column}' not in "
                                    f"{table['source']}")

        raw_single = spec.get("rendered_view")
        if raw_single is not None and not isinstance(raw_single, dict):
            problem(ERROR, f"{loc}.rendered_view",
                    "rendered_view must be a mapping")
        raw_list = spec.get("rendered_views")
        if raw_list is not None and not isinstance(raw_list, list):
            problem(ERROR, f"{loc}.rendered_views",
                    "rendered_views must be a list of view mappings")
        views = [(f"{loc}.rendered_view", raw_single)] if isinstance(
            raw_single, dict) else []
        views += [(f"{loc}.rendered_views[{i}]", v)
                  for i, v in enumerate(raw_list or [])
                  if isinstance(v, dict)]
        for rloc, rview in views:
            if True:
                for key in rview:
                    if key not in KNOWN_RENDERED_VIEW_KEYS:
                        problem(ERROR, rloc, f"unknown key '{key}'")
                if spec.get("source"):
                    problem(ERROR, rloc,
                            "rendered_view is for labels WITHOUT a row-source "
                            "(a source label renders from its own mapping)")
                template = rview.get("name_template")
                if template is not None and (
                        not isinstance(template, str)
                        or "{key}" not in template):
                    problem(ERROR, rloc,
                            "name_template must be a string containing '{key}'")
                rheader = []
                if not rview.get("source"):
                    problem(ERROR, rloc, "rendered_view needs a source CSV")
                elif not (ontology.base_dir / rview["source"]).exists():
                    problem(ERROR, rloc,
                            f"source file not found: {rview['source']}")
                else:
                    rheader = read_csv_header(ontology.base_dir / rview["source"])
                    if rview.get("key") and rview["key"] not in rheader:
                        problem(ERROR, rloc,
                                f"key column '{rview['key']}' not in "
                                f"{rview['source']}")

                def check_view_block(where, properties, relationships,
                                     block_catalog):
                    for prop, mapping in (properties or {}).items():
                        if prop not in block_catalog:
                            problem(ERROR, f"{where}.properties.{prop}",
                                    "property not declared in catalog")
                        column = (mapping or {}).get("column")
                        if not column:
                            problem(ERROR, f"{where}.properties.{prop}",
                                    "property mapping needs a column")
                        elif rheader and column not in rheader:
                            problem(ERROR, f"{where}.properties.{prop}",
                                    f"column '{column}' not in {rview['source']}")
                    for index, rel in enumerate(relationships or []):
                        rrloc = f"{where}.relationships[{index}]"
                        if not isinstance(rel, dict):
                            problem(ERROR, rrloc,
                                    "relationship must be a mapping")
                            continue
                        if not rel.get("type"):
                            problem(ERROR, rrloc, "relationship needs a type")
                        column = rel.get("column")
                        if not column:
                            problem(ERROR, rrloc, "relationship needs a column")
                        elif rheader and column not in rheader:
                            problem(ERROR, rrloc,
                                    f"column '{column}' not in {rview['source']}")

                # A matrix view defers to a whole-table grammar inverter; its
                # columns are the grammar's business, not per-column maps.
                if not rview.get("matrix"):
                    check_view_block(rloc, rview.get("properties"),
                                     rview.get("relationships"), catalog)
                # Multi-label view (Fix 5): each entry maps its OWN label's
                # catalog into the shared columns.
                for index, entry in enumerate(rview.get("labels") or []):
                    eloc = f"{rloc}.labels[{index}]"
                    if not isinstance(entry, dict):
                        problem(ERROR, eloc, "a labels entry must be a mapping")
                        continue
                    for key in entry:
                        if key not in KNOWN_VIEW_ENTRY_KEYS:
                            problem(ERROR, eloc, f"unknown key '{key}'")
                    entry_label = entry.get("label")
                    if not entry_label:
                        problem(ERROR, eloc, "a labels entry needs a label")
                        entry_catalog = {}
                    elif entry_label not in ontology.nodes:
                        problem(ERROR, eloc,
                                f"unknown contributor label '{entry_label}'")
                        entry_catalog = {}
                    else:
                        entry_catalog = (ontology.nodes[entry_label]
                                         .get("catalog") or {})
                    etemplate = entry.get("name_template")
                    if etemplate is not None and (
                            not isinstance(etemplate, str)
                            or "{key}" not in etemplate):
                        problem(ERROR, eloc,
                                "name_template must contain '{key}'")
                    for key in ("only_with", "names"):
                        value = entry.get(key)
                        if value is not None and not (
                                isinstance(value, list)
                                and all(isinstance(v, str) for v in value)):
                            problem(ERROR, eloc,
                                    f"'{key}' must be a list of names")
                    for prop in entry.get("only_with") or []:
                        if entry_catalog and prop not in entry_catalog:
                            problem(ERROR, eloc,
                                    f"only_with property '{prop}' not in "
                                    f"{entry_label}'s catalog")
                    check_view_block(eloc, entry.get("properties"),
                                     entry.get("relationships"), entry_catalog)

        overlay = spec.get("overlay")
        if overlay and not (ontology.base_dir / overlay).exists():
            problem(WARNING, f"{loc}.overlay",
                    f"overlay file not found: {overlay} (skipped)")

        for index, rel in enumerate(spec.get("relationships") or []):
            rloc = f"{loc}.relationships[{index}]"
            if not isinstance(rel, dict):
                problem(ERROR, rloc, "relationship must be a mapping")
                continue
            for key in rel:
                if key not in KNOWN_REL_KEYS:
                    problem(ERROR, rloc, f"unknown key '{key}'")
            if not rel.get("type"):
                problem(ERROR, rloc, "relationship needs a type")
            parser = rel.get("parser")
            if parser and parser not in KNOWN_REL_PARSERS:
                problem(ERROR, rloc, f"unknown parser '{parser}' "
                        f"(registered: {sorted(KNOWN_REL_PARSERS)})")
            if rel.get("parser") == RelParser.EFFECTS_TABLE:
                for needed_key in ("source", "from_column", "verb_column",
                                   "verbs", "condition_column", "column",
                                   "to", "effect_label"):
                    if not rel.get(needed_key):
                        problem(ERROR, rloc,
                                f"effects_table needs '{needed_key}'")
                if not isinstance(rel.get("verbs"), list):
                    problem(ERROR, rloc,
                            "verbs must be a list of allowed verb values")
                effect_label = rel.get("effect_label")
                if effect_label and effect_label not in ontology.nodes:
                    problem(ERROR, rloc,
                            f"effect_label '{effect_label}' is not a declared label")
            if parser == RelParser.PREREQUISITES:
                # A prerequisites rel must declare where its parsed clauses
                # point (staged_to / named_to) — otherwise the extractor
                # would emit edges to a None label, crashing far from the
                # misdeclaration.
                if not rel.get("column"):
                    problem(ERROR, rloc,
                            "prerequisites needs a 'column' to read "
                            "clauses from")
                for needed_key, clause_kind in (("staged_to", "staged"),
                                                ("named_to", "named")):
                    target = rel.get(needed_key)
                    if not target:
                        problem(ERROR, rloc,
                                f"prerequisites needs '{needed_key}' — the "
                                f"label its {clause_kind} clauses point at")
                    elif target == ANY_LABEL:
                        # same coherence rule as `to: any`: no label to
                        # create a placeholder in
                        if rel.get("on_missing",
                                   ontology.default_on_missing) != OnMissing.REPORT:
                            problem(ERROR, rloc,
                                    f"{needed_key}: any requires "
                                    f"on_missing: report")
                    elif target not in ontology.nodes:
                        problem(ERROR, rloc,
                                f"unknown target label '{target}'")
                # A stage_enum naming no declared enum would silently
                # disable stage checking at extraction — refuse the typo
                # where it was written.
                stage_enum = rel.get("stage_enum")
                if stage_enum and stage_enum not in ontology.enums:
                    problem(ERROR, rloc,
                            f"unknown enum '{stage_enum}' in 'stage_enum' "
                            f"(declared: {sorted(ontology.enums)})")
            if rel.get("from_column"):
                rel_header = []
                if not rel.get("source"):
                    problem(ERROR, rloc, "from_column needs a source file")
                elif (ontology.base_dir / rel["source"]).exists():
                    rel_header = read_csv_header(
                        ontology.base_dir / rel["source"])
                needed = [rel["from_column"]]
                if rel.get("column"):
                    needed.append(rel["column"])
                else:
                    problem(ERROR, rloc, "from_column needs a target column")
                if not rel.get("to"):
                    problem(ERROR, rloc, "from_column needs a 'to' label")
                needed.extend((rel.get("prop_columns") or {}).values())
                for extra in ("verb_column", "condition_column"):
                    if rel.get(extra):
                        needed.append(rel[extra])
                for column in needed:
                    if rel_header and column not in rel_header:
                        problem(ERROR, rloc,
                                f"column '{column}' not in {rel.get('source')}")
            if not parser:
                if not rel.get("column"):
                    problem(ERROR, rloc, "relationship needs a column or a parser")
                if not rel.get("to"):
                    problem(ERROR, rloc, "relationship needs a 'to' label")
                elif rel["to"] == ANY_LABEL:
                    # label-agnostic resolution: unique names resolve, ambiguous
                    # ones need a "Label: Name" qualifier; no label to create a
                    # placeholder in, so report-mode is mandatory
                    if rel.get("on_missing",
                               ontology.default_on_missing) != OnMissing.REPORT:
                        problem(ERROR, rloc,
                                "to: any requires on_missing: report")
                elif rel["to"] not in ontology.nodes:
                    problem(ERROR, rloc, f"unknown target label '{rel['to']}'")
            if rel.get("column") and header and rel["column"] not in header:
                # parser rels may read their own source file instead
                if not rel.get("source"):
                    problem(ERROR, rloc,
                            f"column '{rel['column']}' not in {spec.get('source')}")
            if rel.get("source"):
                rel_source = ontology.base_dir / rel["source"]
                if not rel_source.exists():
                    problem(ERROR, rloc, f"source file not found: {rel['source']}")
            on_missing = rel.get("on_missing")
            if on_missing and on_missing not in ON_MISSING_VALUES:
                problem(ERROR, rloc,
                        f"on_missing must be one of {sorted(ON_MISSING_VALUES)}")
            unmatched_prop = rel.get("unmatched_property")
            if unmatched_prop and unmatched_prop not in catalog:
                problem(ERROR, rloc,
                        f"unmatched_property '{unmatched_prop}' not in catalog")

    return findings
