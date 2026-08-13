import sys
import textwrap
from pathlib import Path

import pytest

# Make the repo root importable regardless of pytest invocation directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def make_repo(tmp_path):
    """Build a miniature repo: write files from {relative path: content} and
    return (base_dir, ontology_path)."""
    def _make(files, ontology_yaml):
        for relpath, content in files.items():
            path = tmp_path / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(content), encoding="utf-8")
        ontology_path = tmp_path / "graph" / "ontology.yaml"
        ontology_path.parent.mkdir(parents=True, exist_ok=True)
        ontology_path.write_text(textwrap.dedent(ontology_yaml),
                                 encoding="utf-8")
        return tmp_path, ontology_path
    return _make


# The suite is a consuming corpus: it registers the storybook grammar
# module through the engine's registry seam, exactly as any corpus
# registers its grammars before extraction runs. The engine itself
# ships none.
from tests import storybook_grammars  # noqa: E402,F401
