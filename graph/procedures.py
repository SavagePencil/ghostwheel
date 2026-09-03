"""Approved procedure programs: parse, lift, walk, render.

Procedures are rules-as-programs (data/procedures/*.yaml), approved by the
approver per the two-stage rule. Purpose is COMPREHENSION, not execution: the
lift turns a program into (:Procedure)-[:FIRST_STEP]->(:Step) chains an agent
can traverse ("how does the Awakening work for me?"); walk_transitions derives
the State-transition facts a program implies (checked against the approved
transition table); render_markdown generates rulebook-style prose back out of
the structure (the generation experiment).

Every procedure has a COMPLETENESS — how much of it the graph holds
(owner ruling; the two-axis test decides: does an agent need the inner
workings, and do we own the source?):
  transcribed  full lift; the signature (reads/mutates/calls/outcomes) is
               DERIVED from the body and closed by construction
  attested     asserted signature + prose body via specified_in; sections
               carry open/closed closure markers; the approved_hash
               tripwire guards drift
  cited        name + link only; everything open

Program vocabulary (grows by owner approval, like everything):
  procedure, completeness, specified_in, inputs, outputs, precondition,
  possible_outcomes, steps
  step forms: {branch on, cases}, {when, then[, otherwise]}, {otherwise},
              and single-key actions: spend/reduce/set/become/note/roll/
              call/stop/continue
  stop takes prose, or {outcome: Name, note: prose} to bind an outcome
              inline; possible_outcomes `ends:` text-matches stop prose.
              Bijection enforced: every stop claimed by exactly one outcome,
              every outcome claims at least one stop.
  inputs entries: description string (required), or
              {description, required: bool, when_absent: prose}
  attested outcome entries: guarantee, description, and the asserted
              effects assigns: [values] (each derives its own
              ASSIGNS_<LABEL> edge from the resolved target — the same
              transform the transcribed become-step uses) and
              mutates: [values].
  Authored facts only: inputs, outcome names + guarantees, completeness.
  Reads, consults, mutates, and outcome effects are DERIVED for transcribed
  procedures — never authored (they could drift from the body).

This module is pure (no graph, no I/O beyond the caller's text): the
extractor materializes the lift into nodes/edges and resolves references.
"""

import enum
from dataclasses import dataclass, field

import yaml

from . import parsers


class Completeness(enum.StrEnum):
    """How much of the procedure the graph holds (cited < attested <
    transcribed). Coverage, not accuracy — accuracy is guarded by the
    approved_hash tripwire and the derivation answer-keys."""
    TRANSCRIBED = "transcribed"
    ATTESTED = "attested"
    CITED = "cited"


class Guarantee(enum.StrEnum):
    """Failure semantics per outcome (plain English — owner ruling)."""
    READ_ONLY = "read-only"
    CANNOT_FAIL = "cannot-fail"
    FAILS_CLEAN = "fails-clean"
    FAILS_WITH_SIDE_EFFECTS = "fails-with-side-effects"


GUARANTEES = frozenset(g.value for g in Guarantee)
COMPLETENESS_LEVELS = frozenset(c.value for c in Completeness)

COMMON_KEYS = {"procedure", "completeness", "specified_in"}
TOP_KEYS_BY_COMPLETENESS = {
    Completeness.TRANSCRIBED: COMMON_KEYS | {"inputs", "outputs", "precondition",
                                    "possible_outcomes", "steps",
                                    "locals"},
    Completeness.ATTESTED: COMMON_KEYS | {"inputs", "outputs", "precondition",
                                "possible_outcomes", "description",
                                "reads", "consults", "mutates", "locals"},
    Completeness.CITED: COMMON_KEYS | {"description"},
}
MUTATION_VERBS = ("spend", "reduce", "set", "become")
# compute: a calculation over observed values — projects READS, never
# MUTATES (a sum step that names State or Property reads them, it does
# not change them).
ACTION_VERBS = MUTATION_VERBS + ("compute", "note", "roll", "call", "stop",
                                 "continue")
BRANCH_KEY = "branch on"
# from_text: the RECEIPT — a verbatim quote of the source sentence an
# authored fact was extracted from. Claim sits beside evidence at review;
# the extractor verifies the quote actually appears in the source.
KNOWN_INPUT_KEYS = {"description", "required", "when_absent", "from_text"}
KNOWN_OUTCOME_KEYS = {"ends", "guarantee", "from_text"}
# assigns: a list of value citizens the outcome assigns (each derives its
# own ASSIGNS_<LABEL> edge from the resolved target's label, mirroring the
# transcribed become-step); mutates: a list it changes in place.
KNOWN_ATTESTED_OUTCOME_KEYS = {"guarantee", "assigns", "mutates",
                               "description", "from_text"}
KNOWN_SECTION_KEYS = {"closed", "known"}
# approved_in: an archive pointer beside the approved_hash tripwire —
# the hash DETECTS that the approved source moved; a commit or PR link
# RETRIEVES the exact approved text forever. Stamped post-ship (the
# text is typically amended in the same branch, so the link only exists
# once the ship lands), like Judgment-row PR provenance.
KNOWN_SPECIFIED_IN_KEYS = {"artifact", "section", "approved_hash",
                           "approved_in"}

# Edge vocabulary of the lift (referenced by extractor and tests).
FIRST_STEP, NEXT, CASE, THEN, OTHERWISE = (
    "FIRST_STEP", "NEXT", "CASE", "THEN", "OTHERWISE")


def effective_completeness(spec):
    """The spec's completeness: explicit completeness: wins; steps: implies
    transcribed."""
    if spec.get("completeness") in COMPLETENESS_LEVELS:
        return Completeness(spec["completeness"])
    return Completeness.TRANSCRIBED if spec.get("steps") else None


def specified_in_of(spec):
    """Normalize specified_in to (artifact | None, sections, approved_hash),
    where sections is a LIST of targets (empty when uncited).

    With artifact: a FILE-SPAN citation — each section is a heading inside
    that file, resolved by reading the bytes (canon holds no section
    citizens; canon-side references are artifact + span). A chapter-spanning
    procedure may cite SEVERAL sections (the multi-section citation rule); its receipts check against
    all of them and its approved_hash covers their bodies joined in the
    listed order. Without artifact: the single target resolves to a citizen
    by name (a procedure may cite the citizen it operates on)."""
    raw = spec.get("specified_in")
    if isinstance(raw, dict):
        section = raw.get("section")
        if isinstance(section, list):
            sections = [str(s).strip() for s in section if str(s).strip()]
        else:
            sections = [str(section).strip()] \
                if str(section or "").strip() else []
        return ((raw.get("artifact") or "").strip() or None,
                sections,
                raw.get("approved_hash"))
    target = (raw or "").strip()
    return None, ([target] if target else []), None


def stop_fields(value):
    """A stop's (note prose, inline outcome name). Accepts both forms."""
    if isinstance(value, dict):
        return (value.get("note") or "").strip(), \
               (value.get("outcome") or "").strip()
    return (value or "").strip(), ""


@dataclass
class LiftedStep:
    name: str            # deterministic: "<procedure> §<path>"
    kind: str            # branch | case | when | one of ACTION_VERBS
    text: str
    condition: str = ""  # when-steps only
    outcome: str = ""    # inline-tagged stops only


@dataclass
class Terminal:
    """One stop, with the action steps on the path from start to it."""
    step_name: str
    stop_text: str
    inline_outcome: str
    trail: list          # step names of action verbs on the path (incl. stop)


@dataclass
class Lift:
    steps: list = field(default_factory=list)      # LiftedStep, creation order
    edges: list = field(default_factory=list)      # (type, from_name, to_name)
    cases: list = field(default_factory=list)      # (case_step_name, case_value)
    terminals: list = field(default_factory=list)  # Terminal per stop
    first_step: str = ""


def parse_procedure(text):
    """Parse + structurally validate one program. Returns (spec, errors);
    spec is None when the YAML itself is unreadable. errors are
    (location, detail) pairs — the extractor wraps them into Findings."""
    errors = []
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [("-", f"cannot parse procedure YAML: {exc}")]
    if not isinstance(spec, dict):
        return None, [("-", "procedure file root must be a mapping")]
    if not spec.get("procedure"):
        errors.append(("procedure", "procedure needs 'procedure'"))
    if spec.get("completeness") and \
            spec["completeness"] not in COMPLETENESS_LEVELS:
        errors.append(("completeness",
                       f"unknown completeness '{spec['completeness']}' "
                       f"(known: {sorted(COMPLETENESS_LEVELS)})"))
        return spec, errors
    completeness = effective_completeness(spec)
    if completeness is None:
        errors.append(("completeness",
                       "procedure needs steps (transcribed) or an explicit "
                       "completeness: attested | cited"))
        return spec, errors
    allowed = TOP_KEYS_BY_COMPLETENESS[completeness]
    for key in spec:
        if key not in allowed:
            errors.append((key, f"'{key}' is not a valid key for a "
                                f"{completeness} procedure"))
    _check_specified_in(spec, errors)
    _check_inputs(spec, errors)
    _check_precondition(spec, errors)
    if spec.get("locals") is not None and (
            not isinstance(spec["locals"], list)
            or not all(isinstance(name, str) for name in spec["locals"])):
        errors.append(("locals",
                       "'locals' must be a list of the program's "
                       "non-citizen computed names"))
    match completeness:
        case Completeness.TRANSCRIBED:
            if not spec.get("steps"):
                errors.append(("steps",
                               "a transcribed procedure needs steps"))
            else:
                _check_sequence(spec["steps"], "steps", errors)
                _check_outcome_bijection(spec, errors)
        case Completeness.ATTESTED:
            _check_attested_sections(spec, errors)
            _check_attested_outcomes(spec, errors)
    return spec, errors


def _check_specified_in(spec, errors):
    raw = spec.get("specified_in")
    if isinstance(raw, dict):
        for key in raw:
            if key not in KNOWN_SPECIFIED_IN_KEYS:
                errors.append(("specified_in",
                               f"unknown specified_in key '{key}'"))
        section = raw.get("section")
        if isinstance(section, list):
            if not section or not all(
                    isinstance(s, str) and s.strip() for s in section):
                errors.append(("specified_in",
                               "'section' list entries must be non-empty "
                               "heading strings"))
            if not (raw.get("artifact") or "").strip():
                errors.append(("specified_in",
                               "a multi-section citation needs 'artifact' "
                               "— only file-span citations may list "
                               "several sections"))
        elif not section:
            errors.append(("specified_in",
                           "specified_in mapping needs 'section'"))
        approved = raw.get("approved_hash")
        if approved is not None and not (
                isinstance(approved, str) and len(approved) == 64
                and all(c in "0123456789abcdef" for c in approved)):
            errors.append(("specified_in",
                           "approved_hash must be a 64-char sha256 hex "
                           "string (quote it — YAML parses all-digit "
                           "values as numbers)"))
        approved_in = raw.get("approved_in")
        if approved_in is not None and not (
                isinstance(approved_in, str) and approved_in.strip()):
            errors.append(("specified_in",
                           "approved_in must be a commit or PR link "
                           "(the archive pointer that retrieves the "
                           "approved text)"))


KNOWN_PRECONDITION_KEYS = {"text", "from_text"}


def _check_precondition(spec, errors):
    """A precondition is a plain string, or the mapping form
    {text, from_text} so its quote is machine-verified like inputs'
    and outcomes' receipts are."""
    entry = spec.get("precondition")
    if entry is None or isinstance(entry, str):
        return
    if not isinstance(entry, dict):
        errors.append(("precondition",
                       "precondition must be a string or a "
                       "{text, from_text} mapping"))
        return
    for key in entry:
        if key not in KNOWN_PRECONDITION_KEYS:
            errors.append(("precondition",
                           f"unknown precondition key '{key}'"))
    if not str(entry.get("text") or "").strip():
        errors.append(("precondition",
                       "precondition mapping needs a 'text'"))


def _check_inputs(spec, errors):
    for section in ("inputs", "outputs"):
        entries = spec.get(section)
        if entries is None:
            continue
        if not isinstance(entries, dict):
            errors.append((section, f"'{section}' must be a mapping of "
                                    "name -> description"))
            continue
        if section == "outputs":
            continue  # outputs stay plain descriptions
        for name, entry in entries.items():
            if isinstance(entry, dict):
                for key in entry:
                    if key not in KNOWN_INPUT_KEYS:
                        errors.append((f"inputs.{name}",
                                       f"unknown input key '{key}'"))
                if not entry.get("description"):
                    errors.append((f"inputs.{name}",
                                   "input mapping needs a description"))


def input_fields(entry):
    """Normalize an inputs entry to (description, required, when_absent)."""
    if isinstance(entry, dict):
        return ((entry.get("description") or "").strip(),
                entry.get("required", True),
                (entry.get("when_absent") or "").strip())
    return (entry or "").strip(), True, ""


def precondition_text(spec):
    """The precondition's prose, whichever form carried it: the plain
    string, or the mapping form's `text` (the mapping exists so the
    precondition can carry a machine-verified from_text receipt like
    inputs and outcomes do)."""
    entry = spec.get("precondition")
    if isinstance(entry, dict):
        return str(entry.get("text") or "").strip()
    return str(entry or "").strip()


def receipts_of(spec):
    """Every (location, from_text) receipt an authored fact carries."""
    receipts = []
    for name, entry in (spec.get("inputs") or {}).items():
        if isinstance(entry, dict) and entry.get("from_text"):
            receipts.append((f"inputs.{name}", entry["from_text"].strip()))
    for name, entry in (spec.get("possible_outcomes") or {}).items():
        if isinstance(entry, dict) and entry.get("from_text"):
            receipts.append((f"possible_outcomes.{name}",
                             entry["from_text"].strip()))
    entry = spec.get("precondition")
    if isinstance(entry, dict) and entry.get("from_text"):
        receipts.append(("precondition", entry["from_text"].strip()))
    return receipts


def collect_stops(items):
    """Every (stop_text, inline_outcome) in a step tree, in order."""
    stops = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if BRANCH_KEY in item:
            for body in (item.get("cases") or {}).values():
                stops.extend(collect_stops(body))
        elif "when" in item:
            stops.extend(collect_stops(item.get("then")))
            stops.extend(collect_stops(item.get("otherwise")))
        elif set(item) == {"otherwise"}:
            stops.extend(collect_stops(item["otherwise"]))
        elif "stop" in item:
            stops.append(stop_fields(item["stop"]))
    return stops


def _check_outcome_bijection(spec, errors):
    """possible_outcomes <-> stops: every stop claimed by exactly one
    outcome; every outcome claims at least one stop. (Only enforced when
    the block is present.)"""
    outcomes = spec.get("possible_outcomes")
    if outcomes is None:
        return
    if not isinstance(outcomes, dict) or not outcomes:
        errors.append(("possible_outcomes",
                       "possible_outcomes must be a non-empty mapping"))
        return
    ends_by_outcome = {}
    for name, entry in outcomes.items():
        loc = f"possible_outcomes.{name}"
        entry = entry or {}
        if not isinstance(entry, dict):
            errors.append((loc, "outcome must be a mapping"))
            continue
        for key in entry:
            if key not in KNOWN_OUTCOME_KEYS:
                errors.append((loc, f"unknown outcome key '{key}'"))
        guarantee = entry.get("guarantee")
        if not guarantee:
            errors.append((loc, "outcome needs a guarantee "
                                f"({sorted(GUARANTEES)})"))
        elif guarantee not in GUARANTEES:
            errors.append((loc, f"unknown guarantee '{guarantee}' "
                                f"(known: {sorted(GUARANTEES)})"))
        ends_by_outcome[name] = (entry.get("ends") or "").strip()
    claimed = {name: 0 for name in ends_by_outcome}
    for stop_text, inline in collect_stops(spec.get("steps")):
        owners = [name for name in ends_by_outcome
                  if name == inline or (ends_by_outcome[name]
                                        and ends_by_outcome[name] == stop_text)]
        owners = sorted(set(owners))
        if not owners:
            errors.append((f"stop '{stop_text}'",
                           "stop not claimed by any possible_outcome"))
        elif len(owners) > 1:
            errors.append((f"stop '{stop_text}'",
                           f"stop claimed by multiple outcomes {owners}"))
        else:
            claimed[owners[0]] += 1
    for name, count in claimed.items():
        if count == 0:
            errors.append((f"possible_outcomes.{name}",
                           "outcome claims no stop (ends: matches nothing "
                           "and no stop is tagged with it)"))


def _check_attested_sections(spec, errors):
    for section in ("reads", "consults", "mutates"):
        entry = spec.get(section)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            errors.append((section, f"'{section}' must be a mapping "
                                    "{closed: bool, known: [names]}"))
            continue
        for key in entry:
            if key not in KNOWN_SECTION_KEYS:
                errors.append((section, f"unknown key '{key}'"))
        if not isinstance(entry.get("closed", False), bool):
            errors.append((section, "'closed' must be true or false"))
        if entry.get("known") is not None and \
                not isinstance(entry["known"], list):
            errors.append((section, "'known' must be a list of names"))


def _check_attested_outcomes(spec, errors):
    for name, entry in (spec.get("possible_outcomes") or {}).items():
        loc = f"possible_outcomes.{name}"
        entry = entry or {}
        if not isinstance(entry, dict):
            errors.append((loc, "outcome must be a mapping"))
            continue
        for key in entry:
            if key not in KNOWN_ATTESTED_OUTCOME_KEYS:
                errors.append((loc, f"unknown attested-outcome key '{key}' "
                                    "(ends: is transcribed-only — attested "
                                    "procedures have no stops)"))
        guarantee = entry.get("guarantee")
        if guarantee and guarantee not in GUARANTEES:
            errors.append((loc, f"unknown guarantee '{guarantee}' "
                                f"(known: {sorted(GUARANTEES)})"))
        for listy in ("assigns", "mutates"):
            if entry.get(listy) is not None and \
                    not isinstance(entry[listy], list):
                errors.append((loc, f"'{listy}' must be a list of names"))


def _check_sequence(items, loc, errors):
    if not isinstance(items, list):
        errors.append((loc, "step sequence must be a list"))
        return
    for index, item in enumerate(items, start=1):
        here = f"{loc}[{index}]"
        if not isinstance(item, dict) or not item:
            errors.append((here, "step must be a mapping"))
            continue
        if BRANCH_KEY in item:
            if set(item) != {BRANCH_KEY, "cases"}:
                errors.append((here, "a branch step has exactly "
                                     f"'{BRANCH_KEY}' and 'cases'"))
            cases = item.get("cases")
            if not isinstance(cases, dict) or not cases:
                errors.append((here, "cases must be a non-empty mapping"))
            else:
                for case, body in cases.items():
                    _check_sequence(body, f"{here}.{case}", errors)
        elif "when" in item:
            unknown = set(item) - {"when", "then", "otherwise"}
            if unknown:
                errors.append((here, f"unknown when-step keys {sorted(unknown)}"))
            if not item.get("then"):
                errors.append((here, "a when step needs 'then'"))
            else:
                _check_sequence(item["then"], f"{here}.then", errors)
            if "otherwise" in item:
                _check_sequence(item["otherwise"], f"{here}.else", errors)
        elif "otherwise" in item:
            if set(item) != {"otherwise"}:
                errors.append((here, "an otherwise step has only 'otherwise'"))
            elif index == 1 or "when" not in items[index - 2]:
                errors.append((here, "otherwise must follow a when step"))
            else:
                _check_sequence(item["otherwise"], f"{here}", errors)
        else:
            (verb, value), *extra = item.items()
            if extra:
                errors.append((here, "an action step has a single verb key"))
            elif verb not in ACTION_VERBS:
                errors.append((here, f"unknown action verb '{verb}' "
                                     f"(known: {list(ACTION_VERBS)})"))
            elif verb == "stop" and isinstance(value, dict):
                unknown = set(value) - {"outcome", "note"}
                if unknown:
                    errors.append((here, f"unknown stop keys {sorted(unknown)}"))
                elif not (value.get("note") or "").strip():
                    errors.append((here, "a tagged stop needs 'note' prose"))
            elif not isinstance(value, str) or not value.strip():
                errors.append((here, f"'{verb}' needs prose after it"))


# -- lift ---------------------------------------------------------------------

class _Lifter:
    def __init__(self, proc_name):
        self.proc = proc_name
        self.out = Lift()

    def step(self, path, kind, text, condition="", outcome=""):
        name = f"{self.proc} §{path}"
        self.out.steps.append(LiftedStep(name, kind, text, condition, outcome))
        return name

    def edge(self, edge_type, from_name, to_name):
        self.out.edges.append((edge_type, from_name, to_name))

    def sequence(self, items, prefix, trail):
        """Lift a step list: siblings chain with NEXT; an otherwise item
        hangs off its preceding when via OTHERWISE. `trail` is the action
        steps accumulated on the path from the procedure start (terminals
        record a copy). Returns the first step's name."""
        first = prev = prev_path = None
        count = 0
        for item in items:
            if set(item) == {"otherwise"}:
                body_first = self.sequence(item["otherwise"],
                                           f"{prev_path}.else", list(trail))
                self.edge(OTHERWISE, prev, body_first)
                continue
            count += 1
            path = f"{prefix}.{count}" if prefix else str(count)
            name = self.item(item, path, trail)
            first = first or name
            if prev:
                self.edge(NEXT, prev, name)
            prev, prev_path = name, path
        return first

    def item(self, item, path, trail):
        if BRANCH_KEY in item:
            name = self.step(path, "branch", f"branch on {item[BRANCH_KEY]}")
            for case, body in item["cases"].items():
                case_name = self.step(f"{path}.{case}", "case", case)
                self.edge(CASE, name, case_name)
                self.out.cases.append((case_name, case))
                body_first = self.sequence(body, f"{path}.{case}", list(trail))
                if body_first:
                    self.edge(NEXT, case_name, body_first)
            return name
        if "when" in item:
            condition = item["when"]
            name = self.step(path, "when", condition, condition=condition)
            self.edge(THEN, name, self.sequence(item["then"], path,
                                                list(trail)))
            if "otherwise" in item:
                self.edge(OTHERWISE, name,
                          self.sequence(item["otherwise"], f"{path}.else",
                                        list(trail)))
            return name
        (verb, value), = item.items()
        if verb == "stop":
            note, inline_outcome = stop_fields(value)
            name = self.step(path, verb, f"stop {note}",
                             outcome=inline_outcome)
            self.out.terminals.append(Terminal(name, note, inline_outcome,
                                               trail + [name]))
            return name
        name = self.step(path, verb, f"{verb} {value.strip()}")
        trail.append(name)
        return name


def lift(spec):
    """Turn a parsed program into Step structure (pure names; the extractor
    materializes nodes/edges and resolves case values and references)."""
    lifter = _Lifter(spec["procedure"])
    lifter.out.first_step = lifter.sequence(spec.get("steps") or [], "", []) or ""
    return lifter.out


def bind_outcomes(spec, lifted):
    """Match possible_outcomes to lifted terminals. Returns
    {outcome_name: {"guarantee", "notes", "terminal_steps", "trail_steps"}}.
    Assumes parse_procedure's bijection check passed (unmatched stops were
    already errors)."""
    outcomes = spec.get("possible_outcomes") or {}
    bound = {name: {"guarantee": (entry or {}).get("guarantee", ""),
                    "notes": [], "terminal_steps": [], "trail_steps": []}
             for name, entry in outcomes.items()}
    ends_by_outcome = {name: ((entry or {}).get("ends") or "").strip()
                       for name, entry in outcomes.items()}
    for terminal in lifted.terminals:
        owners = [name for name in bound
                  if name == terminal.inline_outcome
                  or (ends_by_outcome[name]
                      and ends_by_outcome[name] == terminal.stop_text)]
        if len(owners) != 1:
            continue  # bijection errors already reported at parse
        entry = bound[owners[0]]
        if terminal.stop_text and terminal.stop_text not in entry["notes"]:
            entry["notes"].append(terminal.stop_text)
        entry["terminal_steps"].append(terminal.step_name)
        entry["trail_steps"].extend(
            step for step in terminal.trail if step not in entry["trail_steps"])
    return bound


# -- derivation (Validation A) ------------------------------------------------

def branches_on_subject(spec, subject_surfaces):
    """The branch-on texts of every top-level branch whose subject resolves
    to one of `subject_surfaces` (the surface forms of the corpus's
    Exclusive+Stateful subject concepts). Resolution is the term index's
    letter-bounded match, not a substring test — 'State' does not fire on
    'Statement', and a declared plural surface still resolves. This is what
    lets the answer-key check tell "attests nothing" (a real subject branch
    that derived no rows) apart from "no subject branch here at all"."""
    return [item[BRANCH_KEY] for item in spec.get("steps") or []
            if BRANCH_KEY in item
            and parsers.mention_matches(item[BRANCH_KEY], subject_surfaces)]


def walk_transitions(spec, subject_surfaces):
    """Every (from, to) transition fact the program implies: for each case
    of a branch whose subject resolves to one of `subject_surfaces` — the
    surface forms of the corpus's Exclusive+Stateful subject concepts,
    discovered from the ontology and expanded through the term index (the
    engine assumes no corpus's ladder) — every `become:` reachable under
    that case yields (case value, become value)."""

    def becomes(items):
        for item in items:
            if "become" in item:
                yield item["become"].strip()
            for key in ("then", "otherwise"):
                if isinstance(item.get(key), list):
                    yield from becomes(item[key])

    found = set()
    for item in spec.get("steps") or []:
        if BRANCH_KEY in item and \
                parsers.mention_matches(item[BRANCH_KEY], subject_surfaces):
            for case, body in item["cases"].items():
                found.update((case, target) for target in becomes(body))
    return found


# -- generation (Validation B) ------------------------------------------------

def render_markdown(spec):
    """Deterministic template rendering of a program back into rulebook-style
    prose. An experiment in closing the graph->prose loop: output is measured
    against the authored section, never adopted automatically."""
    lines = [f"### {spec['procedure']}", ""]
    if precondition_text(spec):
        lines += [f"*Precondition:* {precondition_text(spec)}. "
                  "If not met, skip this step.", ""]
    # The whole signature renders, not just the steps: authored inputs and
    # outputs face the generation diff too — an input the source never
    # states shows up as an invention (the Truename lesson).
    for section, title in (("inputs", "Inputs"), ("outputs", "Outputs")):
        entries = spec.get(section)
        if not entries:
            continue
        lines.append(f"**{title}:**")
        for name, entry in entries.items():
            if section == "inputs":
                description, required, when_absent = input_fields(entry)
                line = f"- {name} — {description}" if description else f"- {name}"
                if not required:
                    line += " *(optional"
                    if when_absent:
                        line += f"; when absent: {when_absent}"
                    line += ")*"
            else:
                line = f"- {name} — {entry}"
            lines.append(line)
        lines.append("")
    for item in spec.get("steps") or []:
        if BRANCH_KEY in item:
            lines += [f"Compare the {item[BRANCH_KEY]}:", ""]
            for case, body in item["cases"].items():
                lines.append(f"- **{case}:** {_render_body(body)}")
                lines.append("")
        else:
            lines += [_render_item(item), ""]
    return "\n".join(lines).rstrip() + "\n"


def _render_body(items):
    """A case body: bare actions join into one sentence run; when/otherwise
    alternatives become indented sub-bullets."""
    whens = [item for item in items if "when" in item or "otherwise" in item]
    if not whens:
        return " ".join(_render_item(item) for item in items)
    parts = [""]
    for item in items:
        if "when" in item:
            line = (f"  - *{_sentence(item['when'])}:* "
                    f"{' '.join(_render_item(sub) for sub in item['then'])}")
            if "otherwise" in item:
                line += (" Otherwise: "
                         + " ".join(_render_item(sub)
                                    for sub in item["otherwise"]))
            parts.append(line)
        elif set(item) == {"otherwise"}:
            parts.append("  - *Otherwise:* "
                         + " ".join(_render_item(sub)
                                    for sub in item["otherwise"]))
        else:
            parts.append(f"  {_render_item(item)}")
    return "\n".join(parts)


def _render_item(item):
    if "when" in item:
        line = (f"If {item['when']}: "
                + " ".join(_render_item(sub) for sub in item["then"]))
        if "otherwise" in item:
            line += (" Otherwise: "
                     + " ".join(_render_item(sub)
                                for sub in item["otherwise"]))
        return line
    if set(item) == {"otherwise"}:
        # a top-level otherwise sits as a sibling of the prior when — the
        # validator allows the shape; render it the way _render_body does
        return ("Otherwise: "
                + " ".join(_render_item(sub) for sub in item["otherwise"]))
    (verb, value), = item.items()
    if verb == "stop":
        note, _ = stop_fields(value)
        return _sentence(f"stop here — {note}.")
    value = value.strip()
    match verb:
        case "spend" | "reduce" | "set" | "roll" | "compute":
            return _sentence(f"{verb} {value}.")
        case "become":
            return f"The character becomes {value}."
        case "call":
            return f"Perform the {value}."
        case "note":
            return _sentence(f"{value}.")
        case "continue":
            return _sentence(f"{value}.")
    return _sentence(f"{verb} {value}.")


def _sentence(text):
    return text[:1].upper() + text[1:] if text else text


def truncation_findings(text, spec):
    """Comment-like tails that YAML may have silently swallowed (the silent-truncation tripwire).

    An unquoted scalar stops at ' #' — an inline citation or a numbered
    reference eats the rest of its own sentence, and nothing errors. For
    every raw line carrying a ' #' tail that did NOT survive into any
    parsed string, report (lineno, tail): the author either meant a
    comment (fine — the finding says so) or lost content (the reason
    this tripwire exists). Full-line comments never flag."""
    strings = set()

    def collect(value):
        if isinstance(value, str):
            strings.add(" ".join(value.split()))
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(spec)
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or " #" not in line:
            continue
        head, tail = line.split(" #", 1)
        tail = " ".join(tail.split()).rstrip("\"'")
        if not tail:
            continue
        if any(tail in parsed for parsed in strings):
            continue  # quoted properly; the tail survived parsing
        # A tail after a FINISHED sentence reads as a deliberate comment;
        # a tail after a mid-sentence break is the eaten-content
        # signature this tripwire exists for.
        if head.rstrip()[-1:] in ".!?\"')]}":
            continue
        # Keys whose values are constrained elsewhere (enum checks, the
        # ends<->stop bijection) already scream on truncation — a tail
        # there is a comment, not a loss.
        key = head.split(":", 1)[0].strip().lstrip("- ")
        if key in ("guarantee", "ends", "completeness", "required",
                   "closed", "known"):
            continue
        findings.append((lineno, tail))
    return findings
