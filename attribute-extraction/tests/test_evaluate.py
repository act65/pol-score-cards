"""Offline tests for the pure metric functions in evaluate.py (no API calls)."""

import math

import evaluate


def test_perfect_agreement():
    pred = [0.1, 0.5, 0.9]
    gold = [0.1, 0.5, 0.9]
    m = evaluate.metrics(pred, gold)
    assert m["mae"] == 0
    assert m["rmse"] == 0
    assert math.isclose(m["pearson_r"], 1.0)
    assert m["binary_accuracy"] == 1.0


def test_mae_rmse():
    pred = [0.0, 1.0]
    gold = [0.5, 0.5]
    assert math.isclose(evaluate.mae(pred, gold), 0.5)
    assert math.isclose(evaluate.rmse(pred, gold), 0.5)


def test_pearson_anticorrelated():
    pred = [0.0, 0.5, 1.0]
    gold = [1.0, 0.5, 0.0]
    assert math.isclose(evaluate.pearson(pred, gold), -1.0)


def test_pearson_constant_is_none():
    assert evaluate.pearson([0.5, 0.5, 0.5], [0.1, 0.2, 0.3]) is None


def test_binary_accuracy_threshold():
    # gold good/good/bad ; pred good/bad/bad  -> 2/3 agree at 0.5
    pred = [0.9, 0.2, 0.1]
    gold = [0.8, 0.7, 0.1]
    assert math.isclose(evaluate.binary_accuracy(pred, gold), 2 / 3)


def test_gold_score_extraction():
    assert evaluate._gold_score({"civility_score": 0.6, "statement": "x"}) == 0.6
    assert evaluate._gold_score({"veracity_score": 0.3}) == 0.3
    assert evaluate._gold_score({"label": {"x": 1}}) is None
