# ADR-051: The System Admin is its own role, and people can delete their accounts, get their data and withdraw consent

## Status

**Accepted** — 2026-11-01 by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado (IR-780, spec IR-779). The decisions come from design sessions with Hermoine Zozobrado on 2026-11-01. **None of it is built yet.**

**Partly replaced by [ADR-054](054-each-person-answers-whether-ai-may-use-their-papers.md), 2026-11-02:** Submission consent is gone. Decision 14's per-paper half, the last sentence of decision 15, decision 16's submission notice and the first half of decision 18 no longer apply.

It reverses IR-165's choice that `admin@cit.edu` holds no application role, though not IR-165's rule that `is_superuser` grants nothing in the API. It changes [ADR-050](050-calls-for-papers-and-rdco-confirmation.md) decision 15, gives "system administrator" in [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) a meaning, widens [ADR-029](029-proposal-similarity-and-collaboration.md)'s choice of Contact person from Proposals to every paper, and answers IR-705's open decision.

The data protection officer's review under IR-123 can change the wording of any notice, the retention periods and the withdrawal rule. Nothing here is legal advice.

## Context

Observed on `main`, 2026-11-01:

- **"Administrator" means two things.** `core.permissions.ADMIN_ROLES` is `{RDCO}`, and `seed_demo` calls RDCO "IRIS's administrator". ADR-032, `CONTEXT.md` and the Settings page speak of "a system administrator" as someone else, but no such role exists. `admin@cit.edu` is a Django superuser with no role, and it can only open Django's admin site, which registers record files, turnarounds and holidays.
- **`/admin/` points at two things.** RDCO's pages live under `/admin/`, and `frontend/nginx.conf` sends every `/admin/...` address to Django in production. Opening or refreshing RDCO's page directly should therefore reach Django, while clicking through the app works. Development hides this because Vite proxies only `/api`. This comes from reading the config and hasn't been reproduced. IR-668 would close `/admin/` to outside networks, including those pages.
- **Nobody can delete their account or get a copy of their data.** Deleting a `User` row cascades into `RecordOwner`, `DownloadRequest`, `DeleteRequest`, review and document rows. `AuditEvent` is insert-only at the database (IR-166).
- **Consent has no version.** `User.consent_given` is a boolean, and `Record.dpa_accepted_at` is a stamp. Neither records which notice was accepted, and neither can be withdrawn. `docs/compliance/IR-123-processing-review.md` lists these as unbuilt.
- **Notice text lives in frontend code** (`DataNotice.tsx`, `lib/dpaTerms.ts`), so changing it takes a release. IR-214 is still waiting on the university's real text.
- **Nothing erases old data.** `CELERY_BEAT_SCHEDULE` holds only deadline notifications and recovery dispatch, and the compliance review's retention checklist is open.
- **RDCO isn't told about role requests.** `notify_role_request` exists, but nothing calls it. `accounts/tasks.py` holds two functions containing only a TODO.
- **Some work can't change hands.** Nobody can replace a paper's Adviser, and `owner_emails` works on drafts only. An office coordinator can already withdraw a reviewer's seat and seat someone else.
- **Signups aren't checked.** Registration accepts any email address. RDCO's lists show unverified accounts, RDCO can approve one, and an owner can add one as a co-owner. A mistyped address leaves an account that nothing ever removes (IR-705).
- **The Contact person can't be changed.** Decisions, revision requests and document requests email only that owner, while every owner gets the in-app notice. `set_primary_owner` has no callers.

## Decision

### Roles

1. **The System Admin is a role of its own, separate from RDCO.** RDCO is the highest office staff role and runs the research workflow. The System Admin runs IRIS itself.
2. **It holds no workflow access.** It isn't in `STAFF_ROLES` or `REVIEWER_ROLES`, joins no reviewer pool, and sees only the public catalogue.
3. **The System Admin does four things:**
   - confirms or rejects account deletion requests;
   - sets retention periods and any other system setting;
   - alone reads the Audit Log and its export;
   - shares removing comments and publishing notices with RDCO.
4. **RDCO keeps** users, role requests, office coordinators, active sessions, download requests, delete requests and analytics. It loses the Audit Log. Analytics read audit events directly and are unaffected.
5. **Nobody can ask for the role.** It can't be requested at registration or granted through the Users page, and RDCO can't grant it, remove it, lock the account or revoke its sessions. Developers create the first account with a server command.
6. **Each System Admin is a named person's account, and not a Django superuser,** so the role doesn't open Django's admin site. Only the demo login `admin@cit.edu` holds both.

### Addresses

7. **Each address has one owner:**

   | Address | Who uses it |
   |---|---|
   | `/admin/...` | The System Admin's pages, in the **Administration** nav section |
   | `/rdco/...` | RDCO's pages, in a nav section named **RDCO** |
   | `/moderation/comments` | Reported comments, shared by both roles |
   | `/notices` | Publishing notices, shared by both roles |
   | `/django-admin/` | Django's admin site, which IR-668 closes to outside networks |

   Old addresses get no redirects, because IRIS isn't deployed.

### Account deletion

8. **A person requests deletion in Settings, and a System Admin confirms or rejects it.** A rejection needs a reason the person receives. Nobody decides their own request.
9. **Confirmation is refused while someone is waiting on that person.** The System Admin sees what's blocking it, and RDCO, a coordinator or the person clears it:

   | What the person still has | What happens |
   |---|---|
   | A draft nobody else is waiting on | Deleted with the account |
   | A paper in review with no other owner | Withdrawn, or given another owner, first |
   | A paper with another owner | That owner carries on (decision 28 covers the Contact person) |
   | Open reviews as an Adviser or office reviewer | Reassigned first |

10. **RDCO gains three acts on any paper,** so every blocker can be cleared: replace its Adviser, add an owner to a paper in review, and withdraw a paper in review with a required reason.
11. **On confirmation, the account's personal details and private data go, and the person can't sign in.** The row stays, because deleting it would cascade into ownership and review history. What others see afterwards:

    | Where the name appeared | After deletion |
    |---|---|
    | A published paper's Authors | Stays |
    | Adviser on a published paper | Name stays as plain text, with no link |
    | Profile, people search, Adviser picker, reviewer pools | Gone |
    | Comments, review history and a Call's Posted by | "Former user" |
    | Audit Log | Unchanged |

    Someone with a serious reason to have their name removed from a paper raises it with RDCO as a separate case.
12. **The freed email can register again,** as a new account with no link to the old one.

### Personal data and consent

13. **A person downloads their own data from Settings,** with no RDCO work. It leaves out other people's data and all credentials.
14. **Two consents record a notice version.** Signup consent covers having an account, and Submission consent covers AI use of one paper. A history keeps each acceptance. Existing rows are marked "version unknown", never as accepting the current notice. The Discoverable setting stays its own decision.
15. **When the signup notice changes, a person must accept it at their next sign-in.** Until then they can only accept, sign out or request deletion, and the server enforces this. Their papers stay as they are. How older papers are treated after a change to the submission notice is IR-123's decision.
16. **RDCO or the System Admin publishes a new notice by pasting it.** The Notices page holds one large text field per notice, filled with the current text, plus a preview. Publishing takes effect at once, after a confirmation saying who must accept. New registrants see the current signup notice, and anyone submitting a paper for the first time sees the current submission notice.
17. **A published version never changes.** Every publish is a new version, even for a typo, and old versions stay readable on the page, so IRIS can always show what someone accepted. The text shows as plain text with its line breaks, with no HTML, formatting or clickable links. Publishing doesn't count as accepting. The first versions are today's notice text, moved out of frontend code.
18. **Withdrawing Submission consent stops AI use of that paper and removes its stored passages, vectors and AI Overview from IRIS.** The paper stays in its workflow, and the original acceptance stays on record beside the withdrawal. One owner's withdrawal applies to the whole paper until that owner accepts again. Withdrawing Signup consent means account deletion. The notice must say that text already sent to vendors can't be recalled.
19. **One scheduled job erases old personal data by type,** using a retention period the System Admin enters after the data protection officer approves it. All start blank, and a blank period erases nothing. No default exists in the code, and audit rows are exempt.

### Role requests and unverified signups

20. **RDCO gets the existing in-app notification once the person has verified their email,** so a mistyped address alerts nobody (IR-705). Both empty email tasks are deleted. Verification emails are sent directly and keep working.
21. **Registration accepts only the configured email domain,** `cit.edu` here. Existing accounts and accounts made by server commands aren't affected.
22. **RDCO sees verified accounts only,** on the role request list, the Users page and the user detail view. An unverified account's role request can't be approved.
23. **Only a verified account can be a co-owner.**
24. **An account still unverified after 30 days is deleted outright,** with its role request. The period is a setting, not a retention period, because this removes data sooner and shouldn't wait for the officer. Unlike decision 11, the row goes: the account never signed in, and decision 23 leaves nothing depending on it.
25. **Registering again on an unverified address replaces the abandoned signup.** The earlier link stops working and a fresh one goes out, within [ADR-045](045-account-recovery-contract.md)'s send limits. A verified address still says "already registered".
26. **The verification email names who registered,** and says to ignore it if that wasn't them, because the account is deleted in 30 days.

### Contact person

27. **Any owner can name any co-owner as Contact person,** from one dropdown, on every paper, at any time until the paper is deleted. Both people are told in-app, and the change is audited. RDCO has no say. The choice decides who gets the review emails and, on a Discoverable Proposal, whose email is shared.
28. **If the Contact person's account is deleted, the longest-standing remaining owner takes over** and is told.

### Timing

29. **All of this is built now, before deployment,** rather than holding the personal-data work until real people sign up.

## Alternatives Considered

- **RDCO does the System Admin's jobs.** Nothing new to build. Rejected: RDCO is office staff, and account deletion and the Audit Log shouldn't sit with the office whose acts they record.
- **Move all administration from RDCO to the System Admin.** One clean split. Rejected: it changes finished screens, and approving roles and answering requests are office work.
- **Keep RDCO under `/admin/` and only move Django's admin.** Fewer changes. Rejected: `/admin/` is for the System Admin.
- **Keep `admin@cit.edu` as a shared production login.** Easy to set up. Rejected: the audit trail couldn't say who acted.
- **Delete the `User` row.** A true delete. Rejected: it would silently remove ownership, reviews and documents.
- **Delete immediately, without the System Admin.** It respects the request faster. Rejected: it strands papers and reviews, and the person asked for an administrator to decide.
- **Remove the name from published papers.** The most complete erasure. Rejected: it leaves papers without credit, and the published record shouldn't change because an account closed.
- **Handle data requests by hand through RDCO.** Cheaper to build. Rejected: slower, and easy to get wrong.
- **Let people continue under the old notice.** Nothing blocks them. Rejected: consent would mean little.
- **Keep notices in code, changed by a release.** A developer and a review check every change. Rejected: the people responsible for the text couldn't publish it, and each change would wait on a deployment.
- **Let a small correction skip re-acceptance.** A typo fix wouldn't interrupt anyone. Rejected: someone has to judge what counts as small, and then the version no longer proves what was accepted.
- **Require a second person to approve a publish.** It catches a bad paste. Rejected for now, in favour of one large field: the officer's approval happens outside IRIS.
- **Allow formatting and links in notices.** Easier to read. Rejected: plain text can't carry a harmful link to every user, and it pastes cleanly from any document.
- **Require every owner to agree before AI use stops.** Kinder to a group. Rejected: it ignores one person's choice.
- **Build the cleanup later.** Less work now. Rejected: real data may exist by then.
- **Set retention periods in code.** Simple. Rejected: nobody on the team can decide a legal period, and the System Admin must be able to change one.
- **Email RDCO about each role request.** Reaches them sooner. Rejected: more mail for each registration, and the in-app notifier already exists.
- **Accept any email address.** Alumni and outside advisers could register themselves. Rejected: RDCO would have to judge each one, and it contradicts what the glossary already says.
- **Delete unverified accounts after 7 days.** Frees a blocked address sooner. Rejected by Hermoine Zozobrado in favour of 30 days, which gives slow registrants longer. Decision 25 frees the address anyway.
- **Let RDCO remove unverified accounts from the Users page.** Helps someone who calls. Rejected: that page should show verified accounts only, and decision 25 needs no RDCO work.
- **Make the real owner of a mistyped address wait out the 30 days.** Nothing to build. Rejected: they'd be blocked for up to a month, or end up verifying an account with someone else's name on it.
- **Add a "This wasn't me" link to the email.** Deletes the account at once. Rejected: more to build, and a mail scanner opening links could delete real signups.
- **Require the named Contact person to accept first.** Nobody's email is shared without their say. Rejected: it adds a waiting state, and a co-owner who never answers blocks the change.
- **Let people only claim the Contact person role for themselves.** Also protects the email. Rejected: a Contact person couldn't hand it to someone who doesn't act.
- **Hold the personal-data work until real signups.** Validation with demo accounts would start sooner. Rejected by Hermoine Zozobrado in favour of building it now.

## Decision Rationale

The team already treats the System Admin and RDCO as different people, and the code doesn't. Giving each its own role, addresses and pages settles a confusion that ADR-032, the glossary and the Settings page each carry. It also gives the personal-data work a clear decider who isn't part of the research workflow.

Account deletion keeps the row because this system's value is a trustworthy history. The person's details leave, and the facts about papers and decisions stay.

Publishing notices from IRIS lets the university's own text go live without a developer, which is what IR-214 has been waiting for. Fixed versions keep each acceptance provable.

## Consequences

- **Audit rows keep a deleted person's name and email,** because they're insert-only. The notice has to say so, and the officer may disagree.
- **A deletion can take time,** even though the person asked for it, because others must clear the blockers first.
- **Names stay on published papers,** as Authors and as Adviser.
- **RDCO can no longer read the Audit Log,** including its own acts. Running the thesis evaluation's audit export (`docs/evaluation/AUDIT_EXPORT.md`) now needs a System Admin.
- **One owner can turn off AI for the others,** and the others are told.
- **An owner who refuses a changed notice can hold up their own paper in review.**
- **One person can change a legal text alone,** and a paste goes live to everyone at once. The confirmation and preview reduce mistakes but don't prevent them, and nothing in IRIS checks that the officer approved the text.
- **A typo fix makes everyone accept again,** so a publish interrupts all active users, including whoever published it.
- **A pasted notice can drift from what IRIS does.** Today's text was checked against the code, and pasted text isn't.
- **Notices lose headings, bold text and clickable links.**
- **Alumni and outside advisers can't register themselves,** and someone would have to create those accounts another way.
- **The domain check doesn't catch a typo inside a CIT-U address.** `mraia@cit.edu` still gets through, which is why decisions 24 to 26 exist.
- **RDCO can't look up someone who hasn't verified.** It tells them to resend the link or register again.
- **Someone who waits over 30 days registers again.**
- **A co-owner's email can reach other proposers before they react,** if they're named Contact person on a Discoverable Proposal.
- **A lone System Admin's own request can't be decided** until a developer creates a second account.
- **Nothing is erased until the officer approves periods.**
- **Text already sent to vendors stays with them,** subject to their terms.
- **RDCO has new power over papers.** Replacing an Adviser and withdrawing a paper are audited, but no second person checks them.
- **Two things have to keep up as features ship:** what a deletion removes, and what the download includes. A test fails when a new model isn't declared in each.
- **Existing tests change deliberately:** `test_seed_demo.py` pins "no application role" for `admin@cit.edu`.

## MVP Impact

All of it is `mvp-required` and lands before deployment (decision 29). That adds IR-779's 20 subtasks, IR-705 and IR-801 ahead of MVP validation, so validation starts later than it otherwise would. `IR-668` should restrict `/django-admin/`, and the deployment specs still to come should assume these addresses.

## SaaS Impact

The split maps to any institution: an IT administrator and a research office. Notice versions, retention periods and the registration domain are per deployment today, and would become per institution under multi-tenancy.

## Security Impact

It separates the people who hold the workflow from the person who reads its record. A compromised System Admin can read the whole Audit Log, including names and emails, but no unpublished paper. A compromised RDCO account can't read or export the trail of what it did. It also closes the risk that the network restriction in IR-668 misses or breaks IRIS's own pages.

IRIS still has no MFA (IR-652), which matters more for a role that confirms irreversible deletions. The authorization matrix gains a System Admin actor (IR-781).

A compromised RDCO or System Admin account can put text in front of every user and make them all accept again. Plain text with no links limits what that text can do, and an audit event names who published it. Reading the current notice has to work without signing in, because registrants need it, so it exposes only the notice text.

Decision 25 widens a risk that already exists. Someone could replace a real person's pending signup with their own name and password. If that person clicks the new link, their address is verified on an account the other person can sign in to. Today this can happen only to an address that hasn't registered yet. The email names who registered, and RDCO still has to approve the role. Ashlee reviews this before IR-705 merges. Decisions 21 to 23 narrow who can reach RDCO or become an owner.

## Deployment Impact

nginx proxies `/django-admin/` and lets `/admin/` and `/rdco/` reach the app (IR-782). The runbook needs the command that creates the first System Admin, and the Beat schedule gains the daily jobs (IR-794, IR-705). Registration needs its domain set. Dropping the old Django address breaks any bookmark to it, which matters only for developers today.

## Research Impact

The workflow's clearance rules don't change, and neither does clearance-aware resubmission. Replacing an Adviser is a new workflow act, audited like the others. The audit export used for evaluation moves to the System Admin, with no change to its contents.

## Related Requirements

`FR-M6-06` (a stable label). RA 10173 §16's data subject rights, including access, objection and erasure, for the data protection officer to confirm.

## Related Tasks

IR-779 (spec), IR-780 to IR-795 and IR-797 to IR-800 (subtasks), IR-705 (unverified signups), IR-801 (Contact person). Touches IR-123, IR-165, IR-214, IR-311, IR-420, IR-643, IR-655, IR-667, IR-668, IR-691, IR-693, IR-721, IR-763 and IR-765.
