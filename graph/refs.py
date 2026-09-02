"""CitizenRef — the engine's one way to address a citizen.

Identity is the (knowledge base, label, name) composite, by deliberate
doctrine: renames are refused under the migration charter, so the
composite IS a stable id — no opaque identifiers, no internal database
ids on any surface. A branch, when present, qualifies WHICH line of
truth a reference was read from; it is not part of who the citizen is
(a citizen born on a branch re-addresses to the default line when
succession lands the branch).

Every machine surface serializes citizens through these structs — the
delta report's verdict subjects, the attribution census's homes, and
every surface built after them — so a client reads one shape
everywhere. Serialized rows carry the knowledge base (and branch, off
the default line) whenever the serializer knows the line it is
serving: a row extracted from its response still knows where it came
from.

The knowledge base's own name is declared on the graph, as a property
on the Ontology anchor — it travels with the committed backup, and a
canon that has not yet adopted a name falls back to its base
directory's basename (readable, but not promised stable).
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .ontology import ARCHETYPE_LABEL

# The (Archetype, 'Ontology') anchor: the canon's identity citizen —
# schema version, content fingerprint, and the declared KB name.
ONTOLOGY_ANCHOR = "Ontology"
KB_NAME_PROP = "kb_name"


@dataclass(frozen=True)
class CitizenRef:
    """A citizen, by its graph identity. ``name`` may be None when the
    verdict is precisely that the node has no name yet."""
    label: str
    name: object = None

    def row(self, kb=None, branch=None):
        doc = {"kind": "citizen", "label": self.label, "name": self.name}
        if kb is not None:
            doc["kb"] = kb
        if branch is not None:
            doc["branch"] = branch
        return doc

    def token(self, kb, branch=None):
        """An opaque single-string form of the composite, for clients
        that want one — a content hash, derived and never stored. If
        the migration charter ever admits renames, this method is the
        single seam where identity gets redefined."""
        material = "\x1f".join(
            [kb, branch or "", self.label, str(self.name)])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConnectionRef:
    """A connection, by type and endpoints."""
    type: str
    source: CitizenRef
    target: CitizenRef

    def row(self, kb=None, branch=None):
        doc = {"kind": "connection", "type": self.type,
               "from": {"label": self.source.label,
                        "name": self.source.name},
               "to": {"label": self.target.label,
                      "name": self.target.name}}
        if kb is not None:
            doc["kb"] = kb
        if branch is not None:
            doc["branch"] = branch
        return doc


def connection_ref(edge):
    """ConnectionRef from an extract.Edge (or anything edge-shaped)."""
    return ConnectionRef(edge.type,
                         CitizenRef(edge.from_label, edge.from_name),
                         CitizenRef(edge.to_label, edge.to_name))


def kb_name(graph, base_dir):
    """The knowledge base's name: the Ontology anchor's declared name
    when the canon has adopted one, else the base directory's
    basename."""
    anchor = graph.nodes.get((ARCHETYPE_LABEL, ONTOLOGY_ANCHOR)) or {}
    return anchor.get(KB_NAME_PROP) or Path(base_dir).resolve().name


def kb_name_from_export(base_dir, branch=None):
    """The knowledge base's name read straight from a committed backup,
    for callers that never load the graph. Same rule as ``kb_name``:
    declared name first, basename fallback (including when the backup
    is missing or unreadable — a name is always available)."""
    import json

    from .proposal import export_dir
    nodes_path = export_dir(base_dir, branch) / "nodes.jsonl"
    try:
        with open(nodes_path, encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("label") == ARCHETYPE_LABEL \
                        and record.get("name") == ONTOLOGY_ANCHOR:
                    declared = (record.get("properties")
                                or {}).get(KB_NAME_PROP)
                    if declared:
                        return declared
                    break
    except (OSError, ValueError):
        pass
    return Path(base_dir).resolve().name
