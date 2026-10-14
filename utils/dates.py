"""
Shared date-boundary helpers for gating "actual" KPI/chart calculations to
only fully-complete weeks.

Weeks in the underlying data actually run Monday -> Sunday -- confirmed from
contact_analysis_dash.week_start, whose values land on Mondays, with the
newest row's contact-count columns NULL until that week is over. So a week's
data can't be trusted as complete until the Sunday it ends on has passed --
and on that Sunday itself, the following Monday's backfill run may not have
finished yet, so the boundary falls back one additional week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def most_recent_past_sunday(today: date | None = None) -> date:
    """
    Return the Sunday ending the most recently completed Mon-Sun week,
    except when `today` itself is that Sunday -- in that case the backfill
    run for this week (which fires the following Monday) may still be
    pending, so fall back to the Sunday before.
    """
    today = today or date.today()
    days_since_sunday = (today.weekday() + 1) % 7  # Mon=1 ... Sat=6, Sun=0
    if days_since_sunday == 0:
        days_since_sunday = 7
    return today - timedelta(days=days_since_sunday)


def last_complete_week_end(today: date | None = None) -> date:
    """The last day (a Sunday) of the most recent fully-complete Mon-Sun week."""
    return most_recent_past_sunday(today)


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def resolve_complete_week_range(
    start_date: str | date | None,
    end_date: str | date | None,
    today: date | None = None,
) -> tuple[str, str] | None:
    """
    Snap a free-form date-range selection to whole Monday-Sunday weeks, clamped
    to weeks that are fully complete, so every query run against the range --
    whether against the raw contact table (exact-day filtering) or the weekly
    aggregate (week_start bucketing) -- covers the exact same calendar weeks
    and their totals foot to the same number.

    Returns None when no complete week overlaps the selection at all (e.g. a
    range that only reaches into the still-open current week), so callers can
    render a "Data Pending" state instead of mixing a zeroed-out aggregate
    figure with a raw-table count that quietly includes in-progress-week
    activity.

    Only for free-form ranges with no calendar-anchor meaning to preserve
    (dashboard filters) -- both ends may shift. Calendar-anchored periods
    (month-to-date, year-to-date) must not snap their start backward across
    the anchor; see period_to_date_ready() for those instead.
    """
    cutoff = last_complete_week_end(today)  # a Sunday

    end = cutoff if end_date is None else min(_as_date(end_date), cutoff)
    snapped_end = end + timedelta(days=6 - end.weekday())

    start = snapped_end - timedelta(days=6) if start_date is None else _as_date(start_date)
    snapped_start = start - timedelta(days=start.weekday())

    if snapped_start > snapped_end:
        return None
    return str(snapped_start), str(snapped_end)


def clamp_range_end(
    start_date: str | date | None,
    end_date: str | date | None,
    today: date | None = None,
) -> tuple[str, str] | None:
    """
    Clamp only the end of a free-form range to the last fully-complete week,
    leaving the start exactly as picked. For raw-table-sourced metrics (exact-
    day precision, e.g. Unique Contacts, Contacts by Frequency) that have no
    need to snap to whole-week granularity the way the aggregate table does.

    Unlike resolve_complete_week_range(), this never widens the range
    backward -- so picking a start date mid-week can't silently absorb an
    earlier, unrelated high-activity stretch the user never asked to see (an
    arbitrary Saturday start snapping back to include the preceding Mon-Fri
    could otherwise inflate a raw-table count several times over).

    Returns None when the clamped end falls before the start -- i.e. the whole
    selection sits inside the still-open current week -- so callers can render
    the same "Data Pending" state used for resolve_complete_week_range().
    """
    cutoff = last_complete_week_end(today)  # a Sunday

    end = cutoff if end_date is None else min(_as_date(end_date), cutoff)
    start = end - timedelta(days=6) if start_date is None else _as_date(start_date)

    if start > end:
        return None
    return str(start), str(end)


def period_to_date_ready(anchor_start: str | date, today: date | None = None) -> bool:
    """
    True once the first Mon-Sun week starting on/after anchor_start has fully
    landed in the weekly aggregate -- i.e. there's at least one full week of
    *this period's* data, not just a few trailing days of the previous
    period's boundary week bleeding across the anchor.

    For a month/year that doesn't start on a Monday, the boundary week
    (spanning the anchor date) is always excluded from aggregate-sourced
    totals -- its week_start falls before anchor_start -- so gating on "any
    overlap" would let a period-to-date figure through while still missing
    those leading days. Use this for calendar-anchored periods (month-to-date,
    year-to-date); use resolve_complete_week_range() for free-form ranges.
    """
    anchor = _as_date(anchor_start)
    cutoff = last_complete_week_end(today)
    first_monday = anchor + timedelta(days=(7 - anchor.weekday()) % 7)
    return cutoff >= first_monday + timedelta(days=6)


# -- Program months ------------------------------------------------------------
#
# Goals are benchmarked monthly but data lands weekly. A "program month" is
# the set of Mon-Sun weeks whose week_start Monday falls in that calendar
# month (so 4 or 5 weeks) -- the same rule nation_goal_calendar_org uses when
# it posts each month's goal lump, and the same key contact_analysis_dash_org
# is bucketed on. Filtering week_start to a month's calendar bounds therefore
# lines actuals and goals up on exactly the same weeks.


def mondays_in_month(year: int, month: int) -> list[date]:
    """The week_start Mondays belonging to a program month."""
    d = date(year, month, 1)
    d += timedelta(days=(7 - d.weekday()) % 7)
    weeks = []
    while d.month == month:
        weeks.append(d)
        d += timedelta(days=7)
    return weeks


def parse_ym(value: str) -> tuple[int, int]:
    """'2026-09' -> (2026, 9)."""
    y, m = str(value)[:7].split("-")
    return int(y), int(m)


def month_span(from_ym: str, to_ym: str) -> list[tuple[int, int]]:
    """Every (year, month) from from_ym through to_ym inclusive (swapped if reversed)."""
    a, b = sorted([parse_ym(from_ym), parse_ym(to_ym)])
    months = []
    y, m = a
    while (y, m) <= b:
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def _shift_months(ym: tuple[int, int], n: int) -> tuple[int, int]:
    idx = ym[0] * 12 + (ym[1] - 1) - n
    return idx // 12, idx % 12 + 1


def _ym_label(ym: tuple[int, int]) -> str:
    return date(ym[0], ym[1], 1).strftime("%b %Y")


@dataclass(frozen=True)
class MonthPeriod:
    """
    A run of program months clamped to fully-complete weeks.

    start/end bound week_start the same way the free-form helpers above do
    (start is a Monday, end is the Sunday closing the last complete week), so
    they drop straight into the existing `week_start >= start` /
    `week_start <= end` filters.
    """
    months: tuple[tuple[int, int], ...]
    start: str
    end: str
    last_month_weeks_complete: int
    last_month_weeks_total: int

    @property
    def partial(self) -> bool:
        """True when the last month in the period is still in progress."""
        return self.last_month_weeks_complete < self.last_month_weeks_total

    @property
    def label(self) -> str:
        if len(self.months) == 1:
            return _ym_label(self.months[0])
        return f"{_ym_label(self.months[0])} - {_ym_label(self.months[-1])}"

    @property
    def pace_note(self) -> str:
        """e.g. 'Oct 2026: 1 of 4 weeks complete', or '' for a closed period."""
        if not self.partial:
            return ""
        return (
            f"{_ym_label(self.months[-1])}: {self.last_month_weeks_complete} of "
            f"{self.last_month_weeks_total} weeks complete"
        )


def _period_bounds(months: list[tuple[int, int]], last_month_weeks: int | None) -> tuple[str, str] | None:
    """week_start bounds over `months`, keeping only the first `last_month_weeks`
    weeks of the final month (None = all of them)."""
    weeks = [w for ym in months[:-1] for w in mondays_in_month(*ym)]
    last = mondays_in_month(*months[-1])
    weeks += last if last_month_weeks is None else last[:last_month_weeks]
    if not weeks:
        return None
    return str(weeks[0]), str(weeks[-1] + timedelta(days=6))


def resolve_month_period(from_ym: str, to_ym: str, today: date | None = None) -> MonthPeriod | None:
    """
    Resolve a From/To month selection to its complete weeks. Weeks that haven't
    fully landed yet are dropped, so an in-progress final month contributes
    only its complete weeks (callers pro-rate that month's goal to match).

    Returns None when no week in the selection is complete yet, so callers can
    render the same "Data Pending" state as resolve_complete_week_range().
    """
    cutoff = last_complete_week_end(today)
    months = month_span(from_ym, to_ym)
    complete = [w for ym in months for w in mondays_in_month(*ym) if w + timedelta(days=6) <= cutoff]
    if not complete:
        return None
    last = mondays_in_month(*months[-1])
    return MonthPeriod(
        months=tuple(months),
        start=str(complete[0]),
        end=str(complete[-1] + timedelta(days=6)),
        last_month_weeks_complete=sum(1 for w in last if w + timedelta(days=6) <= cutoff),
        last_month_weeks_total=len(last),
    )


def prior_month_period(period: MonthPeriod) -> tuple[str, str, str] | None:
    """
    (start, end, label) of the comparison period for `period`:

      - a multi-month run starting in January (year to date) -> the same
        months a year earlier ("vs same period 2025")
      - anything else -> the same number of months immediately before it

    If `period`'s last month is still in progress, the comparison's last month
    is cut to the same number of weeks, so a partial month is never compared
    against a whole one.
    """
    months = list(period.months)
    n = len(months)
    if n > 1 and months[0][1] == 1:
        prior = [(y - 1, m) for y, m in months]
        label = f"vs same period {prior[0][0]}"
    else:
        prior = [_shift_months(ym, n) for ym in months]
        label = f"vs {_ym_label(prior[0])}" if n == 1 else f"vs prior {n} months"

    keep = period.last_month_weeks_complete if period.partial else None
    if keep is not None and n == 1:
        label += f", first {keep} wk{'s' if keep != 1 else ''}"

    bounds = _period_bounds(prior, keep)
    if bounds is None:
        return None
    return bounds[0], bounds[1], label
