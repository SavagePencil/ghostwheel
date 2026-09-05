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

The stamp also names WHICH knowledge base the database belongs to, and
the stamps together are the DBMS's registry of names: every load first
reads the target's stamp, and a database another knowledge base holds
refuses by name before a byte is written — the only way two knowledge
bases sharing a DBMS could otherwise collide (a branch's database is
its bare branch name) is closed at the door. Nothing is ever renamed.
"""

from datetime import datetime, timezone

WORKSPACE_LABEL = "[Workspace]"
STAMP_NAME = "This database"
KB_PROP = "kb"

# What a database can be. `canon` and `branch` hold a line of truth;
# `working-copy` is a round's authoring clone; `inspection` is a
# --from load that cuts no round.
ROLES = ("canon", "working-copy", "branch", "inspection")


def stamp(config, role, base_hash, git_ref="unknown", branch=None,
          kb=None, extra=None):
    """Write the identity stamp into the configured database, replacing
    any prior stamp — a database has exactly one identity at a time.
    `kb` names the knowledge base the database belongs to; `extra`
    carries further in-band facts (a pocket's declaration)."""
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
    if kb is not None:
        props[KB_PROP] = kb
    if extra:
        props.update(extra)
    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    with driver, driver.session(
            database=config["NEO4J_DATABASE"]) as session:
        # The label rides a parameterized labels() check, never a label
        # token: a MATCH on a label the database has not seen yet makes
        # the server emit an unknown-label notification, and the driver
        # prints it raw — internals reaching a designer-facing surface.
        # CREATE below is what births the label, quietly.
        session.run("MATCH (w) WHERE $label IN labels(w) DETACH DELETE w",
                    label=WORKSPACE_LABEL)
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
        # parameterized labels() check — see stamp(): a label token for
        # an unstamped database would spew a raw driver notification
        record = session.run(
            "MATCH (w) WHERE $label IN labels(w) "
            "RETURN properties(w) AS props LIMIT 1",
            label=WORKSPACE_LABEL).single()
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


def held_by_problem(found, kb, database):
    """Judge a database's stamp against the knowledge base about to
    load into it. Returns a designer-facing refusal, or None when the
    database is unstamped (pre-stamp, or made by hand), stamped without
    a knowledge base (an older engine's stamp), or this knowledge
    base's own."""
    if found is None:
        return None
    holder = found.get(KB_PROP)
    if not holder or holder == kb:
        return None
    role = found.get("role") or "database"
    return (
        f"Attempted to load knowledge base '{kb}' into database "
        f"'{database}'. Failed due to: that database identifies itself "
        f"as knowledge base '{holder}''s {role} — loading here would "
        "wipe another knowledge base's line. Pick a name this knowledge "
        "base owns: set NEO4J_DATABASE or NEO4J_SCRATCH_DATABASE in its "
        ".env, or choose another --database or branch name. Nothing is "
        "renamed."
    )


def held_by_other(config, kb):
    """The configured database's refusal when another knowledge base
    holds it, else None. A database that does not exist yet, or cannot
    be read, is nobody's — creation and the load report their own
    faults, so nothing is judged here."""
    try:
        found = read_stamp(config)
    except Exception:
        return None
    return held_by_problem(found, kb, config["NEO4J_DATABASE"])


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
