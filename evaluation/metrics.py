"""Collect per-task timing / rework metrics for a pilot or benchmark run (one JSON line per task).

Usage: python evaluation/metrics.py [--ids kandev/kandev_ids.json] [--profiles kandev/profiles.local.json]
For an archived pilot, pass that pilot's ids file via --ids. Review / merge counts come from sessions run by the
reviewer / mechanical profiles.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KANDEV = os.path.join(HERE, "..", "kandev")
sys.path.insert(0, KANDEV)
from build_workflows import Kandev  # noqa: E402
from stage import ts  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--ids", default=os.path.join(KANDEV, "kandev_ids.json"))
p.add_argument("--profiles", default=os.path.join(KANDEV, "profiles.local.json"))
a = p.parse_args()

sys.stdout.reconfigure(encoding="utf-8")
ids = json.load(open(a.ids, encoding="utf-8"))
profiles = json.load(open(a.profiles, encoding="utf-8"))
REVIEWER, MERGER = profiles["reviewer"], profiles["mechanical"]
k = Kandev()
rows = []
for wname, info in ((n, i) for n, i in ids.items() if not n.startswith("_")):
    names = {v: n for n, v in info["steps"].items()}
    for t in k.call("list_tasks_kandev", {"workflow_id": info["workflow_id"]}).get("tasks", []):
        sess = k.call("list_task_sessions_kandev", {"task_id": t["id"]}).get("sessions", [])
        c, u = ts(t["created_at"]), ts(t["updated_at"])
        starts = [ts(s["started_at"]) for s in sess if s.get("started_at")]
        first = min(starts) if starts else None
        rows.append({
            "wf": wname.split("· ")[-1], "title": t["title"], "step": names.get(t["workflow_step_id"], "?"),
            "state": t["state"],
            "created": c.astimezone().strftime("%H:%M"), "first_start": first.astimezone().strftime("%H:%M") if first else "-",
            "last_update": u.astimezone().strftime("%H:%M"),
            "wait_min": int((first - c).total_seconds() // 60) if first else None,
            "span_min": int((u - (first or c)).total_seconds() // 60),
            "sessions": len(sess),
            "reviews": sum(1 for s in sess if s["agent_profile_id"] == REVIEWER),
            "merges": sum(1 for s in sess if s["agent_profile_id"] == MERGER),
        })
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
