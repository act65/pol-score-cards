"""Offline tests for the proposition vocabulary builder.

    cd data && python -m pytest test_propositions.py
"""

import json

import build_propositions as bp
import pytest


def _div(did, date, dtype, ayes, noes, bills, substantive=True,
         aye_members=(), noe_members=()):
    mk = lambda parties, members: {
        "parties": parties, "members": list(members),
        "unresolved_members": [],
        "total": sum(parties.values()) + len(members)}
    return {
        "division_id": did, "date": date, "type": dtype,
        "substantive": substantive, "bills": bills,
        "ayes": mk(ayes, aye_members), "noes": mk(noes, noe_members),
        "abstentions": None, "result": "agreed", "flags": [],
    }


GOVT = {"National": 49, "ACT": 11, "NZ First": 8}
OPP = {"Labour": 34, "Green": 15}

DIVISIONS = [
    # Alpha Bill: opposition supports it into committee, then votes it down at
    # third reading. The settled position is the third reading.
    _div("d1", "2025-02-01", "first_reading", {**GOVT, **OPP}, {}, ["Alpha Bill"]),
    _div("d2", "2025-05-01", "third_reading", GOVT, OPP, ["Alpha Bill"],
         noe_members=["takuta-ferris"]),
    # An amendment carries no stance on the bill itself.
    _div("d3", "2025-04-01", "amendment", OPP, GOVT, ["Alpha Bill"]),
    # Beta Bill only ever saw a committee-stage clause vote — weak evidence.
    _div("d4", "2025-06-01", "committee", {**GOVT, "Green": 15}, {"Labour": 34},
         ["Beta Bill"]),
    # Procedural votes are excluded entirely.
    _div("d5", "2025-06-02", "closure", GOVT, OPP, ["Alpha Bill"], substantive=False),
]

BILLS = [
    {"title": "Alpha Bill", "bill_id": "b1", "bill_type": "Government",
     "outcome": "enacted", "member_in_charge_id": "minister-a",
     "description": "  A bill about alpha.  "},
    {"title": "Beta Bill", "bill_id": "b2", "bill_type": "Member's",
     "outcome": "terminated", "member_in_charge_id": "backbench-b",
     "description": ""},
]


@pytest.fixture
def props(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "divisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in DIVISIONS) + "\n")
    (corpus / "bills.jsonl").write_text(
        "\n".join(json.dumps(b) for b in BILLS) + "\n")
    monkeypatch.setattr(bp, "CORPUS", str(corpus))
    return {p["proposition_id"]: p for p in bp.build()}


def test_one_proposition_per_bill_divided_on(props):
    assert set(props) == {"prop:alpha-bill", "prop:beta-bill"}


def test_slug_is_stable_and_readable():
    assert bp.slug("Education and Training (System Reform) Amendment Bill") == \
        "education-and-training-system-reform-amendment-bill"


def test_third_reading_outranks_earlier_stages(props):
    """Opposition voted Alpha through at first reading and against at third;
    the third reading is the settled position."""
    a = props["prop:alpha-bill"]
    assert a["decisive_stage"] == "third_reading"
    assert a["party_positions"]["Labour"]["stance"] == "oppose"
    assert a["party_positions"]["National"]["stance"] == "support"


def test_amendments_carry_no_stance_on_the_bill(props):
    """d3 has the opposition as ayes; if amendments counted, Labour would flip."""
    assert props["prop:alpha-bill"]["party_positions"]["Labour"]["stance"] == "oppose"


def test_procedural_divisions_are_excluded(props):
    assert "d5" not in props["prop:alpha-bill"]["division_ids"]


def test_stance_confidence_reflects_the_decisive_stage(props):
    assert props["prop:alpha-bill"]["stance_confidence"] == "high"     # third reading
    assert props["prop:beta-bill"]["stance_confidence"] == "low"       # committee only


def test_individually_named_members_get_their_own_stance(props):
    a = props["prop:alpha-bill"]
    assert a["member_positions"]["takuta-ferris"]["stance"] == "oppose"
    assert "takuta-ferris" not in a["party_positions"]


def test_bill_metadata_is_joined(props):
    a = props["prop:alpha-bill"]
    assert a["bill_id"] == "b1"
    assert a["outcome"] == "enacted"
    assert a["description"] == "A bill about alpha."       # stripped
    assert props["prop:beta-bill"]["description"] is None  # empty -> None


def test_min_weight_drops_amendment_only_propositions(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "divisions.jsonl").write_text(json.dumps(
        _div("d9", "2025-01-01", "amendment", OPP, GOVT, ["Gamma Bill"])) + "\n")
    (corpus / "bills.jsonl").write_text("")
    monkeypatch.setattr(bp, "CORPUS", str(corpus))
    assert bp.build() == []


def test_dates_span_all_substantive_divisions(props):
    a = props["prop:alpha-bill"]
    assert a["first_division"] == "2025-02-01"
    assert a["last_division"] == "2025-05-01"
    assert a["n_divisions"] == 3        # 2 readings + 1 amendment, not the closure
