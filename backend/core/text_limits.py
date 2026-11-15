"""Length limits for what people write into IRIS (IR-926, ASVS 5.2.2).

Every free-text field a person fills in is checked on the server before it is
stored. Without a limit an abstract of 2,000,000 characters was accepted,
stored, drawn on Paper View and, for abstracts, embedded and sent to AI
vendors.

10,000 characters was chosen by Ashlee Sean on 2026-11-15, the same as a review
comment (`apps/reviews/comments.py`): far above any real abstract, reason or
message, and small enough that one field can't flood a page or a model call.
Fields that already had a tighter limit (questions, notes, public comments,
RDCO's reasons) keep theirs.
"""

FREE_TEXT_MAX_LENGTH = 10_000


def too_long(text) -> bool:
    return isinstance(text, str) and len(text) > FREE_TEXT_MAX_LENGTH


def too_long_message(what: str) -> str:
    return f"{what} can be at most {FREE_TEXT_MAX_LENGTH:,} characters."
