"""Today's date and what "recent" means, worked out in code (IR-1316, ADR-049)."""

from __future__ import annotations

import re
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


def without(text: str, days) -> str:
    """`text` with these days removed however they are written, so their numbers are not read as findings."""
    for day in days:
        month = rf"(?:{day:%B}|{day:%b}|Sept)\.?" if day.month == 9 else rf"(?:{day:%B}|{day:%b})\.?"
        number, year = rf"0?{day.day}(?:st|nd|rd|th)?", rf"(?:,?\s+{day.year})?"
        text = re.sub(rf"\b(?:{day.isoformat()}|{month}\s+{number}{year}|{number}\s+{month}{year})(?!\w)",
                      " ", text, flags=re.I)
    return text
