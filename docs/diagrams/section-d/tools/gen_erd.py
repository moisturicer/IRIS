"""Generate the Section D ERDs (D-8 to D-15) from models.json and iris_ai.json.

Run extract_models.py and extract_iris_ai.py first. Every entity, primary key,
foreign key and cardinality comes from those files; nothing is typed by hand
except the grouping of apps into diagrams, the captions and the layout hints.
Writes one diagram description per ERD into src/*.json, which render.mjs draws.

    python docs/diagrams/section-d/tools/gen_erd.py
"""
import collections
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "src"
MODELS = json.loads((HERE / "models.json").read_text())
IRIS_AI = json.loads((HERE / "iris_ai.json").read_text())

MAX_ATTRS = 4
# Read only since IR-957: kept for data export, deletion and evaluation replay.
RETAINED = {"ResearchRun", "ResearchStep", "ScreeningJudgment", "ShadowEvidenceDecision",
            "ShadowEvidenceTally", "ConversationState", "ChatSubmission"}

# file name, title, apps, page format, optional layout hints
DIAGRAMS = [
    ("D-09-erd-accounts", "D-9  Accounts, roles and consent", ["accounts"], "landscape"),
    ("D-10-erd-records", "D-10  Records, versions and publication", ["records"], "landscape"),
    ("D-11-erd-reviews", "D-11  Review workflow: seats, clearances, threads and resubmission", ["reviews"], "landscape"),
    ("D-12-erd-documents", "D-12  Documents, extraction and manuscript processing", ["documents", "publication"], "portrait"),
    ("D-13-erd-ai-django", "D-13  AI indexing, provider admission and conversations (Django side)", ["ai"], "landscape", {"gutter": 36}),
    ("D-15-erd-supporting", "D-15  Notifications, audit, library and opportunities", ["notifications", "audit", "library", "opportunities"], "portrait"),
]
# Which figure draws each app in full.
FIGURE = {"accounts": "D-9", "records": "D-10", "reviews": "D-11", "documents": "D-12",
          "publication": "D-12", "ai": "D-13", "notifications": "D-15", "audit": "D-15",
          "library": "D-15", "opportunities": "D-15"}

LEGEND = [
    {"line": "many", "text": "many (zero or more) to exactly one"},
    "circle at an end: zero allowed",
    "bold: primary key",
    "FK → Name (D-n): the entity is drawn on figure D-n",
]


def key(m):
    return f"{m['app']}.{m['name']}"


def alias(ref):
    return ref.replace(".", "_")


def rows(m, names):
    pk, fk, plain = [], [], []
    if not any(f.get("pk") for f in m["fields"]):
        pk.append({"k": "id", "v": "PK", "pk": True})
    for f in m["fields"]:
        if f.get("pk"):
            pk.append({"k": f["name"], "v": "PK", "pk": True})
        elif "relation" in f:
            app, target = f["ref"].split(".")
            tag = {"fk": "FK", "o2o": "FK unique", "m2m": "M2M"}[f["relation"]]
            where = "" if f["ref"] in names else f" ({FIGURE[app]})"
            fk.append({"k": f["name"], "v": f"{tag} → {target}{where}"})
        else:
            plain.append(f)
    out = pk + fk + [{"k": f["name"], "v": f["type"].replace("Field", "")} for f in plain[:MAX_ATTRS]]
    if len(plain) > MAX_ATTRS:
        out.append(f"… {len(plain) - MAX_ATTRS} more fields")
    return out


def ends(relation, null):
    """Crow's foot at the holder of the key (tail) and at the entity it points to (head)."""
    head = "zero-one" if null else "one"
    if relation == "fk":
        return "zero-many", head
    if relation == "o2o":
        return "zero-one", head
    return "zero-many", "zero-many"


def domain_erd(name, title, apps, fmt, layout=None):
    members = [m for m in MODELS if m["app"] in apps]
    names = {key(m) for m in members}
    by_app = collections.defaultdict(list)
    for m in members:
        tone = "muted" if m["name"] in RETAINED else "core"
        by_app[m["app"]].append({"id": alias(key(m)), "shape": "table", "label": m["name"],
                                 "tone": tone, "sections": [rows(m, names)]})
    nodes = []
    for app, tables in by_app.items():
        for t in tables:
            if len(by_app) > 1:
                t["stereotype"] = app  # which Django app owns the table
            nodes.append(t)
    edges = []
    for m in members:
        for f in m["fields"]:
            if "relation" not in f or f["ref"] not in names:
                continue  # an entity on another figure is named in the attribute row instead
            tail, head = ends(f["relation"], f.get("null"))
            edges.append({"from": alias(key(m)), "to": alias(f["ref"]), "field": f["name"], "tail": tail, "head": head})
    legend = list(LEGEND)
    if any(m["name"] in RETAINED for m in members):
        legend.insert(3, {"tone": "muted", "text": "table kept, read only since IR-957"})
    spec = {
        "title": title,
        "caption": "Generated from backend/apps/*/models*.py on main (IR-1021). All keys shown, up to four other "
                   "fields per entity. A line is drawn for every foreign key between two entities on this figure; "
                   "a key to an entity on another figure is named in its attribute row.",
        "kind": "erd", "format": fmt, **(layout or {}),
        "nodes": nodes, "edges": edges, "legend": legend,
    }
    (SRC / f"{name}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def overview():
    by_app = collections.defaultdict(list)
    for m in MODELS:
        by_app[m["app"]].append(m["name"])
    links = collections.Counter()
    for m in MODELS:
        for f in m["fields"]:
            if "relation" in f:
                ta = f["ref"].split(".")[0]
                if ta != m["app"]:
                    links[(m["app"], ta)] += 1
    nodes = []
    for app, ns in sorted(by_app.items()):
        shown = ", ".join(sorted(ns)[:4]) + (" …" if len(ns) > 4 else "")
        nodes.append({"id": app, "shape": "box", "wrap": 132,
                      "label": f"{app}  ({len(ns)} table{'s' if len(ns) != 1 else ''}, {FIGURE[app]})", "sub": shown})
    nodes.append({"id": "iris_ai", "shape": "box", "tone": "ai", "wrap": 132,
                  "label": f"iris_ai schema  ({len(IRIS_AI)} tables, D-14)",
                  "sub": "AI runtime: conversation, ask_run, turn, citation, …"})
    edges = [{"from": a, "to": b, "label": str(n)} for (a, b), n in sorted(links.items())]
    edges.append({"from": "iris_ai", "to": "accounts", "label": "reader_id", "dash": True})
    edges.append({"from": "iris_ai", "to": "records", "label": "record_id", "dash": True})
    spec = {
        "title": "D-8  Data model overview: domains and the links between them",
        "caption": f"Generated from the Django models on main (IR-1021). {len(MODELS)} Django tables in {len(by_app)} apps, "
                   f"plus {len(IRIS_AI)} tables in the iris_ai schema.",
        "kind": "columns", "format": "portrait", "gutter": 96, "vgap": 30, "columnCount": 3, "level": 8,
        "nodes": nodes, "edges": edges,
        "legend": [{"line": "arrow", "text": "foreign keys from one app's tables to the other's (count)"},
                   {"line": "dash arrow", "text": "id held without a database constraint"},
                   {"tone": "core", "text": "Django app"}, {"tone": "ai", "text": "AI runtime schema"}],
    }
    (SRC / "D-08-erd-overview.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


DJANGO_IDS = ("reader_id", "record_id", "scope_record_id", "space_id", "chunk_set_id", "chunk_id")


def iris_ai():
    nodes, edges = [], []
    for t in IRIS_AI:
        pk, fk, plain = [], [], []
        for c in t["columns"]:
            if c["pk"] and c["ref"]:
                pk.append({"k": c["name"], "v": f"PK, FK → {c['ref']}", "pk": True})
            elif c["pk"]:
                pk.append({"k": c["name"], "v": "PK", "pk": True})
            elif c["ref"]:
                fk.append({"k": c["name"], "v": f"FK → {c['ref']}"})
            elif c["name"] in DJANGO_IDS:
                fk.append({"k": c["name"], "v": "Django id, no constraint"})
            else:
                plain.append(c)
        body = pk + fk + [{"k": c["name"], "v": c["type"]} for c in plain[:MAX_ATTRS]]
        if len(plain) > MAX_ATTRS:
            body.append(f"… {len(plain) - MAX_ATTRS} more columns")
        nodes.append({"id": f"ia_{t['name']}", "shape": "table", "label": t["name"], "tone": "ai", "sections": [body]})
        for c in t["columns"]:
            if c["ref"]:
                tail = "zero-one" if c["pk"] else "zero-many"
                head = "one" if c["pk"] or not c["null"] else "zero-one"
                edges.append({"from": f"ia_{t['name']}", "to": f"ia_{c['ref']}", "field": c["name"], "tail": tail, "head": head})
    readers = sorted(t["name"] for t in IRIS_AI if any(c["name"] == "reader_id" for c in t["columns"]))
    records = sorted(t["name"] for t in IRIS_AI if any(c["name"] in ("record_id", "scope_record_id") for c in t["columns"]))
    spec = {
        "title": "D-14  AI runtime schema (iris_ai): runs, conversations and indexing",
        "caption": "Generated from ai/runs/migrations/*.sql on main (IR-1021). Owned by the AI runtime; Django never writes it "
                   "(ADR-049). Ids of Django rows are held without a database constraint: reader_id names a User (D-9) in "
                   + ", ".join(readers) + "; record_id or scope_record_id names a Record (D-10) in " + ", ".join(records) + ".",
        "kind": "erd", "format": "landscape",
        "nodes": nodes, "edges": edges,
        "legend": [LEGEND[0], LEGEND[1], LEGEND[2], {"tone": "ai", "text": "table in the iris_ai schema"}],
    }
    (SRC / "D-14-erd-iris-ai.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    SRC.mkdir(exist_ok=True)
    for args in DIAGRAMS:
        domain_erd(*args)
    overview()
    iris_ai()
    print("ERD descriptions written to", SRC)


if __name__ == "__main__":
    main()
