"""Read every Django model in backend/apps without importing Django.

Writes models.json: one entry per concrete model with its app, table-level
fields and relations. The ERD generator reads that file, so every entity and
relation in the ERDs comes from the model source, not from a drawing.

    python docs/diagrams/section-d/tools/extract_models.py
"""
import ast
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
APPS = ROOT / "backend" / "apps"
OUT = pathlib.Path(__file__).resolve().parent / "models.json"

RELATIONS = {"ForeignKey": "fk", "OneToOneField": "o2o", "ManyToManyField": "m2m"}


def call_name(node):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute):
            return f.attr
        if isinstance(f, ast.Name):
            return f.id
    return None


def is_field_call(node):
    name = call_name(node)
    return bool(name) and (name.endswith("Field") or name in RELATIONS or name == "ForeignKey")


def kw(node, key):
    for k in node.keywords:
        if k.arg == key:
            return k.value
    return None


def literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def model_files():
    for app in sorted(p for p in APPS.iterdir() if p.is_dir()):
        single = app / "models.py"
        if single.exists():
            yield app.name, single
        package = app / "models"
        if package.is_dir():
            for f in sorted(package.glob("*.py")):
                yield app.name, f


def main():
    classes = {}
    for app, path in model_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [ast.unparse(b) for b in node.bases]
            fields, abstract, db_table = [], False, None
            for item in node.body:
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for m in item.body:
                        if isinstance(m, ast.Assign) and isinstance(m.targets[0], ast.Name):
                            if m.targets[0].id == "abstract":
                                abstract = bool(literal(m.value))
                            if m.targets[0].id == "db_table":
                                db_table = literal(m.value)
                targets = []
                value = None
                if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    targets, value = [item.targets[0].id], item.value
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.value is not None:
                    targets, value = [item.target.id], item.value
                if not targets or not is_field_call(value):
                    continue
                kind = call_name(value)
                field = {"name": targets[0], "type": kind}
                if kind in RELATIONS:
                    target = value.args[0] if value.args else kw(value, "to")
                    t = literal(target) if target is not None else None
                    if t is None and target is not None:
                        t = ast.unparse(target)
                    field["relation"] = RELATIONS[kind]
                    field["target"] = t
                field["null"] = literal(kw(value, "null")) is True if kw(value, "null") is not None else False
                field["pk"] = literal(kw(value, "primary_key")) is True if kw(value, "primary_key") is not None else False
                field["unique"] = literal(kw(value, "unique")) is True if kw(value, "unique") is not None else False
                fields.append(field)
            classes[(app, node.name)] = {
                "app": app, "name": node.name, "bases": bases, "fields": fields,
                "abstract": abstract, "db_table": db_table, "file": str(path.relative_to(ROOT)),
            }

    by_name = {}
    for (app, name), c in classes.items():
        by_name.setdefault(name, []).append(c)

    def is_model(c, seen=()):
        for b in c["bases"]:
            short = b.split(".")[-1].split("[")[0]
            if b in ("models.Model", "Model") or short in ("AbstractBaseUser", "AbstractUser", "PermissionsMixin"):
                return True
            for parent in by_name.get(short, []):
                if parent["name"] not in seen and is_model(parent, seen + (c["name"],)):
                    return True
        return False

    def inherited_fields(c, seen=()):
        out = []
        for b in c["bases"]:
            short = b.split(".")[-1]
            for parent in by_name.get(short, []):
                if parent["abstract"] and parent["name"] not in seen:
                    out += inherited_fields(parent, seen + (c["name"],)) + parent["fields"]
        return out

    models = []
    for c in classes.values():
        if not is_model(c) or c["abstract"]:
            continue
        fields = inherited_fields(c) + c["fields"]
        names = set()
        uniq = []
        for f in fields:
            if f["name"] not in names:
                names.add(f["name"])
                uniq.append(f)
        user_base = any(b.split(".")[-1] in ("AbstractBaseUser", "AbstractUser") for b in c["bases"])
        models.append({"app": c["app"], "name": c["name"], "file": c["file"],
                       "fields": uniq, "user_model": user_base})

    def resolve(target, app):
        if not isinstance(target, str):
            return None
        if target in ("settings.AUTH_USER_MODEL", "AUTH_USER_MODEL"):
            return "accounts.User"
        if target == "self":
            return None
        if "." in target and not target.startswith("settings"):
            a, n = target.rsplit(".", 1)
            return f"{a}.{n}"
        return f"{app}.{target}"

    known = {f"{m['app']}.{m['name']}" for m in models}
    for m in models:
        for f in m["fields"]:
            if "relation" in f:
                t = f["target"]
                ref = f"{m['app']}.{m['name']}" if t == "self" else resolve(t, m["app"])
                if ref and ref not in known:
                    name = ref.split(".")[-1]
                    cands = [k for k in known if k.endswith("." + name)]
                    ref = cands[0] if len(cands) == 1 else ref
                f["ref"] = ref
    models.sort(key=lambda m: (m["app"], m["name"]))
    OUT.write_text(json.dumps(models, indent=1))
    print(f"{len(models)} models written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
