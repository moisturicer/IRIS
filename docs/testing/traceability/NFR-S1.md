# NFR-S1

[Back to the matrix](../TRACEABILITY.md)

## NFR-S1

**Requirement:** Transport security

**Implementation:** `SECURE_PROXY_SSL_HEADER` and nginx's `$forwarded_proto` (IR-662). Proven: production settings redirect plain requests once to HTTPS, do not redirect a request the proxy marks https, and keep secure cookies; a real nginx forwards the scheme. **Not proven:** certificates, a TLS terminator and any deployed HTTPS, because the repository has none and nothing is deployed

**Evidence:** `apps/tests/test_transport_security.py`

**Status:** **PARTIAL**
