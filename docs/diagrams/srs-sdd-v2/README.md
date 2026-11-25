# SRS v2 / SDD v2 figures (IR-1275)

The figures for `docs/SRS-v2.md` and `docs/SDD-v2.md`, which keep v1's structure: every SRS feature has a use-case diagram, activity diagrams and screens, and every SDD feature has screens, a class diagram, sequence diagrams and a schema. Section D figures (`../section-d/`) are reused where they fit (D-14, D-16, D-17, D-18, D-20, D-21).

| Folder / prefix | What | How it is made |
|---|---|---|
| `png/U-*` | Use-case diagram per SRS feature (41) | `tools/usecases.py` → `tools/gen_v2.py` |
| `png/A-*` | Activity diagrams per SRS feature (43) | `tools/activities.py` |
| `png/Q-*` | Sequence diagram per SDD feature (39) | `tools/sequences.py` |
| `png/C-*` | Class diagrams per SDD feature group (23) | `tools/classes.py` |
| `png/E-*` | Schema extracts per feature group (18) | `tools/schemas.py`, generated from the Django models |
| `png/V-03`…`V-06` | Record states; clearance-aware resubmission; sign-in and refresh; live hints | `src/V-*.mjs`, by hand |
| `screens/S-*` | Screens of a **local build** (42) | `tools/screenshots.mjs` |
| `v1-kept/` | The 11 v1 figures still accurate, unchanged | copied from v1's embedded images |

Every diagram is drawn by the Section D renderer, so the typeface, sizes and colours match Section D. Activity diagrams name who does each action on its first line, the UML alternative to v1's swimlane columns.

## Re-rendering the diagrams

Needs Python 3 and Node 18 or later.

```bash
python docs/diagrams/section-d/tools/extract_models.py      # models.json, for the schema extracts
python docs/diagrams/srs-sdd-v2/tools/gen_v2.py             # tools/*.py → src/*.json
cd docs/diagrams/section-d/tools && npm ci
DIAGRAM_SRC=../../srs-sdd-v2/src DIAGRAM_OUT=../../srs-sdd-v2/png node render.mjs
```

Name a prefix to redraw only some (`… node render.mjs U-3 Q-3.4`). The command fails if a diagram is wider than its page.

## Retaking the screens

They show a production build of this repository on a local machine, never the live site, and every caption says so. The record ids in the script are those of a freshly seeded database. Start the local stack with `seed_demo` data, then:

```bash
cd frontend && npm run preview:local        # serves http://localhost:4173
cd e2e && IRIS_DEMO_PASSWORD=… node ../docs/diagrams/srs-sdd-v2/tools/screenshots.mjs [S-3 …]
```

The password comes from the environment and never appears in a file or an image; sign-in screens are taken empty or with a deliberately wrong password. `IRIS_PREVIEW_URL` points at another port if 4173 is taken. `IRIS_SCREENSHOT_UPLOAD`, a path to a small placeholder PDF, makes S-3.5 upload it first so the screen shows a held file; each run adds one more upload.
