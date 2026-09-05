"""Canon attribution: the source ladder, verdict semantics, the earned
flag, and the whole-book unit — pure logic over GraphData plus the
roundtrip harness's fixture patterns."""

import json

from graph.attribution import (ATTRIBUTED, CANON_GAP, INVENTION,
                               PROPERTIES, PROSE, RECEIPT, CanonIndex,
                               census, census_claims, render_census)
from graph.extract import GraphData, make_edge


def canon():
    g = GraphData()
    g.ensure_node("Terrain", "Bog", defense_mod=-2,
                  from_text="A Bog Beast suffers -2 to defense.")
    g.ensure_node("Knack", "Fading Step",
                  description="Beasts may need to perform a Fading Step "
                              "Knack to keep their footing while leaving "
                              "the mire.")
    g.ensure_node("Archetype", "Bravery",
                  doc="Bravery measures a Beast's will to keep going "
                      "when the tale turns against it.")
    return g


def test_ladder_prefers_structured_over_receipt_over_prose():
    index = CanonIndex(canon())
    first = index.attribute("Bog imposes -2 to defense.")
    assert first.verdict == ATTRIBUTED and first.rung == PROPERTIES
    assert ("Terrain", "Bog") in first.citizens
    receipt = index.attribute("A Bog Beast suffers -2 to defense.")
    # the receipt sentence ALSO matches rung 1 (name + value present) —
    # the ladder stops at the strongest home
    assert receipt.rung == PROPERTIES
    soup = index.attribute("Bravery measures a Beast's will to keep "
                           "going.")
    assert soup.verdict == ATTRIBUTED and soup.rung == PROSE
    step = index.attribute("Beasts may need to perform a Fading Step "
                           "Knack to keep their footing.")
    assert step.rung == PROSE  # description is a prose home


def test_receipt_rung_matches_carried_sentences():
    g = GraphData()
    g.ensure_node("Knack", "Warden",
                  from_text="The Warden steps into harm's way for "
                            "an adjacent ally.")
    verdict = CanonIndex(g).attribute(
        "The Warden steps into harm's way for an adjacent ally.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == RECEIPT


def test_homeless_claim_splits_on_parity():
    # census claims come back judge-normalized (lowercase, no period)
    draft = ("Bog imposes -2 to defense. The moon phase doubles all "
             "wear. Lanterns cost two gold each.")
    results = census(draft, canon(),
                     invented=["The moon phase doubles all wear."])
    by_claim = {r.claim: r for r in results}
    assert by_claim["bog imposes -2 to defense"].verdict == ATTRIBUTED
    # parity called it invented and canon has no home: the named red
    assert by_claim["the moon phase doubles all wear"].verdict == \
        INVENTION
    # parity-green but homeless: the hole is the graph's, not the
    # drafter's — a debt that never blocks
    assert by_claim["lanterns cost two gold each"].verdict == CANON_GAP


def test_earned_flag_follows_the_consulted_set():
    index = CanonIndex(canon())
    earned = index.attribute("Bog imposes -2 to defense.",
                             consulted={("Terrain", "Bog")})
    assert earned.earned is True
    unearned = index.attribute("Bog imposes -2 to defense.",
                               consulted={("Knack", "Fading Step")})
    assert unearned.earned is False
    silent = index.attribute("Bog imposes -2 to defense.")
    assert silent.earned is None  # no trace supplied — nothing claimed


def test_census_comprehends_headed_tables_and_skips_structure():
    draft = ("Bog imposes -2 to defense.\n"
             "| Knack | Spark |\n| --- | --- |\n| Bound | Faint |\n"
             "{{csv:data/knacks.csv}}\n")
    # prose claims come back judge-normalized; a headed table
    # comprehends into fact-grain claims; the embed stays structure
    assert census_claims(draft) == ["bog imposes -2 to defense",
                                    "the spark of knack bound is faint"]


def test_census_leaves_headerless_tables_as_structure():
    draft = ("Bog imposes -2 to defense.\n"
             "| Knack | Spark |\n| Bound | Faint |\n")
    # no separator line means no header names no properties — the
    # table stays structure until a reading rules its shape
    assert census_claims(draft) == ["bog imposes -2 to defense"]


def test_metadata_props_attest_nothing():
    g = GraphData()
    g.ensure_node("[Decision]", "A ruling on lamps",
                  source="docs/tale.md section Harbor",
                  grade="agent-proposed")
    verdict = CanonIndex(g).attribute(
        "The harbor section of the tale explains the lamps.")
    assert verdict.verdict == CANON_GAP  # provenance strings are not homes


def test_report_names_the_ruled_semantics():
    draft = ("Bog imposes -2 to defense. The moon phase doubles all "
             "wear. Lanterns cost two gold each. Bravery measures a "
             "Beast's will to keep going.")
    results = census(draft, canon(),
                     invented=["The moon phase doubles all wear."])
    report = render_census(results)
    # a gap with a near miss names its nearest citizens readably
    near_gap = census("Bog Beasts suffer badly in mud.", canon())
    near_report = render_census(near_gap)
    assert "(Terrain) Bog" in near_report or "nearest" not in \
        near_report
    assert "1 canon gaps" in report
    assert "1 unattributed inventions" in report
    assert "presented, never hidden" in report          # the S4 ruling
    assert "shipping does not stop" in report            # the S3 ruling
    assert "the soup" in report


# --- structural attribution: the matcher reads the citizens' structure —
#     edges, lifted step text, mechanical value paraphrases — not just
#     their prose ---

def test_edge_relation_attributes_first_class_to_both_endpoints():
    # a claim that names BOTH endpoints of a ground edge AND speaks one
    # of the edge type's own words homes first-class on both citizens
    g = GraphData()
    g.ensure_node("Terrain", "Bog")
    g.ensure_node("Knack", "Bound")
    g.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Bog",
                             "Knack", "Bound"))
    verdict = CanonIndex(g).attribute("Bog grants the Bound knack.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == PROPERTIES
    assert ("Terrain", "Bog") in verdict.citizens
    assert ("Knack", "Bound") in verdict.citizens
    assert "edge" in verdict.evidence
    assert "edge" in verdict.row()["evidence"]


def test_edge_matching_requires_a_type_word_not_mere_co_occurrence():
    # both endpoints named but NO edge-type word spoken → the sentence
    # does not assert the relationship, so it is not an edge home
    g = GraphData()
    g.ensure_node("Terrain", "Bog")
    g.ensure_node("Knack", "Bound")
    g.edges.append(make_edge("GRANTS_KNACK", "Terrain", "Bog",
                             "Knack", "Bound"))
    verdict = CanonIndex(g).attribute("Bog and Bound are both trouble.")
    assert verdict.verdict == CANON_GAP


def test_edge_matching_excludes_machine_derived_and_projection_types():
    # the SAME endpoints + type words: a ground edge is a home; a
    # machine-derived type and the ASSIGNS_* projection family are not
    def graph_with(edge_type):
        g = GraphData()
        g.ensure_node("Cat", "Alpha")
        g.ensure_node("Cat", "Beta")
        g.edges.append(make_edge(edge_type, "Cat", "Alpha", "Cat", "Beta"))
        return CanonIndex(g)

    ground = graph_with("GRANTS_KNACK").attribute("Alpha grants Beta knack.")
    assert ground.verdict == ATTRIBUTED and ground.rung == PROPERTIES
    derived = graph_with("MENTIONS").attribute("Alpha mentions Beta.")
    assert derived.verdict == CANON_GAP
    projected = graph_with("ASSIGNS_CONDITION").attribute(
        "Alpha assigns condition Beta.")
    assert projected.verdict == CANON_GAP


def test_step_lift_attributes_at_receipt_grade_citing_the_procedure():
    # a procedure's lifted step text is receipt-grain prose the OWNING
    # procedure carries; a claim found there cites the procedure, not
    # the step (the owner is the step name's prefix before the mark)
    g = GraphData()
    g.ensure_node("[Procedure]", "Tally the Points")
    g.ensure_node("[Step]", "Tally the Points §1",
                  kind="compute",
                  text="the top point total equals the might score")
    verdict = CanonIndex(g).attribute(
        "the top point total equals the might score")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == RECEIPT
    assert ("[Procedure]", "Tally the Points") in verdict.citizens
    assert "step" in verdict.evidence
    # the step itself is never the cited home
    assert not any(label == "[Step]" for label, _ in verdict.citizens)


def test_value_matching_folds_numeric_format_and_parentheticals():
    g = GraphData()
    g.ensure_node("Gem", "Core Shine (Close)", bonus="+10")
    g.ensure_node("Beast", "Ox", wear="3.0")
    index = CanonIndex(g)
    # parenthetical name: "(close)" tokenizes as "close"; "+10" == "10"
    paren = index.attribute("Core Shine (Close) adds 10 to the roll.")
    assert paren.verdict == ATTRIBUTED and paren.rung == PROPERTIES
    assert ("Gem", "Core Shine (Close)") in paren.citizens
    assert "value" in paren.evidence
    # trailing point-zero strips: "3.0" == "3"
    dotzero = index.attribute("Ox adds 3 wear.")
    assert dotzero.verdict == ATTRIBUTED and dotzero.rung == PROPERTIES


def test_numeric_folding_is_format_only_never_sign_or_spelling():
    # only mechanical FORMAT folds (strip +, strip trailing .0). A bare
    # "2" does NOT match a stored "-2", and "minus 2" never matches "-2"
    g = GraphData()
    g.ensure_node("Gem", "Chill", penalty="-2")
    index = CanonIndex(g)
    assert index.attribute("Chill imposes 2 to the roll.").verdict \
        == CANON_GAP
    assert index.attribute("Chill imposes minus 2 to the roll.").verdict \
        == CANON_GAP


# --- fact-grain fidelity: the guards that keep number claims honest ---


def test_numeric_name_echo_matches_when_the_claim_says_it_twice():
    # "Might 7" whose cap is 7: the value survives the name subtraction,
    # but homes only when the claim carries the number once as the name
    # and once as the value — a bare mention anchors nothing
    g = GraphData()
    g.ensure_node("Rung", "Might 7", cap=7, bite_mod=-1)
    index = CanonIndex(g)
    fact = index.attribute("The Cap of Might 7 is 7.")
    assert fact.verdict == ATTRIBUTED and fact.rung == PROPERTIES
    assert ("Rung", "Might 7") in fact.citizens
    bare = index.attribute("A beast may reach Might 7.")
    assert bare.verdict == CANON_GAP


def test_wrong_number_finds_no_home_through_grammar_words():
    # a surface form like "Boon to X" must not home a wrong-number claim
    # on the strength of the word "to"
    g = GraphData()
    g.ensure_node("Archetype", "Boon", surface_forms="['Boon to X']")
    g.ensure_node("Rung", "Might 3", bite_mod=-4)
    index = CanonIndex(g)
    right = index.attribute("The Bite Mod of Might 3 is -4.")
    assert right.verdict == ATTRIBUTED and right.rung == PROPERTIES
    wrong = index.attribute("The Bite Mod of Might 3 is -5.")
    assert wrong.verdict == CANON_GAP


def test_property_names_lift_the_owning_citizens_score():
    # both citizens anchor, but the one whose property NAMES the claim
    # speaks ("body cap") outranks the passer-by that merely shares a
    # numeric token
    g = GraphData()
    g.ensure_node("Rung", "Might 3", body_cap=3, bite_mod=-4)
    g.ensure_node("Gem", "Might Core", charge=3)
    verdict = CanonIndex(g).attribute("The Body Cap of Might 3 is 3.")
    assert verdict.verdict == ATTRIBUTED
    assert verdict.citizens[0] == ("Rung", "Might 3")


def test_possessive_folds_at_the_structured_rung():
    g = GraphData()
    g.ensure_node("Terrain", "Bog", defense_mod=-2)
    verdict = CanonIndex(g).attribute("Bog's defense mod is -2.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == PROPERTIES


def test_whole_book_unit_produces_one_scorecard(make_repo):
    # two docs judged as ONE artifact: canon rows from every scope
    # apply, and the attribution census runs against the export
    from graph.roundtrip import ALL_SCOPES, run
    base_dir, _ = make_repo({
        "docs/one.md": "# One\n\nBog imposes -2 to defense.\n",
        "docs/two.md": "# Two\n\nRain soaks everyone completely.\n",
        "build/book.md": "# One\n\nBog imposes -2 to defense.\n\n"
                         "# Two\n\nRain soaks everyone completely.\n",
    }, "version: 1\nnodes: {}\n")
    export_dir = base_dir / "graph" / "export"
    export_dir.mkdir(parents=True)
    (export_dir / "nodes.jsonl").write_text(
        json.dumps({"label": "Terrain", "name": "Bog",
                    "properties": {"defense_mod": -2}}) + "\n"
        + json.dumps({"label": "[Approved Omission]",
                      "name": "rain soaks everyone completely",
                      "properties": {"scope": "docs/two.md"}}) + "\n",
        encoding="utf-8")
    (export_dir / "edges.jsonl").write_text("", encoding="utf-8")
    draft = base_dir / "draft.md"
    draft.write_text("# One\n\nBog imposes -2 to defense.\n",
                     encoding="utf-8")
    result = run(base_dir, "build/book.md", draft,
                 canon_scope=ALL_SCOPES)
    # the doc-two-scoped Approved Omission row covers the book run:
    # the dropped rain sentence is an approved omission, not a red
    assert result.passed, [f.message for t in result.tiers
                           for f in t.findings]
    # and the census attributed the surviving claim at the top rung
    [homed] = [r for r in result.attribution
               if r.verdict == ATTRIBUTED]
    assert homed.rung == PROPERTIES


def test_row_shaped_receipts_are_retired_from_the_index():
    # A table row in from_text is presentation, not a sentence — it
    # indexes as nothing, so the honest home beneath it (here the
    # description prop, a prose home) surfaces instead of being
    # outranked by the receipt rung.
    g = GraphData()
    g.ensure_node("Beast", "Ox",
                  description="A slow beast of the fens.",
                  from_text="| Ox | 3 | A slow beast of the fens. |")
    verdict = CanonIndex(g).attribute(
        "The Description of Beast Ox is A slow beast of the fens.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == PROSE
    assert "receipt" not in verdict.evidence


def test_multi_line_row_receipts_retire_and_sentences_stay():
    g = GraphData()
    g.ensure_node("Beast", "Wisp",
                  from_text="| Wisp | 2 |\n| Wisp | dusk only |")
    g.ensure_node("Terrain", "Bog",
                  from_text="A Bog Beast suffers -2 to defense.")
    index = CanonIndex(g)
    rows = index.attribute("Wisp is active at dusk only.")
    assert rows.verdict == CANON_GAP  # the rows index as nothing
    quote = index.attribute("A Bog Beast suffers -2 to defense.")
    assert quote.verdict == ATTRIBUTED  # sentence-grain receipts stay


# --- the plural fold, the declared column binding, and the twin rider ---


def test_plural_headers_home_on_singular_edge_types():
    # "The Ingredients of X is Y" vs HAS_INGREDIENT: morphology, not
    # vocabulary — both sides fold to one form and the edge is a home
    g = GraphData()
    g.ensure_node("Brew", "Twilight Tonic")
    g.ensure_node("Herb", "Nightbell")
    g.edges.append(make_edge("HAS_INGREDIENT", "Brew", "Twilight Tonic",
                             "Herb", "Nightbell"))
    verdict = CanonIndex(g).attribute(
        "The Ingredients of Twilight Tonic is Nightbell.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == PROPERTIES
    assert ("Brew", "Twilight Tonic") in verdict.citizens


def test_type_words_fold_both_sides():
    # a type whose own word is plural-shaped (REQUIRES) still meets the
    # claim's "requires" — the fold is symmetric, never one-sided
    g = GraphData()
    g.ensure_node("Rite", "Dawn Song")
    g.ensure_node("Herb", "Nightbell")
    g.edges.append(make_edge("REQUIRES", "Rite", "Dawn Song",
                             "Herb", "Nightbell"))
    verdict = CanonIndex(g).attribute("Dawn Song requires Nightbell.")
    assert verdict.verdict == ATTRIBUTED


def test_the_lemma_layer_knows_irregulars_no_bespoke_fold_ever_could():
    # rung 1's point: morphology is delegated, so irregular plurals
    # arrive free — the engine never rules on a plural again
    g = GraphData()
    g.ensure_node("Keeper", "Marsh Warden")
    g.ensure_node("Beast", "Goose")
    g.edges.append(make_edge("TENDS_BEAST", "Keeper", "Marsh Warden",
                             "Beast", "Goose"))
    verdict = CanonIndex(g).attribute(
        "The Marsh Warden tends the beasts, geese among them.")
    assert verdict.verdict == ATTRIBUTED


def test_numbers_never_enter_the_lemma():
    # '-2' -> '2' through a lemmatizer would smuggle signed equivalence
    # past the doctrine — number-bearing tokens skip the layer entirely
    g = GraphData()
    g.ensure_node("Gem", "Chill", penalty="-2")
    assert CanonIndex(g).attribute(
        "Chill imposes 2 to the roll.").verdict == CANON_GAP


def test_twin_citizens_read_alike_despite_a_name_echo():
    # the diagnostic rider: byte-identical stat shapes must read alike
    # even when one twin's NAME carries the value word in parentheses —
    # the word-shaped cousin of the numeric name-echo
    g = GraphData()
    g.ensure_node("Weapon", "Mace", damage_class="Crushing")
    g.ensure_node("Weapon", "Sword (Slashing)", damage_class="Slashing")
    index = CanonIndex(g)
    plain = index.attribute("The Damage Class of Mace is Crushing.")
    echoed = index.attribute(
        "The Damage Class of Sword (Slashing) is Slashing.")
    assert plain.verdict == ATTRIBUTED and plain.rung == PROPERTIES
    assert echoed.verdict == ATTRIBUTED and echoed.rung == PROPERTIES
    # a bare mention still attests subject, not content: the value word
    # appears only once (as the name), so it anchors nothing
    bare = index.attribute("Sword (Slashing) gleams in the dark.")
    assert bare.verdict == CANON_GAP


def test_single_letter_codes_keep_their_evidence():
    # the consumer's mover, reproduced: a claim restating a citizen's
    # single-letter code value in parentheses must evidence that value
    # identically before and after the lemma fold — a bare "m" from
    # "(M)" is a code, never the I'm contraction the dictionary sees
    g = GraphData()
    g.ensure_node("Blade", "Falchion", reach_code="M",
                  description="A broad, forward-weighted blade.")
    verdict = CanonIndex(g).attribute(
        "The Falchion (M) is a broad, forward-weighted blade.")
    assert verdict.verdict == ATTRIBUTED and verdict.rung == PROPERTIES
    assert "value" in verdict.evidence


def test_every_single_letter_passes_the_canon_unchanged():
    # the alphabet sweep, made a guard: no letter is a word to fold
    # (m -> be) and none comes back re-cased (i -> I)
    from graph.attribution import _canon
    for letter in "abcdefghijklmnopqrstuvwxyz":
        assert _canon(letter) == letter
