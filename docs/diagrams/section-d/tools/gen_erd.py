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

# Keys only (IR-1022): every primary and foreign key, the other fields counted.
# The full field lists are in models.json and backend/apps/*/models*.py.
MAX_ATTRS = 0
NL = chr(10)
PUML_NL = chr(92) + "n"  # PlantUML's line break inside a label
# Read only since IR-957: kept for data export, deletion and evaluation replay.
RETAINED = {"ResearchRun", "ResearchStep", "ScreeningJudgment", "ShadowEvidenceDecision",
            "ShadowEvidenceTally", "ConversationState", "ChatSubmission"}

# The fourth item names the tables to draw; None draws every table of the apps.
# IR-1022 splits the three largest ERDs in two, so each prints at 7 pt or more.
RECORDS_CORE = {"Record", "RecordVersion", "RecordVersionDocument", "RecordOwner", "Author",
                "AuthorRole", "Publication", "PublicationLevel", "Conference", "ConferenceLevel",
                "ResearchLink", "ReviewText", "ReviewTextSection", "RecordType", "Classification",
                "PSCEDClassification"}
AI_INDEXING = {"ChunkSet", "DocumentChunk", "ChunkEmbedding", "EmbeddingSpace",
               "EmbeddingSpaceActivation", "RecordEmbedding", "RecordSpaceEmbedding",
               "IngestionJob", "EmbeddingJob", "DocumentMetadata", "PaperBrief", "RecordOverview",
               "ProviderCampaign", "ProviderReservation", "TurnEmbedding"}
RECORDS_ALL = {m["name"] for m in MODELS if m["app"] == "records"}
AI_ALL = {m["name"] for m in MODELS if m["app"] == "ai"}

DIAGRAMS = [
    ("D-09-erd-accounts", "D-9  Accounts, roles and consent", ["accounts"], None),
    ("D-10a-erd-records", "D-10a  Records, versions and authorship", ["records"], RECORDS_CORE),
    ("D-10b-erd-records", "D-10b  Publication, requests and discovery", ["records"], RECORDS_ALL - RECORDS_CORE),
    ("D-11-erd-reviews", "D-11  Review workflow: seats, clearances, threads and resubmission", ["reviews"], None),
    ("D-12-erd-documents", "D-12  Documents, extraction and manuscript processing", ["documents", "publication"], None),
    ("D-13a-erd-ai-indexing", "D-13a  AI indexing and provider admission (Django side)", ["ai"], AI_INDEXING),
    ("D-13b-erd-ai-conversations", "D-13b  Earlier conversations and Ask IRIS runs (Django side)", ["ai"], AI_ALL - AI_INDEXING),
    ("D-15-erd-supporting", "D-15  Notifications, audit, library and opportunities", ["notifications", "audit", "library", "opportunities"], None),
]

IRIS_AI_RUNS = {"conversation", "ask_run", "turn", "citation", "run_event", "attempt_accounting",
                "research_handle", "run_checkpoint", "conversation_handoff"}
IRIS_AI_SPLIT = [
    ("D-14a-erd-iris-ai-runs", "D-14a  AI runtime schema (iris_ai): conversations and runs", IRIS_AI_RUNS),
    ("D-14b-erd-iris-ai-indexing", "D-14b  AI runtime schema (iris_ai): manuscripts and indexing",
     {t["name"] for t in IRIS_AI} - IRIS_AI_RUNS),
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
        lines.append(f"<i>+ {len(plain) - MAX_ATTRS} more fields</i>")
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
        "left to right direction",
        "skinparam nodesep 6",
        "skinparam ranksep 30",
        f"title {title}",
        f"caption {caption}\\n{NOTATION}",
    ]


NOTATION = ("Crow's foot: three prongs many, bar exactly one, circle zero allowed. PK primary key, FK foreign key."
            + chr(92) + "nM2M many-to-many. Grey box: drawn in full on another diagram.")


def add_to_caption(out, text):
    """Append text to the diagram's caption line, wherever header() put it."""
    i = next(n for n, line in enumerate(out) if line.startswith("caption "))
    out[i] += text


def legend_erd(extra=()):
    # IR-1022: the notation moved into the caption, which costs one line, not a box.
    return ["@enduml"]


def domain_erd(name, title, apps, only=None):
    members = [m for m in MODELS if m["app"] in apps and (only is None or m["name"] in only)]
    names = {key(m) for m in members}
    out = header(title, "Generated from backend/apps/*/models*.py on main (IR-1021). Every key shown; other fields counted." + ("" if "accounts" in apps else " Links to User appear as FK attributes only."))
    refs = set()
    groups = collections.defaultdict(list)
    for m in members:
        groups[m["app"]].append(m)
    framed = len(groups) > 1  # IR-1022: a frame only when it separates apps
    for app, ms in groups.items():
        if framed:
            out.append(f'package "{APP_LABEL[app]}" {{')
        for m in ms:
            stereo = " <<retained>>" if m["name"] in RETAINED else ""
            out.append(f'  class "{m["name"]}" as {alias(key(m))}{stereo} {{')
            for line in attr_lines(m):
                out.append(f"    {line}")
            out.append("  }")
        if framed:
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
    if any(m["name"] in RETAINED for m in members):
        add_to_caption(out, PUML_NL + "Muted box: table kept, read only since IR-957.")
    out += legend_erd()
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
    i = next(n for n, line in enumerate(out) if line.startswith("caption "))
    out[i] = out[i].split(PUML_NL)[0]  # drop the crow's-foot line: the overview has none
    out = [l for l in out if l != "left to right direction"]
    out.append("top to bottom direction")
    detail = {"accounts": "D-9", "records": "D-10a, D-10b", "reviews": "D-11", "documents": "D-12",
              "publication": "D-12", "ai": "D-13a, D-13b", "notifications": "D-15", "audit": "D-15",
              "library": "D-15", "opportunities": "D-15"}
    for app, ns in sorted(by_app.items()):
        # IR-1022: four names, then a count, so every box stays narrow
        names = sorted(ns)[:4]
        rows = [", ".join(names[i:i + 2]) for i in range(0, len(names), 2)]
        if len(ns) > 4:
            rows[-1] += f" + {len(ns) - 4} more"
        # a size tag can't span a line break, so each row gets its own
        shown = PUML_NL.join(f"<size:10>{r}</size>" for r in rows)
        out.append(f'rectangle "<b>{app}</b> ({len(ns)} table{"s" if len(ns) != 1 else ""}, {detail[app]})\\n{shown}" as {app}')
    out.append('rectangle "<b>iris_ai schema</b> (AI runtime, %d tables, D-14a, D-14b)\\n<size:10>conversation, ask_run, turn, citation, …</size>" as iris_ai <<ai>>' % len(IRIS_AI))
    for (a, b), n in sorted(links.items()):
        out.append(f"{a} --> {b} : {n}")
    out.append('iris_ai ..> accounts : reader_id\\n(no DB constraint)')
    # IR-1022, layout only: the two AI apps on the first row, the five small apps on
    # the second, so no row is wider than the page. Hidden links draw nothing.
    for small in ("audit", "library", "publication"):
        out.append(f"ai -[hidden]down- {small}")
    for small in ("notifications", "opportunities"):
        out.append(f"iris_ai -[hidden]down- {small}")
    out.append('iris_ai ..> records : record_id\\n(no DB constraint)')
    add_to_caption(out, f"{PUML_NL}{len(MODELS)} Django tables in {len(by_app)} apps, plus {len(IRIS_AI)} in the iris_ai schema. "
                        "Solid arrow: foreign keys (count). Dashed: an id held without a DB constraint.")
    out += ["@enduml"]
    (SRC / "D-08-erd-overview.puml").write_text("\n".join(out) + "\n")


def iris_ai_part(name, title, only):
    tables = [t for t in IRIS_AI if t["name"] in only]
    out = header(title,
                 "Generated from ai/runs/migrations/*.sql on main (IR-1021). Owned by the AI runtime; Django never writes it (ADR-049).")
    for t in tables:
        out.append(f'class "{t["name"]}" as ia_{t["name"]} <<ai>> {{')
        plain = []
        for c in t["columns"]:
            if c["pk"] and c["ref"]:
                out.append(f"  <b>{c['name']}</b> : PK, FK → {c['ref']}")
            elif c["pk"]:
                out.append(f"  <b>{c['name']}</b> : PK")
            elif c["ref"]:
                out.append(f"  {c['name']} : FK → {c['ref']}")
            elif c["name"] in ("reader_id", "record_id", "scope_record_id", "space_id", "chunk_set_id", "chunk_id"):
                out.append(f"  {c['name']} : Django id, no DB constraint")
            else:
                plain.append(c)
        for c in plain[:MAX_ATTRS]:
            out.append(f"  {c['name']} : {c['type']}")
        if len(plain) > MAX_ATTRS:
            out.append(f"  <i>+ {len(plain) - MAX_ATTRS} more columns</i>")
        out.append("}")
    others = sorted({c["ref"] for t in tables for c in t["columns"] if c["ref"] and c["ref"] not in only})
    for r in others:
        out.append(f'class "{r}{PUML_NL}<size:9>(iris_ai, other half)</size>" as ia_{r} <<ref>>')
    names = [{c["name"] for c in t["columns"]} for t in tables]
    if any("reader_id" in n for n in names):
        out.append(f'class "User{PUML_NL}<size:9>(accounts, Django)</size>" as dj_user <<ref>>')
    if any("record_id" in n or "scope_record_id" in n for n in names):
        out.append(f'class "Record{PUML_NL}<size:9>(records, Django)</size>" as dj_record <<ref>>')
    for t in tables:
        for c in t["columns"]:
            if c["ref"]:
                arrow = "}o--o|" if c["null"] else "}o--||"
                if c["pk"]:
                    arrow = "|o--||"
                out.append(f"ia_{t['name']} {arrow} ia_{c['ref']}")
    for t, n in zip(tables, names):
        if "reader_id" in n:
            out.append(f"ia_{t['name']} ..> dj_user : reader_id")
        if "record_id" in n or "scope_record_id" in n:
            out.append(f"ia_{t['name']} ..> dj_record")
    add_to_caption(out, PUML_NL + "Dashed arrow: a Django id held without a DB constraint.")
    out += legend_erd()
    (SRC / f"{name}.puml").write_text(NL.join(out) + NL)


def iris_ai():
    for name, title, only in IRIS_AI_SPLIT:
        iris_ai_part(name, title, only)


def main():
    SRC.mkdir(exist_ok=True)
    for name, title, apps, only in DIAGRAMS:
        domain_erd(name, title, apps, only)
    overview()
    iris_ai()
    print("ERD sources written to", SRC)


if __name__ == "__main__":
    main()
