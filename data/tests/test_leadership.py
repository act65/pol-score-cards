"""`leadership.json` is hand-written, so the roster is what keeps it honest.

A typo'd id here does not crash anything — the MP simply never matches the site's
"Leaders & ministers" filter, and a filter that silently omits the Minister of
Health looks like a data gap rather than a bug. These tests are the only thing
standing between a mistyped name and that failure mode.
"""

import json
import os

import pytest

from names import RosterIndex

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "leadership.json")

VALID_TIERS = {"leader", "minister"}


@pytest.fixture(scope="module")
def doc():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def roster():
    return RosterIndex()


def test_every_id_is_a_real_mp(doc, roster):
    unknown = [pid for pid in doc["roles"] if roster.name_of(pid) == pid]
    assert not unknown, f"not in mps_roster.json: {unknown}"


def test_every_entry_has_a_known_tier_and_a_role(doc):
    for pid, entry in doc["roles"].items():
        assert entry["tier"] in VALID_TIERS, f"{pid}: {entry['tier']}"
        assert entry["role"].strip(), f"{pid} has no role label"


def test_the_snapshot_says_when_it_is_from(doc):
    # Roles change mid-term; a list without a date is a list you cannot check.
    assert doc["_as_at"], "leadership.json must carry an _as_at date"
    assert doc["_sources"], "and say where the roles came from"


def test_each_party_has_at_most_two_co_leaders(doc, roster):
    # A party with three "Co-Leader" rows means a former holder was left in when
    # the snapshot moved — the most likely way this file rots.
    counts = {}
    for pid, entry in doc["roles"].items():
        if "Leader" in entry["role"] and "Deputy" not in entry["role"]:
            counts.setdefault(roster.party_of(pid), []).append(pid)
    over = {party: ids for party, ids in counts.items() if len(ids) > 2}
    assert not over, f"more leaders than a party can have: {over}"


def test_the_government_parties_hold_the_ministries(doc, roster):
    # Every warrant in the snapshot belongs to a coalition party. A minister
    # from an opposition party means a role was carried over from the previous
    # government (see _changes_in_term) and the snapshot is inconsistent.
    government = {"National", "ACT", "NZ First"}
    strays = {pid: roster.party_of(pid) for pid, e in doc["roles"].items()
              if e["tier"] == "minister" and roster.party_of(pid) not in government}
    assert not strays, f"ministers from outside the government: {strays}"
