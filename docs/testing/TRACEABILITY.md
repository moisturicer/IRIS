# Requirements Traceability

**Purpose.** The single mapping from requirement to evidence.
**Owns.** Requirement → design → implementation → test → evidence → status, for every SRS requirement.
**Does not own.** The requirements themselves ([`../SRS.md`](../SRS.md) is the only baseline) · test strategy ([`TEST_PLAN.md`](TEST_PLAN.md)).
**Authority.** **The only traceability mechanism in IRIS.** Do not create a second one.
**Update when.** Any change implements, alters or descopes a requirement — in the same PR.

---

## Status vocabulary

| Status | Means |
|---|---|
| **VERIFIED** | Implemented, tested, evidence recorded and linked |
| **IMPLEMENTED** | Code exists, **no test evidence** — not complete |
| **PARTIAL** | Some of the requirement is met |
| **STUBBED** | Placeholder exists, does not function |
| **NOT STARTED** | No implementation |
| **DEFERRED** | Formally descoped, with an ADR or SRS amendment |
| **BLOCKED** | Cannot proceed — reason recorded |

> **A requirement is never marked VERIFIED because source code exists.** IMPLEMENTED is the ceiling until a test demonstrates it and the evidence is linked.

---

## Current position

**Almost nothing in IRIS is VERIFIED.** A pytest harness landed with IR-82 and the `apps/ai` extraction and chunking work now carries tests, so the blanket "there are no automated tests" that stood here is no longer true. Everything outside `apps/ai` still has no test evidence. This table records the honest position; it is not a to-do list disguised as a status report.

> **This document is itself out of date in places** and its header still names `../SRS.md` as the baseline, which [`../../CLAUDE.md`](../../CLAUDE.md) has since frozen in favour of `docs/adr/`. Recorded rather than silently reconciled, per the source-of-truth rule. Rows below are corrected as the work that touches them lands, not in one sweep.

| Req | Requirement | Design | Implementation | Test | Evidence | Status |
|---|---|---|---|---|---|---|
| FR-M2-01 | Record submission | SDD M2 · [ui-ux/05](../ui-ux/05-submission.md) | `apps/records`, `AddRecordPage` | — | — | **IMPLEMENTED** |
| FR-M3-01 | PDF text extraction | **ADR-016** (amends ADR-006) | `apps/ai/extraction/` — `StructuredExtractor` port, `DoclingExtractor` adapter; the prototype three-tier chain is deleted (IR-107) | `apps/ai/extraction/tests/` | `pytest apps/ai/extraction` green | **IMPLEMENTED** — no production run on a real thesis yet (IR-116) |
| FR-M3-02 | Semantic indexing | ADR-013, ADR-007, ADR-015 | `apps/ai/chunking/` (domain, strategies, context path, normalizer, regions, re-chunk diff) · `apps/ai/repositories.py` (ChunkSet persistence; atomic swap behind the `one_active_chunk_set_per_record` partial unique index; incremental re-chunk with vector carry-over and `deleted_at` tombstones) · `apps/ai/ingestion/` + `models/ingestion_job.py` (lifecycle transition table, hash-derived staleness, job idempotency key) — IR-89 A–G | `apps/ai/chunking/tests/`, `apps/ai/ingestion/tests/`, `apps/ai/tests/` | `pytest apps/ai` green — zero writes on an unchanged document asserted with `CaptureQueriesContext`; one active set observed from a concurrent connection mid-swap; re-chunking a published record asserted | **PARTIAL** — chunker, persistence and the re-chunk lifecycle done; **no ingestion task joins extraction to chunking yet** (IR-116), and no vectors are computed (IR-108) |
| FR-M3-03 | Citation provenance — a retrieved passage carries the page and region it occupies in the source PDF | ADR-013 · `chunker_architecture.md` §region model | `chunking/document.py` (`BoundingBox`, per-element regions), `chunking/regions.py`, `chunking/normalizer.py`, `repositories.serialize_regions` — IR-89 E | `chunking/tests/test_regions.py`, `test_normalizer.py`, `apps/ai/tests/test_region_serialization.py` | `pytest apps/ai` green — regions asserted across every registered strategy | **IMPLEMENTED** — storage only; **the PDF.js highlight overlay is out of scope and blocked on IR-59** (`/media/` is unauthenticated) |
| FR-M4-01 | RAG query and answer | ADR-006, ADR-008 | Service stubs; `AIHubPage` shows "Coming Soon" for both modes | — | — | **STUBBED** |
| FR-M4-02 | Summarization | — | — | — | — | **DEFERRED** (ADR-001) |
| **FR-M5-01** | **Hierarchical submission workflow** | **ADR-002, ADR-003** | `reviews/services.py` — 11 guarded transitions, `RecordClearance` | — | — | **PARTIAL** — routing works; **clearance state is never serialized** |
| FR-M6-01 | Authentication | SDD M6 | `apps/accounts`, SimpleJWT | — | — | **PARTIAL** — rotation and blacklisting correct; **30-min inactivity expiry absent (NFR-S2)** |
| FR-M6-02 | DPA consent | SDD M6 | `DpaConsentGate`, `DpaConsentModal` | — | — | **IMPLEMENTED** |
| FR-M6-03 | Role-based access control | **ADR-009** | `core/permissions.py` — 11 classes, **5 referenced nowhere** | — | — | **PARTIAL** — **12 endpoints have no object-level check** |
| FR-M7-01 | KPI dashboard | — | `recharts` installed, **zero importers** | — | — | **DEFERRED** — Phase 2 in SRS §31 |
| FR-M2-06/07 | Institutional / personal storage | — | `apps/storage` — **6 unauthorized endpoints** | — | — | **DEFERRED** — removed by IR-62, needs SRS amendment |

### Non-functional

| Req | Requirement | Implementation | Evidence | Status |
|---|---|---|---|---|
| NFR-S1 | Transport security | Not yet deployed | — | **NOT STARTED** |
| NFR-S2 | 30-minute inactivity expiry | Absent | — | **NOT STARTED** |
| NFR-S3 | Secure configuration | `CORS_ALLOW_ALL_ORIGINS` with credentials; hardcoded DB credentials; `ALLOWED_HOSTS` unset | — | **NOT STARTED** |
| NFR-S4 | Server-side authorization | 12 endpoints unprotected | — | **PARTIAL** |
| NFR-S5 | Audit immutability | No DB-level guard | — | **NOT STARTED** |
| NFR-S6 | Account protection | Lockout events defined in the audit model | — | **PARTIAL** |
| NFR-P1 | 100 concurrent sessions | Untested | — | **NOT STARTED** |
| NFR-P2…P5 | Performance and processing | Untested | — | **NOT STARTED** |
| NFR-R2 | Graceful degradation | ADR-008 — `search_vector` exists and **nothing queries it** | — | **NOT STARTED** |
| NFR-R3, R4 | Reliability and recovery | No backups, no rehearsed restore | — | **NOT STARTED** |
| NFR-U1 | General usability | — | — | **NOT STARTED** |
| **NFR-U2** | **Submission in under 10 min, 5 of 5 participants** | `AddRecordPage` exists; draft/submit boundary unclear | — | **NOT STARTED** |
| NFR-U3 | Responsive at 360 px, no horizontal scroll | 14 files build raw tables; **4 `overflow-x-auto` in the whole codebase** | — | **NOT STARTED** |

---

## The audit gap

`AuditEvent` defines **14 event types — all authentication, file or account.** There is **no workflow event**: no `SUBMITTED`, no `RESUBMITTED`, no `CLEARANCE_PRESERVED`, no `STAGE_CHANGED`.

**Consequence:** the research metrics in [`../mvp-validation/03-final-evaluation-plan.md`](../mvp-validation/03-final-evaluation-plan.md) — turnaround time and preserved-clearance counts — have **no data source**.

This is the one unrecoverable item in the plan. Events not written during the Weeks 11-12 pilot cannot be reconstructed afterwards, and there is no second pilot.

---

## Maintenance

- Update this table **in the same PR** as the change that affects a requirement
- Never move a row to VERIFIED without a link to actual evidence
- If a requirement is descoped, set DEFERRED and cite the ADR or SRS amendment — do not delete the row
- Review the whole table before the technical defence; an unverified requirement reported as unverified is defensible, a false VERIFIED is not
