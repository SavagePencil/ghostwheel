"""Born connected: the per-KB reader and writer, and the MCP scaffold.

A knowledge base is born with its own connections. The query-only
READER answers the designer (the query-receipts conduct made live
queries load-bearing); the WRITER authors the working copy. Both are
created idempotently on the DBMS through the same admin connection
the engine already uses to create databases, their passwords generated
into the gitignored settings file — key names only in the example —
and the project MCP scaffold carries credentials by environment
expansion, never literals, so a session opened in the repo gets the
connections automatically-with-option: the client asks before enabling
a project's servers.
"""

import json
import re
import secrets
from pathlib import Path

READER_USERNAME_KEY = "NEO4J_READER_USERNAME"
READER_PASSWORD_KEY = "NEO4J_READER_PASSWORD"
WRITER_USERNAME_KEY = "NEO4J_WRITER_USERNAME"
WRITER_PASSWORD_KEY = "NEO4J_WRITER_PASSWORD"
MCP_FILE = ".mcp.json"


def _system_runner(config):
    """A runner whose .run() executes one statement against the DBMS's
    system database on the admin connection — the seam the tests fake."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        config["NEO4J_URI"],
        auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]))
    session = driver.session(database="system")

    class _Runner:
        def run(self, statement):
            session.run(statement)

        def close(self):
            session.close()
            driver.close()

    return _Runner()


def usernames(canon_db):
    return f"{canon_db}-reader", f"{canon_db}-writer"


def role_name(username):
    """The user's role, in the only shape the DBMS accepts for roles:
    word characters alone — hyphens are legal in USER names and illegal
    in ROLE names, the verb's first field lesson."""
    folded = re.sub(r"[^0-9A-Za-z_]", "_", username) + "_role"
    return folded if not folded[0].isdigit() else f"kb_{folded}"


def redacted(statement):
    """The statement with any password literal masked — refusal output
    never carries a secret."""
    return re.sub(r"SET PASSWORD '[^']*'", "SET PASSWORD '***'", statement)


def ensure_env(base_dir, canon_db):
    """Make sure the settings file carries the reader/writer keys,
    generating passwords for missing ones. Returns the four values.
    Never rewrites an existing key — a re-run changes nothing."""
    env_file = Path(base_dir) / ".env"
    text = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    have = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            have[key.strip()] = value.strip()
    reader, writer = usernames(canon_db)
    wanted = {
        READER_USERNAME_KEY: reader,
        READER_PASSWORD_KEY: secrets.token_urlsafe(18),
        WRITER_USERNAME_KEY: writer,
        WRITER_PASSWORD_KEY: secrets.token_urlsafe(18),
    }
    missing = {key: value for key, value in wanted.items()
               if not have.get(key)}
    if missing:
        block = "".join(f"{key}={value}\n" for key, value in missing.items())
        text = (text + ("" if text.endswith("\n") or not text else "\n")
                + "\n# This knowledge base's own connections — generated; "
                "keep .env out of source control.\n" + block)
        env_file.write_text(text, encoding="utf-8")
    return {key: have.get(key) or wanted[key] for key in wanted}


def adoption_problems(base_dir):
    """Refusals for a settings file that names a user the verb did not
    create while carrying no password for it. The verb never invents a
    credential for a user it didn't set: a minted password would reach
    the scaffold but never the DBMS, and every session would then knock
    with wrong credentials until the auth rate limit locks the user."""
    env_file = Path(base_dir) / ".env"
    if not env_file.exists():
        return []
    have = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            have[key.strip()] = value.strip()
    problems = []
    for side, user_key, pw_key in (
            ("reader", READER_USERNAME_KEY, READER_PASSWORD_KEY),
            ("writer", WRITER_USERNAME_KEY, WRITER_PASSWORD_KEY)):
        username = have.get(user_key)
        if username and not have.get(pw_key):
            problems.append(
                f"Attempted to scaffold the {side} connection for "
                f"'{username}'. Failed due to: the settings name that "
                f"user but carry no {pw_key} — the engine never invents "
                "a credential for a user it did not create (a minted "
                "password would reach the scaffold but never the DBMS, "
                "and sessions would knock with wrong credentials until "
                "the auth rate limit locks the user). Supply the real "
                f"password as {pw_key} in .env, or run with "
                "--reset-passwords to take ownership of the user's "
                "password.")
    return problems


def rotate_passwords(base_dir):
    """New generated passwords written over the old ones in .env.
    Returns the fresh values (usernames untouched)."""
    env_file = Path(base_dir) / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    fresh = {READER_PASSWORD_KEY: secrets.token_urlsafe(18),
             WRITER_PASSWORD_KEY: secrets.token_urlsafe(18)}
    out = []
    for line in lines:
        key = line.partition("=")[0].strip()
        out.append(f"{key}={fresh[key]}" if key in fresh else line)
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    return fresh


def branch_copy_name(config, branch):
    """The working-copy database a branch's rounds read, by the SAME
    rule the authoring path uses: the KB's own scratch setting (or the
    bare default) suffixed onto the branch — never an assumed name."""
    named = (config.get("NEO4J_SCRATCH_DATABASE") or "").strip()
    return f"{branch}-{named or 'scratch'}"


def pocket_statements(branch, reader, writer, copy=None):
    """The pocket's grant plan: the line's own roles extend over the
    pocket's databases in the main pair's exact shape — the pocket
    canon reads like canon, the pocket scratch writes like scratch.
    The plan creates what it grants on (idempotent, the shape the main
    plan uses), so cut order never matters."""
    reader_role, writer_role = role_name(reader), role_name(writer)
    scratch = copy or f"{branch}-scratch"
    return [
        f"CREATE DATABASE `{branch}` IF NOT EXISTS",
        f"CREATE DATABASE `{scratch}` IF NOT EXISTS",
        f"GRANT ACCESS ON DATABASE `{branch}` TO `{reader_role}`",
        f"GRANT MATCH {{*}} ON GRAPH `{branch}` TO `{reader_role}`",
        f"GRANT ACCESS ON DATABASE `{scratch}` TO `{writer_role}`",
        f"GRANT MATCH {{*}} ON GRAPH `{scratch}` TO `{writer_role}`",
        f"GRANT WRITE ON GRAPH `{scratch}` TO `{writer_role}`",
        f"GRANT NAME MANAGEMENT ON DATABASE `{scratch}` "
        f"TO `{writer_role}`",
    ]


def pocket_revocations(branch, reader, writer, copy=None):
    """Retirement's mirror: the grants leave before the databases drop,
    so a future database under the same name inherits nothing."""
    reader_role, writer_role = role_name(reader), role_name(writer)
    scratch = copy or f"{branch}-scratch"
    return [
        f"REVOKE ACCESS ON DATABASE `{branch}` FROM `{reader_role}`",
        f"REVOKE MATCH {{*}} ON GRAPH `{branch}` FROM `{reader_role}`",
        f"REVOKE ACCESS ON DATABASE `{scratch}` FROM `{writer_role}`",
        f"REVOKE MATCH {{*}} ON GRAPH `{scratch}` FROM `{writer_role}`",
        f"REVOKE WRITE ON GRAPH `{scratch}` FROM `{writer_role}`",
        f"REVOKE NAME MANAGEMENT ON DATABASE `{scratch}` "
        f"FROM `{writer_role}`",
    ]


def named_users(config):
    """(reader, writer) from settings, or (None, None) when the
    knowledge base names no users — then no boundary exists to extend
    and the pocket machinery stays silent."""
    reader = (config.get(READER_USERNAME_KEY) or "").strip()
    writer = (config.get(WRITER_USERNAME_KEY) or "").strip()
    if not reader or not writer:
        return None, None
    return reader, writer


def extend_over_pocket(config, branch):
    """Best-effort at the cut: the boundary follows the pocket. A plain
    note when the DBMS is unreachable — never a failed cut."""
    reader, writer = named_users(config)
    if not reader or not writer:
        return
    copy = branch_copy_name(config, branch)
    plan = pocket_statements(branch, reader, writer, copy=copy)
    try:
        runner = _system_runner(config)
        try:
            for statement in plan:
                runner.run(statement)
        finally:
            close = getattr(runner, "close", None)
            if close:
                close()
    except Exception as exc:
        print(f"Note: the pocket's grants were not extended ({exc}) — "
              f"hand-authoring in '{branch}-scratch' will refuse the "
              "writer until they are. Re-run the cut when the DBMS is "
              "reachable, or grant by hand.")
        return
    print(f"Boundary follows the pocket: '{reader}' reads '{branch}', "
          f"'{writer}' writes '{copy}'.")


def statements(canon_db, scratch_db, creds, reset=False):
    """The idempotent user/role/grant plan, in order. CREATE ... IF NOT
    EXISTS never touches an existing password; reset adds the explicit
    ALTERs."""
    # the plan targets exactly the usernames the settings name — a
    # hand-made reader is granted, never shadowed by a generated twin
    reader = creds[READER_USERNAME_KEY]
    writer = creds[WRITER_USERNAME_KEY]
    reader_role, writer_role = role_name(reader), role_name(writer)
    plan = [
        # a grant on a missing database refuses, and a newborn KB has
        # cut no round yet — the verb creates what it grants on, the
        # same idempotent shape restore uses
        f"CREATE DATABASE `{canon_db}` IF NOT EXISTS",
        f"CREATE DATABASE `{scratch_db}` IF NOT EXISTS",
        f"CREATE USER `{reader}` IF NOT EXISTS "
        f"SET PASSWORD '{creds[READER_PASSWORD_KEY]}' "
        "SET PASSWORD CHANGE NOT REQUIRED",
        f"CREATE USER `{writer}` IF NOT EXISTS "
        f"SET PASSWORD '{creds[WRITER_PASSWORD_KEY]}' "
        "SET PASSWORD CHANGE NOT REQUIRED",
        f"CREATE ROLE `{reader_role}` IF NOT EXISTS",
        f"CREATE ROLE `{writer_role}` IF NOT EXISTS",
        f"GRANT ROLE `{reader_role}` TO `{reader}`",
        f"GRANT ROLE `{writer_role}` TO `{writer}`",
        f"GRANT ACCESS ON DATABASE `{canon_db}` TO `{reader_role}`",
        f"GRANT MATCH {{*}} ON GRAPH `{canon_db}` TO `{reader_role}`",
        f"GRANT ACCESS ON DATABASE `{scratch_db}` TO `{writer_role}`",
        f"GRANT MATCH {{*}} ON GRAPH `{scratch_db}` TO `{writer_role}`",
        f"GRANT WRITE ON GRAPH `{scratch_db}` TO `{writer_role}`",
        # WRITE excludes token creation — a first-of-its-kind label,
        # relationship type, or property key needs NAME MANAGEMENT,
        # and a young KB hits that on nearly everything
        f"GRANT NAME MANAGEMENT ON DATABASE `{scratch_db}` "
        f"TO `{writer_role}`",
    ]
    if reset:
        plan += [
            f"ALTER USER `{reader}` "
            f"SET PASSWORD '{creds[READER_PASSWORD_KEY]}'",
            f"ALTER USER `{writer}` "
            f"SET PASSWORD '{creds[WRITER_PASSWORD_KEY]}'",
        ]
    return plan


def write_mcp(base_dir, canon_db, scratch_db):
    """The project-scoped MCP scaffold: reader on canon, writer on the
    working copy, credentials by environment expansion — never a
    literal. An existing file is kept as-is (the owner's wiring wins).
    Returns True when the file was written."""
    path = Path(base_dir) / MCP_FILE
    if path.exists():
        return False

    def server(username_key, password_key, database):
        return {
            "command": "uvx",
            "args": ["mcp-neo4j-cypher"],
            "env": {
                "NEO4J_URI": "${NEO4J_URI}",
                "NEO4J_USERNAME": "${%s}" % username_key,
                "NEO4J_PASSWORD": "${%s}" % password_key,
                "NEO4J_DATABASE": database,
            },
        }

    doc = {"mcpServers": {
        "neo4j": server(READER_USERNAME_KEY, READER_PASSWORD_KEY, canon_db),
        "neo4j-scratch": server(WRITER_USERNAME_KEY, WRITER_PASSWORD_KEY,
                                scratch_db),
    }}
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return True


def ensure_gitignore(base_dir):
    path = Path(base_dir) / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() \
        if path.exists() else []
    if ".env" not in lines:
        lines.append(".env")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_example(base_dir, canon_db, creds=None):
    """Key NAMES only — a password value in the example would be a
    leak by construction. The usernames documented are the SETTLED
    ones (what .env actually names); an existing example whose
    username lines disagree is reconciled — usernames are not
    secrets, and the scaffold and the verb must agree."""
    path = Path(base_dir) / ".env.example"
    reader, writer = usernames(canon_db)
    if creds:
        reader = creds.get(READER_USERNAME_KEY) or reader
        writer = creds.get(WRITER_USERNAME_KEY) or writer
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        fixed = []
        for line in lines:
            key = line.partition("=")[0].strip()
            if key == READER_USERNAME_KEY:
                fixed.append(f"{READER_USERNAME_KEY}={reader}")
            elif key == WRITER_USERNAME_KEY:
                fixed.append(f"{WRITER_USERNAME_KEY}={writer}")
            else:
                fixed.append(line)
        if fixed != lines:
            path.write_text("\n".join(fixed) + "\n", encoding="utf-8")
        return
    path.write_text(
        "# Copy to .env and fill in; .env stays out of source control.\n"
        "NEO4J_URI=bolt://localhost:7687\n"
        "NEO4J_USERNAME=neo4j\n"
        "NEO4J_PASSWORD=\n"
        f"NEO4J_DATABASE={canon_db}\n"
        f"NEO4J_SCRATCH_DATABASE={canon_db}-scratch\n"
        f"{READER_USERNAME_KEY}={reader}\n"
        f"{READER_PASSWORD_KEY}=\n"
        f"{WRITER_USERNAME_KEY}={writer}\n"
        f"{WRITER_PASSWORD_KEY}=\n",
        encoding="utf-8")


def scaffold(base_dir, canon_db, scratch_db):
    """Everything that needs no DBMS: env keys (passwords generated),
    the MCP file, the gitignore line, the example. Returns the creds."""
    creds = ensure_env(base_dir, canon_db)
    write_mcp(base_dir, canon_db, scratch_db)
    ensure_gitignore(base_dir)
    ensure_example(base_dir, canon_db, creds)
    return creds
