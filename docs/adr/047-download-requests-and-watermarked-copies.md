# ADR-047: Downloading a manuscript needs an approved request, and every downloaded copy is watermarked

## Status

**Proposed** — 2026-10-30 (IR-673, spec IR-672). The decisions below were made by a team member in a design session on 2026-10-30 and are transcribed here by an agent. **Not accepted**: a named person accepts this record. IR-675, IR-676 and IR-677 stay `not-ready` until then. IR-674 (only RDCO approves) restores IR-165's existing intent and does not wait for this ADR.

## Context

Observed on `main`, 2026-10-30:

- `DownloadRequest` exists, with a queue for RDCO at `/admin/download-requests`. An approval emails a 24-hour HS256 bearer link (`apps/records/download_tokens.py`). `DownloadRedeemView` (`AllowAny`) redeems it any number of times, writes no audit row, and carries a TODO for a watermark.
- **No page renders `DownloadRequestModal`**, so a reader has no way to ask.
- The Paper reader (`GET /records/<id>/manuscript/`, inline, IR-335) serves the full manuscript to anyone `visible_to` admits. Its own download button (`PaperPdfReader.handleDownload`) saves those bytes. So downloading is effectively ungated today.
- Approval rights disagree. `partial_update` and the UI admit RDCO only, as IR-165 intended, while the `approve` and `decline` actions admit any of the four offices (`IsStaff`).
- No PDF-editing library is installed. PyMuPDF was removed with the prototype extractors (ADR-016).

## Decision

1. **Reading stays open; downloading is gated.** The in-app reader keeps rendering the full text for everyone `visible_to` admits, so Ask IRIS citations, which open the paper at a page, are unchanged. Saving a copy of the manuscript needs an approved request.
2. **Some readers are exempt from the request:** the record's owners, its adviser, the four offices and its assigned reviewers. They download without one, and their copies are watermarked like everyone else's.
3. **RDCO alone approves or declines** a download request.
4. **An approval is a time-limited grant, not a link.** It lasts `DOWNLOAD_GRANT_DAYS` (default 30). The grantee downloads from the Record page while signed in, as often as they like within the grant. **No bearer token is issued or emailed**: the approval email links to the record. `DownloadRedeemView` and `download_tokens.py` are removed. A declined or expired request may be made again.
5. **Every downloaded copy is watermarked.** The watermark is built per download and never stored:
   - a footer on every page: "Downloaded by <name> (<email>) on <date> via CIT-U IRIS · request #N", or the exemption reason in place of the request;
   - a large grey diagonal **"CIT-U"** drawn in each page's background, beneath the content;
   - the same identity, date and request in the PDF's metadata.
6. **Fail closed.** A copy that cannot be watermarked is not served. The failure is audited and the reader is told to contact RDCO.
7. **Every download is audited** as `DOWNLOAD`, with its source (`grant` or `exempt`) and the request.
8. **Libraries:** pypdf merges the pages and reportlab draws the overlay. Both are BSD-licensed.

## Alternatives Considered

- **Gate the full text, not just downloads.** Without approval, the reader would show only metadata and the abstract. This is a real control. It was rejected for now because Ask IRIS citations would land unapproved readers on a request prompt instead of the page, which changes the RAG reading path (thesis-critical, owned by the RAG workstream).
- **Everything open, every copy watermarked, no approval step.** This is the simplest option and every copy is traceable. It was rejected because the team wants an explicit gate on downloading.
- **Keep the single-use bearer link (IR-664 as written).** It works without signing in. It was rejected because a link is a credential that can be forwarded, and signing in costs a pilot reader little.
- **A watermark drawn over the content at low opacity**, rather than beneath it. It would survive scanned pages, but it was rejected because the decision asks for a background mark. The footer is drawn on top and identifies the copy either way.
- **PyMuPDF.** It is faster and a single library, but it is AGPL-licensed, which conflicts with the commercial track.
- **Fail open.** Downloads would never break on an odd PDF, but the guarantee would weaken to "usually watermarked".

## Decision Rationale

Downloading is the act that produces a copy leaving IRIS. Gating it and marking every copy gives RDCO a record of who holds which copy, without changing how research is read or cited inside IRIS.

## Consequences

- **The gate is a deterrent, not a control.** The reader fetches the full PDF to render it, so a determined reader with an approval can still save an unmarked copy using browser tools. Closing that gap means either watermarking the reader's copy too, which costs a per-request PDF rewrite and breaks range requests and caching, or gating the full text, the first alternative above. Either one is a later decision for a person, and would supersede this ADR.
- On a scanned page that is one opaque image, the background "CIT-U" is hidden beneath the image. The footer still identifies the copy.
- Downloads cost CPU per request. The time for the largest dev-corpus manuscript is recorded in IR-676.
- Links already emailed stop working when `DownloadRedeemView` is removed. Holders request again or sign in, depending on their grant.
- Two new dependencies go through IR-613's audit gate.

## MVP Impact

The download request becomes usable for the first time: a button on the Record page, a status and a grant. RDCO's queue gains grant expiry.

## SaaS Impact

The watermark text names CIT-U. A second institution would need it to come from configuration, the same as the existing installation-wide institution label.

## Security Impact

It removes a forwardable bearer token from email (ASVS 8.3.1) and narrows approval to RDCO (ASVS 4.1.3). Every copy is attributable and every download audited. It does **not** prevent a reader saving what the reader displays (see Consequences).

## Deployment Impact

There is one migration (grant expiry on `DownloadRequest`) and one new setting, `DOWNLOAD_GRANT_DAYS`. pypdf and reportlab are added to `requirements/base.txt`. No new service.

## Research Impact

None on the workflow contribution or RAG. Reading and citations are unchanged.

## Related Requirements

NFR-S labels for access control and audit in `docs/testing/TRACEABILITY.md`.

## Related Tasks

IR-672 (spec), IR-673 (this ADR), IR-674, IR-675, IR-676, IR-677. IR-664 is superseded by IR-675. Also IR-165 and IR-316.
