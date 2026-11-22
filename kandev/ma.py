"""多 Agent workflow 的安装、部署、检查和升级入口（只用标准库）。给 AI 的操作步骤见 AGENTS.md。

  python kandev/ma.py questions [--stage install|customize|redeploy|upgrade]   必须向用户确认的事项
  python kandev/ma.py install --answers answers.json    记录答案；独立安装时把运行所需的文件复制到安装目录
  python <home>/kandev/ma.py diff                        已部署的 workflow 与本目录将要部署的内容的差异
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
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE).replace("\\", "/")
sys.path.insert(0, HERE)
import manifest as mf  # noqa: E402
import slots  # noqa: E402
from kandev_client import DEFAULT_URL, Kandev  # noqa: E402

GUARD_NAME = "多Agent 守护"
# 安装后还能用 answer 改的键；workspace_id、install_mode、home 决定了安装本身，要改就重新安装
EDITABLE = ("profiles", "guard_automation", "python", "kandev_url", "setup_style")


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


def ver_tuple(v):
    return tuple(int(x) for x in (v or "v0").lstrip("v").split(".") if x.isdigit())


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


def connect(dep):
    try:
        return Kandev(url_of(dep), client="ma", version=bw().VERSION)
    except OSError as e:
        die(f"连不上 Kandev（{url_of(dep)}）：{e}")


def beat_path(root, dep, ws):
    """这个 workspace 的守护心跳文件（文件名规则在 stage.beat_name，守护自己也用它）。"""
    import stage
    name = stage.beat_name(dep["ids"], {"_meta": {"workspace_id": ws}})
    return os.path.join(root, "kandev", "guard_state", name)


def custom_slots(root=None):
    return [n for n in slots.CUSTOMIZABLE if slots.is_custom(n, root)]


# ------------------------------------------------------------------ questions
def cmd_questions(a):
    tags = {"always": "必须问", "custom": "选了自定义才问", "when_prompted": "ma.py 停下来时才问"}
    for q in mf.questions(a.stage):
        print(f"[{q['stage']}] {q['key']}（{tags[q['ask']]}）\n  问题：{q['question']}")
        for k, label in (("options", "选项"), ("recommended", "推荐"), ("why", "理由"), ("how", "做法"), ("flag", "同意后")):
            if k in q:
                print(f"  {label}：{' / '.join(q[k]) if isinstance(q[k], list) else q[k]}")
        print()
    print("install 阶段的答案写成一个 JSON 文件（键 = 上面的 key），交给 ma.py install --answers。"
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


def check_paths(answers):
    """守护命令里的路径不加引号（它要原样写进 automation 的 prompt），所以不能含空格；解释器必须存在。"""
    problems = []
    for key in ("home", "python"):
        if any(c.isspace() for c in answers.get(key) or ""):
            problems.append(f"{key}：路径不能含空格（{answers[key]}），换一个位置")
    if not os.path.isfile(answers["python"]):
        problems.append(f"python：找不到解释器 {answers['python']}")
    return problems


def cmd_install(a):
    answers, problems = mf.validate(json.load(open(a.answers, encoding="utf-8-sig")))
    if problems:
        die("答案有问题，先向用户确认：\n  " + "\n  ".join(f"{k}：{msg}" for k, msg in problems), 2)
    ws, link = answers["workspace_id"], answers["install_mode"] == "link"
    if answers["python"].startswith("<"):
        answers["python"] = sys.executable.replace("\\", "/")
    answers["home"] = home = ROOT if link else mf.norm(answers["home"].replace("<workspace id 前 8 位>", ws[:8]))
    problems = check_paths(answers)
    if problems:
        die("\n".join(problems), 2)
    if not link:
        if mf.norm(home) == mf.norm(ROOT):
            die("安装目录不能是源仓库本身；要直接使用本仓库请选 install_mode=link。", 2)
        if mf.load(home):
            die(f"{home} 已经是一个安装目录（版本 {mf.load(home).get('version')}）：升级用 ma.py upgrade --home，"
                f"改答案用 {home}/kandev/ma.py answer。", 2)
        if os.path.isdir(home) and os.listdir(home):
            die(f"{home} 已存在且不为空（ma.py 不覆盖也不删除已有内容）。如果是上次安装中断留下的，"
                "请用户确认后清掉它再装，或换一个目录。", 2)
        files = mf.shipped_files(ROOT)
        for rel in files:
            dst = os.path.join(home, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), dst)
        print(f"已复制 {len(files)} 个文件到 {home}")
    m = mf.load(home) or {"deployments": {}}
    m.update({"version": bw().VERSION, "mode": answers["install_mode"],
              "source": {"path": ROOT, "commit": source_commit(ROOT)}, "installed_at": now()})
    if not link:
        m["files"] = {rel: mf.sha(os.path.join(home, rel)) for rel in mf.shipped_files(home)}
    ids = ids_name(home, m, ws)
    prof = "profiles.local.json" if ids == "kandev_ids.json" else f"profiles.{ws[:8]}.local.json"
    m["deployments"][ws] = {**m["deployments"].get(ws, {}), "answers": answers, "ids": f"kandev/{ids}",
                            "profiles": f"kandev/{prof}"}
    mf.save(home, m)
    py = answers["python"]
    print(f"已记录 workspace {ws} 的部署答案：{home}/{mf.NAME}")
    print("下一步（在安装目录中运行）：")
    if answers["setup_style"] == "custom":
        print(f"  {py} {home}/kandev/ma.py questions --stage customize   # 问用户要定制什么，写进 {home}/custom/rules/")
    print(f"  {py} {home}/kandev/ma.py diff --workspace {ws}")
    print(f"  {py} {home}/kandev/ma.py apply --workspace {ws}")


def cmd_answer(a):
    m = mf.load(ROOT)
    ws, dep = pick_deployment(m, a.workspace)
    new, changed = dict(dep["answers"]), []
    types = {q["key"]: q.get("type") for q in mf.questions("install")}
    for item in a.set:
        key, eq, val = item.partition("=")
        if key not in EDITABLE:
            die(f"{key} 不能用 answer 改（可改：{', '.join(EDITABLE)}）；workspace、安装方式和安装目录要改就重新安装。", 2)
        if not eq or not val:
            die(f"写成 --set {key}=<值>。", 2)
        if types[key] == "object":
            try:
                val = json.loads(val)
            except json.JSONDecodeError as e:
                die(f"{key} 的值要是 JSON 对象（shell 里注意引号，或改答案文件后重新 install）：{e}", 2)
        new[key] = val
        changed.append(key)
    problems = [f"{k}：{msg}" for k, msg in mf.validate(new)[1]] + (check_paths(new) if "python" in changed else [])
    if problems:
        die("没有改动：\n  " + "\n  ".join(problems), 2)
    dep["answers"] = new
    mf.save(ROOT, m)
    print("已更新：" + "、".join(changed))
    if {"python", "profiles"} & set(changed):
        print("守护的命令或 profile 可能变了：重新部署后运行 ma.py guard，并按交接文件更新 automation。")


# ------------------------------------------------------------------ what is deployed vs. what would be deployed
def fingerprint():
    """将要部署的内容的指纹：三套 workflow 的全部内容（prompt、结构、事件、会话策略、角色）和守护 prompt，
    不含本机 ID 和路径。diff 打印它，apply --confirmed 核对它。"""
    b = bw()
    doc = [[{**b.clean(wf), "roles": [s["_role"] for s in wf["steps"]]} for wf in b.all_workflows()], b.GUARD_PROMPT]
    return hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def discover(k, ws):
    """workspace 里按名字找到的三套 workflow：{名称: {"workflow_id", "steps": {步骤名: id}, "version"}}。"""
    b, out = bw(), {}
    for w in k.call("list_workflows_kandev", {"workspace_id": ws})["workflows"]:
        if w["name"] in (b.W1_NAME, b.W2_NAME, b.W3_NAME):
            out[w["name"]] = {"workflow_id": w["id"], "steps": b.list_steps(k, w["id"]),
                              "version": b.desc_version(w.get("description"))}
    return out


def workflow_state(found):
    """none：没有同名 workflow；update：都属于当前系列，可以就地更新；retire：有其他系列的，只能改名保留后重新导入。"""
    b = bw()
    if not found:
        return "none"
    return "update" if all(i["version"] and b.series(i["version"]) == b.series(b.VERSION) for i in found.values()) else "retire"


def workflows_for(found):
    """用 workspace 里已有的 ID 和本目录的路径渲染三套 workflow（还不存在的 workflow 的 ID 留占位）。"""
    b, ids = bw(), {}
    w3, w2 = found.get(b.W3_NAME), found.get(b.W2_NAME)
    if w3 and {"开发", "待开发"} <= set(w3["steps"]):
        ids["w3"] = (w3["workflow_id"], w3["steps"]["开发"], w3["steps"]["待开发"])
    if w2 and "模块规划" in w2["steps"]:
        ids["w2"] = (w2["workflow_id"], w2["steps"]["模块规划"])
    return b.all_workflows(ids, ROOT)


def drift(k, found):
    """已部署的与将要部署的差异：([(workflow, 步骤, 已部署的 prompt, 新 prompt)], [结构差异的说明])。"""
    b, prompts, structure = bw(), [], []
    for wf in workflows_for(found):
        info = found.get(wf["name"])
        if not info:
            structure.append(f"{wf['name']}：还不存在，将新建")
            continue
        doc = k.call("export_workflow_kandev", {"workflow_id": info["workflow_id"]})
        have = {s["name"]: s.get("prompt") or "" for s in doc["workflows"][0]["steps"]}
        for s in wf["steps"]:
            if have.get(s["name"], "") != s.get("prompt", ""):
                prompts.append((wf["name"], s["name"], have.get(s["name"], ""), s.get("prompt", "")))
        try:
            diffs, _, reordered = b.structure_diff(k, wf, info["workflow_id"])
        except SystemExit as e:
            structure.append(f"{wf['name']}：步骤集合不同，不能就地更新（{e}）")
            continue
        structure += [f"{wf['name']} · {name}：{', '.join(sorted(d))}" for name, _, d in diffs]
        if reordered:
            structure.append(f"{wf['name']}：步骤顺序")
        if (doc["workflows"][0].get("description") or "") != wf["description"]:
            structure.append(f"{wf['name']}：description（{info['version']} → {b.VERSION}）")
    return prompts, structure


def running_projects(k, found):
    """「项目管理」workflow 中还没结束的 pm 任务的标题。"""
    info = found.get(bw().W1_NAME)
    if not info:
        return []
    done = info["steps"].get("完成")
    tasks = k.call("list_tasks_kandev", {"workflow_id": info["workflow_id"]}).get("tasks", [])
    return [t["title"] for t in tasks if t.get("workflow_step_id") != done and t.get("state") != "COMPLETED"]


def guard_files(ws):
    hd = os.path.join(HERE, "handoff")
    return os.path.join(hd, f"guard-handoff.{ws[:8]}.local.md"), os.path.join(hd, f"guard-prompt.{ws[:8]}.local.md")


def guard_text(dep):
    return bw().guard_prompt(ROOT, dep["answers"]["python"], os.path.basename(dep["ids"]))


def cmd_diff(a):
    b = bw()
    ws, dep = pick_deployment(mf.load(ROOT), a.workspace)
    k = connect(dep)
    try:
        found = discover(k, ws)
        state = workflow_state(found)
        prompts, structure = drift(k, found) if state == "update" else ([], [])
    except (RuntimeError, KeyError) as e:
        die(f"读不到已部署的 workflow：{e}")
    h = fingerprint()
    if state == "none":
        print(f"workspace {ws} 里没有同名 workflow：apply 会新建三套（{b.VERSION}），不需要 --confirmed。")
    elif state == "retire":
        print(f"workspace {ws} 里的同名 workflow 属于另一个系列（{sorted({i['version'] or '无版本号' for i in found.values()})}），"
              f"不能就地更新成 {b.VERSION}：apply --retire 会把旧版改名保留再导入新版（先问用户，见 questions --stage redeploy）。")
    else:
        for wname, sname, old, new in prompts:
            print(f"== {wname} · {sname}")
            for line in difflib.unified_diff(old.split("\n"), new.split("\n"), lineterm="", n=0):
                if not line.startswith(("---", "+++", "@@")):
                    print("  " + (line if a.full or len(line) <= 220 else line[:220] + " …"))
        if structure:
            print("== 结构（顺序、事件、开关、会话策略、WIP）\n  " + "\n  ".join(structure))
        print(f"\n{len(prompts)} 个步骤的 prompt、{len(structure)} 处结构有变化"
              + ("。" if prompts or structure else f"：已部署的 workflow 与本目录一致（{b.VERSION}）。"))
    out2 = guard_files(ws)[1]
    if dep["answers"]["guard_automation"] == "yes" and os.path.exists(out2):
        if guard_text(dep) not in open(out2, encoding="utf-8").read():
            print("守护 prompt 与上次生成的交接文件不同：部署后要按新的交接文件更新 automation。")
    if state == "update":
        print(f"把变化讲给用户，同意后运行：ma.py apply --workspace {ws} --confirmed {h}")
    print(f"confirm: {h}")


# ------------------------------------------------------------------ guard handoff
def render_guard(ws, dep):
    """生成填好本机取值的守护交接文件和守护 prompt（*.local.md，不提交）。返回两个路径。"""
    ans = dep["answers"]
    out1, out2 = guard_files(ws)          # 不用 guard-automation.local.md：那是用户手填副本的名字
    values = {"{WORKSPACE_ID}": ws, "{ARCH_ROOT}": ROOT, "{ARCH_REPO_ID}": "", "{PYTHON}": ans["python"],
              "{IDS_FILE}": os.path.basename(dep["ids"]), "{GUARD_PROMPT_FILE}": out2.replace("\\", "/"),
              "{GUARD_PROFILE_ID}": mf.full_profiles(ans["profiles"])["mechanical"], "{KANDEV_URL}": url_of(dep)}
    text = open(os.path.join(HERE, "handoff", "guard-automation.md"), encoding="utf-8").read()
    for key, v in values.items():
        text = text.replace(key, v)
    with open(out1, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    with open(out2, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 守护 automation 的 prompt（已填好本机取值，由 ma.py 生成）\n\n```text\n" + guard_text(dep) + "\n```\n")
    return out1, out2


def cmd_guard(a):
    ws, dep = pick_deployment(mf.load(ROOT), a.workspace)
    out1, out2 = render_guard(ws, dep)
    print(f"交接文件：{out1}\n守护 prompt：{out2}")


# ------------------------------------------------------------------ apply
def cmd_apply(a):
    b = bw()
    m = mf.load(ROOT)
    ws, dep = pick_deployment(m, a.workspace)
    ans = dep["answers"]
    missing = mf.missing_answers(ROOT, ws)
    if missing:
        die("部署前必须先向用户确认：\n  " + "\n  ".join(missing), 2)
    k = connect(dep)
    found = discover(k, ws)
    state, h = workflow_state(found), fingerprint()
    busy = running_projects(k, found)
    if state == "retire":
        if not a.retire:
            die(f"workspace 里的同名 workflow 属于另一个系列（{sorted({i['version'] or '无版本号' for i in found.values()})}），"
                f"不能就地更新成 {b.VERSION}。问用户（questions --stage redeploy 的 retire_existing）后加 --retire："
                "旧版改名保留，再导入新版。", 2)
        if busy and not a.with_running:
            die("旧版 workflow 上有进行中的项目：" + "、".join(busy) + "。它们会在旧 workflow 上跑完，但守护只巡检新版，"
                "不再巡检它们。用户同意后加 --with-running。", 2)
    elif state == "update":
        resumed = dep.get("apply_started") == h and not dep.get("deployed_version")   # 上次首次部署中断：不用再确认一遍
        if a.confirmed != h and not resumed:
            die(f"这次是就地更新已部署的 workflow：先运行 ma.py diff --workspace {ws} 把变化给用户看，"
                "同意后带上它打印的 confirm 值（--confirmed）。", 2)
        if busy and not a.with_running:
            die("有进行中的项目：" + "、".join(busy) + "。它们从下一轮起会用新的 prompt。用户同意后加 --with-running。", 2)
    # 自检。prompts.md 和 export/ 是生成的：独立安装目录里按本机的定制重新生成；
    # 链接模式下它们是版本库里的文件，保持出厂内容，本机定制后的导出写到 export.local/
    link_custom = m.get("mode") == "link" and custom_slots()
    env = {k2: v for k2, v in os.environ.items() if k2 != "MA_NO_CUSTOM"}
    if link_custom:
        env["MA_NO_CUSTOM"] = "1"
    else:
        b.cmd_dump(SimpleNamespace(out=os.path.join(ROOT, "docs", "prompts.md")))
    if subprocess.run([sys.executable, os.path.join(HERE, "check_docs.py")], env=env).returncode:
        die("check_docs.py 没有全部通过，未部署。")
    ids_path, prof_path = os.path.join(ROOT, dep["ids"]), os.path.join(ROOT, dep["profiles"])
    write_keep(prof_path, json.dumps(ans["profiles"], ensure_ascii=False, indent=2) + "\n")   # 以答案为准
    if state == "retire" and os.path.exists(ids_path):        # 旧版的 ID 留一份，之后还能查旧 workflow 上的任务
        old_v = next((i["version"] for i in found.values() if i["version"]), "old")
        keep = f"{ids_path[:-5]}.{old_v}.bak"
        if not os.path.exists(keep):
            shutil.copyfile(ids_path, keep)
    dep["apply_started"] = h
    mf.save(ROOT, m)
    b.cmd_apply(SimpleNamespace(workspace=ws, profiles=prof_path, url=url_of(dep),
                                retire_existing=state == "retire", ids_out=ids_path))
    dep.update({"deployed_version": b.VERSION, "deployed_at": now(), "fingerprint": h})
    dep.pop("apply_started", None)
    m["version"] = b.VERSION
    mf.save(ROOT, m)
    out1, out2 = guard_files(ws)
    guard_changed = not os.path.exists(out2) or guard_text(dep) not in open(out2, encoding="utf-8").read()
    render_guard(ws, dep)
    export = os.path.join(HERE, "export.local" if link_custom else "export")
    r = subprocess.run([sys.executable, os.path.join(HERE, "verify_export.py"), "--ids", ids_path, "--out", export],
                       capture_output=True, text=True, encoding="utf-8")
    print(f"导出已更新：{export}" if r.returncode == 0 else f"导出失败（不影响部署）：{(r.stdout + r.stderr)[-300:]}")
    print(f"\n已部署 {b.VERSION} 到 workspace {ws}。接下来：")
    if ans["guard_automation"] == "skip":
        print("  守护：用户选择不建（项目卡住时不会有告警）。")
    elif guard_changed:
        print(f"  守护：按 {out1} 中的「交接 prompt」创建或更新 automation。你有 create_automation_kandev 就自己做；"
              "没有就把这个文件交给用户，请用户在任一 Kandev 任务里把「交接 prompt」交给 agent。")
    else:
        print("  守护：prompt 没有变化，已有的 automation 不用动。")
    print("  验收：按 AGENTS.md「B. 验收部署」做（第 3 项会启动一次真实会话，做之前问用户）。")
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
        if m.get("mode") == "standalone":
            if m.get("version") != b.VERSION:
                add("FAIL", f"清单记录的版本 {m.get('version')} 与脚本的 {b.VERSION} 不一致：安装目录被手工改过，用 ma.py upgrade 重新对齐")
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
    add("OK", "定制的规则槽位：" + ("、".join(custom_slots()) or "无（全部出厂规则）"))
    want_steps = {wf["name"]: {s["name"] for s in wf["steps"]} for wf in b.all_workflows()}
    for ws, dep in ((m or {}).get("deployments", {})).items():
        if a.workspace and ws != a.workspace:
            continue
        tag = f"[{ws[:8]}] "
        missing = mf.missing_answers(ROOT, ws)
        if missing:
            add("FAIL", tag + "提问清单有未回答或不合格的必问项：" + "；".join(missing))
        ids = load_ids(dep)
        if not ids:
            add("WARN", tag + f"还没有部署（没有 {dep['ids']}）")
            continue
        meta = ids.get("_meta", {})
        if mf.norm(meta.get("arch_root", "")) != mf.norm(ROOT):
            add("FAIL", tag + f"上次部署是从另一个目录做的（{meta.get('arch_root')}）：Kandev 里的路径指向那里，在本目录重新 apply")
        if meta.get("version") != b.VERSION:
            add("WARN", tag + f"已部署 {meta.get('version')}，本目录是 {b.VERSION}：运行 ma.py diff 后 apply")
        elif dep.get("fingerprint") and dep["fingerprint"] != fingerprint():
            add("WARN", tag + "规则或 prompt 源在上次部署后改过，还没有重新部署：运行 ma.py diff")
        stale = [n for n, steps in want_steps.items() if set(ids.get(n, {}).get("steps", {})) != steps]
        if stale:
            add("FAIL", tag + f"ids 文件里的步骤与脚本不一致（{'、'.join(stale)}）：守护会认不出这些步骤，重新 apply")
        bp = beat_path(ROOT, dep, ws)
        beat = json.load(open(bp, encoding="utf-8")) if os.path.exists(bp) else None
        if a.offline:
            add("WARN", tag + "离线模式：没有核对 Kandev 中的 workflow 和守护")
        else:
            try:
                k = Kandev(url_of(dep), client="ma", version=b.VERSION)
                found = discover(k, ws)
                if workflow_state(found) != "update":
                    add("FAIL", tag + "workspace 里找不到当前系列的三套 workflow（被改名或删除了？）")
                else:
                    prompts, structure = drift(k, found)
                    if prompts or structure:
                        names = [f"{w.split('· ')[-1]}·{s}" for w, s, _, _ in prompts] + structure
                        add("WARN", tag + "已部署的 workflow 与本目录不一致：" + "、".join(names[:8])
                            + ("…" if len(names) > 8 else "") + "（ma.py diff 看详情）")
                    else:
                        add("OK", tag + "已部署的 workflow 与本目录一致")
                busy = running_projects(k, found)
                res_auto = k.call("list_settings_resources_kandev", {"resource_type": "automation", "workspace_id": ws, "limit": 50})
                guards = [r for r in res_auto.get("resources", []) if r.get("label") == GUARD_NAME]
                skip = dep["answers"].get("guard_automation") == "skip"
                if not guards:
                    add("OK" if skip else "FAIL", tag + f"没有名为「{GUARD_NAME}」的 automation" + ("（用户选择不建）" if skip else ""))
                else:
                    add("OK", tag + f"守护 automation 存在（{len(guards)} 个）")
                if busy:
                    add("OK", tag + "进行中的项目：" + "、".join(busy))
                    at = beat and beat.get("at")
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() / 60 if at else None
                    if skip:
                        pass
                    elif age is None or age > 40:
                        add("FAIL", tag + f"有进行中的项目，但守护心跳（{os.path.relpath(bp, ROOT)}）"
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
    return 1 if any(lv == "FAIL" for lv, _ in res) else 0


# ------------------------------------------------------------------ upgrade
def free_name(path):
    """.new / .mine 已存在时不覆盖（可能是用户合并到一半的），换一个带序号的名字。"""
    n, out = 1, path
    while os.path.exists(out):
        n += 1
        out = f"{path}.{n}"
    return out


def cmd_upgrade(a):
    b = bw()
    home = mf.norm(a.home)
    hm = mf.load(home)
    if not hm:
        die(f"{home} 不是安装目录（没有 {mf.NAME}）。")
    if hm.get("mode") == "link" or mf.norm(home) == mf.norm(ROOT):
        die("链接模式直接更新仓库（git pull）即可，然后在仓库里运行 ma.py diff / apply。")
    old_v = hm.get("version")
    if ver_tuple(b.VERSION) < ver_tuple(old_v) and not a.allow_downgrade:
        die(f"安装目录是 {old_v}，这个仓库是 {b.VERSION}（更旧）。确实要降级的话加 --allow-downgrade。", 2)
    busy = []
    for ws, dep in hm.get("deployments", {}).items():
        bp = beat_path(home, dep, ws)
        beat = json.load(open(bp, encoding="utf-8")) if os.path.exists(bp) else {}
        if beat.get("projects") and beat.get("at"):
            if (datetime.now(timezone.utc) - datetime.fromisoformat(beat["at"])).total_seconds() <= 3600:
                busy += beat["projects"]
    if busy and not a.with_running:
        other = old_v and b.series(old_v) != b.series(b.VERSION)
        die("守护最近一小时的巡检里有进行中的项目：" + "、".join(busy) + "。升级会立刻影响它们的守护和「接收」步骤"
            + (f"；新版 {b.VERSION} 与已安装的 {old_v} 不是同一系列，建议等项目结束" if other else "")
            + "。用户同意后加 --with-running。", 2)
    base = hm.get("files", {})
    plan = {"add": [], "update": [], "same": [], "kept": [], "conflict": []}
    src_hash = {}
    for rel in mf.shipped_files(ROOT):
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
    for label, rels in (("保留（你改过，新版没变）", plan["kept"]), ("冲突（你改过，新版也变了）", plan["conflict"]),
                        ("新版不再包含（没有删除，可自行处理）", removed)):
        for rel in rels:
            print(f"  {label}：{rel}")
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
            shutil.copyfile(os.path.join(ROOT, rel), free_name(dst + ".new"))
        else:
            shutil.copyfile(dst, free_name(dst + ".mine"))
            shutil.copyfile(os.path.join(ROOT, rel), dst)
    hm.update({"version": b.VERSION, "source": {"path": ROOT, "commit": source_commit(ROOT)}, "upgraded_at": now(),
               "upgraded_from": old_v, "files": src_hash})
    mf.save(home, hm)
    if plan["conflict"] and a.conflicts == "keep":
        print("冲突的文件保留了你的版本；新版在同名的 .new 文件里，合并后可以删掉 .new。")
    py = sys.executable.replace("\\", "/")
    print("文件已升级，Kandev 里的 workflow 还没有变。下一步（在安装目录中运行）：")
    for ws in hm.get("deployments", {}):
        print(f"  {py} {home}/kandev/ma.py diff --workspace {ws}    # 给用户看变化，然后 apply --confirmed")
    if custom_slots(home):
        print("  你有定制的规则槽位（custom/rules/）：对照新版 rules/ 里的说明看格式有没有变。")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
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
            s.add_argument("--retire", action="store_true", help="同名 workflow 属于另一个系列时：旧版改名保留，再导入新版（用户已同意）")
        if name == "doctor":
            s.add_argument("--offline", action="store_true", help="不连 Kandev")
        if name == "answer":
            s.add_argument("--set", action="append", required=True, metavar="key=value")
    u = sub.add_parser("upgrade")
    u.add_argument("--home", required=True)
    u.add_argument("--conflicts", choices=("keep", "take-new"))
    u.add_argument("--with-running", action="store_true")
    u.add_argument("--allow-downgrade", action="store_true")
    u.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    fn = {"questions": cmd_questions, "install": cmd_install, "diff": cmd_diff, "apply": cmd_apply, "guard": cmd_guard,
          "doctor": cmd_doctor, "answer": cmd_answer, "upgrade": cmd_upgrade}[a.cmd]
    sys.exit(fn(a) or 0)


if __name__ == "__main__":
    main()
