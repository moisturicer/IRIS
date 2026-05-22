# IRIS — Security Risk Register

Living register of **security risks**: threats, vulnerabilities, mitigations, and status. Review at each milestone per [SDLC_PROCESS](SDLC_PROCESS.md).

**Rating scale**

| Likelihood | Score | Impact | Score |
|------------|-------|--------|-------|
| Rare | 1 | Negligible | 1 |
| Unlikely | 2 | Minor | 2 |
| Possible | 3 | Moderate | 3 |
| Likely | 4 | Major | 4 |
| Almost certain | 5 | Critical | 5 |

**Risk score** = Likelihood × Impact. **Priority:** 1–6 Low, 7–12 Medium, 13–19 High, 20–25 Critical.

---

## Summary dashboard

| Priority | Open | Mitigated | Accepted |
|----------|------|-----------|----------|
| Critical | 0 | 0 | 0 |
| High | 3 | 2 | 0 |
| Medium | 5 | 3 | 1 |
| Low | 4 | 2 | 0 |

*Update counts when statuses change.*

---

## Risk register

| ID | Category | Threat / vulnerability | Affected assets | L | I | Score | Mitigation | Owner | Status |
|----|----------|------------------------|-----------------|:-:|:-:|-------|------------|-------|--------|
| **SR-01** | Auth | Brute-force password guessing | User accounts | 4 | 4 | 16 | django-axes 3-strike / 15 min lock; generic errors; audit failed logins | Backend | **Mitigated** (verify in UAT) |
| **SR-02** | Auth | Stolen JWT (XSS, device compromise) | Sessions, records | 3 | 4 | 12 | Short access TTL; refresh rotation; blacklist; CSP/XSS hygiene; HTTPS | Full stack | **Partial** — idle logout TODO |
| **SR-03** | Auth | Refresh token theft | Sessions | 3 | 4 | 12 | HttpOnly if moved to cookie; rotation + blacklist; secure storage guidance | Backend/FE | **Partial** |
| **SR-04** | AuthZ | Student calls reviewer approve API | Workflow integrity | 3 | 5 | 15 | DRF permissions + pipeline state checks; 403 + audit | Backend | **Mitigated** (per-endpoint test required) |
| **SR-05** | AuthZ | User accesses another user’s record by ID | IP data | 3 | 5 | 15 | Object-level permissions; queryset filtering by owner/role | Backend | **Open** — verify all detail views |
| **SR-06** | AuthZ | UI-only RBAC (hidden nav, direct URL) | All protected data | 4 | 4 | 16 | Every endpoint enforces role (NFR-S4); penetration-style role matrix tests | Full stack | **Partial** |
| **SR-07** | Workflow | Unauthorized stage bypass (wrong role approves) | Pipeline | 3 | 5 | 15 | State machine validates stage vs role; FR-M5-01 alt flow | Backend | **Open** until M5 finalized |
| **SR-08** | Data | Secrets committed to Git | All | 2 | 5 | 10 | `.gitignore` for `.env`; pre-commit secret scan; review PRs | Dev | **Mitigated** |
| **SR-09** | Data | Production `DEBUG=True` or weak `SECRET_KEY` | All | 2 | 5 | 10 | Deploy checklist [SECURITY.md](SECURITY.md) §10 | Ops | **Open** (pre-prod) |
| **SR-10** | Transport | HTTP in production | Credentials, PDFs | 2 | 5 | 10 | TLS 1.2+ NFR-S3; redirect HTTP→HTTPS | Ops | **Open** (pre-prod) |
| **SR-11** | Data | Unencrypted DB/media at rest | PDFs, PII | 3 | 4 | 12 | NFR-S1 volume encryption; media permissions | IT | **Open** (infra) |
| **SR-12** | Audit | Audit log deletion or tampering | Compliance | 2 | 4 | 8 | Append-only app logic; DB ACL; backups NFR-S5 | Backend/IT | **Partial** |
| **SR-13** | Upload | Malicious PDF (malware, zip bomb) | Server, users | 3 | 4 | 12 | Size cap; MIME check; scan if IT provides AV | Backend | **Open** |
| **SR-14** | Upload | Path traversal in filenames | Filesystem | 2 | 4 | 8 | Sanitize stored names; chroot media root | Backend | **Open** |
| **SR-15** | API | DoS via expensive AI/indexing | Availability | 3 | 3 | 9 | Rate limits; queue workers; auth required | Backend | **Partial** |
| **SR-16** | API | DRF throttle too loose for prod | API | 3 | 3 | 9 | Tune anon/user rates; WAF if available | Backend | **Open** |
| **SR-17** | CORS | `CORS_ALLOW_ALL` in production | Tokens, data | 2 | 4 | 8 | Production settings whitelist only | Backend | **Mitigated** in prod settings pattern |
| **SR-18** | Privacy | Processing IP without DPA consent | Legal/compliance | 3 | 5 | 15 | FR-M6-02 modal + audit before submit | Full stack | **Open** |
| **SR-19** | Third party | Data leakage to Anthropic/embeddings | Record content | 3 | 4 | 12 | Institutional approval; minimal context; opt-out path | Product | **Open** |
| **SR-20** | Email | SMTP credential theft | Mail account | 2 | 3 | 6 | App passwords; env secrets; TLS | Ops | **Partial** |
| **SR-21** | Spec | Implementing wrong M5/M7 workflow in code | Workflow, trust | 4 | 4 | 16 | Generic UI; API-driven states; OD log; stakeholder sign-off | Product/Dev | **Accepted** (process mitigation) |
| **SR-22** | Ops | Redis/PostgreSQL exposed to internet | All | 2 | 5 | 10 | Firewall; bind localhost/VPC only | IT | **Open** |
| **SR-23** | Dependency | Vulnerable Python/npm packages | All | 3 | 4 | 12 | Regular `pip audit` / `npm audit`; pin versions | Dev | **Open** |
| **SR-24** | Session | Access token TTL > idle policy (60 vs 30 min) | Sessions | 3 | 3 | 9 | Align JWT and NFR-S2; idle logout in AppShell | Frontend | **Open** |

---

## Treatment plan by priority

### High (score ≥ 13) — address before production

| ID | Next action | Target date |
|----|-------------|-------------|
| SR-04, SR-06 | Automated API tests: forbidden role matrix | M1 complete |
| SR-05 | Audit all `Record` detail/update views for object-level checks | M2 |
| SR-07 | Formalize pipeline FSM when M5 SRS frozen | M3 |
| SR-18 | Implement DPA consent + audit event | M2 |
| SR-21 | Close OD-01–04 in engineering plan | Stakeholder meeting |

### Medium — schedule in beta

| ID | Next action |
|----|-------------|
| SR-02, SR-24 | Ship 30 min idle logout; review access token minutes |
| SR-11, SR-22 | IT infrastructure review |
| SR-13, SR-14 | Harden upload handlers |
| SR-19 | Legal + AI data processing agreement |

---

## Residual risk acceptance

| ID | Condition for acceptance |
|----|--------------------------|
| SR-21 | Documented in [SOFTWARE_ENGINEERING_PLAN §10](SOFTWARE_ENGINEERING_PLAN.md#10-open-decisions-spec-uncertainty); no KTTO/RDCO-specific UI until sign-off |
| SR-19 | Accepted only if CIT-U approves third-party AI processing in writing |

**Sign-off (production):**

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Project lead | | | |
| CIT-U IT / Security | | | |

---

## Review log

| Date | Reviewer | Notes |
|------|----------|-------|
| 2026-05 | Initial register | Baseline from SRS NFR-S*, stack review |

---

*Update this table when risks are discovered, mitigated, or accepted. Link new mitigations to PRs in the review log.*
