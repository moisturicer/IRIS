"""THROWAWAY (IR-462): native tool call vs structured route label, on the configured model.

Reads LLM_BASE_URL / LLM_MODEL / LLM_API_KEY / LLM_TEMPERATURE from the
environment (load backend/.env first). Buffered, never streamed. Writes raw
per-call records to --out so the write-up can be re-derived without a vendor.

    python scripts/spikes/ir462_route_spike.py --out docs/evaluation/spikes/ir462_runs.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

SYSTEM_BASE = (
    "You are Ask IRIS, the assistant of a university research repository of "
    "theses and papers. Some questions can only be answered from passages in "
    "the repository; others (greetings, thanks, questions about you, "
    "rewriting your previous answer, general knowledge unrelated to the "
    "repository) need no passages."
)
SYSTEM_TOOL = (
    SYSTEM_BASE
    + " If the question needs passages from the repository, call the "
    "search_corpus tool. Otherwise reply directly in prose and do not call it."
)
SYSTEM_ROUTE = (
    SYSTEM_BASE
    + ' Decide whether the question needs passages from the repository. '
    'Reply with exactly one JSON object and nothing else: {"route": "search"} '
    'if it needs passages, or {"route": "answer"} if it does not.'
)
TOOL = {
    "type": "function",
    "function": {
        "name": "search_corpus",
        "description": "Search the repository for passages relevant to the user's question.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def messages(system: str, item: dict) -> list[dict]:
    out = [{"role": "system", "content": system}]
    h = item.get("history")
    if h:
        out += [
            {"role": "user", "content": h["user"]},
            {"role": "assistant", "content": h["assistant"]},
        ]
    out.append({"role": "user", "content": item["q"]})
    return out


def call(client: httpx.Client, body: dict, timeout: float) -> dict:
    """One buffered request. Returns {'ok', 'latency', 'msg'|'error'}."""
    for attempt in range(6):
        t0 = time.perf_counter()
        try:
            r = client.post("/chat/completions", json=body, timeout=timeout)
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout", "latency": time.perf_counter() - t0}
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"transport:{type(e).__name__}", "latency": time.perf_counter() - t0}
        lat = time.perf_counter() - t0
        if r.status_code == 429:
            time.sleep(min(2 ** attempt, 20))
            continue
        if r.status_code != 200:
            return {"ok": False, "error": f"http{r.status_code}", "detail": r.text[:300], "latency": lat}
        d = r.json()
        return {"ok": True, "latency": lat, "msg": d["choices"][0]["message"], "usage": d.get("usage", {})}
    return {"ok": False, "error": "rate_limited", "latency": 0.0}


def classify_tool(res: dict) -> dict:
    if not res["ok"]:
        # Groq reports a model-generated malformed call as 400 tool_use_failed
        err = "malformed" if "tool_use_failed" in res.get("detail", "") else res["error"]
        return {"decision": None, "failure": err}
    msg = res["msg"]
    calls = msg.get("tool_calls") or []
    text = (msg.get("content") or "").strip()
    if not calls:
        if not text:
            return {"decision": None, "failure": "empty"}
        return {"decision": "answer", "failure": None}
    failure = None
    if len(calls) > 1:
        failure = "several_calls"
    elif text:
        failure = "text_and_call"
    for c in calls:
        raw = (c.get("function") or {}).get("arguments") or ""
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {"decision": None, "failure": "malformed", "example": raw[:200]}
        if args:
            failure = failure or "args_supplied"
            res["example"] = raw[:200]
        if (c.get("function") or {}).get("name") != "search_corpus":
            return {"decision": None, "failure": "wrong_tool", "example": str(c)[:200]}
    out = {"decision": "search", "failure": failure}
    if res.get("example"):
        out["example"] = res["example"]
    return out


def classify_route(res: dict) -> dict:
    if not res["ok"]:
        return {"decision": None, "failure": res["error"]}
    text = (res["msg"].get("content") or "").strip()
    if not text:
        return {"decision": None, "failure": "empty"}
    try:
        obj = json.loads(text)
        wrapped = False
    except json.JSONDecodeError:
        m = re.search(r"\{.*?\}", text, re.S)
        try:
            obj = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            obj = None
        wrapped = True
    if not isinstance(obj, dict) or obj.get("route") not in ("search", "answer"):
        return {"decision": None, "failure": "malformed", "example": text[:200]}
    out = {"decision": obj["route"], "failure": "wrapped" if wrapped else None}
    if wrapped:
        out["example"] = text[:200]
    return out


def one(client, cfg, mech, effort, item, run):
    system = SYSTEM_TOOL if mech == "tool" else SYSTEM_ROUTE
    body = {
        "model": cfg["model"],
        "messages": messages(system, item),
        "temperature": cfg["temperature"],
        "max_completion_tokens": 2000,
    }
    if mech == "tool":
        body["tools"] = [TOOL]
        body["tool_choice"] = "auto"
    body["reasoning_effort"] = effort
    body["include_reasoning"] = False
    res = call(client, body, cfg["timeout"])
    c = (classify_tool if mech == "tool" else classify_route)(res)
    return {
        "mech": mech, "effort": effort, "run": run, "id": item["id"],
        "kind": item["kind"], "label": item["label"], "latency": round(res["latency"], 3),
        "reasoning_tokens": (res.get("usage", {}).get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "completion_tokens": res.get("usage", {}).get("completion_tokens"),
        **c,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="docs/evaluation/spikes/ir462_questions.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--efforts", default="medium,low")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--env-file", default="")
    a = ap.parse_args()

    if a.env_file:
        for line in open(a.env_file, encoding="utf-8"):
            k, sep, v = line.strip().partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

    cfg = {
        "model": os.environ["LLM_MODEL"],
        "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.5")),
        "timeout": a.timeout,
    }
    items = json.load(open(a.questions, encoding="utf-8"))["questions"]
    if a.limit:
        items = items[: a.limit]
    client = httpx.Client(
        base_url=os.environ["LLM_BASE_URL"].rstrip("/"),
        headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
    )
    jobs = [
        (m, e, it, r)
        for r in range(1, a.runs + 1)
        for e in a.efforts.split(",")
        for m in ("tool", "route")
        for it in items
    ]
    print(f"{len(jobs)} calls, model={cfg['model']} temp={cfg['temperature']}", file=sys.stderr)
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda j: one(client, cfg, j[0], j[1], j[2], j[3]), jobs))
    json.dump({"config": cfg, "rows": rows}, open(a.out, "w", encoding="utf-8"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
