"""检查一个开发任务的改动是否都在 tasks.json 的 owns 范围内。

用法（在任务的 worktree 里运行）：
  python <mgmt_root>/tools/check_owns.py --tasks <mgmt_root>/modules/<模块>/tasks.json --task <任务id> --base mod/<模块>

检查的改动 = 已提交（<base>...HEAD）+ 未提交（暂存和未暂存）+ 未跟踪的文件。
owns 的写法：以 / 结尾表示目录前缀；含 * ? [ 的按通配符匹配；其他按完整路径匹配（也匹配以它为前缀的目录）。
退出码：0 全部在范围内；1 有越界文件（逐行列出）；2 参数或环境错误。只用标准库。
"""
import argparse
import fnmatch
import json
import subprocess
import sys


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return [line.strip().replace("\\", "/") for line in r.stdout.splitlines() if line.strip()]


def changed_files(repo, base):
    files = set(git(repo, "diff", "--name-only", f"{base}...HEAD"))
    files |= set(git(repo, "diff", "--name-only", "HEAD"))
    files |= set(git(repo, "ls-files", "--others", "--exclude-standard"))
    return sorted(files)


def owned(path, owns):
    for pat in owns:
        pat = pat.replace("\\", "/")
        if pat.startswith("./"):
            pat = pat[2:]
        if pat.endswith("/"):
            if path.startswith(pat):
                return True
        elif any(c in pat for c in "*?["):
            if fnmatch.fnmatchcase(path, pat):
                return True
        elif path == pat or path.startswith(pat.rstrip("/") + "/"):
            return True
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tasks", required=True, help="modules/<模块>/tasks.json")
    p.add_argument("--task", required=True, help="任务 id，例如 auth-02")
    p.add_argument("--base", required=True, help="比较基准，例如 mod/auth")
    p.add_argument("--repo", default=".", help="worktree 路径（默认当前目录）")
    a = p.parse_args()
    try:
        tasks = json.load(open(a.tasks, encoding="utf-8"))["tasks"]
        task = next(t for t in tasks if t["id"] == a.task)
        owns = task.get("owns") or []
        files = changed_files(a.repo, a.base)
    except StopIteration:
        print(f"ERROR 在 {a.tasks} 中找不到任务 {a.task}")
        return 2
    except (OSError, KeyError, json.JSONDecodeError, RuntimeError) as e:
        print(f"ERROR {e}")
        return 2
    if not owns:
        print(f"ERROR 任务 {a.task} 没有 owns")
        return 2
    bad = [f for f in files if not owned(f, owns)]
    if bad:
        print(f"VIOLATION {a.task}: {len(bad)} 个文件不在 owns 范围内（owns={owns}）")
        for f in bad:
            print(f"  {f}")
        return 1
    print(f"OK {a.task}: {len(files)} 个改动文件都在 owns 范围内")
    return 0


if __name__ == "__main__":
    sys.exit(main())
