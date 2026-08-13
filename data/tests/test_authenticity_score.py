"""Authenticity join: words against the recorded vote."""

import authenticity_score as a


def _prop(pid="prop:x", party=None, member=None):
    return {"proposition_id": pid,
            "party_positions": party or {},
            "member_positions": member or {}}


def _pos(stance, pid="prop:x", party="Labour", who="mp-a", confidence=None):
    p = {"politician_id": who, "politician": who, "party": party,
         "proposition_id": pid, "stance": stance, "quote": "..."}
    if confidence is not None:
        p["confidence"] = confidence
    return p


def test_vote_matching_words_is_consistent():
    j = a.judge(_pos("support"), _prop(party={"Labour": {"stance": "support"}}))
    assert j["verdict"] == "consistent"


def test_vote_opposing_words_is_a_contradiction():
    j = a.judge(_pos("support"), _prop(party={"Labour": {"stance": "oppose"}}))
    assert j["verdict"] == "contradiction"
    assert j["stated"] == "support" and j["voted"] == "oppose"


def test_individual_record_beats_the_party_record():
    """A conscience vote says what the member did; the party vote does not.

    Here the party voted against and the member personally voted for. Judged
    on the party record this is a contradiction; on their own record it is not.
    """
    j = a.judge(
        _pos("support"),
        _prop(party={"Labour": {"stance": "oppose"}},
              member={"mp-a": {"stance": "support"}}),
    )
    assert j["basis"] == "member"
    assert j["verdict"] == "consistent"


def test_mixed_party_vote_is_not_a_contradiction():
    """A split party has no single direction to contradict."""
    j = a.judge(_pos("support"), _prop(party={"Labour": {"stance": "mixed"}}))
    assert j["verdict"] == "unscorable"


def test_unknown_proposition_is_unscorable():
    assert a.judge(_pos("support"), None)["verdict"] == "unscorable"


def test_no_recorded_vote_for_that_party_is_unscorable():
    j = a.judge(_pos("support", party="ACT"),
                _prop(party={"Labour": {"stance": "oppose"}}))
    assert j["verdict"] == "unscorable"


def test_low_confidence_positions_do_not_manufacture_hypocrisy():
    j = a.judge(_pos("support", confidence=0.2),
                _prop(party={"Labour": {"stance": "oppose"}}))
    assert j["verdict"] == "unscorable"


def test_score_is_a_rate_with_the_denominator_shown():
    """Three positions, one contradicted, one unscorable => 1/2, not 1/3."""
    judged = [
        {"verdict": "consistent", "basis": "party"},
        {"verdict": "contradiction", "basis": "party"},
        {"verdict": "unscorable", "basis": None},
    ]
    agg = a._score_member(judged)
    assert agg["score"] == 0.5
    assert agg["positions_stated"] == 3
    assert agg["positions_scored"] == 2
    assert agg["unscorable"] == 1


def test_no_scorable_positions_gives_no_score_not_zero():
    agg = a._score_member([{"verdict": "unscorable", "basis": None}])
    assert agg["score"] is None
    assert agg["insufficient_evidence"] is True


def test_basis_is_reported_so_the_card_can_carry_the_caveat():
    agg = a._score_member([
        {"verdict": "consistent", "basis": "party"},
        {"verdict": "contradiction", "basis": "member"},
    ])
    assert agg["basis"] == "mixed"
    assert agg["member_level_n"] == 1 and agg["party_level_n"] == 1


# --- matching spoken bill names to the proposition vocabulary ---------------

PROPS = {
    "prop:business-payment-practices-bill": {"label": "Business Payment Practices Bill"},
    "prop:gangs-bill": {"label": "Gangs Legislation Amendment Bill"},
    "prop:fast-track-approvals-bill": {"label": "Fast-track Approvals Bill"},
}


def test_exact_bill_name_matches():
    assert a.resolve_proposition("Fast-track Approvals Bill", PROPS) \
        == "prop:fast-track-approvals-bill"


def test_bill_name_matches_without_the_word_bill():
    assert a.resolve_proposition("the Fast-track Approvals", PROPS) \
        == "prop:fast-track-approvals-bill"


def test_unrelated_text_matches_nothing():
    assert a.resolve_proposition("the state of the housing market", PROPS) is None


def test_empty_text_matches_nothing():
    assert a.resolve_proposition("", PROPS) is None
    assert a.resolve_proposition("the a of and", PROPS) is None


def test_ambiguous_match_is_refused_rather_than_guessed():
    """Two bills fit equally well, so we do not know which was meant."""
    props = {"prop:a": {"label": "Local Government Rating Bill"},
             "prop:b": {"label": "Local Government Electoral Bill"}}
    assert a.resolve_proposition("Local Government", props) is None
