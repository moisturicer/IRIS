"""Email account recovery (ADR-045, IR-642).

`service` admits requests and consumes links, `limits` holds the shared
counters, `delivery` is the worker that issues tokens and sends mail, and
`views` is the anonymous HTTP contract. Verification resend (IR-643) reuses
these with its own purpose.
"""
