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
退出码：0 全部通过；1 有问题（逐条列出）。只用标准库。
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_workflows as bw  # noqa: E402

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

        class A:
            pass
        a = A()
        a.out = out
        with contextlib.redirect_stdout(io.StringIO()):
            bw.cmd_dump(a)
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


def check_version():
    first = open(os.path.join(ROOT, "docs", "workflow.md"), encoding="utf-8").readline()
    return [] if f"（{bw.VERSION}）" in first else [f"docs/workflow.md 标题版本与 VERSION={bw.VERSION} 不一致：{first.strip()}"]


def check_stage_test():
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", "test_stage.py")],
                       capture_output=True, text=True, encoding="utf-8")
    return [] if r.returncode == 0 else [f"stage.py 回归测试失败：{(r.stdout + r.stderr).strip()[-500:]}"]


def run_test(name, script):
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", script)],
                       capture_output=True, text=True, encoding="utf-8")
    return [] if r.returncode == 0 else [f"{name} 测试失败：{(r.stdout + r.stderr).strip()[-500:]}"]


def check_tasks_test():
    return run_test("check_tasks.py", "test_check_tasks.py")


def check_owns_test():
    return run_test("check_owns.py", "test_check_owns.py")


def check_precommit_test():
    return run_test("mgmt_precommit.py", "test_mgmt_precommit.py")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    checks = [("prompts.md", check_prompts), ("链接", check_links), ("步骤名", check_steps),
              ("模板路径", check_template_refs), ("版本", check_version), ("stage 测试", check_stage_test),
              ("check_tasks 测试", check_tasks_test),
              ("check_owns 测试", check_owns_test), ("precommit 测试", check_precommit_test),
              ("接收文档", check_arch_refs)]
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
