"""Engine-generic cell/prose parsers: they never raise on messy input,
returning what they could parse. Only vocabulary-free machinery lives
here; corpus-specific grammars live behind the grammar registry and are
not exercised by this file."""

from graph import parsers


class TestSplitMulti:
    def test_plain_list(self):
        assert parsers.split_multi("Glide, Perch") == ["Glide", "Perch"]

    def test_empty_markers(self):
        for marker in ["", "—", "-", "N/A", None, "  "]:
            assert parsers.split_multi(marker) == []

    def test_single_value_with_parens(self):
        assert parsers.split_multi("Can't Fly (Indoors)") == ["Can't Fly (Indoors)"]


class TestParseInt:
    def test_signed(self):
        assert parsers.parse_int("+5") == (5, True)
        assert parsers.parse_int("-4") == (-4, True)
        assert parsers.parse_int("0") == (0, True)

    def test_empty(self):
        assert parsers.parse_int("—") == (None, True)
        assert parsers.parse_int("") == (None, True)

    def test_garbage(self):
        assert parsers.parse_int("+2x") == (None, False)


class TestParseFloat:
    def test_decimals(self):
        assert parsers.parse_float("2.0") == (2.0, True)
        assert parsers.parse_float("0.5") == (0.5, True)
        assert parsers.parse_float("-.75") == (-0.75, True)
        assert parsers.parse_float("+1.5") == (1.5, True)
        assert parsers.parse_float("3") == (3.0, True)

    def test_empty(self):
        assert parsers.parse_float("—") == (None, True)
        assert parsers.parse_float("") == (None, True)
        assert parsers.parse_float(None) == (None, True)

    def test_garbage(self):
        assert parsers.parse_float("x2.0") == (None, False)


class TestParseBool:
    def test_truthy(self):
        for token in ["Y", "y", "Yes", "TRUE", "1"]:
            assert parsers.parse_bool(token) == (True, True)

    def test_empty_is_false(self):
        # A total boolean: empty reads as False, not unknown.
        for marker in ["", "—", "-", "N/A", None, "  "]:
            assert parsers.parse_bool(marker) == (False, True)

    def test_falsy_tokens(self):
        for token in ["N", "no", "False", "0"]:
            assert parsers.parse_bool(token) == (False, True)

    def test_check_and_ballot_marks(self):
        for token in ["✓", "✔"]:
            assert parsers.parse_bool(token) == (True, True)
        for token in ["✗", "✘"]:
            assert parsers.parse_bool(token) == (False, True)

    def test_garbage(self):
        assert parsers.parse_bool("maybe") == (None, False)


class TestMarkdownSections:
    DOC = """\
Intro text before any heading is ignored.

## Turn Order

Overview paragraph.

### Grade Checks

Compare each Beast's current Grade.

#### Example 1

A Gryphon takes a turn.
"""

    def test_sections_split_per_heading(self):
        sections = parsers.markdown_sections(self.DOC)
        assert [h for h, _ in sections] == [
            "Turn Order", "Grade Checks", "Example 1"]
        assert "Overview paragraph." in sections[0][1]
        assert "current Grade" in sections[1][1]

    def test_preamble_ignored_and_empty_doc(self):
        assert parsers.markdown_sections("no headings here") == []
        assert parsers.markdown_sections("") == []

    def test_outline_preserves_levels(self):
        outline = parsers.markdown_outline(self.DOC)
        assert [(level, heading) for level, heading, _ in outline] == [
            (2, "Turn Order"), (3, "Grade Checks"), (4, "Example 1")]
        # the level-blind wrapper is exactly the outline minus levels
        assert parsers.markdown_sections(self.DOC) == [
            (heading, body) for _, heading, body in outline]


class TestMentionMatches:
    def test_letter_boundaries(self):
        body = "The Brightly lit lamp stays Bright, not merely Faint."
        assert parsers.mention_matches(body, ["Bright", "Faint", "Blazing"]) \
            == ["Bright", "Faint"]

    def test_names_with_punctuation(self):
        body = "Grants Double Leap and Can't Fly (Indoors) rules apply."
        assert parsers.mention_matches(
            body, ["Double Leap", "Can't Fly (Indoors)"]) \
            == ["Double Leap", "Can't Fly (Indoors)"]

    def test_case_sensitive(self):
        assert parsers.mention_matches("the spark of things", ["Spark"]) == []
