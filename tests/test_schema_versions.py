"""The schema-version tripwire (owner rule): any change to the
metaontology or the project ontology must bump the version and append
(version, fingerprint) to the ledger — red otherwise, naming the file
and printing the fingerprint to paste. Versioning schemes split: the
metaontology stays SEMVER (bumps are ceremony); the project ontology is
a plain incremental REVISION NUMBER (`version: 30`) — the optional
free-text `tag:` beside it is display metadata and never enters the
ledger. The ontology's semver rows before the switch are history, never
rewritten.

The real repo's schema files are one instance of this contract; the test
drives it over a fixture repo built in tmp_path so the invariants are
exercised in isolation — a green repo, and a drifted one whose file
moved but whose ledger did not.
"""

import hashlib
import re

import pytest

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
REVISION = re.compile(r"^\d+$")

META_REL = "graph/metaontology.yaml"
ONTO_REL = "graph/ontology.yaml"
LEDGER_REL = "graph/schema-versions.txt"
SCHEMA_FILES = [META_REL, ONTO_REL]

# A metaontology parses clean (known keys only) and carries the four
# roots the loader layers a project ontology over; its version is semver.
METAONTOLOGY = """\
version: "{version}"
roots:
  Concept:
  Facet:
  Provenance:
  Judgment:
"""

# A project ontology: a plain revision number, an optional display tag,
# and an empty node set — enough for the loader to build an Ontology and
# report its self-description.
ONTOLOGY = """\
version: {version}
tag: {tag}
nodes: {{}}
"""


def _dummy_fingerprint(marker):
    """A stable placeholder hash for a ledger HISTORY row — never checked
    against a file (only the latest row is), so any distinct 64-hex value
    serves; deriving it from the version keeps rows self-explanatory."""
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()


def build_repo(root, *, meta_version, onto_version, onto_tag="draft",
               meta_history=(), onto_history=(),
               drift_meta=False, drift_onto=False):
    """Write a fixture repo (graph/metaontology.yaml, graph/ontology.yaml,
    graph/schema-versions.txt) into `root` and return `root`.

    The ledger's latest row for each schema file is written from the file's
    actual bytes, so the repo is green by construction. `drift_*` withholds
    that closing row, leaving the file changed but the ledger un-extended —
    the red case the tripwire must catch.
    """
    graph = root / "graph"
    graph.mkdir(parents=True, exist_ok=True)
    meta_text = METAONTOLOGY.format(version=meta_version)
    onto_text = ONTOLOGY.format(version=onto_version, tag=onto_tag)
    (root / META_REL).write_text(meta_text, encoding="utf-8")
    (root / ONTO_REL).write_text(onto_text, encoding="utf-8")
    meta_fp = hashlib.sha256(meta_text.encode("utf-8")).hexdigest()
    onto_fp = hashlib.sha256(onto_text.encode("utf-8")).hexdigest()

    lines = ["# fixture schema-version ledger: (file, version, sha256)"]
    for version in meta_history:
        lines.append(f"{META_REL} {version} {_dummy_fingerprint(version)}")
    if not drift_meta:
        lines.append(f"{META_REL} {meta_version} {meta_fp}")
    for version in onto_history:
        lines.append(f"{ONTO_REL} {version} {_dummy_fingerprint(version)}")
    if not drift_onto:
        lines.append(f"{ONTO_REL} {onto_version} {onto_fp}")
    (root / LEDGER_REL).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def ledger_entries(root):
    entries = {}
    for line in (root / LEDGER_REL).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        file, version, fingerprint = line.split()
        entries.setdefault(file, []).append((version, fingerprint))
    return entries


def current_state(root, relpath):
    data = (root / relpath).read_bytes()
    text = data.decode("utf-8")
    version_line = next(line for line in text.splitlines()
                        if line.startswith("version:"))
    version = version_line.split(":", 1)[1].strip().strip('"')
    return version, hashlib.sha256(data).hexdigest()


def ledger_problems(root):
    """The tripwire's collate loop: every schema file whose latest ledger
    fingerprint disagrees with the file on disk becomes one problem naming
    the file and the exact line to paste. Empty means green."""
    entries = ledger_entries(root)
    problems = []
    for relpath in SCHEMA_FILES:
        version, fingerprint = current_state(root, relpath)
        history = entries.get(relpath, [])
        if not history:
            problems.append(f"{relpath}: no ledger history at all")
            continue
        last_version, last_fingerprint = history[-1]
        if fingerprint != last_fingerprint:
            problems.append(
                f"{relpath}: the file changed but the ledger was not "
                f"extended — bump the version (currently "
                f"{last_version}, file says {version}) and append:\n"
                f"  {relpath} {version} {fingerprint}")
        elif version != last_version:
            problems.append(
                f"{relpath}: file version {version} disagrees with the "
                f"ledger's latest {last_version}")
    return problems


@pytest.fixture
def green_repo(tmp_path):
    # metaontology: pure semver history; ontology: pre-switch semver rows
    # (history, never rewritten) then plain revision numbers, strictly
    # rising, the latest matching the file on disk.
    return build_repo(
        tmp_path,
        meta_version="0.6.1", meta_history=["0.5.0", "0.6.0"],
        onto_version="30",
        onto_history=["0.5.0", "0.5.1", "28", "29"])


@pytest.fixture
def drifted_repo(tmp_path):
    # the metaontology file moved but no ledger row was appended: the last
    # metaontology row is a stale history entry, not the current bytes.
    return build_repo(
        tmp_path,
        meta_version="0.6.1", meta_history=["0.5.0", "0.6.0"],
        onto_version="30",
        onto_history=["0.5.0", "0.5.1", "28", "29"],
        drift_meta=True)


def test_schema_changes_bump_the_version_and_extend_the_ledger(green_repo):
    assert ledger_problems(green_repo) == []


def test_a_changed_file_with_an_unextended_ledger_is_red(drifted_repo):
    problems = ledger_problems(drifted_repo)
    # the file is named and the failure explained...
    assert any(META_REL in p
               and "the file changed but the ledger was not extended" in p
               for p in problems)
    # ...and the fingerprint to paste is printed verbatim.
    _, fingerprint = current_state(drifted_repo, META_REL)
    assert any(fingerprint in p for p in problems)


def test_versions_follow_their_scheme_and_history_never_repeats(green_repo):
    for relpath, history in ledger_entries(green_repo).items():
        versions = [version for version, _ in history]
        assert len(set(versions)) == len(versions), \
            f"{relpath}: a version appears twice in the ledger"
        if relpath == META_REL:
            for version in versions:
                assert SEMVER.match(version), (relpath, version)
            continue
        # ontology: semver rows are pre-switch history; from the switch
        # on, plain revision numbers, strictly rising (the optional tag
        # is yaml-side display metadata, never a ledger entry)
        revisions = []
        for version in versions:
            match = REVISION.match(version)
            assert match or SEMVER.match(version), (relpath, version)
            if match:
                revisions.append(int(version))
        assert revisions == sorted(set(revisions)), \
            f"{relpath}: revision numbers must strictly increase"
        semver_rows = [v for v in versions if SEMVER.match(v)]
        if semver_rows and revisions:
            assert versions.index(semver_rows[-1]) < \
                versions.index(next(v for v in versions
                                    if REVISION.match(v))), \
                f"{relpath}: a semver row appears after the switch"


def test_the_graph_reports_the_ledgered_version(green_repo):
    # the self-description anchors carry exactly what the ledger says:
    # load the fixture ontology over the fixture metaontology and confirm
    # each reported version matches the file on disk.
    from graph.ontology import load_ontology
    ontology, _ = load_ontology(
        green_repo / "graph" / "ontology.yaml", green_repo,
        metaontology_path=green_repo / "graph" / "metaontology.yaml")
    assert ontology.meta["version"] == current_state(green_repo, META_REL)[0]
    assert str(ontology.raw["version"]) == current_state(
        green_repo, ONTO_REL)[0]
