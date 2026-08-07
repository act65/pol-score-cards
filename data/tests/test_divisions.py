"""Offline tests for the Hansard division parser (no network, no corpus needed).

    cd data && python -m pytest test_divisions.py
"""

import parse_divisions as pd
import pytest
from names import RosterIndex

ROSTER = RosterIndex.from_mapping(
    {"ferris": "takuta-ferris", "kapa-kingi": "mariameno-kapa-kingi"})


# --- vote-line detection --------------------------------------------------

@pytest.mark.parametrize("line", [
    "New Zealand National 48; ACT New Zealand 11; New Zealand First 8.",
    "New Zealand Labour 34; Green Party of Aotearoa New Zealand 15; Te Pāti Māori 4; Ferris; Kapa-Kingi.",
    # Hansard sprinkles non-breaking spaces inside party names.
    "New Zealand National 49; ACT New Zealand 11; New\xa0Zealand\xa0First\xa08.",
    # A handful of lines separate with commas instead of semicolons.
    "New Zealand Labour 34, Green Party of Aotearoa New Zealand 15, ACT New Zealand 11.",
    # Alternate spelling that appears in the record.
    "Te Paati Māori 6; New Zealand Labour 34.",
])
def test_is_vote_line_accepts_tallies(line):
    assert pd.is_vote_line(line)


@pytest.mark.parametrize("line", [
    "",
    "SPEAKER : The question is that the motion be agreed to.",
    "The result corrected after originally being announced as Ayes 82, Noes 35",
    "A party vote was called for on the question, That the motion be agreed to .",
    "The bill was divided into the Contracts of Insurance Bill and another, as set out on Amendment Paper 12.",
    "Amendment to the amendment not agreed to.",
    # An unknown party name means we have mis-detected the line.
    "Imaginary Party of Nowhere 12; New Zealand Labour 34.",
])
def test_is_vote_line_rejects_prose(line):
    assert not pd.is_vote_line(line)


# --- tally parsing --------------------------------------------------------

def test_parse_vote_line_parties_and_total():
    got = pd.parse_vote_line("New Zealand National 48; ACT New Zealand 11; New Zealand First 8.")
    assert got["parties"] == {"National": 48, "ACT": 11, "NZ First": 8}
    assert got["total"] == 67
    assert got["members"] == [] and got["unresolved_members"] == []


def test_parse_vote_line_resolves_named_members():
    got = pd.parse_vote_line(
        "New Zealand Labour 34; Te Pāti Māori 4; Ferris; Kapa-Kingi.", ROSTER)
    assert got["parties"] == {"Labour": 34, "Te Pāti Māori": 4}
    assert got["members"] == ["takuta-ferris", "mariameno-kapa-kingi"]
    # Each individually-recorded member is one vote on top of the party counts.
    assert got["total"] == 40


def test_parse_vote_line_keeps_unresolved_surnames():
    got = pd.parse_vote_line("New Zealand Labour 34; Kerekere.", ROSTER)
    assert got["unresolved_members"] == ["Kerekere"]
    assert got["total"] == 35


def test_parse_vote_line_handles_nbsp():
    got = pd.parse_vote_line("New\xa0Zealand\xa0First\xa08; ACT New Zealand 11.")
    assert got["parties"] == {"NZ First": 8, "ACT": 11}


# --- classification -------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("That the Disability Support Services Bill be now read a first time", "first_reading"),
    ("That the Arms Bill be now read a second time", "second_reading"),
    ("That the Parliament Bill be now read a third time", "third_reading"),
    ("That debate on this question now close", "closure"),
    ("That the question be now put", "closure"),
    ("That urgency be accorded", "urgency"),
    ("That the amendment be agreed to", "amendment"),
    ("That Part 1 as amended be agreed to", "committee"),
    ("That the motion be agreed to", "motion"),
    ("That the Electoral Amendment Bill be reported to the House by 1 December", "committee_report"),
    ("That leave be granted for something unusual", "other"),
])
def test_classify(question, expected):
    assert pd.classify(question) == expected


def test_substantive_excludes_floor_management():
    assert pd.classify("That the Arms Bill be now read a second time") in pd.SUBSTANTIVE_TYPES
    assert pd.classify("That debate on this question now close") not in pd.SUBSTANTIVE_TYPES
    assert pd.classify("That urgency be accorded") not in pd.SUBSTANTIVE_TYPES


# --- bill identification --------------------------------------------------

def test_bills_from_question():
    q = ("That the Environment (Disestablishment of Ministry for the Environment) "
         "Amendment Bill be now read a third time")
    assert pd.bills_from_question(q) == [
        "Environment (Disestablishment of Ministry for the Environment) Amendment Bill"]


def test_bills_from_question_empty_for_procedural():
    assert pd.bills_from_question("That debate on this question now close") == []


def test_bills_from_question_splits_joint_reading():
    """Bills split in committee get one vote covering both."""
    q = "That the Gangs Bill and the Sentencing Amendment Bill be now read a third time"
    assert pd.bills_from_question(q) == ["Gangs Bill", "Sentencing Amendment Bill"]


def test_bills_from_question_strips_committee_report_prefix():
    q = ("That the report of the Health Committee on the Pae Ora (Healthy Futures) "
         "Amendment Bill be agreed to")
    assert pd.bills_from_question(q) == ["Pae Ora (Healthy Futures) Amendment Bill"]


def test_bills_from_heading():
    assert pd.bills_from_heading("Social Security (Modernisation) Amendment Bill") == \
        ["Social Security (Modernisation) Amendment Bill"]
    assert pd.bills_from_heading("Education and Training Amendment Bill (No 2)") == \
        ["Education and Training Amendment Bill (No 2)"]


def test_bills_from_heading_rejects_prose():
    assert pd.bills_from_heading(
        "GLEN BENNETT (Labour) : I cannot support the Arms Bill at all.") == []
    assert pd.bills_from_heading("That the Arms Bill be now read a second time") == []


# --- verdict lines --------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("Amendment to the amendment not agreed to.", "not_agreed"),
    ("Motion agreed to.", "agreed"),
    ("Bill read a third time.", "agreed"),
    # A following question is not a verdict, even though it ends "agreed to."
    ("A party vote was called for on the question, That Part 2 be agreed to.", None),
    ("CHAIRPERSON (Maureen Pugh) : The question is that the motion be agreed to.", None),
    ("", None),
])
def test_read_verdict_line(line, expected):
    assert pd.read_verdict_line(line)[0] == expected


# --- end-to-end over a synthetic transcript -------------------------------

TRANSCRIPT = "\n".join([
    "Arms Bill",
    "Hon MP (Minister) : I move, That the Arms Bill be now read a second time.",
    "A party vote was called for on the question, That the Arms Bill be now read a second time .",
    "New Zealand National 48; ACT New Zealand 11; New Zealand First 8.",
    "New Zealand Labour 34; Green Party of Aotearoa New Zealand 15; Te Pāti Māori 4; Ferris.",
    "Bill read a second time.",
    "A party vote was called for on the question, That debate on this question now close .",
    "New Zealand Labour 34; Green Party of Aotearoa New Zealand 15.",
    "New Zealand National 48; ACT New Zealand 11; New Zealand First 8.",
])


@pytest.fixture
def parsed(tmp_path, monkeypatch):
    import json
    corpus = tmp_path / "hansard.json"
    corpus.write_text(json.dumps({
        "headline": "Tuesday, 27 May 2026 — part 1 (2026-05-27)",
        "date": "2026-05-27", "author": "Hansard",
        "content": TRANSCRIPT, "url": "https://example.test/h",
    }) + "\n")
    monkeypatch.setattr(pd, "load_roster_index", lambda path=None: ROSTER)
    return pd.parse_corpus(str(corpus), roster_path=str(tmp_path / "missing.json"))


def test_end_to_end_finds_both_divisions(parsed):
    assert len(parsed) == 2
    assert [d["type"] for d in parsed] == ["second_reading", "closure"]


def test_end_to_end_tally_and_result(parsed):
    first = parsed[0]
    assert first["ayes"]["parties"] == {"National": 48, "ACT": 11, "NZ First": 8}
    assert first["ayes"]["total"] == 67
    assert first["noes"]["total"] == 54          # 34 + 15 + 4 + Ferris
    assert first["result"] == "agreed"
    assert first["verdict_line"] == "Bill read a second time."
    assert "ayes_order_inferred" in first["flags"]


def test_end_to_end_result_from_totals_when_no_verdict_line(parsed):
    second = parsed[1]
    assert second["result"] == "not_agreed"      # 49 ayes vs 67 noes
    assert "result_from_totals" in second["flags"]


def test_end_to_end_bill_context_carries_to_procedural_vote(parsed):
    assert parsed[0]["bills"] == ["Arms Bill"]
    assert parsed[0]["bill_source"] == "question"
    # The closure motion names no bill, so it inherits the debate's subject.
    assert parsed[1]["bills"] == ["Arms Bill"]
    assert parsed[1]["bill_source"] == "carried_forward"


def test_end_to_end_ids_and_parliament(parsed):
    assert [d["division_id"] for d in parsed] == ["2026-05-27-001", "2026-05-27-002"]
    assert all(d["parliament"] == 54 for d in parsed)


# --- labelled vote blocks (Hansard scrapes taken after the VOTES.md 1b fix) --

LABELLED = [
    "Ayes 83",
    "New Zealand National 48; Green Party of Aotearoa New Zealand 15; ACT New Zealand 11; New Zealand First 8; Kapa-Kingi.",
    "Noes 34",
    "New Zealand Labour 34.",
    "Motion agreed to.",
]

UNLABELLED = [
    "New Zealand National 48; ACT New Zealand 11; New Zealand First 8.",
    "New Zealand Labour 34; Green Party of Aotearoa New Zealand 15.",
    "Motion agreed to.",
]


def test_scan_vote_block_reads_labels():
    sides, labelled, consumed = pd.scan_vote_block(LABELLED)
    assert labelled is True
    assert [s["side"] for s in sides] == ["ayes", "noes"]
    assert [s["declared"] for s in sides] == [83, 34]
    # Four lines of tally block; the verdict line is not part of it.
    assert consumed == 4


def test_scan_vote_block_falls_back_to_position():
    sides, labelled, consumed = pd.scan_vote_block(UNLABELLED)
    assert labelled is False
    assert [s["side"] for s in sides] == ["ayes", "noes"]
    assert [s["declared"] for s in sides] == [None, None]
    assert consumed == 2


def test_scan_vote_block_handles_abstentions():
    sides, labelled, _ = pd.scan_vote_block([
        "Ayes 60", "New Zealand National 48; ACT New Zealand 11; Ferris.",
        "Noes 49", "New Zealand Labour 34; Green Party of Aotearoa New Zealand 15.",
        "Abstentions 8", "New Zealand First 8.",
    ])
    assert labelled is True
    assert [s["side"] for s in sides] == ["ayes", "noes", "abstentions"]


def test_scan_vote_block_stops_at_prose():
    sides, _, consumed = pd.scan_vote_block(
        ["New Zealand National 48.", "SPEAKER : Order.", "New Zealand Labour 34."])
    assert len(sides) == 1 and consumed == 1


def _parse(tmp_path, monkeypatch, lines):
    import json
    corpus = tmp_path / "hansard.json"
    corpus.write_text(json.dumps({
        "headline": "Wednesday, 27 May 2026 — part 1 (2026-05-27)",
        "date": "2026-05-27", "author": "Hansard",
        "content": "\n".join([
            "Arms Bill",
            "A party vote was called for on the question, That the motion be agreed to .",
            *lines,
        ]),
        "url": "https://example.test/h",
    }) + "\n")
    monkeypatch.setattr(pd, "load_roster_index", lambda path=None: ROSTER)
    return pd.parse_corpus(str(corpus), roster_path=str(tmp_path / "missing.json"))[0]


def test_labelled_division_uses_labels_not_inference(tmp_path, monkeypatch):
    d = _parse(tmp_path, monkeypatch, LABELLED)
    assert "ayes_labelled" in d["flags"]
    assert "ayes_order_inferred" not in d["flags"]
    assert d["ayes"]["declared_total"] == 83 and d["ayes"]["total"] == 83
    assert d["noes"]["declared_total"] == 34 and d["noes"]["total"] == 34
    assert "tally_mismatch" not in d["flags"]


def test_labelled_division_finds_verdict_after_the_block(tmp_path, monkeypatch):
    """The verdict line sits after four tally lines, not two."""
    d = _parse(tmp_path, monkeypatch, LABELLED)
    assert d["verdict_line"] == "Motion agreed to."
    assert "result_from_totals" not in d["flags"]
    assert d["result"] == "agreed"


def test_small_noes_tally_is_not_mistaken_for_unopposed(tmp_path, monkeypatch):
    """The regression that motivated 1b: 'New Zealand Labour 34.' is short, and
    losing it turned a 34-strong Noes into an unopposed vote."""
    d = _parse(tmp_path, monkeypatch, LABELLED)
    assert d["noes"] is not None
    assert "unopposed" not in d["flags"]


def test_declared_total_mismatch_is_flagged(tmp_path, monkeypatch):
    d = _parse(tmp_path, monkeypatch, ["Ayes 99", "New Zealand National 48.",
                                       "Noes 34", "New Zealand Labour 34."])
    assert "tally_mismatch" in d["flags"]
    assert d["ayes"]["declared_total"] == 99 and d["ayes"]["total"] == 48


# --- tallies that wrap across two paragraphs --------------------------------
# Hansard sometimes breaks a long tally over two <p>s, the first ending in ";".
# Read naively, the continuation is taken as the *other* side and a whole
# party's votes disappear (declared 102 vs parsed 94 — a missing "NZ First 8").

WRAPPED = [
    "Ayes 102",
    "New Zealand National 49; New Zealand Labour 34; ACT New Zealand 11;",
    "New Zealand First 8.",
    "Noes 21",
    "Green Party of Aotearoa New Zealand 15; Te Pāti Māori 6.",
    "Motion agreed to.",
]


def test_scan_vote_block_joins_wrapped_tally():
    sides, labelled, consumed = pd.scan_vote_block(WRAPPED)
    assert labelled is True
    assert [s["side"] for s in sides] == ["ayes", "noes"]
    assert consumed == 5                       # 2 labels + 3 tally lines
    ayes = pd.parse_vote_line(sides[0]["line"])
    assert ayes["parties"] == {"National": 49, "Labour": 34, "ACT": 11, "NZ First": 8}
    assert ayes["total"] == 102 == sides[0]["declared"]


def test_wrapped_tally_produces_no_mismatch(tmp_path, monkeypatch):
    d = _parse(tmp_path, monkeypatch, WRAPPED)
    assert "tally_mismatch" not in d["flags"]
    assert d["ayes"]["total"] == 102 and d["noes"]["total"] == 21
    assert d["verdict_line"] == "Motion agreed to."


# --- misspelled surnames ----------------------------------------------------




def test_wrap_join_stops_at_the_declared_total():
    """When Hansard omits the closing full stop, the declared total bounds the
    join — otherwise the Noes tally is swallowed into the Ayes."""
    sides, labelled, _ = pd.scan_vote_block([
        "Ayes 102",
        "New Zealand National 49; New Zealand Labour 34; ACT New Zealand 11; New Zealand First 8",
        "Noes 34",
        "New Zealand Labour 34.",
    ])
    assert [s["side"] for s in sides] == ["ayes", "noes"]
    assert pd.parse_vote_line(sides[0]["line"])["total"] == 102
    assert pd.parse_vote_line(sides[1]["line"])["total"] == 34
