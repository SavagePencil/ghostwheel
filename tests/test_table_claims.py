"""Tables comprehend into claims: each non-empty cell one fact-grain
claim in the domain's own words — subject, property, value, a
fingerprint:position locator, and a rendered sentence that enters the
same census as prose. No cell vocabulary reaches any surface; empty
cells and empty markers yield nothing; provenance is a pointer, never
carried bytes."""

import hashlib

from graph.comprehension import (csv_claims, grid_claims,
                                 markdown_table_claims, read_artifact,
                                 reading_table_claims)

BESTIARY = (b"Beast,Wear,Bite,Knacks\n"
            b"Ox,3,-1,\n"
            b"Wisp,,+2,\"Bound, Faint\"\n")


def test_each_non_empty_cell_yields_one_fact():
    claims = csv_claims(BESTIARY)
    facts = {(c["subject"], c["property"], c["value"]) for c in claims}
    assert facts == {
        ("Beast Ox", "Wear", "3"),
        ("Beast Ox", "Bite", "-1"),
        ("Beast Wisp", "Bite", "+2"),
        ("Beast Wisp", "Knacks", "Bound, Faint"),
    }
    # the sentence speaks only the corpus's words plus minimal grammar
    by_fact = {(c["subject"], c["property"]): c["sentence"]
               for c in claims}
    assert by_fact[("Beast Ox", "Wear")] == "The Wear of Beast Ox is 3."


def test_empty_markers_yield_no_claims():
    claims = csv_claims(b"Gem,Glow,Cost\nChill,\xe2\x80\x94,N/A\nCore,-,5\n")
    assert [(c["subject"], c["property"], c["value"]) for c in claims] \
        == [("Gem Core", "Cost", "5")]


def test_locator_is_fingerprint_and_position_never_content():
    claims = csv_claims(BESTIARY)
    short = hashlib.sha256(BESTIARY).hexdigest()[:12]
    by_fact = {(c["subject"], c["property"]): c["locator"]
               for c in claims}
    assert by_fact[("Beast Ox", "Wear")] == f"{short}:0.1"
    assert by_fact[("Beast Wisp", "Knacks")] == f"{short}:1.3"
    # deterministic: the same bytes recompute the same claims
    assert csv_claims(BESTIARY) == claims
    # changed bytes change the fingerprint — a locator can never
    # silently point into different content
    changed = csv_claims(BESTIARY.replace(b"Ox,3", b"Ox,4"))
    assert all(c["locator"].split(":")[0] != short for c in changed)


def test_key_column_ruling_is_found_by_header_name():
    claims = csv_claims(b"Rank,Beast,Wear\n1,Ox,3\n", key_column="Beast")
    assert {(c["subject"], c["property"], c["value"]) for c in claims} \
        == {("Beast Ox", "Rank", "1"), ("Beast Ox", "Wear", "3")}
    # an unknown ruling falls back to the first column
    fallback = csv_claims(b"Rank,Wear\n1,3\n", key_column="Beast")
    assert [(c["subject"], c["value"]) for c in fallback] \
        == [("Rank 1", "3")]


def test_an_inserted_column_moves_locators_and_no_facts():
    before = csv_claims(b"Beast,Wear\nOx,3\n")
    after = csv_claims(b"Beast,Glow,Wear\nOx,dim,3\n")
    shared_before = {(c["subject"], c["property"], c["value"], c["sentence"])
                     for c in before}
    shared_after = {(c["subject"], c["property"], c["value"], c["sentence"])
                    for c in after if c["property"] != "Glow"}
    assert shared_before == shared_after  # facts are position-free
    new = [c for c in after if c["property"] == "Glow"]
    assert [(c["subject"], c["value"]) for c in new] == [("Beast Ox", "dim")]


def test_rows_missing_a_key_yield_nothing():
    claims = grid_claims(["Beast", "Wear"], [["", "3"], ["—", "4"],
                                             ["Ox", "5"]])
    assert [(c["subject"], c["value"]) for c in claims] \
        == [("Beast Ox", "5")]


def test_markdown_tables_comprehend_only_when_headed():
    text = ("Prose stands.\n\n"
            "| Beast | Wear |\n| --- | --- |\n| Ox | 3 |\n\n"
            "| Bound | Faint |\n| Chill | Core |\n")   # headerless
    claims = markdown_table_claims(text)
    assert [(c["subject"], c["property"], c["value"]) for c in claims] \
        == [("Beast Ox", "Wear", "3")]


def test_markdown_escaped_delimiters_stay_one_cell():
    text = "| Beast | Cry |\n| --- | --- |\n| Ox | low \\| slow |\n"
    claims = markdown_table_claims(text)
    assert claims[0]["value"] == "low | slow"


def test_markdown_locators_carry_the_table_index():
    text = ("| Beast | Wear |\n| --- | --- |\n| Ox | 3 |\n\n"
            "| Gem | Cost |\n| --- | --- |\n| Core | 5 |\n")
    claims = markdown_table_claims(text)
    positions = [c["locator"].split(":")[1] for c in claims]
    assert positions == ["0.0.1", "1.0.1"]


def test_reading_table_claims_walks_the_sealed_reading():
    artifact = (b"# Bestiary\n\nThe marsh keeps its own.\n\n"
                b"{{csv:data/beasts.csv}}\n\n"
                b"## Gems\n\n{{csv:data/gems.csv}}\n")
    reading = read_artifact(artifact, title="Bestiary")
    tables = {"data/beasts.csv": b"Beast,Wear\nOx,3\n"}

    def read_bytes(relpath):
        if relpath not in tables:
            raise OSError(relpath)
        return tables[relpath]

    claims, unreadable = reading_table_claims(reading, read_bytes)
    assert [(c["section"], c["table"], c["subject"], c["value"])
            for c in claims] \
        == [("Bestiary", "data/beasts.csv", "Beast Ox", "3")]
    # an unreadable table is collated, never raised
    assert unreadable == ["data/gems.csv"]


def test_reading_table_claims_honors_per_table_shape_rulings():
    artifact = b"# Bestiary\n\n{{csv:data/beasts.csv}}\n"
    reading = read_artifact(artifact, title="Bestiary")
    claims, _ = reading_table_claims(
        reading, lambda _rel: b"Rank,Beast\n1,Ox\n",
        key_columns={"data/beasts.csv": "Beast"})
    assert [(c["subject"], c["property"], c["value"]) for c in claims] \
        == [("Beast Ox", "Rank", "1")]
