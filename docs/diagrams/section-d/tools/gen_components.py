"""Generate D-19, the backend component diagram, from the import graph.

Counts `from apps.<x>` / `import apps.<x>` lines in each app's non-test,
non-migration modules on the current checkout.

    python docs/diagrams/section-d/tools/gen_components.py
"""
import collections
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
APPS = ROOT / "backend" / "apps"
OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "D-19-component-backend.puml"

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
    s = path.as_posix()  # forward slashes on every OS, so the checks below hold on Windows too
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
    out = [
        "@startuml",
        "!include ../iris-style.puml",
        "skinparam LineType ortho",
        "title D-19  Backend components: Django apps and their dependencies",
        "caption Generated from import statements in backend/apps on main (IR-1021); tests, migrations, management commands and evaluation tools excluded. Edge label: number of import lines.",
        'package "Django backend (backend/)" {',
        '  component "config\\n<size:10>settings, URLs,</size>\\n<size:10>ASGI, Celery</size>" as config',
        '  component "core\\n<size:10>permissions, pagination,</size>\\n<size:10>utilities</size>" as core',
    ]
    for app in apps:
        stereo = " <<ai>>" if app in ("ai", "publication") else ""
        label = ROLE[app].replace("\\n", "</size>\\n<size:10>")
        out.append(f'  component "{app}\\n<size:10>{label}</size>" as {app}{stereo}')
    out.append("}")
    out.append('rectangle "React SPA\\n(frontend/)" as spa')
    out.append('component "AI runtime\\n(ai/, FastAPI)" as runtime <<ai>>')
    out.append('database "PostgreSQL" as db')
    out.append("spa --> config : REST /api/v1/")
    out.append("config --> core")
    for (a, b), n in sorted(deps.items()):
        out.append(f"{a} --> {b} : {n}")
    out.append("runtime ..> ai : reader grant\\n(edge-grant)")
    out.append("runtime ..> db : iris_ai schema,\\nrow policy")
    out += [
        "legend right",
        "  Solid arrow: Python imports (count). Every app except publication also uses core.",
        "  Dashed arrow: runtime boundary, no Python import",
        "endlegend",
        "@enduml",
    ]
    OUT.write_text("\n".join(out) + "\n")
    print(f"{len(deps)} dependencies written to {OUT.name}")


if __name__ == "__main__":
    main()
