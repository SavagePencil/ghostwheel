"""The conduct plugin: trigger stubs over pulled content (the stub
model). The plugin carries only a stub per conduct record — name, the
when-to-use description, and a pointer at ``python -m graph docs
<name>`` — while the procedure content lives once, in the manual's
canon. These tests keep the stubs honest: one stub per canon conduct
record, the trigger text identical to the citizen's description, the
pointer present, the engine repo's own skills the same stubs (the
dogfood), and the plugin's version locked to the package's so the two
channels cannot drift.
"""

import json
import re
from pathlib import Path

from graph import records

ROOT = Path(__file__).resolve().parent.parent
STUBS = ROOT / "skills"
DOGFOOD = ROOT / ".claude" / "skills"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def _field(path, field):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(field + ":"):
            return line[len(field) + 1:].strip()
    return None


def _stub_names(root):
    return sorted(d.name for d in root.iterdir()
                  if (d / "SKILL.md").is_file())


def _canon_conduct():
    """handle -> description, straight from the packaged canon."""
    canon = records.load_canon()
    assert canon is not None, "the package must ship the manual's canon"
    return {handle: canon.nodes[(label, name)].get("description")
            for handle, (label, name) in records.records(canon).items()
            if records.is_conduct(label)}


def test_one_stub_per_canon_conduct_record_no_orphans():
    assert _stub_names(STUBS) == sorted(_canon_conduct())


def test_stub_trigger_text_matches_the_canon_citizen():
    for handle, description in _canon_conduct().items():
        stub = _field(STUBS / handle / "SKILL.md", "description")
        assert stub == description, (
            f"skills/{handle}: the stub's description (the trigger text) "
            "must equal the canon citizen's — regenerate the stub.")
        assert _field(STUBS / handle / "SKILL.md", "name") == handle


def test_stub_points_at_the_docs_reader():
    for handle in _stub_names(STUBS):
        body = (STUBS / handle / "SKILL.md").read_text(encoding="utf-8")
        assert f"python -m graph docs {handle}" in body, (
            f"skills/{handle}: the stub must pull its instructions via "
            "the docs reader.")


def test_the_engine_repo_eats_the_dogfood():
    assert _stub_names(DOGFOOD) == _stub_names(STUBS)
    for handle in _stub_names(STUBS):
        ours = (DOGFOOD / handle / "SKILL.md").read_bytes()
        plugin = (STUBS / handle / "SKILL.md").read_bytes()
        assert ours == plugin, (
            f".claude/skills/{handle}: the engine repo's own skill must "
            "be the plugin's stub, byte for byte — the prose lives in "
            "canon now.")


def test_plugin_version_locks_to_the_package():
    manifest = json.loads(PLUGIN.read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_line = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert version_line, "pyproject.toml carries no version line"
    package_version = version_line.group(1)
    assert manifest["version"] == package_version, (
        "the plugin and the pip package ride the same tag — bump "
        ".claude-plugin/plugin.json with pyproject.toml.")
    assert manifest["name"] == "ghostwheel"


def test_marketplace_serves_the_plugin_from_the_repo_root():
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    [entry] = market["plugins"]
    assert entry["name"] == "ghostwheel" and entry["source"] == "./"
