# Section D diagrams

The 21 diagrams for Section D of the Final Evaluation (IR-1021). Each diagram's PlantUML source is in `src/` and its PNG in `png/`. Every diagram includes [`iris-style.puml`](iris-style.puml), so fonts, colours, line styles and legends match across all of them.

The ERDs (D-8 to D-15) and the backend component diagram (D-19) are **generated from the code**, not drawn: `tools/` reads the Django models, the AI runtime's SQL migrations and the import graph. The other diagrams are written by hand from the code paths named in each caption.

| # | Diagram | Source |
|---|---|---|
| D-1 | Use case overview: actors and subsystems | hand, from `frontend/src/lib/access.ts`, `core/permissions.py` |
| D-2 | Use cases: accounts and access | hand, from `apps/accounts` |
| D-3 | Use cases: submission and versions | hand, from `RecordViewSet` actions, `apps/documents` |
| D-4 | Use cases: review workflow | hand, from `apps/reviews`, ADR-032, ADR-047, ADR-052 |
| D-5 | Use cases: discovery and reading | hand, from frontend routes and `apps/records`, `apps/library` |
| D-6 | Use cases: Ask IRIS and Paper Chat | hand, from `RuntimeReader`, `apps/ai` grants, `ai/` |
| D-7 | Use cases: administration | hand, from the RDCO and Administration screens |
| D-8 | ERD overview: domains and links | generated |
| D-9 | ERD: accounts, roles and consent | generated |
| D-10 | ERD: records, versions and publication | generated |
| D-11 | ERD: review workflow | generated |
| D-12 | ERD: documents, extraction and manuscript processing | generated |
| D-13 | ERD: AI indexing, admission and conversations (Django) | generated |
| D-14 | ERD: AI runtime schema (`iris_ai`) | generated from `ai/runs/migrations/*.sql` |
| D-15 | ERD: notifications, audit, library, opportunities | generated |
| D-16 | Deployment architecture | hand, from `docker-compose.prod.yml`, `deploy/` |
| D-17 | Manuscript processing flow | hand, from `apps/documents/tasks.py`, `apps/ai/tasks.py` |
| D-18 | Ask IRIS request flow | hand, from `frontend/runtime-edge.conf`, `ai/api/runs.py`, `ai/runs` |
| D-19 | Backend components and dependencies | generated from imports |
| D-20 | Workflow core classes | hand, from the models and `apps/reviews` service functions |
| D-21 | AI runtime classes: ports and adapters | hand, from `ai/` |

## Re-rendering

Needs Java, Graphviz and a PlantUML jar (tested with 1.2024.7):

```bash
PLANTUML_JAR=/path/to/plantuml.jar bash docs/diagrams/section-d/render.sh
```

It regenerates the ERD and component sources from the current code, then renders every PNG. Re-run it after a model, migration or app-dependency change so the diagrams stay true.

## What the ERDs show

All primary and foreign keys, and up to four other fields per entity, with "… n more fields" for the rest. Outside the accounts diagram, links to `User` appear as FK attributes only, to keep the lines readable. A grey box is an entity drawn in full on another diagram; a muted box is a table kept read only since IR-957.
