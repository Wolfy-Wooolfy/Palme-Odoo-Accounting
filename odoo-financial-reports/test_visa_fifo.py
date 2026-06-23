"""Pure-function self-check for the Visa monitor's working-day + FIFO helpers.

No Odoo connection — imports only the pure helpers from the service module and
asserts their behaviour against the discovery's worked examples, INCLUDING a
due-date that crosses a Friday (the only weekend day).

Run from the project root:  python test_visa_fifo.py
"""
from datetime import date

from api.services.visa_reconciliation import (
    LATE_WORKING_DAYS,
    is_working_day,
    oldest_unconfirmed,
    working_days_between,
)

TODAY = date(2026, 6, 23)  # the discovery's "server today" (Tue)


def _is_late(stop_at: date) -> bool:
    return working_days_between(stop_at, TODAY) > LATE_WORKING_DAYS


def test_friday_is_only_weekend():
    assert is_working_day(date(2026, 6, 20)) is True   # Saturday works
    assert is_working_day(date(2026, 6, 19)) is False  # Friday off
    assert is_working_day(date(2026, 6, 21)) is True   # Sunday works


def test_working_days_match_discovery_examples():
    # (stop_at, weekday, expected working days elapsed by 2026-06-23, expected late?)
    # Drawn verbatim from DISCOVERY_REPORT.md "§3 2-working-day due dates".
    cases = [
        (date(2026, 6, 17), "Wed", 5, True),   # POS/16217 — due 06-20 (skips Fri 06-19), PAST DUE
        (date(2026, 6, 18), "Thu", 4, True),   # POS/16246 — due 06-21, PAST DUE
        (date(2026, 6, 19), "Fri", 4, True),   # POS/16275 — closed on Friday, due 06-21, PAST DUE
        (date(2026, 6, 21), "Sun", 2, False),  # POS/16326 — due 06-23 (today), within window
        (date(2026, 6, 23), "Tue", 0, False),  # POS/16355 — due 06-25, within window
    ]
    for stop_at, _wd, expected_days, expected_late in cases:
        got = working_days_between(stop_at, TODAY)
        assert got == expected_days, f"{stop_at}: expected {expected_days} wd, got {got}"
        assert _is_late(stop_at) is expected_late, f"{stop_at}: late mismatch"


def test_due_date_crosses_friday():
    # A collection closed Thu 2026-06-18 is due Thu + 2 working days. Counting
    # 06-19 (Fri, skipped), 06-20 (Sat, wd1), 06-21 (Sun, wd2) → due 2026-06-21.
    # Measured the next day (Mon 06-22) it is exactly 2 wd old → NOT yet late;
    # measured Tue 06-23 it is 4 wd old (Fri skipped) → late. Proves the weekend
    # skip only drops Friday and that the clock keeps counting Sat/Sun.
    stop_at = date(2026, 6, 18)
    assert working_days_between(stop_at, date(2026, 6, 22)) == 3   # Thu→Sat(1)→Sun(2)→Mon(3)
    assert working_days_between(stop_at, date(2026, 6, 21)) == 2   # exactly the 2-wd due point
    assert working_days_between(stop_at, date(2026, 6, 20)) == 1   # Sat counts
    # On its due day (06-21) it is within window; one working day later it is late.
    assert working_days_between(stop_at, date(2026, 6, 21)) <= LATE_WORKING_DAYS
    assert working_days_between(stop_at, date(2026, 6, 23)) > LATE_WORKING_DAYS


def test_fifo_consumes_oldest_first():
    # Three collections, confirmations cover the first 1.5 of them.
    collections = [
        (date(2026, 6, 17), 100.0),
        (date(2026, 6, 18), 100.0),
        (date(2026, 6, 19), 100.0),
    ]
    # 150 confirmed → fully covers 06-17, partially 06-18 → oldest unconfirmed = 06-18.
    assert oldest_unconfirmed(collections, 150.0) == date(2026, 6, 18)
    # 0 confirmed → oldest unconfirmed is the very first collection.
    assert oldest_unconfirmed(collections, 0.0) == date(2026, 6, 17)
    # Everything confirmed → nothing unconfirmed.
    assert oldest_unconfirmed(collections, 300.0) is None
    # Tiny rounding slack still counts as fully covered.
    assert oldest_unconfirmed(collections, 299.995) is None


def test_fifo_plus_working_day_late_decision():
    # Branch confirmed 120 of three 100-EGP days (06-17/18/19). FIFO leaves the
    # 06-18 day as oldest unconfirmed; on 2026-06-23 that is 4 working days old → LATE.
    collections = [
        (date(2026, 6, 17), 100.0),
        (date(2026, 6, 18), 100.0),
        (date(2026, 6, 19), 100.0),
    ]
    oldest = oldest_unconfirmed(collections, 120.0)
    assert oldest == date(2026, 6, 18)
    assert _is_late(oldest) is True

    # A fresh branch: only today's collection unconfirmed → within window, not late.
    fresh = [(date(2026, 6, 23), 500.0)]
    oldest_fresh = oldest_unconfirmed(fresh, 0.0)
    assert oldest_fresh == date(2026, 6, 23)
    assert _is_late(oldest_fresh) is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\nAll {len(tests)} Visa FIFO / working-day self-checks passed.")
