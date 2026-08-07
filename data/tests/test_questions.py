"""Offline tests for the Hansard oral-question pair parser.

    cd data && python -m pytest test_questions.py
"""

import json

import parse_questions as pq
import pytest
from names import RosterIndex

ROSTER = RosterIndex.from_mapping({
    "chris hipkins": "chris-hipkins", "hipkins": "chris-hipkins",
    "christopher luxon": "luxon", "luxon": "luxon",
    "nicola willis": "nicola-willis", "willis": "nicola-willis",
    "ginny andersen": "ginny-andersen", "andersen": "ginny-andersen",
})


# --- name cleaning ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Rt Hon CHRISTOPHER LUXON (Prime Minister)", "Christopher Luxon"),
    ("Rt Hon Chris Hipkins", "Chris Hipkins"),
    ("Hon NICOLA WILLIS (Minister of Finance) (14:44)", "Nicola Willis"),
    ("DAN BIDOIS (National—Northcote)", "Dan Bidois"),
    # A minister answering for a colleague: keep who actually answered.
    ("WINSTON PETERS  on behalf of the Prime Minister", "Winston Peters"),
    ("David Seymour )", "David Seymour"),
])
def test_clean_name(raw, expected):
    assert pq.clean_name(raw) == expected  # re-exported from names.clean


def test_same_person_across_caps_and_supplementaries():
    """Hansard caps whoever has the call, so the same MP appears both ways."""
    assert pq._same_person("Rt Hon CHRISTOPHER LUXON (Prime Minister)",
                           "Rt Hon Christopher Luxon")
    assert not pq._same_person("Rt Hon Chris Hipkins", "Hon Nicola Willis")


# --- turn splitting --------------------------------------------------------

def test_split_turn_ignores_colons_inside_parentheses():
    """A title containing a colon must not truncate the speaker."""
    got = pq.split_turn("Hon TAMA POTAKA (Minister for Māori Crown Relations: "
                        "Te Arawhiti) : Kia ora.")
    assert got is not None
    speaker, text = got
    assert "Te Arawhiti" in speaker and text == "Kia ora."


def test_split_turn_returns_none_without_a_colon():
    assert pq.split_turn("Just some prose with no speaker") is None


# --- block parsing, both house styles --------------------------------------

BLOCK_2025 = """Question No. 1—Prime Minister
1. Rt Hon CHRIS HIPKINS (Leader of the Opposition) to the Prime Minister: Does he stand by all his statements?
Rt Hon CHRISTOPHER LUXON (Prime Minister): Yes.
Rt Hon Chris Hipkins : Does he stand by his statement on the economy?
Rt Hon CHRISTOPHER LUXON : Well, absolutely, and that is why we have acted.
Hon Ginny Andersen : Answer the question.
SPEAKER : Order. The Prime Minister was answering.
Rt Hon Chris Hipkins : Will he resign?
Rt Hon CHRISTOPHER LUXON : No.""".split("\n")

BLOCK_2026 = """Question No. 1
DAN BIDOIS (National—Northcote) (14:44) to the Minister of Finance : Will conflict have an impact?
Hon NICOLA WILLIS (Minister of Finance) (14:44) : New Zealand is a trading nation.""".split("\n")


def test_parses_2025_style_block():
    pairs = pq.parse_block(BLOCK_2025, ROSTER)
    assert len(pairs) == 3
    assert pairs[0]["is_primary"] is True
    assert pairs[0]["question"].startswith("Does he stand by all his statements")
    assert pairs[0]["answer"] == "Yes."
    assert pairs[0]["portfolio"] == "Prime Minister"
    assert pairs[-1]["question"] == "Will he resign?"
    assert pairs[-1]["answer"] == "No."


def test_parses_2026_style_block_without_number_or_portfolio():
    pairs = pq.parse_block(BLOCK_2026, ROSTER)
    assert len(pairs) == 1
    assert pairs[0]["asker"] == "Dan Bidois"
    assert pairs[0]["responder"] == "Nicola Willis"
    assert pairs[0]["addressee"] == "Minister of Finance"
    assert pairs[0]["portfolio"] is None


def test_interjections_and_chair_are_dropped():
    """'Answer the question' from a third MP is heckling, not a question."""
    pairs = pq.parse_block(BLOCK_2025, ROSTER)
    texts = [p["question"] for p in pairs] + [p["answer"] for p in pairs]
    assert not any("Answer the question" in t for t in texts)
    assert not any("Order." in t for t in texts)


def test_asker_and_responder_resolve_to_ids():
    pairs = pq.parse_block(BLOCK_2025, ROSTER)
    assert all(p["asker_id"] == "chris-hipkins" for p in pairs)
    assert all(p["responder_id"] == "luxon" for p in pairs)


def test_supplementaries_are_numbered_after_the_primary():
    pairs = pq.parse_block(BLOCK_2025, ROSTER)
    assert pairs[0]["supplementary_index"] is None
    assert [p["supplementary_index"] for p in pairs[1:]] == [1, 2]


def test_block_without_a_primary_question_yields_nothing():
    assert pq.parse_block(["Question No. 4—Health", "SPEAKER : Order."], ROSTER) == []


# --- end to end ------------------------------------------------------------

def test_parse_corpus_splits_multiple_blocks(tmp_path, monkeypatch):
    corpus = tmp_path / "hansard.json"
    corpus.write_text(json.dumps({
        "headline": "Wednesday, 15 October 2025 — part 1",
        "date": "2025-10-15", "author": "Hansard",
        "content": "\n".join(BLOCK_2025 + BLOCK_2026),
        "url": "https://example.test/h",
    }) + "\n")
    monkeypatch.setattr(pq, "load_roster_index", lambda path=None: ROSTER)
    pairs = pq.parse_corpus(str(corpus), roster_path=str(tmp_path / "missing.json"))
    assert len(pairs) == 4                       # 3 from the first block, 1 from the second
    assert all(p["date"] == "2025-10-15" for p in pairs)
    assert len({p["question_id"] for p in pairs}) == 4


def test_points_of_order_are_not_counted_as_questions():
    """The asker also raises points of order mid-block. Counting them pairs the
    Minister's real answer with the wrong text and inflates the question count."""
    block = """Question No. 2—Health
2. Dr AYESHA VERRALL (Labour) to the Minister of Health: Does she stand by her statement?
Hon SIMEON BROWN (Minister of Health): Yes.
Dr Ayesha Verrall : Point of order, Mr Speaker. I didn't hear that answer.
Dr Ayesha Verrall : Why did waiting lists grow?
Hon SIMEON BROWN : Because of the previous Government.""".split("\n")
    pairs = pq.parse_block(block, ROSTER)
    assert len(pairs) == 2
    assert not any("Point of order" in p["question"] for p in pairs)
    assert pairs[1]["question"] == "Why did waiting lists grow?"
