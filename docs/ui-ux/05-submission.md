# 05 — Submission

**Verdict: KEEP, with corrections.** The wizard exists and works. NFR-U2 sets a hard target it must meet.

---

## 1 · What exists

`AddRecordPage` (188 lines) with three steps in `features/records/steps/`:

| Step | Component | Content |
|---|---|---|
| 1 | `TitleAbstractStep` | Title, abstract |
| 2 | `RecordDetailsStep` (201 lines) | Type, classification, PSCED, adviser, authors, IP flags |
| 3 | `UploadsStep` (171 lines) | Documents per upload slot |

Validation via `recordFormSchema.ts` (react-hook-form + Zod) — the good pattern. DPA consent is gated at step 3 by `DpaConsentGate` / `DpaConsentModal` (FR-M6-02).

Submission is two calls: create the record (`draft`), then `POST /records/:id/submit/` to enter the pipeline.

---

## 2 · The governing requirement

> **NFR-U2** — *a first-time user, after a 1-hour onboarding, shall complete a full IP disclosure submission including PDF upload and consent acknowledgment within **10 minutes** without external assistance.* Validated with **five** participants; **all five** must pass.

This is the tightest usability constraint in the SRS and it validates this screen specifically. Every decision below is measured against it.

---

## 3 · Problems

| # | Problem | Impact on NFR-U2 |
|---|---|---|
| 1 | **Type is chosen at step 2**, but type determines the entire route and the required documents | A user cannot see what they are committing to until after they have typed an abstract |
| 2 | **No route preview.** Nothing says "this will go to RDCO, then IERC and KTTO" | The workflow is invisible at the moment of entry |
| 3 | **Draft vs submitted is unclear.** Creating a record leaves it in `draft`; a separate action submits it | A user may believe they have submitted when they have not. **This is the most likely NFR-U2 failure** |
| 4 | Adviser is required for Proposals but the requirement surfaces only on submit | Server-side error for a rule never stated |
| 5 | Upload slots are type-dependent; step 3 cannot be previewed from step 1 | Users cannot gather documents in advance |

---

## 4 · Direction

**Move type selection to step 1** and show the consequences immediately.

```
STEP 1 of 3 — What are you submitting?

  ○ Proposal
    Reviewed by your adviser.
    → Adviser review → Approved

  ● Thesis / Research
    Reviewed by RDCO, then by IERC and KTTO together.
    → RDCO intake → IERC + KTTO → RDCO final → Published

  ○ Project
    Reviewed by RDCO, then ITSO, then IERC and KTTO.
    → RDCO intake → ITSO → IERC + KTTO → RDCO final → Published

  You will need: Concept paper, Ethics clearance form
```

Three things this fixes at once: the route becomes visible before commitment; required documents are known in advance; and the adviser requirement can be stated on the step where Proposal is chosen rather than discovered on submit.

**Keep three steps.** Adding a fourth costs time against a 10-minute budget.

| Step | Content |
|---|---|
| **1 · Type** | Type selection + route preview + document requirements |
| **2 · Details** | Title, abstract, authors, adviser *(if Proposal)*, classification, IP flags |
| **3 · Documents & consent** | Upload per slot, DPA consent, **explicit submit** |

### The draft/submit boundary

The single most important correction. Step 3's action must be unambiguous:

```
  [ Save as draft ]              [ Submit for review → ]

  Submitting sends this to RDCO. You will not be able to
  edit it while it is under review.
```

Confirm on submit — this is irreversible from the user's perspective and starts institutional review.

---

## 5 · Specification

**User.** Student (primary), Adviser, RDCO.

**Goal.** Submit a research or IP disclosure record with its documents in under 10 minutes.

**Primary action.** Submit for review.

**Secondary actions.** Save as draft · back a step · remove an uploaded file · cancel.

**Required data.**
- Reference: record types, classifications, PSCED classifications, upload slots for the chosen type, adviser list
- Input: title, abstract, type, authors, adviser (Proposal), classification, IP flags, documents, consent

**Permissions.** Student, Adviser, RDCO may create. Office roles may not — they review, they do not submit. **Server-enforced**; nav hiding is UX only.

**States.**

| State | Rendering |
|---|---|
| Step 1–3 | Progress indicator, step title, back/next |
| Draft saved | Toast + the record appears in My Submissions marked **Draft** |
| Submitting | Button `loading`, form disabled, no navigation |
| Submitted | Redirect to record detail with a success banner and the Clearance Track visible |
| Editing a declined record | Same wizard, prefilled, with the decline reason pinned above ([08](08-workflow-resubmission.md)) |

**Errors.**

| Error | Handling |
|---|---|
| Validation | Inline, at the field, on blur and on submit. Focus moves to the first invalid field |
| File > 50 MB | *"Your file is 62 MB. The limit is 50 MB."* — **before** upload starts, from `file.size` |
| Non-PDF | *"Only PDF files are accepted."* Reject on selection |
| Missing adviser on a Proposal | Prevented at step 2, not discovered on submit |
| Server rejects submit | Show the server's specific message; **keep the form intact** and never lose entered data |
| Network failure mid-upload | Per-file retry; other files retain their state |

**Empty states.** No upload slots for a type → *"No documents are required for this type"*, not an empty container. No advisers in the list → *"No advisers available — contact RDCO"*, since this blocks Proposal submission entirely.

**Loading states.** Reference data loads before step 1 renders — a blank type list is worse than a brief skeleton. Uploads show per-file progress; the step is not blocked while a file uploads.

**Accessibility.**
- `<form>` with a `<fieldset>`/`<legend>` per step
- Step indicator as `<ol>` with `aria-current="step"`
- Type selection as a genuine radio group, keyboard-navigable with arrow keys
- Every input labelled via the `Input` primitive's `htmlFor`
- Errors linked by `aria-describedby` and `aria-invalid` (**needs the `Input` fix**, [01](01-design-system.md))
- Step change moves focus to the new step's heading and announces it via `aria-live`
- Upload zone reachable and operable by keyboard, not drag-only — `FileUploadZone` must expose a real file input
- Consent is a checkbox with the full text reachable, never a click-through the user cannot read

**Responsive.** Single column at every breakpoint. At 360 px: one field per row, step indicator collapses to *"Step 2 of 3"*, actions become full-width stacked buttons with the primary action last (thumb reach). File list stacks name over size and remove. **No horizontal scroll** ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP** — three steps, type-first, route preview, explicit submit boundary. **Post-MVP** — autosave drafts, bulk author import, document templates, per-institution configurable slots ([11](11-saas-admin.md)).

**Backend/API dependencies.**
- `POST /records/` (create draft) · `POST /records/:id/submit/` (enter pipeline)
- `GET /documents/slots/?record_type=` — needed at **step 1** to show requirements
- `GET /users/advisers/`, classification and PSCED reference endpoints
- `POST /documents/submit/` — **currently has no ownership check** (`S-03`)
- **New, small:** route preview per type. Derivable from `W-01`'s transition table; a static client-side map is acceptable for the MVP but should move server-side for per-institution configuration ([11](11-saas-admin.md))
