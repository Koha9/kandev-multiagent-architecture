"""mgmt_precommit.py 的测试：python kandev/tests/test_mgmt_precommit.py（也由 check_docs.py 调用）。只用标准库。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "mgmt-template", "tools"))
from mgmt_precommit import violations  # noqa: E402

ENV = "project/environment.md"


def ok(scope, *files):
    assert violations(scope, list(files)) == [], (scope, files, violations(scope, list(files)))


def no(scope, *files):
    got = violations(scope, list(files))
    assert got == list(files), (scope, files, got)


def main():
    assert violations("", ["README.md"]) is None and violations("bogus", ["README.md"]) is None   # 无效 scope

    ok("pm-init", "README.md", ENV, "modules/a/tasks.json")
    ok("pm", "README.md", ".gitignore", "project/charter.md", "project/attention.md", "agents/pm/journal.md", "quota/q.json")
    no("pm", ENV, "modules/a/tasks.json", "agents/mod-a/x.md", "agents/guard/stage.md")

    ok("mod:auth", "modules/auth/tasks.json", "agents/mod-auth/journal.md")
    no("mod:auth", "modules/auth/acceptance.md", "modules/other/tasks.json", "modules/auth-fix-1/tasks.json",
       "project/charter.md", ENV, "agents/mod-other/x.md")

    ok("mod:baseline", "modules/baseline/tasks.json", ENV)
    ok("mod:baseline-fix-1", "modules/baseline-fix-1/tasks.json", "agents/mod-baseline-fix-1/j.md", ENV)
    no("mod:baseline-fix-1", "modules/baseline/tasks.json", "modules/baseline-fix-1/acceptance.md")
    no("mod:auth", ENV)                                         # 只有 baseline 能碰 environment.md
    no("mod:auth-fix-1", ENV)

    # 修复模块：只有自己的目录，不含原模块（前缀天然不重叠），反过来原模块也碰不到修复模块
    ok("mod:auth-fix-2", "modules/auth-fix-2/tasks.json", "agents/mod-auth-fix-2/journal.md")
    no("mod:auth-fix-2", "modules/auth/tasks.json", "agents/mod-auth/journal.md", "modules/auth-fix-1/tasks.json")

    ok("mod-audit:auth", "modules/auth/acceptance.md")
    no("mod-audit:auth", "modules/auth/tasks.json", "modules/other/acceptance.md", "project/final-report.md")

    ok("audit", "project/final-report.md")
    no("audit", "project/attention.md", ENV, "modules/auth/acceptance.md", "project/final-report.md.bak")

    ok("dev:auth-01", "evidence/auth-01/test.log")
    no("dev:auth-01", "evidence/auth-02/test.log", "modules/auth/tasks.json")
    ok("guard", "agents/guard/stage.md")
    no("guard", "agents/pm/x.md")
    print("OK test_mgmt_precommit")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
