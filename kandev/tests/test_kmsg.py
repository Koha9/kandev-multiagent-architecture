"""mgmt-template/tools/kmsg.py 的测试：python kandev/tests/test_kmsg.py（也由 check_docs.py 调用）。只用标准库。
本文件里每个 test_ 开头的函数都会自动运行。"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mgmt-template", "tools", "kmsg.py")
SELF = "11111111-2222-3333-4444-555555555555"
PARENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
LINE = f"parent: mod:auth @ task {PARENT} session sess-0123abcd"
ID = re.compile(r"^id: M-dev\.auth-02-\d{6}-\d{6}$")


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else None), r.stderr


def common(parent=LINE):
    return ["--self-scope", "dev:auth-02", "--self-task", SELF, "--parent", parent]


def report(parent=LINE, *extra):
    return run("report", *common(parent), "--refs", "abc1234",
               "--evidence", "abc1234；合并门禁 npm test：通过", *extra)


def test_report_format():
    code, out, err = report()
    assert code == 0, err
    assert out["task_id"] == PARENT and out["session_id"] == "sess-0123abcd", out
    lines = out["prompt"].split("\n")
    assert ID.match(lines[1]), lines[1]
    lines[1] = "id: X"
    assert lines == [
        "[KMSG v1]", "id: X", "type: REPORT",
        f"from: dev:auth-02 @ task {SELF}", f"to: mod:auth @ task {PARENT}",
        "reply: none", "reply_to: -", "due: -", "refs: abc1234", "---",
        "结果：done", "摘要：auth-02 已合入 mod/auth", "证据：abc1234；合并门禁 npm test：通过",
        "偏差：无", "未完成 / 无法验证：无", "需要决定：无",
    ], lines


def test_report_summary_override():
    code, out, _ = report(LINE, "--summary", "auth-02 已合入 mod/auth（进入时已合入）")
    assert code == 0 and "摘要：auth-02 已合入 mod/auth（进入时已合入）" in out["prompt"].split("\n"), out


def test_escalate_format():
    code, out, err = run("escalate", *common(), "--problem", "合并门禁失败：npm test", "--impact", "auth-03",
                         "--option", "A. 回「开发」修复（推荐，失败在本任务范围内）", "--option", "拆分任务")
    assert code == 0, err
    lines = out["prompt"].split("\n")
    assert ID.match(lines[1]), lines[1]
    lines[1] = "id: X"
    assert lines == [
        "[KMSG v1]", "id: X", "type: ESCALATE",
        f"from: dev:auth-02 @ task {SELF}", f"to: mod:auth @ task {PARENT}",
        "reply: required", "reply_to: -", "due: next-wake", "refs: -", "---",
        "问题：合并门禁失败：npm test", "影响：auth-03", "选项：",
        "  A. 回「开发」修复（推荐，失败在本任务范围内）", "  B. 拆分任务",
        "需要谁决定：mod:auth", "等待期间我将：暂停",
    ], lines


def test_parent_variants():
    for line in (f"parent=mod:auth @ task {PARENT} session sess-0123abcd",
                 f"mod:auth @ task {PARENT} session sess-0123abcd",
                 f"  parent:   mod:auth   @   task   {PARENT}   session   sess-0123abcd  ",
                 f"parent：mod:auth@task {PARENT} session sess-0123abcd"):
        code, out, err = report(line)
        assert code == 0, (line, err)
        assert (out["task_id"], out["session_id"]) == (PARENT, "sess-0123abcd"), (line, out)
        assert f"to: mod:auth @ task {PARENT}" in out["prompt"], (line, out["prompt"])


def test_missing_session_is_null():
    code, out, err = report(f"parent: mod:auth @ task {PARENT}")
    assert code == 0, err
    assert out["task_id"] == PARENT and out["session_id"] is None, out


def test_bad_parent_exit_2():
    for line in ("parent: mod:auth", "parent: mod:auth @ task 1234", ""):
        code, out, err = report(line)
        assert code == 2 and "task" in err, (line, code, err)


def test_missing_required_exit_2():
    code, _, _ = run("report", *common(), "--refs", "abc1234")      # 缺 --evidence
    assert code == 2


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
        except Exception:
            print(f"FAIL {name}", file=sys.stderr)
            raise
    print("OK test_kmsg")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
