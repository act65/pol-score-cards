"""Offline tests for the written-questions client (no network).

    cd data/scrapers && python -m pytest test_written_questions.py
"""

import json

import written_questions as wq
import pytest
from names import RosterIndex

NAMES = {"m1": "Utikere, Tangi", "m2": "Hernandez, Francisco"}
ROSTER = RosterIndex.from_mapping({
    "tangi utikere": "tangi-utikere", "utikere": "tangi-utikere",
    "chris bishop": "chris-bishop", "bishop": "chris-bishop",
    "christopher luxon": "luxon", "luxon": "luxon",
})


def _row(**over):
    base = {
        "writtenQuestionsDocumentId": "WQ_19631_2026",
        "questionNumber": 19631, "questionYear": 2026, "parliamentNumber": 54,
        "memberId": "m1", "ministerName": "Hon Chris Bishop",
        "ministerialDisplayName": "Minister of Housing",
        "questionText": "  How many houses were consented?  ",
        "replyText": "I am advised that 1,234 houses were consented.",
        "statusId": 2, "attachmentName": None,
        "questionReleasedDate": "2026-05-19T00:00:00Z",
    }
    base.update(over)
    return base


# --- name tidying ----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Rt Hon Christopher Luxon", "Christopher Luxon"),
    ("Andersen, Hon Ginny", "Ginny Andersen"),
    ("Hon Dr Shane Reti", "Shane Reti"),
    ("Utikere, Tangi", "Tangi Utikere"),
    # A real surname must survive; only honorifics are stripped.
    ("Ricardo Menéndez March", "Ricardo Menéndez March"),
])
def test_tidy_name(raw, expected):
    assert wq.tidy_name(raw) == expected


def test_names_resolve_to_roster_ids():
    row = wq.normalise(_row(), NAMES, ROSTER)
    assert row["asker"] == "Tangi Utikere" and row["asker_id"] == "tangi-utikere"
    assert row["minister"] == "Chris Bishop" and row["minister_id"] == "chris-bishop"


def test_unknown_member_id_leaves_asker_empty():
    row = wq.normalise(_row(memberId="nope"), NAMES, ROSTER)
    assert row["asker"] is None and row["asker_id"] is None


# --- answered vs pending: the distinction Forthrightness depends on ---------

def test_answered_question_keeps_its_reply():
    row = wq.normalise(_row(), NAMES, ROSTER)
    assert row["answered"] is True
    assert row["reply"] == "I am advised that 1,234 houses were consented."


def test_pending_placeholder_is_not_treated_as_an_answer():
    """An unanswered question carries 'Reply due: 10 Aug 2026' rather than an
    empty field; scoring that as a reply would read as a non-answer."""
    row = wq.normalise(_row(statusId=1, replyText="Reply due: 10 Aug 2026"),
                       NAMES, ROSTER)
    assert row["answered"] is False
    assert row["reply"] is None


def test_pending_detected_from_text_even_if_status_says_answered():
    row = wq.normalise(_row(statusId=2, replyText="Reply due: 1 Sep 2026"),
                       NAMES, ROSTER)
    assert row["answered"] is False


def test_attachment_only_reply_is_flagged():
    """No reply text to judge — must not count as an evasive non-answer."""
    row = wq.normalise(_row(replyText="", attachmentName="table.pdf"),
                       NAMES, ROSTER)
    assert row["attachment_only"] is True
    assert row["attachment_name"] == "table.pdf"


def test_text_is_stripped_and_dates_shortened():
    row = wq.normalise(_row(), NAMES, ROSTER)
    assert row["question"] == "How many houses were consented?"
    assert row["released_date"] == "2026-05-19"


def test_permalink_is_built_from_the_document_id():
    row = wq.normalise(_row(), NAMES, ROSTER)
    assert row["url"] == ("https://questions.parliament.nz/written-questions/"
                          "question/WQ_19631_2026")


def test_missing_document_id_yields_no_url():
    assert wq.normalise(_row(writtenQuestionsDocumentId=None),
                        NAMES, ROSTER)["url"] is None


# --- pagination contract ---------------------------------------------------

def test_search_template_is_the_questions_shape_not_the_bills_one():
    """This endpoint takes a different filter object; sending the bills shape
    returns a 400."""
    assert "searchTab" in wq.SEARCH_TEMPLATE
    assert "documentPreset" not in wq.SEARCH_TEMPLATE
    assert wq.SEARCH_TEMPLATE["page"] == 1


# --- month slicing: the workaround for the deep-pagination 500 --------------
# Paging the unfiltered set dies at ~page 102 (~101k rows). `dateFrom` and
# `dateTo` together DO filter (either alone is ignored), so we slice by month.

def test_months_are_contiguous_half_open_windows():
    got = list(wq._months("2023-10", "2024-01"))
    assert got[0] == ("2023-10-01T00:00:00Z", "2023-11-01T00:00:00Z")
    # Each window ends exactly where the next begins: no gap, no double count.
    for (_, end), (start, _) in zip(got, got[1:]):
        assert end == start
    assert got[-1][0].startswith("2024-01")


def test_months_span_a_year_boundary():
    got = list(wq._months("2023-12", "2024-02"))
    assert [a[:7] for a, _ in got] == ["2023-12", "2024-01", "2024-02"]


def test_months_single_month_is_one_window():
    assert len(list(wq._months("2024-03", "2024-03"))) == 1


def test_existing_ids_are_read_for_resume(tmp_path):
    """A crashed run must not re-fetch or duplicate what is already on disk."""
    path = tmp_path / "wq.jsonl"
    path.write_text("\n".join(json.dumps({"question_id": f"WQ_{i}_2026"})
                              for i in range(3)) + "\n")
    assert wq._existing(str(path)) == {"WQ_0_2026", "WQ_1_2026", "WQ_2_2026"}


def test_existing_is_empty_when_no_file(tmp_path):
    assert wq._existing(str(tmp_path / "nope.jsonl")) == set()
