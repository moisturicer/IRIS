"""
The AI answer a paper carries (ADR-054 decisions 9 and 10, IR-791).

A paper follows its **Contact person's** answer to "may AI use my papers?", copied
onto it once, when its draft is created, and kept (`Record.ai_consent`). Nothing
here reads a person's answer later: a Yes that becomes a No, a No that becomes a
Yes, a new Contact person -- none of them moves the paper, except the single act
ADR-054 decision 13 allows, `apps.accounts.ai_answer.change_ai_answer`.

**Fail closed.** A person who has not answered the notice has nothing to copy, so
the paper stores nothing (`None`) and the disclosure gate refuses it. An answer is
never guessed: the data notice blocks every request but answering until it is
answered, so in practice a draft is only ever created by someone who has.
"""

from __future__ import annotations

from .models import Record


def answer_of(user) -> bool | None:
    """`user`'s last answer to the notice: True, False, or None when unanswered.

    `ai_consent` alone is not enough to say answered: it mirrors the latest answer
    row, and `answered_notice_version` says whether there is one.
    """
    if user is None or user.answered_notice_version is None:
        return None
    return user.ai_consent


def store_on_new_draft(record: Record, contact) -> bool | None:
    """Copy `contact`'s answer onto the draft just created, and return it.

    Called once per draft, where the draft and its Contact person (primary owner)
    first exist together. Writes only the one column, so it never races a workflow
    save, and writes nothing when there is no answer to copy.
    """
    answer = answer_of(contact)
    if answer is None:
        return None
    record.ai_consent = answer
    Record.objects.filter(pk=record.pk).update(ai_consent=answer)
    return answer
