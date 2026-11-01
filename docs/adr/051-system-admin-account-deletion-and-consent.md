# ADR-051: The System Admin is its own role, and people can delete their accounts, get their data and withdraw consent

## Status

**Proposed** — 2026-11-01 (IR-780, spec IR-779), awaiting acceptance by Lee Jasmin Adolfo, the project lead. The decisions come from a design session with Hermoine Zozobrado on 2026-11-01.

It would reverse IR-165's choice that `admin@cit.edu` holds no application role, though not IR-165's rule that `is_superuser` grants nothing in the API. It would change [ADR-050](050-calls-for-papers-and-rdco-confirmation.md) decision 15, and give "system administrator" in [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) a meaning.

The data protection officer's review under IR-123 can change the wording of any notice, the retention periods and the withdrawal rule. Nothing here is legal advice.

## Context

Observed on `main`, 2026-11-01:

- **"Administrator" means two things.** `core.permissions.ADMIN_ROLES` is `{RDCO}`, and `seed_demo` calls RDCO "IRIS's administrator". ADR-032, `CONTEXT.md` and the Settings page speak of "a system administrator" as someone else, but no such role exists. `admin@cit.edu` is a Django superuser with no role, and it can only open Django's admin site, which registers record files, turnarounds and holidays.
- **`/admin/` points at two things.** RDCO's pages live under `/admin/`, and `frontend/nginx.conf` sends every `/admin/...` address to Django in production. Opening or refreshing RDCO's page directly should therefore reach Django, while clicking through the app works. Development hides this because Vite proxies only `/api`. This comes from reading the config and hasn't been reproduced. IR-668 would close `/admin/` to outside networks, including those pages.
- **Nobody can delete their account or get a copy of their data.** Deleting a `User` row cascades into `RecordOwner`, `DownloadRequest`, `DeleteRequest`, review and document rows. `AuditEvent` is insert-only at the database (IR-166).
- **Consent has no version.** `User.consent_given` is a boolean, and `Record.dpa_accepted_at` is a stamp. Neither records which notice was accepted, and neither can be withdrawn. `docs/compliance/IR-123-processing-review.md` lists these as unbuilt.
- **Nothing erases old data.** `CELERY_BEAT_SCHEDULE` holds only deadline notifications and recovery dispatch, and the compliance review's retention checklist is open.
- **RDCO isn't told about role requests.** `notify_role_request` exists, but nothing calls it. `accounts/tasks.py` holds two functions containing only a TODO.
- **Some work can't change hands.** Nobody can replace a paper's Adviser, and `owner_emails` works on drafts only. An office coordinator can already withdraw a reviewer's seat and seat someone else.

## Decision

### Roles

1. **The System Admin is a role of its own, separate from RDCO.** RDCO is the highest office staff role and runs the research workflow. The System Admin runs IRIS itself.
2. **It holds no workflow access.** It isn't in `STAFF_ROLES` or `REVIEWER_ROLES`, joins no reviewer pool, and sees only the public catalogue.
3. **The System Admin does four things:**
   - confirms or rejects account deletion requests;
   - sets retention periods and any other system setting;
   - alone reads the Audit Log and its export;
   - shares removing comments with RDCO.
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
   | `/django-admin/` | Django's admin site, which IR-668 closes to outside networks |

   Old addresses get no redirects, because IRIS isn't deployed.

### Account deletion

8. **A person requests deletion in Settings, and a System Admin confirms or rejects it.** A rejection needs a reason the person receives. Nobody decides their own request.
9. **Confirmation is refused while someone is waiting on that person.** The System Admin sees what's blocking it, and RDCO, a coordinator or the person clears it:

   | What the person still has | What happens |
   |---|---|
   | A draft nobody else is waiting on | Deleted with the account |
   | A paper in review with no other owner | Withdrawn, or given another owner, first |
   | A paper with another owner | That owner carries on, and becomes Contact person if needed |
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
16. **Withdrawing Submission consent stops AI use of that paper and removes its stored passages, vectors and AI Overview from IRIS.** The paper stays in its workflow. One owner's withdrawal applies to the whole paper until that owner accepts again. Withdrawing Signup consent means account deletion. The notice must say that text already sent to vendors can't be recalled.
17. **One scheduled job erases old personal data by type,** using a retention period the System Admin enters after the data protection officer approves it. All start blank, and a blank period erases nothing. No default exists in the code, and audit rows are exempt.

### Role requests

18. **RDCO gets the existing in-app notification once the person has verified their email,** so a mistyped address alerts nobody (IR-705). Both empty email tasks are deleted. Verification emails are sent directly and keep working.

### Timing

19. **All of this is built now, before deployment,** rather than holding the personal-data work until real people sign up.

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
- **Require every owner to agree before AI use stops.** Kinder to a group. Rejected: it ignores one person's choice.
- **Build the cleanup later.** Less work now. Rejected: real data may exist by then.
- **Set retention periods in code.** Simple. Rejected: nobody on the team can decide a legal period, and the System Admin must be able to change one.
- **Email RDCO about each role request.** Reaches them sooner. Rejected: more mail for each registration, and the in-app notifier already exists.
- **Hold the personal-data work until real signups.** Validation with demo accounts would start sooner. Rejected by Hermoine Zozobrado in favour of building it now.

## Decision Rationale

The team already treats the System Admin and RDCO as different people, and the code doesn't. Giving each its own role, addresses and pages settles a confusion that ADR-032, the glossary and the Settings page each carry. It also gives the personal-data work a clear decider who isn't part of the research workflow.

Account deletion keeps the row because this system's value is a trustworthy history. The person's details leave, and the facts about papers and decisions stay.

## Consequences

- **Audit rows keep a deleted person's name and email,** because they're insert-only. The notice has to say so, and the officer may disagree.
- **A deletion can take time,** even though the person asked for it, because others must clear the blockers first.
- **Names stay on published papers,** as Authors and as Adviser.
- **RDCO can no longer read the Audit Log,** including its own acts. Running the thesis evaluation's audit export (`docs/evaluation/AUDIT_EXPORT.md`) now needs a System Admin.
- **One owner can turn off AI for the others,** and the others are told.
- **An owner who refuses a changed notice can hold up their own paper in review.**
- **A lone System Admin's own request can't be decided** until a developer creates a second account.
- **Nothing is erased until the officer approves periods.**
- **Text already sent to vendors stays with them,** subject to their terms.
- **RDCO has new power over papers.** Replacing an Adviser and withdrawing a paper are audited, but no second person checks them.
- **Two things have to keep up as features ship:** what a deletion removes, and what the download includes. A test fails when a new model isn't declared in each.
- **Existing tests change deliberately:** `test_seed_demo.py` pins "no application role" for `admin@cit.edu`.

## MVP Impact

All of it is `mvp-required` and lands before deployment (decision 19). That adds 18 subtasks ahead of MVP validation, so validation starts later than it otherwise would. `IR-668` should restrict `/django-admin/`, and the deployment specs still to come should assume these addresses.

## SaaS Impact

The split maps to any institution: an IT administrator and a research office. Notice versions and retention periods are per deployment today, and would become per institution under multi-tenancy.

## Security Impact

It separates the people who hold the workflow from the person who reads its record. A compromised System Admin can read the whole Audit Log, including names and emails, but no unpublished paper. A compromised RDCO account can't read or export the trail of what it did. It also closes the risk that the network restriction in IR-668 misses or breaks IRIS's own pages.

IRIS still has no MFA (IR-652), which matters more for a role that confirms irreversible deletions. The authorization matrix gains a System Admin actor (IR-781).

## Deployment Impact

nginx proxies `/django-admin/` and lets `/admin/` and `/rdco/` reach the app (IR-782). The runbook needs the command that creates the first System Admin, and the Beat schedule gains the daily job (IR-794). Dropping the old Django address breaks any bookmark to it, which matters only for developers today.

## Research Impact

The workflow's clearance rules don't change, and neither does clearance-aware resubmission. Replacing an Adviser is a new workflow act, audited like the others. The audit export used for evaluation moves to the System Admin, with no change to its contents.

## Related Requirements

`FR-M6-06` (a stable label). RA 10173 §16's data subject rights, including access, objection and erasure, for the data protection officer to confirm.

## Related Tasks

IR-779 (spec), IR-780 to IR-795, IR-797 and IR-798 (subtasks). Touches IR-123, IR-165, IR-214, IR-311, IR-420, IR-655, IR-667, IR-668, IR-691, IR-693, IR-705, IR-721, IR-763 and IR-765.
