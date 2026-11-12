"""check_owns.py 的测试：python kandev/tests/test_check_owns.py（也由 check_docs.py 调用）。只用标准库，需要本机有 git。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "mgmt-template", "tools", "check_owns.py")


def git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


def write(repo, rel, text="x"):
    p = os.path.join(repo, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def run(repo, task):
    tasks = os.path.join(repo, "..", os.path.basename(repo) + "-tasks.json")
    with open(tasks, "w", encoding="utf-8") as f:
        json.dump({"tasks": [task]}, f)
    r = subprocess.run([sys.executable, TOOL, "--tasks", tasks, "--task", task["id"], "--base", "main", "--repo", repo],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.splitlines()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        git(repo, "init", "-q", "-b", "main")
        write(repo, "README.md")
        write(repo, "requirements.txt", "a\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
        task = {"id": "t1", "owns": ["src/a/", "tests/test_a.py"], "shared": ["requirements.txt"]}

        code, out = run(repo, task)                                       # 没有改动
        assert code == 0 and not any(l.startswith("SHARED") for l in out), out

        write(repo, "src/a/x.py")
        write(repo, "tests/test_a.py")
        code, out = run(repo, task)                                       # 只改 owns
        assert code == 0 and not any(l.startswith("SHARED") for l in out), out

        write(repo, "requirements.txt", "a\nb\n")                         # 改 shared：允许，单独列出
        code, out = run(repo, task)
        assert code == 0 and "SHARED requirements.txt" in out, out

        write(repo, "src/b/y.py")                                         # 越界：退出码 1，shared 仍列出
        code, out = run(repo, task)
        assert code == 1 and out[0].startswith("VIOLATION") and "  src/b/y.py" in out, out
        assert "SHARED requirements.txt" in out, out

        os.remove(os.path.join(repo, "src", "b", "y.py"))
        code, out = run(repo, {**task, "shared": []})                     # 没声明 shared：改它就是越界
        assert code == 1 and "  requirements.txt" in out, out
        code, out = run(repo, {**task, "shared": ["requirements.txt"], "owns": ["src/a/", "tests/test_a.py", "requirements.txt"]})
        assert code == 0 and not any(l.startswith("SHARED") for l in out), out   # owns 优先，不算 SHARED
        code, out = run(repo, {"id": "t1", "owns": []})
        assert code == 2, out
    print("OK test_check_owns")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
