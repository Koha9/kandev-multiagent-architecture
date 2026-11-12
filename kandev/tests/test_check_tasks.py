"""check_tasks.py 的测试：python kandev/tests/test_check_tasks.py（也由 check_docs.py 调用）。只用标准库。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mgmt-template", "tools", "check_tasks.py")
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mgmt-template", "modules", "_template", "tasks.json")


def task(tid, owns=None, blocked_by=(), **kw):
    t = {"id": tid, "title": tid, "owns": owns if owns is not None else [f"src/{tid}/"], "blocked_by": list(blocked_by),
         "acceptance": ["AC-1 x"], "tests": [f"pytest tests/{tid} -q"], "refs": [], "ui": False, "boundaries": []}
    t.update(kw)
    return t


def run(tasks, *extra):
    """写临时 tasks.json 并以子进程运行，返回 (退出码, 输出行)。"""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "tasks.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(tasks if isinstance(tasks, str) else {"module": "m", "tasks": tasks}, f)
        r = subprocess.run([sys.executable, TOOL, "--tasks", p, *extra], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.splitlines()


def has(lines, *words):
    return any(all(w in line for w in words) for line in lines)


def main():
    code, out = run([task("a"), task("b", blocked_by=["a"])])
    assert code == 0 and out == ["OK m: 2 个任务"], (code, out)

    code, out = run([task("a"), task("a", owns=["src/z/"])])
    assert code == 1 and has(out, "a", "id 重复"), out

    code, out = run([task("a", owns=["src/x.py"]), task("b", owns=["./src\\x.py "])])    # 相等（规范化后）
    assert code == 1 and has(out, "a 与 b", "owns 重叠"), out
    code, out = run([task("a", owns=["src/a/"]), task("b", owns=["src/a/b.py"])])        # 目录前缀
    assert code == 1 and has(out, "a 与 b", "owns 重叠"), out
    code, out = run([task("a", owns=["src/a"]), task("b", owns=["src/ab.py", "src/a2/"])])  # 相似名，不重叠
    assert code == 0, out

    code, out = run([task("a", tests=[])])
    assert code == 1 and has(out, "a", "tests 为空"), out
    code, out = run([task("a", acceptance=[])])
    assert code == 1 and has(out, "a", "acceptance 为空"), out
    code, out = run([task("a", owns=[])])
    assert code == 1 and has(out, "a", "owns 为空"), out

    code, out = run([task("a", blocked_by=["ghost"])])
    assert code == 1 and has(out, "a", "ghost", "不存在"), out
    code, out = run([task("a", blocked_by=["c"]), task("b", blocked_by=["a"]), task("c", blocked_by=["b"])])
    assert code == 1 and has(out, "依赖成环"), out

    chain = [task("t1"), task("t2", blocked_by=["t1"]), task("t3", blocked_by=["t2"])]
    code, out = run(chain)
    assert code == 0 and not has(out, "WARN"), out                                       # 深度 3 不警告
    code, out = run(chain + [task("t4", blocked_by=["t3"])])
    assert code == 0 and has(out, "WARN", "深度 4"), out                                 # 深度 4 只警告

    code, out = run([task("a", boundaries=["B-1"])], "--boundaries", "B-1,B-3")
    assert code == 1 and has(out, "边界 B-3") and not has(out, "边界 B-1"), out
    code, out = run([task("a", boundaries=["B-1", "B-3"]), task("b")], "--boundaries", "B-1,B-3")
    assert code == 0, out
    code, out = run([task("a", boundaries=["B-1", "B-9"])], "--boundaries", "B-1")
    assert code == 0 and has(out, "WARN", "B-9"), out                                    # 多出的编号只警告
    code, out = run([task("a")])
    assert code == 0, out                                                                # 没传 --boundaries 就跳过

    # dropped / failed 的任务被跳过：不查 owns 重叠、tests、acceptance；不算作边界覆盖
    code, out = run([task("a"), task("b", owns=["src/a/"], status="dropped", tests=[], acceptance=[]),
                     task("c", owns=["src/a/x.py"], status="failed", tests=[])])
    assert code == 0, out
    code, out = run([task("a"), task("b", status="dropped", boundaries=["B-1"])], "--boundaries", "B-1")
    assert code == 1 and has(out, "B-1"), out

    # shared：不参与 owns 重叠；必须是文件；不能同时是别的任务的 owns
    code, out = run([task("a", shared=["requirements.txt", "src/routes.py"]), task("b", shared=["requirements.txt"])])
    assert code == 0, out
    code, out = run([task("a", shared=["src/shared/"])])
    assert code == 1 and has(out, "a", "shared", "目录"), out
    code, out = run([task("a", owns=["requirements.txt"]), task("b", shared=["./requirements.txt"])])
    assert code == 1 and has(out, "a 的 owns", "b 的 shared"), out
    code, out = run([task("a", owns=["src/a/"]), task("b", shared=["src/a/routes.py"])])      # owns 目录覆盖了别人的 shared
    assert code == 1 and has(out, "a 的 owns", "b 的 shared"), out
    code, out = run([task("a", owns=["src/a/"], shared=["src/a/routes.py"])])                  # 自己的 owns 和 shared 不冲突
    assert code == 0, out

    assert run("[]")[0] == 2                                                              # 没有 tasks 键
    assert run("不是对象")[0] == 2                                                         # 顶层不是对象
    r = subprocess.run([sys.executable, TOOL, "--tasks", os.path.join(tempfile.gettempdir(), "no-such-tasks.json")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2, r.stdout                                                    # 文件不存在
    assert subprocess.run([sys.executable, TOOL], capture_output=True).returncode == 2    # 缺参数

    r = subprocess.run([sys.executable, TOOL, "--tasks", TEMPLATE, "--boundaries", "B-1"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"模板 tasks.json 不能通过检查：{r.stdout}"
    print("OK test_check_tasks")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
