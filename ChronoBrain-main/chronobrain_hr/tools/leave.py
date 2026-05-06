from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional


def _parse_date(d: str) -> date:
    """
    Accepts ISO-like: YYYY-MM-DD.
    """
    return datetime.strptime(d.strip(), "%Y-%m-%d").date()


def working_days_between(start: date, end: date, *, weekend: set[int] | None = None, holidays: Iterable[date] = ()) -> int:
    """
    Counts working days in [start, end] inclusive, excluding weekends and holidays.
    weekend uses Python weekday(): Monday=0 ... Sunday=6.
    Default weekend = {5,6} (Sat/Sun).
    """
    if end < start:
        start, end = end, start
    weekend = weekend or {5, 6}
    holiday_set = set(holidays)
    d = start
    n = 0
    while d <= end:
        if d.weekday() not in weekend and d not in holiday_set:
            n += 1
        d += timedelta(days=1)
    return n


@dataclass(frozen=True)
class LeaveBalanceResult:
    start_date: date
    as_of: date
    entitlement_per_year: float
    accrued_days: float
    taken_days: float
    carryover_days: float
    balance_days: float


def calculate_leave_balance(
    *,
    start_date: str,
    as_of: str,
    entitlement_per_year: float,
    taken_days: float = 0.0,
    carryover_days: float = 0.0,
    accrual: str = "monthly",
) -> LeaveBalanceResult:
    """
    Generic accrual calculator (policy-agnostic):
    - monthly: accrues entitlement_per_year / 12 for each *completed* month employed in the year of `as_of`.
    - daily: accrues entitlement_per_year / 365 for each day employed in the year of `as_of`.

    Notes:
    - This does NOT enforce local labor-law rounding rules; it returns floats.
    - If your transcripts define a specific rule (rounding, waiting period, etc.), the agent will cite it.
    """
    sd = _parse_date(start_date)
    ao = _parse_date(as_of)
    if ao < sd:
        raise ValueError("as_of must be >= start_date")

    year_start = date(ao.year, 1, 1)
    employed_start = max(sd, year_start)

    if accrual == "daily":
        days_employed = (ao - employed_start).days + 1
        accrued = (entitlement_per_year / 365.0) * days_employed
    elif accrual == "monthly":
        # Count completed months between employed_start and as_of within the as_of year.
        # Example: as_of = 2026-04-07 -> completed months: Jan, Feb, Mar (3) if employed_start <= Jan 1
        m_start = employed_start.month
        y = ao.year
        completed_months = 0
        for m in range(m_start, ao.month):
            completed_months += 1
        # If employed_start is not the 1st, first month isn't fully completed.
        if employed_start.day != 1 and completed_months > 0:
            completed_months -= 1
        if completed_months < 0:
            completed_months = 0
        accrued = (entitlement_per_year / 12.0) * completed_months
    else:
        raise ValueError("accrual must be 'monthly' or 'daily'")

    balance = carryover_days + accrued - taken_days
    return LeaveBalanceResult(
        start_date=sd,
        as_of=ao,
        entitlement_per_year=float(entitlement_per_year),
        accrued_days=float(accrued),
        taken_days=float(taken_days),
        carryover_days=float(carryover_days),
        balance_days=float(balance),
    )

