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
    assert keys({**ANSWERS, "setup_style": "custom"}) == ["home", "install_mode", "kandev_url", "python"]   # 自定义：可选项也要回答
    assert keys({**ANSWERS, "setup_style": "custom", "install_mode": "link", "python": "p", "kandev_url": "u"}) == []   # 链接模式不问 home
    assert keys({**ANSWERS, "guard_automation": "maybe"}) == ["guard_automation"]
    assert keys({**ANSWERS, "install_mod": "link"}) == ["install_mod"]                      # 拼错的键不能被静默忽略
    assert keys({**ANSWERS, "workspace_id": 123}) == ["workspace_id"]
    assert keys({**ANSWERS, "profiles": {**PROFILES, "auditor": "p1"}}) == ["profiles"]
    assert all(q["ask"] == "when_prompted" for q in mf.questions() if q["stage"] in ("redeploy", "upgrade"))
    assert mf.check_profiles({**PROFILES, "auditor": "p1"}) and mf.check_profiles({**PROFILES, "reviewer": "p3"})
    assert mf.check_profiles({k: v for k, v in PROFILES.items() if k != "pm"})
    assert not mf.check_profiles({**PROFILES, "intake": "p5"})


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

    # answer：只能改允许的键，校验不通过时不落盘
    run(home, "ma.py", "answer", "--set", "guard_automation=skip")
    assert mf.load(home)["deployments"][WS]["answers"]["guard_automation"] == "skip"
    for bad in ("workspace_id=zzz", "install_mode=link", "guard_automation=maybe", "python=", "python",
                'profiles={"pm":"x","auditor":"x","developer":"d","reviewer":"r","mechanical":"m"}', "profiles=[git"):
        run(home, "ma.py", "answer", "--set", bad, expect=2)
    got = mf.load(home)["deployments"][WS]["answers"]
    assert got["workspace_id"] == WS and got["profiles"] == PROFILES and got["guard_automation"] == "skip", got
    run(home, "ma.py", "answer", "--set", "guard_automation=yes")
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

code, out = run("diff")                                     # 刚部署完：没有差异
assert code == 0 and "0 个步骤的 prompt、0 处结构有变化" in out, out
h = ma.fingerprint()
assert out.strip().endswith(f"confirm: {h}")
assert run("apply")[0] == 2 and run("apply", "--confirmed", "nope")[0] == 2       # 就地更新必须带 diff 给的值
code, out = run("apply")
assert h not in out, "拒绝信息里不能直接给出 confirm 值"
assert run("apply", "--confirmed", h)[0] == 0

intake["prompt"] += "\n被人在界面上改过"                    # 已部署的被改动：diff 和 doctor 都要看得到
next(s for s in wf(bw.W3_NAME)["steps"] if s["name"] == "开发")["wip_limit"] = 9
code, out = run("diff")
assert "接收" in out and "被人在界面上改过" in out and "wip_limit" in out and "1 个步骤的 prompt、1 处结构" in out, out
code, out = run("doctor")
assert "已部署的 workflow 与本目录不一致" in out, out

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
