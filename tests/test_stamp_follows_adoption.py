"""The stamp follows the adoption.

A knowledge base may declare its own name through a gated round (the
one non-doc property edit the ceremony admits). The databases of that
same line — its canon, its working copies — still carry stamps written
under the former name, and a holder check that judges by name alone
would read the line as another knowledge base's and refuse to land the
very round that renames it. The same-line key is the stamp's base
hash: an identity this line has ever held (the chained log's befores
and afters, plus the committed backup's own) proves the database was
cut from this line, just before the name moved. Another knowledge
base's database still refuses by name, unchanged; a same-line
acceptance is read aloud, never silent.

Storybook domain, over the driven-kb harness.
"""

import graph.__main__ as main_mod
from graph import refs as refs_mod
from graph.extract import GraphData
from graph.ontology import ARCHETYPE_LABEL
from graph.proposal import (base_identity, export_dir, line_identities,
                            read_applied_log)
from graph.restore import read_export
from graph.workspace import adoption_note, held_by_problem
from tests.test_branch import driven_kb  # noqa: F401


def _stamp(fake, name):
    return fake.read_stamp({"NEO4J_DATABASE": name})


def _adopt_name(base, fake, new_name):
    """Cut a working copy and author the naming round: the Ontology
    anchor takes the knowledge base's declared name."""
    assert main_mod.cmd_restore(base, database="scratch") == 0
    authored = fake.databases["scratch"]
    authored.nodes[(ARCHETYPE_LABEL, refs_mod.ONTOLOGY_ANCHOR)][
        refs_mod.KB_NAME_PROP] = new_name
    assert main_mod.cmd_delta(base, None) == 0
    assert main_mod.cmd_approve(base, "owner") == 0


# -- the judge -------------------------------------------------------------


def test_same_line_key_is_the_base_hash_another_kb_still_refuses():
    former = {"role": "canon", "base_hash": "abc", "kb": "hearth"}
    # the same line under its former name: an identity the line has held
    assert held_by_problem(former, "emberhold", "neo4j",
                           same_line={"abc"}) is None
    # a base hash the line never held is another knowledge base's —
    # the refusal is the unchanged one, by name
    problem = held_by_problem(former, "emberhold", "neo4j",
                              same_line={"zzz"})
    assert problem is not None
    assert "knowledge base 'hearth''s canon" in problem
    assert "Nothing is renamed" in problem
    # no key offered: judged by name alone, as ever
    assert held_by_problem(former, "emberhold", "neo4j") is not None
    assert held_by_problem(former, "hearth", "neo4j") is None


def test_the_acceptance_is_read_aloud_never_silently():
    former = {"role": "canon", "base_hash": "abc", "kb": "hearth",
              "database": "neo4j"}
    note = adoption_note(former, "emberhold")
    assert note is not None
    assert "followed the knowledge base to its adopted name" in note
    assert "'hearth'" in note and "'emberhold'" in note
    # an ordinary own-name load has nothing to read aloud
    assert adoption_note(former, "hearth") is None
    assert adoption_note(None, "emberhold") is None


# -- the line's recorded identities ----------------------------------------


def test_line_identities_are_the_log_s_and_the_backup_s(driven_kb):
    base, fake, _ = driven_kb
    backup = base_identity(read_export(export_dir(base)))
    # genesis: no round applied yet — the backup's identity alone
    assert line_identities(base) == {backup}
    # a line with no home at all holds no identities
    assert line_identities(base, branch="never-cut") == set()
    # after an applied round: every before and after, plus the backup's
    assert main_mod.cmd_restore(base) == 0
    _adopt_name(base, fake, "emberhold")
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    (_, _, before, after, _, _), = read_applied_log(base)
    now = base_identity(read_export(export_dir(base)))
    assert line_identities(base) == {before, after, now}


# -- the naming round lands on its own canon -------------------------------


def test_the_naming_round_lands_on_the_line_s_own_stamped_canon(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    former = refs_mod.kb_name(read_export(export_dir(base)), base)
    assert main_mod.cmd_restore(base) == 0  # canon stamped, former name
    assert _stamp(fake, "neo4j")["kb"] == former
    _adopt_name(base, fake, "emberhold")
    capsys.readouterr()
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    out = capsys.readouterr().out
    assert "followed the knowledge base to its adopted name" in out
    stamp = _stamp(fake, "neo4j")
    assert stamp["kb"] == "emberhold"
    assert stamp["base_hash"] == base_identity(
        read_export(export_dir(base)))


def test_the_old_working_copy_re_cuts_under_the_adopted_name(
        driven_kb, capsys):
    base, fake, _ = driven_kb
    assert main_mod.cmd_restore(base) == 0
    _adopt_name(base, fake, "emberhold")  # scratch stamped, former name
    assert main_mod.cmd_canonize(base, None, apply=True) == 0
    capsys.readouterr()
    assert main_mod.cmd_restore(base, database="scratch") == 0
    out = capsys.readouterr().out
    assert "followed the knowledge base to its adopted name" in out
    assert _stamp(fake, "scratch")["kb"] == "emberhold"
    # an ordinary re-cut under the standing name reads nothing aloud
    assert main_mod.cmd_restore(base, database="scratch") == 0
    assert "followed the knowledge base" not in capsys.readouterr().out


def test_another_knowledge_base_s_database_still_refuses(driven_kb, capsys):
    base, fake, _ = driven_kb
    fake.databases["theirs"] = GraphData()
    fake.stamp({"NEO4J_DATABASE": "theirs"}, "working-copy", "zzz",
               kb="nightbell")
    calls = list(fake.load_calls)
    assert main_mod.cmd_restore(base, database="theirs") == 1
    assert "knowledge base 'nightbell''s working-copy" in \
        capsys.readouterr().err
    assert fake.load_calls == calls
