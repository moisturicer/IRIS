"""Allowlisted reader state shared by live, reopened and exported runs (IR-730)."""

from ai.agent.tools import PLAN_STEPS, STEP_ID, STEP_STATUS

PROTOCOL = "runs-reader-1"


def progress(events):
    plan = None
    context = None
    compaction = None
    for event in events:
        data = event["data"]
        if event["name"] == "plan":
            revision, steps = data.get("revision"), data.get("steps")
            if (type(revision) is not int or revision < 1 or
                    (plan and revision <= plan["revision"]) or
                    not isinstance(steps, list) or len(steps) > PLAN_STEPS):
                continue
            clean = []
            for step in steps:
                if (not isinstance(step, dict) or not isinstance(step.get("id"), str) or
                        not STEP_ID.fullmatch(step["id"]) or step.get("status") not in STEP_STATUS or
                        not isinstance(step.get("title"), str) or not step["title"].strip() or
                        len(step["title"]) > 160):
                    break
                clean.append({key: step[key] for key in ("id", "title", "status")})
            else:
                ids = [s["id"] for s in clean]
                previous = {s["id"] for s in plan["steps"]} if plan else set()
                if len(set(ids)) == len(ids) and previous <= set(ids):
                    plan = {"revision": revision, "steps": clean}
        elif event["name"] == "compaction":
            # Outcome and counts only: never a reason code, summary text, revision or source.
            turns = data.get("turns")
            if data.get("outcome") not in ("compacted", "kept") or (
                    data["outcome"] == "compacted" and (type(turns) is not int or turns < 0)):
                continue
            compaction = compaction or {"compactions": 0, "turns_compacted": 0, "last": None}
            compaction["last"] = data["outcome"]
            if data["outcome"] == "compacted":
                compaction["compactions"] += 1
                compaction["turns_compacted"] += turns
        elif event["name"] == "context":
            used, capacity = data.get("used_tokens"), data.get("capacity_tokens")
            context = ({"estimated": True, "used_tokens": used, "capacity_tokens": capacity}
                       if type(used) is int and type(capacity) is int and 0 <= used <= capacity
                       and capacity > 0 else None)
    return {"plan": plan, "context": context, "compaction": compaction}


def run(snapshot):
    return {
        "protocol": PROTOCOL,
        **{key: snapshot[key] for key in (
            "id", "conversation_id", "state", "question", "base_revision", "version",
            "turn_id", "depth", "awaiting_reader", "created_at", "finished_at",
        )},
        **progress(snapshot["events"] if snapshot.get("sources_available", True) else []),
        "sources_available": snapshot.get("sources_available", True),
        "capabilities": {"manual_compaction": False},
    }


def conversation(snapshot):
    available = {item["id"]: item.get("sources_available", True) for item in snapshot["runs"]}
    return {
        "protocol": PROTOCOL, "id": snapshot["id"], "revision": snapshot["revision"],
        "runs": [run(item) for item in snapshot["runs"]],
        "turns": [{**{key: turn[key] for key in (
            "id", "run_id", "ordinal", "question", "answer", "kind", "created_at", "citations",
        )}, "facts": turn.get("facts", []),
            **({} if available[turn["run_id"]] else {
                "answer": "This answer is unavailable because its sources changed or are no longer readable.",
                "citations": [], "facts": [],
            })} for turn in snapshot["turns"]],
    }
