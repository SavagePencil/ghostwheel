"""The loader learns the released label.

A released label's canon contract is "reader, no source": its files are
gone and every citizen carries its own body, arriving by rounds. The
bootstrap loader admits that shape as a fourth origin — exactly one of
source / values / implicit / reader-without-source — so a corpus that
keeps its bootstrap file mirrors the released spec verbatim and the
spec-for-spec equivalence with canon holds with no fold. The from-sources
extractor reads nothing for such a label; the lift reads whatever bodies
canon carries, under either ontology alike. `implicit: true` keeps its
own meaning (citizens materialize from referencing cells) and is never
the way to spell a released label.

Storybook domain: the wilting tale from the answer-key fixtures.
"""

import json

import tests.conftest as conftest
from graph import export as export_mod
from graph.extract import derive, extract
from graph.ontology import (ARCHETYPE_LABEL, ERROR, load_ontology,
                            ontology_from_graph)
from tests.test_answer_keys import FILES, GOOD_KEYS, ONTOLOGY
from tests.test_graph_resident_bodies import _adopt, _clone, _corpus

_make_repo = getattr(conftest.make_repo, "__wrapped__", conftest.make_repo)

RELEASED = ONTOLOGY.format(keys=GOOD_KEYS).replace(
    "        source: [data/procedures/wilt.yaml]\n", "")


def _errors(findings):
    return [f.detail for f in findings if f.severity == ERROR]


def test_a_reader_without_a_source_loads_as_a_released_label(tmp_path):
    files = {k: v for k, v in FILES.items() if not k.startswith("data/proc")}
    base_dir, path = _make_repo(tmp_path)(files, RELEASED)
    ontology, findings = load_ontology(path, base_dir)
    assert ontology is not None
    assert _errors(findings) == [], findings
    assert "source" not in ontology.nodes["[Procedure]"]
    assert ontology.nodes["[Procedure]"]["reader"] == "procedure_yaml"
    # nothing to read from sources: no citizens, no findings under it
    graph, extract_findings = extract(ontology)
    assert _errors(extract_findings) == []
    assert not [n for (label, n) in graph.nodes if label == "[Procedure]"]
    # and the embedding carries the released spec verbatim
    row = graph.nodes[(ARCHETYPE_LABEL, "[Procedure]")]
    assert "source" not in json.loads(row["spec_json"])


def test_the_released_spec_matches_canon_with_no_fold(tmp_path):
    base_dir, filed = _corpus(tmp_path)
    resident = _adopt(_clone(filed))
    (base_dir / "data" / "procedures" / "wilt.yaml").unlink()
    (base_dir / "graph" / "ontology.yaml").write_text(RELEASED,
                                                      encoding="utf-8")
    yaml_ontology, findings = load_ontology(
        base_dir / "graph" / "ontology.yaml", base_dir)
    assert yaml_ontology is not None and _errors(findings) == []
    rec = ontology_from_graph(resident, base_dir)
    assert yaml_ontology.nodes["[Procedure]"] == rec.nodes["[Procedure]"]
    # the lift reads the resident bodies under either ontology alike
    from_yaml, f1 = derive(yaml_ontology, resident)
    from_canon, f2 = derive(rec, resident)
    assert _errors(f1) == [] and _errors(f2) == []
    assert export_mod.serialize(from_yaml) == export_mod.serialize(from_canon)
    assert any(e.type == "KNOWN_AT" and e.from_name == "Wilt"
               for e in from_yaml.edges)


def test_the_origin_rule_still_refuses_none_and_two(tmp_path):
    files = {k: v for k, v in FILES.items() if not k.startswith("data/proc")}
    none = RELEASED.replace("        reader: procedure_yaml\n", "")
    base_dir, path = _make_repo(tmp_path)(files, none)
    _, findings = load_ontology(path, base_dir)
    assert any("exactly one of source / values / implicit / "
               "reader-without-source" in d for d in _errors(findings))
    two = RELEASED.replace("        reader: procedure_yaml\n",
                           "        reader: procedure_yaml\n"
                           "        implicit: true\n")
    (base_dir / "graph" / "ontology.yaml").write_text(two, encoding="utf-8")
    _, findings = load_ontology(base_dir / "graph" / "ontology.yaml",
                                base_dir)
    assert any("exactly one of" in d for d in _errors(findings))
    unknown = RELEASED.replace("reader: procedure_yaml", "reader: runes")
    (base_dir / "graph" / "ontology.yaml").write_text(unknown,
                                                      encoding="utf-8")
    _, findings = load_ontology(base_dir / "graph" / "ontology.yaml",
                                base_dir)
    assert any("unknown reader 'runes'" in d for d in _errors(findings))
