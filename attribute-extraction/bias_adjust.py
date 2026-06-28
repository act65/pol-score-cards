"""Sample-bias mitigation for the presented attribute scores (task 2b).

A raw scorecard value is the *mean of the statements the LLM chose to extract*
for one MP on one attribute. Two biases threaten cross-MP comparison:

  1. Thin-sample noise. An MP with n=1 civility statement at 0.2 should not be
     ranked below an MP with n=40 averaging 0.55 — the n=1 value is mostly noise.
  2. Selection/salience bias. The extractor is told to sample representatively
     (see extract.build_combined_system), but mean(extracted) still need not equal
     mean(all said), so a raw mean over-trusts a handful of flagged lines.

(Hansard-only v2.0 removes the *source-mix* confound — every MP is measured in the
same adversarial chamber — so that bias, the worst one, is gone by construction.)

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


def _attr_prior(groups):
    """Empirical-Bayes prior for one attribute, by method of moments over MPs.

    Returns (prior_mean, between_var, within_var). between_var is the spread of
    *true* MP means; within_var is per-statement noise. The shrinkage weight for
    an MP with n statements is between/(between + within/n)."""
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
            shrink = between_var / (between_var + within_var / n)
            adj = shrink * raw + (1 - shrink) * prior_mean
            post_var = 1.0 / (1.0 / between_var + n / within_var)
            ci95 = 1.96 * math.sqrt(post_var)
            conf = "high" if n >= 10 else "medium" if n >= 3 else "low"
            out[(mid, attr)] = AdjustedScore(n, raw, adj, ci95, conf, shrink)
    return out


def display_score(adj: AdjustedScore) -> int:
    """The 0-100 number shown on a card (the project's S = 100*positive scale,
    here the shrunk mean on 0..1 mapped to 0..100)."""
    return round(adj.adj_mean * 100)
