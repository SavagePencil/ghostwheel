"""Ontology-declared derivation answer keys.

Each transcribed program's derived facts must equal its approved table —
declared in the ontology's `answer_keys:` section, checked by ONE
generic engine pass inside validate. A new procedure gets its fidelity
net by adding a declaration; nobody hand-writes a test.

Three kinds:

- derives: transitions — the program's ladder walk (walk_transitions
  over the corpus's Exclusive+Stateful subjects, discovered from the
  facets — no subject is declared on the key) must equal EXACTLY the
  approved table's (from_column, to_column) rows, optionally filtered by
  `where:` {column: value}. Missing and surplus transitions are each
  named; a program that branches on a tracked subject yet derives nothing
  is a loud finding, never a silent pass.
- derives: thresholds — the drift tripwire (absorbs the earlier drift-tripwire work's
  hand-written check): for each table row, the program's branch case
  for that row's key must contain the literal condition_pattern with
  the row's value substituted ("Heat > {value}"). Editing the
  table without re-approving the program fails validation, by name.
- derives: recompute — worked examples as checks: each fixture row is
  one worked example (its givens and its asserted numbers); every
  asserted number is recomputed from the approved tables and compared.
  A component sums a given column, a single lookup (optionally variant
  by a discriminator column), and/or a pairs cell ("Key Row=Claim;
  ...") where every claimed contribution is verified against its
  declared lookup table (with an optional instance→template fallback
  and an optional property gate). The result formula must also appear
  verbatim in the program body, so the fixture, the tables, and the
  program cannot drift apart silently.

Declaration keys: procedure, derives, table,
from_column/to_column/where (transitions), key_column/value_column/
condition_pattern (thresholds), example_column/components/result
(recompute).
"""

import csv
import io
import json
import re
from pathlib import Path

from . import procedures
from .ontology import (ERROR, WARNING, Category, Finding, Reader,
                       concept_bindings, node_reader, source_files_of)
from .parsers import EMPTY_MARKERS, name_variants

KNOWN_KEY_FIELDS = {"procedure", "derives", "table",
                    "from_column", "to_column", "where",
                    "key_column", "value_column", "condition_pattern",
                    "skip_values", "example_column", "components",
                    "result"}
KNOWN_KINDS = {"transitions", "thresholds", "recompute"}
# The subject facets that make a label a transition ladder: a value it
# holds exactly one of (Exclusive) whose changes are rule-governed
# (Stateful). Both present -> the label's surfaces are candidate subjects.
SUBJECT_FACETS = frozenset({"Exclusive", "Stateful"})


def subject_surfaces(ontology):
    """Surface forms of every Exclusive+Stateful subject label — the
    candidate subjects a transition walk resolves branch-on text against.
    Candidates come from the declarations (a label is a subject when its
    concept: bindings carry BOTH facets), expanded to the label name's
    plural/declared surface forms through name_variants — the
    ontology-derivable slice of the term index (the graph-backed index is
    not built during validate). No subject is named in the answer key; the
    facets declare the ladder."""
    surfaces = set()
    for label, spec in ontology.nodes.items():
        if not isinstance(spec, dict):
            continue
        if SUBJECT_FACETS <= set(concept_bindings(spec)):
            forms = [str(label).strip()] + [
                str(f).strip() for f in (spec.get("surface_forms") or [])]
            for form in forms:
                if form:
                    surfaces |= name_variants(form)
    return sorted(surfaces)


def _load_procedures(ontology):
    """{procedure name: spec} from every procedure-yaml source."""
    specs = {}
    for spec in ontology.nodes.values():
        if not isinstance(spec, dict) or \
                node_reader(spec) != Reader.PROCEDURE_YAML:
            continue
        for relpath in source_files_of(spec):
            try:
                text = (ontology.base_dir / relpath).read_text(
                    encoding="utf-8")
            except OSError:
                continue  # already an ontology finding
            proc_spec, errors = procedures.parse_procedure(text)
            if proc_spec is not None and not errors:
                specs[str(proc_spec["procedure"]).strip()] = proc_spec
    return specs


def _table_rows(base_dir, relpath):
    text = (Path(base_dir) / relpath).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def _case_bodies(proc_spec):
    """{case value: flattened body text} across every branch step."""
    bodies = {}
    for step in proc_spec.get("steps") or []:
        if procedures.BRANCH_KEY in step:
            for case, body in (step.get("cases") or {}).items():
                bodies[str(case)] = json.dumps(body, ensure_ascii=False)
    return bodies


def check(ontology):
    """Every declared answer key, verified. Findings collate — the
    approver never fixes one to discover the next."""
    findings = []
    if not ontology.answer_keys:
        return findings
    fname = str(ontology.path)
    specs = _load_procedures(ontology)
    surfaces = subject_surfaces(ontology)
    for index, key in enumerate(ontology.answer_keys):
        where = f"answer_keys[{index}]"
        if not isinstance(key, dict):
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, fname, where,
                "an answer key must be a mapping"))
            continue
        unknown = sorted(set(key) - KNOWN_KEY_FIELDS)
        if unknown:
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, fname, where,
                f"unknown answer-key field(s) {unknown}"))
        kind = key.get("derives")
        proc_name = (key.get("procedure") or "").strip()
        if kind not in KNOWN_KINDS or not proc_name or not key.get("table"):
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, fname, where,
                "an answer key needs procedure, derives "
                f"(one of {sorted(KNOWN_KINDS)}), and table"))
            continue
        spec = specs.get(proc_name)
        if spec is None:
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, fname, where,
                f"no transcribed procedure named '{proc_name}' — the "
                "declaration and the procedure files disagree"))
            continue
        try:
            rows = _table_rows(ontology.base_dir, key["table"])
        except OSError as exc:
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, fname, where,
                f"approved table {key['table']} is unreadable ({exc})"))
            continue
        if kind == "transitions":
            findings.extend(_check_transitions(key, proc_name, spec, rows,
                                               where, surfaces))
        elif kind == "thresholds":
            findings.extend(_check_thresholds(key, proc_name, spec, rows,
                                              where))
        else:
            findings.extend(_check_recompute(key, proc_name, spec, rows,
                                             where, ontology.base_dir))
    return findings


def _check_transitions(key, proc_name, spec, rows, where, surfaces):
    findings = []
    from_col, to_col = key.get("from_column"), key.get("to_column")
    if not from_col or not to_col:
        return [Finding(ERROR, Category.ANSWER_KEY, key["table"], where,
                        "a transitions key needs from_column and to_column")]
    conditions = key.get("where") or {}
    approved = {(row.get(from_col, "").strip(), row.get(to_col, "").strip())
                for row in rows
                if all((row.get(col) or "").strip() == value
                       for col, value in conditions.items())}
    derived = procedures.walk_transitions(spec, surfaces)
    # Silent-miss tripwire: the walker's candidate subjects come
    # from the Exclusive+Stateful facets, resolved through the term index.
    # If the program branches on a tracked subject yet derives NOTHING, the
    # old check would pass in silence (an empty derived set matches an empty
    # or mis-scoped approved set) — attest that loudly instead.
    if procedures.branches_on_subject(spec, surfaces) and not derived:
        return [Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"'{proc_name}' branches on a tracked subject but derives no "
            "transitions at all — the approved table cannot be checked "
            "against a program that attests nothing; verify the program's "
            "become-steps resolve to value citizens")]
    for pair in sorted(approved - derived):
        findings.append(Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"'{proc_name}' no longer derives the approved transition "
            f"{pair[0]} → {pair[1]} — the program and the approved table "
            "disagree; re-verify the program, then re-approve the table"))
    for pair in sorted(derived - approved):
        findings.append(Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"'{proc_name}' derives {pair[0]} → {pair[1]} but the "
            "approved table has no such row — the program grew a "
            "transition nobody approved"))
    return findings


def _check_thresholds(key, proc_name, spec, rows, where):
    findings = []
    key_col, value_col = key.get("key_column"), key.get("value_column")
    pattern = key.get("condition_pattern")
    if not key_col or not value_col or not pattern:
        return [Finding(ERROR, Category.ANSWER_KEY, key["table"], where,
                        "a thresholds key needs key_column, value_column, "
                        "and condition_pattern")]
    bodies = _case_bodies(spec)
    # skip_values: cell values the key declares to mean "no threshold
    # exists" beyond the global empty markers (e.g. an infinity glyph).
    skip = set(key.get("skip_values") or ())
    for row in rows:
        case = (row.get(key_col) or "").strip()
        value = (row.get(value_col) or "").strip()
        if not case or value in EMPTY_MARKERS or value in skip:
            continue  # an empty-marker value means "no threshold here"
        expected = pattern.replace("{value}", value)
        body = bodies.get(case)
        if body is None:
            findings.append(Finding(
                WARNING, Category.ANSWER_KEY, key["table"], where,
                f"'{proc_name}' has no branch case for '{case}' — the "
                "approved table names it; the program does not"))
        elif expected not in body:
            findings.append(Finding(
                WARNING, Category.ANSWER_KEY, key["table"], where,
                f"'{proc_name}' case '{case}' does not carry the approved "
                f"condition \"{expected}\" — the table changed without "
                "re-approving the program (or vice versa)"))
    return findings


# --- derives: recompute — worked examples as checks ---------------------

_NUMBER_RE = re.compile(r"^[+−-]?\d*\.?\d+$")
_DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
_FORMULA_CHARS = re.compile(r"^[\d\s+*/().×−-]+$")


def _number(text):
    """'+2' → 2.0, '-.75' → -0.75. Raises ValueError on anything else."""
    cleaned = str(text).strip().replace("−", "-").lstrip("+")
    if not _NUMBER_RE.match(cleaned or "x"):
        raise ValueError(f"'{text}' is not a number")
    return float(cleaned)


def _parse_cell(raw, mode):
    """A table cell as a number, per the declared parse mode:
    number ('+2'), multiplier ('+2x' → 2, '-.75x' → -0.75), or
    dice_flat ('3-8 (1d6+2)' → 2, '1-6 (1d6)' → 0: the flat term of
    the dice expression, the only part a recompute can hold still)."""
    text = str(raw).strip()
    if mode == "multiplier":
        return _number(text.rstrip("xX"))
    if mode == "dice_flat":
        inner = text
        if "(" in text and text.endswith(")"):
            inner = text[text.index("(") + 1:-1].strip()
        match = _DICE_RE.match(inner.replace(" ", ""))
        if not match:
            raise ValueError(f"'{raw}' is not a dice expression")
        return float(match.group(3) or 0)
    return _number(text)


def _resolve_lookup(lookup, fixture_row):
    """The concrete {table, key_column, value_column, parse, ...} for
    this fixture row — either the lookup itself or the variant chosen
    by the row's discriminator column (select_by/variants)."""
    if "variants" in lookup:
        discriminator = str(
            fixture_row.get(lookup.get("select_by") or "", "")).strip()
        chosen = (lookup.get("variants") or {}).get(discriminator)
        if chosen is None:
            raise ValueError(
                f"no variant for '{discriminator}' "
                f"(declared: {sorted(lookup.get('variants') or {})})")
        merged = dict(lookup)
        merged.pop("variants", None)
        merged.pop("select_by", None)
        merged.update(chosen)
        return merged
    return lookup


def _table_cell(base_dir, cache, lookup, key):
    """The (found, raw cell) for `key` in the lookup's table."""
    relpath = lookup["table"]
    if relpath not in cache:
        cache[relpath] = _table_rows(base_dir, relpath)
    for row in cache[relpath]:
        if (row.get(lookup["key_column"]) or "").strip() == key:
            return True, (row.get(lookup["value_column"]) or "").strip()
    return False, ""


def _pairs(cell):
    """'Flair 16=+2; Ribbon Golden=+1x' → [(prefix, key, claim)];
    a pair without '=' (a suppressed assertion) yields claim None."""
    parsed = []
    for chunk in str(cell or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, claim = chunk.partition("=")
        prefix, _, key = name.strip().partition(" ")
        parsed.append((prefix.strip(), key.strip(),
                       claim.strip() if "=" in chunk else None))
    return parsed


def _check_recompute(key, proc_name, spec, rows, where, base_dir):
    findings = []
    components = key.get("components")
    result = key.get("result") or {}
    if not isinstance(components, dict) or not components or \
            not result.get("formula") or not result.get("expected_column"):
        return [Finding(
            ERROR, Category.ANSWER_KEY, key["table"], where,
            "a recompute key needs components (a mapping) and result "
            "{formula, expected_column}")]
    formula = str(result["formula"])
    flat_steps = json.dumps(spec.get("steps") or [], ensure_ascii=False)
    if formula.replace("*", "×") not in flat_steps and \
            formula not in flat_steps:
        findings.append(Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"the declared formula \"{formula}\" no longer appears in "
            f"'{proc_name}' — the program and the examples' arithmetic "
            "have drifted apart; re-verify both"))
    cache = {}
    example_col = key.get("example_column") or "Example"
    for row in rows:
        example = (row.get(example_col) or "").strip() or "unnamed example"
        values = {}
        broken = False
        for name, comp in components.items():
            try:
                value, comp_findings = _recompute_component(
                    comp, row, example, key, where, base_dir, cache)
            except ValueError as exc:
                findings.append(Finding(
                    ERROR, Category.ANSWER_KEY, key["table"], where,
                    f"{example}: component '{name}' cannot be recomputed "
                    f"({exc})"))
                broken = True
                continue
            findings.extend(comp_findings)
            expected_col = comp.get("expected_column")
            if expected_col:
                try:
                    asserted = _number(row.get(expected_col, ""))
                except ValueError:
                    findings.append(Finding(
                        ERROR, Category.ANSWER_KEY, key["table"], where,
                        f"{example}: '{expected_col}' does not hold a "
                        "number"))
                    broken = True
                    continue
                if abs(asserted - value) > 1e-9:
                    findings.append(Finding(
                        WARNING, Category.ANSWER_KEY, key["table"], where,
                        f"{example}: recomputed {name} = {value:g} from "
                        f"the approved tables, but the example asserts "
                        f"{asserted:g} — the example and the tables "
                        "disagree; re-verify, then re-approve whichever "
                        "moved"))
            values[name] = value
        if broken:
            continue
        expression = formula
        for name in sorted(values, key=len, reverse=True):
            expression = expression.replace(name, repr(values[name]))
        if not _FORMULA_CHARS.match(expression.replace("'", "")):
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, key["table"], where,
                f"result formula \"{formula}\" names quantities beyond "
                f"the declared components {sorted(values)}"))
            continue
        total = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        if "floor" in result:
            total = max(float(result["floor"]), total)
        try:
            asserted_total = _number(row.get(result["expected_column"], ""))
        except ValueError:
            findings.append(Finding(
                ERROR, Category.ANSWER_KEY, key["table"], where,
                f"{example}: '{result['expected_column']}' does not hold "
                "a number"))
            continue
        if abs(asserted_total - total) > 1e-9:
            findings.append(Finding(
                WARNING, Category.ANSWER_KEY, key["table"], where,
                f"{example}: the formula recomputes to {total:g}, but the "
                f"example asserts {asserted_total:g} — the example and "
                "the approved tables disagree; re-verify, then re-approve "
                "whichever moved"))
    return findings


def _recompute_component(comp, row, example, key, where, base_dir, cache):
    """(value, findings) for one component of one fixture row."""
    findings = []
    value = 0.0
    given_col = comp.get("given_column")
    if given_col:
        value += _number(row.get(given_col, ""))
    lookup = comp.get("lookup")
    if lookup:
        concrete = _resolve_lookup(lookup, row)
        subject = (row.get(concrete.get("key_from") or "") or "").strip()
        found, cell = _table_cell(base_dir, cache, concrete, subject)
        if not found:
            raise ValueError(
                f"'{subject}' has no row in {concrete['table']}")
        value += _parse_cell(cell, concrete.get("parse") or "number")
    for prefix, subject, claim in _pairs(row.get(comp.get("pairs_column")
                                                 or "", "")):
        pair_lookup = (comp.get("pair_lookups") or {}).get(prefix)
        if pair_lookup is None:
            raise ValueError(
                f"contribution '{prefix} {subject}' has no declared "
                f"lookup (declared: {sorted(comp.get('pair_lookups') or {})})")
        concrete = _resolve_lookup(pair_lookup, row)
        found, cell = _table_cell(base_dir, cache, concrete, subject)
        fallback = concrete.get("template_fallback")
        if (not found or not cell) and fallback:
            # a name-only instance inherits its template's value
            found_template, template = _table_cell(
                base_dir, cache, fallback, subject)
            if found_template and template:
                found, cell = _table_cell(base_dir, cache, concrete,
                                          template)
        if not found or not cell:
            raise ValueError(
                f"'{subject}' has no value in {concrete['table']} "
                "(nor via its template)")
        parse_mode = concrete.get("parse") or "number"
        canon = _parse_cell(cell, parse_mode)
        if claim is not None and \
                abs(canon - _parse_cell(claim, parse_mode)) > 1e-9:
            findings.append(Finding(
                WARNING, Category.ANSWER_KEY, key["table"], where,
                f"{example}: claims {prefix} {subject} contributes "
                f"{claim}, but {concrete['table']} now says {canon:g} — "
                "the example and the table disagree"))
        value += canon
        findings.extend(_check_gate(concrete, row, example, prefix,
                                    subject, key, where, base_dir, cache,
                                    applied=True))
    for prefix, subject, _ in _pairs(row.get(comp.get("suppressed_column")
                                             or "", "")):
        pair_lookup = (comp.get("pair_lookups") or {}).get(prefix)
        if pair_lookup is None:
            raise ValueError(
                f"suppressed '{prefix} {subject}' has no declared lookup")
        concrete = _resolve_lookup(pair_lookup, row)
        findings.extend(_check_gate(concrete, row, example, prefix,
                                    subject, key, where, base_dir, cache,
                                    applied=False))
    if "floor" in comp:
        value = max(float(comp["floor"]), value)
    return value, findings


def _check_gate(concrete, row, example, prefix, subject, key, where,
                base_dir, cache, applied):
    """A gated contribution is only lawful when the gate property is
    present (applied) or absent (suppressed) on the gate lookup's row."""
    gate = concrete.get("gate")
    if not gate:
        return []
    gate_lookup = _resolve_lookup(gate.get("lookup") or {}, row)
    bearer = (row.get(gate_lookup.get("key_from") or "") or "").strip()
    found, cell = _table_cell(base_dir, cache, gate_lookup, bearer)
    if not found:
        raise ValueError(f"'{bearer}' has no row in {gate_lookup['table']}")
    held = {p.strip() for p in cell.split(",") if p.strip()}
    prop = gate.get("property") or ""
    if applied and prop not in held:
        return [Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"{example}: applies {prefix} {subject}, but '{bearer}' no "
            f"longer bears {prop} in {gate_lookup['table']} — the gate "
            "that authorized this contribution is gone")]
    if not applied and prop in held:
        return [Finding(
            WARNING, Category.ANSWER_KEY, key["table"], where,
            f"{example}: says {prefix} {subject} is NOT applied, but "
            f"'{bearer}' now bears {prop} in {gate_lookup['table']} — "
            "the example's suppression no longer matches the data")]
    return []
