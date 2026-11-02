# ADR-053: The threat model IRIS is defended against

## Status

**Accepted** — 2026-11-02 by Ashlee Sean, after review ([IR-617](https://citiris.atlassian.net/browse/IR-617)). Drafted by an AI agent.

## Context

IRIS holds unpublished research and IP disclosures. A leak before filing can destroy patentability, and that can't be undone. Its controls were built ticket by ticket, so nothing yet says which attacker each control is for, or which threats have no control.

This ADR writes that down. [`docs/testing/SECURITY_CHECKLIST.md`](../testing/SECURITY_CHECKLIST.md) checks the same system against OWASP ASVS 4.0.3 Level 1, and [`docs/security/SECURITY.md`](../security/SECURITY.md) §11 holds the open risk list.

## Decision

Use the assets, actors, boundaries and threats below as the threat model. Each threat maps to an existing control or to a ticketed gap. A new trust boundary or asset updates this ADR.

### Assets

| Asset | Why it matters |
|---|---|
| Unpublished manuscripts | Pre-publication research, and the core of what IRIS stores |
| IP disclosures | A leak before filing can destroy patentability |
| Embargoed records | Disclosure breaks an obligation to the author or a partner |
| Review findings | Ethics and IP judgements about named people's work |
| Accounts | Personal data under RA 10173, and each account's reach into the above |
| Provider spend | Paid AI calls can be run up by abuse or a bug |

### Actors

| Actor | Starting position |
|---|---|
| Anonymous visitor | Reaches public sign-in, registration and recovery routes only |
| Student | Owns their records and reads the public catalogue |
| Adviser | Also reads records they advise |
| Office reviewer | Reads what their office reviews |
| RDCO | Holds administrator powers today, until [IR-781](https://citiris.atlassian.net/browse/IR-781) |
| Django superuser | Holds Django's admin site, a separate path to the database |
| Compromised account | Any of the above, used by someone else |
| Prompt injection through an uploaded paper | Text in a PDF that tries to instruct a model reading it |

### Trust boundaries and STRIDE threats

STRIDE means Spoofing, Tampering, Repudiation, Information disclosure, Denial of service and Elevation of privilege.

**Browser ↔ nginx ↔ Django**

| | Threat | Control or gap |
|---|---|---|
| S | Password guessing, stolen credentials | Lockout on the real client address ([IR-656](https://citiris.atlassian.net/browse/IR-656)), rate limits ([IR-661](https://citiris.atlassian.net/browse/IR-661)), recovery ([IR-642](https://citiris.atlassian.net/browse/IR-642)). Gap: password rules ([IR-819](https://citiris.atlassian.net/browse/IR-819)). SSO and MFA deferred ([IR-652](https://citiris.atlassian.net/browse/IR-652)) |
| S | A stolen session stays usable | Idle expiry ([IR-166](https://citiris.atlassian.net/browse/IR-166)), revoke ([IR-657](https://citiris.atlassian.net/browse/IR-657)), ending sessions on lock or password change ([IR-644](https://citiris.atlassian.net/browse/IR-644)). Gap: no notice on password change ([IR-820](https://citiris.atlassian.net/browse/IR-820)) |
| T | Forged client address in `X-Forwarded-For` | `TRUSTED_PROXY_COUNT` ([IR-656](https://citiris.atlassian.net/browse/IR-656)) |
| T | Traffic altered in transit | Caddy serves HTTPS, and nginx isn't published ([IR-847](https://citiris.atlassian.net/browse/IR-847), ADR-056). Gap: not yet run on a deployed domain |
| R | Denying a sign-in or an act | Insert-only audit log ([IR-166](https://citiris.atlassian.net/browse/IR-166)), workflow events ([IR-144](https://citiris.atlassian.net/browse/IR-144)). Gap: refused sign-ins aren't audited ([IR-659](https://citiris.atlassian.net/browse/IR-659)) |
| I | Reading a record or file by guessing its id | One `visible_to` predicate ([IR-153](https://citiris.atlassian.net/browse/IR-153)), route matrix ([IR-615](https://citiris.atlassian.net/browse/IR-615), [IR-616](https://citiris.atlassian.net/browse/IR-616)), no public `/media/` ([IR-152](https://citiris.atlassian.net/browse/IR-152)) |
| I | Script injection reading tokens | React escaping, report-only CSP. Gap: enforce it ([IR-823](https://citiris.atlassian.net/browse/IR-823)). Gap: unpinned CDN stylesheet ([IR-822](https://citiris.atlassian.net/browse/IR-822)) |
| I | Cached responses on a shared computer | Gap: [IR-821](https://citiris.atlassian.net/browse/IR-821) |
| D | Request floods, huge uploads | Rate limits, 50 MB upload limit |
| E | Role escalation through the API | Application role only ([IR-165](https://citiris.atlassian.net/browse/IR-165)), route matrix |
| E | Django's admin reached from the internet | Gap: it stays at `/admin/` until [IR-782](https://citiris.atlassian.net/browse/IR-782) moves it behind [IR-668](https://citiris.atlassian.net/browse/IR-668)'s allowlist |

**Django ↔ Celery and Redis**

| | Threat | Control or gap |
|---|---|---|
| S, T | Someone on the host's network writes to the broker | Redis password and localhost binding ([IR-669](https://citiris.atlassian.net/browse/IR-669)). JSON-only Celery content, so a broker message can't run pickle |
| I | Reading tokens or data from Redis | Same. Every development port binds to localhost ([IR-828](https://citiris.atlassian.net/browse/IR-828)) |

**Django ↔ Docling**

| | Threat | Control or gap |
|---|---|---|
| T, E | A hostile PDF exploits the parser | PDF content check ([IR-665](https://citiris.atlassian.net/browse/IR-665)), Docling isn't published. Docling has no route out ([IR-825](https://citiris.atlassian.net/browse/IR-825)). Gap: malware scan ([IR-666](https://citiris.atlassian.net/browse/IR-666)) |
| D | A PDF that takes the parser down | 50 MB limit, worker separation on the `extraction` queue |

**Django ↔ Voyage and LLM vendors**

| | Threat | Control or gap |
|---|---|---|
| I | Withheld paper text reaches a vendor | Disclosure check (ADR-015, ADR-052), outbound guard ([IR-720](https://citiris.atlassian.net/browse/IR-720), partial) |
| I | A vendor trains on or retains the text | Gap: no recorded evidence of the settings ([IR-827](https://citiris.atlassian.net/browse/IR-827)) |
| T | Prompt injection in a paper changes an answer | Retrieval is limited by `visible_to` before scoring, so injected text can't reach papers the reader can't see. **How far an answer can be steered is not measured**, and [IR-829](https://citiris.atlassian.net/browse/IR-829) checks it |
| D | Spend run up by abuse | `ai_query` rate limit, provider admission (ADR-041, off by default) |

**AI gateway**

| | Threat | Control or gap |
|---|---|---|
| S | An outside caller uses the vendor key | Shared service secret, no published port, no CORS (`ai/main.py`) |
| E | The gateway bypasses Django's visibility rule | Gap: it still receives `DATABASE_URL` ([IR-826](https://citiris.atlassian.net/browse/IR-826)) |

## Consequences

**Gains:**

- Every control now has a stated reason, so removing one has a visible cost.
- Each gap has a ticket.
- The ASVS checklist has something to point at for 11.1.5, the business risks IRIS has identified.

**Costs:**

- It goes stale unless a boundary change updates it, and only review enforces that.
- It lists threats from reading the code, without a penetration test. The severities in `SECURITY.md` are estimates until a reviewer confirms them.

**Rejected:** a separate risk register, because `SECURITY.md` §11 already is one and two lists would drift.
