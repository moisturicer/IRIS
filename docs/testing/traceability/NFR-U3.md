# NFR-U3

[Back to the matrix](../TRACEABILITY.md)

**IR-97, 2026-11-02:** Moved from NOT STARTED. `reflow360` checks exist in three browser journey specs and IR-414 ran an automated pre-pass. PARTIAL, because no journey run record is committed and no person has checked every screen.

## NFR-U3

**Requirement:** Responsive at 360 px, no horizontal scroll

**Implementation:** 14 files build raw tables; **4 `overflow-x-auto` in the whole codebase**.

**IR-204** verified the login screen only. **IR-414's automated pre-pass** (2026-11-01, headless Chromium, frontend `a9df3d9f`) measured page-level overflow on 26 screens at 360, 768, 1280, 1745 and 200 %: one failure, *Download requests* at 360 (the *Refresh* button, **68 px**). The ITSO coordinator's two screens were not measured (account not seeded), and overflow inside panes that scroll on their own is not measured at all; see [`evidence/IR-414/README.md`](../evidence/IR-414/README.md)

**Evidence:** **Login screen only**, measured in Chrome against the running stack: `documentElement.scrollWidth === clientWidth` at both 360 px and 320 px, and at 200 % zoom in a 640 px viewport, with both fields and the submit action still present. Measured, not eyeballed

**Status:** **NOT STARTED** — one screen out of sixteen is not the requirement; the raw-table screens are untouched
