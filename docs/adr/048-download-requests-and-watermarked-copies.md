# ADR-048: Downloading a manuscript needs an approved request, and downloaded copies are watermarked

## Status

**Proposed** — 2026-10-30 (IR-673, spec IR-672). Drafted as ADR-047 and renumbered the same day: ADR-047 on `main` is the RDCO routing proposal. The decisions come from two design sessions on 2026-10-30: the first by a team member, the second by Hermoine Zozobrado, which phased the watermark and added notes, cancelling, revoking and a My Library view. Both are transcribed here by an agent. **Not accepted**: Lee Jasmin Adolfo, the project lead, accepts this record. IR-675, IR-676, IR-677 and IR-688 stay `not-ready` until then. IR-674 (only RDCO approves) restores IR-165's existing intent and does not wait for this ADR.

## Context

Observed on `main`, 2026-10-30:

- `DownloadRequest` exists, with a queue for RDCO at `/admin/download-requests`. An approval emails a 24-hour HS256 bearer link (`apps/records/download_tokens.py`). `DownloadRedeemView` (`AllowAny`) redeems it any number of times, writes no audit row, and carries a TODO for a watermark.
- **No page renders `DownloadRequestModal`**, so a reader has no way to ask. A second, unrouted RDCO page, `AccessRequestsPage`, still copies the bearer link to the clipboard.
- A request carries only the record: the reader gives no reason, and a decline records none.
- The Paper reader (`GET /records/<id>/manuscript/`, inline, IR-335) serves the full manuscript to anyone `visible_to` admits. Its own download button (`PaperPdfReader.handleDownload`) saves those bytes. So downloading is effectively ungated today.
- Approval is already RDCO-only on every route. The `approve` and `decline` actions declare `IsStaff`, but the viewset's `get_permissions` overrides that (corrected 2026-10-31 under IR-674; this line previously said any office could approve). RDCO could decide their own request, the `PATCH` route did not notify the requester, and a new request notified every KTTO and RDCO account.
- No PDF-editing library is installed. PyMuPDF was removed with the prototype extractors (ADR-016).

## Decision

1. **Reading stays open; downloading is gated.** The in-app reader keeps rendering the full text for everyone `visible_to` admits, so Ask IRIS citations, which open the paper at a page, are unchanged. Saving a copy of the manuscript needs an approved request.
2. **Some readers are exempt from the request:** the record's owners, its adviser, the four offices and its assigned reviewers. They download without one. The rule is the same for every published record, whatever its declared origin (ADR-046).
3. **A download request carries the reader's note** saying why. A reader holds at most one pending request per record, and may cancel it.
4. **RDCO alone approves, declines or revokes.** A decline always carries a note. RDCO may revoke an unexpired grant early, also with a note. A declined, revoked or expired request may be made again.
5. **An approval is a time-limited grant, not a link.** It lasts `DOWNLOAD_GRANT_DAYS` (default 30). The grantee downloads from the Record page while signed in, as often as they like within the grant. **No bearer token is issued or emailed.** `DownloadRedeemView` and `download_tokens.py` are removed.
6. **Notifications.** A new request notifies RDCO only, in-app. Approval, decline and revocation notify the reader in-app and by email, with RDCO's note where there is one; the email links to the record, never to a file. The record's owners are never told who asked or downloaded.
7. **Where requests are seen.** The reader sees a request's state on the Record page and in a **Download requests** view in My Library, where they can cancel, download or request again. RDCO works from `/admin/download-requests` only; `AccessRequestsPage` is deleted. Download requests have no due date and no turnaround (ADR-043 does not apply).
8. **Requests made before this change.** Each approved request gets a grant expiring `DOWNLOAD_GRANT_DAYS` after the migration runs. Pending requests stay pending. Declined ones show "No note recorded".
9. **Every download is audited** as `DOWNLOAD`, with its source (`grant` or `exempt`) and the request. Every cancel and revoke is audited too.
10. **Every downloaded copy is watermarked, once IR-676 lands.** Until then, the download route serves the manuscript unmarked: still stricter than today, when the reader's own button saves an unmarked copy for anyone. The watermark is built per download and never stored:
    - a footer on every page: "Downloaded by <name> (<email>) on <date> via CIT-U IRIS · request #N", or the exemption reason in place of the request;
    - a large grey diagonal **"CIT-U"** drawn in each page's background, beneath the content;
    - the same identity, date and request in the PDF's metadata.
11. **Fail closed, from IR-676 on.** A copy that cannot be watermarked is not served. The failure is audited and the reader is told to contact RDCO.
12. **Libraries for the watermark:** pypdf merges the pages and reportlab draws the overlay. Both are BSD-licensed.

## Alternatives Considered

- **Gate the full text, not just downloads.** Without approval, the reader would show only metadata and the abstract. This is a real control. It was rejected for now because Ask IRIS citations would land unapproved readers on a request prompt instead of the page, which changes the RAG reading path (thesis-critical, owned by the RAG workstream).
- **Everything open, every copy watermarked, no approval step.** This is the simplest option and every copy is traceable. It was rejected because the team wants an explicit gate on downloading.
- **Ship nothing until the watermark exists.** It keeps the first session's "every copy watermarked" true from day one. It was rejected because the reader's ungated button stays live meanwhile, which is worse than a gated, unmarked download.
- **Keep the single-use bearer link (IR-664 as written).** It works without signing in. It was rejected because a link is a credential that can be forwarded, and signing in costs a pilot reader little.
- **Requests and declines without notes.** Simpler, but RDCO would decide blind and a declined reader would not know why.
- **No revocation; a grant simply expires.** Simpler, but RDCO could not stop a grant given by mistake or misused, short of hiding the record from everyone.
- **Tell a record's owners who requested or downloaded it.** It was rejected to keep a reader's interest private, as saving a record is; RDCO's audit already records every download.
- **A watermark drawn over the content at low opacity**, rather than beneath it. It would survive scanned pages, but it was rejected because the decision asks for a background mark. The footer is drawn on top and identifies the copy either way.
- **PyMuPDF.** It is faster and a single library, but it is AGPL-licensed, which conflicts with the commercial track.
- **Fail open.** Downloads would never break on an odd PDF, but the guarantee would weaken to "usually watermarked".

## Decision Rationale

Downloading is the act that produces a copy leaving IRIS. Gating it, and later marking every copy, gives RDCO a record of who holds which copy, without changing how research is read or cited inside IRIS. Shipping the gate before the watermark closes today's ungated button sooner.

## Consequences

- **The gate is a deterrent, not a control.** The reader fetches the full PDF to render it, so a determined reader can still save an unmarked copy using browser tools. Closing that gap means either watermarking the reader's copy too, which costs a per-request PDF rewrite and breaks range requests and caching, or gating the full text, the first alternative above. Either one is a later decision for a person to make.
- **Until IR-676 lands, downloaded copies are unmarked.** They are still attributable through the audit log.
- On a scanned page that is one opaque image, the background "CIT-U" is hidden beneath the image. The footer still identifies the copy.
- Watermarked downloads cost CPU per request. The time for the largest dev-corpus manuscript is recorded in IR-676.
- Links already emailed stop working when `DownloadRedeemView` is removed. Their holders get a grant through decision 8 and download while signed in.
- Two new dependencies go through IR-613's audit gate when IR-676 lands.

## MVP Impact

The download request becomes usable for the first time: a button and states on the Record page, a My Library view, notes, cancel and revoke, and a grant. RDCO's queue gains notes, revoke and grant expiry.

## SaaS Impact

The watermark text names CIT-U. A second institution would need it to come from configuration, the same as the existing installation-wide institution label.

## Security Impact

It removes a forwardable bearer token from email (ASVS 8.3.1) and narrows approval to RDCO (ASVS 4.1.3). Every download is audited, and every copy is attributable once IR-676 lands. It does **not** prevent a reader saving what the reader displays (see Consequences).

## Deployment Impact

Migrations add to `DownloadRequest` the reader's note, RDCO's note, the grant expiry, and the revoked and cancelled states, and give existing approvals a grant. One new setting, `DOWNLOAD_GRANT_DAYS`. pypdf and reportlab are added to `requirements/base.txt` with IR-676. No new service.

## Research Impact

None on the workflow contribution or RAG. Reading and citations are unchanged.

## Related Requirements

NFR-S labels for access control and audit in `docs/testing/TRACEABILITY.md`.

## Related Tasks

IR-672 (spec, under IR-671), IR-673 (this ADR), IR-674, IR-675, IR-677, IR-688, and IR-676 (the watermark, belonging to IR-687, S2 Epic: QA & Security). IR-664 is superseded by IR-675. Also IR-165 and IR-316.
