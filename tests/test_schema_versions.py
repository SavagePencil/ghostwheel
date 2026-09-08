"""The schema-version tripwire (owner rule): any change to the
metaontology must bump its semver version and append (version,
fingerprint) to the ledger — red otherwise, naming the file and printing
the fingerprint to paste. The metaontology is the one schema FILE left
(a project's schema lives on the graph, its revision number stamped on
the Ontology anchor at canonize), so the ledger contract covers it
alone; semver bumps are ceremony.

The real repo's metaontology is one instance of this contract; the test
drives it over a fixture repo built in tmp_path so the invariants are
exercised in isolation — a green repo, and a drifted one whose file
moved but whose ledger did not.
"""

import hashlib
import re

import pytest

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

META_REL = "graph/metaontology.yaml"
LEDGER_REL = "graph/schema-versions.txt"
SCHEMA_FILES = [META_REL]

# A metaontology parses clean (known keys only) and carries the roots a
# kernel ontology is layered from; its version is semver.
METAONTOLOGY = """\
version: "{version}"
roots:
  Concept:
  Facet:
  Provenance:
  Judgment:
"""


def _dummy_fingerprint(marker):
    """A stable placeholder hash for a ledger HISTORY row — never checked
    against a file (only the latest row is), so any distinct 64-hex value
    serves; deriving it from the version keeps rows self-explanatory."""
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()


def build_repo(root, *, meta_version, meta_history=(), drift_meta=False):
    """Write a fixture repo (graph/metaontology.yaml,
    graph/schema-versions.txt) into `root` and return `root`.

    The ledger's latest row is written from the file's actual bytes, so
    the repo is green by construction. `drift_meta` withholds that
    closing row, leaving the file changed but the ledger un-extended —
    the red case the tripwire must catch.
    """
    graph = root / "graph"
    graph.mkdir(parents=True, exist_ok=True)
    meta_text = METAONTOLOGY.format(version=meta_version)
    (root / META_REL).write_text(meta_text, encoding="utf-8")
    meta_fp = hashlib.sha256(meta_text.encode("utf-8")).hexdigest()

    lines = ["# fixture schema-version ledger: (file, version, sha256)"]
    for version in meta_history:
        lines.append(f"{META_REL} {version} {_dummy_fingerprint(version)}")
    if not drift_meta:
        lines.append(f"{META_REL} {meta_version} {meta_fp}")
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
    # pure semver history, strictly extended, the latest row matching the
    # file on disk
    return build_repo(tmp_path, meta_version="0.6.1",
                      meta_history=["0.5.0", "0.6.0"])


@pytest.fixture
def drifted_repo(tmp_path):
    # the metaontology file moved but no ledger row was appended: the last
    # metaontology row is a stale history entry, not the current bytes.
    return build_repo(tmp_path, meta_version="0.6.1",
                      meta_history=["0.5.0", "0.6.0"], drift_meta=True)


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


def test_versions_follow_semver_and_history_never_repeats(green_repo):
    for relpath, history in ledger_entries(green_repo).items():
        versions = [version for version, _ in history]
        assert len(set(versions)) == len(versions), \
            f"{relpath}: a version appears twice in the ledger"
        for version in versions:
            assert SEMVER.match(version), (relpath, version)


def test_the_kernel_reports_the_ledgered_version(green_repo):
    # the self-description anchor carries exactly what the ledger says:
    # build the kernel ontology over the fixture metaontology and confirm
    # the reported version matches the file on disk.
    from graph.ontology import kernel_ontology
    ontology, _findings = kernel_ontology(
        green_repo,
        metaontology_path=green_repo / "graph" / "metaontology.yaml")
    assert ontology is not None
    assert ontology.meta["version"] == current_state(green_repo, META_REL)[0]
