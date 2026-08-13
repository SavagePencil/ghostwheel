"""The check-file header contract: `// expect: empty` marks assertions."""

from graph.__main__ import parse_check


def test_assertion_directive():
    description, expect_empty = parse_check(
        "// expect: empty\n// Every Thing must Frob.\nMATCH (n) RETURN n")
    assert expect_empty
    assert description == "Every Thing must Frob."


def test_informational_default():
    description, expect_empty = parse_check(
        "// Findings dashboard.\nMATCH (n) RETURN n")
    assert not expect_empty
    assert description == "Findings dashboard."


def test_no_header_falls_back_to_name():
    description, expect_empty = parse_check("MATCH (n) RETURN n", "my-check")
    assert not expect_empty
    assert description == "my-check"


def test_agnostic_checks_classify_as_intended():
    """A batch of check files: `// expect: empty` marks the assertions,
    everything else is an informational finding report."""
    checks = {
        "grade-consistency":
            "// expect: empty\n// Every Grade ladder must be ordered.\n"
            "MATCH (n) RETURN n",
        "knacks-without-spark":
            "// expect: empty\n// Every Knack must name a Spark cost.\n"
            "MATCH (n) RETURN n",
        "placeholders": "// Placeholder census.\nMATCH (n) RETURN n",
        "orphans": "// Orphan nodes.\nMATCH (n) RETURN n",
    }
    classified = {stem: parse_check(text)[1]
                  for stem, text in checks.items()}
    assert classified["grade-consistency"] is True
    assert classified["knacks-without-spark"] is True
    assert classified["placeholders"] is False
    assert classified["orphans"] is False
