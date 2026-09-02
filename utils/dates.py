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
