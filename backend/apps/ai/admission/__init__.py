"""Shared admission for paid provider attempts (IR-545, ADR-041).

Every physical attempt to a paid vendor -- a chat completion, a tool call, an
embedding or rerank request, a Jev decision; a retry or a fallback model is
another attempt -- reserves its worst-case cost in Postgres before it is
sent, against limits every web process, worker and replica shares:

* the campaign ceiling (attempts, input and output tokens, US$, active
  minutes), less a protected reserve until the budget owner releases it;
* the run's own caps, when the call belongs to a run;
* how many attempts may be in flight at once, per lane and per vendor
  account.

`limits` reads the settings, `scope` carries the lane, the run and the
attempt's usage through a call without widening any port, `ledger` makes and
settles reservations, and `llm` is the decorator around the chat adapter.

Submodules are imported by name, never re-exported here: the chat adapter
imports `scope`, and `errors` imports the adapter.
"""
