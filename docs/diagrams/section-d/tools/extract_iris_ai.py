"""Read the AI runtime's own schema (iris_ai) from ai/runs/migrations/*.sql.

Applies the migrations in order: CREATE TABLE, ALTER TABLE ... ADD COLUMN,
ADD CONSTRAINT ... FOREIGN KEY and DROP TABLE. Writes iris_ai.json for the
ERD generator.

    python docs/diagrams/section-d/tools/extract_iris_ai.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "ai" / "runs" / "migrations"
OUT = pathlib.Path(__file__).resolve().parent / "iris_ai.json"

SKIP = ("CONSTRAINT", "PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN KEY", "EXCLUDE", ")")


def strip_comments(sql):
    return re.sub(r"--[^\n]*", "", sql)


def split_columns(body):
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def column(defn):
    m = re.match(r'"?(\w+)"?\s+([\w\[\]]+(?:\s+(?:precision|varying|with time zone))?)(.*)', defn, re.S | re.I)
    if not m:
        return None
    name, typ, rest = m.group(1), m.group(2), m.group(3)
    if name.upper() in [s.split()[0] for s in SKIP]:
        return None
    ref = re.search(r"REFERENCES\s+([\w.]+)", rest, re.I)
    return {
        "name": name,
        "type": typ.lower(),
        "pk": bool(re.search(r"PRIMARY KEY", rest, re.I)),
        "null": not re.search(r"NOT NULL|PRIMARY KEY", rest, re.I),
        "ref": ref.group(1).replace("iris_ai.", "") if ref else None,
    }


def main():
    tables = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = strip_comments(path.read_text(encoding="utf-8"))
        for m in re.finditer(r"CREATE TABLE (?:IF NOT EXISTS )?iris_ai\.(\w+)\s*\((.*?)\);", sql, re.S | re.I):
            name, body = m.group(1), m.group(2)
            cols = []
            for part in split_columns(body):
                if re.match(r"(CONSTRAINT|PRIMARY KEY|UNIQUE|CHECK|FOREIGN KEY|EXCLUDE)\b", part, re.I):
                    fk = re.match(r"(?:CONSTRAINT \w+ )?FOREIGN KEY\s*\((\w+)[^)]*\)\s*REFERENCES\s+([\w.]+)", part, re.I)
                    if fk:
                        for c in cols:
                            if c["name"] == fk.group(1):
                                c["ref"] = fk.group(2).replace("iris_ai.", "")
                    pk = re.match(r"PRIMARY KEY\s*\(([^)]*)\)", part, re.I)
                    if pk:
                        keys = [k.strip() for k in pk.group(1).split(",")]
                        for c in cols:
                            if c["name"] in keys:
                                c["pk"] = True
                    continue
                c = column(part)
                if c:
                    cols.append(c)
            tables[name] = {"name": name, "columns": cols, "created_in": path.name}
        for m in re.finditer(r"ALTER TABLE (?:IF EXISTS )?iris_ai\.(\w+)\s+(.*?);", sql, re.S | re.I):
            table, actions = m.group(1), m.group(2)
            if table not in tables:
                continue
            for act in split_columns(actions):
                add = re.match(r"ADD COLUMN (?:IF NOT EXISTS )?(.*)", act, re.S | re.I)
                if add:
                    c = column(add.group(1))
                    if c and all(x["name"] != c["name"] for x in tables[table]["columns"]):
                        tables[table]["columns"].append(c)
                fk = re.match(r"ADD CONSTRAINT \w+ FOREIGN KEY\s*\((\w+)\)\s*REFERENCES\s+([\w.]+)", act, re.I)
                if fk:
                    for c in tables[table]["columns"]:
                        if c["name"] == fk.group(1):
                            c["ref"] = fk.group(2).replace("iris_ai.", "")
                drop = re.match(r"DROP COLUMN (?:IF EXISTS )?(\w+)", act, re.I)
                if drop:
                    tables[table]["columns"] = [c for c in tables[table]["columns"] if c["name"] != drop.group(1)]
        for m in re.finditer(r"DROP TABLE (?:IF EXISTS )?iris_ai\.(\w+)", sql, re.I):
            tables.pop(m.group(1), None)
    OUT.write_text(json.dumps(list(tables.values()), indent=1))
    print(f"{len(tables)} iris_ai tables written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
