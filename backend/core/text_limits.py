"""Length limits for what people write into IRIS (IR-926, ASVS 5.2.2).

The free-text fields that had no limit are checked on the server before they
are stored (the list is in docs/testing/traceability/IR-926.md). Without one,
an abstract of 2,000,000 characters was accepted, stored, drawn on Paper View,
embedded and sent to AI vendors.

10,000 characters was chosen by Ashlee Sean on 2026-11-15, the same as a review
comment (`apps/reviews/comments.py`): far above any real abstract, reason or
message, and small enough that one field can't flood a page or a model call.
Fields that already had their own limit keep it: questions 2,000, public
comments 2,000, RDCO's reasons 1,000, reading notes 20,000, the notice 50,000.
"""

FREE_TEXT_MAX_LENGTH = 10_000


def too_long(text) -> bool:
    return isinstance(text, str) and len(text) > FREE_TEXT_MAX_LENGTH


def too_long_message(what: str) -> str:
    return f"{what} can be at most {FREE_TEXT_MAX_LENGTH:,} characters."
