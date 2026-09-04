"""The reading room: a comprehension graph per intake round.

Canon is the knowledge; a dumped artifact's insides are comprehension
material (ruled at the canon-primacy gate, 2026-07-31 — see its Decision row).
This module builds the machine's understanding of one artifact — its
fingerprint identity, its section tree with bodies, order, and embedded
table references — in a separate workspace database with a
build → archive → dispose lifecycle:

- BUILD: the live reading room is ONE well-known workspace database
  (default 'comprehension'), wiped per round like scratch. Never a
  standing database per asset.
- ARCHIVE: at round close the room serializes to small flat JSONL files
  filed with the proposal (git-tracked — ordinary git recovery is the
  first line of deletion defense). Archives batch-import: any set of
  rounds rehydrates into the workspace in one command, coexisting
  because every citizen carries its artifact's fingerprint.
- DISPOSE: the live room is wiped; the archive is the record.

Identity is deletion-tolerant by construction: an artifact's id is the
sha256 of its bytes (your Downloads copy and a co-worker's Temp copy are
the same artifact); a section's id is fingerprint-prefix : position-path
("3f2a9c1d4e5b:2.0.1") — deterministic, so the structure layer of a lost
archive recomputes bit-identical from the immutable artifact. Canon never
references comprehension ids (fingerprint + span only), so canon
integrity survives total archive loss. Duplicate headings are a
non-event: ids come from position, never from heading text — quirks
inside a dumped artifact are the pipeline's job, never the submitter's.

Pure logic (fingerprint/read/serialize/parse) is driver-free and
unit-tested; only the load/wipe helpers touch the neo4j driver.
"""

import csv as _csv
import hashlib
import io as _io
import json
import re as _re
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import parsers

WORKSPACE_DATABASE = "comprehension"
ARCHIVE_ARTIFACT = "artifact.json"
ARCHIVE_SECTIONS = "sections.jsonl"

# {{csv:data/foo.csv}} or {{csv:data/foo.csv|columns=...}} — the book
# build's table-embed syntax; comprehension records which tables a
# section embeds so structure survives without re-parsing prose.
CSV_REF = re.compile(r"\{\{csv:([^}|]+)(?:\|[^}]*)?\}\}")

# Content classes: every span of a section is classified so the
# round-trip harness can dispatch it to the right renderer and judging
# bar. Deduction is mechanical and corpus-neutral only:
#   table          — a {{csv:}} embed line
#   procedure      — the section is cited by a procedure's specified_in
#   rule-prose     — the default for prose; the machine never guesses flavor
#   verbatim-carried — approver-assigned at the plan gate, never deduced.
#     v0 records ratified overrides in the round's archive; a standing
#     override registry is deliberately deferred until the Phase 2
#     campaign forces it.
TABLE = "table"
PROCEDURE = "procedure"
RULE_PROSE = "rule-prose"
VERBATIM_CARRIED = "verbatim-carried"


def carried_patterns(carried_texts):
    """Compile registered verbatim passages into whitespace-tolerant
    patterns (the registry keys by normalized text; artifacts wrap
    lines freely)."""
    patterns = []
    for text in carried_texts or ():
        tokens = [_re.escape(token) for token in text.split()]
        if tokens:
            # registry keys are judge-normalized (lowercased); the match
            # is case-tolerant, but the SPAN keeps the artifact's exact
            # bytes — carriage is byte-faithful to the original
            patterns.append(_re.compile(r"\s+".join(tokens),
                                        _re.IGNORECASE))
    return patterns


def split_carried(text, patterns):
    """Split a prose run around registered verbatim passages: the exact
    matched bytes become verbatim-carried; the rest stays prose.
    Returns [(piece_text, is_carried), ...] in order."""
    pieces = [(text, False)]
    for pattern in patterns:
        next_pieces = []
        for piece, is_carried in pieces:
            if is_carried:
                next_pieces.append((piece, is_carried))
                continue
            cursor = 0
            for match in pattern.finditer(piece):
                before = piece[cursor:match.start()]
                if before.strip():
                    next_pieces.append((before.strip("\n"), False))
                next_pieces.append((match.group(0), True))
                cursor = match.end()
            rest = piece[cursor:]
            if cursor == 0 or rest.strip():
                next_pieces.append((rest.strip("\n") if cursor else piece,
                                    False))
        pieces = [(piece, carried) for piece, carried in next_pieces
                  if piece.strip() or carried]
    return pieces


def split_spans(body, prose_class=RULE_PROSE, patterns=()):
    """A section body as ordered spans: table spans (the {{csv:}} lines,
    carrying the csv path) and prose runs between them. Prose runs
    containing registered verbatim passages split further (the verbatim-carriage rule): the
    passage's exact bytes class as verbatim-carried."""
    spans = []
    prose_lines = []

    def flush():
        text = "\n".join(prose_lines).strip("\n")
        if text.strip():
            for piece, is_carried in split_carried(text, patterns):
                spans.append({
                    "class": VERBATIM_CARRIED if is_carried
                    else prose_class,
                    "text": piece})
        prose_lines.clear()

    for line in body.splitlines():
        cursor = 0
        matched = False
        for match in CSV_REF.finditer(line):
            matched = True
            before = line[cursor:match.start()]
            if before.strip():
                prose_lines.append(before)
            flush()
            spans.append({"class": TABLE, "text": match.group(0),
                          "table": match.group(1).strip()})
            cursor = match.end()
        remainder = line[cursor:]
        if matched:
            if remainder.strip():
                prose_lines.append(remainder)
        else:
            prose_lines.append(line)
    flush()
    return spans


def carried_fraction(sections):
    """Chars of verbatim-carried prose over all prose chars — the
    honesty-valve metric. The ceiling is approver-set and enforced by
    the round-trip harness; here it is reported."""
    carried = total = 0
    for section in sections:
        for span in section.get("spans", []):
            if span["class"] == TABLE:
                continue
            total += len(span["text"])
            if span["class"] == VERBATIM_CARRIED:
                carried += len(span["text"])
    return (carried / total) if total else 0.0


@dataclass
class Reading:
    """One artifact, understood: identity + section tree."""
    fingerprint: str          # sha256 hex of the artifact's bytes
    title: str                # display metadata, never identity
    origin: str               # where the bytes came from (display only)
    sections: list = field(default_factory=list)  # dicts, document order

    @property
    def short(self):
        return self.fingerprint[:12]


def fingerprint_bytes(data):
    return hashlib.sha256(data).hexdigest()


# -- the floor receipt: any artifact's identity, before anyone reads it --
#
# The front door promises any artifact (text, image, model, audio, link).
# Every artifact enters at least at its floor receipt — a whole-file
# fingerprint, its size, and the medium its BYTES declare (never its
# file extension) — and a non-text artifact is cited on the citizen it
# is about by that receipt, with an observation of what it shows. The
# reading room's structural comprehension is text-only and says so.

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"\xff\xd8\xff", "image"),
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"%PDF-", "pdf"),
    (b"ID3", "audio"),
    (b"fLaC", "audio"),
    (b"OggS", "audio"),
)
_MEDIUM_PHRASE = {"image": "an image", "pdf": "a PDF", "audio": "audio",
                  "binary": "binary data", "text": "text"}


def sniff_medium(data):
    """The medium an artifact's bytes declare: text, image, pdf, audio,
    or binary (bytes the engine recognizes as neither text nor a known
    medium)."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio"
    for signature, medium in _SIGNATURES:
        if data.startswith(signature):
            return medium
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    return "text"


def receipt(data):
    """The floor receipt: fingerprint, size in bytes, medium."""
    return {"fingerprint": fingerprint_bytes(data), "bytes": len(data),
            "medium": sniff_medium(data)}


class NotTextArtifact(ValueError):
    """A non-text artifact handed to the reading room. The refusal
    carries the artifact's floor receipt, so what arrived is still on
    record even though its structure cannot be read."""

    def __init__(self, title, floor_receipt):
        self.title = title
        self.receipt = floor_receipt
        medium = _MEDIUM_PHRASE.get(floor_receipt["medium"],
                                    floor_receipt["medium"])
        super().__init__(
            f"Attempted to read artifact {title} into the reading room. "
            f"Failed due to: it is {medium}, not text (fingerprint "
            f"{floor_receipt['fingerprint'][:12]}, "
            f"{floor_receipt['bytes']} bytes). A non-text artifact enters "
            "canon at its floor receipt — cited by fingerprint on the "
            "citizen it is about, with an observation of what it shows — "
            "never through the reading room. python -m graph receipt "
            "<file> prints the receipt to paste.")


def read_artifact(data, title, origin="", cited_sections=(),
                  carried_texts=()):
    """Build a Reading from an artifact's bytes (markdown, v0).

    Sections carry: id (deterministic — fingerprint prefix : position
    path), level, heading, body, order (sibling index), parent (id or
    None), embeds (table files referenced), spans (the body classified
    per content class), and classes (the distinct classes present).
    Nesting: a section's parent is the nearest preceding shallower
    heading; skipped levels attach to the nearest real ancestor.
    cited_sections: headings cited by procedures' specified_in for THIS
    artifact — their prose spans classify as procedure.
    carried_texts: registered verbatim passages (normalized) — their
    exact bytes classify as verbatim-carried.
    """
    patterns = carried_patterns(carried_texts)
    fingerprint = fingerprint_bytes(data)
    short = fingerprint[:12]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise NotTextArtifact(title, receipt(data)) from None
    sections = []
    # stack of (level, position-path list, child-counter dict)
    stack = []  # entries: {"level": int, "path": [..], "children": int}
    roots = 0
    for level, heading, body in parsers.markdown_outline(text):
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        if stack:
            parent = stack[-1]
            order = parent["children"]
            parent["children"] += 1
            path = parent["path"] + [order]
            parent_id = f"{short}:{'.'.join(map(str, parent['path']))}"
        else:
            order, roots = roots, roots + 1
            path = [order]
            parent_id = None
        section_id = f"{short}:{'.'.join(map(str, path))}"
        prose_class = (PROCEDURE if heading in cited_sections
                       else RULE_PROSE)
        spans = split_spans(body, prose_class=prose_class,
                            patterns=patterns)
        sections.append({
            "id": section_id,
            "parent": parent_id,
            "level": level,
            "order": order,
            "heading": heading,
            "body": body,
            "embeds": CSV_REF.findall(body),
            "spans": spans,
            "classes": sorted({span["class"] for span in spans}),
        })
        stack.append({"level": level, "path": path, "children": 0})
    return Reading(fingerprint=fingerprint, title=title, origin=origin,
                   sections=sections)


# -- archive: small flat files, batch-importable, git-friendly ------------


def serialize(reading):
    """Reading -> {filename: content}. Deterministic: same Reading, same
    bytes — archives diff cleanly and rebuild identically."""
    artifact = {"fingerprint": reading.fingerprint, "title": reading.title,
                "origin": reading.origin, "format": "markdown-v0"}
    lines = [json.dumps(section, ensure_ascii=False, sort_keys=True)
             for section in reading.sections]
    return {
        ARCHIVE_ARTIFACT: json.dumps(artifact, ensure_ascii=False,
                                     indent=2, sort_keys=True) + "\n",
        ARCHIVE_SECTIONS: "\n".join(lines) + ("\n" if lines else ""),
    }


def parse_archive(files):
    """{filename: content} -> Reading (inverse of serialize)."""
    artifact = json.loads(files[ARCHIVE_ARTIFACT])
    sections = [json.loads(line)
                for line in files[ARCHIVE_SECTIONS].splitlines() if line]
    return Reading(fingerprint=artifact["fingerprint"],
                   title=artifact.get("title", ""),
                   origin=artifact.get("origin", ""),
                   sections=sections)


def write_archive(reading, directory):
    """File the archive with the proposal. Returns the paths written."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, content in serialize(reading).items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def read_archive(directory):
    directory = Path(directory)
    return parse_archive({
        ARCHIVE_ARTIFACT: (directory / ARCHIVE_ARTIFACT).read_text(
            encoding="utf-8"),
        ARCHIVE_SECTIONS: (directory / ARCHIVE_SECTIONS).read_text(
            encoding="utf-8"),
    })


# -- the live reading room (driver-facing) --------------------------------


def room_session(config):
    """Driver + session on the workspace database. The room is machine-
    managed workspace, same trust class as scratch — never rulesdata."""
    from neo4j import GraphDatabase  # deferred: only DB access needs it

    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    return driver


def ensure_room(driver):
    with driver.session(database="system") as session:
        session.run(f"CREATE DATABASE {WORKSPACE_DATABASE} IF NOT EXISTS")


def dispose(driver):
    """Wipe the live room. The archive is the record."""
    with driver.session(database=WORKSPACE_DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")


def load_reading(driver, reading):
    """Load one Reading into the room. Rounds coexist: everything is
    keyed by the artifact fingerprint, so batch imports never collide."""
    rows = [{**{k: v for k, v in section.items() if k != "spans"},
             "spans_json": json.dumps(section.get("spans", []),
                                      ensure_ascii=False, sort_keys=True)}
            for section in reading.sections]
    with driver.session(database=WORKSPACE_DATABASE) as session:
        session.run(
            "MERGE (a:Artifact {fingerprint: $fp}) "
            "SET a.title = $title, a.origin = $origin, a.name = $title, "
            "    a.carried_fraction = $carried",
            fp=reading.fingerprint, title=reading.title,
            origin=reading.origin,
            carried=carried_fraction(reading.sections))
        session.run(
            "UNWIND $rows AS row "
            "MERGE (s:Section {id: row.id}) "
            "SET s.heading = row.heading, s.level = row.level, "
            "    s.order = row.order, s.body = row.body, "
            "    s.embeds = row.embeds, s.fingerprint = $fp, "
            "    s.name = row.heading, s.classes = row.classes, "
            "    s.spans_json = row.spans_json "
            "WITH s, row WHERE row.parent IS NULL "
            "MATCH (a:Artifact {fingerprint: $fp}) "
            "MERGE (s)-[:PART_OF]->(a)",
            rows=rows, fp=reading.fingerprint)
        session.run(
            "UNWIND [row IN $rows WHERE row.parent IS NOT NULL] AS row "
            "MATCH (child:Section {id: row.id}), "
            "      (parent:Section {id: row.parent}) "
            "MERGE (child)-[:PART_OF]->(parent)",
            rows=rows)


# -- tables comprehend into claims (fact grain) ---------------------------
#
# A table is presentation, not structure-of-record. Comprehension reads
# one SEMANTICALLY: each non-empty cell yields an ordinary fact-grain
# claim in the domain's own words — subject (key-column header + key
# cell), property (the column's own header), value (the cell) — with a
# rendered sentence that enters the same census as prose claims. Zero
# cell vocabulary reaches any surface. The shape ruling (which column is
# the key) is a one-time judgment recorded per table; the default is the
# first column. The claim's provenance is a LOCATOR, never carried
# bytes: fingerprint-prefix : position path — the section-id scheme one
# level down. Same bytes recompute the same locators (deletion-
# tolerant); changed bytes change the fingerprint, so a locator can
# never silently point into different content. Facts are position-free
# (extraction is header-keyed), so a column inserted mid-table moves
# locators in the new file and moves no facts.

# a markdown table row, and the separator line that underlines a header
MD_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
MD_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def _clean_cell(value):
    return " ".join(str(value or "").split())


def is_row_text(text):
    """Is this text a table ROW rather than prose — every non-empty line
    a markdown table row? A row is presentation, not a sentence: it
    never serves as a receipt (the row-receipt retirement — a cell's
    facts land as structured properties; the census refuses to index a
    row as a carried quote, and the delta gate refuses to author one)."""
    lines = [line for line in str(text).splitlines() if line.strip()]
    return bool(lines) and all(MD_TABLE_ROW.match(line) for line in lines)


def grid_claims(columns, rows, fingerprint="", key_column=None,
                path_prefix=""):
    """Fact-grain claims from one table grid: header names + body rows
    of raw cells. Empty cells and empty markers yield nothing (sparsity
    is free). ``key_column`` is the shape ruling, found by header name
    wherever it sits; absent or unknown, the first column is the key.
    ``path_prefix`` extends the locator's position path for containers
    (a markdown text's table index; one day a workbook's sheet)."""
    columns = [_clean_cell(column) for column in columns]
    if not columns:
        return []
    key_index = columns.index(key_column) if key_column in columns else 0
    short = fingerprint[:12]
    claims = []
    for row_index, row in enumerate(rows):
        cells = [_clean_cell(cell) for cell in row]
        cells += [""] * (len(columns) - len(cells))
        key_cell = cells[key_index]
        if not key_cell or key_cell in parsers.EMPTY_MARKERS:
            continue
        subject = f"{columns[key_index]} {key_cell}".strip()
        for col_index, column in enumerate(columns):
            if col_index == key_index or not column:
                continue
            value = cells[col_index]
            if not value or value in parsers.EMPTY_MARKERS:
                continue
            locator = f"{path_prefix}{row_index}.{col_index}"
            claims.append({
                "subject": subject,
                "property": column,
                "value": value,
                "locator": f"{short}:{locator}" if short else locator,
                "sentence": f"The {column} of {subject} is {value}.",
            })
    return claims


def csv_claims(data, key_column=None):
    """Fact-grain claims from a CSV table's bytes. The table is its own
    content-addressed artifact — the locator's fingerprint is the
    sha256 of THESE bytes."""
    rows = list(_csv.reader(_io.StringIO(data.decode("utf-8"))))
    if not rows:
        return []
    return grid_claims(rows[0], rows[1:],
                       fingerprint=fingerprint_bytes(data),
                       key_column=key_column)


def _markdown_cells(line):
    """One markdown table row as cells — escaped delimiters unescaped,
    so a cell carrying the delimiter never splits into phantom cells."""
    inner = line.strip().strip("|")
    return [piece.replace("\\|", "|").strip()
            for piece in re.split(r"(?<!\\)\|", inner)]


def markdown_table_claims(text, key_columns=None):
    """Fact-grain claims from every HEADED markdown table in a text (a
    header row underlined by a separator line). A headerless table
    names no properties, so it yields no claims — it stays structure.
    ``key_columns``, when given, maps a table's key-column header to
    itself as a shape ruling: any table whose header row contains one
    of these names uses it as the key."""
    lines = text.splitlines()
    fingerprint = fingerprint_bytes(text.encode("utf-8"))
    claims = []
    table_index = 0
    index = 0
    while index < len(lines):
        if not (MD_TABLE_ROW.match(lines[index])
                and index + 1 < len(lines)
                and MD_TABLE_ROW.match(lines[index + 1])
                and MD_TABLE_SEPARATOR.match(lines[index + 1])):
            index += 1
            continue
        columns = _markdown_cells(lines[index])
        body = []
        index += 2
        while index < len(lines) and MD_TABLE_ROW.match(lines[index]) \
                and not MD_TABLE_SEPARATOR.match(lines[index]):
            body.append(_markdown_cells(lines[index]))
            index += 1
        key_column = next((name for name in (key_columns or ())
                           if name in columns), None)
        claims += grid_claims(columns, body, fingerprint=fingerprint,
                              key_column=key_column,
                              path_prefix=f"{table_index}.")
        table_index += 1
    return claims


def reading_table_claims(reading, read_bytes, key_columns=None):
    """A sealed reading's table spans comprehended into fact-grain
    claims, in document order. ``read_bytes(relpath)`` supplies each
    embedded table's bytes; ``key_columns`` maps relpath -> the ruled
    key column. Every claim rides with its section heading and table
    path. Unreadable tables are collated, never raised — returns
    (claims, unreadable_relpaths)."""
    claims, unreadable = [], []
    for section in reading.sections:
        for span in section.get("spans", []):
            if span.get("class") != TABLE:
                continue
            relpath = span["table"]
            try:
                data = read_bytes(relpath)
            except OSError:
                unreadable.append(relpath)
                continue
            for row in csv_claims(data, key_column=(key_columns
                                                    or {}).get(relpath)):
                claims.append({**row, "section": section["heading"],
                               "table": relpath})
    return claims, unreadable


FINDINGS_FILE = "findings.jsonl"


def write_findings_archive(archive_dir, rows):
    """Findings ride the artifact's archive (findings-as-rows) — one JSON line per
    row, deterministic order, so a disposed room recalls its finding
    history along with its structure."""
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True)
             for row in sorted(rows, key=lambda r: r["id"])]
    (archive_dir / FINDINGS_FILE).write_text(
        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_findings_archive(archive_dir):
    path = Path(archive_dir) / FINDINGS_FILE
    if not path.exists():
        return []
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()]


def load_findings(driver, fingerprint, rows):
    """Land finding rows in the room beside the sections they judge.

    Identity is content-derived, so a re-judge MERGEs onto the same
    rows: statuses agents have worked (escalated, ruled) survive a
    re-run; findings that no longer red are removed — the room always
    shows the latest judgment's open set plus preserved work."""
    with driver.session(database=WORKSPACE_DATABASE) as session:
        session.run(
            "MATCH (f:Finding {fingerprint: $fp}) "
            "WHERE NOT f.id IN [row IN $rows | row.id] "
            "DETACH DELETE f",
            fp=fingerprint, rows=rows)
        session.run(
            "UNWIND $rows AS row "
            "MERGE (f:Finding {id: row.id}) "
            "ON CREATE SET f.status = row.status "
            "SET f.tier = row.tier, f.kind = row.kind, "
            "    f.message = row.message, f.original = row.original, "
            "    f.regenerated = row.regenerated, "
            "    f.section_heading = row.section_heading, "
            "    f.name = row.kind + ': ' + left(row.message, 60), "
            "    f.fingerprint = $fp "
            "WITH f, row WHERE row.section_id <> '' "
            "MATCH (s:Section {id: row.section_id}) "
            "MERGE (f)-[:JUDGED_FROM]->(s)",
            rows=rows, fp=fingerprint)


def room_report(driver):
    """The plan-gate view's raw numbers: artifacts in the room, each
    one's section count, depth, content-class census, and the
    carried-fraction honesty metric."""
    with driver.session(database=WORKSPACE_DATABASE) as session:
        return [dict(record) for record in session.run(
            "MATCH (a:Artifact) "
            "OPTIONAL MATCH (s:Section {fingerprint: a.fingerprint}) "
            "WITH a, count(s) AS sections, max(s.level) AS deepest, "
            "     [x IN collect(s.classes) | x] AS class_lists "
            "RETURN a.title AS title, a.fingerprint AS fingerprint, "
            "       sections, deepest, "
            "       a.carried_fraction AS carried_fraction, "
            "       reduce(acc = [], l IN class_lists | acc + l) "
            "         AS class_census "
            "ORDER BY title")]
