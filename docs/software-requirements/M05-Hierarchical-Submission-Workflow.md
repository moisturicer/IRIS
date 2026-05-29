# Module 5: Hierarchical Submission Workflow

---

## FR-M5-01 — Document Routing and IP Evaluation Workflow

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Student
actor Adviser
actor "RDCO Staff" as RDCO
actor "ITSO Staff" as ITSO
actor "IERC Staff" as IERC
actor "KTTO Staff" as KTTO

rectangle "Module 5 : Hierarchical Submission Workflow" {
  usecase "Submit Record into Pipeline" as UC1
  usecase "Route Proposal → Adviser Review" as UC2
  usecase "Route Thesis/Research → RDCO Intake" as UC3
  usecase "Route Project → RDCO Intake" as UC4
  usecase "Adviser: Approve / Revise / Reject" as UC5
  usecase "RDCO: Intake Completeness Check" as UC6
  usecase "Route to IERC + KTTO (parallel)\n[Thesis/Research]" as UC7
  usecase "Route to ITSO + KTTO (parallel),\nthen IERC after ITSO [Project]" as UC8
  usecase "ITSO Review" as UC9
  usecase "IERC Review" as UC10
  usecase "KTTO Review" as UC11
  usecase "RDCO Final Decision" as UC12
  usecase "Publish Record" as UC13
  usecase "Return for Revision" as UC14
  usecase "Reject Record (terminal)" as UC15
  usecase "RDCO: Mark Proposal as Completed" as UC16
  usecase "View Approved Proposals Queue" as UC17
}

Student  --> UC1
UC1      ..> UC2 : extend (Proposal)
UC1      ..> UC3 : extend (Thesis/Research)
UC1      ..> UC4 : extend (Project)
Adviser  --> UC5
UC2      ..> UC5 : leads to
UC5      ..> UC13 : extend (approved → ongoing)
UC5      ..> UC14 : extend (revise)
UC5      ..> UC15 : extend (reject)
RDCO     --> UC17
UC17     ..> UC16 : include
RDCO     --> UC16
UC13     ..> UC16 : extend (research finished)
RDCO     --> UC6
UC3      ..> UC6 : leads to
UC4      ..> UC6 : leads to
UC6      ..> UC7  : extend (Thesis/Research complete)
UC6      ..> UC8  : extend (Project complete)
UC6      ..> UC14 : extend (revise)
UC6      ..> UC15 : extend (reject)
IERC     --> UC10
KTTO     --> UC11
ITSO     --> UC9
UC7      ..> UC10 : include (parallel)
UC7      ..> UC11 : include (parallel)
UC8      ..> UC9  : include (first)
UC8      ..> UC11 : include (parallel throughout)
UC9      ..> UC10 : leads to (after ITSO)
UC10     ..> UC15 : extend (serious violation)
UC11     ..> UC15 : extend (serious violation)
RDCO     --> UC12
UC12     ..> UC13 : extend (approved)
UC12     ..> UC14 : extend (revise)
UC12     ..> UC15 : extend (reject)
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M5-01 |
| **Name** | Document Routing and IP Evaluation Workflow |
| **Actors** | Student, Adviser, RDCO, ITSO, IERC, KTTO |
| **Preconditions** | Record is in `draft` status; record type is set; required documents uploaded |
| **Main Flow — Proposal** | 1. Student submits → `adviser_review` 2. Adviser checks document completeness 3. Adviser approves → `approved` (visible as ongoing) OR declines → back to student for revision (loop) OR rejects → terminal 4. When research is done, RDCO manually marks → `completed` (remains visible) |
| **Main Flow — Thesis/Research** | 1. Student submits → `rdco_intake` 2. RDCO checks completeness 3. If complete → `parallel_review`: IERC reviews Ethics Clearance + Release Form in parallel with KTTO reviewing Patent Search/Draft + IP Status + Pub/Conf + Commercialization Assessment 4. All offices clear → `rdco_review` → RDCO consolidates and approves → `published` |
| **Main Flow — Project** | 1. Student submits → `rdco_intake` 2. RDCO checks completeness 3. If complete → `itso_review`: ITSO reviews NDA + Assessment File; KTTO begins IP & Commercialization review in parallel from this stage 4. ITSO clears → IERC starts Ethics Clearance review; KTTO continues in parallel 5. All three offices clear → `rdco_review` → RDCO consolidates → `published` |
| **Alternative Flow A** | RDCO returns submission for revision (incomplete) → `declined`; student uploads revised documents and resubmits. System validates that at least one new document version exists (uploaded after the most recent declined Review timestamp) before accepting the resubmission. All `RecordClearance` rows are deleted; record re-enters at `rdco_intake`. |
| **Alternative Flow B** | RDCO rejects at intake (out of scope, ineligible) → `rejected` terminal |
| **Alternative Flow C** | Any office (ITSO / IERC / KTTO) declines → `declined`; student uploads revised documents and resubmits. **Smart clearance routing:** the system inspects the `stage` field of the most recent declined `Review`. Only the declining office's `RecordClearance` row is reset to `pending`; all other offices' cleared status is preserved. The record re-enters at the correct stage: ITSO decline → `itso_review`; IERC decline → `parallel_review`; KTTO decline → `itso_review` if ITSO is still pending, otherwise `parallel_review`. The same new-document validation applies. |
| **Alternative Flow D** | Any office (ITSO / IERC / KTTO) rejects (serious violation) → `rejected` terminal |
| **Alternative Flow E** | RDCO final issues revision → `declined`; student uploads revised documents and resubmits. All clearances are deleted; record re-enters at the first stage for its record type. |
| **Alternative Flow F** | RDCO final rejects → `rejected` terminal |
| **Main Flow — Proposal Completion** | 1. RDCO opens the **Approved Proposals** queue (`/review/approved-proposals`) 2. RDCO sees all records with `pipeline_status = "approved"` (only Proposals can reach this status) 3. RDCO clicks "Mark as Completed" on the target row 4. System calls `POST /records/<id>/complete/`, transitions record to `completed` 5. Row is removed from the queue; record owners are notified 6. Record remains publicly visible with "Completed" badge |
| **Postconditions** | Record status reflects current pipeline stage; transitions enforced server-side via RecordClearance rows for parallel stages; completed Proposals remain visible in Browse Collections |

### Activity Diagram
```plantuml
@startuml
start
:Student submits record;
if (Record Type = Proposal?) then (Yes)
  :pipeline_status = "adviser_review";
  :Adviser checks document completeness;
  if (Adviser decision?) then (Approved)
    :pipeline_status = "approved";
    :Record visible as ongoing proposal;
    note right: Research is in progress
    :— later, when research finishes —;
    :RDCO manually marks record;
    :pipeline_status = "completed";
    stop
  else if (Declined)
    :pipeline_status = "declined";
    :Notify student;
    :Student resubmits → adviser_review;
  else (Rejected)
    :pipeline_status = "rejected";
    stop
  endif
else if (Record Type = Thesis/Research?) then (Yes)
  :pipeline_status = "rdco_intake";
  :RDCO checks completeness;
  if (RDCO decision?) then (Declined)
    :pipeline_status = "declined";
    stop
  else if (Rejected)
    :pipeline_status = "rejected";
    stop
  else (Complete → Route)
  endif
  :pipeline_status = "parallel_review";
  :Create RecordClearance: IERC(pending) + KTTO(pending);
  fork
    :IERC reviews Ethics Clearance + Release Form;
    if (IERC decision?) then (Cleared)
      :RecordClearance IERC → cleared;
    else if (Declined)
      :pipeline_status = "declined";
      stop
    else (Rejected)
      :pipeline_status = "rejected";
      stop
    endif
  fork again
    :KTTO reviews Patent/IP/Pub/Conf/Comm;
    if (KTTO decision?) then (Cleared)
      :RecordClearance KTTO → cleared;
    else if (Declined)
      :pipeline_status = "declined";
      stop
    else (Rejected)
      :pipeline_status = "rejected";
      stop
    endif
  end fork
  :All clearances done → pipeline_status = "rdco_review";
else (Project)
  :pipeline_status = "rdco_intake";
  :RDCO checks completeness;
  if (RDCO decision?) then (Declined)
    :pipeline_status = "declined";
    stop
  else if (Rejected)
    :pipeline_status = "rejected";
    stop
  else (Complete → Route)
  endif
  :pipeline_status = "itso_review";
  :Create RecordClearance: ITSO(pending) + KTTO(pending);
  fork
    :ITSO reviews NDA + Assessment File;
    if (ITSO decision?) then (Cleared)
      :RecordClearance ITSO → cleared;
      :Create RecordClearance: IERC(pending);
      :pipeline_status = "parallel_review";
      :IERC reviews Ethics Clearance;
      if (IERC decision?) then (Cleared)
        :RecordClearance IERC → cleared;
      else if (Declined)
        :pipeline_status = "declined";
        stop
      else (Rejected)
        :pipeline_status = "rejected";
        stop
      endif
    else if (Declined)
      :pipeline_status = "declined";
      stop
    else (Rejected)
      :pipeline_status = "rejected";
      stop
    endif
  fork again
    :KTTO reviews IP Status + Pub/Conf + Comm (parallel throughout);
    if (KTTO decision?) then (Cleared)
      :RecordClearance KTTO → cleared;
    else if (Declined)
      :pipeline_status = "declined";
      stop
    else (Rejected)
      :pipeline_status = "rejected";
      stop
    endif
  end fork
  :All clearances done → pipeline_status = "rdco_review";
endif
:RDCO final review — consolidates all clearances;
if (RDCO decision?) then (Approved)
  :pipeline_status = "published";
else if (Revision needed?) then (Yes)
  :pipeline_status = "declined";
  :Notify student to resubmit;
else (Rejected)
  :pipeline_status = "rejected";
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > My Records > Smart Irrigation System
  ==
  Status: 🔵 Parallel Office Review
  .
  Pipeline Progress
  {#
  ✅ Submitted | ✅ RDCO Intake | ⬜ ITSO | 🔵 IERC | 🔵 KTTO | ⬜ RDCO Final | ⬜ Published
  }
  ==
  IRIS > Review Queue (RDCO Staff View)
  --
  Pending — RDCO Intake Review
  {#
  Record                 | Type    | Submitted  | Action
  Smart Irrigation...    | Project | 2026-05-25 | [Review]
  Blockchain Credentials | Thesis  | 2026-05-24 | [Review]
  }
  .
  Review Panel
  --
  [✓ Approve & Route]   [↩ Return for Revision]   [⛔ Reject]
  Comment: | "                                            "
}
@endsalt
```

### Wireframe — Approved Proposals Queue (RDCO View)
```plantuml
@startsalt
{+
  IRIS > Review Queue > Approved Proposals
  ==
  Ongoing research proposals awaiting completion mark by RDCO.
  --
  {#
  Title                          | Authors             | Approved   | Action
  AI Flood Monitoring System     | Juan Dela Cruz, ... | 2026-03-10 | [✅ Mark as Completed]
  Blockchain Certificate Verify  | Maria Santos, ...   | 2026-04-02 | [✅ Mark as Completed]
  Smart Campus Energy Monitor    | Pedro Reyes         | 2026-04-18 | [✅ Mark as Completed]
  }
  .
  ✅ "AI Flood Monitoring System" marked as completed.
  Owners have been notified.
}
@endsalt
```

---

## FR-M5-02 — Auth PIN for Gated Record Access

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "Authenticated User" as User
actor System

rectangle "Module 5 : Hierarchical Submission Workflow" {
  usecase "Request PIN for Gated Record" as UC1
  usecase "Generate One-Time PIN" as UC2
  usecase "Email PIN to User" as UC3
  usecase "Log PIN Generation in Audit Trail" as UC4
  usecase "User Enters PIN" as UC5
  usecase "Validate PIN Server-Side" as UC6
  usecase "Mark PIN as Used" as UC7
  usecase "Grant Access to Gated Content" as UC8
  usecase "Reject Expired / Used PIN" as UC9
  usecase "Log PIN Use in Audit Trail" as UC10
}

User   --> UC1
UC1    ..> UC2 : include
UC2    ..> UC3 : include
UC2    ..> UC4 : include
User   --> UC5
UC5    ..> UC6 : include
UC6    ..> UC7 : extend (valid, not expired)
UC7    ..> UC8 : include
UC7    ..> UC10 : include
UC6    ..> UC9 : extend (invalid / used / expired)
System --> UC2
System --> UC6
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M5-02 |
| **Name** | Auth PIN for Gated Record Access |
| **Actors** | Authenticated User (primary), System |
| **Preconditions** | User is authenticated; record requires PIN-based access authorization |
| **Main Flow** | 1. User requests access to a gated record 2. System invalidates any previous unused PINs for this user+record 3. System generates a one-time 6-digit PIN with a 24-hour expiry 4. System emails the PIN to the user 5. System logs a PIN generation event in the audit trail 6. User enters the PIN in the verification form 7. System validates: PIN matches, `is_used = false`, `expires_at > now()` 8. System marks PIN as used (`is_used = true`) 9. System grants access to the gated content 10. PIN use event logged in the audit trail |
| **Alternative Flow A** | PIN already used → "Invalid or already used PIN" error |
| **Alternative Flow B** | PIN expired (`expires_at ≤ now()`) → same "Invalid or already used PIN" error (no detail disclosed for security) |
| **Alternative Flow C** | Wrong PIN → same error |
| **Postconditions** | PIN marked as used; access granted; both events logged |

### Activity Diagram
```plantuml
@startuml
start
:User requests access to gated record;
:Invalidate any existing unused PINs for this user+record;
:Generate 6-digit one-time PIN;
:Set expires_at = now() + 24 hours;
:Create RecordAuthPin entry (is_used = false);
:Send PIN to user via email;
:Log PIN generation in AuditEvent;
:User receives PIN email;
:User enters PIN in IRIS;
:System looks up RecordAuthPin
  WHERE record = X AND user = Y AND pin = Z AND is_used = false;
if (Valid PIN found?) then (No)
  :Return "Invalid or already used PIN";
  stop
else (Yes)
endif
if (expires_at ≤ now()?) then (Yes — expired)
  :Return "Invalid or already used PIN";
  stop
else (No — still valid)
endif
:Set RecordAuthPin.is_used = true;
:Log PIN verification in AuditEvent;
:Grant access to gated record content;
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Record Detail > [Gated Record]
  ==
  🔒 This record requires PIN verification.
  .
  [Request Access PIN]
  .
  --
  PIN sent to your registered email address.
  Valid for 24 hours. Single use only.
  --
  {+
    Enter your 6-digit PIN
    ==
    " " | " " | " " | " " | " " | " "
    .
    [            Verify PIN            ]
  }
  .
  ✅ Access granted.
  ⚠  Invalid or already used PIN.
}
@endsalt
```

---

## FR-M5-03 — Document-Level Review and Status Transitions

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "Staff Reviewer" as Staff
actor System

rectangle "Module 5 : Hierarchical Submission Workflow" {
  usecase "View Uploaded Document Version" as UC1
  usecase "Select New Status for Document" as UC2
  usecase "Submit Upload Review" as UC3
  usecase "Update Upload.status" as UC4
  usecase "Create UploadReview Record\n(timestamped, user-associated)" as UC5
}

Staff  --> UC1
Staff  --> UC2
UC2    ..> UC3 : include
UC3    ..> UC4 : include
UC3    ..> UC5 : include
System --> UC4
System --> UC5
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M5-03 |
| **Name** | Document-Level Review and Status Transitions |
| **Actors** | Staff Reviewer (primary), System |
| **Preconditions** | Staff is authenticated with a reviewer role; a document upload exists for the record |
| **Main Flow** | 1. Staff opens a record's document view 2. Staff selects a document version to review 3. Staff chooses a new status (e.g., For Application, Reviewed, Filed, Approved, Disapproved) 4. Staff optionally adds a comment 5. Staff submits the review via POST `/documents/upload-reviews/` 6. System creates an `UploadReview` record with timestamp and acting user 7. System mirrors the new status onto `RecordUpload.status` |
| **Alternative Flow A** | Upload or status not found → HTTP 404 |
| **Postconditions** | `UploadReview` created; `RecordUpload.status` updated; timestamp and reviewer identity recorded |

### Activity Diagram
```plantuml
@startuml
start
:Staff opens document version on record detail view;
:Staff selects new status for the document;
:Staff adds optional comment;
:Staff submits review;
:System validates: upload exists, status exists;
if (Upload or status not found?) then (Yes)
  :Return HTTP 404;
  stop
else (No)
endif
:Create UploadReview entry:
  upload, reviewed_by, status, comment, timestamp;
:Update RecordUpload.status to new status;
:Return UploadReview data (HTTP 201);
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Review > Smart Irrigation System > Documents
  ==
  NDA — v1   nda_signed.pdf   Uploaded: 2026-05-10
  Current Status: ⬜ Pending Review
  .
  Set Status: | ^Select status...         ^
  Comment:    | "                                       "
  .
  [              Submit Review              ]
  ==
  Review History
  {#
  Date       | Reviewer   | Status   | Comment
  2026-05-12 | RDCO Staff | Reviewed | Looks complete
  2026-05-15 | KTTO Staff | Approved | Cleared for IP
  }
}
@endsalt
```

---

## FR-M5-04 — Pipeline Event Notifications

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor Student
actor "RDCO Staff" as RDCO
actor "Reviewing Office" as Reviewer
actor System

rectangle "Module 5 : Hierarchical Submission Workflow" {
  usecase "Record Submitted" as UC1
  usecase "Notify RDCO (submission received)" as UC2
  usecase "Review Assigned to Office" as UC3
  usecase "Notify Reviewing Office" as UC4
  usecase "Revision Requested or Rejection" as UC5
  usecase "Notify Record Owner" as UC6
  usecase "Office Clears Record (partial)" as UC7
  usecase "Notify Owner of Partial Progress" as UC8
  usecase "All Offices Cleared" as UC9
  usecase "Notify RDCO for Final Review" as UC10
  usecase "Log Notification Delivery" as UC11
}

Student  --> UC1
UC1      ..> UC2 : include
System   --> UC2
System   --> UC4
System   --> UC6
System   --> UC8
System   --> UC10
UC3      ..> UC4 : include
UC5      ..> UC6 : include
UC7      ..> UC8 : include
UC9      ..> UC10 : include
UC2      ..> UC11 : include
UC4      ..> UC11 : include
UC6      ..> UC11 : include
UC8      ..> UC11 : include
UC10     ..> UC11 : include
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M5-04 |
| **Name** | Pipeline Event Notifications |
| **Actors** | Student/Owner, RDCO, Reviewing Office, System |
| **Preconditions** | A pipeline status transition has occurred |
| **Main Flow** | 1. A workflow transition occurs 2. System determines recipients by event type: · Submission → RDCO (or Adviser for Proposals) · Routed to offices → each reviewing office · Resubmission after clearance decline → only the offices with pending `RecordClearance` rows (IERC, KTTO, and/or ITSO as applicable) · Resubmission after non-clearance decline → RDCO or Adviser (same as initial submission) · Partial clearance → record owner · All offices cleared → RDCO (final review) + owner · Decline/rejection → record owner 3. System dispatches in-app notification to each recipient 4. Delivery status is logged |
| **Alternative Flow A** | Notification delivery fails → Failure is logged |
| **Postconditions** | In-app notifications sent to all relevant parties; delivery logged |

### Activity Diagram
```plantuml
@startuml
start
:Pipeline status transition occurs;
if (Transition = "submitted"?) then (Yes)
  if (Record type = Proposal?) then (Yes)
    :Notify: assigned Adviser;
    :Message: "New Proposal awaiting your review";
  else (Thesis / Research / Project)
    :Notify: RDCO;
    :Message: "New record submitted for intake review";
  endif
else if (Transition = "routed to offices"?) then (Yes)
  :Notify: each relevant reviewing office;
  :Notify: owner of routing;
else if (Transition = "partial clearance"?) then (Yes)
  :Notify: record owner;
  :Message: "[Office] has cleared your record — review still in progress";
else if (Transition = "all offices cleared"?) then (Yes)
  :Notify: RDCO (for final review);
  :Notify: owner (all offices cleared);
else (Decline or rejection)
  :Notify: record owner;
  :Message: "Your record was declined/rejected by [Office]";
endif
:Dispatch in-app notification to each recipient;
if (Delivery successful?) then (Yes)
  :Log delivery success;
else (No)
  :Log delivery failure;
endif
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Notifications                             🔔 3 new
  ==
  {+
    🔵 New Submission                              2026-05-27
    --
    "Smart Irrigation System" submitted for RDCO intake review.
  }
  {+
    🟡 Partial Clearance                           2026-05-26
    --
    KTTO has cleared "Blockchain Credentials".
    IERC review is still in progress.
  }
  {+
    ✅ All Offices Cleared                         2026-05-25
    --
    "AI Flood Monitoring" is ready for RDCO final review.
  }
}
@endsalt
```

---

## FR-M5-05 — Record IP Classification and Tagging

### Use Case Diagram
```plantuml
@startuml
left to right direction
actor "Reviewer-role User" as Reviewer
actor "Authenticated User" as User

rectangle "Module 5 : Hierarchical Submission Workflow" {
  usecase "Tag Record with IP Classification" as UC1
  usecase "Set ip_type (Patent / Copyright /\nTrade Secret / Utility Model)" as UC2
  usecase "Set Boolean Flags\n(is_ip, for_commercialization,\ncommunity_extension)" as UC3
  usecase "View IP Tags on Record Detail" as UC4
  usecase "Filter Published Records by IP Classification" as UC5
}

Reviewer --> UC1
UC1   ..> UC2 : include
UC1   ..> UC3 : include
User  --> UC4
User  --> UC5
@enduml
```

### Use Case Description

| Field | Details |
|---|---|
| **FR ID** | FR-M5-05 |
| **Name** | Record IP Classification and Tagging |
| **Actors** | Reviewer-role User (Adviser, KTTO, RDCO, ITSO, IERC) (primary), Authenticated User |
| **Preconditions** | User is authenticated with a reviewer role (Adviser, KTTO, RDCO, ITSO, or IERC); record exists |
| **Main Flow** | 1. Reviewer-role user opens a record after RDCO final review 2. Reviewer-role user sets the structured `ip_type` label: Patent, Copyright, Trade Secret, or Utility Model (or clears it with "") 3. Reviewer-role user sets boolean flags: `is_ip`, `for_commercialization`, `community_extension` 4. Reviewer-role user submits via PATCH `/records/<id>/tags/` 5. System validates and saves 6. IP tags visible on record detail and filterable in browse interface |
| **Alternative Flow A** | Invalid `ip_type` value → "Not a valid ip_type" error |
| **Alternative Flow B** | Boolean field sent as non-boolean → Error |
| **Alternative Flow C** | `ip_type = ""` clears the IP classification label |
| **Postconditions** | IP tags saved; visible on record detail; filterable; ACCESS audit event logged |

### Activity Diagram
```plantuml
@startuml
start
:Reviewer-role user opens record detail after final review;
:Reviewer-role user selects ip_type from valid options;
note right
  Valid ip_type values:
  patent | copyright |
  trade_secret | utility_model | ""
end note
:Reviewer-role user sets boolean flags:
  is_ip, for_commercialization,
  community_extension;
:Reviewer-role user submits PATCH /records/<id>/tags/;
if (ip_type value valid?) then (No)
  :Return "Not a valid ip_type" error;
  stop
else (Yes)
endif
if (Boolean fields are proper booleans?) then (No)
  :Return "'field' must be a boolean" error;
  stop
else (Yes)
endif
:Save changes to Record;
:Log ACCESS audit event (tags_updated);
:Return updated RecordDetailSerializer;
:IP tags visible on record detail page;
:Tags available as filter on browse page;
stop
@enduml
```

### Wireframe
```plantuml
@startsalt
{+
  IRIS > Record Detail > Smart Irrigation System (Reviewer View)
  ==
  Title:  Smart Irrigation System   |   Status: ✅ Published
  .
  IP Classification (Reviewer-role only)
  --
  IP Type: | ^Patent               ^
  .
  [X] Is IP
  [X] For Commercialization
  [ ] Community Extension
  .
  [             Save Tags             ]
  ==
  Public Badge View
  🏷 Patent   💼 For Commercialization
}
@endsalt
```
