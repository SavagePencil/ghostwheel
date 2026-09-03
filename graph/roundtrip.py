"""The round-trip harness: regeneration vs original, judged per
content class at the functional-parity bar, with one scorecard and a
real exit status. No human in the comparison step.

The bar (ruled): no factual data lost, omitted unapproved, or
mistranslated — structure, wording, and format free to improve. So the
harness judges at CHAPTER scope, never section-by-section: a draft that
fully reorganizes still passes if no fact is lost, none is invented,
and no value moved. (Chapter-scope example: a rank ladder's row may
move anywhere in the draft; its cells may not change.)

Tiers, dispatched by the reading room's content classes (the content-class taxonomy):
- table       — zero cell-level loss with row integrity: every source
                row's (column-filtered) values must appear together in
                some single draft table row; restructuring is free.
- procedure   — the draft must carry the approved program's claims (the
                deterministic render's atoms) — v0 teeth; the
                ontology-declared answer keys (the declared answer keys) add behavior
                equivalence in this tier without reshaping the harness.
                Citation hash tripwires remain validate's job.
- rule-prose  — the claim-diff judge (graph/judge.py), chapter-wide —
                INCLUDING prose spans inside procedure-cited sections
                (the vanishing-rule catch: the owner's spot-check found a rule vanishing
                under a green scorecard because cited-section prose was
                unjudged; no content class is unjudged now). The draft
                carries the rendered programs, so program-covered claims
                match through; what a program deliberately excludes
                surfaces as the omission it is, answerable by Approved
                Omission or intake.
- verbatim-carried — approver-approved flavor must appear byte-intact
                (whitespace-normalized) somewhere in the draft.

Inventions are judged ONCE against the combined original corpus (prose
+ procedure renders + carried spans + table content), so a rendered
table in the draft is never mistaken for invented prose; the table tier
carries the reverse clause (a draft table row no source row accounts
for is an invented row), and — the cadence experiment's catch —
the ADDITIVE clause: extra cells inside a matched row are allowed only
when the combined original corpus accounts for them (restructuring
latitude covers merging canon-held facts into a table, never smuggling
new values). Approved Omission rows (scope: corpus-wide or
this artifact) clear omissions.

KNOWN GAP, accepted for v0: headings are structure on both sides —
free to rename, never claims — so a fact smuggled INTO a heading
("the tide rises twice at night") escapes the judge. The convergence loop and
approver spot-checks (D13) are the net until a judge with judgment
arrives; revisit if M1 shows real leakage.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import comprehension, judge, procedures
from .grammars import get_optional as grammar_for
from .judge import (DISTORTED, INVENTED, OMITTED_APPROVED,
                    OMITTED_UNAPPROVED)
from .parsers import EMPTY_MARKERS, parse_bool, parse_float, parse_int

COLUMNS_OPT = re.compile(r"\|columns=([^}|]+)")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
SEPARATOR_ROW = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


@dataclass
class RoundFinding:
    """One judged difference as a ROW (findings-as-rows): queryable in the reading
    room beside the section it judges; the prose report renders these.
    Identity is content-derived, so a re-judge recreates the same row
    ids and the room can preserve worked statuses across runs."""
    tier: str
    kind: str            # omitted | distorted | invented | cell-loss | ...
    message: str         # the report line (human prose)
    original: str = ""
    regenerated: str = ""
    section_id: str = ""
    section_heading: str = ""
    status: str = "open"

    def __str__(self):
        return self.message

    @property
    def identity(self):
        digest = hashlib.sha256(
            f"{self.tier}|{self.kind}|{self.original}|"
            f"{self.regenerated}".encode()).hexdigest()
        return f"{digest[:16]}"

    def row(self):
        # the kind IS the verdict code; the designer-facing ref rides
        # beside it (the record shape), and the archive keeps every key
        # it always had
        from .report import ref_key
        return {"id": self.identity, "tier": self.tier,
                "kind": self.kind, "code": self.kind,
                "ref": ref_key(self.kind), "message": self.message,
                "original": self.original,
                "regenerated": self.regenerated,
                "section_id": self.section_id,
                "section_heading": self.section_heading,
                "status": self.status}


@dataclass
class TierResult:
    tier: str
    findings: list = field(default_factory=list)   # human-facing strings
    approved: int = 0
    checked: int = 0

    @property
    def passed(self):
        return not self.findings


@dataclass
class RoundtripResult:
    scope: str
    tiers: list = field(default_factory=list)
    surface: str = ""   # every PASS names its judged surface (retro rule)
    fingerprint: str = ""   # the judged artifact's identity
    attribution: list = field(default_factory=list)  # [Attribution] (the canon-attribution pass)

    def findings_rows(self):
        return [finding.row() for tier in self.tiers
                for finding in tier.findings]

    @property
    def passed(self):
        return all(tier.passed for tier in self.tiers)


# -- table tier -----------------------------------------------------------

# The comparison kinds a typed column is judged under. `text` is byte-exact
# (whitespace-normalized already by the cell reader); the rest relax equality
# to the value-space the declaration says the column IS.
KIND_TEXT = "text"
KIND_INT = "int"
KIND_FLOAT = "float"
KIND_BOOL = "bool"
KIND_SET = "set"   # an edge-carried multi-value cell: order-free membership
# A grammar-structured cell (e.g. a requirements clause): compared through
# the declaration's own grammar so phrasing/word-order/clause-order are free
# but a dropped or changed requirement still reds. The kind carries the
# grammar name from the declaration (never a literal here — the engine speaks
# no corpus vocabulary), as "grammar:<name>".
KIND_GRAMMAR_PREFIX = "grammar:"


def _catalog_kind(catalog, prop):
    """The comparison kind a catalog property's type maps to. enum: and
    text both stay byte-exact — only numbers/booleans/sets relax."""
    from .ontology import PropType
    ptype = (catalog.get(prop) or {}).get("type", PropType.TEXT)
    if ptype == PropType.INT:
        return KIND_INT
    if ptype == PropType.FLOAT:
        return KIND_FLOAT
    if ptype == PropType.BOOL:
        return KIND_BOOL
    return KIND_TEXT


def column_types(ontology):
    """{(csv relpath, column): kind} for every column a declaration TYPES —
    threaded into the table judge so a number compares as a number, a
    boolean as a boolean, an edge-carried multi-value cell as an order-free
    SET, and a grammar-structured cell through its own grammar. Columns no
    declaration types stay byte-exact (absent from the map). Reads a label's
    own `source:` CSV (properties -> catalog type, plain relationships ->
    set, parser columns -> grammar), its `property_tables:`, and the
    render/judge-only `rendered_view:` (Leg 2) — including a multi-label
    view's per-label `labels:` entries, each typed against ITS OWN label's
    catalog. None ontology -> empty map -> every column byte-exact."""
    from .ontology import (Reader, node_reader, rendered_views_of,
                           source_files_of)
    index = {}
    if ontology is None:
        return index

    def type_columns(relpath, catalog, properties, rels):
        for prop, mapping in (properties or {}).items():
            column = (mapping or {}).get("column")
            if column:
                index[(relpath, column)] = _catalog_kind(catalog, prop)
        for rel in rels or []:
            if not isinstance(rel, dict):
                continue
            column = rel.get("column")
            if not column:
                continue
            # a parser cell (no foreign source, no edge table) is compared
            # through its declared grammar; the grammar NAME rides the kind
            if rel.get("parser") and not rel.get("source") \
                    and not rel.get("from_column"):
                index[(relpath, column)] = KIND_GRAMMAR_PREFIX + rel["parser"]
            # a plain column<->edge map (no from_column edge table, no
            # foreign source) renders as a multi-value set cell
            elif not rel.get("from_column") and not rel.get("source"):
                index[(relpath, column)] = KIND_SET

    def catalog_of(label):
        spec = ontology.nodes.get(label)
        return (spec or {}).get("catalog") or {} if isinstance(spec, dict) \
            else {}

    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        catalog = spec.get("catalog") or {}
        files = source_files_of(spec)
        if files and node_reader(spec) == Reader.CSV_ROWS:
            type_columns(files[0], catalog, spec.get("properties"),
                         spec.get("relationships"))
        for rview in rendered_views_of(spec):
            if not rview.get("source"):
                continue
            relpath = rview["source"]
            type_columns(relpath, catalog, rview.get("properties"),
                         rview.get("relationships"))
            # multi-label view: each entry types against its own label
            for entry in rview.get("labels") or []:
                if isinstance(entry, dict) and entry.get("label"):
                    type_columns(relpath, catalog_of(entry["label"]),
                                 entry.get("properties"),
                                 entry.get("relationships"))
        for table in spec.get("property_tables") or []:
            if isinstance(table, dict) and table.get("source"):
                type_columns(table["source"], catalog,
                             table.get("properties"), None)
    return index


def column_aliases(ontology):
    """{(csv relpath, column): {cell text -> canonical name}} — the declared
    aliases of every label whose citizens a rendered column names. A source
    cell that references a citizen by a declared alias is semantic identity,
    not a red (Fix 1). This covers both the KEY (row-label) column — through
    the owning label(s)' aliases — and any citizen-reference column, an edge
    column that names its TARGET label's citizens (a size code 'M' is the
    'Medium' citizen; an ambiguous term may be a declared list-alias of two
    citizens). Multi-label views merge every contributor's
    aliases onto the shared key column. None ontology -> empty map."""
    from .ontology import rendered_views_of, source_files_of
    index = {}
    if ontology is None:
        return index

    def add(relpath, column, label):
        spec = ontology.nodes.get(label)
        aliases = (spec or {}).get("aliases") if isinstance(spec, dict) else None
        if relpath and column and aliases:
            index.setdefault((relpath, column), {}).update(aliases)

    def add_rels(relpath, rels):
        for rel in rels or []:
            if isinstance(rel, dict) and rel.get("column") and rel.get("to"):
                add(relpath, rel["column"], rel["to"])

    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        files = source_files_of(spec)
        if files:
            add(files[0], spec.get("key"), label)
            add_rels(files[0], spec.get("relationships"))
        for rview in rendered_views_of(spec):
            if not rview.get("source"):
                continue
            relpath, keycol = rview["source"], rview.get("key")
            add(relpath, keycol, label)
            add_rels(relpath, rview.get("relationships"))
            for entry in rview.get("labels") or []:
                if isinstance(entry, dict) and entry.get("label"):
                    add(relpath, keycol, entry["label"])
                    add_rels(relpath, entry.get("relationships"))
    return index


def _set_of(raw):
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _aliased_equal(a, b, aliases):
    """Two name cells are the same citizen when equal outright, or when a
    declared alias maps one to the other (a list-valued alias — a term that
    resolves ambiguously — matches if the other side is one of its
    targets)."""
    if a == b:
        return True
    if not aliases:
        return False
    for x, y in ((a, b), (b, a)):
        target = aliases.get(x)
        if target == y or (isinstance(target, list) and y in target):
            return True
    return False


def _grammar_equiv(grammar_name, source_raw, draft_raw):
    """Two grammar-structured cells are equivalent when the declaration's
    grammar parses them to the same requirements — the structured clauses
    order-free, and the verbatim remainder the grammar could not structure
    normalized and order-free. A missing grammar falls back to byte-exact."""
    parse = grammar_for(grammar_name)
    if parse is None:
        return source_raw == draft_raw
    source_parsed, source_rest = parse(source_raw)
    draft_parsed, draft_rest = parse(draft_raw)

    def norm_parsed(items):
        return sorted(tuple(sorted(item.items())) for item in items)

    def norm_rest(items):
        return sorted(" ".join(str(item).lower().split()) for item in items)

    return (norm_parsed(source_parsed) == norm_parsed(draft_parsed)
            and norm_rest(source_rest) == norm_rest(draft_rest))


def _cell_matches(kind, source_raw, draft_raw, aliases=None):
    """Does a draft cell carry the same VALUE as a source cell, under the
    source column's declared kind? text is byte-exact (or alias-equal for a
    name cell); numbers/booleans compare in their value-space ('+2' == '2'
    == 2, 'Y' == true); a set cell compares order-free; a grammar cell
    through its declaration's grammar."""
    if kind == KIND_SET:
        source_set, draft_set = _set_of(source_raw), _set_of(draft_raw)
        if not aliases:
            return source_set == draft_set
        # order-free AND alias-aware: every element on each side has an
        # alias-equal partner on the other (a size code 'M' == the citizen
        # 'Medium'; 'Ruby' == its list-alias member 'Ruby (cut)')
        return (all(any(_aliased_equal(s, d, aliases) for d in draft_set)
                    for s in source_set)
                and all(any(_aliased_equal(s, d, aliases) for s in source_set)
                        for d in draft_set))
    if kind.startswith(KIND_GRAMMAR_PREFIX):
        return _grammar_equiv(kind[len(KIND_GRAMMAR_PREFIX):],
                              source_raw, draft_raw)
    if kind in (KIND_INT, KIND_FLOAT):
        parse = parse_int if kind == KIND_INT else parse_float
        source_value, source_ok = parse(source_raw)
        draft_value, draft_ok = parse(draft_raw)
        return (source_ok and draft_ok and source_value is not None
                and source_value == draft_value)
    if kind == KIND_BOOL:
        source_value, source_ok = parse_bool(source_raw)
        draft_value, draft_ok = parse_bool(draft_raw)
        return source_ok and draft_ok and source_value == draft_value
    return _aliased_equal(source_raw, draft_raw, aliases)


def _row_covered(source_cells, draft_row):
    """A draft table row (a set of raw cell strings) HOLDS a source row when
    every source cell has some draft cell equal to it under that cell's
    kind. The subset check of the untyped era, made type-aware. Source
    cells are (kind, raw, aliases) triples."""
    return all(
        any(_cell_matches(kind, raw, draft_raw, aliases)
            for draft_raw in draft_row)
        for kind, raw, aliases in source_cells)


def table_ref_columns(span_text):
    match = COLUMNS_OPT.search(span_text)
    if not match:
        return None
    return [column.strip() for column in match.group(1).split(",")
            if column.strip()]


def strip_tables(text):
    """Markdown table rows out — tables are the table tier's business;
    the claim tiers judge prose only."""
    return "\n".join(line for line in text.splitlines()
                     if not TABLE_ROW.match(line))


def draft_table_rows(draft_text):
    """Every BODY row of every markdown table in the draft as a set of
    cell strings. Header rows (the row a separator line underlines) are
    structure, not data — excluded, like headings in prose."""
    lines = draft_text.splitlines()
    rows = []
    for index, line in enumerate(lines):
        match = TABLE_ROW.match(line)
        if not match or SEPARATOR_ROW.match(line):
            continue
        if index + 1 < len(lines) and TABLE_ROW.match(lines[index + 1]) \
                and SEPARATOR_ROW.match(lines[index + 1]):
            continue  # header row
        cells = {cell.strip() for cell in match.group(1).split("|")
                 if cell.strip()}
        if cells:
            rows.append(cells)
    return rows


def corpus_blob(sections, cited_specs, base_dir):
    """The combined original corpus as one normalized haystack — what
    the invention pass judges against, reused by the table tier's
    additive clause (the cadence experiment)."""
    parts = []
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] == comprehension.TABLE:
                try:
                    text = (Path(base_dir) / span["table"]).read_text(
                        encoding="utf-8")
                except OSError:
                    continue
                for row in csv.DictReader(io.StringIO(text)):
                    parts.extend(str(v).strip() for v in row.values()
                                 if str(v or "").strip())
            else:
                parts.append(span["text"])
    for _, spec in cited_specs:
        parts.append(procedures.render_markdown(spec))
    return " ".join(" ".join(parts).lower().split())


def judge_tables(sections, base_dir, draft_text, blob="", col_types=None,
                 col_aliases=None):
    """Judge the table tier at TYPE-AWARE equivalence (Leg 1). A source
    cell is compared to the draft in the value-space its column declares:
    numeric-typed columns as numbers ('+2' == '2' == 2), boolean-typed as
    booleans ('Y' == true), edge-carried multi-value cells as order-free
    sets, grammar-typed cells through their grammar, and a name cell through
    the label's declared aliases; every other column stays byte-exact.
    `col_types` is {(relpath, column): kind}; `col_aliases` is
    {(relpath, column): {alias -> canonical}}; empty/None maps judge every
    column byte-exact (the untyped behaviour, unchanged). A source cell that
    is an EMPTY MARKER ('—', '-', 'N/A', '') carries no information — it is
    not required in the draft (parity: no information is lost when nothing
    was there)."""
    col_types = col_types or {}
    col_aliases = col_aliases or {}
    result = TierResult("table")
    draft_rows = draft_table_rows(draft_text)
    source_rows = []   # list of cells where cells = [(kind, raw, aliases), ..]
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] != comprehension.TABLE:
                continue
            relpath = span["table"]
            columns = table_ref_columns(span["text"])
            try:
                text = (Path(base_dir) / relpath).read_text(encoding="utf-8")
            except OSError as exc:
                result.findings.append(RoundFinding(
                    tier="table", kind="unreadable-source",
                    message=f"{relpath}: the source table is unreadable "
                            f"({exc})",
                    original=relpath, section_id=section["id"],
                    section_heading=section["heading"]))
                continue
            for row in csv.DictReader(io.StringIO(text)):
                # collapse internal whitespace (newlines, runs of spaces) the
                # same way the rendered draft cell does — format is free to
                # improve, so a multi-line source cell and its one-line draft
                # are the same VALUE, not a difference
                cells = [(col_types.get((relpath, column), KIND_TEXT),
                          " ".join(str(value).split()),
                          col_aliases.get((relpath, column)))
                         for column, value in row.items()
                         if (columns is None or column in columns)
                         and " ".join(str(value or "").split())
                         and " ".join(str(value).split()) not in EMPTY_MARKERS]
                if not cells:
                    continue
                source_rows.append(cells)
                result.checked += 1
                if not any(_row_covered(cells, draft_row)
                           for draft_row in draft_rows):
                    key = next(iter(row.values()), "?")
                    missing = ", ".join(sorted(raw for _, raw, _ in cells))
                    result.findings.append(RoundFinding(
                        tier="table", kind="cell-loss",
                        message=f"{relpath} row '{key}': no draft table "
                                f"row holds all of [{missing}] together "
                                "— cell-level loss or a split row",
                        original=missing, section_id=section["id"],
                        section_heading=section["heading"]))
    # the reverse clause: a draft table row no source row accounts for
    # is an INVENTED row; extra cells inside a MATCHED row are allowed
    # only when the combined corpus accounts for them (the cadence experiment — the
    # additive direction is judged, not waved through)
    for draft_row in draft_rows:
        matched = [cells for cells in source_rows
                   if _row_covered(cells, draft_row)]
        if not matched:
            cells = ", ".join(sorted(draft_row))
            result.findings.append(RoundFinding(
                tier="table", kind="invented-row",
                message=f"invented table row — no source table has a "
                        f"row for [{cells}]",
                regenerated=cells))
            continue
        # a draft cell is explained if some matched source cell matches it
        explained = {
            draft_raw for draft_raw in draft_row
            if any(_cell_matches(kind, raw, draft_raw, aliases)
                   for cells in matched for kind, raw, aliases in cells)}
        unaccounted = sorted(
            cell for cell in draft_row - explained
            if " ".join(cell.lower().split()) not in blob)
        if unaccounted:
            cells = ", ".join(unaccounted)
            result.findings.append(RoundFinding(
                tier="table", kind="additive-cells",
                message=f"additive cells in a matched table row — the "
                        f"original corpus nowhere accounts for "
                        f"[{cells}]",
                regenerated=cells))
    return result


# -- claim tiers ----------------------------------------------------------


def _keep_original_side(scorecard, result, label, origin=None):
    for verdict in scorecard.verdicts:
        result.checked += 1
        section_id, heading = (origin or {}).get(verdict.original,
                                                 ("", ""))
        where = f" [§ {heading}]" if heading else ""
        if verdict.verdict == OMITTED_UNAPPROVED:
            result.findings.append(RoundFinding(
                tier=result.tier, kind="omitted",
                message=f"{label}{where}: omitted with no approval on "
                        f"record — \"{verdict.original}\"",
                original=verdict.original,
                section_id=section_id, section_heading=heading))
        elif verdict.verdict == DISTORTED:
            result.findings.append(RoundFinding(
                tier=result.tier, kind="distorted",
                message=f"{label}{where}: distorted — original "
                        f"\"{verdict.original}\" → "
                        f"draft \"{verdict.regenerated}\"",
                original=verdict.original,
                regenerated=verdict.regenerated,
                section_id=section_id, section_heading=heading))
        elif verdict.verdict == OMITTED_APPROVED:
            result.approved += 1


def judge_procedures(cited_specs, draft_text, approved, sections=()):
    """The approved programs' atoms must survive into the draft."""
    result = TierResult("procedure")
    prose_only = strip_tables(draft_text)
    by_heading = {section["heading"]: section["id"]
                  for section in sections}
    for proc_name, spec in cited_specs:
        rendered = procedures.render_markdown(spec)
        _, targets, _ = procedures.specified_in_of(spec)
        # Multi-section citations (the multi-section citation rule) anchor findings to the FIRST
        # listed section — the program's primary home.
        target = targets[0] if targets else ""
        origin = {claim: (by_heading.get(target, ""), target)
                  for claim in judge.claims_of(rendered)} if target else None
        card = judge.judge(rendered, prose_only,
                           approved_omissions=approved)
        _keep_original_side(card, result, proc_name, origin)
    return result


def judge_prose(sections, draft_text, approved):
    result = TierResult("rule-prose")
    texts, origin = [], {}
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] in (comprehension.RULE_PROSE,
                                 comprehension.PROCEDURE):
                texts.append(span["text"])
                for claim in judge.claims_of(span["text"]):
                    origin.setdefault(
                        claim, (section["id"], section["heading"]))
    card = judge.judge("\n\n".join(texts), strip_tables(draft_text),
                       approved_omissions=approved)
    _keep_original_side(card, result, "prose", origin)
    return result


def judge_carried(sections, draft_text):
    result = TierResult("verbatim-carried")
    haystack = " ".join(draft_text.split())
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] != comprehension.VERBATIM_CARRIED:
                continue
            result.checked += 1
            if " ".join(span["text"].split()) not in haystack:
                result.findings.append(RoundFinding(
                    tier="verbatim-carried", kind="missing-carried",
                    message=f"approved flavor text missing from the "
                            f"draft: \"{span['text'][:80]}…\"",
                    original=span["text"],
                    section_id=section["id"],
                    section_heading=section["heading"]))
    return result


def judge_inventions(sections, cited_specs, base_dir, draft_text, approved):
    """One combined pass so nothing legitimate reads as invented."""
    result = TierResult("invented")
    corpus = []
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] == comprehension.TABLE:
                try:
                    text = (Path(base_dir) / span["table"]).read_text(
                        encoding="utf-8")
                except OSError:
                    continue
                for row in csv.DictReader(io.StringIO(text)):
                    corpus.append(" ".join(
                        str(v).strip() for v in row.values()
                        if str(v or "").strip()))
            else:
                corpus.append(span["text"])
    for _, spec in cited_specs:
        corpus.append(procedures.render_markdown(spec))
    card = judge.judge("\n\n".join(corpus), strip_tables(draft_text),
                       approved_omissions=approved)
    for verdict in card.verdicts:
        if verdict.verdict == INVENTED:
            result.findings.append(RoundFinding(
                tier="invented", kind="invented",
                message=f"the original never says this: "
                        f"\"{verdict.regenerated}\"",
                regenerated=verdict.regenerated))
    result.checked = len(card.verdicts)
    return result


# -- the harness ----------------------------------------------------------


# scope sentinel: consult EVERY row regardless of its scope — the
# whole-book unit (the canon-attribution pass) judges one artifact that spans all scopes
ALL_SCOPES = "*"


def _scope_covers(row_scope, scope):
    return not row_scope or row_scope == scope or scope == ALL_SCOPES


def approved_differences_for(base_dir, scope):
    """Approved Difference rows for this artifact (or corpus-wide): the
    owner ruled that the regeneration RENDERS one thing where the original
    SAYS another (a corrected typo, a renamed term, a reworked example).
    Each row's `original` property holds the original's wording (excused
    from omission/distortion) and its name holds the approved rendering
    (excused from invention). Returns (originals, renderings)."""
    originals, renderings = [], []
    nodes_path = Path(base_dir) / "graph" / "export" / "nodes.jsonl"
    if nodes_path.exists():
        for line in nodes_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["label"] != "Approved Difference":
                continue
            props = record["properties"]
            row_scope = (props.get("scope") or "").strip()
            if _scope_covers(row_scope, scope):
                if props.get("original"):
                    originals.append(props["original"])
                renderings.append(record["name"])
    return originals, renderings


def _difference_key(text):
    """Aggressive normalization for matching judge findings to Approved
    Difference rows: case, punctuation, and whitespace all fold away."""
    import re as _re
    return _re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def apply_approved_differences(tiers, originals, renderings):
    """Drop findings the owner has ruled on: a finding whose original-side
    text sits inside an approved row's original, or whose regenerated text
    sits inside an approved rendering, is an approved difference, not a
    defect. Containment (not equality) so one ruled row covers every claim
    of a reworked passage."""
    ok_originals = [_difference_key(o) for o in originals]
    ok_renderings = [_difference_key(r) for r in renderings]

    def _covered(text, ruled):
        key = _difference_key(text)
        return bool(key) and any(key in b for b in ruled)

    for tier in tiers:
        if tier.tier not in ("rule-prose", "invented", "verbatim-carried"):
            continue
        kept = []
        for finding in tier.findings:
            original = getattr(finding, "original", None)
            regenerated = getattr(finding, "regenerated", None)
            if original and _covered(original, ok_originals):
                tier.approved += 1
                continue
            if regenerated and _covered(regenerated, ok_renderings):
                tier.approved += 1
                continue
            kept.append(finding)
        tier.findings = kept
    return tiers


def approved_omissions_for(base_dir, scope, ledger_path=None):
    """Approved Omission rows for this artifact (or corpus-wide) — the
    same rows the graph holds as Judgment citizens. ledger_path
    overrides the project-default location (split-ready, the engine split)."""
    entries = []
    # post-flip: the ledger rows are canon citizens — read the backup
    nodes_path = Path(base_dir) / "graph" / "export" / "nodes.jsonl"
    if nodes_path.exists():
        for line in nodes_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["label"] != "Approved Omission":
                continue
            row_scope = (record["properties"].get("scope") or "").strip()
            if _scope_covers(row_scope, scope):
                entries.append(record["name"])
    # bootstrap fallback: the file-era ledger (fixture repos, fresh
    # projects before their first export)
    path = Path(ledger_path) if ledger_path \
        else Path(base_dir) / "data" / "approved-omissions.csv"
    if path.exists():
        for row in csv.DictReader(io.StringIO(
                path.read_text(encoding="utf-8"))):
            row_scope = (row.get("Scope") or "").strip()
            if _scope_covers(row_scope, scope):
                claim = (row.get("Omission") or "").strip()
                if claim and claim not in entries:
                    entries.append(claim)
    return entries


def carried_passages_for(base_dir, scope):
    """Registered Verbatim rows for this artifact (or corpus-wide) —
    canon citizens read from the backup (the verbatim-carriage rule; medium: text)."""
    nodes_path = Path(base_dir) / "graph" / "export" / "nodes.jsonl"
    if not nodes_path.exists():
        return []
    passages = []
    for line in nodes_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["label"] != "Verbatim":
            continue
        props = record["properties"]
        if (props.get("medium") or "text") != "text":
            continue
        row_scope = (props.get("scope") or "").strip()
        if _scope_covers(row_scope, scope):
            # the name is the judge-normalized matching key; the text
            # property carries the original bytes — casing is information
            # (owner ruling at the wave-2 gate), so regeneration reads
            # the bytes, and normalization stays matching-only
            passages.append(props.get("text") or record["name"])
    return passages


def run(base_dir, scope, draft_path, cited_sections=(), cited_specs=(),
        carried_texts=None, ontology=None, canon_scope=None,
        consulted=None):
    """The whole harness: original (through the reading room) vs draft,
    every tier, one result. `ontology` (when given) supplies the table
    tier's column typing (Leg 1) — without it every table column is judged
    byte-exact. `canon_scope` overrides which Approved Omission /
    Difference / Verbatim rows apply (ALL_SCOPES for the whole-book
    unit); `consulted` is the drafter's trace-recorded citizen set for
    the strong-form earned check (the canon-attribution pass)."""
    base_dir = Path(base_dir)
    rows_scope = canon_scope or scope
    col_types = column_types(ontology)
    col_aliases = column_aliases(ontology)
    if carried_texts is None:
        carried_texts = carried_passages_for(base_dir, rows_scope)
    data = (base_dir / scope).read_bytes()
    reading = comprehension.read_artifact(
        data, title=Path(scope).name, origin=scope,
        cited_sections=cited_sections, carried_texts=carried_texts)
    draft_text = Path(draft_path).read_text(encoding="utf-8")
    ad_originals, ad_renderings = approved_differences_for(base_dir,
                                                           rows_scope)
    approved = approved_omissions_for(base_dir, rows_scope) + ad_originals
    result = RoundtripResult(scope=scope,
                             fingerprint=reading.fingerprint)
    span_counts = {}
    for section in reading.sections:
        for span in section.get("spans", []):
            span_counts[span["class"]] = \
                span_counts.get(span["class"], 0) + 1
    result.surface = (
        f"Judged surface: {len(reading.sections)} sections — "
        + ", ".join(f"{count} {cls}"
                    for cls, count in sorted(span_counts.items()))
        + " spans; unjudged: none.")
    blob = corpus_blob(reading.sections, cited_specs, base_dir)
    result.tiers = [
        judge_tables(reading.sections, base_dir, draft_text, blob=blob,
                     col_types=col_types, col_aliases=col_aliases),
        judge_procedures(cited_specs, draft_text, approved,
                         sections=reading.sections),
        judge_prose(reading.sections, draft_text, approved),
        judge_carried(reading.sections, draft_text),
        judge_inventions(reading.sections, cited_specs, base_dir,
                         draft_text, approved),
    ]
    apply_approved_differences(result.tiers, ad_originals, ad_renderings)
    # canon attribution (the canon-attribution pass): every draft claim seeks its graph home,
    # judged against the committed export (fixture repos without an
    # export simply have no canon to attribute against — empty census)
    export_nodes = base_dir / "graph" / "export" / "nodes.jsonl"
    export_edges = base_dir / "graph" / "export" / "edges.jsonl"
    if export_nodes.exists() and export_edges.exists():
        from . import attribution as attribution_mod
        from .restore import read_export
        invented = [f.regenerated
                    for tier in result.tiers if tier.tier == "invented"
                    for f in tier.findings if f.regenerated]
        result.attribution = attribution_mod.census(
            draft_text, read_export(export_nodes.parent),
            invented=invented, consulted=consulted)
    return result


ROUNDTRIP_REPORT_FILE = "roundtrip-report.json"


def roundtrip_report(result, base_dir=None, kb=None):
    """The scorecard as one record: scope, the judged artifact's
    identity, the pass flag, one row per tier with its findings as
    rows, the judged-surface sentence, and the census as rows. The
    prose scorecard is a rendering of this — the doctrine already
    said so; now the code does."""
    from .report import record_header
    doc: dict = (record_header(base_dir, "roundtrip-report") if base_dir
                 else {"kind": "roundtrip-report"})
    kb = kb or doc.get("kb")
    doc.update(scope=result.scope, fingerprint=result.fingerprint,
               passed=result.passed)
    doc["tiers"] = [{"tier": tier.tier, "passed": tier.passed,
                     "checked": tier.checked, "approved": tier.approved,
                     "findings": [f.row() for f in tier.findings]}
                    for tier in result.tiers]
    if result.surface:
        doc["surface"] = result.surface
    if result.attribution:
        doc["census"] = [r.row(kb=kb) for r in result.attribution]
        counts = {}
        for r in result.attribution:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        doc["census_counts"] = counts
    return doc


def render_report(result):
    """The prose scorecard, rendered FROM the record: the summary line
    from the tier rows, each failing tier's findings from its rows, the
    surface sentence, and the census (whose renderer already reads its
    own rows)."""
    doc = roundtrip_report(result)
    lines = [f"# Round-trip parity scorecard — {doc['scope']}", ""]
    lines.append("**" + ("PASS" if doc["passed"] else "FAIL") + "** — "
                 + " · ".join(
                     f"{tier['tier']}: "
                     + ("green" if tier["passed"]
                        else f"{len(tier['findings'])} red")
                     + (f" ({tier['approved']} approved omission"
                        + ("s)" if tier["approved"] != 1 else ")")
                        if tier["approved"] else "")
                     for tier in doc["tiers"]))
    lines.append("")
    for tier in doc["tiers"]:
        if tier["passed"]:
            continue
        lines += [f"## {tier['tier']} — the differences, named", ""]
        lines += [f"- {row['message']}" for row in tier["findings"]] + [""]
    if doc["passed"]:
        lines += ["Zero inventions, zero distortions, zero unapproved "
                  "omissions, zero cell-level loss.", ""]
    if doc.get("surface"):
        lines += [doc["surface"], ""]
    if result.attribution:
        from . import attribution as attribution_mod
        lines += [attribution_mod.render_census(result.attribution), ""]
    return "\n".join(lines)
