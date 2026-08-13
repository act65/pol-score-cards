"""Strength scoring: the rules that stop it becoming a government detector."""

import strength_score as ss


def _row(pid, scope="member", delivery=None, proposed=0, ap=0, insufficient=False):
    return {
        "politician_id": pid, "name": pid, "party": "Labour",
        "delivery_scope": scope,
        "components": {"delivery_rate": delivery},
        "proposed_bills": {"total": proposed},
        "amendment_papers": {"distinct_bills": ap},
        "evidence_n": 0 if insufficient else 3,
        "insufficient_evidence": insufficient,
    }


def _by_id(rows):
    return {r["politician_id"]: r for r in rows}


def test_insufficient_evidence_never_scores_zero():
    """No lever to pull is not a failure to deliver. It must be None, not 0.0."""
    rows = _by_id(ss._scored([
        _row("a", delivery=1.0, proposed=2, ap=2),
        _row("nobody", insufficient=True),
    ]))
    assert rows["nobody"]["score"] is None
    assert rows["nobody"]["insufficient_evidence"] is True


def test_ties_contribute_nothing():
    """A component identical across a cohort tells you nothing about anyone.

    This is the minister case: delivery_rate is ~1.0 for all of them, and must
    not hand every minister the same large bonus.
    """
    rows = _by_id(ss._scored([
        _row(f"m{i}", scope="minister", delivery=1.0, proposed=i, ap=i)
        for i in range(4)
    ]))
    assert all(r["component_ranks"]["delivery_rate"] == 0.5 for r in rows.values())
    # The components that do vary still separate them.
    assert rows["m0"]["score"] < rows["m3"]["score"]


def test_null_delivery_is_excluded_not_zeroed():
    """Pending is not failure — the same rule as `uncheckable` in the resolver.

    Two members with identical other components must score the same whether or
    not one has a resolved bill yet.
    """
    rows = _by_id(ss._scored([
        _row("pending", delivery=None, proposed=2, ap=2),
        _row("resolved", delivery=1.0, proposed=2, ap=2),
        _row("other", delivery=1.0, proposed=2, ap=2),
    ]))
    assert "delivery_rate" not in rows["pending"]["components_used"]
    assert rows["pending"]["score"] == rows["resolved"]["score"]


def test_cohorts_are_ranked_separately():
    """A minister and a backbencher are not attempting the same task.

    The lone member here has the weakest raw record of anyone, but tops its own
    cohort, so it must not be dragged down by the ministers' larger numbers.
    """
    rows = _by_id(ss._scored(
        [_row(f"m{i}", scope="minister", delivery=1.0, proposed=0, ap=20 + i)
         for i in range(3)]
        + [_row("backbencher", scope="member", delivery=None, proposed=1, ap=1)]
    ))
    assert rows["backbencher"]["cohort"] == "member"
    assert rows["backbencher"]["cohort_n"] == 1
    assert rows["backbencher"]["score"] == 0.5      # alone in its cohort


def test_missing_component_reweights_rather_than_penalising():
    """Someone with no resolved bill is not capped at the remaining weights."""
    rows = _by_id(ss._scored([
        _row("top", delivery=None, proposed=9, ap=9),
        _row("mid", delivery=None, proposed=5, ap=5),
        _row("low", delivery=None, proposed=1, ap=1),
    ]))
    # Ranked top of both available components => the maximum, not 0.5.
    assert rows["top"]["score"] == 1.0
    assert rows["low"]["score"] == 0.0


def test_ranking_removes_the_government_delivery_gap():
    """The whole point: raw delivery separates the sides, rank within cohort
    does not. Ministers all deliver; backbenchers' ballot bills rarely pass."""
    ministers = [_row(f"gov{i}", scope="minister", delivery=1.0, proposed=0, ap=5)
                 for i in range(5)]
    members = [_row(f"opp{i}", scope="member", delivery=0.0, proposed=2, ap=1)
               for i in range(5)]
    rows = ss._scored(ministers + members)
    gov = [r["score"] for r in rows if r["politician_id"].startswith("gov")]
    opp = [r["score"] for r in rows if r["politician_id"].startswith("opp")]
    assert abs(sum(gov) / len(gov) - sum(opp) / len(opp)) < 0.01
