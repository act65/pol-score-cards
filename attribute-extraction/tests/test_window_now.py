"""Starting late must join tonight's window, not forfeit it.

On 2026-09-17 the machine booted at 23:09, nine minutes into a 23:00-06:00
window. `_next("23:00")` returned tomorrow, so the scheduler slept 23.85h with
6.8 usable hours sitting there. One night lost to nine minutes.
"""
import datetime as dt

import pytest

import tonight


def _at(y, m, d, hh, mm=0):
    return dt.datetime(y, m, d, hh, mm)


def test_before_the_window_waits_for_it():
    start, stop = tonight._window_now("23:00", "06:00", _at(2026, 9, 17, 20, 0))
    assert start == _at(2026, 9, 17, 23, 0)
    assert stop == _at(2026, 9, 18, 6, 0)


def test_nine_minutes_late_joins_tonight():
    """The actual bug."""
    now = _at(2026, 9, 17, 23, 9)
    start, stop = tonight._window_now("23:00", "06:00", now)
    assert start == now
    assert stop == _at(2026, 9, 18, 6, 0)
    assert (stop - start).total_seconds() / 3600 == pytest.approx(6.85, abs=0.01)


def test_after_midnight_still_joins_the_window_that_began_yesterday():
    """03:00 is inside a window that started at 23:00 the previous day — the
    midnight wrap is where an off-by-one day would hide."""
    now = _at(2026, 9, 18, 3, 0)
    start, stop = tonight._window_now("23:00", "06:00", now)
    assert start == now
    assert stop == _at(2026, 9, 18, 6, 0)


def test_just_after_the_window_closes_waits_for_the_next_one():
    start, stop = tonight._window_now("23:00", "06:00", _at(2026, 9, 18, 6, 1))
    assert start == _at(2026, 9, 18, 23, 0)
    assert stop == _at(2026, 9, 19, 6, 0)


def test_the_closing_instant_is_not_inside_the_window():
    """06:00 exactly is the end, not 0 seconds of usable night."""
    start, _ = tonight._window_now("23:00", "06:00", _at(2026, 9, 18, 6, 0))
    assert start == _at(2026, 9, 18, 23, 0)


def test_a_same_day_window_does_not_wrap():
    """A daytime window (09:00-17:00) must not be read as crossing midnight."""
    start, stop = tonight._window_now("09:00", "17:00", _at(2026, 9, 18, 10, 0))
    assert start == _at(2026, 9, 18, 10, 0)
    assert stop == _at(2026, 9, 18, 17, 0)

    start, stop = tonight._window_now("09:00", "17:00", _at(2026, 9, 18, 18, 0))
    assert start == _at(2026, 9, 19, 9, 0)
    assert stop == _at(2026, 9, 19, 17, 0)
