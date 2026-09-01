"""Workspace identity: every database says what it is, in-band.

A stamp node rides each database the engine creates — canon, working
copy, branch, inspection load — answering "what am I, built from
what?" from inside the database itself, so the answer travels WITH
the database instead of living in a chat message or a file beside it.
The stamp describes the DATABASE, never the canon it holds: every
read-back path strips it before diffing, drilling, or exporting, and
it is invisible to the ceremony.

The round machinery checks the stamp before trusting a working copy:
when several knowledge bases share one DBMS, diffing one KB's canon
against another KB's working copy — or against a copy cut for a round
that has since closed — refuses with a plain answer instead of
producing a surreal changeset. A database cut before this stamp
existed carries none and is let through with a note; only a
MISMATCHED identity refuses.
"""

from datetime import datetime, timezone

WORKSPACE_LABEL = "[Workspace]"
STAMP_NAME = "This database"

# What a database can be. `canon` and `branch` hold a line of truth;
# `working-copy` is a round's authoring clone; `inspection` is a
# --from load that cuts no round.
ROLES = ("canon", "working-copy", "branch", "inspection")


def stamp(config, role, base_hash, git_ref="unknown", branch=None):
    """Write the identity stamp into the configured database, replacing
    any prior stamp — a database has exactly one identity at a time."""
    from neo4j import GraphDatabase  # deferred: only DB paths need it

    assert role in ROLES, role
    props = {
        "role": role,
        "base_hash": base_hash,
        "git_ref": git_ref,
        "database": config["NEO4J_DATABASE"],
        "stamped_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    }
    if branch is not None:
        props["branch"] = branch
    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    with driver, driver.session(
            database=config["NEO4J_DATABASE"]) as session:
        session.run(f"MATCH (w:`{WORKSPACE_LABEL}`) DETACH DELETE w")
        session.run(
            f"CREATE (w:`{WORKSPACE_LABEL}` {{name: $name}}) SET w += $props",
            name=STAMP_NAME, props=props)


def read_stamp(config):
    """The configured database's identity, or None when it carries no
    stamp (a database cut before the stamp existed, or made by hand)."""
    from neo4j import GraphDatabase  # deferred: only DB paths need it

    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    with driver, driver.session(
            database=config["NEO4J_DATABASE"]) as session:
        record = session.run(
            f"MATCH (w:`{WORKSPACE_LABEL}`) "
            "RETURN properties(w) AS props LIMIT 1").single()
    return dict(record["props"]) if record else None


def strip(graph):
    """Drop the stamp from a graph read back out of a database. Identity
    rides the database, never the canon it holds — the drill, the diff,
    and the export all see the graph as if no stamp existed."""
    graph.nodes = {key: props for key, props in graph.nodes.items()
                   if key[0] != WORKSPACE_LABEL}
    graph.edges = [edge for edge in graph.edges
                   if WORKSPACE_LABEL not in (edge.from_label,
                                              edge.to_label)]
    return graph


def identity_problem(found, pinned_base_hash, database):
    """Judge a working copy's stamp against the round it claims to serve.
    Returns a designer-facing refusal message, or None when the copy is
    the round's own. A missing stamp is NOT a problem (pre-stamp
    databases exist); the caller may note it."""
    if found is None:
        return None
    role = found.get("role")
    if role not in ("working-copy", "branch"):
        return (
            f"Attempted to run the round against database '{database}'. "
            f"Failed due to: that database identifies itself as "
            f"'{role}', not a working copy — running a round against it "
            "would author into a line of truth. Cut a working copy "
            f"first (python -m graph restore --database <copy-name>)."
        )
    if pinned_base_hash and found.get("base_hash") != pinned_base_hash:
        theirs = (found.get("base_hash") or "unknown")[:12]
        ours = pinned_base_hash[:12]
        return (
            f"Attempted to run the round against database '{database}'. "
            f"Failed due to: that database identifies itself as a "
            f"working copy cut from base {theirs}, but this round's "
            f"pinned base is {ours} — it is another knowledge base's "
            "copy, or a copy from a round that has since closed. Re-cut "
            f"the working copy (python -m graph restore --database "
            f"{database})."
        )
    return None
