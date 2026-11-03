"""Read and refresh committed module timings from pytest JUnit XML (IR-854)."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def load_timings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("timings must map module paths to seconds")
    for module, seconds in data.items():
        if (not module.startswith("apps/") or not module.endswith(".py")
                or ".." in module.split("/") or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds < 0):
            raise ValueError(f"invalid module duration: {module}")
    return data


def from_junit(paths):
    durations = defaultdict(float)
    seen = set()
    for path in paths:
        for case in ET.parse(path).iter("testcase"):
            classname = case.get("classname", "")
            parts = classname.split(".")
            # JUnit classname includes the class after the test module.
            candidates = [i for i, part in enumerate(parts) if part.startswith("test_") or part == "tests"]
            if not candidates:
                raise ValueError(f"cannot identify test module: {classname}")
            module = "/".join(parts[:candidates[-1] + 1]) + ".py"
            identity = (classname, case.get("name"))
            if identity in seen:
                raise ValueError(f"duplicate testcase across reports: {identity}")
            seen.add(identity)
            seconds = float(case.get("time", "0"))
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError(f"invalid JUnit duration: {identity}")
            durations[module] += seconds
    if not durations:
        raise ValueError("no testcases in reports")
    return {module: round(seconds, 6) for module, seconds in sorted(durations.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("module_durations.json"))
    args = parser.parse_args()
    try:
        durations = from_junit(args.reports)
        args.output.write_text(json.dumps(durations, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ValueError, OSError, ET.ParseError, DefusedXmlException) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
