"""ma.py（安装、定制、升级）的离线测试：python kandev/tests/test_ma.py（也由 check_docs.py 调用）。
不连 Kandev；在临时目录里做一次独立安装、定制和升级。只用标准库。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KANDEV = os.path.dirname(HERE)
ROOT = os.path.dirname(KANDEV)
sys.path.insert(0, KANDEV)
import manifest as mf  # noqa: E402
import slots  # noqa: E402

WS = "11111111-2222-3333-4444-555555555555"
PROFILES = {"pm": "p1", "auditor": "p2", "developer": "p3", "reviewer": "p4", "mechanical": "p5"}
ANSWERS = {"setup_style": "quick", "workspace_id": WS, "profiles": PROFILES, "guard_automation": "yes"}


def run(root, *args, expect=0):
    r = subprocess.run([sys.executable, os.path.join(root, "kandev", args[0])] + list(args[1:]),
                       capture_output=True, text=True, encoding="utf-8",
                       env={**{k: v for k, v in os.environ.items() if k != "MA_NO_CUSTOM"}, "MA_TEST_NESTED": "1"})
    assert r.returncode == expect, (args, r.returncode, r.stdout[-800:], r.stderr[-800:])
    return r.stdout + r.stderr


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def test_slots_and_answers():
    assert slots.body("说明\n---\n- a\n- b\n") == "- a\n- b" and slots.body("说明\n---\n") == "" and slots.body("x") == "x"
    assert slots.slot("git") == "" and slots.slot("coding") == "", "git / coding 槽位出厂必须为空（不改变 prompt）"
    keys = lambda answers: sorted({k for k, _ in mf.validate(answers)[1]})       # noqa: E731
    assert keys({}) == sorted(q["key"] for q in mf.questions("install") if q["ask"] == "always")
    full, problems = mf.validate(ANSWERS)
    assert not problems and full["install_mode"] == "standalone" and full["kandev_url"].startswith("http")
    guided = sorted(q["key"] for q in mf.tree() if q["ask"] == "guided" and not q.get("when") and not q.get("after"))
    assert keys({**ANSWERS, "setup_style": "guided"}) == guided           # guided：这一级的项都要回答（缺的 install 拒绝）
    pd = {"remote": "auto", "ci": "auto", "autonomy": "ask", "plan_only": "ask", "run_policy": "ask", "integration_test": "auto",
          "paid_calls": "ask"}
    g = {**ANSWERS, "setup_style": "guided", "review_access": "ask", "model_strategy": "auto", "project_defaults": pd}
    assert keys(g) == []
    assert keys({k: v for k, v in g.items() if k != "review_access"}) == ["review_access"]
    # ci 不依赖 remote：只在本地的项目也可以在本地跑 CI 的检查；ci=remote 才需要推送
    local_ci = mf.validate({**g, "project_defaults": {**pd, "remote": "none", "ci": "local"}})
    assert not local_ci[1] and local_ci[0]["project_defaults"]["ci"] == "local"
    assert keys({**g, "project_defaults": {**pd, "remote": "none", "ci": "remote"}}) == ["project_defaults.ci"]
    assert keys({**g, "review_access": "remote_only", "project_defaults": {**pd, "remote": "none"}}) == ["project_defaults.remote"]
    noted = mf.cross_checks(mf.flatten({"project_defaults": {"autonomy": "4", "plan_only": "true", "remote": "push"}}))
    assert noted[0] == [] and len(noted[1]) == 2 and mf.cross_checks(mf.flatten(g)) == ([], [])       # 提示不拒绝安装
    assert keys({**g, "project_defaults": {**pd, "autonomy": "4", "plan_only": "true", "remote": "push"}}) == []
    # review_access=remote_only：没回答的 remote 推荐值变成 pr；回答了的不动
    quick_remote = mf.validate({**ANSWERS, "review_access": "remote_only"})
    assert not quick_remote[1] and quick_remote[0]["project_defaults"]["remote"] == "pr"
    assert mf.validate({**ANSWERS, "review_access": "remote_only", "project_defaults.remote": "push"})[0]["project_defaults"]["remote"] == "push"
    assert mf.recommended(next(q for q in mf.tree() if q["key"] == "project_defaults.remote"), {"review_access": "local"}) == "auto"
    # plan_only 只在 autonomy 是 ask / 3 / 4 时适用；1、2 时不问，写 ask
    two = {k: v for k, v in pd.items() if k != "plan_only"}
    assert keys({**g, "project_defaults": {**two, "autonomy": "4"}}) == ["project_defaults.plan_only"]
    fixed = mf.validate({**g, "project_defaults": {**two, "autonomy": "2", "plan_only": "false"}})
    assert not fixed[1] and fixed[0]["project_defaults"]["plan_only"] == "ask"
    assert keys({**g, "project_defaults": {**pd, "autonomy": "5"}}) == ["project_defaults.autonomy"]
    assert keys({**g, "project_defaults": {**pd, "autonomy": 3, "plan_only": True}}) == []   # 数字、布尔记成字符串
    assert keys({**g, "project_defaults.autonomy": "3", "project_defaults": two}) == ["project_defaults.plan_only"]   # 带点的键也可以平铺
    assert keys({**ANSWERS, "project_defaults": {"remot": "pr"}}) == ["project_defaults.remot"]
    assert keys({**ANSWERS, "project_defaults": "pr"}) == ["project_defaults"]
    custom = {**g, "setup_style": "custom"}
    assert keys(custom) == ["install_mode", "python"]   # 自定义：可选项也要回答；home 等 install_mode 答了再问；kandev_url 不问
    assert keys({**custom, "install_mode": "standalone"}) == ["home", "python"]
    assert keys({**custom, "install_mode": "link", "python": "p"}) == []   # 链接模式不问 home
    # _agent：agent 检测后自己填的键。不是答案；必须问的项不能列在里面；不认识的键报错
    assert keys({**ANSWERS, "kandev_url": "http://h:1/mcp", "_agent": ["kandev_url"], "_note": "x"}) == []
    assert mf.agent_keys({**ANSWERS, "kandev_url": "http://h:1/mcp", "_agent": ["kandev_url", "python"]}) == ["kandev_url"]
    for bad in (["workspace_id"], ["nope"], "kandev_url", [1]):
        assert keys({**ANSWERS, "_agent": bad}) == ["_agent"], bad
    assert sorted(mf.explicit_keys({**ANSWERS, "review_access": "local"})) == sorted([*ANSWERS, "review_access"])
    # 旧的答案：quick 照样通过；已记录的 custom 答案在 apply / doctor 时不因新增的项失败；
    # 已删除的提问（vendors、reviewer_cross_vendor）静默丢弃，改了名的取值（vendor、integration_test=ask）换成新值
    old_custom = {**ANSWERS, "setup_style": "custom", "install_mode": "standalone", "home": "h", "python": "p", "kandev_url": "u",
                  "model_strategy": "vendor", "vendors": ["Claude Code"], "reviewer_cross_vendor": "yes",
                  "project_defaults": {"remote": "none", "ci": "none", "integration_test": "ask"}}
    full, problems = mf.validate(old_custom, strict=False)
    assert not problems and mf.validate(old_custom)[1] and "vendors" not in full and full["model_strategy"] == "scoped", (full, problems)
    assert mf.project_defaults(old_custom) == {
        "_schema": "2", "_source": mf.project_defaults({})["_source"], "review_access": "ask", "remote": "none", "ci": "none",
        "autonomy": "ask", "plan_only": "ask", "run_policy": "ask", "integration_test": "auto", "paid_calls": "ask"}
    assert mf.resolve({"python": "<x>", "home": "~/.kandev-ma/<workspace id 前 8 位>", "workspace_id": WS}, "r")["home"] \
        .endswith(".kandev-ma/11111111")
    assert mf.resolve({"python": "<x>", "install_mode": "link"}, "r") == {"python": sys.executable.replace("\\", "/"),
                                                                           "install_mode": "link", "home": "r"}
    # 问题树：没有 when 引用不存在的键；先问的项排在依赖它的项前面；每项有 group，一批最多 4 题
    order = [q["key"] for q in mf.tree()]
    for q in mf.tree():
        assert q.get("group"), q["key"]
        for k in list(q.get("when", {})) + q.get("after", []) + [k for r in q.get("recommended_when", []) for k in r["when"]]:
            assert k in order and order.index(k) < order.index(q["key"]), (q["key"], k)
    assert "remote_kandev" not in order and all(q["ask"] == "when_prompted" for q in mf.questions("install") if q not in mf.tree())
    status = lambda answers: {q["key"]: st for q, st, _ in mf.walk(answers)[1]}       # noqa: E731
    s = status({})
    assert s["setup_style"] == "pending" and s["model_strategy"] == "deferred" and s["profiles"] == "deferred"
    s = status({"setup_style": "quick", "workspace_id": WS, "guard_automation": "yes"})
    assert s["profiles"] == "pending" and s["project_defaults.remote"] == "default" and s["kandev_url"] == "default"
    # 逐批：一批 = 一个 group，按清单顺序，每批最多 4 题，直到问完
    ask = lambda answers: [q["key"] for q, st, _ in mf.walk(answers)[1] if st == "pending"]       # noqa: E731
    step = {"setup_style": "guided"}
    assert ask(step) == ["workspace_id", "guard_automation"] and status(step)["review_access"] == "later"
    step.update({"workspace_id": WS, "guard_automation": "yes"})
    assert ask(step) == ["review_access", "model_strategy"] and status(step)["project_defaults.ci"] == "later"
    step.update({"review_access": "remote_only", "model_strategy": "scoped"})
    assert ask(step) == ["profiles"]
    step["profiles"] = PROFILES
    assert ask(step) == ["project_defaults.remote", "project_defaults.ci", "project_defaults.autonomy"]
    step.update({"project_defaults.remote": "pr", "project_defaults.ci": "auto", "project_defaults.autonomy": "2"})
    assert ask(step) == ["project_defaults.run_policy", "project_defaults.integration_test", "project_defaults.paid_calls"]
    step.update({"project_defaults.run_policy": "active", "project_defaults.integration_test": "off", "project_defaults.paid_calls": "deny"})
    assert ask(step) == [] and not mf.validate(step)[1]
    assert ask({**step, "setup_style": "custom"}) == ["install_mode", "python"]
    # check_docs 的清单检查：一批超过 4 题、缺 group、条件推荐引用后面的键或给出选项之外的值都报错
    import check_docs
    qs = mf.questions()
    assert not check_docs.check_questions(qs)
    edit = lambda key, **kw: [{**q, **kw} if q["key"] == key else q for q in qs]       # noqa: E731
    assert any("最多 4 题" in p for p in check_docs.check_questions(edit("review_access", group="policy")))
    assert any("缺少 group" in p for p in check_docs.check_questions(edit("review_access", group="")))
    assert any("recommended_when" in p for p in check_docs.check_questions(
        edit("project_defaults.remote", recommended_when=[{"when": {"project_defaults.ci": "local"}, "value": "pr"}])))
    assert any("value 不在 options" in p for p in check_docs.check_questions(
        edit("project_defaults.remote", recommended_when=[{"when": {"review_access": "remote_only"}, "value": "mr"}])))
    assert keys({**ANSWERS, "guard_automation": "maybe"}) == ["guard_automation"]
    assert keys({**ANSWERS, "install_mod": "link"}) == ["install_mod"]                      # 拼错的键不能被静默忽略
    assert keys({**ANSWERS, "workspace_id": 123}) == ["workspace_id"]
    assert keys({**ANSWERS, "profiles": {**PROFILES, "auditor": "p1"}}) == ["profiles"]
    assert all(q["ask"] == "when_prompted" for q in mf.questions() if q["stage"] in ("redeploy", "upgrade"))
    assert mf.check_profiles({**PROFILES, "auditor": "p1"}) and mf.check_profiles({**PROFILES, "reviewer": "p3"})
    assert mf.check_profiles({k: v for k, v in PROFILES.items() if k != "pm"})
    assert not mf.check_profiles({**PROFILES, "intake": "p5"})
    # 守护的 profile：可选角色 guard，缺省 = intake，再缺省 = mechanical
    assert not mf.check_profiles({**PROFILES, "guard": "p9"}) and mf.full_profiles({**PROFILES, "guard": "p9"})["guard"] == "p9"
    assert mf.full_profiles(PROFILES)["guard"] == "p5" and mf.full_profiles({**PROFILES, "intake": "p6"})["guard"] == "p6"


def test_install_customize_upgrade(tmp):
    src, home = os.path.join(tmp, "src"), os.path.join(tmp, "home").replace("\\", "/")
    for rel in mf.shipped_files(ROOT):                 # 源仓库的副本：只含随安装复制的文件，没有 .git、本机文件
        os.makedirs(os.path.dirname(os.path.join(src, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT, rel), os.path.join(src, rel))
    assert not any(r.startswith(("reports/", "custom/", "kandev/guard_state/")) or r.endswith(".local.json")
                   or "kandev_ids" in r for r in mf.shipped_files(ROOT))

    # 没有答案：apply 拒绝（在连接 Kandev 之前）
    write(os.path.join(src, "kandev", "p.json"), json.dumps(PROFILES))
    out = run(src, "build_workflows.py", "apply", "--workspace", WS, "--profiles", os.path.join(src, "kandev", "p.json"), expect=1)
    assert "必须先向用户确认" in out and "workspace_id" in out, out
    os.remove(os.path.join(src, "kandev", "p.json"))

    # 答案不全：install 拒绝，什么都不复制
    ans = os.path.join(tmp, "answers.json")
    write(ans, json.dumps({**ANSWERS, "home": home, "guard_automation": ""}))
    assert "guard_automation" in run(src, "ma.py", "install", "--answers", ans, expect=2) and not os.path.exists(home)
    write(ans, json.dumps({**ANSWERS, "home": os.path.join(tmp, "my home")}))                # 守护命令不加引号：路径不能含空格
    assert "空格" in run(src, "ma.py", "install", "--answers", ans, expect=2)
    write(ans, json.dumps({**ANSWERS, "home": home, "python": "C:/nope/python.exe"}))
    assert "找不到解释器" in run(src, "ma.py", "install", "--answers", ans, expect=2) and not os.path.exists(home)

    # 提问循环：只列出这一批（一个 group）该问的项；答完后打印标明来源的总表
    write(ans, json.dumps({"setup_style": "guided", "workspace_id": WS}))
    out = run(src, "ma.py", "questions", "--stage", "install", "--answers", ans)
    assert "[install] guard_automation" in out and "这一批（basics） 1 个问题" in out, out
    assert "[install] review_access" not in out and "[install] profiles" not in out and "没有待问的问题" not in out, out
    write(ans, json.dumps({"setup_style": "guided", "workspace_id": WS, "guard_automation": "yes", "review_access": "remote_only",
                           "model_strategy": "auto", "profiles": PROFILES}))
    out = run(src, "ma.py", "questions", "--stage", "install", "--answers", ans)
    assert "这一批（delivery） 3 个问题" in out and "[install] project_defaults.remote" in out and "推荐：pr" in out, out
    assert "[install] project_defaults.run_policy" not in out and "project_defaults.plan_only" in out, out   # 下一批只列名字
    write(ans, json.dumps({**ANSWERS, "home": home, "kandev_url": "http://localhost:38429/mcp", "_agent": ["kandev_url"],
                           "project_defaults": {"autonomy": "4", "plan_only": "true"}}))
    out = run(src, "ma.py", "questions", "--stage", "install", "--answers", ans)
    assert "没有待问的问题，可以运行 install" in out and "project_defaults.ci = auto（推荐值）" in out, out
    assert "kandev_url = http://localhost:38429/mcp（agent 检测）" in out and "setup_style = quick（用户）" in out, out
    assert f"home = {home}（用户）" in out and f"python = {sys.executable}".replace("\\", "/") in out and "<运行" not in out and "<workspace" not in out, out
    assert "提示：autonomy=4 且 plan_only=true" in out, out
    write(ans, json.dumps({**ANSWERS, "review_access": "remote_only", "project_defaults": {"remote": "none"}}))
    assert "答案之间有冲突" in run(src, "ma.py", "questions", "--stage", "install", "--answers", ans, expect=2)
    write(ans, json.dumps({**ANSWERS, "_agent": ["profiles"]}))
    assert "不能由 agent 决定" in run(src, "ma.py", "questions", "--stage", "install", "--answers", ans, expect=2)
    write(ans, json.dumps({**ANSWERS, "projct_defaults": {}}))
    assert "不认识的键" in run(src, "ma.py", "questions", "--stage", "install", "--answers", ans, expect=2)
    out = run(src, "ma.py", "questions", "--stage", "install")
    assert "    [install] project_defaults.plan_only" in out and "仅当 project_defaults.autonomy 为 ask / 3 / 4" in out, out
    assert "review_access 为 remote_only 时推荐 pr" in out and "[install] remote_kandev（ma.py 停下来时才问）" in out, out

    # kandev_url 不是本机地址：install 停下，用户确认这台就是 Kandev 主机后带 --remote-kandev 才继续（这里只验证停下）
    write(ans, json.dumps({**ANSWERS, "home": home, "kandev_url": "http://10.0.0.5:38429/mcp", "_agent": ["kandev_url"]}))
    out = run(src, "ma.py", "install", "--answers", ans, expect=2)
    assert "--remote-kandev" in out and not os.path.exists(home), out

    write(ans, json.dumps({**ANSWERS, "home": home}))
    run(src, "ma.py", "install", "--answers", ans)
    m = mf.load(home)
    assert m["mode"] == "standalone" and m["deployments"][WS]["answers"]["home"] == home
    for rel in ("docs/intake.md", "mgmt-template/roles/pm.md", "mgmt-template/VERSION", "kandev/stage.py", "rules/git.md"):
        assert os.path.exists(os.path.join(home, rel)), rel
    assert not mf.missing_answers(home, WS) and mf.missing_answers(home, "other-ws")
    run(src, "ma.py", "install", "--answers", ans, expect=2)                 # 已是安装目录：不覆盖

    # 安装目录自包含：删掉源仓库副本的 kandev/ 后，自检、守护脚本、离线 doctor 仍能运行
    shutil.move(os.path.join(src, "kandev"), os.path.join(tmp, "src-kandev"))
    out = run(home, "check_docs.py")
    assert "FAIL" not in out, out
    run(home, "stage.py", "--snapshot", os.path.join(home, "kandev", "tests", "stage_snapshot.json"),
        "--state-dir", os.path.join(tmp, "state"), "--now", "2026-01-01T00:00:00+00:00")
    out = run(home, "ma.py", "doctor", "--offline")
    assert "FAIL" not in out and "standalone" in out, out
    run(home, "ma.py", "guard")
    hd = os.path.join(home, "kandev", "handoff")
    hand = open(os.path.join(hd, "guard-prompt.11111111.local.md"), encoding="utf-8").read()
    assert f"{home}/kandev/stage.py --ids {home}/kandev/kandev_ids.json" in hand, hand[:400]
    assert "<arch_root>" not in hand and "<python>" not in hand and "<<" not in hand
    handoff = open(os.path.join(hd, "guard-handoff.11111111.local.md"), encoding="utf-8").read()
    assert "guard-prompt.11111111.local.md" in handoff and "p5" in handoff and "{GUARD" not in handoff and "{ARCH" not in handoff
    assert "{KANDEV_URL}" not in handoff and "http://localhost:38429/mcp" in handoff
    run(home, "ma.py", "answer", "--set", "kandev_url=http://localhost:38430/mcp")     # 非缺省地址要进交接文件
    run(home, "ma.py", "guard")
    handoff = open(os.path.join(hd, "guard-handoff.11111111.local.md"), encoding="utf-8").read()
    assert "http://localhost:38430/mcp" in handoff and "38429" not in handoff.replace("缺省 `http://localhost:38429/mcp`", ""), handoff

    # answer：只能改允许的键，校验不通过时不落盘
    run(home, "ma.py", "answer", "--set", "guard_automation=skip")
    assert mf.load(home)["deployments"][WS]["answers"]["guard_automation"] == "skip"
    for bad in ("workspace_id=zzz", "install_mode=link", "guard_automation=maybe", "python=", "python",
                'profiles={"pm":"x","auditor":"x","developer":"d","reviewer":"r","mechanical":"m"}', "profiles=[git"):
        run(home, "ma.py", "answer", "--set", bad, expect=2)
    got = mf.load(home)["deployments"][WS]["answers"]
    assert got["workspace_id"] == WS and got["profiles"] == PROFILES and got["guard_automation"] == "skip", got
    run(home, "ma.py", "answer", "--set", "guard_automation=yes")

    # 项目缺省值：install 写出 custom/project-defaults.json；answer --set 改它；doctor 打印一行
    pd_path = os.path.join(home, "custom", "project-defaults.json")
    pd = json.load(open(pd_path, encoding="utf-8"))
    assert {k: v for k, v in pd.items() if k != "_source"} == {
        "_schema": "2", "review_access": "ask", "remote": "auto", "ci": "auto", "autonomy": "ask", "plan_only": "ask",
        "run_policy": "ask", "integration_test": "auto", "paid_calls": "ask"}, pd
    dep = mf.load(home)["deployments"][WS]
    assert "project_defaults.remote" not in dep["explicit"] and {"profiles", "home", "python"} <= set(dep["explicit"]), dep["explicit"]
    # 没回答过的项跟着前面的答案重新取推荐值：review_access=remote_only → remote 变成 pr；写明过的不跟着变
    out = run(home, "ma.py", "answer", "--set", "review_access=remote_only")
    pd = json.load(open(pd_path, encoding="utf-8"))
    assert pd["review_access"] == "remote_only" and pd["remote"] == "pr" and "project_defaults.remote=pr" in out, (pd, out)
    assert os.path.exists(pd_path + ".bak")
    assert "review_access=remote_only" in run(home, "ma.py", "answer", "--set", "project_defaults.remote=none", expect=2)   # 交叉校验
    run(home, "ma.py", "answer", "--set", "review_access=local")
    assert json.load(open(pd_path, encoding="utf-8"))["remote"] == "auto"
    run(home, "ma.py", "answer", "--set", "project_defaults.remote=none", "--set", "project_defaults.autonomy=3",
        "--set", "project_defaults.ci=local", "--set", "project_defaults.run_policy=active")
    pd = json.load(open(pd_path, encoding="utf-8"))
    assert pd["remote"] == "none" and pd["ci"] == "local" and pd["autonomy"] == "3" and pd["run_policy"] == "active", pd
    run(home, "ma.py", "answer", "--set", "review_access=remote_only", expect=2)      # remote=none 是写明的：不跟着变，冲突
    for bad in ("project_defaults.remote=github", "project_defaults.nope=1", "project_defaults.ci=remote", "vendors=[\"x\"]"):
        run(home, "ma.py", "answer", "--set", bad, expect=2)
    run(home, "ma.py", "answer", "--set", "project_defaults.integration_test=ask")      # 旧取值：静默按 auto
    assert json.load(open(pd_path, encoding="utf-8"))["integration_test"] == "auto"
    run(home, "ma.py", "answer", "--set", "project_defaults.remote=pr", "--set", "project_defaults.ci=auto")
    assert json.load(open(pd_path, encoding="utf-8"))["ci"] == "auto"
    assert mf.load(home)["deployments"][WS]["answers"]["project_defaults"]["remote"] == "pr"
    out = run(home, "ma.py", "doctor", "--offline")
    assert "remote=pr，ci=auto，autonomy=3" in out and "交付预检" in out and "FAIL" not in out, out      # remote=pr：预检 git / gh
    # 新增提问之前的安装：答案里没有新键和 explicit、没有 project-defaults.json，doctor 不 FAIL，answer 照常能用
    m = mf.load(home)
    saved = dict(m["deployments"][WS])
    m["deployments"][WS] = {k: v for k, v in saved.items() if k not in ("explicit", "agent")}
    m["deployments"][WS]["answers"] = {**{k: v for k, v in saved["answers"].items()
                                          if k not in ("project_defaults", "model_strategy", "review_access")},
                                       "vendors": ["x"], "reviewer_cross_vendor": "no"}
    mf.save(home, m)
    shutil.move(pd_path, pd_path + ".moved")
    out = run(home, "ma.py", "doctor", "--offline")
    assert "FAIL" not in out and "project-defaults.json" in out, out
    run(home, "ma.py", "answer", "--set", "guard_automation=yes")
    assert not os.path.exists(pd_path)
    old = mf.load(home)["deployments"][WS]
    assert "vendors" not in old["answers"] and old["answers"]["home"] == home and "guard_automation" in old["explicit"], old
    shutil.move(pd_path + ".moved", pd_path)
    m = mf.load(home)
    m["deployments"][WS] = saved
    mf.save(home, m)
    shutil.move(os.path.join(tmp, "src-kandev"), os.path.join(src, "kandev"))

    # 定制：custom/rules 覆盖出厂槽位，进入 prompt；出厂文件不变
    def fp():       # 指纹：ma.py diff 打印、apply --confirmed 核对的值（diff 本身要连 Kandev，这里直接取）
        r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import ma; print(ma.fingerprint())",
                            os.path.join(home, "kandev")], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if k != "MA_NO_CUSTOM"})
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()
    before = fp()
    write(os.path.join(home, "custom", "rules", "git.md"), "说明\n---\n- 提交信息用英文。\n")
    write(os.path.join(home, "custom", "rules", "params.json"), '{"dev_wip": 2, "guard": {"T_IDLE": 25}}')
    dump = os.path.join(tmp, "prompts.md")
    run(home, "build_workflows.py", "dump", "--out", dump)
    text = open(dump, encoding="utf-8").read()
    assert "【Git 规则】" in text and "提交信息用英文" in text and "WIP 2" in text
    assert fp() != before, "定制后 confirm 值必须变化"
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import stage; print(stage.T_IDLE, stage.T_WAKES)",
                        os.path.join(home, "kandev")], capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if k != "MA_NO_CUSTOM"})
    assert r.stdout.split() == ["25", "15"], (r.stdout, r.stderr)
    write(os.path.join(home, "custom", "rules", "params.json"), '{"nope": 1}')
    assert "不认识的键" in run(home, "build_workflows.py", "dump", "--out", dump, expect=1)
    write(os.path.join(home, "custom", "rules", "params.json"), '{"guard": {"T_IDLE": "10"}}')
    assert "正整数" in run(home, "build_workflows.py", "dump", "--out", dump, expect=1)
    os.remove(os.path.join(home, "custom", "rules", "params.json"))

    test_apply_gates(home)

    # 升级：用户改过角色卡和 intake；新版改了角色卡（冲突）、协议（直接更新）、新增一个文件；intake 新版没变（保留）
    write(os.path.join(home, "mgmt-template", "roles", "pm.md"), "我的 pm 角色卡\n")
    write(os.path.join(home, "docs", "intake.md"), "我的 intake\n")
    write(os.path.join(src, "mgmt-template", "roles", "pm.md"), "新版 pm 角色卡\n")
    write(os.path.join(src, "mgmt-template", "protocol", "message.md"), "新版协议\n")
    write(os.path.join(src, "rules", "extra.md"), "新增\n")
    out = run(src, "ma.py", "upgrade", "--home", home, expect=2)              # 有冲突且没有指定处理方式：不改任何东西
    assert "mgmt-template/roles/pm.md" in out and not os.path.exists(os.path.join(home, "rules", "extra.md"))
    run(src, "ma.py", "upgrade", "--home", home, "--conflicts", "keep")
    rd = lambda rel: open(os.path.join(home, rel), encoding="utf-8").read()   # noqa: E731
    assert rd("mgmt-template/roles/pm.md") == "我的 pm 角色卡\n" and rd("mgmt-template/roles/pm.md.new") == "新版 pm 角色卡\n"
    assert rd("docs/intake.md") == "我的 intake\n" and not os.path.exists(os.path.join(home, "docs", "intake.md.new"))
    assert rd("mgmt-template/protocol/message.md") == "新版协议\n" and rd("rules/extra.md") == "新增\n"
    assert "提交信息用英文" in rd("custom/rules/git.md") and mf.load(home)["deployments"][WS]["answers"]["home"] == home
    assert json.loads(rd("custom/project-defaults.json"))["remote"] == "pr"          # 升级不动 custom/
    write(os.path.join(src, "mgmt-template", "roles", "pm.md"), "更新的 pm 角色卡\n")
    run(src, "ma.py", "upgrade", "--home", home, "--conflicts", "take-new")
    assert rd("mgmt-template/roles/pm.md") == "更新的 pm 角色卡\n" and rd("mgmt-template/roles/pm.md.mine") == "我的 pm 角色卡\n"
    write(os.path.join(src, "mgmt-template", "roles", "pm.md"), "第三版 pm 角色卡\n")       # 已有 .new 时不覆盖它
    write(os.path.join(home, "mgmt-template", "roles", "pm.md"), "我又改了\n")
    run(src, "ma.py", "upgrade", "--home", home, "--conflicts", "keep")
    assert rd("mgmt-template/roles/pm.md.new") == "新版 pm 角色卡\n" and rd("mgmt-template/roles/pm.md.new.2") == "第三版 pm 角色卡\n"
    out = run(src, "ma.py", "upgrade", "--home", home, "--dry-run")            # 再升一次：没有要改的（pm.md 仍是冲突，保留）
    assert "更新 0" in out and "新增 0" in out, out
    write(os.path.join(home, "mgmt-template", "roles", "pm.md"), "第三版 pm 角色卡\n")
    out = run(src, "ma.py", "upgrade", "--home", home)
    assert "冲突 0" in out and "更新 0" in out, out

    # 有进行中的项目：升级停下
    beat = {"at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "projects": ["demo"]}
    write(os.path.join(home, "kandev", "guard_state", "last_run.json"), json.dumps(beat))
    assert "demo" in run(src, "ma.py", "upgrade", "--home", home, expect=2)
    run(src, "ma.py", "upgrade", "--home", home, "--with-running")


APPLY_SCENARIO = r"""
import contextlib, io, json, os, sys
home, ws = sys.argv[1], sys.argv[2]
sys.path[:0] = [os.path.join(home, "kandev"), os.path.join(home, "kandev", "tests")]
import ma, fake_kandev
import build_workflows as bw
fake_kandev.install()
W1 = bw.W1_NAME


def run(*args):
    sys.argv = ["ma.py", *args]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            ma.main()
    except SystemExit as e:
        return e.code or 0, out.getvalue()


def wf(name):
    return next(w for w in fake_kandev.STATE["workflows"].values() if w["name"] == name)


code, out = run("apply")                                    # 没有同名 workflow：直接新建，不需要确认
assert code == 0 and len(fake_kandev.STATE["workflows"]) == 3, out
dep = json.load(open(os.path.join(home, "ma-manifest.json"), encoding="utf-8"))["deployments"][ws]
assert dep["deployed_version"] == bw.VERSION and "apply_started" not in dep, dep
ids = json.load(open(os.path.join(home, "kandev", "kandev_ids.json"), encoding="utf-8"))
assert ids["_meta"]["arch_root"] == home and ids[W1]["workflow_id"] == wf(W1)["id"], ids["_meta"]
intake = next(s for s in wf(W1)["steps"] if s["name"] == "接收")
assert f"{home}/docs/intake.md" in intake["prompt"] and intake["agent_profile_id"] == "p5", intake["prompt"][:300]
assert json.load(open(os.path.join(home, "kandev", "profiles.local.json"), encoding="utf-8"))["pm"] == "p1"
py = dep["answers"]["python"]                               # 「接收」运行 intake.py 用部署答案里的解释器，不用裸 python
assert f"{py} {home}/kandev/intake.py probe" in intake["prompt"] and bw.PY_PLACEHOLDER not in intake["prompt"], intake["prompt"][:900]
assert ids["_meta"]["python"] == py and chr(92) not in py, ids["_meta"]
assert bw.PY_PLACEHOLDER + " " + bw.ARCH_PLACEHOLDER + "/kandev/intake.py probe" in bw.all_workflows()[2]["steps"][0]["prompt"]   # 文档版本保留占位
import verify_export                                        # 导出时解释器路径换回占位符（导出本身要连 Kandev，这里只查替换表）
assert verify_export.placeholders(ids)[py] == bw.PY_PLACEHOLDER and verify_export.placeholders(ids)[home] == bw.ARCH_PLACEHOLDER

code, out = run("diff")                                     # 刚部署完：没有差异
assert code == 0 and "0 个步骤的 prompt、0 处结构有变化" in out, out
h = ma.fingerprint()
assert out.strip().endswith(f"confirm: {h}")
assert run("apply")[0] == 2 and run("apply", "--confirmed", "nope")[0] == 2       # 就地更新必须带 diff 给的值
code, out = run("apply")
assert h not in out, "拒绝信息里不能直接给出 confirm 值"
assert run("apply", "--confirmed", h)[0] == 0
code, out = run("answer", "--set", f"python={py}")           # 改 python：提示要重新部署（它写在「接收」的 prompt 里）
assert code == 0 and "重新部署" in out and "接收" in out, out
keep = intake["prompt"]
intake["prompt"] = keep.replace(py, "C:/old/python.exe")    # 已部署的是旧解释器：diff 要看得到
assert "C:/old/python.exe" in run("diff")[1]
intake["prompt"] = keep

intake["prompt"] += "\n被人在界面上改过"                    # 已部署的被改动：diff 和 doctor 都要看得到
next(s for s in wf(bw.W3_NAME)["steps"] if s["name"] == "开发")["wip_limit"] = 9
code, out = run("diff")
assert "接收" in out and "被人在界面上改过" in out and "wip_limit" in out and "1 个步骤的 prompt、1 处结构" in out, out
code, out = run("doctor")
assert "已部署的 workflow 与本目录不一致" in out, out
assert ma.ACCEPT_TMP_PREFIX not in out, out

hold = next(s for s in wf(bw.W3_NAME)["steps"] if s["name"] == "待开发")   # 验收部署留下的临时任务：doctor WARN 列出
fake_kandev.STATE["tasks"].append({"id": "tmp-1", "title": ma.ACCEPT_TMP_PREFIX + " 待开发行为", "workflow_id": wf(bw.W3_NAME)["id"],
                                   "workflow_step_id": hold["id"], "state": "TODO"})
fake_kandev.STATE["tasks"].append({"id": "t9", "title": "普通任务 " + ma.ACCEPT_TMP_PREFIX, "workflow_id": wf(bw.W3_NAME)["id"],
                                   "workflow_step_id": hold["id"], "state": "TODO"})
code, out = run("doctor")
line = next((l for l in out.splitlines() if ma.ACCEPT_TMP_PREFIX + "」开头" in l), "")
assert line.startswith("WARN") and "tmp-1" in line and "待开发" in line and "t9" not in line and "删除" in line, out
del fake_kandev.STATE["tasks"][-2:]

fake_kandev.STATE["tasks"].append({"id": "t1", "title": "进行中的项目", "workflow_id": wf(W1)["id"],
                                   "workflow_step_id": intake["id"], "state": "IN_PROGRESS"})
code, out = run("apply", "--confirmed", h)                  # 有进行中的项目：要用户同意
assert code == 2 and "进行中的项目" in out, out
assert run("apply", "--confirmed", h, "--with-running")[0] == 0
assert "被人在界面上改过" not in intake["prompt"]
assert run("diff")[1].count("0 个步骤的 prompt、0 处结构有变化") == 1

for w in fake_kandev.STATE["workflows"].values():           # 另一个系列：不能就地更新
    w["description"] = w["description"].replace(f"[{bw.VERSION}]", "[v3.2]")
code, out = run("apply", "--confirmed", h, "--with-running")
assert code == 2 and "--retire" in out, out
code, out = run("apply", "--retire")
assert code == 2 and "不再巡检" in out, out
old_id = wf(W1)["id"]
assert run("apply", "--retire", "--with-running")[0] == 0
names = sorted(w["name"] for w in fake_kandev.STATE["workflows"].values())
assert len(names) == 6 and f"{W1} (v3.2)" in names and wf(W1)["id"] != old_id, names
assert os.path.exists(os.path.join(home, "kandev", "kandev_ids.v3.2.bak")), os.listdir(os.path.join(home, "kandev"))
print("SCENARIO OK")
"""


def test_apply_gates(home):
    """用内存里的 Kandev 替身走一遍 apply：新建、就地更新要确认、进行中的项目、另一个系列要 --retire。"""
    env = {**{k: v for k, v in os.environ.items() if k != "MA_NO_CUSTOM"}, "MA_TEST_NESTED": "1"}
    r = subprocess.run([sys.executable, "-c", APPLY_SCENARIO, home, WS], capture_output=True, text=True,
                       encoding="utf-8", env=env)
    assert r.returncode == 0 and "SCENARIO OK" in r.stdout, (r.stdout[-1500:], r.stderr[-3000:])


def main():
    test_slots_and_answers()
    tmp = tempfile.mkdtemp(prefix="ma-test-")
    try:
        test_install_customize_upgrade(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("OK test_ma")


if __name__ == "__main__":
    main()
