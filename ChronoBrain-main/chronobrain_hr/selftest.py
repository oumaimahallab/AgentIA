from __future__ import annotations

from datetime import date

from .tools.leave import calculate_leave_balance, working_days_between


def main() -> int:
    # Working days sanity
    wd = working_days_between(date(2026, 7, 1), date(2026, 7, 12))
    assert wd >= 0

    # Leave balance sanity
    res = calculate_leave_balance(
        start_date="2025-09-15",
        as_of="2026-04-07",
        entitlement_per_year=25,
        taken_days=6,
        carryover_days=0,
        accrual="monthly",
    )
    assert res.balance_days == (res.carryover_days + res.accrued_days - res.taken_days)
    print("selftest ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

