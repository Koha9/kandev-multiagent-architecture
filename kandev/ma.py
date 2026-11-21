"""多 Agent workflow 的安装、部署、检查和升级入口（只用标准库）。给 AI 的操作步骤见 AGENTS.md。

  python kandev/ma.py questions [--stage install|customize|redeploy|upgrade]   部署前必须向用户确认的事项
  python kandev/ma.py install --answers answers.json    记录答案；独立安装时把运行所需的文件复制到安装目录
  python <home>/kandev/ma.py diff                        已部署的 prompt 与本目录将要部署的 prompt 的差异
  python <home>/kandev/ma.py apply [--confirmed <值>]    部署到 Kandev（自检 → 导入 / 就地更新 → 生成守护交接文件 → 导出）
  python <home>/kandev/ma.py guard                       重新生成填好本机取值的守护交接文件
  python <home>/kandev/ma.py doctor [--offline]          检查安装目录、已部署的 workflow 和守护是否一致
  python kandev/ma.py upgrade --home <home>              在新版源仓库中运行：把安装目录升级到这个版本
  python <home>/kandev/ma.py answer --set key=value      改动已记录的答案（先问过用户）

<home> 是安装目录；链接模式下就是本仓库。ma.py 不删除任何东西。
"""
import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE).replace("\\", "/")
sys.path.insert(0, HERE)
import manifest as mf  # noqa: E402
import slots  # noqa: E402
from kandev_client import DEFAULT_URL, Kandev  # noqa: E402

GUARD_NAME = "多Agent 守护"
SLOT_ITEMS = ("git", "coding", "testing", "workspace", "quality", "params")


def bw():
    import build_workflows
    return build_workflows


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def source_commit(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    except OSError:
        return None


def pick_deployment(m, workspace):
    deps = (m or {}).get("deployments", {})
    if not deps:
        die("这里还没有记录任何部署：先运行 python kandev/ma.py questions --stage install，问过用户后运行 install --answers。")
    if workspace:
        if workspace not in deps:
            die(f"没有 workspace {workspace} 的部署记录；已有：{sorted(deps)}")
        return workspace, deps[workspace]
    if len(deps) > 1:
        die(f"这里记录了多个 workspace 的部署，用 --workspace 指定：{sorted(deps)}")
    return next(iter(deps.items()))


def load_ids(dep):
    p = os.path.join(ROOT, dep["ids"])
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def url_of(dep):
    return dep.get("answers", {}).get("kandev_url") or DEFAULT_URL


# ------------------------------------------------------------------ questions
def cmd_questions(a):
    for q in mf.questions(a.stage):
        tag = "必须问" if q["ask"] == "always" else "选了自定义才问"
        print(f"[{q['stage']}] {q['key']}（{tag}）\n  问题：{q['question']}")
        if q.get("options"):
            print(f"  选项：{' / '.join(q['options'])}")
        if "recommended" in q:
            print(f"  推荐：{q['recommended']}")
        for k, label in (("why", "理由"), ("how", "做法")):
            if q.get(k):
                print(f"  {label}：{q[k]}")
        print()
    print("把答案写成一个 JSON 文件（键 = 上面的 key），交给 ma.py install --answers。"
          "「必须问」的项要有用户的明确回答，不能替用户填。")


# ------------------------------------------------------------------ install
def ids_name(root, m, workspace):
    """这个 workspace 的 ids 文件名：已有的沿用；第一个部署用 kandev_ids.json，其余带 workspace 前 8 位。"""
    kd = os.path.join(root, "kandev")
    for f in sorted(os.listdir(kd)) if os.path.isdir(kd) else []:
        if f.startswith("kandev_ids") and f.endswith(".json"):
            try:
                if json.load(open(os.path.join(kd, f), encoding="utf-8")).get("_meta", {}).get("workspace_id") == workspace:
                    return f
            except (OSError, json.JSONDecodeError):
                pass
    used = {d.get("ids") for d in (m or {}).get("deployments", {}).values()}
    default = "kandev_ids.json"
    if f"kandev/{default}" not in used and not os.path.exists(os.path.join(kd, default)):
        return default
    return f"kandev_ids.{workspace[:8]}.json"


def write_keep(path, text):
    """写文件；已有且内容不同的先另存为 .bak（不覆盖已有的 .bak）。"""
    if os.path.exists(path):
        old = open(path, encoding="utf-8").read()
        if old == text:
            return
        if not os.path.exists(path + ".bak"):
            shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def cmd_install(a):
    answers = json.load(open(a.answers, encoding="utf-8"))
    answers, problems = mf.validate(answers, "install")
    if problems:
        die("答案不完整，先向用户确认：\n  " + "\n  ".join(problems), 2)
    ws = answers["workspace_id"]
    if answers["python"].startswith("<"):
        answers["python"] = sys.executable.replace("\\", "/")
    if answers["install_mode"] == "link":
        home = ROOT
        answers["home"] = home
    else:
        home = mf.norm(answers["home"].replace("<workspace id 前 8 位>", ws[:8]))
        answers["home"] = home
        if mf.norm(home) == mf.norm(ROOT):
            die("安装目录不能是源仓库本身；要直接使用本仓库请选 install_mode=link。", 2)
        if mf.load(home):
            die(f"{home} 已经是一个安装目录（版本 {mf.load(home).get('version')}）：升级用 ma.py upgrade --home，"
                f"改答案用 {home}/kandev/ma.py answer。", 2)
        if os.path.isdir(home) and os.listdir(home):
            die(f"{home} 已存在且不为空，换一个目录（ma.py 不覆盖也不删除已有内容）。", 2)
        files = mf.shipped_files(ROOT)
        for rel in files:
            dst = os.path.join(home, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), dst)
        print(f"已复制 {len(files)} 个文件到 {home}")
    m = mf.load(home) or {"schema": 1, "deployments": {}}
    m.update({"version": bw().VERSION, "mode": answers["install_mode"],
              "source": {"path": ROOT, "commit": source_commit(ROOT)}, "installed_at": now()})
    if answers["install_mode"] == "standalone":
        m["files"] = {rel: mf.sha(os.path.join(home, rel)) for rel in mf.shipped_files(home)}
    ids = ids_name(home, m, ws)
    prof = "profiles.local.json" if ids == "kandev_ids.json" else f"profiles.{ws[:8]}.local.json"
    write_keep(os.path.join(home, "kandev", prof), json.dumps(answers["profiles"], ensure_ascii=False, indent=2) + "\n")
    prev = m["deployments"].get(ws, {})
    m["deployments"][ws] = {**prev, "answers": answers, "ids": f"kandev/{ids}", "profiles": f"kandev/{prof}"}
    mf.save(home, m)
    py = answers["python"]
    print(f"已记录 workspace {ws} 的部署答案：{home}/{mf.NAME}")
    print("下一步（在安装目录中运行）：")
    if answers.get("setup_style") == "custom":
        print(f"  {py} {home}/kandev/ma.py questions --stage customize   # 问用户要定制哪些规则，写进 {home}/custom/rules/")
    print(f"  {py} {home}/kandev/ma.py diff --workspace {ws}")
    print(f"  {py} {home}/kandev/ma.py apply --workspace {ws}")


def cmd_answer(a):
    m = mf.load(ROOT)
    ws, dep = pick_deployment(m, a.workspace)
    known = {q["key"]: q for q in mf.questions()}
    for item in a.set:
        key, _, val = item.partition("=")
        if key not in known:
            die(f"不认识的 key：{key}（可用：{sorted(known)}）")
        q = known[key]
        if q.get("type") in ("list", "object") or val[:1] in "[{":
            val = json.loads(val)
        dep["answers"][key] = val
    for stage in ("install", "customize"):
        _, problems = mf.validate(dep["answers"], stage)
        problems = [p for p in problems if p.split("：")[0] in [i.partition("=")[0] for i in a.set]]
        if problems:
            die("\n".join(problems), 2)
    if "profiles" in [i.partition("=")[0] for i in a.set]:
        write_keep(os.path.join(ROOT, dep["profiles"]), json.dumps(dep["answers"]["profiles"], ensure_ascii=False, indent=2) + "\n")
    mf.save(ROOT, m)
    print("已更新：" + "，".join(a.set))


# ------------------------------------------------------------------ prompts: hash / diff
def prompt_hash():
    """将要部署的内容的指纹（prompt + 结构，不含本机 ID 和路径）。diff 打印它，apply --confirmed 核对它。"""
    b = bw()
    doc = [[wf["name"], wf["description"], [[s["name"], s["position"], s.get("prompt", ""), s["events"], s["_role"],
                                             s.get("wip_limit", 0)] for s in wf["steps"]]] for wf in b.all_workflows()]
    doc.append(b.GUARD_PROMPT)
    return hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def rendered(ids):
    """用已部署的 ID 和本目录的路径渲染出的三套 workflow：{workflow 名: {步骤名: prompt}}。"""
    b = bw()
    w3, w2 = ids[b.W3_NAME], ids[b.W2_NAME]
    wfs = b.all_workflows({"w3": (w3["workflow_id"], w3["steps"]["开发"], w3["steps"]["待开发"]),
                           "w2": (w2["workflow_id"], w2["steps"]["模块规划"])}, ROOT)
    return {wf["name"]: {s["name"]: s.get("prompt", "") for s in wf["steps"]} for wf in wfs}


def deployed(k, ids):
    out = {}
    for name, info in ids.items():
        if name.startswith("_"):
            continue
        doc = k.call("export_workflow_kandev", {"workflow_id": info["workflow_id"]})
        out[name] = {s["name"]: s.get("prompt") or "" for s in doc["workflows"][0]["steps"]}
    return out


def prompt_drift(k, ids):
    """[(workflow, 步骤, 已部署的 prompt, 本目录的 prompt)]，只列不同的。"""
    want, have = rendered(ids), deployed(k, ids)
    out = []
    for wname, steps in want.items():
        cur = have.get(wname, {})
        for sname in sorted(set(steps) | set(cur)):
            if (cur.get(sname) or "") != (steps.get(sname) or ""):
                out.append((wname, sname, cur.get(sname, ""), steps.get(sname, "")))
    return out


def running_projects(k, ids):
    """「项目管理」workflow 中还没结束的 pm 任务的标题。"""
    info = ids.get(bw().W1_NAME)
    if not info:
        return []
    done = info["steps"].get("完成")
    tasks = k.call("list_tasks_kandev", {"workflow_id": info["workflow_id"]}).get("tasks", [])
    return [t["title"] for t in tasks if t.get("workflow_step_id") != done and t.get("state") != "COMPLETED"]


def cmd_diff(a):
    m = mf.load(ROOT)
    ws, dep = pick_deployment(m, a.workspace)
    ids = load_ids(dep)
    h = prompt_hash()
    if not ids:
        print(f"workspace {ws} 还没有部署过（没有 {dep['ids']}），没有可比较的内容；apply 会新建三套 workflow。")
        print(f"confirm: {h}")
        return
    try:
        drift = prompt_drift(Kandev(url_of(dep), client="ma"), ids)
    except (OSError, RuntimeError, KeyError) as e:
        die(f"读不到已部署的 workflow：{e}")
    if not drift:
        print(f"已部署的 prompt 与本目录一致（{bw().VERSION}）。")
    for wname, sname, old, new in drift:
        print(f"== {wname} · {sname}")
        for line in difflib.unified_diff(old.split("\n"), new.split("\n"), lineterm="", n=0):
            if line.startswith(("---", "+++", "@@")):
                continue
            print("  " + (line if a.full or len(line) <= 220 else line[:220] + " …"))
    print(f"\n{len(drift)} 个步骤的 prompt 有变化。把变化讲给用户，同意后运行：ma.py apply --workspace {ws} --confirmed {h}")
    print(f"confirm: {h}")


# ------------------------------------------------------------------ guard handoff
def render_guard(ws, dep):
    """生成填好本机取值的守护交接文件和守护 prompt（*.local.md，不提交）。返回两个路径。"""
    b, ans = bw(), dep["answers"]
    ids_file = os.path.basename(dep["ids"])
    profiles = json.load(open(os.path.join(ROOT, dep["profiles"]), encoding="utf-8"))
    values = {"{WORKSPACE_ID}": ws, "{ARCH_ROOT}": ROOT, "{ARCH_REPO_ID}": "", "{PYTHON}": ans["python"],
              "{IDS_FILE}": ids_file, "{GUARD_PROFILE_ID}": profiles.get("mechanical", "")}
    hd = os.path.join(HERE, "handoff")
    text = open(os.path.join(hd, "guard-automation.md"), encoding="utf-8").read()
    for k, v in values.items():
        text = text.replace(k, v)
    prompt = (b.GUARD_PROMPT.replace("<本架构仓库的绝对路径>", ROOT)
              .replace("<Python 解释器的绝对路径（3.9+，只用标准库）>", ans["python"])
              .replace("<arch_root>", ROOT).replace("<python>", ans["python"])
              .replace("kandev/kandev_ids.json", f"kandev/{ids_file}"))
    out1 = os.path.join(hd, f"guard-handoff.{ws[:8]}.local.md")     # 不用 guard-automation.local.md：那是用户手填副本的名字
    out2 = os.path.join(hd, f"guard-prompt.{ws[:8]}.local.md")
    with open(out1, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(out2, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 守护 automation 的 prompt（已填好本机取值，由 ma.py 生成）\n\n```text\n" + prompt + "\n```\n")
    return out1, out2


def cmd_guard(a):
    ws, dep = pick_deployment(mf.load(ROOT), a.workspace)
    out1, out2 = render_guard(ws, dep)
    print(f"交接文件：{out1}\n守护 prompt：{out2}")


# ------------------------------------------------------------------ apply
def workflow_state(k, ws):
    """workspace 中同名 workflow 的情况：none / update（同一系列）/ retire（其他系列）。"""
    b = bw()
    found = [w for w in k.call("list_workflows_kandev", {"workspace_id": ws})["workflows"]
             if w["name"] in (b.W1_NAME, b.W2_NAME, b.W3_NAME)]
    if not found:
        return "none"
    vers = [b.desc_version(w.get("description")) for w in found]
    return "update" if all(v and b.series(v) == b.series(b.VERSION) for v in vers) else "retire"


def cmd_apply(a):
    b = bw()
    m = mf.load(ROOT)
    ws, dep = pick_deployment(m, a.workspace)
    ans = dep["answers"]
    missing = mf.missing_answers(ROOT, ws)
    if missing:
        die("部署前必须先向用户确认：\n  " + "\n  ".join(missing), 2)
    for item in ans.get("customize") or []:
        if item in SLOT_ITEMS and not slots.is_custom(item):
            die(f"答案里说要定制 {item}，但 custom/rules/ 下没有对应的文件：先按用户的要求写好，或用 ma.py answer 改掉这一项。", 2)
    try:
        k = Kandev(url_of(dep), client="ma", version=b.VERSION)
        state = workflow_state(k, ws)
    except OSError as e:
        die(f"连不上 Kandev（{url_of(dep)}）：{e}")
    want = ans["existing_workflows"]
    if dep.get("deployed_version") and state == "update":
        want = "update"                     # 之前由 ma.py 部署过的同一系列：就地更新，下面要求确认差异
    if state != want:
        die(f"workspace 中同名 workflow 的实际情况是 {state}，用户确认的是 {want}。向用户说明后运行："
            f"ma.py answer --workspace {ws} --set existing_workflows={state}", 2)
    ids = load_ids(dep)
    if state == "update":
        h = prompt_hash()
        if a.confirmed != h:
            die(f"这次是就地更新已部署的 workflow：先运行 ma.py diff --workspace {ws} 把变化给用户看，"
                f"同意后加 --confirmed {h}。", 2)
        busy = running_projects(k, ids) if ids else []
        if busy and not a.with_running:
            die("有进行中的项目：" + "、".join(busy) + "。它们从下一轮起会用新的 prompt。用户同意后加 --with-running。", 2)
    # 自检：prompts.md 是生成的，先重新生成（定制规则后它会变）
    class A:
        pass
    d = A()
    d.out = os.path.join(ROOT, "docs", "prompts.md")
    b.cmd_dump(d)
    r = subprocess.run([sys.executable, os.path.join(HERE, "check_docs.py")])
    if r.returncode:
        die("check_docs.py 没有全部通过，未部署。")
    p = A()
    p.workspace, p.profiles, p.url = ws, os.path.join(ROOT, dep["profiles"]), url_of(dep)
    p.retire_existing, p.ids_out = state == "retire", os.path.join(ROOT, dep["ids"])
    b.cmd_apply(p)
    dep.update({"deployed_version": b.VERSION, "deployed_at": now(), "prompt_hash": prompt_hash()})
    ans["existing_workflows"] = "update"
    mf.save(ROOT, m)
    out1, out2 = render_guard(ws, dep)
    r = subprocess.run([sys.executable, os.path.join(HERE, "verify_export.py"), "--ids", os.path.join(ROOT, dep["ids"])],
                       capture_output=True, text=True, encoding="utf-8")
    print("导出已更新：kandev/export/" if r.returncode == 0 else f"导出失败（不影响部署）：{(r.stdout + r.stderr)[-300:]}")
    print(f"\n已部署 {b.VERSION} 到 workspace {ws}。接下来：")
    g = ans["guard_automation"]
    if g == "create":
        print(f"  守护：按 {out1} 中的「交接 prompt」创建或更新 automation（prompt 正文已填好：{out2}）。")
    elif g == "manual":
        print(f"  守护：把 {out1} 交给用户，请用户在 Kandev 里把其中的「交接 prompt」交给 agent。")
    else:
        print("  守护：用户选择不建。")
    print("  验收：" + ("按 AGENTS.md「B. 验收部署」做，包括第 3 项（会启动一次真实会话，用户已同意）。"
                       if ans["acceptance_run"] == "yes" else "按 AGENTS.md「B. 验收部署」做第 1、2、4 项；第 3 项用户选择不做，记为 unverified。"))
    print(f"  检查：{ans['python']} {ROOT}/kandev/ma.py doctor --workspace {ws}")


# ------------------------------------------------------------------ doctor
def cmd_doctor(a):
    b = bw()
    res = []          # (级别, 说明)：OK / WARN / FAIL

    def add(level, msg):
        res.append((level, msg))

    m = mf.load(ROOT)
    if not m:
        add("FAIL", f"没有 {mf.NAME}：这个目录还没有用 ma.py install 记录过部署")
    else:
        add("OK", f"安装：{m.get('mode')}，版本 {m.get('version')}，来源 {m.get('source', {}).get('path')}"
                  f"（{m.get('source', {}).get('commit') or '无 commit'}）")
        if m.get("version") != b.VERSION:
            add("WARN", f"清单记录的版本 {m.get('version')} 与脚本的 {b.VERSION} 不一致（链接模式下更新了仓库时重新运行 install 即可）")
        if m.get("mode") == "standalone":
            src = m.get("source", {}).get("path")
            add("OK", "来源仓库" + ("仍在" if src and os.path.isdir(src) else "已不在") + "：不影响运行，升级时再提供新版仓库")
            changed = [r for r, h in m.get("files", {}).items() if os.path.exists(os.path.join(ROOT, r))
                       and not mf.is_generated(r) and mf.sha(os.path.join(ROOT, r)) != h]
            gone = [r for r in m.get("files", {}) if not os.path.exists(os.path.join(ROOT, r))]
            if changed:
                add("OK", f"你改过的出厂文件（升级时会保留）：{', '.join(changed)}")
            if gone:
                add("FAIL", f"出厂文件缺失：{', '.join(gone)}")
    for rel in ("docs/intake.md", "mgmt-template/README.md", "mgmt-template/VERSION", "kandev/stage.py", "rules/params.json"):
        if not os.path.exists(os.path.join(ROOT, rel)):
            add("FAIL", f"运行时需要的文件不存在：{rel}")
    custom = [n for n in slots.SLOTS + ("params",) if slots.is_custom(n)]
    add("OK", "定制的规则槽位：" + ("、".join(custom) if custom else "无（全部出厂规则）"))
    for ws, dep in ((m or {}).get("deployments", {})).items():
        if a.workspace and ws != a.workspace:
            continue
        tag = f"[{ws[:8]}] "
        missing = mf.missing_answers(ROOT, ws)
        if missing:
            add("FAIL", tag + "提问清单有未回答的必问项：" + "；".join(x.split("：")[0] for x in missing))
        ids = load_ids(dep)
        if not ids:
            add("WARN", tag + f"还没有部署（没有 {dep['ids']}）")
            continue
        meta = ids.get("_meta", {})
        if mf.norm(meta.get("arch_root", "")) != mf.norm(ROOT):
            add("FAIL", tag + f"上次部署是从另一个目录做的（{meta.get('arch_root')}）：Kandev 里的路径指向那里，在本目录重新 apply")
        if meta.get("version") != b.VERSION:
            add("WARN", tag + f"已部署 {meta.get('version')}，本目录是 {b.VERSION}：运行 ma.py diff 后 apply")
        if dep.get("prompt_hash") and dep["prompt_hash"] != prompt_hash():
            add("WARN", tag + "规则或 prompt 源在上次部署后改过，还没有重新部署：运行 ma.py diff")
        beat_p = os.path.join(HERE, "guard_state", "last_run.json")
        beat = json.load(open(beat_p, encoding="utf-8")) if os.path.exists(beat_p) else None
        if a.offline:
            add("WARN", tag + "离线模式：没有核对 Kandev 中的 workflow 和守护")
        else:
            try:
                k = Kandev(url_of(dep), client="ma", version=b.VERSION)
                drift = prompt_drift(k, ids)
                if drift:
                    add("WARN", tag + "已部署的 prompt 与本目录不一致：" + "、".join(f"{w.split('· ')[-1]}·{s}" for w, s, _, _ in drift[:8])
                        + ("…" if len(drift) > 8 else "") + "（ma.py diff 看详情）")
                else:
                    add("OK", tag + "已部署的 prompt 与本目录一致")
                busy = running_projects(k, ids)
                res_auto = k.call("list_settings_resources_kandev", {"resource_type": "automation", "workspace_id": ws, "limit": 50})
                guards = [r for r in res_auto.get("resources", []) if r.get("label") == GUARD_NAME]
                if not guards:
                    level = "OK" if dep["answers"].get("guard_automation") == "skip" else "FAIL"
                    add(level, tag + f"没有名为「{GUARD_NAME}」的 automation" + ("（用户选择不建）" if level == "OK" else ""))
                else:
                    add("OK", tag + f"守护 automation 存在（{len(guards)} 个）")
                if busy:
                    add("OK", tag + "进行中的项目：" + "、".join(busy))
                    at = beat and beat.get("at")
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() / 60 if at else None
                    if age is None or age > 40:
                        add("FAIL", tag + "有进行中的项目，但守护心跳（kandev/guard_state/last_run.json）"
                            + ("不存在" if age is None else f"是 {age:.0f} 分钟前") + "：守护没有在本目录运行（automation 停用了，或它的 prompt 指向别的目录）")
                    else:
                        add("OK", tag + f"守护心跳 {age:.0f} 分钟前")
                    for root in (beat or {}).get("mgmt_roots") or []:
                        vp = os.path.join(root, "VERSION")
                        v = open(vp, encoding="utf-8").read().strip() if os.path.exists(vp) else "早于 v3.3.4"
                        if v != b.VERSION:
                            add("OK", tag + f"项目 {root} 的管理目录来自 {v}（角色卡是启动时的版本，prompt 是当前部署的版本）")
                else:
                    add("OK", tag + "没有进行中的项目")
            except (OSError, RuntimeError, KeyError) as e:
                add("FAIL", tag + f"连不上 Kandev 或查询失败（{url_of(dep)}）：{e}")
        if beat and beat.get("failures"):
            add("WARN", tag + f"守护最近连续 {beat['failures']} 次连不上 Kandev：{beat.get('last_error')}")
    for level, msg in res:
        print(f"{level:<4} {msg}")
    return 1 if any(l == "FAIL" for l, _ in res) else 0


# ------------------------------------------------------------------ upgrade
def cmd_upgrade(a):
    b = bw()
    home = mf.norm(a.home)
    hm = mf.load(home)
    if not hm:
        die(f"{home} 不是安装目录（没有 {mf.NAME}）。")
    if hm.get("mode") == "link" or mf.norm(home) == mf.norm(ROOT):
        die("链接模式直接更新仓库（git pull）即可，然后在仓库里运行 ma.py diff / apply。")
    old_v = hm.get("version")
    beat_p = os.path.join(home, "kandev", "guard_state", "last_run.json")
    beat = json.load(open(beat_p, encoding="utf-8")) if os.path.exists(beat_p) else {}
    if beat.get("projects") and beat.get("at"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(beat["at"])).total_seconds() / 60
        if age <= 60 and not a.with_running:
            other = old_v and b.series(old_v) != b.series(b.VERSION)
            die("守护最近一次巡检（%d 分钟前）时有进行中的项目：%s。升级会立刻影响它们的守护和「接收」步骤%s。"
                "用户同意后加 --with-running。" % (age, "、".join(beat["projects"]),
                                             f"；新版 {b.VERSION} 与已安装的 {old_v} 不是同一系列，建议等项目结束" if other else ""), 2)
    base = hm.get("files", {})
    new_files = mf.shipped_files(ROOT)
    plan = {"add": [], "update": [], "same": [], "kept": [], "conflict": []}
    src_hash = {}
    for rel in new_files:
        src_hash[rel] = sh = mf.sha(os.path.join(ROOT, rel))
        dst = os.path.join(home, rel)
        cur = mf.sha(dst) if os.path.exists(dst) else None
        if cur is None:
            plan["add"].append(rel)
        elif cur == sh:
            plan["same"].append(rel)
        elif mf.is_generated(rel) or cur == base.get(rel):
            plan["update"].append(rel)
        elif base.get(rel) == sh:
            plan["kept"].append(rel)          # 用户改过，新版没有变
        else:
            plan["conflict"].append(rel)      # 用户改过，新版也变了
    removed = [r for r in base if r not in src_hash and os.path.exists(os.path.join(home, r))]
    print(f"升级 {home}：{old_v} → {b.VERSION}")
    print(f"  新增 {len(plan['add'])}，更新 {len(plan['update'])}，未变 {len(plan['same'])}，"
          f"保留你的改动 {len(plan['kept'])}，冲突 {len(plan['conflict'])}")
    for rel in plan["kept"]:
        print(f"  保留（你改过，新版没变）：{rel}")
    for rel in plan["conflict"]:
        print(f"  冲突（你改过，新版也变了）：{rel}")
    for rel in removed:
        print(f"  新版不再包含（没有删除，可自行处理）：{rel}")
    if plan["conflict"] and not a.conflicts:
        die("有冲突，什么都没有改。问用户后加 --conflicts keep（保留用户的版本，新版写成 .new）"
            "或 --conflicts take-new（采用新版，用户的版本另存为 .mine）。", 2)
    if a.dry_run:
        print("--dry-run：什么都没有改。")
        return
    for rel in plan["add"] + plan["update"]:
        dst = os.path.join(home, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), dst)
    for rel in plan["conflict"]:
        dst = os.path.join(home, rel)
        if a.conflicts == "keep":
            shutil.copyfile(os.path.join(ROOT, rel), dst + ".new")
        else:
            shutil.copyfile(dst, dst + ".mine")
            shutil.copyfile(os.path.join(ROOT, rel), dst)
    hm.update({"version": b.VERSION, "source": {"path": ROOT, "commit": source_commit(ROOT)}, "upgraded_at": now(),
               "upgraded_from": old_v, "files": {**{r: h for r, h in base.items() if r in removed}, **src_hash}})
    mf.save(home, hm)
    if plan["conflict"] and a.conflicts == "keep":
        print("冲突的文件保留了你的版本；新版在同名的 .new 文件里，合并后可以删掉 .new。")
    py = sys.executable.replace("\\", "/")
    print("文件已升级，Kandev 里的 workflow 还没有变。下一步（在安装目录中运行）：")
    for ws in hm.get("deployments", {}):
        print(f"  {py} {home}/kandev/ma.py diff --workspace {ws}    # 给用户看 prompt 的变化，然后 apply --confirmed")
    if any(slots.is_custom(n, home) for n in slots.SLOTS + ("params",)):
        print("  你有定制的规则槽位（custom/rules/）：对照新版 rules/ 里的说明看格式有没有变。")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("questions")
    q.add_argument("--stage", choices=mf.STAGES)
    i = sub.add_parser("install")
    i.add_argument("--answers", required=True)
    for name in ("diff", "apply", "guard", "doctor", "answer"):
        s = sub.add_parser(name)
        s.add_argument("--workspace")
        if name == "diff":
            s.add_argument("--full", action="store_true", help="不截断长行")
        if name == "apply":
            s.add_argument("--confirmed", help="ma.py diff 打印的 confirm 值（就地更新时必须）")
            s.add_argument("--with-running", action="store_true", help="有进行中的项目也继续（用户已同意）")
        if name == "doctor":
            s.add_argument("--offline", action="store_true", help="不连 Kandev")
        if name == "answer":
            s.add_argument("--set", action="append", required=True, metavar="key=value")
    u = sub.add_parser("upgrade")
    u.add_argument("--home", required=True)
    u.add_argument("--conflicts", choices=("keep", "take-new"))
    u.add_argument("--with-running", action="store_true")
    u.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    fn = {"questions": cmd_questions, "install": cmd_install, "diff": cmd_diff, "apply": cmd_apply, "guard": cmd_guard,
          "doctor": cmd_doctor, "answer": cmd_answer, "upgrade": cmd_upgrade}[a.cmd]
    sys.exit(fn(a) or 0)


if __name__ == "__main__":
    main()
