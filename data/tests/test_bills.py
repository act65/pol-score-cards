"""Offline tests for the bills API client (no network).

    cd data/scrapers && python -m pytest test_bills.py
"""

import bills
import pytest
from names import RosterIndex

ROSTER = RosterIndex.from_mapping({
    "paul goldsmith": "paul-goldsmith",
    "goldsmith": "paul-goldsmith",
    "camilla belich": "camilla-belich",
})


def _detail(**overrides):
    base = {
        "Id": "abc-123",
        "Title": "English Language Bill",
        "BillNumber": "198-1",
        "ParliamentNumber": 54,
        "BillTypeName": "Government",
        "BillStatusName": "Active",
        "BillCurrentStageName": "Royal Assent",
        "Description": "A bill.",
        "BillLegislationUrl": "https://www.legislation.govt.nz/bill/...",
        "Members": [{"PreferredFormOfAddress": "Hon Paul Goldsmith",
                     "SortedName": "Goldsmith, Paul"}],
        "SelectCommitteeInfo": {"Committees": [{"Name": "Justice"}]},
        "Stages": [
            {"StageName": "Third Reading", "StageDate": "2026-07-30T04:09:00Z",
             "OutcomeName": "Concluded", "TypeName": "Normal"},
            {"StageName": "Introduced", "StageDate": "2026-02-15T11:00:00Z",
             "OutcomeName": None, "TypeName": "Normal"},
        ],
        "IntroducedDate": "2026-02-15T11:00:00Z",
        "FirstReadingDate": "2026-03-03T02:41:00Z",
        "ThirdReadingDate": "2026-07-30T04:09:00Z",
    }
    base.update(overrides)
    return base


def test_normalise_core_fields():
    row = bills.normalise_bill(_detail(), ROSTER)
    assert row["bill_id"] == "abc-123"
    assert row["title"] == "English Language Bill"
    assert row["bill_type"] == "Government"
    assert row["select_committees"] == ["Justice"]
    assert row["url"] == "https://bills.parliament.nz/v/6/abc-123"


def test_stages_sorted_chronologically():
    row = bills.normalise_bill(_detail(), ROSTER)
    assert [s["stage"] for s in row["stages"]] == ["Introduced", "Third Reading"]


@pytest.mark.parametrize("stage,status,expected", [
    ("Royal Assent", "Active", "enacted"),
    # `status` lags behind: assent while still marked Active is still enacted.
    ("Royal Assent", "Terminated", "enacted"),
    ("First Reading", "Terminated", "terminated"),   # defeated at first reading
    ("Select Committee", "Active", "in_progress"),
])
def test_outcome_derivation(stage, status, expected):
    row = bills.normalise_bill(
        _detail(BillCurrentStageName=stage, BillStatusName=status), ROSTER)
    assert row["outcome"] == expected
    assert row["enacted"] == (expected == "enacted")


def test_member_in_charge_linked_to_roster():
    row = bills.normalise_bill(_detail(), ROSTER)
    assert row["member_in_charge"] == "Hon Paul Goldsmith"
    assert row["member_in_charge_id"] == "paul-goldsmith"


def test_member_in_charge_unlinked_when_not_on_roster():
    detail = _detail(Members=[{"PreferredFormOfAddress": "Hon Departed Member",
                               "SortedName": "Member, Departed"}])
    row = bills.normalise_bill(detail, ROSTER)
    assert row["member_in_charge"] == "Hon Departed Member"
    assert row["member_in_charge_id"] is None


def test_bill_with_no_member_in_charge():
    row = bills.normalise_bill(_detail(Members=[]), ROSTER)
    assert row["member_in_charge"] is None
    assert row["member_in_charge_id"] is None


@pytest.mark.parametrize("display,sorted_name", [
    ("Hon Paul Goldsmith", "Goldsmith, Paul"),
    ("Rt Hon Paul Goldsmith", "Goldsmith, Paul"),
    ("", "Goldsmith, Hon Paul"),
    ("Paul Goldsmith", ""),
])
def test_resolve_member_handles_honorifics_and_sort_order(display, sorted_name):
    assert bills._resolve_member(display, sorted_name, ROSTER) == "paul-goldsmith"


def test_search_template_is_not_mutated_by_list_calls():
    """`list_bills` copies the template; a stale page number would silently
    truncate later fetches."""
    assert bills.SEARCH_TEMPLATE["page"] == 1
    assert bills.SEARCH_TEMPLATE["parliament"] is None


# --- the other two document types that carry a named member -----------------

def test_normalise_proposed_members_bill():
    row = bills.normalise_proposed({
        "id": "p1", "title": "Financial Markets Conduct Amendment Bill\n",
        "partyName": "New Zealand First", "memberName": "Wilson, Dr David",
        "publicationDate": "2026-07-23T00:00:00Z", "parliamentNumber": 54,
    }, RosterIndex.from_mapping({"david wilson": "david-wilson"}))
    assert row["title"] == "Financial Markets Conduct Amendment Bill"   # trailing \n stripped
    assert row["member_id"] == "david-wilson"
    assert row["party"] == "New Zealand First"
    assert row["ballot_date"] == "2026-07-23T00:00:00Z"


def test_normalise_amendment_paper_links_to_its_bill():
    """`shortTitle` is the bill on its own — the join key for distinct bills."""
    row = bills.normalise_amendment({
        "id": "a1", "sop": 661,
        "title": "661 - Building and Construction Sector Amendment Bill",
        "shortTitle": "Building and Construction Sector Amendment Bill",
        "memberName": "Hon Chris Penk", "parliamentNumber": 54,
    }, RosterIndex.from_mapping({"chris penk": "chris-penk"}))
    assert row["sop"] == 661
    assert row["bill_title"] == "Building and Construction Sector Amendment Bill"
    assert row["member_id"] == "chris-penk"


def test_non_bill_presets_drop_bill_only_search_fields():
    """Sending billTab/includeBillStages with another preset 500s the endpoint."""
    assert bills._NON_BILL_OVERRIDES["billTab"] is None
    assert bills._NON_BILL_OVERRIDES["includeBillStages"] is None
    assert bills.PRESET_PROPOSED != bills.PRESET_BILLS
    assert bills.PRESET_AMENDMENTS != bills.PRESET_BILLS
