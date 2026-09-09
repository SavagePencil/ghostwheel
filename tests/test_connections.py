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

    def run(self, statement):
        if self.refuse:
            raise RuntimeError("Unsupported administration command")
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
