"""Offline tests for the per-MP Strength ledger.

    cd data && python -m pytest test_strength_ledger.py
"""

import json

import pytest
import strength_ledger as sl


MPS = [
    {"id": "minister-a", "name": "Minister A", "party": "National"},
    {"id": "backbench-b", "name": "Backbench B", "party": "Labour"},
    {"id": "amender-c", "name": "Amender C", "party": "Green"},
    {"id": "silent-d", "name": "Silent D", "party": "National"},
]

BILLS = [
    {"title": "Alpha Bill", "parliament": 54, "bill_type": "Government",
     "outcome": "enacted", "member_in_charge_id": "minister-a",
     "dates": {"third_reading": "2025-03-01T00:00:00Z"}, "stages": []},
    {"title": "Beta Bill", "parliament": 54, "bill_type": "Government",
     "outcome": "terminated", "member_in_charge_id": "minister-a",
     "dates": {}, "stages": []},
    {"title": "Gamma Bill", "parliament": 54, "bill_type": "Government",
     "outcome": "in_progress", "member_in_charge_id": "minister-a",
     "dates": {}, "stages": []},
    {"title": "Delta Bill", "parliament": 54, "bill_type": "Member's",
     "outcome": "terminated", "member_in_charge_id": "backbench-b",
     "dates": {}, "stages": []},
    # 53rd-Parliament bill that never moved in this term — excluded.
    {"title": "Old Bill", "parliament": 53, "bill_type": "Government",
     "outcome": "enacted", "member_in_charge_id": "minister-a",
     "dates": {"third_reading": "2022-05-01T00:00:00Z"}, "stages": []},
    # 53rd-Parliament bill carried over and finished in this term — included.
    {"title": "Carryover Bill", "parliament": 53, "bill_type": "Government",
     "outcome": "enacted", "member_in_charge_id": "minister-a",
     "dates": {"third_reading": "2024-06-01T00:00:00Z"}, "stages": []},
]

PROPOSED = [
    {"title": "Ballot Bill", "member_id": "backbench-b", "party": "Labour"},
]

AMENDMENTS = (
    # Ten papers, but only two distinct bills: the filibuster pattern.
    [{"bill_title": "Alpha Bill", "member_id": "amender-c", "sop": i} for i in range(8)]
    + [{"bill_title": "Beta Bill", "member_id": "amender-c", "sop": 99}]
    + [{"bill_title": "Alpha Bill", "member_id": "backbench-b", "sop": 100}]
)


@pytest.fixture
def rows(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name, data in (("bills.jsonl", BILLS), ("proposed_bills.jsonl", PROPOSED),
                       ("amendment_papers.jsonl", AMENDMENTS)):
        (corpus / name).write_text(
            "\n".join(json.dumps(d) for d in data) + "\n")
    monkeypatch.setattr(sl, "CORPUS", str(corpus))
    pol = tmp_path / "politicians.jsonl"
    pol.write_text("\n".join(json.dumps(m) for m in MPS) + "\n")
    return {r["politician_id"]: r for r in sl.build(str(pol))}


# --- the two design rules --------------------------------------------------

def test_no_evidence_is_flagged_not_scored(rows):
    """An MP with no legislative record has not failed to deliver; they had no
    opportunity. That must not read as a zero."""
    d = rows["silent-d"]
    assert d["insufficient_evidence"] is True
    assert d["evidence_n"] == 0
    assert d["components"]["delivery_rate"] is None
    assert "score" not in d          # scoring is a separate, explicit decision


def test_amendments_counted_as_distinct_bills_not_raw_papers(rows):
    c = rows["amender-c"]
    assert c["amendment_papers"]["total"] == 9
    assert c["amendment_papers"]["distinct_bills"] == 2
    assert c["components"]["engagement"] == 2


# --- delivery --------------------------------------------------------------

def test_delivery_rate_ignores_bills_still_in_progress(rows):
    """A bill still before the House is pending, not a failure to deliver."""
    a = rows["minister-a"]
    assert a["bills_in_charge"]["in_progress"] == 1
    assert a["components"]["resolved_in_charge"] == 3   # 2 enacted + 1 terminated
    assert a["components"]["delivery_rate"] == pytest.approx(2 / 3)


def test_delivery_rate_is_none_when_nothing_resolved(rows):
    """Never zero — zero would claim they tried and failed."""
    assert rows["amender-c"]["components"]["delivery_rate"] is None


# --- scope and term windowing ---------------------------------------------

def test_minister_scope_inferred_from_government_bills(rows):
    assert rows["minister-a"]["delivery_scope"] == "minister"
    assert rows["backbench-b"]["delivery_scope"] == "member"
    assert rows["silent-d"]["delivery_scope"] == "none"


def test_carried_over_bill_counts_but_stale_one_does_not(rows):
    titles = rows["minister-a"]["bills_in_charge"]["titles"]
    assert "Carryover Bill" in titles      # 53rd Parliament, finished in this term
    assert "Old Bill" not in titles        # 53rd Parliament, finished before it


def test_engagement_unions_bills_in_charge_and_bills_amended(rows):
    b = rows["backbench-b"]
    assert b["bills_in_charge"]["total"] == 1        # Delta
    assert b["amendment_papers"]["distinct_bills"] == 1   # Alpha
    assert b["components"]["engagement"] == 2        # union, not double-count


def test_initiative_counts_ballot_bills(rows):
    """A bill lodged in the ballot is intent, whether or not it was drawn."""
    b = rows["backbench-b"]
    assert b["proposed_bills"]["total"] == 1
    assert b["components"]["initiative"] == 2        # 1 in charge + 1 proposed
    assert b["insufficient_evidence"] is False


def test_every_mp_gets_a_row(rows):
    assert len(rows) == len(MPS)
