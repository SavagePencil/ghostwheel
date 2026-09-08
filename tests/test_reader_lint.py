"""A spec's declared reader must be a kind the engine knows.

The yaml loader once validated this; post-closure the schema stratum
is the only declaration surface, and a label whose spec names an
unknown reader would simply never lift its citizens' bodies — silence
reading as held. Derivation names it as an ERROR per label, and the
delta gate's landing preview promotes derive ERRORs, so a round that
lands a bad reader refuses at the gate.
"""

import json

from graph.extract import derive, make_edge, unknown_reader_findings
from graph.ontology import ARCHETYPE_LABEL, ontology_from_graph
from graph.report import REF_KEYS
from tests.test_branch import build_canon


def _declare(canon, label, spec):
    canon.ensure_node(ARCHETYPE_LABEL, label, doc="a kind of writing",
                      spec_json=json.dumps(spec))
    canon.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, label,
                                 ARCHETYPE_LABEL, "Ontology"))


def test_an_unknown_reader_is_an_error_named_per_label(tmp_path):
    canon = build_canon()
    _declare(canon, "[Scroll]", {"reader": "papyrus"})
    canon.ensure_node("[Scroll]", "the wilting tale", body="once, a vine")
    _, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    [finding] = [f for f in findings if "papyrus" in f.detail]
    assert finding.severity == "error"
    assert "[Scroll]" in finding.detail
    assert "never lift" in finding.detail
    assert "csv_rows" in finding.detail  # the known kinds are offered


def test_a_known_reader_and_a_readerless_spec_are_clean(tmp_path):
    canon = build_canon()
    _declare(canon, "[Recipe]", {"reader": "procedure_yaml"})
    canon.ensure_node("[Recipe]", "brew a calming tea",
                      body="steps: []", completeness="Transcribed")
    _declare(canon, "[Notice]", {"properties": {"tone": {"type": "str"}}})
    canon.ensure_node("[Notice]", "the fair opens", tone="bright")
    _, findings = derive(ontology_from_graph(canon, tmp_path), canon)
    assert not [f for f in findings
                if f.severity == "error" and "reader" in f.detail.lower()]


def test_the_finding_has_a_designer_safe_ref():
    assert unknown_reader_findings.__name__  # the producer exists
    assert "label-reader-unknown" in REF_KEYS
