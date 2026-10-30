# IR-214 code evidence inventory

Status: CURRENT code evidence collected 2026-10-30. This is not a verified production inventory or approved policy. Paths are relative to the repository root. Configuration defaults do not establish deployment configuration.

Core claims were cross-checked against the task worktree baseline `68f2bd52cbbf772ca6f7fdb1cf3331212b6a6c66`: record visibility/deletion, account consent storage, conversation ownership/deletion/lifetime, surviving audit identifiers, browser auth storage, inference dialects and disabled-by-default feature boundaries. The remaining operational inventory requires the operating team's confirmation. This package does not claim live deployment verification or comprehensive security auditing.

| Area | Observed behavior | Evidence |
| --- | --- | --- |
| Accounts | Name, email, password hash, roles, verification/lock/activity flags, signup date, consent boolean, Student program or Adviser college/department, role approval history and session activity timestamps | `backend/apps/accounts/models.py` |
| Signup notice | Interim notice describes account registration and Adviser directory exposure. Signup acceptance is a boolean without a policy version or acceptance timestamp | `frontend/src/features/auth/DataNotice.tsx`; `backend/apps/accounts/models.py` |
| Research | Metadata, abstracts, manuscripts, supplementary files, owners/authors/adviser, classifications, IP flags, versions, submission consent stamps, extracted document text and processing errors | `backend/apps/records/models.py`; `backend/apps/documents/models.py` |
| Record access | Office roles see nondeleted records; owners and assigned advisers see their records; signed-in users can see published catalogue records. Anonymous users do not receive catalogue records | `backend/apps/records/models.py`, `RecordManager.visible_to`; `backend/core/enums.py` |
| Review | Decisions/comments, reviewers/times, office clearances, assignments, routing, revisions, document requests and deadlines. Some history survives account deletion with nullable user references | `backend/apps/reviews/models.py`; `backend/apps/documents/models.py` |
| Operations | Notifications, download/delete requests, audit metadata and identifiers. Audit records deliberately survive deletion of referenced users/records. Authentication lockout uses username/IP information | `backend/apps/notifications/models.py`; `backend/apps/records/models.py`; `backend/apps/audit/models.py`; `backend/config/settings/base.py` |
| AI storage | Conversations, questions, rewritten questions, answers, citations, raw model reasoning, summaries, research/routing metadata and embeddings. Conversation access is owner scoped; deleting a conversation cascades its turns | `backend/apps/ai/models/conversation.py`; `backend/apps/ai/views/conversations.py` |
| External processing | Configurable Groq/OpenRouter inference; Voyage embeddings/reranking transmit passages or queries; email uses configurable SMTP. OpenRouter data-collection denial is request behavior, not evidence of every provider's retention | `backend/apps/ai/inference/profiles.py`; `backend/apps/ai/providers/voyage.py`; `backend/apps/ai/providers/dialects.py`; `backend/config/settings/base.py` |
| Browser storage | Refresh token in sessionStorage, access token in memory; local/session login metadata; localStorage saved research/opportunity selections | `frontend/src/lib/authStorage.ts`; `authSession.ts`; `recordLibrary.ts`; `opportunityLibrary.ts` |
| Deletion | Research deletion generally marks a record deleted; accepted research requires RDCO approval. Conversations have no automatic expiry. No verified promise of universal erasure, backup deletion, vendor deletion or automatic account erasure follows | `backend/apps/records/views.py`; `backend/apps/ai/models/conversation.py`; `backend/apps/audit/models.py` |

## Deployment verification required

Identify actual hosting, database/file storage, backup and logging services, SMTP and AI providers, enabled task profiles and feature flags, processing locations, contracts and vendor retention. Do not inspect or reproduce secrets in this package.

AI research lane, durable queued chat, screening cache and shadow evidence decisions are conditional features; inspected defaults are off. AI Overview needs a configured summary model. Jev/TypeSafe paths must not be described as unconditionally active. The development disclosure bypass is not institutional policy.

## Decision evidence

IR-214 comments dated 2026-10-12 and 2026-10-14 record the approved interim notice and IR-540 / PR #273. ADR-019 and ADR-026 describe stored conversations and their deletion/lifetime; vendor-related decisions in ADR-015 and ADR-036 require operational verification rather than an assumption that every implemented integration is deployed.
