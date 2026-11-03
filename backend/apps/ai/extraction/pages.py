"""A raw result's pages for staff: confidence and watermark (IR-841).

Kept here so no caller outside extraction reads a vendor's result shape.
"""

# Provisional until IR-851's acceptance check picks a cut-off (ADR-056 decision 16).
LOW_CONFIDENCE = 0.5


def page_report(raw):
    """One line per page, least confident first."""
    pages = (raw.get("metadata") or {}).get("pages") or []

    def line(page):
        printed = page.get("printed_page_number")
        label = f"p{page['page_number']}" + (f" ({printed})" if printed else "")
        score = page.get("confidence")
        text = "unscored" if score is None else f"{score:.2f}" + (" LOW" if score < LOW_CONFIDENCE else "")
        if page.get("watermark"):
            text += f", watermark {page['watermark']}"
        return f"{label}: {text}"

    ordered = sorted(pages, key=lambda p: (p.get("confidence") is None, p.get("confidence") or 0))
    return "\n".join(line(page) for page in ordered)
