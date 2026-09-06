# 02 — Information Architecture

---

## 1 · Content model, as the user sees it

The UI vocabulary must be the institution's, not the database's.

| User concept | Backend | Notes |
|---|---|---|
| **Submission** / Record | `Record` | Say "submission" to students, "record" to staff. Both appear in CIT-U usage |
| **Type** | `RecordType` | Proposal · Thesis/Research · Project. **Determines the route** |
| **Stage** | `pipeline_status` | Institutional language, never the enum |
| **Office** | `RecordClearance.office` | ITSO · IERC · KTTO, plus RDCO as the coordinating office |
| **Clearance** | `RecordClearance.status` | An office's verdict on one record |
| **Decision** | `Review` | One reviewer action, with comment |
| **Document** | `RecordUpload` | Versioned, attached to an upload slot |
| **Requirement** | `UploadSlot` | What a record type must supply |
| **History** | `Review` + `AuditEvent` | What happened, in order |

**Terminology is per-institution configuration** ([11](11-saas-admin.md)). Another university may call an office a "committee" and a submission a "disclosure". The UI renders labels supplied by the API.

---

## 2 · The spine

The product is a workflow, and the IA should read as one.

```
SUBMIT → REVIEW → ROUTE → PARALLEL CLEARANCE → DECLINE/APPROVE
   → CLEARANCE-AWARE RESUBMISSION → COMPLETE/PUBLISH → AUDIT
```

Every MVP screen sits on that spine. Anything that does not is a candidate for removal ([15](15-mvp-ui-scope.md)).

| Spine step | Screen | Actor |
|---|---|---|
| SUBMIT | Submission wizard ([05](05-submission.md)) | Student |
| — | My submissions ([04](04-dashboard.md)) | Student |
| REVIEW / ROUTE | Review queue ([07](07-review-clearance.md)) | Adviser, RDCO |
| PARALLEL CLEARANCE | Record detail + Clearance Track ([06](06-record-detail.md), [08](08-workflow-resubmission.md)) | Offices |
| DECLINE / APPROVE | Decision screen ([07](07-review-clearance.md)) | Reviewer |
| RESUBMISSION | Record detail — decline banner + resubmission panel ([08](08-workflow-resubmission.md)) | Student |
| COMPLETE / PUBLISH | Record detail | RDCO |
| AUDIT | Audit log ([10](10-audit-history.md)) | RDCO |
| *(supporting)* | Search / AI ([09](09-search-rag.md)) | All |

---

## 3 · Screen map

**16 MVP screens.** Full KEEP/REDUCE/DEFER/REMOVE reasoning in [15](15-mvp-ui-scope.md).

```
PUBLIC
  /login · /signup · /activate/:uid/:token · /pending-approval

AUTHENTICATED
  /                       Home — role-aware landing
  /records                Published records (browse + search)
  /records/add            Submission wizard
  /records/mine           My submissions
  /records/:id            Record detail  ← the workflow's home
  /records/:id/documents  Documents for a record
  /workspace              Reviewer working set
  /review/pending         Review queue           (reviewers)
  /review/:id/evaluate    Decision screen        (reviewers)
  /notifications          Notifications
  /audit                  Audit log              (RDCO)
  /users/role-requests    Role approvals         (RDCO)
  /ai                     Search / AI            (all)
```

**Hidden for the pilot** (routes removed, components retained): Dashboard · Discover · Approved/Declined/ApprovedProposals lists · Settings · Help · DownloadToken · UserList · Sessions.

**Deferred:** DownloadRequests · DeleteRequests · DocumentReviews · ReviewAnalytics (returns 501) · ImportRecords.

**Removed:** RAGChatPage + 7 chat components · StoragePage · FolderBrowserPage · AccessRequestsPage · superseded route guards.

---

## 4 · Depth

Three levels maximum. Everything on the spine is reachable in **two clicks from the home screen**.

```
L1  Home
L2  My submissions · Review queue · Published records · Search · Audit
L3  Record detail · Submission wizard · Decision screen · Documents
```

`/records/:id` is the hub. From it: documents, history, resubmission, decisions. **Nothing important should sit deeper than the record it belongs to** — the current `/records/:id/documents` split is acceptable because document management is genuinely a separate task, but the record's *state* must never require a second navigation.

---

## 5 · Role → screen matrix

Client-side gating is **UX only**; enforcement is server-side (`S-02`…`S-05`). See [03](03-navigation.md).

| Screen | Student | Adviser | RDCO | ITSO | IERC | KTTO |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Discover | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Paper view | ◐ | ◐ | ✅ | ◐ | ◐ | ◐ |
| Ask IRIS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| My Library *(reader)* | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Calls & Conferences | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notifications · Settings · Help | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Submit Disclosure** | ✅ | ✅ | — | — | — | — |
| **My Workspace** *(author)* | ✅ | ✅ | — | — | — | — |
| Edit record | ◐ | ◐ | — | — | — | — |
| Documents | ◐ | ◐ | ✅ | ◐ | ◐ | ◐ |
| **Review queue** *(+ Approved / Declined filters)* | — | ◐ | ✅ | ◐ | ◐ | ◐ |
| **Decision screen** | — | ◐ | ✅ | ◐ | ◐ | ◐ |
| Approved Proposals | — | — | ✅ | — | — | — |
| Import Records *(file on behalf of)* | — | — | ✅ | — | — | — |
| Download Requests | — | — | ✅ | — | — | — |
| Delete Requests | — | — | ✅ | — | — | — |
| Audit log | — | — | ✅ | — | — | — |
| Role approvals | — | — | ✅ | — | — | — |

**✅** full · **◐** scoped to your own or assigned records — the server decides which, not the client (`IR-153`) · **—** hidden in nav *and* 403 on direct URL.

**The gating rule.** *Permission* → hidden in the nav and refused on the URL. *State* → visible but **disabled, with the reason stated**. So ITSO never sees Delete Requests (never their role), but ITSO does see its clearance action greyed out with "waiting on RDCO intake" (their role, wrong moment). Disabling for permission teaches people to want what they can never have; hiding for state makes the workflow look broken.

**Named surfaces** ([15](15-mvp-ui-scope.md)'s unit of scope): Student → My Workspace · Adviser → My Workspace and the review queue for records they advise · ITSO / IERC / KTTO → the review queue for their office's clearances · RDCO → the review queue plus the coordination screens.

**~~Audit is RDCO-only~~ — done.** `AUDIT_LOG_ROLES = [RDCO]` was correct and referenced nowhere; `IR-160` wires it, and `IR-165` narrowed the backend from DRF's `IsAdminUser` (which reads `is_staff`, and therefore admitted all four offices under the `accounts/0005` seeding) to `IsAdmin` with `ADMIN_ROLES = {RDCO}`.

**Amended 2026-09-06, and one row is narrower than it was.** Submission was listed as Student / Adviser / **RDCO**. SRS Use Cases M2-2.1 and M2-2.2 both name the actor *"Record Owner (Student or Adviser)"*, and the SRS outranks this document — so RDCO is removed. The reasoning matters as much as the source: RDCO performs **both** intake and final review, so authoring would mean reviewing its own record at two of the three gates. That is a sharper conflict than the one that (correctly) keeps ITSO, IERC and KTTO out. RDCO's genuine need to file for others is served by **Import Records** instead. Recorded rather than silently reconciled.

**Manage Users and Active Sessions left this table**, and the React app with them: account administration is the Django admin site's job. The SRS names seven user classes; the role enum has six, and the missing one is *System Administrators* — `is_staff` had been standing in for it, which is what produced the defect above. Self-service session management ("your devices") is a different, per-user screen and is tracked as `IR-124`.

**Enforced, not just documented.** `frontend/src/lib/access.ts` is this table in code; the router and the sidebar both read it, so a nav item cannot exist without a matching gate. `frontend/src/lib/access.test.ts` asserts every role against every screen in both directions.

---

## 6 · What the record detail screen must hold

The busiest screen and the workflow's home. Ordered by what users look for first.

| Priority | Block | Why |
|---|---|---|
| 1 | **Decline banner** — when declined | The only screen where a user must act; it must be first |
| 2 | **Clearance Track** | "Where is this?" — the primary question |
| 3 | **Resubmission panel** — when declined | The action, immediately after its reason |
| 4 | Title, type, authors, abstract | Identity |
| 5 | Documents | The artefact under review |
| 6 | History | "What happened?" |
| 7 | Reviewer actions — when eligible | Decision entry point |
| 8 | Metadata — classification, IP flags, dates | Reference |

**State before identity.** A reviewer opening a record already knows what it is; they need to know where it stands. This inverts the usual document-first layout and is deliberate.

---

## 7 · Cross-cutting

**Notifications** are an index into the workflow, not a destination. Every notification links to the record and stage that produced it. The bell shows unread count; the page lists them. Nothing else.

**Search** spans published records. It must never surface records the viewer cannot see (`S-02`, `B-05`) — including via AI citations ([09](09-search-rag.md)).

**Audit** is a filtered log, read-only, RDCO-only. It is also the source for the research metrics (`W-04`), so its data model matters more than its UI.

---

## 8 · Naming

| Route | Screen title | Nav label |
|---|---|---|
| `/` | Home | Home |
| `/records` | Published Records | Published |
| `/records/add` | New Submission | Submit |
| `/records/mine` | My Submissions | My Submissions |
| `/records/:id` | *record title* | — |
| `/review/pending` | Pending Review | Review Queue |
| `/review/:id/evaluate` | Record Decision | — |
| `/ai` | Search | Search |
| `/audit` | Audit Log | Audit |

**Call it "Search", not "AI Hub".** The product is not primarily a chatbot; the user's goal is finding records. AI is how some of that search works, not what the feature is. This also makes the FTS fallback ([09](09-search-rag.md)) coherent rather than a downgrade — the feature is still "Search" when the AI is offline.
