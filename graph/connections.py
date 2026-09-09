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


def statements(canon_db, scratch_db, creds, reset=False):
    """The idempotent user/role/grant plan, in order. CREATE ... IF NOT
    EXISTS never touches an existing password; reset adds the explicit
    ALTERs."""
    reader, writer = usernames(canon_db)
    reader_role, writer_role = f"{reader}-role", f"{writer}-role"
    plan = [
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


def ensure_example(base_dir, canon_db):
    """Key NAMES only — a password value in the example would be a
    leak by construction."""
    path = Path(base_dir) / ".env.example"
    if path.exists():
        return
    reader, writer = usernames(canon_db)
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
    ensure_example(base_dir, canon_db)
    return creds
