"""Today's date and what "recent" means, worked out in code (IR-1316, ADR-049)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

#: The Philippines keeps no daylight saving time.
MANILA = timezone(timedelta(hours=8))
#: This year and the four before it, for completion and publication years.
RECENT_YEARS = 5
#: Days back from today, for the date a paper was added.
RECENT_DAYS = 90


def today() -> date:
    return datetime.now(MANILA).date()


def window(day: date) -> dict:
    """Today and the ranges "recent" names, as the model is told them."""
    return {
        "today": day.isoformat(),
        "recent_years": {"from": day.year - RECENT_YEARS + 1, "to": day.year},
        "recent_added": {"from": (day - timedelta(days=RECENT_DAYS)).isoformat(), "to": day.isoformat()},
    }


def parts(day: date) -> set[str]:
    """The numbers a written date states."""
    return {str(day.year), str(day.month), str(day.day)}
