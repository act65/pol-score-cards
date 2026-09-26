"""Offline unit tests for the v2.0 Hansard pipeline pure-logic modules.

No API key, no network — run with `python -m pytest test_v2_pipeline.py`.
Covers roster name resolution, empirical-Bayes bias shrinkage, and Hansard
speaker segmentation/attribution.
"""

import hansard_prep
from bias_adjust import adjust_scores
from build_v2_dataset import Roster, is_probably_mp_name
from names import norm as _norm

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


def test_the_interval_reflects_spread_not_just_sample_size():
    """Two MPs with the same number of statements, one consistent and one all
    over the place, must not get the same interval.

    They did: `within_var` was pooled across every MP on an attribute, so the
    posterior variance reduced to a function of n. Two MPs with three Rigor
    statements each got the same +/-11 whether their statements ranged over 16
    points or 23.
    """
    population = {(f"o{i}", "rigor"): [0.30 + 0.01 * i] * 12 for i in range(30)}
    tight = [0.50, 0.50, 0.52, 0.48, 0.50]
    wide = [0.05, 0.95, 0.50, 0.20, 0.80]
    adj = adjust_scores({**population,
                         ("tight", "rigor"): tight,
                         ("wide", "rigor"): wide})

    assert adj[("tight", "rigor")].n == adj[("wide", "rigor")].n
    assert adj[("wide", "rigor")].ci95 > adj[("tight", "rigor")].ci95


def test_a_noisy_mp_is_shrunk_harder_than_a_consistent_one():
    """The same logic applies to the score itself: a mean over statements that
    disagree is weaker evidence of a true mean, so it should be pulled further
    toward the population."""
    population = {(f"o{i}", "civility"): [0.30 + 0.01 * i] * 12 for i in range(30)}
    adj = adjust_scores({**population,
                         ("tight", "civility"): [0.9, 0.9, 0.88, 0.92, 0.9],
                         ("wide", "civility"): [0.5, 1.0, 1.0, 1.0, 1.0]})

    assert adj[("tight", "civility")].shrink > adj[("wide", "civility")].shrink


def test_confidence_is_not_just_a_count():
    """`n >= 10 -> high` called an MP well-measured for talking a lot. High
    confidence now needs a tight interval AND enough statements to trust it."""
    population = {(f"o{i}", "focus"): [0.30 + 0.01 * i] * 12 for i in range(30)}
    adj = adjust_scores({**population,
                         ("noisy", "focus"): [0.0, 1.0] * 15,       # n=30, huge spread
                         ("steady", "focus"): [0.7, 0.72, 0.68] * 10})

    assert adj[("noisy", "focus")].n == adj[("steady", "focus")].n
    assert adj[("steady", "focus")].confidence == "high"
    assert adj[("noisy", "focus")].confidence != "high"


def test_two_agreeing_statements_are_not_high_confidence():
    """A sample variance from n=2 is almost pure noise and can be exactly zero.
    Without regularisation that buys a tighter interval than fifty statements."""
    population = {(f"o{i}", "rigor"): [0.30 + 0.01 * i] * 12 for i in range(30)}
    adj = adjust_scores({**population, ("lucky", "rigor"): [0.6, 0.6]})

    assert adj[("lucky", "rigor")].confidence != "high"


# --- Confidence must know how much of the score is actually this MP ---------
# post_var = between_var * (1 - shrink), so as an MP's evidence gets noisier the
# posterior collapses onto the PRIOR and the interval narrows toward the spread
# of the House. The interval is right; calling it "high confidence" was not.
#
# Divination, 2026-09-26: mean shrink 0.09 — every card 91% prior, a 9-point
# spread across 129 MPs — and 70 of them were labelled high confidence.

def _prior_dominated_population(n_mps=130, rotations=True):
    """The pathological limit, built deterministically rather than sampled.

    Every observation is 0, 0.5 or 1 — a coin flip per statement, which is what a
    resolved prediction is — and every MP gets the SAME multiset, so the spread of
    per-MP means is zero and between_var falls to its floor. That is the regime
    Divination is actually in: enormous within-MP noise, nothing between MPs, nine
    observations each.

    Sampling this instead made the test a coin flip itself: whether between_var
    floored depended on the seed, so the defect appeared for 0 or for all 130
    cards depending on which one was picked.
    """
    base = [0.0, 0.0, 0.0, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0]
    return {(f"mp{i}", "divination"):
            (base[i % len(base):] + base[:i % len(base)]) if rotations else list(base)
            for i in range(n_mps)}


def test_a_prior_dominated_score_is_never_high_confidence():
    adj = adjust_scores(_prior_dominated_population())
    prior_dominated = [a for a in adj.values() if a.shrink < 0.5]
    assert prior_dominated, "this population should shrink hard; test is not set up"
    assert all(a.confidence != "high" for a in prior_dominated)


def test_a_narrow_interval_alone_does_not_buy_high_confidence():
    """The exact defect: tight ci95, plenty of n, and the number is still the
    prior. Under the old rule every one of these was "high confidence"."""
    adj = adjust_scores(_prior_dominated_population())
    cards = list(adj.values())
    assert all(a.n >= 8 for a in cards)
    assert max(a.ci95 for a in cards) <= 0.05, "interval is not tight; test is not set up"
    assert max(a.shrink for a in cards) < 0.25, "not prior-dominated; test is not set up"
    assert all(a.confidence == "low" for a in cards)


def test_an_overwhelmingly_prior_score_is_low_whatever_the_interval():
    from bias_adjust import _confidence
    # Would have been "high" on interval and count alone.
    assert _confidence(ci95=0.01, n=50, shrink=0.10) == "low"
    assert _confidence(ci95=0.01, n=50, shrink=0.24) == "low"


def test_evidence_backed_scores_keep_their_confidence():
    """The fix must be surgical. Civility/Rigor/Specificity/Focus shrink at
    0.80-0.89, and demoting those would throw away real measurement."""
    from bias_adjust import _confidence
    assert _confidence(ci95=0.03, n=40, shrink=0.85) == "high"
    assert _confidence(ci95=0.03, n=40, shrink=0.50) == "high"
    assert _confidence(ci95=0.10, n=10, shrink=0.85) == "medium"


def test_the_shrink_argument_defaults_to_trusting_the_data():
    """Callers that predate the argument must not be silently demoted."""
    from bias_adjust import _confidence
    assert _confidence(0.03, 40) == "high"
