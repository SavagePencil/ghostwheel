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


VALIDATION_REPORT_FILE = "validation-report.json"


def graph_summary(graph):
    """The graph's shape as a record: node count, counts per label,
    edge count, placeholders."""
    label_counts = Counter(label for label, _ in graph.nodes)
    return {"nodes": len(graph.nodes),
            "by_label": dict(sorted(label_counts.items())),
            "edges": len(graph.edges),
            "placeholders": sum(1 for props in graph.nodes.values()
                                if props.get("placeholder"))}


def validation_report(findings, graph, base_dir=None):
    """The validation verdict as one record: severity counts, the
    graph's shape (when extraction ran), and one row per finding in
    the record shape — the markdown report is a rendering of this."""
    from .report import record_header
    doc: dict = (record_header(base_dir, "validation-report") if base_dir
                 else {"kind": "validation-report"})
    counts = Counter(f.severity for f in findings)
    doc["counts"] = {"errors": counts.get(ERROR, 0),
                     "warnings": counts.get(WARNING, 0),
                     "info": counts.get(INFO, 0)}
    if graph is not None:
        doc["graph"] = graph_summary(graph)
    doc["findings"] = [f.row(kb=doc.get("kb")) for f in findings]
    return doc


def render_report(doc):
    """The human-readable validation report, rendered FROM the record:
    summary line, graph line, one section per category (the known
    sections in their fixed order, unknown categories after them in
    name order), one table row per finding."""
    lines = ["# Graph validation report", ""]
    counts = doc["counts"]
    lines.append(f"**Summary:** {counts['errors']} errors · "
                 f"{counts['warnings']} warnings · {counts['info']} info")
    if "graph" in doc:
        shape = doc["graph"]
        node_summary = ", ".join(f"{label}: {count}"
                                 for label, count in shape["by_label"].items())
        lines.append(f"**Graph:** {shape['nodes']} nodes ({node_summary}), "
                     f"{shape['edges']} edges, "
                     f"{shape['placeholders']} placeholder nodes")
    lines.append("")

    by_category = {}
    for row in doc["findings"]:
        by_category.setdefault(row["category"], []).append(row)

    known = {str(key) for key, _ in REPORT_SECTIONS}
    sections = [(str(key), title) for key, title in REPORT_SECTIONS] + [
        (key, key) for key in sorted(by_category) if key not in known]

    for key, title in sections:
        section = by_category.get(key)
        if not section:
            continue
        lines.append(f"## {title} ({len(section)})")
        lines.append("")
        lines.append("| Severity | File | Location | Detail |")
        lines.append("| --- | --- | --- | --- |")
        for row in section:
            detail = row["message"].replace("|", "\\|")
            lines.append(f"| {row['severity']} | {row['file']} "
                         f"| {row['location']} | {detail} |")
        lines.append("")

    if not doc["findings"]:
        lines.append("No findings. The graph is clean.")
        lines.append("")
    return "\n".join(lines)


def write_report(findings, graph, path, base_dir=None):
    """Write the markdown report (a rendering of the record) and, when
    the base directory is known, the record itself beside it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = validation_report(findings, graph, base_dir)
    path.write_text(render_report(doc), encoding="utf-8")
    if base_dir is not None:
        from .report import write_record
        write_record(base_dir, VALIDATION_REPORT_FILE, doc)
    return doc
