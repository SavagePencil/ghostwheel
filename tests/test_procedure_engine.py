"""The procedure-round engine sitting.

- program bodies sync from their approved files (the file is the truth;
  the paste-and-hash ritual retires; the whole scratch graph is scanned
  so forgot-to-paste can't hide outside the changeset).
- the silent-truncation tripwire: a ' #' tail that vanished in parsing is
  surfaced, with finished-sentence comments and constrained-key comments
  excluded.
- a chapter-spanning procedure may cite several sections; receipts and the
  approved hash cover all of them.
"""

from graph import procedures
from graph.delta import body_sync_violations
from graph.extract import GraphData


# --- multi-section citations -----------------------------------------------

def test_specified_in_normalizes_all_shapes():
    single = {"specified_in": {"artifact": "docs/x.md", "section": "A"}}
    multi = {"specified_in": {"artifact": "docs/x.md",
                              "section": ["A", "B"]}}
    citizen = {"specified_in": "Awaken"}
    assert procedures.specified_in_of(single) == ("docs/x.md", ["A"], None)
    assert procedures.specified_in_of(multi) == ("docs/x.md", ["A", "B"],
                                                 None)
    assert procedures.specified_in_of(citizen) == (None, ["Awaken"], None)
    assert procedures.specified_in_of({}) == (None, [], None)


def test_multi_section_requires_artifact():
    text = ("procedure: T\ncompleteness: cited\n"
            "specified_in:\n  section: [A, B]\n")
    spec, errors = procedures.parse_procedure(text)
    assert any("multi-section citation needs 'artifact'" in detail
               for _, detail in errors)


# --- the silent-truncation tripwire -----------------------------------------

def _findings(text):
    spec, errors = procedures.parse_procedure(text)
    assert spec is not None and not errors, errors
    return procedures.truncation_findings(text, spec)


def test_truncation_catches_eaten_mid_sentence_tail():
    text = ("procedure: T\nsteps:\n"
            "  - note: compare against the roster #2 rows apply here\n")
    assert _findings(text) == [(3, "2 rows apply here")]


def test_truncation_ignores_quoted_and_comment_shapes():
    text = ("procedure: T\n"
            "# a full-line comment #with a hash\n"
            "completeness: transcribed   # constrained key comment\n"
            "steps:\n"
            "  - note: \"the whole sentence #2 included, quoted\"\n"
            "  - note: a finished sentence.  # a deliberate aside\n")
    assert _findings(text) == []


# --- body sync ---------------------------------------------------------------

def _graph_with_body(source_path, body):
    graph = GraphData()
    graph.ensure_node("Procedure", "T", body=body,
                      source_path=source_path)
    return graph


def test_body_in_sync_passes(tmp_path):
    (tmp_path / "prog.yaml").write_text("procedure: T\n", encoding="utf-8")
    graph = _graph_with_body("prog.yaml", "procedure: T\n")
    assert body_sync_violations(graph, tmp_path) == []


def test_body_out_of_sync_is_a_violation(tmp_path):
    (tmp_path / "prog.yaml").write_text("procedure: T\n# edited\n",
                                        encoding="utf-8")
    graph = _graph_with_body("prog.yaml", "procedure: T\n")
    violations = body_sync_violations(graph, tmp_path)
    assert len(violations) == 1
    assert "out of sync" in violations[0]
    assert "--sync-bodies" in violations[0]


def test_missing_program_file_is_a_violation(tmp_path):
    graph = _graph_with_body("gone.yaml", "procedure: T\n")
    violations = body_sync_violations(graph, tmp_path)
    assert len(violations) == 1
    assert "not readable" in violations[0]


def test_nodes_without_programs_are_ignored(tmp_path):
    graph = GraphData()
    graph.ensure_node("Knack", "Rally", description="no body here")
    assert body_sync_violations(graph, tmp_path) == []
