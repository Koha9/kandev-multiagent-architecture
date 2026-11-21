"""多 agent workflow 的部署逻辑：把 prompts.py 里定义的三套 workflow 部署到 Kandev，或把全部 prompt 导出成 Markdown。

本文件负责：导入 / 就地更新 workflow、按 ID 绑定步骤 profile、同步步骤结构、写 ids 文件（apply），生成 docs/prompts.md（dump），
打印每个步骤的长度和携带的共享块（stats）。prompt 正文、步骤结构和 VERSION 都在 prompts.py；这里把它的名字原样转出，
其他脚本照旧 `import build_workflows`。

Builds three workflows (项目管理 / 模块管理 / 开发) in any Kandev workspace through the external MCP
endpoint, binds step profiles by ID, and can dump all prompts + step config to Markdown.

Usage:
  python build_workflows.py dump   --out ../docs/prompts.md
  python build_workflows.py stats                       每个步骤的 prompt 长度和携带的共享块（只打印）
  python build_workflows.py apply  --workspace <id> --profiles profiles.json [--retire-existing] [--url URL]
Deploy through ma.py (ma.py apply): it shows the diff first, checks for running projects and records what was
deployed. `apply` here is the import step it calls; run directly it only checks that the answers exist.
Re-running apply on workflows of the same series (same major.minor, e.g. v3.3 and v3.3.1) updates them in place:
prompts, profiles, description and step structure (order, events, flags); step IDs and resident tasks are kept.
Workflows of another series need --retire-existing: they are renamed
"<name> (<old version>)", e.g. "(v3.1)"; "(旧)" when the old description carries no version.
With several workspaces, pass --ids-out so each workspace keeps its own ids file (the guard reads it via --ids).

profiles.json maps roles to Kandev agent profile IDs (see profiles.example.json):
  required: {"pm": "...", "auditor": "...", "developer": "...", "reviewer": "...", "mechanical": "..."}
  optional: "module" (default = pm), "module_auditor" (default = auditor), "plan_auditor" (default = auditor),
            "intake" (default = mechanical; W1 step 0 接收, a light model is enough)

Import matches profiles by name/model/mode, which is ambiguous when several similar profiles exist,
so workflows are imported without profiles and profiles are bound afterwards by ID.
Workflows reference each other's step IDs in prompts, so the import order is W3 -> W2 -> W1.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kandev_client import DEFAULT_URL, Kandev  # noqa: E402,F401
from manifest import OPTIONAL_ROLES, REQUIRED_ROLES, full_profiles  # noqa: E402,F401
import prompts  # noqa: E402
from prompts import *  # noqa: E402,F401,F403  其他脚本通过本模块使用的名字（VERSION、W1_NAME、guard_prompt、all_workflows……）
from prompts import (ARCH_PLACEHOLDER, GUARD_AUTOMATION, GUARD_PROMPT, VERSION, W1_NAME, W2_NAME, W3_NAME,  # noqa: E402,F401
                     all_workflows, arch_root, guard_prompt, structure_problems, w1, w2, w3)


# ================================================================== build / apply
def clean(wf):
    return {**wf, "steps": [{k: v for k, v in s.items() if not k.startswith("_")} for s in wf["steps"]]}


def list_steps(k, wid):
    steps = k.call("list_workflow_steps_kandev", {"workflow_id": wid})
    steps = steps.get("steps", steps) if isinstance(steps, dict) else steps
    return {s["name"]: s["id"] for s in steps}


def find_workflow(k, ws, name):
    return next((w for w in k.call("list_workflows_kandev", {"workspace_id": ws})["workflows"] if w["name"] == name), None)


def series(version):
    """v3.3.1 -> v3.3：同一系列（major.minor 相同）的 workflow 可以就地更新。"""
    return ".".join(version.split(".")[:2])


def desc_version(desc):
    m = re.search(r"\[(v[\d.]+)\]", desc or "")
    return m.group(1) if m else None


def import_one(k, ws, wf, retire):
    existing = find_workflow(k, ws, wf["name"])
    old_ver = desc_version(existing.get("description")) if existing else None
    if existing and not (old_ver and series(old_ver) == series(VERSION)):
        if not retire:
            raise SystemExit(f"'{wf['name']}' exists but is not {series(VERSION)}.x; rerun with --retire-existing to rename it.")
        old = f"{wf['name']} ({old_ver or '旧'})"   # 带旧版本号，避免与更早的"(旧)"重名
        k.call("update_workflow_kandev", {"workflow_id": existing["id"], "name": old})
        print(f"retired: {wf['name']} -> {old}")
        existing = None
    if existing:
        print(f"exists ({old_ver}), update in place:", wf["name"])
        if existing.get("description") != wf["description"]:
            k.call("update_workflow_kandev", {"workflow_id": existing["id"], "description": wf["description"]})
        return existing["id"], list_steps(k, existing["id"])
    doc = {"type": "kandev_workflow", "version": 2, "workflows": [clean(wf)]}
    res = k.call("import_workflow_kandev", {"workspace_id": ws, "document": json.dumps(doc, ensure_ascii=False)})
    print("import", wf["name"], "->", res)
    wid = find_workflow(k, ws, wf["name"])["id"]
    return wid, list_steps(k, wid)


def bind(k, wf, steps_by_name, profiles, sync_prompts=False):
    for s in wf["steps"]:
        args = {"step_id": steps_by_name[s["name"]]}
        if s["_role"] and profiles:
            args["agent_profile_id"] = profiles[s["_role"]]
        if sync_prompts and s.get("prompt"):
            args["prompt"] = s["prompt"]
        if len(args) > 1:
            k.call("update_workflow_step_kandev", args)
            print("updated", wf["name"], s["name"], "profile=" + str(s["_role"]), "prompt" if "prompt" in args else "")


STRUCT_FIELDS = ("events", "complete_task_on_enter", "auto_advance_requires_signal", "is_start_step",
                 "profile_session_start_policy", "profile_session_end_policy", "show_in_command_panel", "wip_limit")


def fetch_steps(k, wid):
    steps = k.call("list_workflow_steps_kandev", {"workflow_id": wid})
    steps = steps.get("steps", steps) if isinstance(steps, dict) else steps
    return sorted(steps, key=lambda s: s["position"])


def structure_diff(k, wf, wid):
    """已部署的 workflow 与脚本在步骤顺序和结构字段上的差异（只读）。
    返回 ([(步骤名, 步骤 id, {字段: 脚本里的值})], 脚本顺序的步骤 id 列表, 顺序是否不同)。步骤名集合不同时无法就地更新。"""
    want = sorted(wf["steps"], key=lambda s: s["position"])
    cur = {s["name"]: s for s in fetch_steps(k, wid)}
    if set(cur) != {s["name"] for s in want}:
        raise SystemExit(f"'{wf['name']}': deployed steps {sorted(cur)} differ from the script; "
                         "cannot update in place, retire it and import again (ma.py apply --retire).")
    # Kandev 存的 move_to_step 目标是步骤 ID（导入时由 step_position 换算），就地更新时要自己换算
    id_at = {s["position"]: cur[s["name"]]["id"] for s in want}
    want = [{**s, "events": {ev: [{"type": a["type"], "config": {"step_id": id_at[a["config"]["step_position"]]}}
                                  if a["type"] == "move_to_step" else a for a in actions]
                             for ev, actions in s["events"].items()}} for s in want]
    diffs = []
    for s in want:
        c = cur[s["name"]]
        diff = {f: s.get(f, 0 if f == "wip_limit" else None) for f in STRUCT_FIELDS
                if (c.get(f) or None) != (s.get(f) or None)}
        if diff:
            diffs.append((s["name"], c["id"], diff))
    order = [cur[s["name"]]["id"] for s in want]
    reordered = [c["id"] for c in sorted(cur.values(), key=lambda c: c["position"])] != order
    return diffs, order, reordered


def sync_structure(k, wf, wid):
    """把已部署 workflow 的步骤顺序和结构字段改成脚本里的样子（步骤 ID 和步骤里的任务不变）。
    只发送有差异的字段；新导入的 workflow 上没有差异，相当于一次核对。"""
    diffs, order, reordered = structure_diff(k, wf, wid)
    for name, sid, diff in diffs:
        k.call("update_workflow_step_kandev", {"step_id": sid, **diff})
        print("structure", wf["name"], name, sorted(diff))
    if reordered:
        k.call("reorder_workflow_steps_kandev", {"workflow_id": wid, "step_ids": order})
        print("reordered", wf["name"])
    diffs, _, reordered = structure_diff(k, wf, wid)
    if diffs or reordered:
        raise SystemExit(f"'{wf['name']}': structure still differs after sync: "
                         f"{[(n, sorted(d)) for n, _, d in diffs]} reordered={reordered}")


def cmd_apply(a):
    profiles = json.load(open(a.profiles, encoding="utf-8")) if a.profiles else None
    if profiles:
        missing = set(REQUIRED_ROLES) - set(profiles)
        if missing:
            raise SystemExit(f"profiles.json missing roles: {sorted(missing)}")
        profiles = full_profiles(profiles)
    problems = [p for wf in all_workflows() for p in structure_problems(wf)]
    if problems:
        raise SystemExit("\n".join(problems))
    import manifest   # 提问清单的必问项没有答案时拒绝部署（答案由 ma.py install 记录）
    missing = manifest.missing_answers(arch_root(), a.workspace)
    if missing:
        raise SystemExit("部署前必须先向用户确认这些事项（python kandev/ma.py questions --stage install，"
                         "答案交给 python kandev/ma.py install --answers <文件>）：\n  " + "\n  ".join(missing))
    k = Kandev(a.url, version=VERSION)
    out = {}
    wf3 = w3()
    id3, st3 = import_one(k, a.workspace, wf3, a.retire_existing)
    sync_structure(k, wf3, id3)
    bind(k, wf3, st3, profiles, sync_prompts=True)
    wf2 = w2(id3, st3["开发"], st3["待开发"])
    id2, st2 = import_one(k, a.workspace, wf2, a.retire_existing)
    sync_structure(k, wf2, id2)
    bind(k, wf2, st2, profiles, sync_prompts=True)
    wf1 = w1(id2, st2["模块规划"], arch_root())
    id1, st1 = import_one(k, a.workspace, wf1, a.retire_existing)
    sync_structure(k, wf1, id1)
    bind(k, wf1, st1, profiles, sync_prompts=True)
    for name, wid, st in ((W1_NAME, id1, st1), (W2_NAME, id2, st2), (W3_NAME, id3, st3)):
        out[name] = {"workflow_id": wid, "steps": st}
    out["_meta"] = {"version": VERSION, "workspace_id": a.workspace, "arch_root": arch_root(), "url": a.url}
    with open(a.ids_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"ids written to {a.ids_out}")


def cmd_dump(a):
    wfs = all_workflows()
    lines = [
        f"# 各步骤 Prompt 与配置（{VERSION}）", "",
        "> 本文件由 `kandev/build_workflows.py dump` 生成，不要手改；修改请改脚本后重新生成。",
        "> 跨 workflow 的 ID 以占位符显示（`<W2_ID>` 等），部署时自动填入实际 ID；`<ARCH_ROOT>` 填入安装目录（链接模式下是本仓库）的绝对路径。", "",
        "Kandev 变量：`{task_id}`、`{task_title}`、`{step_entry_number}`（第几次进入本步骤）、`{{task_prompt}}`（任务描述）。",
        "公共头部内嵌在每个步骤的 prompt 中（不使用 Kandev 的 workflow 级 prompt 和共享 prompt，原因见 docs/workflow.md）。", "",
    ]
    for wf in reversed(wfs):
        lines += [f"## {wf['name']}", "", wf["description"], "",
                  "| # | 步骤 | 角色（profile） | 会话 | 事件 | 完成信号 | 说明 |", "|---|---|---|---|---|---|---|"]
        for s in wf["steps"]:
            ev = "; ".join(f"{k}: " + ", ".join(e["type"] + (f"→#{e['config']['step_position']}" if e.get("config") else "")
                                                for e in v) for k, v in s["events"].items()) or "—"
            sess = f"{s['profile_session_start_policy']}/{s['profile_session_end_policy']}" if s["_role"] else "—"
            extra = f"WIP {s['wip_limit']}" if s.get("wip_limit") else ""
            lines.append(f"| {s['position']} | {s['name']} | {s['_role'] or '—'} | {sess} | {ev} | "
                         f"{'是' if s['auto_advance_requires_signal'] else '否'} | {' '.join(x for x in (s['_note'], extra) if x)} |")
        lines.append("")
        for s in wf["steps"]:
            if s.get("prompt"):
                lines += [f"### {wf['name']} · {s['name']}", "", "```text", s["prompt"], "```", ""]
    g = GUARD_AUTOMATION
    lines += ["## 守护 automation", "",
              f"每个 workspace 只建一次，覆盖所有项目，新项目不需要任何配置。外部 MCP 不能创建 automation：交给 Kandev 内部的配置 agent "
              f"用 `create_automation_kandev` 创建（`ma.py apply` 会生成填好本机取值的交接文件和 prompt 正文，见 `kandev/handoff/`），或在 Kandev 设置 → "
              f"Automations 手动创建。配置：trigger={g['trigger']}"
              f"（cron `{g['cron']}`），task mode={g['task_mode']}，profile={g['profile']}，max concurrent runs={g['max_concurrent_runs']}。"
              "prompt 如下（`<arch_root>`、`<python>` 由 `ma.py` 填入本机取值）：", "",
              "```text", GUARD_PROMPT, "```", ""]
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {a.out}")


def cmd_stats(a):
    """每个步骤的 prompt 长度和它携带的共享块；再列出每个共享块的长度和被多少个步骤携带。只打印，不写进 docs/prompts.md。"""
    used, total = {}, 0
    print("| workflow · 步骤 | 角色 | 字符数 | 头部 | 头部携带的共享块 | 步骤模板里的共享块 |")
    print("|---|---|---|---|---|---|")
    for wf in reversed(all_workflows()):
        for s in wf["steps"]:
            if not s.get("prompt"):
                continue
            head, in_head, in_step = prompts.carried(wf["name"], s["name"])
            for b in in_head + in_step:
                used[b] = used.get(b, 0) + 1
            total += len(s["prompt"])
            print(f"| {wf['name']} · {s['name']} | {s['_role']} | {len(s['prompt'])} | {head or '—'} | "
                  f"{', '.join(in_head) or '—'} | {', '.join(in_step) or '—'} |")
    print(f"| 守护 automation | guard | {len(GUARD_PROMPT)} | — | — | — |")
    print(f"\n步骤 prompt 合计 {total} 字符（ID 和安装目录以占位符计）。\n")
    print("| 共享块 | 字符数 | 携带它的步骤数 |")
    print("|---|---|---|")
    texts = {**prompts.BLOCKS, **prompts.PARAM_BLOCKS}     # PARAM_BLOCKS 是填入 ID 之前的模板，长度略有出入
    for b in sorted(used, key=lambda b: -len(texts[b]) * used[b]):
        print(f"| {b} | {len(texts[b])} | {used[b]} |")
    unused = sorted(b for b in texts if b not in used and b not in prompts.HEADER_BLOCKS)
    if unused:
        print(f"\n没有任何步骤携带的共享块：{unused}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("apply")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--retire-existing", action="store_true")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--ids-out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "kandev_ids.json"))
    dp = sub.add_parser("dump")
    dp.add_argument("--out", required=True)
    sub.add_parser("stats")
    a = p.parse_args()
    {"apply": cmd_apply, "dump": cmd_dump, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    main()
