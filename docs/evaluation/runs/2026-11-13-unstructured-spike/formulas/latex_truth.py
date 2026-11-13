"""Score model LaTeX against the authors' display equations."""
import difflib, json, re, sys
from pathlib import Path

ENVS = r"equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|displaymath"


def strip_comments(t):
    return re.sub(r"(?<!\\)%.*", "", t)


def macros(t):
    out = {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\(\w+)\}?\s*(?:\[(\d)\])?\s*\{", t):
        i, depth = m.end(), 1
        while i < len(t) and depth:
            depth += {"{": 1, "}": -1}.get(t[i], 0)
            i += 1
        out[m.group(1)] = (int(m.group(2) or 0), t[m.end():i - 1])
    for m in re.finditer(r"\\DeclareMathOperator\*?\{\\(\w+)\}\{([^}]*)\}", t):
        out[m.group(1)] = (0, "\\operatorname{" + m.group(2) + "}")
    return out


def expand(s, defs, rounds=4):
    for _ in range(rounds):
        def sub(m):
            name = m.group(1)
            if name in defs and defs[name][0] == 0:
                return defs[name][1].replace("\\", "\\\\")
            return m.group(0)
        s2 = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", lambda m: sub(m).replace("\\\\", "\\"), s)
        for name, (n, body) in defs.items():
            if n == 1:
                s2 = re.sub(r"\\" + name + r"\s*\{([^{}]*)\}", lambda m: body.replace("#1", m.group(1)), s2)
        if s2 == s:
            break
        s = s2
    return s


def equations(tex_dir):
    text = "\n".join(strip_comments(p.read_text(encoding="utf-8", errors="ignore"))
                     for p in Path(tex_dir).rglob("*.tex"))
    defs = macros(text)
    eqs = [m.group(2) for m in re.finditer(r"\\begin\{(" + ENVS + r")\}(.*?)\\end\{\1\}", text, re.S)]
    eqs += re.findall(r"\\\[(.*?)\\\]", text, re.S) + re.findall(r"\$\$(.*?)\$\$", text, re.S)
    return [expand(e, defs) for e in eqs]


SAME = [  # pairs that typeset identically
    (r"\\ket\{([^{}]*)\}", r"|\1\\rangle"), (r"\\bra\{([^{}]*)\}", r"\\langle \1|"),
    (r"\\bm\{", r"\\boldsymbol{"), (r"\\mathbf\{(\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|rho|sigma|phi|psi|omega|Lambda|Gamma|Delta|Theta|Sigma|Phi|Psi|Omega))\}", r"\\boldsymbol{\1}"),
    (r"\\le(?![a-zA-Z])", r"\\leq"), (r"\\ge(?![a-zA-Z])", r"\\geq"), (r"\\land(?![a-zA-Z])", r"\\wedge"),
    (r"\\lor(?![a-zA-Z])", r"\\vee"), (r"\\ast(?![a-zA-Z])", "*"), (r"\\dfrac", r"\\frac"), (r"\\tfrac", r"\\frac"),
    (r"\\phantom\{[^{}]*\}", ""), (r"\\\\\[[^\]]*\]", r"\\\\"), (r"\\scalebox\{[^{}]*\}", ""), (r"\\ensuremath", ""),
    (r"\\text\{\s*([^{}]*?)\s*\}", r"\\mathrm{\1}"), (r"\\operatorname\{", r"\\mathrm{"),
]


def norm(s):
    for a, b in SAME:
        s = re.sub(a, b, s)
    s = re.sub(r"\\(label|tag|eqref|ref)\{[^}]*\}", "", s)
    s = re.sub(r"\\(nonumber|notag|displaystyle|left|right|bigg|Bigg|big|Big)[lrm]?(?![A-Za-z])", "", s)
    s = re.sub(r"\\[,;:! ]|\\q?quad(?![A-Za-z])|~|&|\\\\", "", s)
    s = re.sub(r"\\(begin|end)\{(aligned|split)\}", "", s)
    s = re.sub(r"\s+", "", s)
    for _ in range(3):
        s = re.sub(r"([_^])\{(\\?[A-Za-z0-9])\}", r"\1\2", s)
    s = s.replace("\\cdots", "\\ldots").replace("\\dots", "\\ldots").replace("\\mathrm{d}", "d")
    return s.rstrip(".,;")


def score(preds, truth):
    T = [(t, norm(t)) for t in truth if norm(t)]
    rows = []
    for p in preds:
        n = norm(p)
        best = max(T, key=lambda t: difflib.SequenceMatcher(None, n, t[1]).ratio())
        r = difflib.SequenceMatcher(None, n, best[1]).ratio()
        rows.append({"exact": n == best[1], "similarity": round(r, 3), "pred": p, "truth": best[0].strip()})
    return rows


if __name__ == "__main__":
    S = Path(sys.argv[1])
    latex = json.load(open(S / "crops/latex.json", encoding="utf-8"))
    report = {}
    for p in ("38", "58", "25", "40"):
        print(p, "source display equations:", len(equations(S / "arxiv_src" / p / "tex")))
    for model in sorted({r["model"] for r in latex if "latex" in r}):
        allrows = []
        for p in ("38", "58", "25", "40"):
            preds = [r["latex"] for r in latex if r["model"] == model and r["paper"] == p and "latex" in r]
            allrows += [dict(x, paper=p) for x in score(preds, equations(S / "arxiv_src" / p / "tex"))]
        ex = sum(r["exact"] for r in allrows)
        hi = sum(r["similarity"] >= 0.95 for r in allrows)
        print(f"{model}: exact {ex}/{len(allrows)}, >=0.95 similar {hi}/{len(allrows)}, "
              f"mean similarity {sum(r['similarity'] for r in allrows) / len(allrows):.3f}")
        report[model] = allrows
    json.dump(report, open(S / "crops/truth_scores.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
