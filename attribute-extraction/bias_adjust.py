"""Sample-bias mitigation for the presented attribute scores (task 2b).

A raw scorecard value is the *mean of the statements the LLM chose to extract*
for one MP on one attribute. Three biases threaten cross-MP comparison; this
module addresses the first two only:

  1. Thin-sample noise. An MP with n=1 civility statement at 0.2 should not be
     ranked below an MP with n=40 averaging 0.55 — the n=1 value is mostly noise.
  2. Selection/salience bias. The extractor is told to sample representatively
     (see extract.build_combined_system), but mean(extracted) still need not equal
     mean(all said), so a raw mean over-trusts a handful of flagged lines.

  3. Source-mix confound. NOT MITIGATED, and probably the worst of the three.
     An early Hansard-only build did remove it by construction — every MP was
     measured in the same adversarial chamber — but the served dataset now blends
     65,075 Hansard, 23,935 party-release and 5,419 presser statements into one
     pool per (MP, attribute). Scores differ substantially by source (party
     releases run ~+18 on Forthrightness and ~-7 to -9 on Civility/Rigor/
     Specificity relative to Hansard), the mix differs by party (~45% releases for
     ACT vs ~17% for NZ First), and pressers are government-only. Nothing below
     corrects for any of that: shrinkage is fit over the pooled scores and cannot
     see which source a statement came from. Fixing it means either scoring per
     source and reweighting to a common mix, or going back to Hansard-only for
     cross-MP comparison.

Mitigation = hierarchical (empirical-Bayes) shrinkage toward the per-attribute
population mean, plus an explicit n and 95% credible interval. An MP's adjusted
score is pulled toward the prior in proportion to how little / how noisy their
evidence is; thin scores are flagged low-confidence rather than shown as fact.

    from bias_adjust import adjust_scores
    adjusted = adjust_scores(per_mp_attr_scores)   # {(mid,attr): AdjustedScore}
"""

import collections
import math
from dataclasses import dataclass, asdict


@dataclass
class AdjustedScore:
    n: int
    raw_mean: float
    adj_mean: float        # empirical-Bayes posterior mean (shown on the site)
    ci95: float            # +/- half-width of the 95% credible interval
    confidence: str        # "high" | "medium" | "low"
    shrink: float          # 0=fully prior, 1=fully trust the raw mean

    def dict(self):
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _var(xs, mu=None):
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs) if mu is None else mu
    return sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)


# Pseudo-observations of the pooled within-variance blended into each MP's own.
# An MP with two statements has a sample variance that is almost pure noise (and
# can be exactly zero if the two happen to agree), which would hand them a
# tighter interval than an MP with fifty. Blending regularises that: at n=1 the
# estimate is the pooled value, and by n≈20 it is essentially the MP's own.
_VAR_PSEUDO_N = 4.0


def _within_var_for(scores, pooled):
    """This MP's per-statement variance, shrunk toward the attribute's pooled one."""
    n = len(scores)
    if n < 2:
        return pooled
    own = _var(scores)
    w = (n - 1) / (n - 1 + _VAR_PSEUDO_N)
    return max(1e-6, w * own + (1 - w) * pooled)


def _attr_prior(groups):
    """Empirical-Bayes prior for one attribute, by method of moments over MPs.

    Returns (prior_mean, between_var, within_var). between_var is the spread of
    *true* MP means; within_var is the POOLED per-statement noise, used to
    de-bias between_var and as the prior for each MP's own variance."""
    all_scores = [s for g in groups for s in g]
    prior_mean = _mean(all_scores)
    within_var = _mean([_var(g) for g in groups if len(g) >= 2]) or _var(all_scores)
    # variance of the per-MP means, de-biased by the sampling variance it carries
    means = [_mean(g) for g in groups]
    grand = _mean(means)
    obs_var_of_means = _var(means, grand)
    avg_inv_n = _mean([1.0 / len(g) for g in groups]) if groups else 1.0
    between_var = max(1e-6, obs_var_of_means - within_var * avg_inv_n)
    return prior_mean, between_var, max(1e-6, within_var)


def adjust_scores(per_mp_attr):
    """per_mp_attr: {(mp_id, attribute): [score, ...]} -> {(mp_id, attr): AdjustedScore}.

    Shrinkage is fit per attribute across all MPs, so each attribute gets its own
    prior mean and shrink strength."""
    by_attr = collections.defaultdict(list)        # attr -> list of score-lists
    keys_by_attr = collections.defaultdict(list)
    for (mid, attr), scores in per_mp_attr.items():
        if scores:
            by_attr[attr].append(scores)
            keys_by_attr[attr].append((mid, attr, scores))

    out = {}
    for attr, groups in by_attr.items():
        prior_mean, between_var, within_var = _attr_prior(groups)
        for mid, _attr, scores in keys_by_attr[attr]:
            n = len(scores)
            raw = _mean(scores)
            # Each MP's OWN spread, not one pooled number for the attribute.
            # Pooling it made both the shrinkage and the interval a function of
            # n alone: two MPs with three Rigor statements got the same +/-11
            # whether their statements ranged over 16 points or 23. An MP who is
            # consistently middling is better measured than one who swings from
            # 5 to 95, at the same sample size, and the interval has to say so.
            mp_within = _within_var_for(scores, within_var)
            se2 = mp_within / n
            shrink = between_var / (between_var + se2)
            adj = shrink * raw + (1 - shrink) * prior_mean
            post_var = 1.0 / (1.0 / between_var + 1.0 / se2)
            ci95 = 1.96 * math.sqrt(post_var)
            out[(mid, attr)] = AdjustedScore(n, raw, adj, ci95,
                                             _confidence(ci95, n, shrink),
                                             shrink)
    return out


# Confidence reads off the INTERVAL, not the count. "high confidence, +/-4" on
# a score whose statements range from 5 to 95 was the old tiering saying only
# "this MP talks a lot". The n floor stays as a guard: an interval is a model
# output, and three statements should never be called high confidence however
# tightly they happen to agree.
_CONF_HIGH, _CONF_MED = 0.05, 0.12      # half-width on the 0..1 scale
_CONF_MIN_N = 8

# ...and it reads off SHRINK too, because a narrow interval has two completely
# different causes and only one of them is good news.
#
# post_var = 1/(1/between_var + 1/se2), which rearranges to between_var *
# (1 - shrink). So as an MP's evidence gets noisier, shrink falls, the posterior
# collapses onto the PRIOR, and ci95 tends to 1.96*sqrt(between_var) -- the
# spread of the House, which for a tightly-bunched attribute is narrow. The
# interval is correct as a posterior. As a label it was a lie: it said "we
# measured this MP well" when it meant "we learned nothing from this MP, so this
# is the House average, and the House average is itself narrow".
#
# Found 2026-09-26 on Divination: mean shrink 0.09, so every card was 91% prior
# and 9% that MP, a 9-point spread across 129 MPs -- and 70 of them were labelled
# HIGH confidence. Every other attribute shrinks at 0.80-0.89, which is why this
# went unnoticed: the two readings only diverge when shrinkage is severe.
#
# Thresholds are on the share of the estimate that is the MP's OWN evidence:
# below half, the number is more prior than MP and cannot be "high"; below a
# quarter it is overwhelmingly the population mean and is "low" whatever the
# interval says.
_CONF_MIN_SHRINK = 0.50
_CONF_FLOOR_SHRINK = 0.25


def _confidence(ci95: float, n: int, shrink: float = 1.0) -> str:
    """How much to trust one displayed score: interval, sample size AND how much
    of the estimate came from this MP rather than from the prior."""
    if shrink < _CONF_FLOOR_SHRINK:
        # Mostly the House average wearing this MP's name.
        return "low"
    if ci95 <= _CONF_HIGH and n >= _CONF_MIN_N and shrink >= _CONF_MIN_SHRINK:
        return "high"
    if ci95 <= _CONF_MED and n >= 3:
        return "medium"
    return "low"


def display_score(adj: AdjustedScore) -> int:
    """The 0-100 number shown on a card (the project's S = 100*positive scale,
    here the shrunk mean on 0..1 mapped to 0..100)."""
    return round(adj.adj_mean * 100)
