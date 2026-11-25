"""Write the SRS v2 / SDD v2 per-feature diagram sources (IR-1275).

The figures are described as compact Python data in this folder:

    usecases.py    U-*  one use-case diagram per SRS v2 feature
    activities.py  A-*  activity diagrams (each action names who does it)
    sequences.py   Q-*  one sequence diagram per SDD v2 feature
    classes.py     C-*  class diagrams per SDD v2 feature group
    schemas.py     E-*  schema extracts, generated from the Django models

This script turns them into src/*.json in the shapes the Section D renderer
(docs/diagrams/section-d/tools/render.mjs) draws. Re-run it after editing the
data, then render (README.md).

    python docs/diagrams/srs-sdd-v2/tools/gen_v2.py
"""
import importlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "src"
SECTION_D = HERE.parents[1] / "section-d" / "tools"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SECTION_D))

EXT = {"Unstructured", "Voyage AI", "Language model", "Email service", "SMTP", "ClamAV"}
AI_LANES = {"AI runtime", "ai-gateway", "ai-runs-worker"}
UC_LEGEND = [{"line": "solid", "text": "actor takes part"},
             {"line": "dash arrow", "text": "dependency between use cases"}]


def write(name, spec):
    (SRC / f"{name}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- use cases
def usecase(d):
    cases = []
    for c in d["cases"]:
        cid, label = c[0], c[1]
        opts = c[2] if len(c) > 2 else {}
        node = {"id": cid, "label": label, "wrap": opts.get("wrap", 160)}
        if opts.get("ai"):
            node["tone"] = "ai"
        cases.append(node)
    legend = list(UC_LEGEND)
    if any(c.get("tone") == "ai" for c in cases):
        legend.append({"tone": "ai", "text": "AI-assisted"})
    if d.get("right"):
        legend.append({"tone": "ext", "text": "external system"})
    return {
        "kind": "usecase", "format": "portrait",
        "title": d["title"], "caption": d["caption"], "system": d["system"],
        "left": [{"id": a, "label": l} for a, l in d["left"]],
        "right": [{"id": a, "label": l, "tone": "ext"} for a, l in d.get("right", [])],
        "cases": cases,
        "links": [[actor, *cs] for actor, cs in d["links"].items()],
        "deps": [{"from": f, "to": t, "label": f"«{k}»"} for f, t, k in d.get("deps", [])],
        "notes": [{"on": on, "text": text, "wrap": 130} for on, text in d.get("notes", [])],
        "legend": legend,
    }


# ---------------------------------------------------------------- activities
class Flow:
    """Builds an activity graph from a list of steps.

    ("Lane", "text")                       an action; the lane is who does it
    ("?", "question", [yes...], [no...])   a decision; a branch ending in "end" stops there
    ("||", [branch...], [branch...])       work that continues in parallel
    "end"                                  a final node
    """

    def __init__(self):
        self.nodes, self.edges, self.n = [], [], 0

    def nid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def tone(self, lane):
        if lane in EXT:
            return "ext"
        if lane in AI_LANES:
            return "ai"
        if lane[:1].isupper() and lane in ACTORS:
            return "plain"
        return "core"

    def run(self, steps, tails, label=None):
        """Append steps after `tails` (list of (node, edge label)). Returns the open tails."""
        for s in steps:
            if s == "end":
                e = self.nid("end")
                self.nodes.append({"id": e, "shape": "end"})
                self.link(tails, e, label)
                return []
            if s[0] == "?":
                q = self.nid("q")
                self.nodes.append({"id": q, "shape": "diamond", "wrap": 150, "label": s[1]})
                self.link(tails, q, label)
                labels = s[4] if len(s) > 4 else ("yes", "no")
                yes = self.run(s[2], [(q, labels[0])])
                no = self.run(s[3], [(q, labels[1])]) if s[3] else [(q, labels[1])]
                tails, label = yes + no, None
                continue
            if s[0] == "||":
                fork = self.nid("bar")
                self.nodes.append({"id": fork, "shape": "bar", "barW": 180})
                self.link(tails, fork, label)
                out = []
                for branch in s[1:]:
                    out += self.run(branch, [(fork, None)])
                join = self.nid("bar")
                self.nodes.append({"id": join, "shape": "bar", "barW": 180})
                self.link(out, join, None)
                tails, label = [(join, None)], None
                continue
            lane, text = s[0], s[1]
            a = self.nid("a")
            self.nodes.append({"id": a, "shape": "box", "tag": lane, "label": text, "plain": True,
                               "tone": self.tone(lane), "wrap": 150})
            self.link(tails, a, label)
            tails, label = [(a, None)], None
        return tails

    def link(self, tails, to, label):
        for frm, lab in tails:
            e = {"from": frm, "to": to}
            if lab or label:
                e["label"] = lab or label
            self.edges.append(e)


ACTORS = set()


def activity(d):
    ACTORS.update(d.get("actors", []))
    f = Flow()
    f.nodes.append({"id": "start", "shape": "start"})
    tails = f.run(d["steps"], [("start", None)])
    if tails:
        f.nodes.append({"id": "stop", "shape": "end"})
        f.link(tails, "stop", None)
    legend = ["first line of an action: who does it",
              {"tone": "core", "text": "IRIS"}]
    tones = {n.get("tone") for n in f.nodes}
    if "plain" in tones:
        legend.insert(1, {"tone": "plain", "text": "person"})
    if "ai" in tones:
        legend.append({"tone": "ai", "text": "AI runtime"})
    if "ext" in tones:
        legend.append({"tone": "ext", "text": "external service"})
    if any(n["shape"] == "bar" for n in f.nodes):
        legend.append("bar: work that continues in parallel")
    return {
        "format": "portrait", "direction": "DOWN", "title": d["title"], "caption": d["caption"],
        "elk": {"elk.layered.spacing.nodeNodeBetweenLayers": "16", "elk.spacing.nodeNode": "22",
                "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
                "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
                "elk.aspectRatio": str(d.get("aspect", 0.7))},
        "nodes": f.nodes, "edges": f.edges, "legend": legend,
    }


# ---------------------------------------------------------------- sequences
def seq_steps(steps):
    out = []
    for s in steps:
        if s[0] == "loop":
            out.append({"loop": s[1], "steps": seq_steps(s[2])})
        else:
            kind, frm, to, label = s
            m = {"from": frm, "to": to, "label": label}
            if kind == "r":
                m["dash"] = True
            out.append(m)
    return out


def sequence(d):
    parts = []
    for p in d["participants"]:
        pid, label = p[0], p[1]
        node = {"id": pid, "label": label}
        if len(p) > 2 and p[2]:
            node["sub"] = p[2]
        if len(p) > 3:
            node["tone"] = p[3]
        parts.append(node)
    legend = [{"line": "arrow", "text": "request or write"}, {"line": "dash arrow", "text": "response or notice"}]
    tones = {p.get("tone") for p in parts}
    if "ai" in tones:
        legend.append({"tone": "ai", "text": "AI runtime"})
    if "ext" in tones:
        legend.append({"tone": "ext", "text": "external service"})
    return {"kind": "sequence", "format": "portrait", "title": d["title"], "caption": d["caption"],
            "participants": parts, "steps": seq_steps(d["steps"]), "legend": legend}


# ---------------------------------------------------------------- classes
def klass(d):
    nodes = []
    for c in d["nodes"]:
        cid, attrs, ops = c[0], c[1], c[2] if len(c) > 2 else []
        sections = [attrs] + ([ops] if ops else [])
        node = {"id": cid, "shape": "class", "label": cid, "sections": sections}
        if len(c) > 3:
            node.update(c[3])
        nodes.append(node)
    edges = []
    for e in d["edges"]:
        frm, to, kind = e[0], e[1], e[2]
        opts = e[3] if len(e) > 3 else {}
        if kind == "owns":
            edge = {"from": frm, "to": to, "tail": "diamond", "head": "none", "mFrom": "1", "mTo": opts.pop("m", "0..*")}
        elif kind == "uses":
            edge = {"from": frm, "to": to, "dash": True}
        else:  # association
            edge = {"from": frm, "to": to}
        edge.update(opts)
        edges.append(edge)
    legend = [{"line": "diamond", "text": "composition (owner at the diamond)"},
              {"line": "arrow", "text": "association"},
              {"line": "dash arrow", "text": "uses / calls"}]
    return {"kind": "columns", "format": d.get("format", "portrait"), "title": d["title"], "caption": d["caption"],
            "gutter": d.get("gutter", 60), "vgap": d.get("vgap", 30),
            "nodes": nodes, "columns": d["columns"], "edges": edges, "legend": legend}


# ---------------------------------------------------------------- schemas
def schema(d):
    import gen_erd as g
    want = set(d["models"])
    members = [m for m in g.MODELS if g.key(m) in want]
    missing = want - {g.key(m) for m in members}
    assert not missing, f"{d['title']}: no such model {missing}"
    names = {g.key(m) for m in members}
    nodes = [{"id": g.alias(g.key(m)), "shape": "table", "label": m["name"], "tone": "core",
              "sections": [rows_any(g, m, names)]} for m in members]
    edges = []
    for m in members:
        for f in m["fields"]:
            if "relation" in f and f["ref"] in names:
                tail, head = g.ends(f["relation"], f.get("null"))
                edges.append({"from": g.alias(g.key(m)), "to": g.alias(f["ref"]), "field": f["name"],
                              "tail": tail, "head": head})
    return {"title": d["title"], "caption": d["caption"] + " Generated from backend/apps/*/models*.py at 2d8d4e4a; "
            "all keys and up to four other fields per table; the full schema is D-8 to D-15.",
            "kind": "erd", "format": d.get("format", "portrait"),
            "nodes": nodes, "edges": edges, "legend": g.LEGEND[:3] + ["FK → Name (D-n): drawn in full on figure D-n"]}


def rows_any(g, m, names):
    """gen_erd.rows, but a key to a table outside this extract names its Section D figure."""
    return g.rows(m, names)


def main():
    SRC.mkdir(exist_ok=True)
    count = 0
    for module, fn in (("usecases", usecase), ("activities", activity), ("sequences", sequence),
                       ("classes", klass), ("schemas", schema)):
        try:
            data = importlib.import_module(module)
        except ModuleNotFoundError:
            continue
        ACTORS.update(getattr(data, "ACTORS", []))
        for name, d in data.FIGURES.items():
            write(name, fn(d))
            count += 1
    print(f"{count} diagram sources written to {SRC}")


if __name__ == "__main__":
    main()
