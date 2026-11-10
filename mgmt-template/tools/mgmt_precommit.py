"""管理目录的 pre-commit 钩子：按提交者的 scope 拒绝提交别人担当的文件（单写者）。

安装（在管理目录根运行一次）：
  python tools/mgmt_precommit.py --install
它会写入 .git/hooks/pre-commit，钩子用当前的 Python 解释器调用本文件。

提交时用环境变量 MGMT_SCOPE 声明自己的 scope：
  PowerShell： $env:MGMT_SCOPE = "mod:auth"; git commit -m "..."; Remove-Item Env:MGMT_SCOPE
  sh：         MGMT_SCOPE=mod:auth git commit -m "..."

各 scope 允许提交的路径（相对管理目录根）：
  pm-init    全部（只用于立项规划首次复制模板后的那一次提交）
  pm         README.md、.gitignore、project/、agents/pm/、quota/
  mod:<m>    modules/<m>/、agents/mod-<m>/
  dev:<id>   evidence/<id>/
  guard      agents/guard/
没有 MGMT_SCOPE 或有越界文件时拒绝提交。只用标准库。
"""
import os
import subprocess
import sys


def allowed_prefixes(scope):
    if scope == "pm-init":
        return [""]
    if scope == "pm":
        return ["README.md", ".gitignore", "project/", "agents/pm/", "quota/"]
    if scope == "guard":
        return ["agents/guard/"]
    if scope.startswith("mod:"):
        m = scope[4:]
        return [f"modules/{m}/", f"agents/mod-{m}/"]
    if scope.startswith("dev:"):
        return [f"evidence/{scope[4:]}/"]
    return None


def staged_files():
    r = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, encoding="utf-8")
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def check():
    scope = os.environ.get("MGMT_SCOPE", "").strip()
    prefixes = allowed_prefixes(scope) if scope else None
    if prefixes is None:
        print(f"[mgmt pre-commit] 拒绝：需要用 MGMT_SCOPE 声明 scope（当前：{scope or '未设置'}）。见 tools/mgmt_precommit.py。")
        return 1
    bad = [f for f in staged_files() if not any(f == p or f.startswith(p) for p in prefixes)]
    if bad:
        print(f"[mgmt pre-commit] 拒绝：scope={scope} 不能提交以下文件（它们由别人担当）：")
        for f in bad:
            print(f"  {f}")
        print("用 git restore --staged <文件>（仓库还没有提交时用 git rm --cached <文件>）取消暂存，只提交自己担当的路径。")
        return 1
    return 0


def install():
    hook = os.path.join(".git", "hooks", "pre-commit")
    if not os.path.isdir(os.path.dirname(hook)):
        print("ERROR 当前目录不是 git 仓库根")
        return 2
    py = sys.executable.replace("\\", "/")
    me = os.path.abspath(__file__).replace("\\", "/")
    with open(hook, "w", encoding="utf-8", newline="\n") as f:
        f.write(f'#!/bin/sh\nexec "{py}" "{me}"\n')
    print(f"OK 已安装 {hook}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(install() if "--install" in sys.argv else check())
