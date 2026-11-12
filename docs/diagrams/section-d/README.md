# Section D diagrams

The 21 diagrams for Section D of the Final Evaluation (IR-1021). Each diagram's source is in `src/` and its PNG in `png/`.

Every diagram is drawn by one renderer ([`tools/render.mjs`](tools/render.mjs)) from one style sheet ([`tools/style.mjs`](tools/style.mjs)), so typeface, text sizes, colours, line weight, arrowheads and legends are the same in all of them. No diagram source sets a colour or a size.

The ERDs (D-8 to D-15) and the backend component diagram (D-19) are **generated from the code**, not drawn: `tools/` reads the Django models, the AI runtime's SQL migrations and the import graph and writes `src/*.json`. The other diagrams are written by hand (`src/*.mjs`) from the code paths named in each caption.

| # | Diagram | Page | Source |
|---|---|---|---|
| D-1 | Use case overview: actors and subsystems | portrait | hand, from `frontend/src/lib/access.ts`, `core/permissions.py` |
| D-2 | Use cases: accounts and access | portrait | hand, from `apps/accounts` |
| D-3 | Use cases: submission and versions | portrait | hand, from `RecordViewSet` actions, `apps/documents` |
| D-4 | Use cases: review workflow | portrait | hand, from `apps/reviews`, ADR-032, ADR-047, ADR-052 |
| D-5 | Use cases: discovery and reading | portrait | hand, from frontend routes and `apps/records`, `apps/library` |
| D-6 | Use cases: Ask IRIS and Paper Chat | portrait | hand, from `RuntimeReader`, `apps/ai` grants, `ai/` |
| D-7 | Use cases: administration | portrait | hand, from the RDCO and Administration screens |
| D-8 | ERD overview: domains and links | portrait | generated |
| D-9 | ERD: accounts, roles and consent | landscape | generated |
| D-10 | ERD: records, versions and publication | landscape | generated |
| D-11 | ERD: review workflow | landscape | generated |
| D-12 | ERD: documents, extraction and manuscript processing | portrait | generated |
| D-13 | ERD: AI indexing, admission and conversations (Django) | landscape | generated |
| D-14 | ERD: AI runtime schema (`iris_ai`) | landscape | generated from `ai/runs/migrations/*.sql` |
| D-15 | ERD: notifications, audit, library, opportunities | portrait | generated |
| D-16 | Deployment architecture | landscape | hand, from `docker-compose.prod.yml`, `deploy/` |
| D-17 | Manuscript processing flow | portrait | hand, from `apps/documents/tasks.py`, `apps/ai/tasks.py` |
| D-18 | Ask IRIS request flow | portrait | hand, from `frontend/runtime-edge.conf`, `ai/api/runs.py`, `ai/runs` |
| D-19 | Backend components and dependencies | portrait | generated from imports |
| D-20 | Workflow core classes | portrait | hand, from the models and `apps/reviews` service functions |
| D-21 | AI runtime classes: ports and adapters | landscape | hand, from `ai/` |

## Placing them in the document

Every PNG is one of two widths, so text is the same size in every figure when each is placed at full text width:

| Page | PNG width | Place at | Smallest text in print |
|---|---|---|---|
| portrait | 1980 px | 6.5 in (the text block of an A4 or Letter portrait page) | about 6 pt |
| landscape | 2860 px | 9.4 in (a landscape page) | about 6 pt |

Both come out at about 300 dpi. Do not scale a portrait figure to a different width from the others, or its text stops matching. D-13 is the tallest landscape figure (28 tables); on a landscape page it is limited by height, so its text prints a little smaller than the rest.

## Re-rendering

Needs Python 3 and Node 18 or later. No Java, Graphviz or PlantUML.

```bash
bash docs/diagrams/section-d/render.sh
```

It regenerates the ERD and component sources from the current code, then renders every PNG. Re-run it after a model, migration or app-dependency change so the diagrams stay true. To redraw only some, name them: `bash docs/diagrams/section-d/render.sh D-04 D-11`. The command fails if a diagram no longer fits its page width.

The typeface (Inter) is installed with the renderer's dependencies, so the result does not depend on the fonts on the machine.

## How they are laid out

| Diagrams | Layout |
|---|---|
| Use cases (D-1 to D-7) | Actors left and right of one column of use cases ([`tools/usecase.mjs`](tools/usecase.mjs)). Actor links run in lanes outside the system boundary, dependencies between use cases in lanes inside it. |
| ERDs, deployment, components, classes (D-8 to D-16, D-19 to D-21) | Nodes in columns, lines routed at right angles through the gutters between them ([`tools/grid.mjs`](tools/grid.mjs)). No line passes under a box. Unlabelled lines to the same box share a trunk, joined with a dot. |
| Activity (D-17) | Top to bottom (ELK layered layout). Each action names who does it on its first line. |
| Sequence (D-18) | One lifeline per participant, messages in time order. |

## What the ERDs show

All primary and foreign keys, and up to four other fields per entity, with "… n more fields" for the rest. Each foreign-key line leaves from its own attribute row. A line is drawn for every foreign key between two entities on the same figure; a key to an entity on another figure is named in its attribute row with that figure's number, for example `record  FK → Record (D-10)`. A muted table is one kept read only since IR-957.
