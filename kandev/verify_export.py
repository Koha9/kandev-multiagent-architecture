"""Export the three deployed workflows, print a compact per-step summary for verification,
and save a shareable copy under export/ with every workspace-specific ID replaced by a placeholder.

Usage (from kandev/): python verify_export.py [--ids kandev_ids.json] [--out export] [--url URL]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_workflows import DEFAULT_URL, W1_NAME, W2_NAME, W3_NAME, Kandev  # noqa: E402

FILES = {W1_NAME: ("W1-project.json", "W1"), W2_NAME: ("W2-module.json", "W2"), W3_NAME: ("W3-dev.json", "W3")}
# Same names as the placeholders in docs/prompts.md (build_workflows.py dump)
NAMED = {("W3", "开发"): "<W3_DEV_STEP_ID>", ("W3", "待开发"): "<W3_HOLD_STEP_ID>",
         ("W2", "模块规划"): "<W2_PLAN_STEP_ID>"}


def placeholders(ids):
    """Map every local ID in kandev_ids.json to a stable placeholder."""
    out = {}
    ws = ids.get("_meta", {}).get("workspace_id")
    if ws:
        out[ws] = "<WORKSPACE_ID>"
    for wname, info in ids.items():
        if wname.startswith("_") or wname not in FILES:
            continue
        tag = FILES[wname][1]
        out[info["workflow_id"]] = f"<{tag}_ID>"
        for sname, sid in info["steps"].items():
            out[sid] = NAMED.get((tag, sname), f"<{tag}_STEP_ID:{sname}>")
    return out


def sanitize(obj, repl):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    for real, ph in repl.items():
        text = text.replace(real, ph)
    return text + "\n"


def summary(doc):
    for s in doc["workflows"][0]["steps"]:
        prof = s.get("agent_profile")
        prof = f"{prof.get('model')}/{prof.get('mode')}" if prof else "-"
        ev = {k2: [e["type"] + (str(e.get("config")) if e.get("config") else "") for e in v]
              for k2, v in (s.get("events") or {}).items()}
        p = s.get("prompt") or ""
        print(f" {s['position']} {s['name']:<6} start={s['is_start_step']} sig={s['auto_advance_requires_signal']} "
              f"wip={s.get('wip_limit', 0)} pol={s['profile_session_start_policy']}/{s['profile_session_end_policy']} "
              f"prof={prof} tgt={s.get('session_target')} done={s['complete_task_on_enter']}")
        print(f"     events={ev}")
        if p:
            print(f"     prompt: {len(p)} chars, has{{task_id}}={'{task_id}' in p}, "
                  f"has{{{{task_prompt}}}}={'{{task_prompt}}' in p}, step_entry={'{step_entry_number}' in p}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default=os.path.join(here, "kandev_ids.json"))
    ap.add_argument("--out", default=os.path.join(here, "export"))
    ap.add_argument("--url", default=DEFAULT_URL)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    ids = json.load(open(a.ids, encoding="utf-8"))
    repl = placeholders(ids)
    os.makedirs(a.out, exist_ok=True)
    k = Kandev(a.url)
    for wname, info in ids.items():
        if wname.startswith("_") or wname not in FILES:
            continue
        doc = k.call("export_workflow_kandev", {"workflow_id": info["workflow_id"]})
        fname = os.path.join(a.out, FILES[wname][0])
        with open(fname, "w", encoding="utf-8") as f:
            f.write(sanitize(doc, repl))
        print(f"== {wname}  (version {doc.get('version')}) -> {os.path.relpath(fname, here)}")
        summary(doc)


if __name__ == "__main__":
    main()
