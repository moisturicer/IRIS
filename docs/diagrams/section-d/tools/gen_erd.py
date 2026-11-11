"""Generate the Section D ERDs (D-8 to D-15) from models.json and iris_ai.json.

Run extract_models.py and extract_iris_ai.py first. Every entity, primary key,
foreign key and cardinality comes from those files; nothing is typed by hand
except the grouping of apps into diagrams and the captions.

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

DIAGRAMS = [
    ("D-09-erd-accounts", "D-9  Accounts, roles and consent", ["accounts"], None),
    ("D-10-erd-records", "D-10  Records, versions and publication", ["records"], None),
    ("D-11-erd-reviews", "D-11  Review workflow: seats, clearances, threads and resubmission", ["reviews"], None),
    ("D-12-erd-documents", "D-12  Documents, extraction and manuscript processing", ["documents", "publication"], None),
    ("D-13-erd-ai-django", "D-13  AI indexing, provider admission and conversations (Django side)", ["ai"], None),
    ("D-15-erd-supporting", "D-15  Notifications, audit, library and opportunities", ["notifications", "audit", "library", "opportunities"], None),
]

APP_LABEL = {
    "accounts": "accounts", "records": "records", "reviews": "reviews", "documents": "documents",
    "publication": "publication", "ai": "ai", "notifications": "notifications", "audit": "audit",
    "library": "library", "opportunities": "opportunities",
}


def key(m):
    return f"{m['app']}.{m['name']}"


INDEX = {key(m): m for m in MODELS}


def alias(ref):
    return ref.replace(".", "_")


def attr_lines(m):
    lines = []
    has_pk = any(f.get("pk") for f in m["fields"])
    if not has_pk:
        lines.append("<b>id</b> : PK")
    plain = []
    for f in m["fields"]:
        if f.get("pk"):
            lines.append(f"<b>{f['name']}</b> : PK")
        elif "relation" in f:
            target = f["ref"].split(".")[-1]
            tag = {"fk": "FK", "o2o": "FK unique", "m2m": "M2M"}[f["relation"]]
            lines.append(f"{f['name']} : {tag} → {target}")
        else:
            plain.append(f)
    for f in plain[:MAX_ATTRS]:
        lines.append(f"{f['name']} : {f['type'].replace('Field', '')}")
    if len(plain) > MAX_ATTRS:
        lines.append(f"<i>… {len(plain) - MAX_ATTRS} more fields</i>")
    return lines


def edge(src, f):
    tgt = alias(f["ref"])
    rel = f["relation"]
    if rel == "fk":
        arrow = "}o--o|" if f.get("null") else "}o--||"
    elif rel == "o2o":
        arrow = "|o--o|" if f.get("null") else "|o--||"
    else:
        arrow = "}o--o{"
    return f"{src} {arrow} {tgt}"


def header(title, caption):
    return [
        "@startuml",
        "!include ../iris-style.puml",
        "hide methods",
        "skinparam LineType ortho",
        f"title {title}",
        f"caption {caption}",
    ]


def legend_erd(extra=()):
    return [
        "legend right",
        "  <b>Notation</b> (crow's foot)",
        "  three-pronged end: many · bar: exactly one · circle: zero allowed",
        "  PK primary key · FK foreign key · M2M many-to-many",
        "  grey box: entity drawn in full on another diagram",
        *["  " + e for e in extra],
        "endlegend",
        "@enduml",
    ]


def domain_erd(name, title, apps):
    members = [m for m in MODELS if m["app"] in apps]
    names = {key(m) for m in members}
    out = header(title, "Generated from backend/apps/*/models*.py on main (IR-1021). All keys shown, up to four other fields per entity." + ("" if "accounts" in apps else " Links to User appear as FK attributes only."))
    refs = set()
    groups = collections.defaultdict(list)
    for m in members:
        groups[m["app"]].append(m)
    for app, ms in groups.items():
        out.append(f'package "{APP_LABEL[app]}" {{')
        for m in ms:
            stereo = " <<retained>>" if m["name"] in RETAINED else ""
            out.append(f'  class "{m["name"]}" as {alias(key(m))}{stereo} {{')
            for line in attr_lines(m):
                out.append(f"    {line}")
            out.append("  }")
        out.append("}")
    edges = []
    for m in members:
        for f in m["fields"]:
            if "relation" not in f:
                continue
            if f["ref"] == "accounts.User" and "accounts" not in apps:
                continue  # listed in the attributes; edges to User omitted for legibility
            if f["ref"] not in names:
                refs.add(f["ref"])
            edges.append(edge(alias(key(m)), f))
    for r in sorted(refs):
        app, nm = r.split(".")
        out.append(f'class "{nm}\\n<size:9>({app})</size>" as {alias(r)} <<ref>>')
    out += sorted(set(edges))
    extra = ["muted box: table kept, read only since IR-957"] if any(m["name"] in RETAINED for m in members) else []
    out += legend_erd(extra)
    (SRC / f"{name}.puml").write_text("\n".join(out) + "\n")


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
    out = header("D-8  Data model overview: domains and the links between them",
                 "Generated from the Django models on main (IR-1021). Edge labels: number of foreign keys from one app's tables to the other's.")
    out.append("skinparam LineType polyline")
    detail = {"accounts": "D-9", "records": "D-10", "reviews": "D-11", "documents": "D-12",
              "publication": "D-12", "ai": "D-13", "notifications": "D-15", "audit": "D-15",
              "library": "D-15", "opportunities": "D-15"}
    for app, ns in sorted(by_app.items()):
        shown = ", ".join(sorted(ns)[:8]) + (" …" if len(ns) > 8 else "")
        out.append(f'rectangle "<b>{app}</b> ({len(ns)} table{"s" if len(ns) != 1 else ""}, {detail[app]})\\n<size:10>{shown}</size>" as {app}')
    out.append('rectangle "<b>iris_ai schema</b> (AI runtime, %d tables, D-14)\\n<size:10>conversation, ask_run, turn, citation, …</size>" as iris_ai <<ai>>' % len(IRIS_AI))
    for (a, b), n in sorted(links.items()):
        out.append(f"{a} --> {b} : {n}")
    out.append('iris_ai ..> accounts : reader_id\\n(no DB constraint)')
    out.append('iris_ai ..> records : record_id\\n(no DB constraint)')
    out += [
        "legend right",
        f"  {len(MODELS)} Django tables in {len(by_app)} apps, plus {len(IRIS_AI)} tables in the iris_ai schema",
        "  solid arrow: foreign keys (count) · dashed: id reference without a DB constraint",
        "endlegend",
        "@enduml",
    ]
    (SRC / "D-08-erd-overview.puml").write_text("\n".join(out) + "\n")


def iris_ai():
    out = header("D-14  AI runtime schema (iris_ai): runs, conversations and indexing",
                 "Generated from ai/runs/migrations/*.sql on main (IR-1021). Owned by the AI runtime; Django never writes it (ADR-049).")
    out.append('package "iris_ai" {')
    for t in IRIS_AI:
        out.append(f'  class "{t["name"]}" as ia_{t["name"]} <<ai>> {{')
        plain = []
        for c in t["columns"]:
            if c["pk"] and c["ref"]:
                out.append(f"    <b>{c['name']}</b> : PK, FK → {c['ref']}")
            elif c["pk"]:
                out.append(f"    <b>{c['name']}</b> : PK")
            elif c["ref"]:
                out.append(f"    {c['name']} : FK → {c['ref']}")
            elif c["name"] in ("reader_id", "record_id", "scope_record_id", "space_id", "chunk_set_id", "chunk_id"):
                out.append(f"    {c['name']} : Django id, no DB constraint")
            else:
                plain.append(c)
        for c in plain[:MAX_ATTRS]:
            out.append(f"    {c['name']} : {c['type']}")
        if len(plain) > MAX_ATTRS:
            out.append(f"    <i>… {len(plain) - MAX_ATTRS} more columns</i>")
        out.append("  }")
    out.append("}")
    out.append('class "User\\n<size:9>(accounts, Django)</size>" as dj_user <<ref>>')
    out.append('class "Record\\n<size:9>(records, Django)</size>" as dj_record <<ref>>')
    for t in IRIS_AI:
        for c in t["columns"]:
            if c["ref"]:
                arrow = "}o--o|" if c["null"] else "}o--||"
                if c["pk"]:
                    arrow = "|o--||"
                out.append(f"ia_{t['name']} {arrow} ia_{c['ref']}")
    for t in IRIS_AI:
        names = {c["name"] for c in t["columns"]}
        if "reader_id" in names:
            out.append(f"ia_{t['name']} ..> dj_user : reader_id")
        if "record_id" in names or "scope_record_id" in names:
            out.append(f"ia_{t['name']} ..> dj_record")
    out += legend_erd(["dashed arrow: Django id held without a DB constraint"])
    (SRC / "D-14-erd-iris-ai.puml").write_text("\n".join(out) + "\n")


def main():
    SRC.mkdir(exist_ok=True)
    for name, title, apps, _ in DIAGRAMS:
        domain_erd(name, title, apps)
    overview()
    iris_ai()
    print("ERD sources written to", SRC)


if __name__ == "__main__":
    main()
