"""The from-sources era is closed.

A knowledge base is born graph-native (`init`) or ingested through the
front door; nothing bootstraps from files. The retired verbs refuse by
name — they do not vanish — and the committed backup alone marks a
knowledge base root. The staleness tripwire rides here too: the
packaged canon carries no retired machinery token, so a rename or a
retirement cannot leave stale prose behind silently.
"""

import json
import re
from pathlib import Path

import graph.__main__ as main_mod
from graph.ontology import METAONTOLOGY_PATH, load_metaontology

ENGINE = Path(__file__).resolve().parent.parent


# -- the retired verbs refuse by name --------------------------------------


def test_validate_refuses_and_points_at_the_graph_native_path(
        tmp_path, capsys):
    status, graph = main_mod.cmd_validate(tmp_path)
    assert (status, graph) == (1, None)
    err = capsys.readouterr().err
    assert "the from-sources era is closed" in err
    assert "check" in err and "corpus" in err and "rederive" in err


def test_load_refuses_and_points_at_restore_and_init(tmp_path, capsys):
    assert main_mod.cmd_load(tmp_path) == 1
    err = capsys.readouterr().err
    assert "the from-sources era is closed" in err
    assert "restore" in err and "init" in err


def test_export_from_sources_refuses_at_the_door(tmp_path, capsys,
                                                 monkeypatch):
    target = tmp_path / "hearth"
    assert main_mod.cmd_init(target, name="Hearth") == 0
    monkeypatch.setenv("GHOSTWHEEL_BASE", str(target))
    capsys.readouterr()
    assert main_mod.main(["export", "--from-sources"]) == 1
    err = capsys.readouterr().err
    assert "the from-sources era is closed" in err
    assert "FROM the database" in err


# -- the committed backup alone marks a knowledge base ---------------------


def test_a_yaml_file_no_longer_marks_a_knowledge_base(tmp_path):
    old_style = tmp_path / "old"
    (old_style / "graph").mkdir(parents=True)
    (old_style / "graph" / "ontology.yaml").write_text("nodes: {}\n",
                                                      encoding="utf-8")
    assert not main_mod._looks_like_kb(old_style)
    born = tmp_path / "born"
    assert main_mod.cmd_init(born, name="Born") == 0
    assert main_mod._looks_like_kb(born)


def test_the_root_refusal_offers_birth(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTWHEEL_BASE", str(tmp_path / "nowhere"))
    try:
        main_mod.find_base_dir()
    except SystemExit as exc:
        assert "init" in str(exc)
    else:
        raise AssertionError("an empty directory passed as a KB root")


# -- the staleness tripwire (packaged canon only; the mirror test holds
# the manual copy byte-equal, so one sweep covers both) --------------------

# regex tokens: the packaged metaontology.yaml is alive and well, so
# the ontology.yaml sweep must not substring-match it
RETIRED_TOKENS = (
    r"(?<!meta)ontology\.yaml",
    r"data/overlays",
    r"data/procedures",
    r"questions\.csv",
    r"validation\.md",
    r"engine_docs/design",
)


def _canon_text():
    text = []
    canon = ENGINE / "graph" / "engine_docs" / "canon" / "nodes.jsonl"
    for line in canon.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for value in (record.get("properties") or {}).values():
            if isinstance(value, str):
                text.append((record["label"], record["name"], value))
    return text


def test_packaged_canon_carries_no_retired_machinery_token():
    hits = []
    for label, name, value in _canon_text():
        for token in RETIRED_TOKENS:
            if re.search(token, value):
                hits.append(f"{label} / {name}: '{token}'")
    assert not hits, "retired tokens in packaged canon:\n" + "\n".join(hits)


def test_packaged_canon_carries_no_retired_kernel_name():
    # Only bracketed old names sweep cleanly: a bare old word (a name
    # later bracketed) is ordinary prose, and sweeping it would ban the
    # designer's own vocabulary. The bracketed forms are unambiguous
    # machinery tokens and never legal after their rename.
    _, meta, findings = load_metaontology(METAONTOLOGY_PATH)
    assert not findings, findings
    retired = [old for old in (meta.get("renamed") or {})
               if old.startswith("[")]
    assert retired, "the renamed map lost its bracketed entries"
    # A ruling's text is the record of what was decided, in the
    # vocabulary of its day — the Judgment family is exempt: rewriting
    # a ruling to modern names would forge history. Everything else in
    # canon is living prose and must speak the current names.
    historical = {"[Decision]", "[Question]", "[Answer]"}
    hits = []
    for label, name, value in _canon_text():
        if label in historical:
            continue
        for token in retired:
            if token in value:
                hits.append(f"{label} / {name}: '{token}'")
    assert not hits, "retired kernel names in packaged canon:\n" + \
        "\n".join(hits)
