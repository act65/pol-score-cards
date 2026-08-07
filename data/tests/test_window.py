"""Offline tests for the date-window helpers in utils.py (no network)."""

import datetime

from utils import cutoff_date, is_recent, parse_date_loose

REF = datetime.date(2025, 6, 19)


def test_parse_date_loose_formats():
    assert parse_date_loose("2025-03-20") == datetime.date(2025, 3, 20)
    assert parse_date_loose("2025-03-20T12:50:00+13:00") == datetime.date(2025, 3, 20)
    assert parse_date_loose(datetime.date(2024, 1, 1)) == datetime.date(2024, 1, 1)
    assert parse_date_loose(datetime.datetime(2024, 1, 1, 9, 0)) == datetime.date(2024, 1, 1)
    assert parse_date_loose("") is None
    assert parse_date_loose("no date here") is None


def test_cutoff_date():
    assert cutoff_date(6, ref=REF) == REF - datetime.timedelta(days=180)


def test_is_recent_window():
    # ~3 months ago -> within a 6-month window
    assert is_recent("2025-03-20", months=6, ref=REF) is True
    # ~8 months ago -> outside a 6-month window
    assert is_recent("2024-10-01", months=6, ref=REF) is False
    # exactly on the cutoff -> inclusive
    assert is_recent((REF - datetime.timedelta(days=180)).isoformat(), months=6, ref=REF) is True


def test_unparseable_kept():
    # missing/garbage dates are kept (return True), not silently dropped
    assert is_recent("", months=6, ref=REF) is True
    assert is_recent(None, months=6, ref=REF) is True
