"""A sweep whose verdict depends on reading canon by kernel label
refuses on kernel skew.

A canon whose kernel is behind the engine's keeps its rows under names
the engine no longer looks for; a sweep that proceeds anyway answers
"nothing here" and exits clean — silence read as held, the hazard the
sweeps exist against. So the answer-key sweep, the dependency drift
query, the branch roster, a merge, and the receipt sweep refuse by
name, write no record, and point at kernel-migrate — exactly as
rederive already does. Plain reads keep warn-and-proceed.

Storybook domain, over the driven-kb harness.
"""

import graph.__main__ as main_mod
from graph import export as export_mod
from graph.kernel_migrate import KERNEL_ANCHOR, sweep_skew_refusal
from graph.ontology import ARCHETYPE_LABEL
from graph.report import record_path
from graph.restore import read_export
from tests.test_branch import driven_kb, export_dir  # noqa: F401


def _skew(base):
    canon = read_export(export_dir(base))
    canon.nodes[(ARCHETYPE_LABEL, KERNEL_ANCHOR)]["version"] = "0.16.0"
    export_mod.write_export(canon, export_dir(base))
    return canon


def test_the_refusal_names_both_kernels_and_the_remedy(driven_kb):
    base, _fake, _ = driven_kb
    assert sweep_skew_refusal(read_export(export_dir(base)), "a sweep") \
        is None
    refusal = sweep_skew_refusal(_skew(base), "the answer-key sweep")
    assert refusal is not None
    assert refusal.startswith("Attempted to run the answer-key sweep. "
                              "Failed due to: This canon was built with "
                              "kernel 0.16.0")
    assert "python -m graph kernel-migrate" in refusal
    assert "silence read as held" in refusal


def test_every_verdict_bearing_sweep_refuses_and_writes_nothing(driven_kb,
                                                                capsys):
    base, fake, _ = driven_kb
    # a pocket cut while the kernel was current, so the merge reaches
    # its skew check rather than a missing backup
    assert main_mod.cmd_restore(base, branch="maren", base="clone-of-canon",
                                by="Maren") == 0
    _skew(base)
    for verb, call, report in (
            ("the answer-key sweep", lambda: main_mod.cmd_answer_keys(base),
             "answer-keys-report.json"),
            ("the dependency drift query",
             lambda: main_mod.cmd_dependencies(base),
             "dependencies-report.json"),
            ("the branch roster", lambda: main_mod.cmd_branches(base),
             "branches-report.json"),
            ("the receipt sweep", lambda: main_mod.cmd_receipts(base),
             "receipts-report.json"),
            ("a merge over canon",
             lambda: main_mod.cmd_merge(base, "maren", "canon"),
             "merge-report.json")):
        capsys.readouterr()
        assert call() == 1, verb
        captured = capsys.readouterr()
        assert f"Attempted to run {verb}." in captured.err, verb
        assert "nothing was checked, nothing written" in captured.err
        assert "No answer keys" not in captured.out
        assert "No dependencies" not in captured.out
        assert not record_path(base, report).exists(), report
