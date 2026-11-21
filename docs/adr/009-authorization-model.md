# ADR-009: Authorization model and `is_staff` semantics

## Status

Accepted — 2026-09-01

[ADR-051](051-system-admin-account-deletion-and-consent.md), Accepted 2026-11-01 and built for this part by IR-781 (corrected 2026-11-07, IR-968), adds a seventh role, the System Admin, and moves the Audit Log and system settings to it. It keeps decision 2: Django's `is_staff` and `is_superuser` grant nothing in this API.

*Amended 2026-11-19 (IR-1227): an unsubmitted draft is its creator's alone* (decision 6). Proposed with IR-1227's PR, decided by Hermoine Zozobrado. It is accepted when that PR merges, and it needs Ashlee Sean's security review.

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

**6 · An unsubmitted draft is its creator's alone** (*Amendment, 2026-11-19, IR-1227*). A record whose `pipeline_status` is `draft` is one its submitter started in the Publish form and has not submitted. Only the account that created it reads it (`Record.added_by`, set when Publish creates the draft and when someone continues a Proposal). Everyone else gets the answer a missing record gets, a 404 that confirms nothing (IR-153):
    - the co-owners it names: anyone added under the Publish form's owner emails (`owner_emails`, changeable only on a draft), and, on a continuation, the Proposal's owners, whom it copies;
    - office staff (KTTO, RDCO, ITSO, IERC);
    - the Adviser the draft names;
    - the System Admin and every other user.

  Only a submitted record reaches its co-owners, the Adviser, RDCO or an office pool. *Decided by Hermoine Zozobrado on 2026-11-19*: the card's own wording, "a draft has exactly one owner", was wrong (co-owners are named before submission), and the rule is the creator, not every owner. The creator is not always the primary owner, the Contact person, since a continuation copies the Proposal's.
- **What it corrects.** Until now `visible_to` gave office staff every record and the named Adviser their record, drafts included. Lists already left drafts out (Discover, the review queues, the office consoles), so only a direct open by link or id reached one. The documents rules (`owns_or_staffs_record`, `may_read_record_documents`, `may_read_embargo`) had the same office and Adviser grounds, as did the AI runtime's copy of the rule in PostgreSQL, `iris_authz.research_record_ids()` (`ai/0035`).
- **The rule is one predicate in three places, and they move together.** `Record.objects.visible_to` gives a draft to its creator alone and puts every other ground, ownership included, behind "not a draft". `core.permissions.hides_draft(user, record)` says the same for the documents rules, and the document routes answer a hidden draft with the same 404 as a missing record, not their usual 403. The AI runtime's function is replaced by a migration with the same condition, so a citation can never point at a draft for anyone but its creator. That function now reads `records_record.added_by_id`, which `provision_research_roles` grants its verifier, so the command must be run again after `migrate`, as deployment already does. Until it is, research reads fail closed with a permission error.
- **The owner's own lists follow it.** `Record.objects.owned_by(user)` is a person's records minus the drafts someone else created. My submissions (`records/mine/`) and the dashboard's counts read it, so a co-owner neither sees nor counts a draft they cannot open. The office-only route that queues one record for indexing (`POST /ai/embed/<id>/`) now answers a record its caller cannot read as a missing one; it used to queue a draft and fail on a missing id, which told the two apart.
- **Unchanged.**
    - After Submit, the record reads exactly as before: its Adviser at once, then the offices it is routed to and RDCO.
    - A record sent back for revision is in review, not a draft, so nobody loses it.
    - Django's own admin site (`/admin/`, superusers only by decision 2) reads the database directly and still shows every row. It is not part of the app's authorization, and this decision leaves it as it is.
    - Deleting a draft stays its creator's (IR-508), since nobody else reaches it.
    - The System Admin's Audit Log still lists a draft's events, such as its creator's upload, with the record's id and title. It records what was done and opens nothing. *Decided by Hermoine Zozobrado, 2026-11-19: leave it.*
- **Consequences.**
    - Deleting a draft tells nobody. IR-517 told its other owners, but a co-owner never saw the draft, and the message would name it. A rejected record's owners are still told.
    - Deleting an account deletes the drafts it created, even ones that name co-owners, who could never open them. A draft someone else created stays theirs. ADR-051's account deletion deleted a draft only when it had no other owner.
    - The duplicate check offers *resume your draft* to the draft's creator alone.
    - The manuscript duplicate check (`records.duplicates`) reads through `visible_to`, so it no longer reports someone else's draft of the same file to an Adviser or an office account. It never could to a student.
    - Nothing in the app relied on reading another person's draft. Every list already filters drafts out. Notifications reach the Adviser and the offices only at Submit or later, and comments and mentions already refuse a draft. `seed_demo`'s draft is opened only by its creator.
- **Presentation** (part of the same decision). A draft is not shown as a paper page. Its creator opening `/records/<id>`, including an old link to `?section=review`, lands in the Publish form at the step they left off (`/?publish=<id>`). Closing the Publish form asks what to do with the work:
    - with a draft saved (*Leave this submission?*): **Keep as draft** (the default), **Delete draft**, confirmed once, and **Keep editing**. *Amended 2026-11-21 (IR-1256):* the confirmation is a dialog over the form, the one My Library uses (*Delete this draft?* "“<title>” and its files will be removed. It can't be restored.", Cancel focused), and Cancel returns to *Leave this submission?*;
    - with entries but no manuscript yet, so nothing saved (*Discard what you've entered?*): **Discard** and **Keep editing**;
    - while a file uploads, the existing *Stop the upload and close?*;
    - with nothing entered, it simply closes.
- *Rejected: an escape hatch for the System Admin or a superuser.* Nobody but its creator has a reason to read a paper they have not submitted, and support can ask the author.
- *Rejected: creating the draft on the first answer*, so that closing has one case. It would leave empty drafts in My submissions, and creating the draft at upload is what titles it from the file and runs the duplicate search.

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

**Decision 6 (2026-11-19).** It narrows reading for co-owners, office staff and Advisers, and only on records nobody has submitted yet. The capability table's `draft` row and the HTTP tests in `apps/records/test_draft_visibility.py` pin who still reads.

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
