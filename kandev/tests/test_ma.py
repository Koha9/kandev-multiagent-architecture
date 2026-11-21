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
ANSWERS = {"setup_style": "quick", "workspace_id": WS, "profiles": PROFILES, "existing_workflows": "none",
           "guard_automation": "manual", "acceptance_run": "no"}


def run(root, *args, expect=0):
    r = subprocess.run([sys.executable, os.path.join(root, "kandev", args[0])] + list(args[1:]),
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "MA_TEST_NESTED": "1"})
    assert r.returncode == expect, (args, r.returncode, r.stdout[-800:], r.stderr[-800:])
    return r.stdout + r.stderr


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def test_slots_and_answers():
    assert slots.body("说明\n---\n- a\n- b\n") == "- a\n- b" and slots.body("说明\n---\n") == "" and slots.body("x") == "x"
    assert slots.slot("git") == "" and slots.slot("coding") == "", "git / coding 槽位出厂必须为空（不改变 prompt）"
    _, problems = mf.validate({}, "install")
    always = [q["key"] for q in mf.questions("install") if q["ask"] == "always"]
    assert len(problems) == len(always) and all(any(p.startswith(k) for p in problems) for k in always)
    full, problems = mf.validate(ANSWERS, "install")
    assert not problems and full["install_mode"] == "standalone" and full["kandev_url"].startswith("http")
    _, problems = mf.validate({**ANSWERS, "setup_style": "custom"}, "install")       # 自定义：可选项也必须回答
    assert {p.split("：")[0] for p in problems} == {"install_mode", "home", "python", "kandev_url"}, problems
    assert mf.validate({**ANSWERS, "guard_automation": "maybe"}, "install")[1]
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
    write(ans, json.dumps({**ANSWERS, "home": home, "acceptance_run": ""}))
    assert "acceptance_run" in run(src, "ma.py", "install", "--answers", ans, expect=2) and not os.path.exists(home)

    write(ans, json.dumps({**ANSWERS, "home": home}))
    run(src, "ma.py", "install", "--answers", ans)
    m = mf.load(home)
    assert m["mode"] == "standalone" and m["deployments"][WS]["answers"]["home"] == home
    assert json.load(open(os.path.join(home, "kandev", "profiles.local.json"), encoding="utf-8")) == PROFILES
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
    hand = open(os.path.join(home, "kandev", "handoff", "guard-prompt.11111111.local.md"), encoding="utf-8").read()
    assert f"{home}/kandev/stage.py --ids {home}/kandev/kandev_ids.json" in hand and "<arch_root>" not in hand, hand[:400]
    shutil.move(os.path.join(tmp, "src-kandev"), os.path.join(src, "kandev"))

    # 定制：custom/rules 覆盖出厂槽位，进入 prompt；出厂文件不变
    before = run(home, "ma.py", "diff").split("confirm: ")[-1].strip()
    write(os.path.join(home, "custom", "rules", "git.md"), "说明\n---\n- 提交信息用英文。\n")
    write(os.path.join(home, "custom", "rules", "params.json"), '{"dev_wip": 2, "guard": {"T_IDLE": 25}}')
    dump = os.path.join(tmp, "prompts.md")
    run(home, "build_workflows.py", "dump", "--out", dump)
    text = open(dump, encoding="utf-8").read()
    assert "【Git 规则】" in text and "提交信息用英文" in text and "WIP 2" in text
    assert run(home, "ma.py", "diff").split("confirm: ")[-1].strip() != before, "定制后 confirm 值必须变化"
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import stage; print(stage.T_IDLE, stage.T_WAKES)",
                        os.path.join(home, "kandev")], capture_output=True, text=True)
    assert r.stdout.split() == ["25", "15"], (r.stdout, r.stderr)
    write(os.path.join(home, "custom", "rules", "params.json"), '{"nope": 1}')
    assert "不认识的键" in run(home, "build_workflows.py", "dump", "--out", dump, expect=1)
    os.remove(os.path.join(home, "custom", "rules", "params.json"))

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
    out = run(src, "ma.py", "upgrade", "--home", home)                         # 再升一次：没有要改的
    assert "冲突 0" in out and "更新 0" in out, out

    # 有进行中的项目：升级停下
    beat = {"at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "projects": ["demo"]}
    write(os.path.join(home, "kandev", "guard_state", "last_run.json"), json.dumps(beat))
    assert "demo" in run(src, "ma.py", "upgrade", "--home", home, expect=2)
    run(src, "ma.py", "upgrade", "--home", home, "--with-running")


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
