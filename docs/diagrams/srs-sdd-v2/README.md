# SRS v2 / SDD v2 diagrams (IR-1275)

The new figures for `docs/SRS-v2.md` and `docs/SDD-v2.md`. Each source is in `src/` and its PNG in `png/`. Everything else the two documents show is reused from [Section D](../section-d/README.md).

| # | Diagram | Page | From |
|---|---|---|---|
| V-1 | Deployment architecture (production) | landscape | D-16, corrected for ADR-067 (Unstructured) and ADR-074 (ClamAV) |
| V-2 | Manuscript processing: upload to searchable passages | portrait | D-17, corrected for ADR-067, ADR-074 and ADR-052's 2026-11-21 amendment |
| V-3 | Record lifecycle and review states | portrait | `core/enums.py`, `apps/reviews/tracker.py` |
| V-4 | Clearance-aware resubmission | portrait | `apps/reviews/new_version.py` |
| V-5 | Sign in, stay signed in, and the inactivity limit | portrait | `apps/accounts` (ADR-072) |
| V-6 | Live updates by server-sent hints | portrait | `apps/live` (ADR-073) |

They are drawn by the Section D renderer, so the typeface, sizes and colours match. Placement widths are the same as Section D's.

## Re-rendering

Needs Node 18 or later.

```bash
cd docs/diagrams/section-d/tools && npm ci
DIAGRAM_SRC=../../srs-sdd-v2/src DIAGRAM_OUT=../../srs-sdd-v2/png node render.mjs
```

Name diagrams to redraw only some (`… node render.mjs V-04`). The command fails if a diagram is wider than its page.
