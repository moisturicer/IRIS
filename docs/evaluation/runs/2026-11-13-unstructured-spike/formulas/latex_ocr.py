"""Ask vision models for exact LaTeX of each formula crop, via OpenRouter."""
import base64, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
KEY = os.environ["OPENROUTER_API_KEY"]
PROMPT = ("Transcribe the display equation in this image into LaTeX, exactly as typeset. "
          r"Output only the LaTeX body, with no $ or \[ delimiters and no explanation. "
          r"Keep the equation number as \tag{n} if one is printed. Ignore any partial prose lines cut off at the edges.")
models, root = sys.argv[1].split(","), Path(sys.argv[2])
jobs = [(m, d, item) for m in models for d in sorted(root.iterdir()) if d.is_dir()
        for item in json.load(open(d / "index.json", encoding="utf-8"))]
def call(job):
    m, d, item = job
    img = base64.b64encode((d / item["file"]).read_bytes()).decode()
    body = {"model": m, "temperature": 0, "max_tokens": 1500, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}]}]}
    t = time.monotonic()
    for attempt in range(3):
        try:
            r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=120,
                           headers={"Authorization": f"Bearer {KEY}"})
            j = r.json(); text = j["choices"][0]["message"]["content"].strip()
            return {"model": m, "paper": d.name, "file": item["file"], "latex": text,
                    "cost": (j.get("usage") or {}).get("cost"), "seconds": round(time.monotonic() - t, 1)}
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]} {r.text[:200] if 'r' in locals() else ''}"
    return {"model": m, "paper": d.name, "file": item["file"], "error": err}
with ThreadPoolExecutor(8) as ex:
    rows = list(ex.map(call, jobs))
json.dump(rows, open(root / "latex.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
for m in models:
    mine = [r for r in rows if r["model"] == m]
    print(m, "ok", sum("latex" in r for r in mine), "/", len(mine), "cost $", round(sum(r.get("cost") or 0 for r in mine), 4))
