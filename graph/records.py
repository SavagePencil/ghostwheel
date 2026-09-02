"""Engine records, assembled from the manual's canon.

The manual is the engine's own knowledge base: its records live as
citizens (a record node carrying a `handle`, its prose riding as section
citizens PART_OF it, section claims PART_OF their section), and this
module renders a record back to prose from the packaged canon export —
no database, pure file parsing. Assembly is structural: a node's body,
then its members by rank. While the prose files still exist, the render
is held byte-identical to them (the parity tests — the flip criterion);
after they retire, the canon is the only source and the golden snapshot
holds the render steady within a version.
"""

from pathlib import Path

from .ontology import KERNEL_PROCEDURE_LABEL
from .restore import read_export

CANON_DIR = Path(__file__).resolve().parent / "engine_docs" / "canon"


def load_canon(canon_dir=CANON_DIR):
    """The packaged canon as a GraphData, or None when no canon ships
    (nothing mirrored yet — callers fall back to the packaged files)."""
    canon_dir = Path(canon_dir)
    if not canon_dir.is_dir():
        return None
    return read_export(canon_dir)


def records(graph):
    """The records the canon carries: handle -> (label, name). A record is
    any citizen wearing a `handle` property — the name a reader asks for
    at the command line."""
    return {props["handle"]: (label, name)
            for (label, name), props in graph.nodes.items()
            if "handle" in props}


def is_conduct(label):
    """Conduct records are kernel Procedures; everything else with a
    handle is a design record."""
    return label == KERNEL_PROCEDURE_LABEL


def render(graph, label, name):
    """Assemble one record to prose: each member's body in rank order,
    members' own members following their body — the containment walk
    that reverses the intake's byte-faithful slicing."""
    members = {}
    for edge in graph.edges:
        if edge.type == "PART_OF":
            members.setdefault((edge.to_label, edge.to_name), []).append(
                (edge.from_label, edge.from_name))

    def assemble(key):
        props = graph.nodes.get(key, {})
        parts = [props.get("body", "")]
        children = sorted(
            members.get(key, ()),
            key=lambda child: (graph.nodes[child].get("rank", 0), child[1]))
        parts.extend(assemble(child) for child in children)
        return "".join(parts)

    return assemble((label, name))
