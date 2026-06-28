"""Offline unit tests for the v2.0 Hansard pipeline pure-logic modules.

No API key, no network — run with `python -m pytest test_v2_pipeline.py`.
Covers roster name resolution, empirical-Bayes bias shrinkage, and Hansard
speaker segmentation/attribution.
"""

import hansard_prep
from bias_adjust import adjust_scores
from roster import Roster, _norm, is_probably_mp_name

R = Roster()


# --- roster matching --------------------------------------------------------

def test_honorifics_stripped():
    assert R.match("Rt Hon Christopher Luxon") == R.match("Christopher Luxon")
    assert R.match("Hon Dr Megan Woods") == R.match("Megan Woods")


def test_accent_and_apostrophe_folding():
    a = R.match("Ricardo Menéndez March")
    assert a is not None and a == R.match("RICARDO MENENDEZ MARCH")
    # curly vs straight apostrophe resolve the same
    assert R.match("Damien O’Connor") == R.match("Damien O'Connor")


def test_middle_name_first_last():
    # "Takutai Tarsh Kemp" should resolve via first+last to Takutai Kemp
    assert R.match("Takutai Tarsh Kemp") == R.match("Takutai Kemp")


def test_added_mps_resolve():
    for name in ["Tanya Unkovich", "Georgie Dansey", "Laura Trask",
                 "Benjamin Doyle", "Mike Davidson", "David Parker"]:
        assert R.match(name) is not None, name


def test_non_mp_and_unknown_filtered():
    assert not is_probably_mp_name("Hon Member")
    assert not is_probably_mp_name("SPEAKER")
    assert not is_probably_mp_name("Speaker-elect")
    assert R.match("Hon Member") is None


def test_norm_idempotent():
    assert _norm(_norm("Rt Hon  CHRISTOPHER  LUXON")) == _norm("Rt Hon CHRISTOPHER LUXON")


# --- bias shrinkage ---------------------------------------------------------

def test_thin_pulls_to_prior_thick_stays():
    # one MP with a single extreme score, one with many near the mean
    per = {("thin", "civility"): [0.1]}
    per.update({(f"mp{i}", "civility"): [0.55, 0.6, 0.5, 0.58] for i in range(8)})
    adj = adjust_scores(per)
    thin = adj[("thin", "civility")]
    thick = adj[("mp0", "civility")]
    prior = sum(s for g in per.values() for s in g) / sum(len(g) for g in per.values())
    # thin score is pulled from 0.1 well toward the prior
    assert thin.raw_mean == 0.1
    assert abs(thin.adj_mean - prior) < abs(thin.raw_mean - prior)
    assert thin.confidence == "low"
    # thick score barely moves and is higher confidence than thin
    assert abs(thick.adj_mean - thick.raw_mean) < abs(thin.adj_mean - thin.raw_mean)
    assert thin.shrink < thick.shrink


def test_ci_narrows_with_n():
    per = {("a", "rigor"): [0.5], ("b", "rigor"): [0.5] * 20}
    per.update({(f"x{i}", "rigor"): [0.4, 0.6] for i in range(5)})
    adj = adjust_scores(per)
    assert adj[("b", "rigor")].ci95 < adj[("a", "rigor")].ci95


def test_confidence_tiers():
    per = {("a", "veracity"): [0.5]}                 # n=1 -> low
    per[("b", "veracity")] = [0.5, 0.6, 0.55]        # n=3 -> medium
    per[("c", "veracity")] = [0.5] * 12              # n=12 -> high
    adj = adjust_scores(per)
    assert adj[("a", "veracity")].confidence == "low"
    assert adj[("b", "veracity")].confidence == "medium"
    assert adj[("c", "veracity")].confidence == "high"


# --- Hansard segmentation ---------------------------------------------------

def test_segment_drops_procedural_keeps_member():
    text = ("SPEAKER (14:00) : Order.\n"
            "Hon NICOLA WILLIS (Minister of Finance): We are delivering for New "
            "Zealanders and growing the economy across the board this year.\n"
            "Rt Hon CHRIS HIPKINS (Leader of the Opposition): That claim does not "
            "match what families are actually experiencing at the supermarket.")
    turns = hansard_prep.segment_turns(text)
    speakers = [t["speaker"] for t in turns]
    assert any("NICOLA WILLIS" in (s or "") for s in speakers)
    procedural = [t for t in turns if t["procedural"]]
    assert any("SPEAKER" in (t["speaker"] or "") for t in procedural)


def test_prep_day_carries_speaker_across_parts():
    # a speech split across two parts: part 2 opens mid-speech (no tag)
    part1 = {"date": "2026-05-28", "content":
             "Hon NICOLA WILLIS (Minister of Finance): " + "We are delivering. " * 20}
    part2 = {"date": "2026-05-28", "content": "And we will keep delivering. " * 20}
    blocks = hansard_prep.prep_day([part1, part2])
    # the orphaned opener of part2 is attributed to Willis (carried), not dropped
    willis = [b for b in blocks if "WILLIS" in b["speaker"]]
    assert willis and "keep delivering" in willis[0]["text"]
