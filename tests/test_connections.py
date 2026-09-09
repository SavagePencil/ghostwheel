"""Born connected: the per-KB reader and writer, and the MCP scaffold.

A knowledge base is born with its own connections: a query-only
reader for answering (the query-receipts conduct made live queries
load-bearing) and a writer for its working copy, created idempotently
on the DBMS through the admin connection the engine already holds.
Passwords are generated into the gitignored settings file — key names
only in the example — and the project MCP scaffold carries credentials
by environment expansion, never literals, so a session opened in the
repo gets the connections automatically-with-option.
"""

import json

import pytest

import graph.__main__ as main_mod
from graph import connections
from graph.load import read_config


class FakeSystem:
    """Records every statement the verb runs against the system db;
    optionally refuses like a DBMS without user management."""

    def __init__(self, refuse=False):
        self.statements = []
        self.refuse = refuse

    message = "Unsupported administration command"

    def run(self, statement):
        if self.refuse:
            raise RuntimeError(self.message)
        self.statements.append(statement)


@pytest.fixture
def born(tmp_path, monkeypatch):
    """A freshly-born KB with the system-db seam faked."""
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    return target, fake


# -- the users, idempotently -----------------------------------------------


def test_the_verb_creates_reader_and_writer_scoped_to_the_kb(born, capsys):
    target, fake = born
    fake.statements.clear()
    assert main_mod.cmd_connections(target) == 0
    text = " ".join(fake.statements)
    assert "hearth-reader" in text and "hearth-writer" in text
    assert "IF NOT EXISTS" in fake.statements[0]
    # the reader reaches the canon database read-only; the writer, the
    # working copy
    assert any("hearth" in s and "reader" in s.lower()
               for s in fake.statements)
    assert any("hearth-scratch" in s for s in fake.statements)
    # nothing grants the reader a write
    assert not any("WRITE" in s and "hearth-reader" in s
                   for s in fake.statements)
    out = capsys.readouterr().out
    assert "hearth-reader" in out and "hearth-writer" in out


def test_re_runs_never_reset_a_password_unasked(born):
    target, fake = born
    assert main_mod.cmd_connections(target) == 0
    env_before = (target / ".env").read_text(encoding="utf-8")
    fake.statements.clear()
    assert main_mod.cmd_connections(target) == 0
    assert not any("ALTER USER" in s for s in fake.statements)
    assert (target / ".env").read_text(encoding="utf-8") == env_before
    fake.statements.clear()
    assert main_mod.cmd_connections(target, reset_passwords=True) == 0
    assert any("ALTER USER" in s for s in fake.statements)


def test_a_dbms_without_user_management_refuses_plainly(
        tmp_path, monkeypatch, capsys):
    target = tmp_path / "hearth"
    fake = FakeSystem(refuse=True)
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    capsys.readouterr()
    assert main_mod.cmd_connections(target) == 1
    err = capsys.readouterr().err
    assert "Attempted" in err and "Failed due to" in err
    assert "by hand" in err


# -- the settings and the scaffold -----------------------------------------


def test_passwords_live_in_env_and_only_names_in_the_example(born):
    target, _ = born
    env = (target / ".env").read_text(encoding="utf-8")
    assert "NEO4J_READER_USERNAME=hearth-reader" in env
    assert "NEO4J_READER_PASSWORD=" in env
    assert "NEO4J_WRITER_USERNAME=hearth-writer" in env
    reader_pw = [line for line in env.splitlines()
                 if line.startswith("NEO4J_READER_PASSWORD=")][0]
    assert len(reader_pw.split("=", 1)[1]) >= 16  # generated, not blank
    example = (target / ".env.example").read_text(encoding="utf-8")
    assert "NEO4J_READER_PASSWORD=" in example
    for line in example.splitlines():
        if "PASSWORD" in line:
            assert line.endswith("="), f"a password value leaked: {line}"


def test_the_mcp_scaffold_expands_env_and_carries_no_literal(born):
    target, _ = born
    doc = json.loads((target / ".mcp.json").read_text(encoding="utf-8"))
    servers = doc["mcpServers"]
    assert "neo4j" in servers and "neo4j-scratch" in servers
    reader_env = servers["neo4j"]["env"]
    assert reader_env["NEO4J_USERNAME"] == "${NEO4J_READER_USERNAME}"
    assert reader_env["NEO4J_PASSWORD"] == "${NEO4J_READER_PASSWORD}"
    assert servers["neo4j"]["env"]["NEO4J_DATABASE"] == "hearth"
    assert servers["neo4j-scratch"]["env"]["NEO4J_DATABASE"] == \
        "hearth-scratch"
    text = (target / ".mcp.json").read_text(encoding="utf-8")
    env = read_config(target)
    assert env["NEO4J_READER_PASSWORD"] not in text  # never a literal
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()


def test_init_scaffolds_even_when_the_dbms_is_unreachable(
        tmp_path, monkeypatch, capsys):
    target = tmp_path / "hearth"

    def _down(config):
        raise ConnectionError("nobody home")

    monkeypatch.setattr(connections, "_system_runner", _down)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    out = capsys.readouterr().out
    assert (target / ".mcp.json").exists()
    assert "NEO4J_READER_PASSWORD" in \
        (target / ".env").read_text(encoding="utf-8")
    assert "python -m graph connections" in out  # the deferred half named


# -- the field lessons: role names, diagnosis, convergence ----------------


def test_role_names_are_legal_for_every_kb_name():
    # Neo4j forbids hyphens in role names — including the verb's own
    # old "-role" suffix, which failed EVERY name. Users keep their
    # hyphens (legal); roles fold to underscores.
    import re
    for canon in ("emberhold", "tale-of-the-hearth", "hearth"):
        creds = {
            connections.READER_USERNAME_KEY: f"{canon}-reader",
            connections.READER_PASSWORD_KEY: "pw1",
            connections.WRITER_USERNAME_KEY: f"{canon}-writer",
            connections.WRITER_PASSWORD_KEY: "pw2",
        }
        for s in connections.statements(canon, f"{canon}-scratch", creds):
            for role in re.findall(r"ROLE `([^`]+)`", s):
                assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role), \
                    (canon, s)
            if "TO `" in s and "GRANT ROLE" not in s:
                target = s.rsplit("TO `", 1)[1].rstrip("`")
                assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target), s


def test_the_refusal_names_the_real_cause_and_redacts_secrets(
        tmp_path, monkeypatch, capsys):
    cases = [
        ("Role name 'x-reader-role' contains illegal characters. Use "
         "simple ascii characters, numbers and underscores.",
         "illegal", "does not manage users"),
        ("Unsupported administration command",
         "does not manage users", "lacks the right"),
        ("Permission denied executing CREATE USER",
         "lacks the right", "does not manage users"),
    ]
    for exc_text, must_say, must_not_say in cases:
        target = tmp_path / f"kb-{cases.index((exc_text, must_say, must_not_say))}"
        fake = FakeSystem()
        monkeypatch.setattr(connections, "_system_runner",
                            lambda config: fake)
        assert main_mod.cmd_init(target, name=target.name) == 0
        fake.refuse = True
        fake.message = exc_text
        capsys.readouterr()
        assert main_mod.cmd_connections(target) == 1
        err = capsys.readouterr().err
        assert must_say in err, (exc_text, err)
        assert must_not_say not in err, (exc_text, err)
        # the printed statements are runnable and secret-free
        env = (target / ".env").read_text(encoding="utf-8")
        for line in env.splitlines():
            if "PASSWORD=" in line and line.split("=", 1)[1]:
                assert line.split("=", 1)[1] not in err, "password leaked"
        assert "SET PASSWORD '" not in err or "'***'" in err


def test_reset_over_partial_state_converges_and_rotates(born):
    # the field state: users exist, no roles, no grants. The reset run
    # must create what is missing AND rotate the exposed passwords —
    # CREATE ... IF NOT EXISTS before any ALTER, grants idempotent.
    target, fake = born
    fake.statements.clear()
    assert main_mod.cmd_connections(target, reset_passwords=True) == 0
    kinds = [s.split()[0:2] for s in fake.statements]
    first_alter = next(i for i, s in enumerate(fake.statements)
                       if s.startswith("ALTER USER"))
    assert all("IF NOT EXISTS" in s for s in fake.statements
               if s.startswith("CREATE ")), "a CREATE could not converge"
    assert all(not s.startswith("CREATE") for s in
               fake.statements[first_alter:]), "an ALTER preceded a CREATE"
    env = (target / ".env").read_text(encoding="utf-8")
    alter_text = " ".join(s for s in fake.statements
                          if s.startswith("ALTER USER"))
    for line in env.splitlines():
        if line.startswith("NEO4J_READER_PASSWORD="):
            assert line.split("=", 1)[1] in alter_text  # env == DBMS


def test_the_plan_targets_the_reader_the_settings_name(
        tmp_path, monkeypatch):
    # a KB whose settings already name a hand-made reader: the verb
    # grants THAT user, never shadows it with a generated twin
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    env = env.replace("NEO4J_READER_USERNAME=hearth-reader",
                      "NEO4J_READER_USERNAME=keeper_reader")
    (target / ".env").write_text(env, encoding="utf-8")
    fake.statements.clear()
    assert main_mod.cmd_connections(target) == 0
    text = " ".join(fake.statements)
    assert "keeper_reader" in text
    assert "`hearth-reader`" not in text


def test_the_plan_creates_the_databases_it_grants_on(born):
    # a newborn KB has cut no round: neither its canon database nor its
    # working copy need exist yet, and a grant on a missing database
    # refuses — so the plan opens by creating both, idempotently, the
    # same shape restore uses. Born connected holds for exactly the
    # newborn state, rotation included (the ALTERs still run last).
    target, fake = born
    fake.statements.clear()
    assert main_mod.cmd_connections(target, reset_passwords=True) == 0
    first_grant = next(i for i, s in enumerate(fake.statements)
                       if s.startswith("GRANT"))
    heads = fake.statements[:first_grant]
    assert any(s.startswith("CREATE DATABASE `hearth`") and
               "IF NOT EXISTS" in s for s in heads)
    assert any(s.startswith("CREATE DATABASE `hearth-scratch`") and
               "IF NOT EXISTS" in s for s in heads)
    assert any(s.startswith("ALTER USER") for s in fake.statements)


def test_a_declined_default_pair_is_named_never_abandoned(
        tmp_path, monkeypatch, capsys):
    # the settings name a hand-made reader, so the verb declines the
    # per-KB default pair — if such users exist from an earlier run,
    # they are named in the output with ready cleanup statements;
    # silent abandonment is the one wrong answer, and the verb never
    # deletes what it cannot see.
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    env = env.replace("NEO4J_READER_USERNAME=hearth-reader",
                      "NEO4J_READER_USERNAME=keeper_reader")
    (target / ".env").write_text(env, encoding="utf-8")
    capsys.readouterr()
    assert main_mod.cmd_connections(target) == 0
    out = capsys.readouterr().out
    assert "hearth-reader" in out and "DROP USER" in out
    assert "keeper_reader" in out  # the settled name leads


def test_the_example_agrees_with_the_settled_names(tmp_path, monkeypatch):
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    env = env.replace("NEO4J_READER_USERNAME=hearth-reader",
                      "NEO4J_READER_USERNAME=keeper_reader")
    (target / ".env").write_text(env, encoding="utf-8")
    assert main_mod.cmd_connections(target) == 0
    example = (target / ".env.example").read_text(encoding="utf-8")
    assert "NEO4J_READER_USERNAME=keeper_reader" in example
    assert "hearth-reader" not in example


def test_adoption_without_a_password_refuses_before_any_write(
        tmp_path, monkeypatch, capsys):
    # the settings name a hand-made user but carry no password for it:
    # the verb never invents a credential for a user it didn't create —
    # a minted password would reach the scaffold but never the DBMS,
    # and every session would then knock with wrong credentials until
    # the auth rate limit locks the user.
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    env = env.replace("NEO4J_READER_USERNAME=hearth-reader",
                      "NEO4J_READER_USERNAME=keeper_reader")
    env = "\n".join(line for line in env.splitlines()
                    if not line.startswith("NEO4J_READER_PASSWORD=")) + "\n"
    (target / ".env").write_text(env, encoding="utf-8")
    mcp_before = (target / ".mcp.json").read_text(encoding="utf-8")
    fake.statements.clear()
    capsys.readouterr()
    assert main_mod.cmd_connections(target) == 1
    err = capsys.readouterr().err
    assert "keeper_reader" in err and "Failed due to" in err
    assert "--reset-passwords" in err
    assert fake.statements == []  # nothing reached the DBMS
    assert (target / ".mcp.json").read_text(encoding="utf-8") == mcp_before
    assert "NEO4J_READER_PASSWORD=" not in \
        (target / ".env").read_text(encoding="utf-8")


def test_reset_passwords_is_the_sanctioned_adoption_road(
        tmp_path, monkeypatch):
    target = tmp_path / "hearth"
    fake = FakeSystem()
    monkeypatch.setattr(connections, "_system_runner",
                        lambda config: fake)
    assert main_mod.cmd_init(target, name="Hearth") == 0
    env = (target / ".env").read_text(encoding="utf-8")
    env = env.replace("NEO4J_READER_USERNAME=hearth-reader",
                      "NEO4J_READER_USERNAME=keeper_reader")
    env = "\n".join(line for line in env.splitlines()
                    if not line.startswith("NEO4J_READER_PASSWORD=")) + "\n"
    (target / ".env").write_text(env, encoding="utf-8")
    fake.statements.clear()
    assert main_mod.cmd_connections(target, reset_passwords=True) == 0
    env = (target / ".env").read_text(encoding="utf-8")
    [pw_line] = [l for l in env.splitlines()
                 if l.startswith("NEO4J_READER_PASSWORD=")]
    minted = pw_line.split("=", 1)[1]
    assert minted and any(
        s.startswith("ALTER USER `keeper_reader`") and minted in s
        for s in fake.statements)  # env and DBMS agree by construction
