"""intake.py 的离线测试：python kandev/tests/test_intake.py（也由 check_docs.py 调用）。只用标准库和 git。
每个 test_ 开头的函数都会自动运行。远端用本地裸仓库代替，不访问网络。"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import intake  # noqa: E402

NOW = datetime(2026, 11, 23, 14, 5)


def sh(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", GIT_TERMINAL_PROMPT="0")
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def make_repo(root, name="app", remote=False, ci=False):
    repo = os.path.join(root, name)
    os.makedirs(repo)
    sh(repo, "init", "-q", "-b", "main")
    open(os.path.join(repo, "a.txt"), "w").write("a\n")
    if ci:
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        open(os.path.join(repo, ".github", "workflows", "ci.yml"), "w").write("on: push\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "init")
    if remote:
        bare = os.path.join(root, name + ".git")
        sh(root, "init", "-q", "--bare", "-b", "main", bare)
        sh(repo, "remote", "add", "origin", bare)
        sh(repo, "push", "-q", "-u", "origin", "main")
    return os.path.realpath(repo)


def arch(root, defaults=None):
    a = os.path.join(root, "arch")
    os.makedirs(os.path.join(a, "custom"))
    if defaults is not None:
        json.dump(defaults, open(os.path.join(a, "custom", "project-defaults.json"), "w"))
    return a


def run(root, repo, defaults=None, **kw):
    return intake.probe(repo=repo, arch_root=arch(root, defaults), now=NOW, gh="ok", **kw)


def test_defaults_missing_and_legacy():
    with tempfile.TemporaryDirectory() as root:
        d, notes = intake.load_defaults(os.path.join(root, "nowhere"))
        assert d == {"review_access": "ask", "remote": "auto", "ci": "auto", "autonomy": "ask", "plan_only": "ask",
                     "run_policy": "ask", "integration_test": "auto", "paid_calls": "ask"}, d
        assert notes and "按出厂缺省" in notes[0]
        a = arch(root, {"_schema": "2", "integration_test": "ask", "review_access": "remote", "autonomy": 3, "ci": "bogus"})
        d, notes = intake.load_defaults(a)
        assert (d["integration_test"], d["review_access"], d["autonomy"], d["ci"]) == ("auto", "remote_only", "3", "auto"), d
        assert any("ci" in n for n in notes), notes
        open(os.path.join(a, "custom", "project-defaults.json"), "w").write("{broken")
        d, notes = intake.load_defaults(a)
        assert d["remote"] == "auto" and any("读不出" in n for n in notes)


def test_resolve():
    base = {k: v[1] for k, v in intake.DEFAULT_KEYS.items()}
    r = intake.resolve(base, has_remote=False, has_upstream=False, ci_files=[])
    assert (r["remote"], r["remote_no_ask"], r["ci"], r["run_policy"], r["run_policy_no_ask"]) == ("none", "none", "none", "ask", "active"), r
    r = intake.resolve(base, True, True, [".github/workflows"])
    assert (r["remote"], r["remote_recommend"], r["remote_no_ask"], r["ci"]) == ("ask", "pr", "none", "local"), r
    r = intake.resolve(base, True, False, [])
    assert r["remote_recommend"] == "none"
    r = intake.resolve({**base, "review_access": "remote_only"}, True, False, [])
    assert (r["remote"], r["remote_recommend"], r["remote_no_ask"]) == ("ask", "pr", "pr"), r
    r = intake.resolve({**base, "remote": "push", "ci": "remote", "run_policy": "conservative", "plan_only": "true"}, True, True, [])
    assert (r["remote"], r["remote_no_ask"], r["ci"], r["run_policy_no_ask"], r["plan_only_no_ask"]) == ("push", "push", "remote", "conservative", "true"), r
    notes = []
    r = intake.resolve({**base, "remote": "pr"}, False, False, [], notes=notes)
    assert r["remote"] == "none" and any("没有远端" in n for n in notes), "没有远端时部署缺省的 pr 也只能是 none"


def test_resolve_is_consistent():
    """resolved 不自相矛盾；改正和提醒都写进 notes。"""
    base = {k: v[1] for k, v in intake.DEFAULT_KEYS.items()}
    # 没有远端 + ci remote → ci 改为 local
    notes = []
    r = intake.resolve({**base, "ci": "remote"}, False, False, [], notes=notes)
    assert (r["remote"], r["ci"], r["ci_no_ask"]) == ("none", "local", "local") and any("改为 local" in n for n in notes), (r, notes)
    # remote 要问 + ci remote：提问时保留（用户可能选 pr），不提问时 remote 取 none，ci 跟着改
    notes = []
    r = intake.resolve({**base, "ci": "remote"}, True, True, [], notes=notes)
    assert (r["remote"], r["ci"], r["remote_no_ask"], r["ci_no_ask"]) == ("ask", "remote", "none", "local"), r
    assert any("Q9" in n for n in notes) and any(n.startswith("不提问时") for n in notes), notes
    # 部署缺省 none + ci remote
    notes = []
    r = intake.resolve({**base, "remote": "none", "ci": "remote"}, True, True, [], notes=notes)
    assert r["ci"] == "local" and notes
    # push 到基线分支 + ci remote：不改，只提醒
    notes = []
    r = intake.resolve({**base, "remote": "push", "ci": "remote"}, True, True, [], base="main", project="app", notes=notes)
    assert r["ci"] == "remote" and any("提醒" in n for n in notes), notes
    # 声明只能在远端审查，但仓库没有远端
    notes = []
    r = intake.resolve({**base, "review_access": "remote_only"}, False, False, [], notes=notes)
    assert r["remote"] == r["remote_no_ask"] == r["remote_recommend"] == "none" and any("remote_only" in n for n in notes), notes
    # gh 不可用：有 upstream 也不推荐 pr；remote_only 仍推荐 pr，但要说明
    for gh in ("missing", "unauthenticated"):
        assert intake.resolve(base, True, True, [], gh=gh)["remote_recommend"] == "none", gh
        notes = []
        r = intake.resolve({**base, "review_access": "remote_only"}, True, True, [], gh=gh, notes=notes)
        assert r["remote_recommend"] == "pr" and any("gh 不可用" in n for n in notes), (gh, notes)
    notes = []
    intake.resolve(base, True, True, [".github/workflows"], notes=notes)
    assert notes == [], "正常情况没有说明"


def test_check_combo():
    f, notes = intake.check_combo("pr", "main", "main", "local", "app")
    assert f["push_branch"] == "ma/app" and notes
    f, notes = intake.check_combo("none", None, "main", "remote", "app")
    assert f["ci"] == "local" and notes
    f, notes = intake.check_combo("push", None, "main", "remote", "app")
    assert f == {"remote": "push", "push_branch": "main", "ci": "remote"} and "提醒" in notes[0]
    f, notes = intake.check_combo("pr", "ma/app", "main", "remote", "app")
    assert f == {"remote": "pr", "push_branch": "ma/app", "ci": "remote"} and not notes


def test_probe_local_repo():
    with tempfile.TemporaryDirectory() as root:
        repo = make_repo(root)
        out = run(root, repo)
        assert out["repo"] == {"ok": True, "path": repo} and out["project"] == "app"
        assert out["base"]["value"] == "main" and out["base"]["exists"] and not out["base"]["needs_confirm"] and out["base"]["upstream"] is None
        assert out["remotes"] == [] and out["remote"] is None and out["ci_files"] == [] and out["gh"] == "missing"
        assert out["push_branch"] == {"suggested": "ma/app", "exists_remote": None, "checked": False, "note": None}
        assert out["mgmt_root"]["state"] == "new" and out["mgmt_root"]["suggested"] == os.path.join(os.path.dirname(repo), "app-mgmt")
        assert out["resolved"]["remote"] == "none" and out["resolved"]["ci"] == "none"
        sub = os.path.join(repo, "src")
        os.makedirs(sub)
        assert intake.probe(repo=sub, arch_root=arch(os.path.join(root, "x")), now=NOW, gh="ok")["repo"]["path"] == repo, "子目录也能找到主仓库"
        assert run(os.path.join(root, "y"), repo, base="nope")["base"]["needs_confirm"], "不存在的基线分支要确认"
        sh(repo, "checkout", "-q", "-b", "dev")
        b = run(os.path.join(root, "z"), repo)["base"]
        assert b["value"] == "dev" and b["needs_confirm"], "推导出的基线不是 main / master 时要确认"


def test_probe_not_a_repo():
    with tempfile.TemporaryDirectory() as root:
        out = intake.probe(repo=root, arch_root=os.path.join(root, "arch"), now=NOW, gh="ok")
        if out["repo"]["ok"]:           # 临时目录恰好在某个 git 仓库里时没法测
            return
        assert out["repo"] == {"ok": False, "path": None} and any("找不到" in n for n in out["notes"])


def test_probe_remote_ci_and_collision():
    with tempfile.TemporaryDirectory() as root:
        repo = make_repo(root, remote=True, ci=True)
        out = run(root, repo)
        assert out["remote"] == "origin" and out["base"]["upstream"] == "origin/main" and out["ci_files"] == [".github/workflows"]
        assert out["gh"] == "ok" and out["resolved"]["remote"] == "ask" and out["resolved"]["remote_recommend"] == "pr"
        assert out["resolved"]["ci"] == "local"
        assert out["push_branch"] == {"suggested": "ma/app", "exists_remote": False, "checked": True, "note": None}
        # 远端留着以前项目的 ma/app，且不是基线分支的祖先 → 加日期后缀
        sh(repo, "checkout", "-q", "-b", "old")
        open(os.path.join(repo, "b.txt"), "w").write("b\n")
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "old work")
        sh(repo, "push", "-q", "origin", "old:ma/app")
        sh(repo, "checkout", "-q", "main")
        pb = run(os.path.join(root, "a2"), repo)["push_branch"]
        assert pb["suggested"] == "ma/app-20261123" and pb["exists_remote"] and "改用" in pb["note"], pb
        # 同一天带日期后缀的名字也被占了 → 再加序号
        sh(repo, "push", "-q", "origin", "old:ma/app-20261123")
        assert run(os.path.join(root, "a2b"), repo)["push_branch"]["suggested"] == "ma/app-20261123-2"
        sh(repo, "push", "-q", "origin", "old:ma/app-20261123-2")
        assert run(os.path.join(root, "a2c"), repo)["push_branch"]["suggested"] == "ma/app-20261123-3"
        # probe 的 resolved 经过组合检查：没有 gh 时不推荐 pr；部署缺省 pr + 用户写的 push_branch 是基线分支 → 改掉并说明
        out = intake.probe(repo=repo, arch_root=arch(os.path.join(root, "g1")), now=NOW, gh="missing")
        assert out["resolved"]["remote_recommend"] == "none", out["resolved"]
        out = run(os.path.join(root, "g2"), repo, defaults={"remote": "pr", "ci": "remote"}, push_branch="main")
        assert out["resolved"]["remote"] == "pr" and out["push_branch"]["suggested"] == "ma/app", out["push_branch"]
        assert any("不能是基线分支" in n for n in out["notes"]), out["notes"]
        pb = run(os.path.join(root, "a3"), repo, push_branch="ma/app")["push_branch"]
        assert pb["suggested"] == "ma/app" and "请确认" in pb["note"], "用户写明的分支名不改"
        # 远端的 ma/app 已经合进基线分支（是祖先）→ 可以沿用
        sh(repo, "merge", "-q", "--no-ff", "-m", "merge", "old")
        pb = run(os.path.join(root, "a4"), repo)["push_branch"]
        assert pb["suggested"] == "ma/app" and pb["exists_remote"] and pb["note"] is None, pb
        # 远端不可达 → 不检查、不改名
        sh(repo, "remote", "set-url", "origin", os.path.join(root, "gone.git"))
        pb = run(os.path.join(root, "a5"), repo)["push_branch"]
        assert pb["suggested"] == "ma/app" and not pb["checked"] and "查不到" in pb["note"], pb


def test_probe_mgmt_root():
    with tempfile.TemporaryDirectory() as root:
        repo = make_repo(root)
        mgmt = os.path.join(os.path.dirname(repo), "app-mgmt")
        os.makedirs(os.path.join(mgmt, "project"))
        assert run(root, repo)["mgmt_root"]["state"] == "other_project", "不是空目录又没有 registry.json：不沿用"
        json.dump({"project": "app"}, open(os.path.join(mgmt, "project", "registry.json"), "w"))
        m = run(os.path.join(root, "b1"), repo)["mgmt_root"]
        assert m["state"] == "same_project" and m["suggested"] == mgmt, m
        json.dump({"project": "other"}, open(os.path.join(mgmt, "project", "registry.json"), "w"))
        m = run(os.path.join(root, "b2"), repo)["mgmt_root"]
        assert m["state"] == "other_project" and m["suggested"] == mgmt + "-20261123-1405", m
        m = run(os.path.join(root, "b3"), repo, mgmt_root=mgmt)["mgmt_root"]
        assert m["state"] == "other_project" and m["suggested"] == mgmt and "另给" in m["note"], m
        m = run(os.path.join(root, "b4"), repo, mgmt_root=os.path.join(repo, "mgmt"))["mgmt_root"]
        assert m["state"] == "invalid", m


def test_cli_prints_json():
    with tempfile.TemporaryDirectory() as root:
        repo = make_repo(root)
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "intake.py"), "probe", "--repo", repo,
                            "--arch-root", arch(root, {"autonomy": "3"})], capture_output=True)
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout.decode("utf-8"))
        assert out["resolved"]["autonomy"] == "3" and out["repo"]["path"] == repo


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    assert len(tests) >= 8, "没有找到测试函数"
    for name, fn in tests:
        try:
            fn()
        except Exception:
            print(f"FAIL {name}", file=sys.stderr)
            raise
    print("OK test_intake")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
