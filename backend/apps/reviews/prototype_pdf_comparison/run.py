"""PROTOTYPE, throwaway. Run:  python apps/reviews/prototype_pdf_comparison/run.py  (from backend/)

Needs pdfplumber and reportlab, which are not in requirements:
    pip install pdfplumber==0.11.4 reportlab==4.2.5

Runs every check on two sources of the same two Versions:
  drawn - PDFs drawn by make_versions.py, so every position is known exactly
  word  - .docx files built in Microsoft Word and exported by Word to PDF
          (Windows with Word only; skipped elsewhere, or with --no-word)
Writes out/report.html, plus the PDFs and .docx files, next to this file.
"""
import base64
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import compare as c          # noqa: E402
import make_versions as mv   # noqa: E402

OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
FIXTURES = HERE.parents[1] / "ai" / "extraction" / "tests" / "fixtures"
FIXTURE_ORDER = {   # copied from layouts.py's reading_order
    "two_columns.pdf": ["Left column one", "Left column two", "E = m c^2", "Left column three",
                        "Right column one", "Right column two", "Right column three"],
    "numbered_headings.pdf": ["1 Introduction", "1.1 Background", "2 Methods", "3 Results"],
    "table_across_pages.pdf": ["Measurements", "Row 01", "Row 28", "Row 29", "Row 30",
                               "The paragraph after the table."],
}
VERSIONS = {"v1": mv.V1, "v2": mv.make_v2()}
e = html.escape


# ---------------------------------------------------------------- sources
def drawn(name, blocks):
    pdf, truth, words = mv.build(blocks)
    path = OUT / f"{name}-drawn.pdf"
    path.write_bytes(pdf)
    return path, truth, words


def word(name, blocks):
    spec = OUT / f"{name}-blocks.json"
    spec.write_text(json.dumps(mv.to_json(blocks)), encoding="utf-8")
    docx, pdf, pages = (OUT / f"{name}-word.{x}" for x in ("docx", "pdf", "pages.json"))
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(HERE / "word_export.ps1"), str(spec), str(docx), str(pdf), str(pages)], check=True)
    truth = [(x["text"], x["page"]) for x in json.loads(pages.read_text(encoding="utf-8-sig"))]
    return pdf, truth, mv.words_of(blocks)


def word_available():
    if "--no-word" in sys.argv or not shutil.which("powershell"):
        return False
    probe = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "try { $w = New-Object -ComObject Word.Application; $w.Quit(); 'yes' } catch { 'no' }"],
                           capture_output=True, text=True)
    return probe.stdout.strip() == "yes"


# ---------------------------------------------------------------- one source
def run_case(source, make):
    built = {n: make(n, b) for n, b in VERSIONS.items()}
    A, B = (c.read(built[n][0]) for n in ("v1", "v2"))
    results = c.compare(A, B)
    checks = []

    def check(group, what, passed, detail=""):
        checks.append((group, what, bool(passed), str(detail)))

    for label, R in (("v1", A), ("v2", B)):
        _, truth, words = built[label]
        sents = [x for s in R.sections for x in s.sentences]
        n_pages = len(R.columns)
        leaked = [x.text for x in sents if x.page > 1 and (mv.RUNNING_HEAD in x.text or x.text.strip().isdigit())]
        check(f"Reading {label}", "Running heads and page numbers removed",
              not leaked and len(R.dropped) == 2 * (n_pages - 1),
              f"{len(R.dropped)} margin lines dropped on {n_pages} pages; leaked into text: {leaked or 'none'}")
        lower = {w.lower() for w in words}
        unknown = sorted({t for x in sents for t in (re.sub(r"[^\w,.'-]", "", w).strip(".,;:")
                                                      for w in x.text.replace(" | ", " ").split())
                          if t and t.lower() not in lower})
        check(f"Reading {label}", "Every word read is a word that was written (no broken or fused words)",
              not unknown, ", ".join(unknown[:12]) or f"{len(R.repairs)} line-end hyphens repaired")
        keys = {x.key: x for x in sents}
        found = [(s, p, keys.get(c.norm(s))) for s, p in truth]
        missing = [s for s, p, x in found if x is None]
        wrong_page = [(s[:40], p, x.page) for s, p, x in found if x and x.page != p]
        check(f"Reading {label}", "Every sentence comes back whole, split where it ends",
              not missing, f"{len(truth) - len(missing)} of {len(truth)}" + (f"; missing: {missing[:2]}" if missing else ""))
        check(f"Reading {label}", "Each sentence's page is the page it starts on",
              not wrong_page, f"{len(found) - len(missing) - len(wrong_page)} of {len(found) - len(missing)} right"
              + (f"; e.g. {wrong_page[0]}" if wrong_page else ""))
        heads = [b for b in VERSIONS[label] if b[0] in ("chapter", "heading")]
        got = {s.key for s in R.sections}
        want = {c.NUMBERING.sub("", b[2].lower()).strip() if b[0] == "heading" else b[2].lower() for b in heads}
        check(f"Reading {label}", "Every chapter and section heading found, none invented",
              want <= got and len(got - want - {"front matter"}) <= 1,
              f"{len(want & got)} of {len(want)}; missing: {sorted(want - got) or 'none'}; extra: {sorted(got - want) or 'none'}")
        rows = [x.text for x in sents if x.kind == "row"]
        check(f"Reading {label}", "The table is read as rows, not as loose words",
              len(rows) == 5, f"{len(rows)} rows: {rows[:2]}")

    by_key = {(r["a"] or r["b"]).key: r for r in results}
    for key, status in mv.CHANGES["sections"].items():
        r = by_key.get(key)
        if status == "renamed":
            ok = r and "renamed" in r["flags"]
            check("Comparing", f'"{key}" is matched to its renamed section', ok,
                  f'"{r["a"].heading}" → "{r["b"].heading}"' if ok else (r and r["status"]))
        else:
            check("Comparing", f'"{key}" reads {status}', r and r["status"] == status, r and r["status"])
    moved = {k for k, r in by_key.items() if "moved" in r["flags"]}
    check("Comparing", "The swapped literature sections read moved",
          moved & mv.CHANGES["moved_one_of"] and len(moved) == 1, f"moved: {sorted(moved)}")
    others = [k for k, r in by_key.items() if k not in mv.CHANGES["sections"] and r["status"] != "unchanged"]
    shifted = [f'{k} p.{r["a"].page}→{r["b"].page}' for k, r in by_key.items()
               if r["a"] and r["b"] and r["a"].page != r["b"].page and r["status"] == "unchanged"]
    check("Comparing", "Every other section reads unchanged, even where its page moved",
          not others and shifted, f"not unchanged: {others or 'none'}; pages moved: {', '.join(shifted) or 'none'}")
    bg = by_key.get("background of the study", {"changes": []})
    edit = [ch for ch in bg["changes"] if ch["op"] == "changed"]
    check("Comparing", "The edited figure shows as a word change, not a whole new sentence",
          edit and ("del", "1,200") in edit[0]["words"] and ("ins", "1,350") in edit[0]["words"],
          edit and " ".join(f"[{t}: {w}]" if t != "same" else "…" for t, w in edit[0]["words"]))
    gone = [ch for ch in by_key.get("conversion technologies", {"changes": []})["changes"] if ch["op"] == "removed"]
    check("Comparing", "The removed paragraph's sentences read removed",
          len(gone) == mv.CHANGES["removed_sentences"], f"{len(gone)} removed")
    row = [ch for ch in by_key.get("data collection", {"changes": []})["changes"]
           if ch["op"] == "changed" and ch["a"].kind == "row"]
    check("Comparing", "The corrected table value shows in its row",
          row and mv.CHANGES["table_row"] in row[0]["a"].text, row and f'{row[0]["a"].text} → {row[0]["b"].text}')
    concl = [ch["op"] for ch in by_key.get("conclusions", {"changes": []})["changes"] if ch["op"] != "unchanged"]
    check("Comparing", "The added conclusion sentence reads added, nothing else", concl == ["added"], concl)

    sents_a = [x for s in A.sections for x in s.sentences]
    threads = []

    def thread(name, quote, expect_found):
        hit = c.find_quote(B, quote)
        near = None if hit else c.nearest(B, quote)
        threads.append((name, quote, hit, near, expect_found))
        check("Threads", name, (hit is not None) == expect_found,
              f"found on p. {hit.page}" if hit else f"Outdated; nearest now: “{near.text[:70]}…”")

    comp = next(x for x in sents_a if x.text.startswith("Organic waste made up 52"))
    thread(f"A quote on v1 p. {comp.page}, in a section that didn't change, is found again", comp.text[:60], True)
    thread("A quote whose words were edited reads Outdated", "about 1,200 tonnes of municipal solid waste", False)
    rep = next(r for r in A.repairs if r[2].strip(".,;'s").isalpha())
    hy = next(x for x in sents_a if rep[2] in x.text)
    head, tail = rep[1].split(" / ")
    thread(f"A quote across a hyphenated line break (“{head} {tail}”) is found",
           hy.text.replace(rep[2], f"{head}\n{tail}"), True)
    across = next((x for x in sents_a if len({r["page"] for r in x.regions}) > 1), None)
    if across:
        thread(f"A sentence that runs from p. {across.page} onto p. {across.regions[-1]['page']} is found",
               across.text, True)
    else:
        check("Threads", "A sentence that runs onto the next page is found", False, "no such sentence in v1")
    gas = next(x for x in sents_a if x.text.startswith("Gasification converts"))
    thread("A quote in the removed paragraph reads Outdated", gas.text[:50], False)
    return {"source": source, "A": A, "B": B, "results": results, "checks": checks, "threads": threads,
            "pdfs": {n: built[n][0] for n in built}}


def fixture_checks():
    checks = []
    for name, order in FIXTURE_ORDER.items():
        R = c.read(FIXTURES / name)
        stream = " ".join(f"{s.heading} " + " ".join(x.text for x in s.sentences) for s in R.sections)
        pos = [stream.find(o) for o in order]
        ok = all(p >= 0 for p in pos) and pos == sorted(pos)
        checks.append(("Harder layouts", f"{name}: text comes out in reading order", ok,
                       f"positions {pos}; columns found per page: {R.columns}"))
    return checks


# ---------------------------------------------------------------- report
def badge(ok):
    return '<span class="ok">pass</span>' if ok else '<span class="no">fail</span>'


def words_html(parts):
    return " ".join(f"<del>{e(w)}</del>" if t == "del" else f"<ins>{e(w)}</ins>" if t == "ins" else e(w)
                    for t, w in parts)


def check_table(checks):
    return ('<div class="wrap"><table><tr><th>Area</th><th>Check</th><th></th><th>Detail</th></tr>' + "".join(
        f"<tr><td>{e(g)}</td><td>{e(w)}</td><td>{badge(p)}</td><td><small>{e(d)}</small></td></tr>"
        for g, w, p, d in checks) + "</table></div>")


def case_html(case):
    rows = []
    for r in case["results"]:
        sa, sb = r["a"], r["b"]
        name = e(sb.heading if sb else sa.heading)
        if sa and sb and sa.heading != sb.heading:
            name = f"{e(sb.heading)}<br><small>was {e(sa.heading)}</small>"
        flags = " ".join(f'<span class="flag">{f}</span>' for f in r["flags"])
        details = []
        for ch in r["changes"]:
            if ch["op"] == "unchanged":
                continue
            x = ch.get("a") or ch.get("b")
            pages = f'p. {ch["a"].page if ch.get("a") else "–"} → p. {ch["b"].page if ch.get("b") else "–"}'
            body = words_html(ch["words"]) if ch["op"] == "changed" else e(x.text)
            details.append(f'<li class="{ch["op"].split()[0]}"><b>{ch["op"]}</b> <small>{pages}</small><br>{body}</li>')
        rows.append(f'<tr class="st-{r["status"]}"><td>{name}</td><td>{sa.page if sa else "–"}</td>'
                    f'<td>{sb.page if sb else "–"}</td><td><span class="status">{r["status"]}</span> {flags}</td>'
                    f'<td>{"<ul>" + "".join(details) + "</ul>" if details else ""}</td></tr>')
    threads = "".join(
        f"<tr><td>{e(n)}</td><td><code>{e(q[:90])}{'…' if len(q) > 90 else ''}</code></td>"
        f"<td>{('found on p. ' + str(h.page) + ' <small>' + e(str(h.regions[0])) + '</small>') if h else ('Outdated<br><small>nearest now: ' + e(nr.text[:80]) + '…</small>')}</td>"
        f"<td>{badge((h is not None) == x)}</td></tr>" for n, q, h, nr, x in case["threads"])
    repairs = "".join(f"<li>p. {p}: <code>{e(a)}</code> → <code>{e(b)}</code></li>" for p, a, b in case["A"].repairs)
    b64 = {n: base64.b64encode(p.read_bytes()).decode() for n, p in case["pdfs"].items()}
    sid = case["source"]
    return f"""
<h2>Checks</h2>{check_table(case["checks"])}
<h2>Changes, v1 → v2 (what a reviewer's Changes tab would show)</h2>
<div class="wrap"><table><tr><th>Section</th><th>v1 page</th><th>v2 page</th><th>Status</th><th>What changed</th></tr>
{''.join(rows)}</table></div>
<h2>Threads made on v1, looked for in v2</h2>
<p class="lead">The quote is what the browser's PDF text layer gives when a reviewer selects text, so a selection
across a line break keeps the break and the hyphen.</p>
<div class="wrap"><table><tr><th>Thread</th><th>Quote</th><th>In v2</th><th></th></tr>{threads}</table></div>
<h2>Line-end hyphens the reader repaired (v1)</h2><ul>{repairs}</ul>
<h2>The two Versions</h2>
<div class="pdfs"><embed data-pdf="{b64['v1']}" type="application/pdf"><embed data-pdf="{b64['v2']}" type="application/pdf"></div>"""


def report(cases, extra):
    tabs = "".join(f'<button role="tab" data-tab="{x["source"]}">{LABELS[x["source"]]} '
                   f'({sum(p for *_, p, _ in x["checks"])}/{len(x["checks"])})</button>' for x in cases)
    panels = "".join(f'<section role="tabpanel" id="{x["source"]}">{case_html(x)}</section>' for x in cases)
    all_checks = [ch for x in cases for ch in x["checks"]] + extra
    passed = sum(1 for *_, p, _ in all_checks if p)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF Version comparison</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1c1a; --muted:#6b6862; --line:#e3e0d9; --ok:#1f7a4d; --no:#b3261e;
  --add:#e3f4e8; --del:#fbe4e1; --chg:#fff4d6; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#161514; --fg:#ecebe8; --muted:#a39f97;
  --line:#34322f; --ok:#5fcf95; --no:#ff8a80; --add:#16321f; --del:#3a1b18; --chg:#352c12; --card:#1f1e1c; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0; padding:24px 16px 64px; }}
main {{ max-width:1100px; margin:auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:17px; margin:32px 0 8px; }}
.proto {{ display:inline-block; background:var(--chg); padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; }}
p.lead {{ color:var(--muted); max-width:800px; }}
.verdict {{ font-size:18px; font-weight:600; margin:16px 0; }}
[role=tablist] {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:24px; }}
[role=tab] {{ font:inherit; padding:8px 14px; border:1px solid var(--line); background:var(--card); color:var(--fg);
  border-radius:6px; cursor:pointer; }}
[role=tab][aria-selected=true] {{ border-color:var(--fg); font-weight:600; }}
[role=tabpanel][hidden] {{ display:none; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); }}
td, th {{ border-bottom:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
th {{ font-size:12px; text-transform:uppercase; color:var(--muted); }}
.ok {{ color:var(--ok); font-weight:700; }} .no {{ color:var(--no); font-weight:700; }}
.flag {{ background:var(--chg); padding:1px 6px; border-radius:4px; font-size:12px; }}
.status {{ font-weight:600; }} .st-unchanged td {{ color:var(--muted); }}
ul {{ margin:0; padding-left:18px; }} li {{ margin-bottom:6px; }}
li.added, li.moved {{ background:var(--add); }} li.removed {{ background:var(--del); }} li.changed {{ background:var(--chg); }}
ins {{ background:var(--add); text-decoration:none; font-weight:600; }} del {{ background:var(--del); }}
small {{ color:var(--muted); }} code {{ font-size:13px; white-space:pre-wrap; }}
.wrap {{ overflow-x:auto; }}
.pdfs {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.pdfs embed {{ width:100%; height:640px; border:1px solid var(--line); }}
@media (max-width:720px) {{ .pdfs {{ grid-template-columns:1fr; }} }}
</style></head><body><main>
<span class="proto">PROTOTYPE · throwaway</span>
<h1>Can a PDF's text, read on campus with no AI, drive Version comparison?</h1>
<p class="lead">Two Versions of the seeded paper <i>{e(mv.TITLE)}</i>, laid out like a CIT-U thesis: double-spaced,
justified, hyphenated at line ends, running head, page numbers, chapters on new pages, a ruled table. v2 makes seven
known edits and adds enough text to push every later page back. pdfplumber reads the words and their positions;
everything after that is rules (<code>compare.py</code>). Each check compares what the reader found with what was
really written.</p>
<p class="verdict">{passed} of {len(all_checks)} checks pass.</p>
<div role="tablist">{tabs}</div>{panels}
<h2>Harder layouts (the repo's extraction fixtures)</h2>{check_table(extra)}
<script>
const tabs = [...document.querySelectorAll('[role=tab]')];
function show(id) {{
  for (const t of tabs) t.setAttribute('aria-selected', t.dataset.tab === id);
  for (const p of document.querySelectorAll('[role=tabpanel]')) p.hidden = p.id !== id;
}}
tabs.forEach(t => t.onclick = () => show(t.dataset.tab));
show(tabs[tabs.length - 1].dataset.tab);
for (const el of document.querySelectorAll('embed[data-pdf]')) {{
  const bytes = Uint8Array.from(atob(el.dataset.pdf), c => c.charCodeAt(0));
  el.src = URL.createObjectURL(new Blob([bytes], {{type: 'application/pdf'}}));
}}
</script></main></body></html>"""


LABELS = {"drawn": "Drawn by script", "word": "Exported from Word"}

if __name__ == "__main__":
    cases = [run_case("drawn", drawn)]
    if word_available():
        cases.append(run_case("word", word))
    else:
        print("Word not available: the 'Exported from Word' source is skipped.")
    extra = fixture_checks()
    (OUT / "report.html").write_text(report(cases, extra), encoding="utf-8")
    for x in cases:
        print(f"\n== {LABELS[x['source']]}")
        for g, w, p, d in x["checks"]:
            print(("PASS" if p else "FAIL"), f"[{g}]", w, "--", d)
    print("\n== Harder layouts")
    for g, w, p, d in extra:
        print(("PASS" if p else "FAIL"), w, "--", d)
    print(f"\nReport: {OUT / 'report.html'}")
