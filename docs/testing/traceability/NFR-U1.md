# NFR-U1

[Back to the matrix](../TRACEABILITY.md)

## NFR-U1

**Requirement:** General usability

**Implementation:** **IR-414 (F12) automated pre-pass**, 2026-11-01: `frontend/scripts/ir414-prepass.mjs` walked 26 screens × 5 viewports in headless Chromium, plus F6's deferred Review-section keyboard checks. It found and fixed one defect: the *Request documents* dialog left focus behind it. It found five more failures (contrast, reflow, an unlabelled textarea, unreachable scroll regions). See [`evidence/IR-414/README.md`](../evidence/IR-414/README.md)

**Evidence:** Automated only. No participant, no real device: what a browser measures, not usability

**Status:** **NOT STARTED** — the human pass and NFR-U2's rehearsal are F12's evidence; the pre-pass only feeds them
