"""本仓库的自检：文档、prompt 源和模板是否一致。修改 workflow 后、部署前运行：python kandev/check_docs.py

检查项：
  1. docs/prompts.md 与 `build_workflows.py dump` 的输出一致（prompt 只能改脚本后重新生成）
  2. 所有 Markdown 中的本地链接都能解析
  3. docs/workflow.md 中 W1 / W2 / W3 表格的步骤名与 build_workflows.py 一致
  4. prompt 中引用的 <mgmt_root>/... 路径在 mgmt-template 中存在（运行时生成的路径除外）
  5. docs/workflow.md 标题中的版本号与 VERSION 一致
  6. stage.py 的离线回归测试通过
  7. check_tasks.py（tasks.json 契约检查）的测试通过
  8. check_owns.py（改动范围检查）的测试通过
  9. mgmt_precommit.py（管理目录钩子）的测试通过
 10. prompt 中引用的 <ARCH_ROOT>/... 文件在本仓库中存在；docs/intake.md 列出了 [TASK v1] 头的每个字段
 11. 步骤结构：「完成」（complete_task_on_enter）是每个 workflow 的最后一个步骤，move_to_next 不进入「刷新」
 12. mgmt-template/VERSION 与 VERSION 一致（项目的管理目录由它记录来自哪个版本）
 13. 部署提问清单（deploy_questions.json）格式正确，并登记了每个规则槽位和参数
 14. ma.py（安装、定制、升级）的离线测试通过
 15. stage.py 里写死的步骤名、workflow 名与 build_workflows.py 一致（守护靠步骤名分类）
 16. 步骤 prompt 里的 {…} 只有 Kandev 认识的变量（花括号转义写错时不会报错，只会把错的占位符部署出去）
 17. stage.py 的信号表与 mgmt-template/roles/guard.md 的两张表一致（信号名、发给谁、是否升级）
 18. 共享块的位置：【刷新】规则只在常驻步骤里；【定级】每个 prompt 最多一份，且模板里不再另写一份；prompt 里没有反斜杠
源仓库和链接模式下按出厂规则检查（docs/prompts.md 是版本库里的文件）；独立安装目录里按本机的定制检查。
在安装目录（ma.py install 复制出来的目录）里也可以运行：没有随安装复制的调研材料的链接不检查。
退出码：0 全部通过；1 有问题（逐条列出）。只用标准库。
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import manifest as mf  # noqa: E402

if (mf.load(ROOT) or {}).get("mode") != "standalone":
    os.environ["MA_NO_CUSTOM"] = "1"          # 必须在导入 slots / build_workflows 之前
import build_workflows as bw  # noqa: E402
import slots  # noqa: E402

TEMPLATE = os.path.join(ROOT, "mgmt-template")
# 运行时才生成、模板中不存在的管理目录路径
RUNTIME = ("quota/", "evidence/", "agents/guard/", "agents/pm/", "agents/mod-", "modules/<", "roles/<")
SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def md_files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(d, f)


def check_prompts():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "prompts.md")

        with contextlib.redirect_stdout(io.StringIO()):
            bw.cmd_dump(SimpleNamespace(out=out))
        fresh = open(out, encoding="utf-8").read()
    cur_path = os.path.join(ROOT, "docs", "prompts.md")
    cur = open(cur_path, encoding="utf-8").read() if os.path.exists(cur_path) else ""
    return [] if fresh == cur else ["docs/prompts.md 不是最新：运行 python kandev/build_workflows.py dump --out docs/prompts.md"]


LINK = re.compile(r"\]\(([^)\s]+)\)")


def check_links():
    problems = []
    for f in md_files():
        text = open(f, encoding="utf-8").read()
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#")[0]
            top = os.path.relpath(os.path.normpath(os.path.join(os.path.dirname(f), path)), ROOT).replace("\\", "/").split("/")[0]
            if top in mf.SKIP_TOP and not os.path.isdir(os.path.join(ROOT, top)):
                continue      # 安装目录里没有调研材料
            if path and not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), path))):
                problems.append(f"{os.path.relpath(f, ROOT)}: 链接不存在 {target}")
    return problems


def doc_steps(text, heading):
    m = re.search(rf"^## {re.escape(heading)}.*?$(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        return None
    names = []
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) > 2 and re.fullmatch(r"\d+", cells[0]):
            names.append(re.sub(r"[*（(].*$", "", cells[1].replace("**", "")).strip())
    return names


def check_steps():
    text = open(os.path.join(ROOT, "docs", "workflow.md"), encoding="utf-8").read()
    problems = []
    for wf, heading in zip(bw.all_workflows(), ("6. W3 开发", "5. W2 模块管理", "4. W1 项目管理")):
        want = [s["name"] for s in sorted(wf["steps"], key=lambda s: s["position"])]
        got = doc_steps(text, heading)
        if got is None:
            problems.append(f"docs/workflow.md 缺少「## {heading}」一节")
        elif got != want:
            problems.append(f"docs/workflow.md「{heading}」步骤 {got} 与脚本 {want} 不一致")
    return problems


def check_template_refs():
    problems, seen = [], set()
    texts = [s.get("prompt", "") for wf in bw.all_workflows() for s in wf["steps"]] + [bw.GUARD_PROMPT]
    for text in texts:
        for ref in re.findall(r"<mgmt_root>/([^\s，。；、（）()`'\"「」]+)", text):
            ref = ref.rstrip("/.:：」").split("#")[0]
            if not ref or ref in seen or ref.startswith(RUNTIME):
                continue
            seen.add(ref)
            if "<" in ref:
                continue
            if not os.path.exists(os.path.join(TEMPLATE, ref)):
                problems.append(f"prompt 引用 <mgmt_root>/{ref}，mgmt-template 中不存在")
    return problems


TASK_FIELDS = ("project", "mode", "plan_only", "integration_test", "mgmt_root", "mgmt_template", "repo",
               "role", "scope", "parent", "pm", "branch")


def check_arch_refs():
    problems, seen = [], set()
    for wf in bw.all_workflows():
        for s in wf["steps"]:
            for ref in re.findall(re.escape(bw.ARCH_PLACEHOLDER) + r"/([\w./-]+)", s.get("prompt", ""), re.ASCII):
                ref = ref.rstrip(".")
                if ref not in seen and not os.path.exists(os.path.join(ROOT, ref)):
                    problems.append(f"prompt 引用 {bw.ARCH_PLACEHOLDER}/{ref}，本仓库中不存在")
                seen.add(ref)
    if not seen:
        problems.append("「接收」步骤的 prompt 没有引用参数说明文档")
    path = os.path.join(ROOT, "docs", "intake.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    missing = [f for f in TASK_FIELDS if f"`{f}`" not in text]
    if missing:
        problems.append(f"docs/intake.md 没有说明这些 [TASK v1] 字段：{missing}")
    return problems


def check_structure():
    return [p for wf in bw.all_workflows() for p in bw.structure_problems(wf)]


def check_version():
    first = open(os.path.join(ROOT, "docs", "workflow.md"), encoding="utf-8").readline()
    return [] if f"（{bw.VERSION}）" in first else [f"docs/workflow.md 标题版本与 VERSION={bw.VERSION} 不一致：{first.strip()}"]


def run_test(name, script):
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", script)],
                       capture_output=True, text=True, encoding="utf-8")
    return [] if r.returncode == 0 else [f"{name} 测试失败：{(r.stdout + r.stderr).strip()[-500:]}"]


def check_stage_test():
    return run_test("stage.py", "test_stage.py")


def check_tasks_test():
    return run_test("check_tasks.py", "test_check_tasks.py")


def check_owns_test():
    return run_test("check_owns.py", "test_check_owns.py")


def check_precommit_test():
    return run_test("mgmt_precommit.py", "test_mgmt_precommit.py")


def check_template_version():
    p = os.path.join(TEMPLATE, "VERSION")
    v = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else None
    return [] if v == bw.VERSION else [f"mgmt-template/VERSION 是 {v}，应为 {bw.VERSION}"]


def check_questions():
    problems, keys, covers = [], set(), set()
    for q in mf.questions():
        for f in ("key", "stage", "ask", "question"):
            if not q.get(f):
                problems.append(f"deploy_questions.json：{q.get('key', '?')} 缺少 {f}")
        if q.get("stage") not in mf.STAGES or q.get("ask") not in mf.ASKS:
            problems.append(f"deploy_questions.json：{q.get('key')} 的 stage / ask 取值不对")
        if q.get("key") in keys:
            problems.append(f"deploy_questions.json：key 重复 {q.get('key')}")
        if q.get("ask") == "custom" and "recommended" not in q:
            problems.append(f"deploy_questions.json：{q.get('key')} 是可选项，必须给 recommended")
        if q.get("ask") != "when_prompted" and q.get("stage") not in ("install", "customize"):
            problems.append(f"deploy_questions.json：{q.get('key')} 的答案不会被记录（只有 install 阶段记录），ask 应为 when_prompted")
        keys.add(q.get("key"))
        covers |= set(q.get("covers", []))
    want = {f"rules/{n}.md" for n in slots.SLOTS} | {f"rules/params.json:{k}" for k in slots.params()}
    for item in sorted(want - covers):
        problems.append(f"deploy_questions.json 没有登记槽位 {item}（加到 customize 阶段的 covers）")
    for n in slots.SLOTS:
        if not os.path.exists(os.path.join(ROOT, "rules", n + ".md")):
            problems.append(f"缺少槽位文件 rules/{n}.md")
    return problems


def check_stage_names():
    """stage.py 按步骤名和 workflow 名分类；这些名字在 build_workflows.py 里改了而 stage.py 没跟上时，守护会无声失效。"""
    import stage
    wfs = bw.all_workflows()
    names = {s["name"] for wf in wfs for s in wf["steps"]}
    signal = {s["name"] for wf in wfs for s in wf["steps"] if s["auto_advance_requires_signal"]}
    problems = []
    if signal != stage.SIGNAL_STEPS:
        problems.append(f"stage.SIGNAL_STEPS 与要求完成信号的步骤不一致：{sorted(signal ^ stage.SIGNAL_STEPS)}")
    used = stage.GATES | stage.RESIDENT | stage.MOD_LIVE | {stage.HOLD, stage.DECISION, stage.DONE, stage.INTAKE, "刷新"}
    if used - names:
        problems.append(f"stage.py 用到的步骤名在 workflow 里不存在：{sorted(used - names)}")
    for name, suffix in ((bw.W1_NAME, "项目管理"), (bw.W2_NAME, "模块管理"), (bw.W3_NAME, "开发")):
        if not name.endswith(suffix):
            problems.append(f"workflow 名 {name} 不以「{suffix}」结尾：stage.py 靠这个后缀区分三套 workflow")
    if stage.GUARD_NAME not in bw.GUARD_PROMPT:
        problems.append("守护 automation 的名称在 stage.py 和守护 prompt 里不一致")
    return problems


def check_guard_signals():
    """守护的规则只有一份给人看的说明（mgmt-template/roles/guard.md）；它列出的信号、发给谁、是否升级要与 stage.SIGNALS 一致。
    「阶段分类」表最后一列、「信号」表第一列里反引号括起来的就是信号名。"""
    import stage
    text = open(os.path.join(TEMPLATE, "roles", "guard.md"), encoding="utf-8").read()

    def table(heading):
        m = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in (m.group(1) if m else "").split("\n")
                if l.startswith("|")]
        return rows[2:]          # 去掉表头和分隔行

    problems = []
    names = lambda cell: set(re.findall(r"`([a-z_]+)`", cell))     # noqa: E731
    rules = set().union(*(names(r[-1]) for r in table("阶段分类")))
    if rules != set(stage.SIGNALS):
        problems.append(f"guard.md「阶段分类」表最后一列的信号与 stage.SIGNALS 不一致：{sorted(rules ^ set(stage.SIGNALS))}")
    listed = {}
    for r in table("信号"):
        for n in names(r[0]):
            listed[n] = r
    want = set(stage.SIGNALS) | {stage.ESCALATED, stage.DISABLED}
    if set(listed) != want:
        problems.append(f"guard.md「信号」表第一列的信号与 stage.py 不一致：{sorted(set(listed) ^ want)}")
    to = {stage.SUPERIOR: "上级", stage.SELF: "任务自己", stage.TO_PM: "pm"}
    for n, sig in stage.SIGNALS.items():
        r = listed.get(n)
        if not r or len(r) < 3:
            continue
        if not r[1].startswith(to[sig.to]):
            problems.append(f"guard.md「信号」表：{n} 的「发给」应以「{to[sig.to]}」开头（stage.SIGNALS 里是 {sig.to}）")
        if r[2].startswith("升级") != sig.escalate:
            problems.append(f"guard.md「信号」表：{n} 的第三列应以「{'升级' if sig.escalate else '重发'}」开头")
    return problems


KANDEV_VARS = {"{task_id}", "{task_title}", "{step_entry_number}", "{{task_prompt}}"}


def check_placeholders():
    problems = []
    for wf in bw.all_workflows():
        for s in wf["steps"]:
            for m in re.finditer(r"\{+[A-Za-z_][A-Za-z0-9_]*\}+", s.get("prompt", "")):
                if m.group(0) not in KANDEV_VARS:
                    problems.append(f"{wf['name']}「{s['name']}」的 prompt 里有不认识的占位符 {m.group(0)}")
    return problems


def check_block_placement():
    """改措辞时容易悄悄回退的三件事。"""
    import stage
    problems = []
    refresh = (bw.BLOCKS["REFRESH_PM"], bw.BLOCKS["REFRESH_MOD"])
    for wf in bw.all_workflows():
        for s in wf["steps"]:
            p, where = s.get("prompt", ""), f"{wf['name']}「{s['name']}」"
            if any(r in p for r in refresh) and s["name"] not in stage.RESIDENT:
                problems.append(f"{where}带着【刷新】规则，但它不是常驻步骤（守护只在 {sorted(stage.RESIDENT)} 里数唤醒次数）")
            if s["name"] in stage.RESIDENT and not any(r in p for r in refresh):
                problems.append(f"{where}是常驻步骤，却没有【刷新】规则")
            if p.count(bw.BLOCKS["SEVERITY_DEF"]) > 1:
                problems.append(f"{where}里【定级】出现了不止一次")
            if "\\" in p:
                problems.append(f"{where}的 prompt 里有反斜杠（多半是没被解释的 \\n）")
    first = bw.BLOCKS["SEVERITY_DEF"].split("\n")[1][:12]       # 定义正文的开头几个字
    for f in md_files():
        if os.path.relpath(f, ROOT).replace("\\", "/").startswith("mgmt-template/") and first in open(f, encoding="utf-8").read():
            problems.append(f"{os.path.relpath(f, ROOT)} 里又写了一份定级定义（只应在步骤 prompt 的【定级】里）")
    return problems


def check_ma_test():
    if os.environ.get("MA_TEST_NESTED"):      # test_ma.py 在临时安装目录里运行本自检时不再递归
        return []
    return run_test("ma.py", "test_ma.py")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    checks = [("prompts.md", check_prompts), ("链接", check_links), ("步骤名", check_steps),
              ("模板路径", check_template_refs), ("版本", check_version), ("stage 测试", check_stage_test),
              ("check_tasks 测试", check_tasks_test),
              ("check_owns 测试", check_owns_test), ("precommit 测试", check_precommit_test),
              ("接收文档", check_arch_refs), ("步骤结构", check_structure),
              ("模板版本", check_template_version), ("提问清单", check_questions), ("ma 测试", check_ma_test),
              ("步骤名同步", check_stage_names), ("占位符", check_placeholders), ("共享块位置", check_block_placement), ("信号表", check_guard_signals)]
    failed = 0
    for name, fn in checks:
        problems = fn()
        print(f"{'OK  ' if not problems else 'FAIL'} {name}")
        for p in problems:
            print(f"     {p}")
        failed += bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
