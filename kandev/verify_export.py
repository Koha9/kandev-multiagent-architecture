"""Export the three workflows, save them, and print a compact per-step summary for verification."""
import json
import sys

sys.path.insert(0, ".")
from build_workflows import Kandev  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ids = json.load(open("kandev_ids.json", encoding="utf-8"))
k = Kandev()
for wname, info in ((n, i) for n, i in ids.items() if not n.startswith("_")):
    doc = k.call("export_workflow_kandev", {"workflow_id": info["workflow_id"]})
    fname = {"多Agent · 项目管理": "W1-project.json", "多Agent · 模块管理": "W2-module.json",
             "多Agent · 开发": "W3-dev.json"}[wname]
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"== {wname}  (version {doc.get('version')}) -> {fname}")
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
