"""The named AGENT responsibility (IR-727, ADR-049 §13, §14).

One model Conversation per run, pinned to one model, endpoint, dialect and
set of prompt/tool/public/state versions. The tool loop is IR-728.
"""
