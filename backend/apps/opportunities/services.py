"""
Calendar export for opportunities.

Hand-rolled rather than pulling in a dependency: an all-day VEVENT is a dozen
lines of a well-specified text format (RFC 5545), and the escaping rules are the
only genuinely fiddly part -- which is exactly what the tests pin.
"""
from datetime import timedelta


def _escape(text) -> str:
    """
    RFC 5545 s3.3.11 text escaping.

    Backslash is replaced first, or it would double-escape the backslashes
    introduced by the replacements after it. Commas and semicolons are value
    separators in the format, so an unescaped one in a title silently truncates
    the field or corrupts the event -- "Robotics, AI & Sensor Networks" is a
    perfectly ordinary call title that would break a naive writer.
    """
    if text is None:
        return ""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def build_ics(opportunity) -> str:
    """One all-day VEVENT on the deadline date."""
    start = opportunity.due_date
    # DTEND is exclusive for all-day events, so a one-day event ends the
    # following day. Using the same date for both renders a zero-length event
    # that several clients drop entirely.
    end = start + timedelta(days=1)

    summary = f"{opportunity.get_opportunity_type_display()}: {opportunity.title}"
    description_parts = [opportunity.description or ""]
    if opportunity.external_url:
        description_parts.append(f"Apply: {opportunity.external_url}")
    if opportunity.posting_office:
        description_parts.append(f"Posted by: {opportunity.posting_office}")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CIT-U IRIS//Calls and Conferences//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:iris-opportunity-{opportunity.pk}@cit.edu",
        f"DTSTAMP:{opportunity.created_at.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(' '.join(p for p in description_parts if p))}",
    ]
    if opportunity.external_url:
        lines.append(f"URL:{_escape(opportunity.external_url)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]

    # RFC 5545 requires CRLF line endings.
    return "\r\n".join(lines) + "\r\n"
