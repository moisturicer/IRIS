"""Generate D-19, the backend component diagram, from the import graph.

Counts `from apps.<x>` / `import apps.<x>` lines in each app's non-test,
non-migration modules on the current checkout.

    python docs/diagrams/section-d/tools/gen_components.py
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
APPS = ROOT / "backend" / "apps"
OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "D-19-component-backend.json"
WRAP = 120  # text width of a component box

ROLE = {
    "accounts": "users, roles, consent,\\nsessions, recovery",
    "records": "records, versions, embargo,\\ndownload and delete requests",
    "reviews": "adviser-first review, seats,\\nclearances, threads",
    "documents": "uploads, PDF checks,\\nextraction tasks",
    "ai": "chunking, embedding, reader\\ngrants, admission, overview",
    "notifications": "in-app and email\\nnotifications",
    "audit": "insert-only audit log,\\nCSV export",
    "library": "saved records\\nand feeds",
    "opportunities": "Calls & Conferences",
    "publication": "manuscript processing\\nwork for the AI runtime",
}


def is_source(path):
    s = path.as_posix()  # the same answer on Windows and Linux
    return not ("/tests" in s or "/test_" in s or "/migrations/" in s or path.name.startswith("test")
                or "/management/" in s or "/evaluation/" in s)


def main():
    apps = sorted(p.name for p in APPS.iterdir() if p.is_dir() and p.name in ROLE)
    deps = collections.Counter()
    for app in apps:
        for f in (APPS / app).rglob("*.py"):
            if not is_source(f):
                continue
            for m in re.finditer(r"^\s*(?:from|import)\s+apps\.(\w+)", f.read_text(errors="ignore"), re.M):
                target = m.group(1)
                if target != app and target in ROLE:
                    deps[(app, target)] += 1
    nodes = [
        {"id": "spa", "shape": "box", "tone": "plain", "label": "React SPA", "sub": "frontend/", "wrap": WRAP},
        {"id": "config", "shape": "box", "label": "config", "sub": "settings, URLs, ASGI, Celery", "wrap": WRAP},
        {"id": "core", "shape": "box", "label": "core", "sub": "permissions, pagination, utilities", "wrap": WRAP},
    ]
    for app in apps:
        node = {"id": app, "shape": "box", "label": app, "sub": ROLE[app].replace("\\n", " "), "wrap": WRAP}
        if app in ("ai", "publication"):
            node["tone"] = "ai"
        nodes.append(node)
    nodes.append({"id": "runtime", "shape": "box", "tone": "ai", "label": "AI runtime", "sub": "ai/, FastAPI", "wrap": WRAP})
    nodes.append({"id": "db", "shape": "db", "label": "PostgreSQL", "wrap": WRAP})
    edges = [{"from": "spa", "to": "config", "label": "REST /api/v1/"}, {"from": "config", "to": "core"}]
    edges += [{"from": a, "to": b, "label": str(n)} for (a, b), n in sorted(deps.items())]
    edges.append({"from": "runtime", "to": "ai", "label": "reader grant (edge-grant)", "dash": True, "wrap": 64})
    edges.append({"from": "runtime", "to": "db", "label": "iris_ai schema, row policy", "dash": True, "wrap": 64})
    spec = {
        "kind": "columns", "format": "portrait", "gutter": 96, "vgap": 30, "columnCount": 3, "level": 10,
        "title": "D-19  Backend components: Django apps and their dependencies",
        "caption": "Generated from import statements in backend/apps on main (IR-1021); tests, migrations, management "
                   "commands and evaluation tools excluded. The number on a line is the count of import lines. "
                   "Every app except publication also uses core.",
        "nodes": nodes, "edges": edges,
        "legend": [
            {"line": "arrow", "text": "Python imports (count)"},
            {"line": "dash arrow", "text": "runtime boundary, no Python import"},
            {"tone": "core", "text": "Django app (backend/)"}, {"tone": "ai", "text": "AI indexing / AI runtime"},
            "lines to the same component share a trunk, joined with a dot",
        ],
    }
    OUT.write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(deps)} dependencies written to {OUT.name}")


if __name__ == "__main__":
    main()
