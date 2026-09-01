"""The conduct plugin: trigger stubs over pulled content (the stub
model). The plugin carries only a stub per skill — name, the
when-to-use description, and a pointer at ``python -m graph docs
<name>`` — while the procedure content ships once, in the pip package.
These tests keep the stubs honest: one stub per packaged skill, the
trigger text identical, the pointer present, and the plugin's version
locked to the package's so the two channels cannot drift.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUBS = ROOT / "skills"
PACKAGED = ROOT / "graph" / "engine_docs" / "skills"
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def _field(path, field):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(field + ":"):
            return line[len(field) + 1:].strip()
    return None


def _skill_names(root):
    return sorted(d.name for d in root.iterdir()
                  if (d / "SKILL.md").is_file())


def test_one_stub_per_packaged_skill_no_orphans():
    assert _skill_names(STUBS) == _skill_names(PACKAGED)


def test_stub_trigger_text_matches_the_packaged_skill():
    for name in _skill_names(PACKAGED):
        stub = _field(STUBS / name / "SKILL.md", "description")
        packaged = _field(PACKAGED / name / "SKILL.md", "description")
        assert stub == packaged, (
            f"skills/{name}: the stub's description (the trigger text) "
            "must equal the packaged skill's — regenerate the stub.")
        assert _field(STUBS / name / "SKILL.md", "name") == name


def test_stub_points_at_the_docs_reader():
    for name in _skill_names(STUBS):
        body = (STUBS / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"python -m graph docs {name}" in body, (
            f"skills/{name}: the stub must pull its instructions via "
            "the docs reader.")


def test_plugin_version_locks_to_the_package():
    manifest = json.loads(PLUGIN.read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_version = re.search(
        r'^version = "([^"]+)"', pyproject, re.M).group(1)
    assert manifest["version"] == package_version, (
        "the plugin and the pip package ride the same tag — bump "
        ".claude-plugin/plugin.json with pyproject.toml.")
    assert manifest["name"] == "ghostwheel"


def test_marketplace_serves_the_plugin_from_the_repo_root():
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    [entry] = market["plugins"]
    assert entry["name"] == "ghostwheel" and entry["source"] == "./"
