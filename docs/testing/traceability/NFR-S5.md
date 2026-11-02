# NFR-S5

[Back to the matrix](../TRACEABILITY.md)

## NFR-S5

**Requirement:** Audit immutability

**Implementation:** **IR-166.** A PostgreSQL trigger (`audit/0005`) refuses every DELETE on `audit_auditevent` and every UPDATE that changes the row (compared whole, so a future column is covered too). The `user`/`record` foreign keys become `DO_NOTHING` with no database constraint in the same migration, so deleting a subject leaves its rows untouched, still carrying its id; the API shows `user_name: null` for it. Binds every client of the table, not just the ORM. INSERT is unaffected. The audit API stays list-only (`GET /audit/`, RDCO). Not covered: TRUNCATE, and the table owner dropping the trigger, which now takes a deliberate, reviewed migration

**Evidence:** `backend/apps/audit/tests/test_immutability.py` (17): ORM save, queryset update, raw SQL UPDATE, row/queryset/raw DELETE all refused and the row unchanged after; insert still works; deleting the user leaves the row exactly as it was; clearing or re-pointing the user refused; an unchanged save allowed; a deleted user's row still lists; POST/PUT/PATCH/DELETE on `/audit/` → 405 for RDCO; no detail route

**Status:** **VERIFIED (IR-166, 2026-10-29).** CI run 40794738484 on `91a79b0`, merged as PR #307: all 17 tests above pass against real PostgreSQL, within 4298 passed, 0 failed. **Not covered**, by design: TRUNCATE, and the table owner dropping the trigger in a deliberate migration
