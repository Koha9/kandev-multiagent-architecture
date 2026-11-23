"""W1「接收」步骤用的只读探测：python kandev/intake.py probe [--repo <路径>] [--project <名>] [--base <分支>]

把接收步骤里容易做错的检测和缺省值解析集中到一处，打印一个 JSON。只读：不改仓库、不 fetch、不建目录、不连 Kandev。
问什么、怎么问仍由 docs/intake.md 规定；本脚本只回答"现状是什么、部署缺省值解析成什么"。只用标准库。

输出的字段：
  repo         {ok, path}                      主仓库（不是任务的 worktree）
  base         {value, source, exists, upstream, needs_confirm}
  remotes      [{name, url}]；remote = 交付用的远端名（基线分支的 upstream 所在远端，没有时 origin，再没有第一个）
  ci_files     仓库里的 CI 配置
  gh           ok | unauthenticated | missing    （开 PR 和查远端 CI 用）
  push_branch  {suggested, exists_remote, checked, note}   pr 模式的缺省分支；远端已有且不是基线分支的祖先时加日期后缀
  mgmt_root    {suggested, state: new | same_project | other_project, note}
  defaults     部署缺省值（custom/project-defaults.json，缺的键已按出厂值补上）
  resolved     各项解析结果：值是 "ask" 表示要问用户；*_no_ask 是不提问（autonomy 4）时采用的值。
               已经过组合检查（check_combo），不会出现 remote none + ci remote 这样的矛盾
  notes        要告诉用户或写进缺省值清单的说明（改正了什么、哪些没查到）
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_FILE = "custom/project-defaults.json"
# 键 → (允许的值, 文件或键缺失时的值)。旧值的换算见 load_defaults。
DEFAULT_KEYS = {
    "review_access": (("ask", "local", "remote_only"), "ask"),
    "remote": (("auto", "none", "push", "pr"), "auto"),
    "ci": (("auto", "none", "local", "remote"), "auto"),
    "autonomy": (("ask", "1", "2", "3", "4"), "ask"),
    "plan_only": (("ask", "true", "false"), "ask"),
    "run_policy": (("ask", "active", "conservative"), "ask"),
    "integration_test": (("auto", "off"), "auto"),
    "paid_calls": (("ask", "deny", "allow"), "ask"),
}
CI_PATHS = (".github/workflows", ".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile", ".circleci")
NET_TIMEOUT = 15


def git(repo, *args, timeout=30):
    """(退出码, 标准输出)。不弹凭据提示；超时或没有 git 时退出码 -1。"""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return p.returncode, p.stdout.strip()


def load_defaults(arch_root):
    """部署缺省值。文件不存在、读不出、缺键、值不认识：按 DEFAULT_KEYS 的缺失值。
    旧值：integration_test=ask → auto；review_access=remote → remote_only。返回 (值, 说明列表)。"""
    path, raw, notes = os.path.join(arch_root, *DEFAULTS_FILE.split("/")), {}, []
    try:
        raw = json.load(open(path, encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raw, notes = {}, [f"{DEFAULTS_FILE} 不是 JSON 对象，按出厂缺省处理"]
    except FileNotFoundError:
        notes.append(f"没有 {DEFAULTS_FILE}，按出厂缺省处理")
    except (OSError, ValueError) as e:
        notes.append(f"{DEFAULTS_FILE} 读不出（{e}），按出厂缺省处理")
    out = {}
    for key, (allowed, missing) in DEFAULT_KEYS.items():
        v = str(raw.get(key, missing)).strip().lower()
        if key == "integration_test" and v == "ask":
            v = "auto"
        if key == "review_access" and v == "remote":
            v = "remote_only"
        if v not in allowed:
            notes.append(f"{key}={raw.get(key)!r} 不认识，按 {missing}")
            v = missing
        out[key] = v
    return out, notes


def resolve(defaults, has_remote, has_upstream, ci_files, gh="ok", base="", project="", notes=None):
    """部署缺省值 + 检测结果 → 各项取值。"ask" = 要问用户；*_no_ask = 不提问时用的值；*_recommend = 提问时的推荐答案。
    结果先过一遍 check_combo，不会给出自相矛盾的组合（例如 remote none + ci remote）；改了什么写进 notes。"""
    notes = [] if notes is None else notes
    d, remote_only = defaults, defaults["review_access"] == "remote_only"
    if not has_remote:
        remote = remote_no_ask = "none"
        if d["remote"] in ("push", "pr"):
            notes.append(f"部署缺省 remote={d['remote']}，但仓库没有远端：remote 取 none")
        if remote_only:
            notes.append("部署时声明只能在远端审查（review_access=remote_only），但仓库没有远端：只能在本机审查，"
                         "remote 取 none，请在确认汇总或摘要里告诉用户")
    elif d["remote"] != "auto":
        remote = remote_no_ask = d["remote"]
    else:
        remote, remote_no_ask = "ask", ("pr" if remote_only else "none")
    # 推荐 pr 的条件：声明了只能在远端审查；或基线分支有 upstream 且 gh 可用（开不了 PR 时不把 pr 当推荐）
    recommend = "none"
    if has_remote and (remote_only or (has_upstream and gh == "ok")):
        recommend = "pr"
    if has_remote and gh != "ok" and (recommend == "pr" or "pr" in (remote, remote_no_ask)):
        notes.append(f"gh 不可用（{gh}）：pr 只能推分支，PR 要用户自己创建，远端 CI 结果也查不到")
    ci = d["ci"] if d["ci"] != "auto" else ("local" if ci_files else "none")
    ci_no_ask = ci
    if remote == "ask":
        if ci == "remote":
            notes.append("ci: remote 需要推送：用户在 Q9′ 选 none 时改为 local")
        fixed, more = check_combo(remote_no_ask, None, base, ci, project)
        ci_no_ask = fixed["ci"]
        notes += [f"不提问时：{n}" for n in more]
    else:
        fixed, more = check_combo(remote, None, base, ci, project)
        ci = ci_no_ask = fixed["ci"]
        notes += more
    return {
        "autonomy": d["autonomy"],
        "remote": remote, "remote_recommend": recommend, "remote_no_ask": remote_no_ask,
        "ci": ci, "ci_no_ask": ci_no_ask,
        "plan_only": d["plan_only"], "plan_only_no_ask": "false" if d["plan_only"] == "ask" else d["plan_only"],
        "integration_test": d["integration_test"],
        "run_policy": d["run_policy"], "run_policy_no_ask": "active" if d["run_policy"] == "ask" else d["run_policy"],
        "paid_calls": d["paid_calls"],
    }


def check_combo(remote, push_branch, base, ci, project):
    """头里 remote / push_branch / ci 的组合检查（原样放行时也查）。返回 (改正后的 dict, 说明列表)。"""
    fixed, notes = {"remote": remote, "push_branch": push_branch, "ci": ci}, []
    if remote == "pr" and (not push_branch or push_branch == base):
        fixed["push_branch"] = f"ma/{project}"
        if push_branch:
            notes.append(f"remote: pr 的 push_branch 不能是基线分支，改为 ma/{project}")
    if remote == "push" and not push_branch:
        fixed["push_branch"] = base
    if ci == "remote" and remote in ("none", "", None):
        fixed["ci"] = "local"
        notes.append("ci: remote 需要推送，remote 是 none，改为 local")
    if remote == "push" and fixed["push_branch"] == base and fixed["ci"] == "remote":
        notes.append("提醒：remote: push 到基线分支且 ci: remote，CI 失败时远端基线分支已被推送（要先看 CI 结果请用 pr）")
    return fixed, notes


def find_repo(start):
    code, out = git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code != 0 or not out:
        return None
    out = os.path.normpath(out)
    return os.path.dirname(out) if os.path.basename(out) == ".git" else out


def probe_base(repo, wanted):
    if wanted:
        value, source = wanted, "指定"
    else:
        code, value = git(repo, "symbolic-ref", "--short", "HEAD")
        value, source = (value, "主仓库当前分支") if code == 0 and value else ("", "推导不出")
    exists = bool(value) and git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{value}")[0] == 0
    code, up = git(repo, "rev-parse", "--abbrev-ref", f"{value}@{{upstream}}") if exists else (1, "")
    return {"value": value, "source": source, "exists": exists, "upstream": up if code == 0 and up else None,
            "needs_confirm": not exists or (not wanted and value not in ("main", "master"))}


def probe_remotes(repo, upstream):
    code, out = git(repo, "remote")
    names = [n for n in out.split("\n") if n] if code == 0 else []
    remotes = [{"name": n, "url": git(repo, "remote", "get-url", n)[1]} for n in names]
    pick = None
    if upstream and upstream.split("/")[0] in names:
        pick = upstream.split("/")[0]
    elif names:
        pick = "origin" if "origin" in names else names[0]
    return remotes, pick


def probe_gh(repo):
    try:
        p = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=NET_TIMEOUT, cwd=repo)
    except FileNotFoundError:
        return "missing"
    except (OSError, subprocess.TimeoutExpired):
        return "unauthenticated"
    return "ok" if p.returncode == 0 else "unauthenticated"


def probe_push_branch(repo, remote, project, base, wanted, now):
    """pr 模式缺省 ma/<project>。远端已有同名分支、且它不是基线分支的祖先（上一个项目留下的）→ 建议加日期后缀。
    用户写明的分支名（wanted）不改，只给说明。不 fetch：远端的 commit 本地没有时按"不是祖先"处理。"""
    name = wanted or f"ma/{project}"
    out = {"suggested": name, "exists_remote": None, "checked": False, "note": None}
    if not remote:
        return out
    code, text = git(repo, "ls-remote", "--heads", remote, name, timeout=NET_TIMEOUT)
    if code != 0:
        out["note"] = f"查不到远端 {remote}（没有网络或没有权限），没有检查分支是否已存在"
        return out
    def taken(text):
        """ls-remote 的输出里有这个分支，且它不是基线分支的祖先（推上去会被拒绝）。"""
        sha = text.split()[0] if text.split() else None
        return bool(sha) and not (base and git(repo, "merge-base", "--is-ancestor", sha, base)[0] == 0)

    out.update(checked=True, exists_remote=bool(text.split()))
    if taken(text):
        if wanted:
            out["note"] = f"远端已有 {name}，且不是基线分支的祖先：推送时可能被拒绝，请确认"
            return out
        dated = f"{name}-{now:%Y%m%d}"
        for cand in [dated] + [f"{dated}-{i}" for i in range(2, 10)]:     # 同一天的第二个项目：再加序号
            code, text = git(repo, "ls-remote", "--heads", remote, cand, timeout=NET_TIMEOUT)
            if code != 0 or not taken(text):
                break
        out["suggested"] = cand
        out["note"] = f"远端已有 {name}（以前的项目留下的），改用 {cand}"
    return out


def probe_mgmt_root(repo, project, wanted, now):
    path = wanted or os.path.join(os.path.dirname(repo), os.path.basename(repo) + "-mgmt")
    out = {"suggested": path, "state": "new", "note": None}
    if os.path.isdir(path) and os.listdir(path):
        try:
            same = json.load(open(os.path.join(path, "project", "registry.json"), encoding="utf-8-sig")).get("project") == project
        except (OSError, ValueError, AttributeError):
            same = False
        if same:
            out.update(state="same_project", note="继续已有项目（registry.json 的 project 相同）")
        else:
            out["state"] = "other_project"
            if wanted:
                out["note"] = "用户写明的路径已被别的项目占用：请用户另给路径"
            else:
                out["suggested"] = f"{path}-{now:%Y%m%d-%H%M}"
                out["note"] = f"{path} 属于别的项目，改用带时间后缀的路径"
    inside = os.path.commonpath([os.path.abspath(out["suggested"]), repo]) == repo if _same_drive(out["suggested"], repo) else False
    if inside:
        out["note"] = "管理目录不能在仓库之内：请用户另给路径"
        out["state"] = "invalid"
    return out


def _same_drive(a, b):
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def probe(repo=None, project=None, base=None, push_branch=None, mgmt_root=None, arch_root=None, now=None, gh=None):
    now = now or datetime.now()
    arch_root = arch_root or os.path.dirname(HERE)
    defaults, notes = load_defaults(arch_root)
    repo = find_repo(repo or os.getcwd())
    if not repo:
        return {"repo": {"ok": False, "path": None}, "defaults": defaults, "notes": notes + ["找不到 git 仓库：请用户给出主仓库的绝对路径"]}
    project = project or os.path.basename(repo)
    b = probe_base(repo, base)
    remotes, remote = probe_remotes(repo, b["upstream"])
    ci_files = [p for p in CI_PATHS if os.path.exists(os.path.join(repo, *p.split("/")))]
    gh = (gh or probe_gh(repo)) if remotes else "missing"
    pb = probe_push_branch(repo, remote, project, b["value"] if b["exists"] else None, push_branch, now)
    resolved = resolve(defaults, bool(remotes), bool(b["upstream"]), ci_files, gh, b["value"], project, notes)
    if push_branch and resolved["remote"] != "ask":       # 用户写明了 push_branch：连同它再查一遍组合
        fixed, more = check_combo(resolved["remote"], push_branch, b["value"], resolved["ci"], project)
        if fixed["push_branch"] != push_branch:
            pb.update(suggested=fixed["push_branch"], note="；".join(more))
        notes += [n for n in more if n not in notes]
    return {
        "repo": {"ok": True, "path": repo}, "project": project, "base": b,
        "remotes": remotes, "remote": remote, "ci_files": ci_files, "gh": gh,
        "push_branch": pb,
        "mgmt_root": probe_mgmt_root(repo, project, mgmt_root, now),
        "defaults": defaults, "resolved": resolved, "notes": notes,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="W1「接收」步骤的只读探测")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="检测仓库现状并解析部署缺省值，打印 JSON")
    p.add_argument("--repo", help="仓库或其 worktree 中的任意路径；缺省为当前目录")
    p.add_argument("--project", help="项目名；缺省为仓库目录名")
    p.add_argument("--base", help="用户写明的基线分支；缺省为主仓库当前分支")
    p.add_argument("--push-branch", help="用户写明的 push_branch")
    p.add_argument("--mgmt-root", help="用户写明的管理目录")
    p.add_argument("--arch-root", help="安装目录；缺省为本脚本的上级目录")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    out = probe(a.repo, a.project, a.base, a.push_branch, a.mgmt_root, a.arch_root)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["repo"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
