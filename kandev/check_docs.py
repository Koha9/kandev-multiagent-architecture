"""本仓库的自检：文档、prompt 源和模板是否一致。修改 workflow 后、部署前运行：python kandev/check_docs.py

检查项：
  1. docs/prompts.md 与 `build_workflows.py dump` 的输出一致（prompt 只能改脚本后重新生成）
  2. 所有 Markdown 中的本地链接都能解析
  3. docs/workflow.md 中 W1 / W2 / W3 表格的步骤名与 build_workflows.py 一致
  4. prompt 中引用的 <mgmt_root>/... 路径在 mgmt-template 中存在（运行时生成的路径除外）
  5. docs/workflow.md 标题中的版本号与 VERSION 一致
  6. stage.py 的离线回归测试通过
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


def check_version():
    first = open(os.path.join(ROOT, "docs", "workflow.md"), encoding="utf-8").readline()
    return [] if f"（{bw.VERSION}）" in first else [f"docs/workflow.md 标题版本与 VERSION={bw.VERSION} 不一致：{first.strip()}"]


def check_stage_test():
    r = subprocess.run([sys.executable, os.path.join(HERE, "tests", "test_stage.py")],
                       capture_output=True, text=True, encoding="utf-8")
    return [] if r.returncode == 0 else [f"stage.py 回归测试失败：{(r.stdout + r.stderr).strip()[-500:]}"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    checks = [("prompts.md", check_prompts), ("链接", check_links), ("步骤名", check_steps),
              ("模板路径", check_template_refs), ("版本", check_version), ("stage 测试", check_stage_test)]
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
