"""检查模块的 tasks.json 形式是否合格（模块 agent 在创建开发子任务之前运行）。

用法：
  python <mgmt_root>/tools/check_tasks.py --tasks <mgmt_root>/modules/<模块>/tasks.json [--boundaries B-1,B-3]

检查项（status 为 dropped / failed 的任务不参与第 2、3 项的检查，但仍计入第 1、4 项）：
  1. 任务 id 非空且唯一
  2. 每个任务 owns 非空；不同任务的 owns 不重叠
     （规范化后路径相等，或一个是另一个的目录前缀；`src/a/` 与 `src/a/b.py` 重叠，`src/a` 与 `src/ab.py` 不重叠）
     可选字段 shared：多个任务都可以改的共享文件（依赖清单、路由注册等，每个任务只追加自己的条目）。
     shared 不参与任务之间的 owns 重叠检查（不同任务可以有相同的 shared 路径），但必须是具体文件路径
     （以 / 结尾的报问题），并且一个路径不能既是某个任务的 owns（含目录前缀）又出现在另一个任务的 shared 里
  3. 每个任务 acceptance 非空、tests（可直接执行的测试命令）非空
  4. blocked_by 引用的 id 都存在；依赖无环；依赖链深度（最长路径上的任务数）超过 3 时给出警告（WARN，不影响退出码）
  5. 给了 --boundaries 时：其中每个编号都至少出现在某个任务的 boundaries 里；任务里出现了 --boundaries 之外的编号时给出警告
退出码：0 全部通过（可以有 WARN）；1 有问题（逐条列出，每条一行）；2 用法或文件错误。只用标准库。
"""
import argparse
import json
import sys

SKIPPED = {"dropped", "failed"}
MAX_DEPTH = 3


def norm(path):
    p = str(path).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def overlap(a, b):
    """两个已规范化的 owns 路径是否重叠：相等，或一个是另一个的目录前缀。"""
    if not a or not b:
        return False
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        prefix = x if x.endswith("/") else x + "/"
        if y.startswith(prefix):
            return True
    return False


def as_list(task, key):
    v = task.get(key)
    return v if isinstance(v, list) else []


def find_cycle(graph):
    """graph: id -> [id]。有环返回环上的 id 列表，否则 None。"""
    state, stack = {}, []

    def visit(n):
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if m not in state:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        state[n] = 2
        return None

    for n in graph:
        if n not in state:
            found = visit(n)
            if found:
                return found
    return None


def longest_chain(graph):
    """无环图中最长依赖链（任务数，链上的 id）。"""
    memo = {}

    def chain(n):
        if n not in memo:
            memo[n] = max((chain(m) for m in graph.get(n, [])), key=len, default=[]) + [n]
        return memo[n]

    best = max((chain(n) for n in graph), key=len, default=[])
    return len(best), best


def check(tasks, boundaries=None):
    """返回 (problems, warnings)，各为字符串列表。"""
    problems, warnings = [], []
    seen = {}
    for i, t in enumerate(tasks):
        tid = t.get("id")
        if not isinstance(tid, str) or not tid.strip():
            problems.append(f"第 {i + 1} 个任务: id 为空")
        elif tid in seen:
            problems.append(f"{tid}: id 重复（与第 {seen[tid] + 1} 个任务相同）")
        else:
            seen[tid] = i
    ids = set(seen)
    active = [t for t in tasks if t.get("id") in ids and t.get("status") not in SKIPPED]

    owns, shared = {}, {}
    for t in active:
        owns[t["id"]] = [n for n in (norm(p) for p in as_list(t, "owns") if isinstance(p, str)) if n]
        if not owns[t["id"]]:
            problems.append(f"{t['id']}: owns 为空")
        if not [a for a in as_list(t, "acceptance") if isinstance(a, str) and a.strip()]:
            problems.append(f"{t['id']}: acceptance 为空")
        if not [c for c in as_list(t, "tests") if isinstance(c, str) and c.strip()]:
            problems.append(f"{t['id']}: tests 为空（需要可直接执行的测试命令）")
        shared[t["id"]] = [n for n in (norm(p) for p in as_list(t, "shared") if isinstance(p, str)) if n]
        for p in shared[t["id"]]:
            if p.endswith("/"):
                problems.append(f"{t['id']}: shared 中的 {p} 是目录，必须是具体文件路径")
    for x in range(len(active)):
        for y in range(x + 1, len(active)):
            a, b = active[x]["id"], active[y]["id"]
            if a == b:
                continue
            for pa in owns[a]:
                for pb in owns[b]:
                    if overlap(pa, pb):
                        problems.append(f"{a} 与 {b}: owns 重叠（{pa} 与 {pb}）")
            for x_id, y_id in ((a, b), (b, a)):   # 一个任务的 owns 不能覆盖另一个任务的 shared
                for po in owns[x_id]:
                    for ps in shared[y_id]:
                        if overlap(po, ps):
                            problems.append(f"{x_id} 的 owns（{po}）与 {y_id} 的 shared（{ps}）冲突：共享文件不能归某个任务独占")

    graph = {}
    for t in tasks:
        tid = t.get("id")
        if tid not in ids or tid in graph:
            continue
        deps = [d for d in as_list(t, "blocked_by") if isinstance(d, str)]
        for d in deps:
            if d not in ids:
                problems.append(f"{tid}: blocked_by 引用的任务 {d} 不存在")
        if tid in deps:
            problems.append(f"{tid}: blocked_by 包含自己")
        graph[tid] = [d for d in deps if d in ids and d != tid]
    cycle = find_cycle(graph)
    if cycle:
        problems.append("依赖成环: " + " -> ".join(cycle))
    else:
        n, chain = longest_chain(graph)
        if n > MAX_DEPTH:
            warnings.append(f"依赖链深度 {n} 超过 {MAX_DEPTH}（{' -> '.join(chain)}），考虑拆得更扁平")

    if boundaries is not None:
        used = {}
        for t in tasks:
            for b in as_list(t, "boundaries"):
                used.setdefault(b, []).append((t.get("id"), t.get("status") not in SKIPPED))
        for b in boundaries:
            if not any(live for _, live in used.get(b, [])):
                problems.append(f"边界 {b}: 没有任何任务的 boundaries 包含它")
        for b, who in used.items():
            if b not in boundaries:
                warnings.append(f"{', '.join(str(i) for i, _ in who)}: boundaries 中的 {b} 不在 --boundaries 给出的范围内")
    return problems, warnings


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--tasks", required=True, help="modules/<模块>/tasks.json")
    p.add_argument("--boundaries", help="charter 中与本模块有关的跨模块边界编号，逗号分隔，例如 B-1,B-3")
    a = p.parse_args()
    try:
        with open(a.tasks, encoding="utf-8") as f:
            doc = json.load(f)
        tasks = doc["tasks"]
        if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
            raise ValueError("tasks 必须是对象列表")
    except (OSError, KeyError, TypeError, ValueError) as e:   # JSONDecodeError 是 ValueError 的子类
        print(f"ERROR 读取 {a.tasks} 失败：{e!r}")
        return 2
    boundaries = None
    if a.boundaries is not None:
        boundaries = [b.strip() for b in a.boundaries.split(",") if b.strip()]
    problems, warnings = check(tasks, boundaries)
    for w in warnings:
        print(f"WARN {w}")
    if problems:
        for msg in problems:
            print(f"PROBLEM {msg}")
        print(f"FAIL {len(problems)} 个问题")
        return 1
    print(f"OK {doc.get('module') or '?'}: {len(tasks)} 个任务")
    return 0


if __name__ == "__main__":
    sys.exit(main())
