"""Run the full extraction and turn findings into a human-readable report.

Severity contract: 'error' means the ontology or a source file is broken and
loading is blocked (non-zero exit). 'warning'/'info' are data findings — they
never block, so branch exploration always works.
"""

from collections import Counter
from pathlib import Path

from .answer_keys import check as check_answer_keys
from .extract import extract
from .ontology import ERROR, WARNING, INFO, Category, Finding, load_ontology

REPORT_SECTIONS = [
    (Category.DANGLING_REF, "Dangling references"),
    (Category.ENUM_VIOLATION, "Enum violations"),
    (Category.DUPLICATE_KEY, "Duplicate keys"),
    (Category.EMPTY_KEY, "Empty keys"),
    (Category.UNPARSED_CELL, "Unparsed cells (kept verbatim)"),
    (Category.TYPE_CONVERSION, "Type conversion problems"),
    (Category.CATALOG_VIOLATION, "Catalog violations"),
    (Category.OVERLAY, "Overlay problems"),
    (Category.ONTOLOGY, "Ontology problems"),
    (Category.UNMAPPED_CSV, "Files not referenced by any declaration (owner TODO)"),
    (Category.ANSWER_KEY, "Answer-key drift (programs vs approved tables)"),
]


def run(base_dir, ontology_path=None):
    """Returns (ontology, graph, findings)."""
    base_dir = Path(base_dir)
    ontology_path = ontology_path or base_dir / "graph" / "ontology.yaml"
    ontology, findings = load_ontology(ontology_path, base_dir)
    if ontology is None:
        return None, None, findings
    if any(f.severity == ERROR for f in findings):
        # The severity contract above: an ERROR means the ontology or a
        # source file is broken. Extracting anyway can only crash far
        # from the cause — return the collated refusals instead, and say
        # that later phases were skipped so their findings aren't a
        # surprise on the re-run.
        findings.append(Finding(
            INFO, Category.ONTOLOGY, str(ontology_path), "-",
            "extraction skipped — fix the load errors above, then re-run "
            "to surface extraction and answer-key findings"))
        return ontology, None, findings
    graph, extract_findings = extract(ontology)
    findings.extend(extract_findings)
    findings.extend(unmapped_artifacts(ontology))
    findings.extend(check_answer_keys(ontology))
    return ontology, graph, findings


def unmapped_artifacts(ontology):
    # bootstrap-era sweep; retires with the sources and is not part of the
    # split surface (the engine split). Walks every declared content root and reports
    # each file no declaration consumes, regardless of extension — the
    # owner triages what the graph has not yet mapped.
    referenced = ontology.referenced_files()
    findings = []
    seen = set()
    for root in ontology.content_roots():
        root_dir = ontology.base_dir / root
        if not root_dir.is_dir():
            continue  # a WARNING already surfaced at load
        for path in sorted(root_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ontology.base_dir).as_posix()
            if rel in referenced or rel in seen:
                continue
            seen.add(rel)
            findings.append(Finding(
                INFO, Category.UNMAPPED_CSV, rel, "-",
                "under a content root but not referenced by any declaration "
                "(see the TODO block in ontology.yaml)"))
    return findings


def summarize(findings):
    counts = Counter(f.severity for f in findings)
    return (f"{counts.get(ERROR, 0)} errors · "
            f"{counts.get(WARNING, 0)} warnings · "
            f"{counts.get(INFO, 0)} info")


def has_errors(findings):
    return any(f.severity == ERROR for f in findings)


def write_report(findings, graph, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Graph validation report", ""]
    lines.append(f"**Summary:** {summarize(findings)}")
    if graph is not None:
        label_counts = Counter(label for label, _ in graph.nodes)
        placeholder_count = sum(
            1 for props in graph.nodes.values() if props.get("placeholder"))
        node_summary = ", ".join(
            f"{label}: {count}" for label, count in sorted(label_counts.items()))
        lines.append(f"**Graph:** {len(graph.nodes)} nodes ({node_summary}), "
                     f"{len(graph.edges)} edges, "
                     f"{placeholder_count} placeholder nodes")
    lines.append("")

    by_category = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)

    known = {key for key, _ in REPORT_SECTIONS}
    sections = list(REPORT_SECTIONS) + [
        (key, key) for key in sorted(by_category) if key not in known]

    for key, title in sections:
        section = by_category.get(key)
        if not section:
            continue
        lines.append(f"## {title} ({len(section)})")
        lines.append("")
        lines.append("| Severity | File | Location | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for finding in section:
            detail = finding.detail.replace("|", "\\|")
            lines.append(f"| {finding.severity} | {finding.file} "
                         f"| {finding.location} | {detail} |")
        lines.append("")

    if not findings:
        lines.append("No findings. The graph is clean.")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
