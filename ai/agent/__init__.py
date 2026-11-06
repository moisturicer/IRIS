"""The named AGENT responsibility (IR-727, ADR-049 §13, §14).

One model Conversation per run, pinned to one model, endpoint, dialect and
set of prompt/tool/public/state versions, which searches, reads and
answers in one bounded tool loop (IR-728).
"""
