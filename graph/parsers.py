"""Special-case parsers for cells/files that aren't flat name lists.

Parsers are pure functions over raw CSV content. They never raise on messy
input: they return what they could parse plus the text they could not, and the
caller (extract.py) turns unparsed remainders into validation findings.
Only ENGINE-GENERIC machinery lives here (the storybook test: a corpus
that never heard of any one project still needs it); corpus-specific grammars
live in graph/grammars/ and are resolved through its registry (the grammar registry).
"""

import re

# Cell values that mean "empty" throughout the data files.
EMPTY_MARKERS = {"", "—", "-", "N/A"}

# Tokens a bool cell recognizes (case-insensitive). Empty markers read as False.
# Check/ballot marks are included because tables in the wild use them (e.g.
# a roster.csv's Has-* columns use ✓).
BOOL_TRUE = {"Y", "YES", "TRUE", "1", "✓", "✔"}
BOOL_FALSE = {"N", "NO", "FALSE", "0", "✗", "✘"}


def split_multi(cell):
    """Split a multi-valued cell on commas. Returns [] for empty markers.

    Caveat: values containing commas would be split apart; none exist today
    (names use parentheses, e.g. "Cannot Roar (Silenced)"), and the
    dangling-reference check is the safety net if one ever appears.
    """
    if cell is None:
        return []
    cell = cell.strip()
    if cell in EMPTY_MARKERS:
        return []
    return [part.strip() for part in cell.split(",") if part.strip()]


def parse_int(cell):
    """Parse an integer cell like '+5', '-4', '0'. Returns (value, ok).

    Empty markers return (None, True). Unparseable text returns (None, False).
    """
    if cell is None:
        return None, True
    cell = cell.strip()
    if cell in EMPTY_MARKERS:
        return None, True
    try:
        return int(cell.lstrip("+")), True
    except ValueError:
        return None, False


def parse_float(cell):
    """Parse a decimal cell like '2.0', '0.5', '-.75'. Returns (value, ok).

    Empty markers return (None, True). Unparseable text returns (None, False).
    """
    if cell is None:
        return None, True
    cell = cell.strip()
    if cell in EMPTY_MARKERS:
        return None, True
    try:
        return float(cell.lstrip("+")), True
    except ValueError:
        return None, False


def parse_bool(cell):
    """Parse a boolean cell like 'Y', 'N', '✓', '' (empty). Returns (value, ok).

    Empty markers and explicit false tokens return (False, True); truthy
    tokens return (True, True); anything else returns (None, False). The
    column is a total boolean: an empty cell is False, not unknown.
    """
    if cell is None:
        return False, True
    cell = cell.strip()
    if cell in EMPTY_MARKERS:
        return False, True
    token = cell.upper()
    if token in BOOL_TRUE:
        return True, True
    if token in BOOL_FALSE:
        return False, True
    return None, False


def name_variants(name):
    """Deterministic surface variants of a citizen name: identity plus
    plural morphology on the last word (s/es and ies<->y). Used to build
    the term index — "Pages" resolves to Page, "Properties" to
    Property — so authors never write around the matcher.
    """
    words = name.split()
    if not words:
        return {name}
    last = words[-1]

    def form(replacement):
        return " ".join(words[:-1] + [replacement])

    variants = {name}
    if last.endswith("ies") and len(last) > 3:
        variants.add(form(last[:-3] + "y"))
    elif last.endswith("y") and len(last) > 1:
        variants.add(form(last[:-1] + "ies"))
    if last.endswith("s") and len(last) > 1:
        variants.add(form(last[:-1]))
    else:
        variants.add(form(last + "s"))
        variants.add(form(last + "es"))
    return variants


def capitalized_runs(text):
    """Candidate terms in prose: capitalized word-runs, with the
    sentence/line-leading word discounted (it capitalizes for grammar, not
    terminology). Runs never span line breaks; apostrophe-words scan whole
    ("Cannot Climb Mountains", not a "Climb Mountains" fragment). Yields term strings.
    """
    word = r"[A-Z][a-z]{2,}(?:'[a-z]+)?"
    for match in re.finditer(word + r"(?:[ \t]+" + word + r")*", text):
        words = match.group().split()
        raw_prefix = text[:match.start()]
        prefix = raw_prefix.rstrip()
        if (not prefix or prefix[-1] in ".!?:\"'()*#-"
                or re.search(r"\n[ \t]*$", raw_prefix)):
            words = words[1:]
        if words:
            yield " ".join(words)


def split_clauses(cell):
    """Split a prose cell into sentence-ish clauses on '. ' boundaries."""
    if cell is None:
        return []
    cell = cell.strip()
    if cell in EMPTY_MARKERS:
        return []
    return [c.strip() for c in re.split(r"\.\s+|\.$", cell) if c.strip()]


# Project-specific grammars (the corpus's own parse strategies)
# moved to the project's grammar module (the grammar registry) — the engine hosts them
# through the grammar registry; it no longer contains them.


def markdown_outline(text):
    """Split markdown into heading-anchored sections, levels preserved.

    Returns a list of (level, heading, body) in document order — level is
    the heading depth (1 for '#'). Text before the first heading is
    ignored. The comprehension reader consumes this full form; the canon
    DocSection path uses the level-blind markdown_sections wrapper.
    """
    sections = []
    level, heading = None, None
    body_lines = []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if match:
            if heading is not None:
                sections.append((level, heading, "\n".join(body_lines)))
            level, heading = len(match.group(1)), match.group(2)
            body_lines = []
        elif heading is not None:
            body_lines.append(line)
    if heading is not None:
        sections.append((level, heading, "\n".join(body_lines)))
    return sections


def markdown_sections(text):
    """Level-blind view of markdown_outline: (heading, body) pairs —
    per-heading granularity is the canon DocSection contract."""
    return [(heading, body) for _, heading, body in markdown_outline(text)]


def mention_matches(body, names):
    """Which of `names` appear verbatim in `body`?

    Deterministic exact matching with letter boundaries (so 'Dead' does not
    match 'Deadly'). Case-sensitive — the system's capitalized terminology is
    load-bearing (CLAUDE.md).
    """
    found = []
    for name in names:
        pattern = r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])"
        if re.search(pattern, body):
            found.append(name)
    return found
