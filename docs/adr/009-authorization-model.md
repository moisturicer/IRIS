# ADR-009: Authorization model and `is_staff` semantics

## Status

Accepted — 2026-09-01

## Context

IRIS enforces role-based access across six roles (Student, Adviser, RDCO, KTTO, ITSO, IERC) and object-level ownership on records, documents and files. `core/permissions.py` declares eleven permission classes, of which five are referenced nowhere.

Auditing the working tree found **twelve endpoints with no object-level authorization**, one unauthenticated file-serving route, and a privilege-escalation path:

**Missing object-level checks.** `RecordViewSet.get_queryset()` applies its visibility filter only to the `list` action (`records/views.py:50-58`), while `get_permissions()` returns bare `IsAuthenticated` for `retrieve` — so any authenticated user can read any record by primary key, including other users' drafts and in-review submissions. Six `documents/` endpoints omit ownership checks, `RecordFileDownloadAllView` (`documents/views.py:399`) has none at all, and six `storage/` endpoints are entirely unguarded.

**Unauthenticated media.** `frontend/nginx.conf:52-56` serves the media volume as static files, so every uploaded PDF is reachable at `/media/documents/<filename>` with no authentication, bypassing every check in `documents/views.py`.

**Privilege escalation.** Migration `accounts/0005` sets `is_staff=True` for RDCO, KTTO, ITSO and IERC. `core/permissions.py:23-25` defines `is_django_staff()` as `is_superuser or is_staff`. `IsAdmin` evaluates `is_django_staff(user) or role in ADMIN_ROLES` where `ADMIN_ROLES = {KTTO, RDCO}` — so `ADMIN_ROLES` constrains nobody. ITSO and IERC accounts consequently gain role assignment, account locking, session revocation and system settings. The same helper short-circuits `_can_review()` (`reviews/services.py:76-79`) and `_can_submit_clearance()`, so any office can approve at any stage — including RDCO's final publication.

**Duplication.** The four-line owner-or-staff check is hand-written at `documents/views.py:226, 302, 336, 378` and in a fifth spelling at `reviews/views.py:183-192`, while `IsOwnerOrStaff` exists and is used twice.

This directly violates **NFR-S4**: *"no authenticated user can view, modify, approve, or export records belonging to a workflow tier above their assigned role, with permissions enforced server-side on every API call independent of client-side UI state."*

## Decision

**1 · Object-level authorization is enforced through `core.permissions`, not per-view.** `IsOwnerOrStaff` replaces all five hand-written copies. Record visibility becomes a queryset scope, `Record.objects.visible_to(user)`, applied to **every** action rather than only `list`.

**2 · IRIS office roles are not Django administrators.** `is_django_staff` is removed from `IsAdmin` and from both workflow predicates. `IsAdmin` means `role in ADMIN_ROLES or is_superuser`. Office-role authorization is by role name and workflow stage, never by the Django `is_staff` flag. A migration reverses `is_staff` for ITSO and IERC; `admin/` is gated behind superuser.

**3 · Uploaded media is never served by nginx.** The `/media/` location is removed. Files are served only through the authenticated Django endpoints that already exist.

**4 · Nothing is exposed publicly until 1–3 hold.** The Weeks 1–2 validation deployment is gated on these, with synthetic and already-published data only.

**5 · Client-side role checks are UX only.** `ProtectedRoute`'s own docstring is already correct on this point. No frontend change mitigates any server-side gap.

## Alternatives Considered

**Fix the twelve endpoints individually, leave the pattern.** Rejected. The thirteenth endpoint would ship unchecked — the same way these twelve did. The duplication *is* the defect.

**`django-guardian` for per-object ACLs.** Rejected. This is role-and-ownership logic, not arbitrary ACLs. It would add a table and a dependency for rules that fit in ~60 lines.

**Keep the `is_staff` bypass and rely on the audit log.** Rejected. Audit is detective, not preventive, and review decisions are not currently audited at all (see `W-04`).

**Serve media via nginx with signed URLs.** Deferred, not rejected. `X-Accel-Redirect` with Django performing authorization is the right answer if streaming performance becomes a concern; it is not needed at pilot scale.

**Accept the status quo for the pilot.** Rejected. A real institution loads data in Week 11.

## Decision Rationale

The seam already exists and was routed around. Twelve missing checks are not twelve independent mistakes — they are one structural absence, repeated. Centralising is what prevents recurrence; the individual fixes only address the instances found today.

The `is_staff` decision resolves a genuine conflation. Migration 0005's rationale — making `IsStaff` work via both role name and Django flag — was reasonable in isolation, but combined with `is_django_staff` as a bypass it dissolves the separation of duties that the four-office model exists to enforce. **The workflow is the thesis contribution; an authorization model that lets any office approve at any stage undermines the claim as well as the security.**

## Consequences

**Positive.** NFR-S4 becomes satisfiable and testable. Separation of duties is enforced rather than assumed. Public deployment becomes safe.

**Negative.** ITSO and IERC accounts lose capabilities they may currently rely on. **This requires team and stakeholder communication before it lands, not after.**

**Risk.** Over-restriction breaking legitimate reviewer access. Mitigated by `T-02`'s role × endpoint × ownership matrix test, written alongside the fixes rather than after.

## MVP Impact

**MVP Blocker, P0** for items 1, 3 and 4 (~5 dev-days, Weeks 1–3). **P1** for item 2 (~1 dev-day, Weeks 4–7).

## SaaS Impact

Under ADR-005 the cross-tenant dimension is structural, so this ADR governs only intra-institution authorization. If pooled multi-tenancy is ever adopted, every rule here acquires a tenant dimension — recorded in `SA-03`.

## Security Impact

Defining. Closes four defects exploitable by any account that completes signup, plus one privilege-escalation path.

## Deployment Impact

The nginx change requires a frontend image rebuild. Gates the Weeks 1–2 public deployment.

## Research Impact

Indirect but real: an unenforced separation of duties would undermine the workflow contribution's credibility at defence.

## Related Requirements

**NFR-S4** (role boundary enforcement) · NFR-S2 · NFR-S5 · FR-M6-03 · FR-M2-01/02/03.

## Related Tasks

`S-01`…`S-05`, `B-06` (queryset scopes), `T-02` (regression suite), `V-07` (validation). See [`05-security.md`](../architecture-tasks/05-security.md).
