# Section D diagrams

The diagrams for Section D of the Final Evaluation (IR-1021, redrawn for the printed report in IR-1022). Each diagram's PlantUML source is in `src/` and its PNG in `png/`. Every diagram includes [`iris-style.puml`](iris-style.puml), so fonts, colours, line styles and spacing match across all of them.

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
| D-10a | ERD: records, versions and authorship | generated |
| D-10b | ERD: publication, requests and discovery | generated |
| D-11 | ERD: review workflow | generated |
| D-12 | ERD: documents, extraction and manuscript processing | generated |
| D-13a | ERD: AI indexing and provider admission (Django) | generated |
| D-13b | ERD: earlier conversations and Ask IRIS runs (Django) | generated |
| D-14a | ERD: AI runtime schema (`iris_ai`), conversations and runs | generated from `ai/runs/migrations/*.sql` |
| D-14b | ERD: AI runtime schema (`iris_ai`), manuscripts and indexing | generated from `ai/runs/migrations/*.sql` |
| D-15 | ERD: notifications, audit, library, opportunities | generated |
| D-16 | Deployment architecture | hand, from `docker-compose.prod.yml`, `deploy/` |
| D-17 | Manuscript processing flow | hand, from `apps/documents/tasks.py`, `apps/ai/tasks.py` |
| D-18 | Ask IRIS request flow | hand, from `frontend/runtime-edge.conf`, `ai/api/runs.py`, `ai/runs` |
| D-19 | Backend components and dependencies | generated from imports |
| D-20 | Workflow core classes | hand, from the models and `apps/reviews` service functions |
| D-21 | AI runtime classes: ports and adapters | hand, from `ai/` |

## Sized for the printed report (IR-1022)

- **One scale.** Every PNG is drawn at 140 dpi with 11-pt text and placed on a canvas 1,500 px wide (`tools/pad_png.py`). Inserted at full page width, every figure prints at the same scale, about 6.7-pt text on a 6.5-inch page, and every one fits on a page. A narrow diagram keeps white margins rather than being enlarged.
- **Right-angle connectors** (`LineType ortho`) on every diagram. Where a label would drift away from its line, its fact is written in the box it belongs to instead.
- **Keys-only ERDs.** Each table shows its primary key and every foreign key; its other fields are counted ("+ 5 more fields"). The full field lists are in `tools/models.json`, `tools/iris_ai.json` and the model source.
- **Three ERDs split in two** (D-10, D-13, D-14), because each held 20 or more tables and could not be read at page width. A table drawn on the other half appears as a grey box.
- **One column for D-17.** The manuscript flow is one vertical sequence; each step names, in bold, the service that runs it (it was seven swimlanes).
- **Groups in D-16.** An arrow to "Celery workers" or "AI runtime" means every service in the group; each such arrow replaces the identical arrows from each member.
- Notes and notation are in each diagram's caption, not in a legend box.

The redraw changed layout and styling only. Compared with PR #692, the ERDs have the same 125 tables and 170 relationships, D-19 the same dependencies, and every other diagram the same elements and relationships, D-16's grouped arrows aside.

## Re-rendering

Needs Java, Graphviz, a PlantUML jar (tested with 1.2024.7) and Pillow:

```bash
PLANTUML_JAR=/path/to/plantuml.jar bash docs/diagrams/section-d/render.sh
# Windows (Git Bash): PYTHON=python PLANTUML_JAR=... GRAPHVIZ_DOT=/path/to/dot.exe bash docs/diagrams/section-d/render.sh
```

It regenerates the ERD and component sources from the current code, renders every PNG and pads it to the shared canvas. Re-run it after a model, migration or app-dependency change so the diagrams stay true. A diagram wider than the canvas stops the run and names itself.

## What the ERDs show

Every primary and foreign key, with the remaining fields counted. Outside the accounts diagram, links to `User` appear as FK attributes only, to keep the lines readable. A grey box is an entity drawn in full on another diagram; a muted box is a table kept read only since IR-957.
