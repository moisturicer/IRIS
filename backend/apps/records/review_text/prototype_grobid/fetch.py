"""PROTOTYPE, throwaway, never merge. Send each split paper to a local GROBID.

    python -I fetch.py <folder of sample PDFs> [--url http://127.0.0.1:8070]

One paper at a time. Writes out/tei/<name>.xml and out/fetch.json (seconds
and the container's peak memory per paper, counts only). Every request turns
consolidation off, so no reference metadata is sent to Crossref or anywhere.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CONTAINER = "grobid-proto"

FORM = {
    "consolidateHeader": "0",
    "consolidateCitations": "0",
    "consolidateFunders": "0",
    "segmentSentences": "1",
    "includeRawCitations": "1",
    "teiCoordinates": ["head", "s", "biblStruct", "figure"],
}


def _mib(text):
    value = text.split("/")[0].strip()
    for unit, scale in (("GiB", 1024), ("MiB", 1), ("KiB", 1 / 1024), ("B", 1 / 2**20)):
        if value.endswith(unit):
            return float(value[: -len(unit)]) * scale
    return 0.0


class Peak:
    """The container's peak memory while a request runs, from `docker stats`."""

    def __init__(self):
        self.peak, self._stop = 0.0, threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", CONTAINER],
                               capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                self.peak = max(self.peak, _mib(r.stdout))

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()


def main(folder, url="http://127.0.0.1:8070"):
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    names = split["tuning"] + split["held_out"]
    (OUT / "tei").mkdir(parents=True, exist_ok=True)
    log_path = OUT / "fetch.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    with httpx.Client(timeout=900) as client:
        for name in names:
            target = OUT / "tei" / (name + ".xml")
            if target.exists() and name in log:
                continue
            pdf = Path(folder) / name
            if not pdf.exists():
                print(f"{name:18} missing, skipped", flush=True)
                continue
            with Peak() as peak:
                start = time.time()
                with pdf.open("rb") as f:
                    r = client.post(f"{url}/api/processFulltextDocument", data=FORM,
                                    files={"input": (name, f, "application/pdf")})
                seconds = time.time() - start
            row = {"status": r.status_code, "seconds": round(seconds, 1), "peak_mib": round(peak.peak)}
            if r.status_code == 200:
                target.write_bytes(r.content)
            log[name] = row
            log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
            print(f"{name:18} {row}", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    url = args[args.index("--url") + 1] if "--url" in args else "http://127.0.0.1:8070"
    main(args[0], url)
