# IRIS Frontend — Implementation Plan

This document tracks what we can build **now** against the SRS/SDD and current backend, aligned with the auth wireframes (login default, invalid credentials, session expired, account locked) and the Discover dashboard mockup.

> **Full stack process:** see the [Documentation hub](../../docs/README.md), [Software engineering plan](../../docs/SOFTWARE_ENGINEERING_PLAN.md), [SDLC process](../../docs/SDLC_PROCESS.md), [Security](../../docs/SECURITY.md), and [Development guide](../../docs/DEVELOPMENT_GUIDE.md).

**Stack:** React 18 · Vite · TypeScript · Tailwind · Zustand · React Router v6 · Axios

---

## Done (auth shell)

| Item | Route / file | SRS / wireframe |
|------|----------------|-----------------|
| Login page (default) | `/login` · `LoginPage.tsx` | FR-M1-01 · Figure 4 |
| Signup page | `/signup` · `SignupPage.tsx` | Self-service (repo extension) |
| Email verification | `/activate/:uidb64/:token` · `EmailVerifyPage.tsx` | Post-register verify |
| Auth layout theme | Cream / maroon / gold split panels | Module 1 responsive UI |
| Login error alert | `AuthAlert` · invalid credentials + attempt count | Figure 5 |
| Session expired alert | `AuthAlert` · `?reason=session_expired` | SDD Module 6 · NFR-S2 |
| Account locked modal | `AccountLockedModal` · 15 min countdown | Figure 6 · FR-M1-01 |
| Forgot password stub | Toast on “Forgot password?” | Future FR |
| Auth session helpers | `lib/authSession.ts` | FR-M1-01 attempt tracking |
| Shared lib | `constants.ts`, `utils.ts`, `signupData.ts` | — |

### Auth flow — modals & alerts (done)

| UI | Component | When shown | SRS |
|----|-----------|------------|-----|
| Invalid credentials box | `AuthAlert` (error) | Failed login (401), not locked; shows **Attempt X of 3** | FR-M1-01 · Fig. 5 |
| Session expired banner | `AuthAlert` (session) | `?reason=session_expired` or JWT refresh failure (`api/client.ts`) | NFR-S2 · SDD 6.1 |
| Account locked modal | `AccountLockedModal` | 3 failed attempts or API locked response | FR-M1-01 · Fig. 6 |
| Email not verified | `AuthAlert` (warning) | Login 403 `Email not verified.` | Register flow |
| Forgot password | Toast (info stub) | Click “Forgot password?” | Future FR |

**How to test locally**

1. Wrong password twice → error box with “Attempt 2 of 3”.
2. Third failure → lock modal with countdown.
3. Open `/login?reason=session_expired` → dismissible session banner.
4. Expire JWT (clear `access_token`, keep stale refresh) → API call redirects to login with banner.
5. Click “Forgot password?” → info toast.

**Not in wireframes (later):** DPA consent gateway modal (FR-M6-02), role-pending banner after signup, in-app `SessionExpiryModal` on idle (Phase 6).

---

## Phase 1 — App shell & navigation (next)

Matches Discover dashboard wireframe structure; reuse existing `AppShell`, `Sidebar`, `Header`.

| Task | Priority | SRS module |
|------|----------|------------|
| Rebrand sidebar (IR logo, “CIT-U Research Hub”, grouped nav) | High | FR-M1 responsive UI |
| Discover / Home route as default landing | High | — |
| Sign out in header | High | FR-M6-01 |
| Breadcrumbs (`Home / Discover`) | Medium | — |
| Mobile sidebar drawer | High | NFR-U3 (360px+) |

**Routes to wire (already in router):** Dashboard, Published Records, My Records, Review queue, AI Hub, Storage, Notifications, Admin users/audit.

---

## Phase 2 — Discover / dashboard (wireframe)

| Task | API (if any) | Notes |
|------|----------------|-------|
| Hero + RAG tagline | — | Static copy from mockup |
| Global search bar (UI only) | `GET /api/...` semantic search later | Submit → AI hub or search results page |
| Filter chips (CS, Patents, etc.) | — | Client-side filter stub |
| Spotlight research cards | `GET /api/records/?status=published` | Read full text → record detail; Summarize → AI hub |
| Recently indexed list | Same list, `ordering=-created_at` | |
| Trending topics sidebar | Static or tags from records | |

---

## Phase 3 — Records & IP disclosure (SRS Module 1 + 5)

| Page | Route | FR-ID |
|------|-------|-------|
| IP disclosure form (responsive) | `/records/add` | FR-M1-02 |
| Record detail | `/records/:id` | — |
| My records | `/records/mine` | — |
| Published browse | `/records` | — |
| Review pending / approved / declined | `/review/*` | FR-M5-01 |
| Evaluation | `/review/:id/evaluate` | FR-M5-01 |

**Form fields (FR-M1-02):** Title, Abstract (500 chars + counter), Inventor tags, Document type dropdown, auto submission date, PDF upload.

---

## Phase 4 — AI features (Modules 2–4)

| Feature | Route | FR-ID |
|---------|-------|-------|
| RAG chatbot UI | `/ai` | FR-M3-01 |
| Summarize from record detail | inline / modal | FR-M4-01 |
| Indexing progress toast | notifications | FR-M2-03 |

Show banner when AI unavailable (SRS constraint).

---

## Phase 5 — Admin & compliance

| Page | Route | FR-ID |
|------|-------|-------|
| User list | `/admin/users` | RBAC |
| Audit log | `/admin/audit` | NFR-S5 |
| Role requests page | TODO route | Signup role approval |
| DPA consent modal on first disclosure | — | FR-M6-02 |

---

## Phase 6 — Polish & NFRs

| Task | NFR |
|------|-----|
| 30 min idle logout + `SessionExpiryModal` in app | NFR-S2 |
| Load signup colleges/courses from API | — |
| Password reset flow | — |
| 403 page component | FR-M6-03 |
| Help / static manual | `/help` TODO |

---

## Design tokens (auth + app)

| Token | Value | Usage |
|-------|-------|--------|
| `brand` | `#6B0F12` | Headings, links, error text |
| `gold` | `#C59334` | Primary buttons, university label |
| `cream` | `#F5F0E8` | Auth left panel |
| Input fill | `#F3F3F3` | Auth inputs |
| Error surface | `bg-red-50` + `border-brand/30` | Auth alerts |

---

## Running locally

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/login`. Backend: `python manage.py runserver` on port 8000.

---

## References

- `IRIS Software Engineering_SRS.pdf` — FR-M1-01 (login), FR-M6-01/02/03, NFR-S2, NFR-U3
- `IRIS Software Engineering_SDD.pdf` — Module 1 login UI, Module 6 session/lockout
- Wireframes: login default, invalid credentials, session expired, account locked, Discover dashboard
- [Traceability matrix](../../docs/TRACEABILITY_MATRIX.md) — FR/NFR implementation status
- [Test plan](../../docs/TEST_PLAN.md) — role matrix and auth test cases (AUTH-*)
