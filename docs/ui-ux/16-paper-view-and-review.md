# 16 — Paper View, Review and My Reviews

**Verdict: ONE Paper View for every role, with four modes chosen by server-computed `capabilities`. "My Reviews" replaces the per-party queues.**

The decisions behind this are [ADR-032](../adr/032-adviser-first-review-and-office-reviewer-pools.md). This page covers **structure only**: which regions exist, what each mode shows, and what each action is called. Visual design goes through `/ui` and the `anti-ui-slop` skill when each screen is built, within the IRIS tokens (IR-357).

**Superseded by this page:**

- [07 — Review & Clearance](07-review-clearance.md) §3 (the queue) and §5 (queue specification).
- The Intake & Triage parts of [`workflow_routing_architecture.md` §9](../workflow_routing_architecture.md).

---

## 1 · The rule

The frontend asks **"what can this user do with this record?"** It never asks "what role is this user?"

`GET /records/<id>/` returns `capabilities: string[]`. A control is rendered **only** when its capability is in that list. The server re-checks every action, so a hidden button is a courtesy and never the protection.

**No component may import a role name to decide what to show.** A guard in the style of IR-358's palette guard should fail the build if `features/records/paper-view/` compares against `RoleName` values.

---

## 2 · Modes

| Mode | Entered when | Regions |
|---|---|---|
| **Reading** | The user can read the record | Header · Paper · Abstract · Cite / Save · Lineage · Public discussion |
| **Author** | The user owns the record | Reading + Version picker · Action Required panel · Review timeline (read / reply) · **New version** · **Continue as…** · Visibility |
| **Review** | The user holds a seat on the record and has pressed **Open review** | Paper (left) · Review timeline (right) · Ask IRIS as a floating dock · Party status strip · Action bar |
| **Summary** | A stranger opens a Discoverable Proposal | Title · Abstract · Classification · Authors · "Looking for" · Proposal label · Public discussion. **No PDF.** |

**Before Open review,** a seat holder sees Reading mode plus one primary action, **Open review**. Opening is recorded (`opened_at`) and moves the record from *To review* to *In review*.

---

## 3 · The header

```
PROPOSAL · In development                          v3 ▾   [Cite]  [Save]
AI-Assisted Medical Imaging
Juan Dela Cruz, Ana Reyes · Adviser: Prof. Santos · Computer Science
Developed from Proposal #123 →            (or)     Continued as Thesis #456 →
```

**Type and state label.** This comes from `workflow_state`, in the IR-358 tones. A Proposal always reads **"Proposal"**, never "Research", so a Discoverable Proposal can never pass for approved work.

**Version picker.** Shown to owners and participants only:

```
● v3 — Current     Revision submitted · Sep 25
○ v2               Revision requested by Adviser · Sep 20
○ v1               Original submission · Sep 15
```

Choosing an older version swaps the manuscript and shows a banner: *"You are viewing v2. Reviews below marked v2 were made against this version."*

---

## 4 · Review mode

```
┌──────────────────────────────┬──────────────────────────────────────┐
│                              │ Adviser ✓ · ITSO ● · IERC ● ·        │
│                              │ KTTO — · RDCO ○                      │
│          PAPER               ├──────────────────────────────────────┤
│       (PDF reader,           │ TIMELINE                             │
│        IR-335/352)           │  ◦ v1 submitted · Sep 15             │
│                              │  ◦ Prof. Santos opened review        │
│                              │  💬 Prof. Santos: "Clarify §3…"      │
│                              │  ↩ Revision requested (Adviser)      │
│                              │  ◦ v2 submitted                      │
│                              │  ✓ Adviser accepted · routed to      │
│                              │    ITSO, IERC — "possible IP"        │
│                  [Ask IRIS]  │  💬 comment box                      │
├──────────────────────────────┴──────────────────────────────────────┤
│ ACTION BAR — only the capabilities this user has                    │
└─────────────────────────────────────────────────────────────────────┘
```

**The timeline** is one chronological list, built by the server from existing rows (ADR-032 §7):

- comments
- versions
- seat openings
- reviews and findings
- routing
- document requests
- resubmission requests and their resolution

Each entry carries its version tag. The comment box is at the bottom, as on GitHub.

**Party status strip:**

| Symbol | Meaning |
|---|---|
| ✓ | done |
| ● | reviewing |
| ◌ | in pool, unassigned |
| ○ | waiting |
| — | not requested |

**RDCO reads "Not required"** when no office was routed to. Hovering or focusing a party lists its reviewers and each seat's state (*Maria Reyes — reviewing · Juan Santos — done*).

### Action bar, by capability

| Seat | Buttons (capability) |
|---|---|
| Adviser on a **Proposal** | **Request revision** (`request_revision`) · **Reject** (`decide_proposal`) · **Accept** (`decide_proposal`) · Request document |
| Adviser on a **Thesis / Project** | Request revision · Reject · **Accept & publish** (`accept_publish`) · **Accept & route…** (`accept_route`) · Request document |
| ITSO / IERC / KTTO | **Clear** · **Record finding** (`record_finding`) · Request revision · Request document · **Add reviewer** (`add_reviewer`) · **Route to office…** (`route`) |
| RDCO | Request revision · Reject · **Accept & publish** · **Accept, keep unlisted** (`final_decide`) · Route to office… · Request document |

**Destructive or terminal actions** (Reject, both Accept & publish) open `ConfirmDialog` and state the consequence:

- *"This archives the proposal. The student will need to submit a new one."*
- *"This publishes the thesis to Discover. No office will review it."*

The **"Request Revision"** copy from `EvaluationPage` is kept verbatim (07 §1).

### Accept & route…

```
Accept and route for specialist review

The author flagged: ☑ possible IP  ☐ human subjects  ☐ commercial

☐ ITSO    Reviewer: [ Leave to ITSO ▾ / search ITSO members… ]
☐ IERC    Reviewer: [ Leave to IERC ▾ ]
☐ KTTO    Reviewer: [ Leave to KTTO ▾ ]

Reason (required)  [ Potential patentable mechanism in §4.2        ]

                                       [Cancel]  [Accept & route]
```

**"Leave to <office>"** is the default: the record goes to that office's pool. Searching nominates a specific member. **Route to office…** for an office reviewer is the same dialog, without the accept step and without the reviewer's own office.

### Add reviewer

**Add reviewer** is a separate, smaller dialog. It searches members of **your** office only.

It is never merged with routing. Adding a colleague and involving another office are different acts (ADR-032 §4).

---

## 5 · My Reviews

This replaces "Awaiting me / Cleared / Sent back" (`ReviewQueuePage`).

```
My Reviews                                       [Search title, author…]

[ To review (4) ]  [ In review (2) ]  [ Done ]

 AI-Based Medical Imaging            THESIS
 Routed by Prof. Santos · "Potential IP concern" · 2 days
 ITSO · Unassigned                                  [Claim review]

 Smart Campus Energy Monitor         PROPOSAL
 Submitted by Juan Dela Cruz · 1 day
 Adviser · You                                      [Open review]
```

| Tab | Rows |
|---|---|
| **To review** | Your unopened seats. **For office members, also your office's unclaimed records**, marked *Unassigned* with **Claim review**. Coordinators also see **Assign reviewer**. |
| **In review** | Seats you have opened. A *Waiting on author* or *Waiting on document* badge replaces the action while the record is with its author. |
| **Done** | Seats you have completed. Filters: Cleared · Finding recorded · Accepted · Rejected · Published. |

**Rules:**

- You see only your own seats and your office's pool. Nobody browses another reviewer's queue.
- Coordinators get an **Office** filter listing every seat in their office, with who holds it.
- The empty states say what arrives there, not "no data". For example: *"Records routed to ITSO appear here until someone claims them."*
- The filter lives in the URL, as it does today.

---

## 6 · Author surfaces

**New version.** Shown when a revision is requested. It opens the upload flow against the same record. Submitting it writes the next version and returns the record to the reviewers who asked (clearance-aware).

The confirmation names them: *"IERC will review v3. ITSO's clearance is kept."*

**Continue as…** Shown on an accepted Proposal with no continuation yet:

```
Your proposal was accepted.
[Continue as Thesis]   [Continue as Project]
```

It opens the submission wizard pre-filled from the Proposal, as a new draft. Afterwards the Proposal header shows *"Continued as Thesis #456 →"*.

**Visibility.** Proposals only:

```
○ Private        Only you, your Adviser and your reviewers can see it.
● Discoverable   Other IRIS users can find the title and abstract to
                 collaborate. The full proposal stays private.
Looking for      [ An ML collaborator; someone with clinical data   ]
```

---

## 7 · Discover

There are two sections, and each is shown as a separate tab:

- **Research.** Published Thesis / Research and Projects. Unchanged.
- **Proposals.** Discoverable Proposals.

Proposal cards carry the **Proposal · In development** label, the "Looking for" line, and **View proposal**, which opens Summary mode.

**Similar proposals** (ADR-029) appear on the card only once matching exists. A count must not appear before the feature behind it does.

---

## 8 · Public discussion

A flat thread below the paper, in Reading and Summary modes, on published records and Discoverable Proposals.

- Any signed-in user may post.
- Owners and administrators may **hide** a comment. Hidden comments show as *"Hidden by the author"*.
- It is visually and structurally separate from the review timeline, and never shares a component that could leak one into the other.

---

## 9 · Accessibility notes

- The status strip's symbols always come with text ("ITSO — reviewing"), so colour is never the only signal (WCAG 1.4.1).
- The timeline is an ordered list. Each entry's actor, act and version are in its accessible name.
- The action bar is a `toolbar` landmark. Destructive actions are last and are confirmed.
- **Claim review** and **Open review** change a row's tab. Announce the move through a polite live region: *"Moved to In review"*.
