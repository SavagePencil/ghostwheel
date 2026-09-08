"""Shared scenario for the delta report's golden-parity tests.

Builds one rich changeset that exercises EVERY section and verdict family
the delta report can carry — listings, lint refusals of each class, the
schema ceremony's permitted items and violations, the stitch, and the
roster advisories — plus a clean changeset and the empty delta. The
golden files pinned from this scenario prove the record-first inversion
reproduces the prose byte-for-byte (structure changed, meaning did not).

Storybook domain throughout: keys, pebbles, bells, and scribes.
"""

import json

from graph.delta import (Delta, ceremony_classify, diff, lint, lint_stitch,
                         render_report)
from graph.extract import GraphData, derive, make_edge
from graph.kernel_migrate import fresh_kernel
from graph.ontology import ARCHETYPE_LABEL, ERROR, ontology_from_graph

# The base schema, as canon holds it: three declared concepts and one
# concept-bound label with its three citizens.
CONCEPTS = ("Treasure", "Tool", "Relic")
OBJECT_SPEC = {"values": ["Golden Key", "Plain Pebble", "Old Rope"],
               "concept": "Treasure"}

ADVISORIES = [
    "the registry names 'rituals/summoning.md' but no citizen on this "
    "branch carries it",
    "the registry names 'rituals/warding.md' but no citizen on this "
    "branch carries it",
]


def _copy(graph):
    clone = GraphData()
    for key, props in graph.nodes.items():
        clone.nodes[key] = dict(props)
    clone.edges = list(graph.edges)
    return clone


def build_base(tmp_path):
    """Build the storybook base the graph-native way — the kernel seed,
    the project's schema rows constructed directly, a derivation pass —
    then append the ground edges the scenario mutates."""
    seed, seed_findings = fresh_kernel(tmp_path)
    assert seed is not None, seed_findings
    for concept in CONCEPTS:
        seed.ensure_node(ARCHETYPE_LABEL, concept)
        seed.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, concept,
                                    ARCHETYPE_LABEL, "Ontology"))
        seed.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, concept,
                                    ARCHETYPE_LABEL, "Concept"))
    seed.ensure_node(ARCHETYPE_LABEL, "Object",
                     spec_json=json.dumps(OBJECT_SPEC, sort_keys=True))
    seed.edges.append(make_edge("DECLARED_IN", ARCHETYPE_LABEL, "Object",
                                ARCHETYPE_LABEL, "Ontology"))
    seed.edges.append(make_edge("INSTANCE_OF", ARCHETYPE_LABEL, "Object",
                                ARCHETYPE_LABEL, "Treasure"))
    for name in OBJECT_SPEC["values"]:
        seed.ensure_node("Object", name)
    ontology = ontology_from_graph(seed, tmp_path)
    base, derive_findings = derive(ontology, seed)
    assert not [f for f in derive_findings if f.severity == ERROR], \
        derive_findings
    base.edges.append(make_edge(
        "KEPT_WITH", "Object", "Golden Key", "Object", "Plain Pebble",
        {"trigger": "dawn"}))
    base.edges.append(make_edge(
        "GUARDS", "Object", "Golden Key", "Object", "Plain Pebble"))
    base.edges.append(make_edge(
        "DECLARED_MEMBER_OF", "Object", "Plain Pebble", "Archetype", "Tool",
        {"basis": "kept by the gatekeeper"}))
    return ontology, base


def rich_materials(tmp_path):
    """(base, scratch, changes, advisories) covering every report section
    and every lint/ceremony verdict family — the raw materials, so tests
    can drive either the record path or the legacy string path."""
    _, base = build_base(tmp_path)
    # A ground row already under "Rune", so the scratch's Rune LABEL row
    # below refuses toward the migration charter (a birth needs nothing
    # underneath — that path is covered in test_schema_ceremony).
    base.ensure_node("Rune", "Ancient Mark")
    scratch = _copy(base)

    # -- plain listings ---------------------------------------------------
    scratch.ensure_node("Object", "Silver Bell", from_text="rings at dusk")
    scratch.nodes[("Object", "Plain Pebble")]["weight"] = "light"
    del scratch.nodes[("Object", "Old Rope")]
    scratch.edges = [e for e in scratch.edges
                     if "Old Rope" not in (e.from_name, e.to_name)]
    scratch.edges.append(make_edge(
        "KEPT_WITH", "Object", "Silver Bell", "Object", "Golden Key",
        {"why": "the bell hangs from the key"}))
    scratch.edges = [e for e in scratch.edges
                     if not (e.type == "KEPT_WITH"
                             and e.from_name == "Golden Key")]
    scratch.edges.append(make_edge(
        "KEPT_WITH", "Object", "Golden Key", "Object", "Plain Pebble",
        {"trigger": "dusk"}))
    scratch.edges = [e for e in scratch.edges if e.type != "GUARDS"]

    # -- lint refusals, one per family ------------------------------------
    scratch.ensure_node("[Step]", "Ghost Step")               # machine label
    scratch.ensure_node("Object", None)                     # unnamed node
    scratch.edges.append(make_edge(                         # derived add
        "INSTANCE_OF", "Object", "Silver Bell", "Archetype", "Tool"))
    scratch.edges = [e for e in scratch.edges               # derived change
                     if not (e.type == "INSTANCE_OF"
                             and e.from_name == "Golden Key")]
    scratch.edges.append(make_edge(
        "INSTANCE_OF", "Object", "Golden Key", "Archetype", "Object",
        {"confidence": "high"}))
    scratch.edges.append(make_edge(                         # clean member
        "DECLARED_MEMBER_OF", "Object", "Golden Key", "Archetype", "Tool",
        {"basis": "opens the locked door"}))
    scratch.edges.append(make_edge(                         # no basis
        "DECLARED_MEMBER_OF", "Object", "Silver Bell", "Archetype", "Tool"))
    scratch.edges.append(make_edge(                         # facet target
        "DECLARED_MEMBER_OF", "Object", "Golden Key", "Archetype", "Ordered",
        {"basis": "sorted on the shelf"}))
    scratch.edges.append(make_edge(                         # from archetype
        "DECLARED_MEMBER_OF", "Archetype", "Object", "Archetype", "Tool",
        {"basis": "rosters are not memberships"}))
    # blank the basis on the base's membership edge (paired change)
    scratch.edges = [e for e in scratch.edges
                     if not (e.type == "DECLARED_MEMBER_OF"
                             and e.from_name == "Plain Pebble")]
    scratch.edges.append(make_edge(
        "DECLARED_MEMBER_OF", "Object", "Plain Pebble", "Archetype", "Tool",
        {"basis": ""}))
    scratch.edges.append(make_edge(                         # schema add
        "INSTANCE_OF", "Archetype", "Treasure", "Archetype", "Tool"))
    scratch.edges = [e for e in scratch.edges               # schema removal
                     if not (e.type == "INSTANCE_OF"
                             and e.from_label == "Archetype"
                             and e.from_name == "Tool")]

    # -- the schema ceremony ----------------------------------------------
    scratch.ensure_node("Archetype", "Lore",
                        doc="Old tales carried by wandering scribes")
    scratch.edges.append(make_edge(
        "DECLARED_IN", "Archetype", "Lore", "Source", "Chronicle"))
    scratch.edges.append(make_edge(
        "INSTANCE_OF", "Archetype", "Lore", "Archetype", "Treasure"))
    scratch.ensure_node("Archetype", "Rune", spec_json="{}")   # LABEL row
    scratch.ensure_node("Archetype", "Myth")                   # undeclared
    scratch.nodes[("Archetype", "Tool")]["doc"] = "A thing that does work"
    del scratch.nodes[("Archetype", "Relic")]                  # removal
    scratch.edges = [e for e in scratch.edges
                     if "Relic" not in (e.from_name, e.to_name)]

    changes = diff(base, scratch)
    changes.stitch = [
        make_edge("KEPT_WITH", "Object", "Silver Bell", "Lore", "First Saga",
                  {"why": "the saga names the bell"}),
        make_edge("KEPT_WITH", "Object", "Golden Key",
                  "Object", "Plain Pebble"),
    ]
    return base, scratch, changes, list(ADVISORIES)


def rich_scenario(tmp_path):
    """(changes, violations, ceremony_items, advisories) — the rich
    materials run through the legacy string surfaces, exactly the lists
    cmd_delta assembled before the record inversion."""
    base, scratch, changes, advisories = rich_materials(tmp_path)
    violations = lint(changes, base)
    ceremony_items = ceremony_classify(changes, base)[0]
    violations += lint_stitch(changes, scratch)
    return changes, violations, ceremony_items, advisories


def clean_scenario(tmp_path):
    """(changes, violations, ceremony_items) for a round with nothing to
    refuse — the 'Clean — every addition is a ground fact.' branch."""
    _, base = build_base(tmp_path)
    scratch = _copy(base)
    scratch.ensure_node("Object", "Silver Bell", from_text="rings at dusk")
    scratch.edges.append(make_edge(
        "KEPT_WITH", "Object", "Silver Bell", "Object", "Golden Key"))
    changes = diff(base, scratch)
    violations = lint(changes, base)
    ceremony_items = ceremony_classify(changes, base)[0]
    violations += lint_stitch(changes, scratch)
    return changes, violations, ceremony_items


def legacy_markdown(changes, violations, ceremony_items, advisories=()):
    """Assemble the markdown exactly as cmd_delta does today: the renderer
    plus the advisories section appended after it. The golden files pin
    this text; the record-first path must reproduce it byte-for-byte."""
    report = render_report(changes, violations, ceremony_items)
    if advisories:
        report += (
            "\n## Advisories — the branch's roster, for the record\n\n"
            "These registered program files have no citizen on this "
            "branch yet. A branch mid-rebuild is incomplete by design, "
            "so these do not block its rounds — the roster check "
            "returns to full strength when the branch stands for "
            "succession.\n\n")
        report += "".join(f"- {detail}\n" for detail in advisories)
    return report


def empty_markdown():
    return render_report(Delta(), [])
