"""stage.py 的离线回归测试：python kandev/tests/test_stage.py（也由 check_docs.py 调用）。只用标准库。
本文件里每个 test_ 开头的函数都会自动运行，不用登记。分类规则的先后见 PRIORITY（test_priority）。"""
import json
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from stage import evaluate, group_projects, load_blockers, parse_reset, should_disable, ts, usage_limit  # noqa: E402

PM, MOD = "00000000-0000-0000-0000-0000000000aa", "00000000-0000-0000-0000-0000000000bb"


def run(state, now):
    snap = json.load(open(os.path.join(HERE, "stage_snapshot.json"), encoding="utf-8"))
    for t in snap["tasks"]:
        t.setdefault("description", ""), t.setdefault("sessions", [])
    rows, alerts, new_state = evaluate(snap["tasks"], ts(now), state, snap["pm_task"])
    return {r["title"]: r["category"] for r in rows}, [(a["signal"], a["to_task"]) for a in alerts], new_state


def test_snapshot():
    """stage_snapshot.json 连续巡检三次：分类、阈值、去重。"""
    cats, alerts, st = run({}, "2026-11-09T05:00:00+00:00")
    assert cats["core-01"] == "完成", cats
    assert cats["core-02"] == "等上级：可放行", cats          # 前置已完成，但刚进入，未到阈值
    assert cats["core-03"] == "运行中", cats
    assert cats["core-04"] == "排队", cats
    assert cats["core-05"] == "等人：权限请求", cats
    assert cats["mod:core"] == "常驻", cats
    assert alerts == [], alerts                              # W1 的 pm 在「立项规划」空闲：只写 stage.md，不告警
    assert cats["pm"] == "等人：空闲未推进", cats

    cats, alerts, st = run(st, "2026-11-09T05:15:00+00:00")
    assert alerts == [("hold_ready", MOD)], alerts           # pm 的告警 60 分钟内不重复

    cats, alerts, st = run(st, "2026-11-09T06:05:00+00:00")
    assert not any(a[0] == "pm_unresponsive" for a in alerts), alerts   # pm 不在常驻步骤：不移到刷新
    assert ("running_stale", MOD) in alerts, alerts
    assert ("hold_ready", MOD) not in alerts, alerts         # 距上次告警 50 分钟，去重


def test_ts():
    assert ts("2026-11-09T05:00:00Z") == ts("2026-11-09T05:00:00+00:00") == ts("2026-11-09T05:00:00")
    assert ts("2026-11-09T05:00:00.123456789Z") == ts("2026-11-09T05:00:00.123456+00:00")
    assert ts("2026-11-09T05:00:00.123-05:00") == ts("2026-11-09T10:00:00.123Z")       # 负时区 + 小数秒
    assert ts("2026-11-09T14:00:00.5+09:00") == ts("2026-11-09T05:00:00.5Z") and ts("") is None


def test_load_modules_tolerant():
    """tasks.json 带 BOM 能读；编码不对或形状不对的模块记入 unreadable，不抛错，也不影响其他模块。"""
    import tempfile
    from stage import load_modules
    doc = {"module_task_id": "M1", "module_session_id": "S1",
           "tasks": [{"id": "a-1", "status": "merged", "kandev_task_id": "K1"},
                     {"id": "a-2", "status": "held", "kandev_task_id": "K2", "blocked_by": ["a-1"]}]}
    with tempfile.TemporaryDirectory() as root:
        for name, data in (("bom", json.dumps(doc).encode("utf-8-sig")), ("utf16", json.dumps(doc).encode("utf-16")),
                           ("list", b"[1, 2]"), ("cut", b'{"tasks": [')):
            os.makedirs(os.path.join(root, "modules", name))
            with open(os.path.join(root, "modules", name, "tasks.json"), "wb") as f:
                f.write(data)
        got = load_modules(root)
        assert got["blockers"] == {"K1": [], "K2": ["merged"]} and got["statuses"] == {"K1": "merged", "K2": "held"}, got
        assert got["sessions"] == {"M1": "S1"} and got["unreadable"] == ["cut", "list", "utf16"], got


def test_main_isolation():
    """一个项目的管理目录写不进去：其他项目照常巡检，告警照常输出；损坏的去重状态按空处理；--dry-run 什么都不写。"""
    import subprocess
    import tempfile
    stage_py = os.path.join(os.path.dirname(HERE), "stage.py")
    with tempfile.TemporaryDirectory() as tmp:
        bad, good, state = (os.path.join(tmp, n) for n in ("bad", "good", "state"))
        for root in (bad, good):
            os.makedirs(root)
            open(os.path.join(root, "README.md"), "w").close()
        open(os.path.join(bad, "agents"), "w").close()            # agents 是文件：stage.md 写不进去
        idle = [{"state": "RUNNING", "updated_at": "2026-11-09T03:00:00Z", "session_id": "s"}]     # 卡住 2 小时 → running_stale
        tasks = [{"id": uid(n), "title": f"pm-{name}", "workflow": "多Agent · 项目管理", "step": "调度", "state": "IN_PROGRESS",
                  "description": f"mgmt_root: {root}", "sessions": idle} for n, (name, root) in enumerate((("bad", bad), ("good", good)), 1)]
        snap = os.path.join(tmp, "snap.json")
        json.dump({"tasks": tasks}, open(snap, "w", encoding="utf-8"))

        def cli(*extra, now="2026-11-09T05:00:00+00:00"):
            r = subprocess.run([sys.executable, stage_py, "--snapshot", snap, "--now", now, "--json", *extra],
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, [json.loads(l) for l in r.stdout.splitlines() if l.strip()], r.stderr

        out_md = os.path.join(good, "agents", "guard", "stage.md")
        code, alerts, err = cli("--state-dir", state, "--dry-run")
        assert code == 0 and len(alerts) == 2 and not os.path.exists(state) and not os.path.exists(out_md), (code, alerts, err)
        code, alerts, err = cli()                                  # 快照模式不带 --state-dir：也不写
        assert code == 0 and not os.path.exists(out_md), (code, err)
        code, alerts, err = cli("--state-dir", state)
        assert code == 1 and "pm-bad" in err and os.path.exists(out_md), (code, err)
        assert {a["project"] for a in alerts} == {"pm-bad", "pm-good"}, alerts          # 出错的项目告警也已输出
        assert not os.path.exists(os.path.join(state, f"{uid(1)}.json")), "写不进去的项目不应记为已告警"
        with open(os.path.join(state, f"{uid(2)}.json"), "w") as f:
            f.write('{"0000')                                      # 写到一半的状态文件
        code, alerts, err = cli("--state-dir", state, now="2026-11-09T05:20:00+00:00")
        assert code == 1 and "pm-good" in {a["project"] for a in alerts}, (code, alerts, err)
        assert json.load(open(os.path.join(state, f"{uid(2)}.json"), encoding="utf-8")), "状态文件应被重新写好"


def test_stuck_and_parent_done():
    """v3.3.3：旧会话一直 RUNNING（消息永久排队）、模块已完成而子任务还在跑 → 都告警 pm，不升级为 pm_unresponsive。"""
    now = ts("2026-11-09T05:00:00Z")
    fresh = {"state": "RUNNING", "updated_at": "2026-11-09T04:58:00Z", "session_id": "aaaaaaaa-new"}
    stale = {"state": "RUNNING", "updated_at": "2026-11-09T03:00:00Z", "session_id": "bbbbbbbb-old"}
    idle = {"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T03:00:00Z", "session_id": "cccccccc-idle"}

    mod = task(11, "模块管理", "验收调查", f"pm: task {uid(1)}")
    mod["sessions"] = [fresh, stale]                                   # 验收会话在跑，模块 agent 的旧会话卡住
    rows, alerts, st = evaluate([mod], now, {}, uid(1))
    assert rows[0]["category"] == "等上级：旧会话卡住" and rows[0]["value"].startswith("bbbbbbbb"), rows
    assert [(a["signal"], a["to_task"]) for a in alerts] == [("session_stuck", uid(1))], alerts
    mod["sessions"] = [stale]                                          # 最新会话卡住仍是原来的 running_stale
    assert evaluate([mod], now, {}, uid(1))[1][0]["signal"] == "running_stale"
    mod["sessions"] = [fresh, idle]                                    # 旧会话只是空闲：不算
    assert evaluate([mod], now, {}, uid(1))[0][0]["category"] == "运行中"

    done = task(12, "模块管理", "完成", f"pm: task {uid(1)}", state="COMPLETED")
    done["sessions"] = [{"state": "COMPLETED", "updated_at": "2026-11-09T03:00:00Z"}, stale]
    rows, alerts, st = evaluate([done], now, {}, uid(1))
    assert rows[0]["category"] == "等上级：已完成但会话卡住", rows
    assert [(a["signal"], a["to_task"]) for a in alerts] == [("session_stuck", uid(1))], alerts
    done["sessions"] = [{"state": "COMPLETED", "updated_at": "2026-11-09T03:00:00Z"}]
    assert evaluate([done], now, {}, uid(1))[0][0]["category"] == "完成"

    pm = task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt")
    pm["sessions"] = [idle, stale]                                     # pm 自己的旧会话卡住：发给 pm，但不把它移到刷新
    rows, alerts, st = evaluate([pm], now, {}, uid(1))
    rows, alerts, st = evaluate([pm], now + timedelta(minutes=65), st, uid(1))
    assert [(a["signal"], a["to_task"]) for a in alerts] == [("session_stuck", uid(1))], alerts

    child = task(21, "开发", "开发", f"parent: mod:a @ task {uid(12)}")
    child["sessions"] = [fresh]
    done["sessions"] = []
    rows, a1, st = evaluate([done, child], now, {}, uid(1))
    rows, a2, st = evaluate([done, child], now + timedelta(minutes=12), st, uid(1))
    assert {r["title"]: r["category"] for r in rows}["t21"] == "等上级：模块已完成", rows
    assert [(a["signal"], a["to_task"]) for a in a1 + a2] == [("parent_done", uid(1))], (a1, a2)   # 刚看到不告警；发给 pm
    live = task(13, "模块管理", "等待开发", f"pm: task {uid(1)}")
    child2 = task(22, "开发", "开发", f"parent: mod:b @ task {uid(13)}")
    child2["sessions"] = [fresh]
    assert evaluate([live, child2], now, {}, uid(1))[0][1]["category"] == "运行中"       # 模块还在：不受影响

    # 用量上限：上限文字又以普通 agent 消息出现一次（排在那条 status 之后）时仍要认出来
    echo = {"type": "message", "author_type": "agent", "created_at": "2026-11-09T11:46:00Z",
            "content": "You've hit your 5-hour limit · resets 3:30am (Asia/Tokyo)"}
    assert usage_limit([echo, limit_status()], "S1") is not None
    said = {"type": "message", "author_type": "user", "created_at": "2026-11-09T11:46:00Z",
            "content": "did you hit your usage limit?"}
    assert usage_limit([said, limit_status()], "S1") is None           # 用户发来的消息不跳过：说明之后已有新一轮


def test_module_session_routing():
    """v3.3.3：发给模块任务的告警带上模块 agent 的会话 id（tasks.json 顶层的 module_session_id）。"""
    import tempfile
    from stage import load_module_sessions
    now = ts("2026-11-09T05:00:00Z")
    mod = task(11, "模块管理", "等待开发", f"pm: task {uid(1)}")
    dev = task(22, "开发", "等待决策", f"parent: mod:a @ task {uid(11)}")
    mod["module_session"] = "S-mod"
    _, a1, st = evaluate([mod, dev], now, {}, uid(1))
    _, a2, st = evaluate([mod, dev], now + timedelta(minutes=12), st, uid(1))
    assert [(a["signal"], a["to_task"], a.get("session_id")) for a in a1 + a2] == [("decision_pending", uid(11), "S-mod")], a2
    mod["module_session"] = None                                       # 旧项目没有记录：照旧不带
    _, a1, st = evaluate([mod, dev], now, {}, uid(1))
    _, a2, st = evaluate([mod, dev], now + timedelta(minutes=12), st, uid(1))
    assert "session_id" not in a2[0], a2
    with tempfile.TemporaryDirectory() as root:
        def put(m, doc):
            os.makedirs(os.path.join(root, "modules", m))
            with open(os.path.join(root, "modules", m, "tasks.json"), "w", encoding="utf-8") as f:
                f.write(doc if isinstance(doc, str) else json.dumps(doc))
        put("auth", {"module_task_id": "T1", "module_session_id": "S1", "tasks": []})
        put("old", {"tasks": []})
        put("half", {"module_task_id": "T3", "tasks": []})
        put("broken", "{坏的")
        put("_template", {"module_task_id": "TX", "module_session_id": "SX", "tasks": []})
        assert load_module_sessions(root) == {"T1": "S1"}, load_module_sessions(root)


def test_note_failure():
    """v3.3.3：连不上 Kandev 时在各项目的 stage.md 留一行故障提示，并记连续失败次数；at（最后一次成功）不变。"""
    import tempfile
    from stage import FAIL_MARK, note_failure
    with tempfile.TemporaryDirectory() as tmp:
        root, state = os.path.join(tmp, "mgmt"), os.path.join(tmp, "state")
        os.makedirs(os.path.join(root, "agents", "guard"))
        os.makedirs(state)
        sm = os.path.join(root, "agents", "guard", "stage.md")
        with open(sm, "w", encoding="utf-8") as f:
            f.write("# 现在在等谁\n\n> 由 kandev/stage.py 生成，不要手改。更新：2026-11-09 14:00\n\n没有需要处理的事项。\n")
        with open(os.path.join(state, "last_run.json"), "w", encoding="utf-8") as f:
            json.dump({"at": "2026-11-09T05:00:00+00:00", "projects": ["P"],
                       "mgmt_roots": [root, os.path.join(tmp, "不存在")]}, f)
        assert note_failure(state, ts("2026-11-09T05:20:00Z"), OSError("Connection refused")) == 1
        assert note_failure(state, ts("2026-11-09T05:40:00Z"), OSError("Connection refused")) == 2
        text = open(sm, encoding="utf-8").read()
        assert text.count(FAIL_MARK) == 1 and "连续 2 次" in text and "Connection refused" in text, text
        assert text.startswith("# 现在在等谁\n" + FAIL_MARK) and "更新：2026-11-09 14:00" in text, text
        beat = json.load(open(os.path.join(state, "last_run.json"), encoding="utf-8"))
        assert beat["failures"] == 2 and beat["at"] == "2026-11-09T05:00:00+00:00", beat
    with tempfile.TemporaryDirectory() as tmp:                         # 没有心跳文件也不报错
        assert note_failure(os.path.join(tmp, "new"), ts("2026-11-09T05:20:00Z"), OSError("x")) == 1


def test_session_long():
    """v3.3.3：常驻会话自上次重置被唤醒 ≥15 次 → 告警任务自己（带会话 id）；pm 不处理则 60 分钟后移到「刷新」。"""
    from stage import T_WAKES, WAKE_PAGES, detect_long, wakes_since_reset
    user = {"type": "message", "author_type": "user", "content": "[KMSG v1] ..."}
    agent = {"type": "message", "author_type": "agent", "content": "已处理"}
    reset = {"type": "status", "author_type": "agent", "content": "Context reset — new conversation started"}
    other = {"type": "status", "author_type": "agent", "content": "Agent encountered an error"}
    assert wakes_since_reset([user, agent, other, user, reset, user, user]) == (2, True)    # 新的在前，重置之前的不算
    assert wakes_since_reset([agent, user]) == (1, False)
    assert wakes_since_reset([]) == (0, False)

    class Fake:                                    # 每页 1 次唤醒；第 9 页才有重置标记
        def __init__(self, pages):
            self.pages, self.calls = pages, []

        def call(self, name, args):
            self.calls.append(args)
            i = len(self.calls) - 1
            return {"messages": [dict(m, id=f"m{i}-{j}") for j, m in enumerate(self.pages[i])],
                    "has_more": i + 1 < len(self.pages)}

    idle = [{"state": "COMPLETED", "session_id": "S-audit"}, {"state": "WAITING_FOR_INPUT", "session_id": "S-mod"}]
    k = Fake([[agent, agent, user]] * 8 + [[reset]])
    got = detect_long(k, uid(11), idle)
    assert got == {"session_id": "S-mod", "wakes": WAKE_PAGES}, got       # 翻页有上限；选的是还活着的会话，不是已结束的验收会话
    assert len(k.calls) == WAKE_PAGES, len(k.calls)
    assert k.calls[0]["message_types"] == ["message", "status"] and "before" not in k.calls[0], k.calls[0]
    assert k.calls[1]["before"] == "m0-2", k.calls[1]
    assert detect_long(Fake([[user, reset, user, user]]), uid(11), idle)["wakes"] == 1
    assert detect_long(Fake([[user] * 20, [user] * 20]), uid(11), idle)["wakes"] == 20   # 够数就不再翻页
    assert detect_long(Fake([]), uid(11), [{"state": "COMPLETED", "session_id": "S"}]) is None

    now = ts("2026-11-09T05:00:00Z")
    pm = task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt")
    mod = task(11, "模块管理", "等待开发", f"pm: task {uid(1)}")
    low = task(12, "模块管理", "等待开发", f"pm: task {uid(1)}")
    pm["long"], mod["long"] = {"session_id": "S-pm", "wakes": T_WAKES}, {"session_id": "S-mod", "wakes": T_WAKES + 3}
    low["long"] = {"session_id": "S-low", "wakes": T_WAKES - 1}
    for t in (pm, mod, low):
        t["sessions"] = [{"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:50:00Z", "session_id": "S"}]
    rows, alerts, st = evaluate([pm, mod, low], now, {}, uid(1))
    cats = {r["title"]: r["category"] for r in rows}
    assert cats == {"t1": "常驻：会话过长", "t11": "常驻：会话过长", "t12": "常驻"}, cats
    got = {(a["signal"], a["to_task"], a.get("session_id")) for a in alerts}
    assert got == {("session_long", uid(1), "S-pm"), ("session_long", uid(11), "S-mod")}, got   # 发给自己的常驻会话
    assert all(a["suggest"].startswith("refresh") for a in alerts), alerts
    rows, alerts, st = evaluate([pm, mod, low], now + timedelta(minutes=20), st, uid(1))
    assert alerts == [], alerts                                                       # 60 分钟内去重
    rows, alerts, st = evaluate([pm, mod, low], now + timedelta(minutes=65), st, uid(1))
    got = {(a["signal"], a["to_task"]) for a in alerts}
    assert got == {("pm_unresponsive", uid(1)), ("session_long", uid(11))}, got       # 只有 pm 升级；模块任务重发原信号
    assert next(a for a in alerts if a["signal"] == "pm_unresponsive")["return_step"] == "调度", alerts
    pm["long"] = {"session_id": "S-pm", "wakes": 0}                                   # 刷新之后
    assert evaluate([pm], now + timedelta(minutes=90), st, uid(1))[0][0]["category"] == "常驻"


def test_child_unrecorded():
    """v3.3.2：开发任务已在「完成」但 tasks.json 没有登记（REPORT 没送达）→ 告警模块 agent，兜底放行。"""
    now = ts("2026-11-09T05:00:00Z")

    def run2(own, mod_step="等待开发", mod_state="IN_PROGRESS", state=None):
        mod = task(11, "模块管理", mod_step, f"pm: task {uid(1)}", state=mod_state)
        d = task(21, "开发", "完成", f"parent: mod:a @ task {uid(11)}", state="COMPLETED")
        d["own_status"] = own
        rows, first, st = evaluate([mod, d], now, state or {}, uid(1))
        rows, second, st = evaluate([mod, d], now + timedelta(minutes=20), st, uid(1))
        cat = {r["title"]: r["category"] for r in rows}["t21"]
        return cat, [(a["signal"], a["to_task"]) for a in first + second], st

    c, al, st = run2("todo")
    assert c == "等上级：完成未登记" and al == [("child_unrecorded", uid(11))], (c, al)   # 第一次看到不告警，20 分钟后告警
    for own in ("merged", "dropped", "failed"):
        assert run2(own)[:2] == ("完成", []), own                                   # 已登记：正常完成
    assert run2(None)[:2] == ("完成", [])                                            # tasks.json 中查不到：不告警
    assert run2("")[0] == "等上级：完成未登记"                                        # 查到了但没有 status
    for mod_step, mod_state in (("验收调查", "IN_PROGRESS"), ("完成", "COMPLETED")):
        c, al, _ = run2("todo", mod_step, mod_state)
        assert c == "完成（tasks.json 未登记）" and al == [], (mod_step, c, al)       # 模块不在能处理的步骤：只显示
    # 60 分钟去重
    mod = task(11, "模块管理", "等待开发", f"pm: task {uid(1)}")
    d = task(21, "开发", "完成", f"parent: mod:a @ task {uid(11)}", state="COMPLETED")
    d["own_status"] = "todo"
    _, a1, st = evaluate([mod, d], now, {}, uid(1))
    _, a2, st = evaluate([mod, d], now + timedelta(minutes=20), st, uid(1))
    _, a3, st = evaluate([mod, d], now + timedelta(minutes=40), st, uid(1))
    _, a4, st = evaluate([mod, d], now + timedelta(minutes=85), st, uid(1))
    assert (len(a1), len(a2), len(a3), len(a4)) == (0, 1, 0, 1), (a1, a2, a3, a4)
    # 旧的快照里「完成」的任务没有 own_status：仍是"完成"
    assert run({}, "2026-11-09T05:00:00+00:00")[0]["core-01"] == "完成"


def test_session_not_started():
    """v3.3.2：进入步骤后 Kandev 没能启动会话、停在 SCHEDULING → 告警上级，且优先于 idle_no_signal。"""
    now = ts("2026-11-09T05:00:00Z")
    old_dev = [{"state": "COMPLETED", "updated_at": "2026-11-09T03:00:00Z"}]   # 上一步骤（开发）留下的会话

    def run2(step, state="SCHEDULING", sessions=old_dev, wf="开发", wip=None):
        t = task(21, wf, step, f"parent: mod:a @ task {uid(11)}", state=state)
        t["sessions"] = [dict(s) for s in sessions]
        if wip is not None:
            t["wip_step"], t["wip_admitted"] = True, wip
        rows, first, st = evaluate([t], now, {}, uid(1))
        rows, second, st = evaluate([t], now + timedelta(minutes=15), st, uid(1))
        return rows[0]["category"], [(a["signal"], a["to_task"]) for a in first + second]

    assert run2("审核") == ("等上级：会话未启动", [("session_not_started", uid(11))])
    assert run2("合并", sessions=[]) == ("等上级：会话未启动", [("session_not_started", uid(11))])
    assert run2("审核", state="IN_PROGRESS")[1] == [("idle_no_signal", uid(11))]     # 不是 SCHEDULING：原规则
    assert run2("审核", sessions=[{"state": "RUNNING", "updated_at": "2026-11-09T04:59:00Z"}])[1] == []   # 会话在跑
    assert run2("开发", wip=False, sessions=[]) == ("排队", [])                      # WIP 排队不算
    c, al = run2("验收调查", wf="模块管理")
    assert c == "等人：会话未启动" and al == [], (c, al)                             # W2 / W1：只给人看
    assert run2("待开发", sessions=[])[0].startswith("待开发")                       # 不是 agent 步骤


def test_load_statuses():
    import tempfile
    from stage import load_statuses
    with tempfile.TemporaryDirectory() as root:
        def put(mod, text):
            os.makedirs(os.path.join(root, "modules", mod))
            with open(os.path.join(root, "modules", mod, "tasks.json"), "w", encoding="utf-8") as f:
                f.write(text)
        put("auth", json.dumps({"tasks": [{"id": "a-1", "kandev_task_id": "K1", "status": "merged"},
                                          {"id": "a-2", "kandev_task_id": "K2"},
                                          {"id": "a-3", "status": "todo"}]}))
        put("broken", "{坏的")
        put("weird", json.dumps({"tasks": ["不是对象"]}))
        put("_template", json.dumps({"tasks": [{"id": "x", "kandev_task_id": "KX", "status": "todo"}]}))
        assert load_statuses(root) == {"K1": "merged", "K2": ""}, load_statuses(root)
        assert load_statuses(os.path.join(root, "nope")) == {}


def test_signal_table():
    """信号表 SIGNALS 的形状；classify 给出表里没有的信号时立即报错（即使停留时间还没到阈值）。"""
    import stage
    for name, sig in stage.SIGNALS.items():
        assert sig.to in (stage.SUPERIOR, stage.SELF, stage.TO_PM) and isinstance(sig.escalate, bool), name
        assert sig.suggest and sig.session in (None, "limit", "long"), name
        assert sig.message is None or sig.session, name                 # 原样发出的消息必须指明发到哪个会话
    assert not {stage.ESCALATED, stage.DISABLED} & set(stage.SIGNALS)
    for due in (True, False):
        try:
            stage.verdict("等上级：不存在", "no_such_signal", due=due)
        except KeyError:
            continue
        raise AssertionError("信号表里没有的信号应当报错")
    assert stage.verdict("等上级：可放行", "hold_ready", 3, 10, due=False)["signal"] is None
    assert {r[-2] for r in PRIORITY if r[-2]} == set(stage.SIGNALS), "PRIORITY 应覆盖信号表里的每个信号"


# 分类规则的先后：从上到下就是 classify 的判断顺序，每行是"同时满足后面几条规则的条件时，这一条生效"。
# (说明, workflow, 步骤, 上级模块, 任务的其他字段, 期望的分类, 期望的信号, 期望的告警对象)
# 上级模块：LIVE = 还在「等待开发」的模块任务，GONE = 已完成的模块任务。告警对象：PM1 / LIVE / ME（任务自己）/ None（不告警）。
PM1, LIVE, GONE, ME = "pm", "live", "gone", "me"
_FRESH = {"state": "RUNNING", "updated_at": "2026-11-09T04:58:00Z", "session_id": "aaaaaaaa-new"}
_STALE = {"state": "RUNNING", "updated_at": "2026-11-09T03:00:00Z", "session_id": "bbbbbbbb-old"}
_IDLE = {"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:00:00Z", "session_id": "cccccccc-idle"}
_ENDED = {"state": "COMPLETED", "updated_at": "2026-11-09T04:00:00Z", "session_id": "dddddddd-done"}
_FAILED = {"state": "FAILED", "updated_at": "2026-11-09T04:00:00Z", "session_id": "eeeeeeee-fail"}
_LIM_DUE = {"session_id": "S-lim", "at": "2026-11-09T03:00:00+00:00", "resets_at": "2026-11-09T04:00:00+00:00"}
_LIM_WAIT = {**_LIM_DUE, "resets_at": "2026-11-09T06:00:00+00:00"}
PRIORITY = [
    ("完成的模块留着卡住的会话", "模块管理", "完成", None, {"state": "COMPLETED", "sessions": [_ENDED, _STALE]},
     "等上级：已完成但会话卡住", "session_stuck", PM1),
    ("完成但 tasks.json 未登记", "开发", "完成", LIVE, {"state": "COMPLETED", "own_status": "todo"},
     "等上级：完成未登记", "child_unrecorded", LIVE),
    ("完成先于其他一切", "开发", "完成", LIVE, {"state": "COMPLETED", "own_status": "merged", "perm": 1, "limit": _LIM_DUE},
     "完成", None, None),
    ("权限请求先于提问、门禁、用量上限", "项目管理", "人工终审", None, {"perm": 2, "question": True, "limit": _LIM_DUE},
     "等人：权限请求", None, None),
    ("autonomy 2 立项确认的提问挂了 60 分钟：超时先于提问 → pm 自己", "项目管理", "立项确认", None,
     {"question": True, "sessions": [_IDLE], "description": "[TASK v1]\nautonomy: 2\nmode: attended\nmgmt_root: D:/p1-mgmt"},
     "等人：立项确认（超时）", "gate_timeout", ME),
    ("提问先于用量上限", "开发", "开发", LIVE, {"question": True, "limit": _LIM_DUE, "sessions": [_IDLE]},
     "等人：提问", None, None),
    ("门禁先于用量上限", "项目管理", "人工终审", None, {"limit": _LIM_DUE, "sessions": [_IDLE]},
     "等人：人工终审", None, None),
    ("用量上限已重置，先于旧会话卡住", "开发", "开发", LIVE, {"limit": _LIM_DUE, "sessions": [_IDLE, _STALE]},
     "等上限：已重置，待恢复", "limit_resume", ME),
    ("用量上限未重置，先于等待决策", "开发", "等待决策", LIVE, {"limit": _LIM_WAIT, "sessions": [_IDLE]},
     "等上限：等待重置", None, None),
    ("旧会话卡住先于模块已完成", "开发", "开发", GONE, {"sessions": [_FRESH, _STALE]},
     "等上级：旧会话卡住", "session_stuck", PM1),
    ("模块已完成先于等待决策", "开发", "等待决策", GONE, {"sessions": [_IDLE]},
     "等上级：模块已完成", "parent_done", PM1),
    ("接收的会话失败只给人看", "项目管理", "接收", None, {"sessions": [_FAILED]},
     "等人：接收会话失败", None, None),
    ("等待决策先于会话失败", "开发", "等待决策", LIVE, {"sessions": [_FAILED]},
     "等上级：等待决策", "decision_pending", LIVE),
    ("会话失败先于会话未启动", "开发", "审核", LIVE, {"state": "SCHEDULING", "sessions": [_FAILED]},
     "等上级：会话失败", "session_failed", LIVE),
    ("模块任务会话失败 → pm", "模块管理", "模块规划", None, {"sessions": [_FAILED]},
     "等上级：会话失败", "session_failed", PM1),
    ("pm 会话失败 → pm 自己", "项目管理", "调度", None, {"sessions": [_FAILED]},
     "等上级：会话失败", "session_failed", ME),
    ("会话未启动先于空闲未推进", "开发", "审核", LIVE, {"state": "SCHEDULING", "sessions": [_ENDED]},
     "等上级：会话未启动", "session_not_started", LIVE),
    ("W2 会话未启动只给人看", "模块管理", "验收调查", None, {"state": "SCHEDULING", "sessions": [_ENDED]},
     "等人：会话未启动", None, None),
    ("前置失败先于可放行", "开发", "待开发", LIVE, {"blocker_status": ["merged", "failed"]},
     "等上级：前置失败", "hold_broken", LIVE),
    ("前置全部完成", "开发", "待开发", LIVE, {"blocker_status": ["merged", "dropped"]},
     "等上级：可放行", "hold_ready", LIVE),
    ("空闲未推进", "开发", "审核", LIVE, {"sessions": [_IDLE]},
     "等上级：空闲未推进", "idle_no_signal", LIVE),
    ("W1 空闲未推进只给人看", "项目管理", "项目验收", None, {"sessions": [_IDLE]},
     "等人：空闲未推进", None, None),
    ("最新会话疑似卡住", "开发", "开发", LIVE, {"sessions": [_STALE]},
     "等上级：疑似卡住", "running_stale", LIVE),
    ("疑似卡住先于会话过长", "模块管理", "等待开发", None, {"sessions": [_STALE], "long": {"session_id": "S-long", "wakes": 99}},
     "等上级：疑似卡住", "running_stale", PM1),
    ("开发步骤前置未满足先于排队", "开发", "开发", LIVE, {"blocker_status": ["todo"]},
     "等上级：开发步骤前置未满足", "dev_blocked", LIVE),
    ("WIP 未准入", "开发", "开发", LIVE, {"wip_step": True, "wip_admitted": False, "sessions": [_FRESH]},
     "排队", None, None),
    ("待开发，前置未完成", "开发", "待开发", LIVE, {"blocker_status": ["todo"]},
     "待开发", None, None),
    ("常驻会话过长", "模块管理", "等待开发", None, {"sessions": [_IDLE], "long": {"session_id": "S-long", "wakes": 99}},
     "常驻：会话过长", "session_long", ME),
    ("常驻", "模块管理", "等待开发", None, {"sessions": [_IDLE]},
     "常驻", None, None),
    ("运行中", "开发", "开发", LIVE, {"sessions": [_FRESH]},
     "运行中", None, None),
]


def test_priority():
    """PRIORITY 逐行核对：分类、信号、告警对象。每个任务都已在当前步骤停留 30 分钟（停留阈值都已满足）。"""
    now = ts("2026-11-09T05:00:00Z")
    ids = {PM1: uid(1), LIVE: uid(11), GONE: uid(12), ME: uid(50)}
    for name, wf, step, parent, extra, want_cat, want_sig, want_to in PRIORITY:
        desc = f"parent: mod:a @ task {ids[parent]}" if parent else f"pm: task {uid(1)}"
        me = task(1 if wf == "项目管理" else 50, wf, step, "[TASK v1]\nmgmt_root: D:/p1-mgmt" if wf == "项目管理" else desc)
        me.update({k: ([dict(x) for x in v] if k == "sessions" else v) for k, v in extra.items()})
        tasks = [task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt"),
                 task(11, "模块管理", "等待开发", f"pm: task {uid(1)}"),
                 task(12, "模块管理", "完成", f"pm: task {uid(1)}", state="COMPLETED")]
        tasks = [t for t in tasks if t["id"] != me["id"]] + [me]
        state = {t["id"]: {"step": t["step"], "since": "2026-11-09T04:30:00+00:00"} for t in tasks}
        rows, alerts, _ = evaluate(tasks, now, state, uid(1))
        mine = [a for a in alerts if a["object"].endswith(me["id"])]
        assert rows[-1]["category"] == want_cat, (name, rows[-1]["category"])
        want = [(want_sig, me["id"] if want_to == ME else ids[want_to])] if want_sig else []
        assert [(a["signal"], a["to_task"]) for a in mine] == want, (name, mine)


def test_gate_timeout():
    """立项确认超时：autonomy 2、plan_only 不是 true、pm 的提问还挂着、且最新会话 ≥T_GATE 分钟没有更新才告警。"""
    import stage
    now = ts("2026-11-09T05:00:00Z")
    head = "[TASK v1]\n{}mode: attended\nmgmt_root: D:/p1-mgmt"

    def sig(extra_head, asked="2026-11-09T04:30:00Z", step="立项确认", question=True, since="2026-11-09T03:00:00+00:00"):
        """asked：pm 会话最后一次更新（发出提问）的时间；since：任务进入本步骤的时间。"""
        t = task(1, "项目管理", step, head.format(extra_head))
        t.update({"question": question, "sessions": [{**_IDLE, "updated_at": asked}], "since": ts(since)})
        return stage.classify(t, now, {t["id"]: t})

    hit = sig("autonomy: 2\n")
    assert (hit["category"], hit["signal"], hit["value"], hit["threshold"]) == ("等人：立项确认（超时）", "gate_timeout", 30, stage.T_GATE), hit
    assert sig("autonomy: 2\nplan_only: false\n")["signal"] == "gate_timeout"
    for extra in ("autonomy: 1\n", "autonomy: 3\n", "autonomy: 2\nplan_only: true\n", ""):
        got = sig(extra)
        assert got["signal"] is None and got["category"] == "等人：提问", (extra, got)
    # 用户选了"先不决定"：没有待答的提问，停留再久也不触发
    got = sig("autonomy: 2\n", question=False)
    assert got["signal"] is None and got["category"] == "等人：立项确认", got
    # 用户 5 分钟前答了第 1 批、pm 刚发出第 2 批：任务已在本步骤 2 小时，但提问只挂了 5 分钟
    got = sig("autonomy: 2\n", asked="2026-11-09T04:55:00Z")
    assert got["signal"] is None and got["category"] == "等人：提问", got
    assert sig("autonomy: 2\n", asked="2026-11-09T04:45:00Z")["signal"] is None, "提问挂着没到 T_GATE 不告警"
    assert sig("autonomy: 2\n", step="人工终审")["signal"] is None, "人工终审不设超时"
    keep, stage.T_GATE = stage.T_GATE, 0
    try:
        assert sig("autonomy: 2\n")["signal"] is None, "T_GATE=0 关闭"
    finally:
        stage.T_GATE = keep


def test_dedup_flapping():
    """时有时无的信号在 60 分钟内只告警一次（旧版在信号消失的那次巡检清掉记录，回来就立刻重发）；
    一直存在的信号满 60 分钟重发；换过步骤算新的情况。"""
    now = ts("2026-11-09T05:00:00Z")

    def patrol(t, minutes, st, sessions=None, **fields):
        at = now + timedelta(minutes=minutes)
        if sessions is not None:
            t["sessions"] = [{"state": s, "updated_at": (at - timedelta(minutes=age)).isoformat(), "session_id": "S"}
                             for s, age in sessions]
        t.update(fields)
        _, alerts, st = evaluate([t], at, st, uid(1))
        return [(a["signal"], a["to_task"]) for a in alerts], st

    idle, running = [("WAITING_FOR_INPUT", 15)], [("RUNNING", 1)]
    hit = [("idle_no_signal", uid(11))]
    d = task(21, "开发", "审核", f"parent: mod:a @ task {uid(11)}")
    got, st = patrol(d, 0, {}, idle)
    assert got == hit, got
    got, st = patrol(d, 20, st, running)                    # 信号消失一次
    assert got == [] and st[uid(21)]["alerts"], (got, st)   # 记录保留
    got, st = patrol(d, 40, st, idle)                       # 又出现：距上次告警 40 分钟，不重发
    assert got == [], got
    got, st = patrol(d, 59, st, idle)
    assert got == [], got
    got, st = patrol(d, 60, st, idle)                       # 满 60 分钟重发
    assert got == hit, got
    got, st = patrol(d, 80, st, running)
    got, st = patrol(d, 125, st, running)                   # 过期的记录被清掉
    assert got == [] and st[uid(21)]["alerts"] == {}, (got, st)
    got, st = patrol(d, 130, st, idle)
    assert got == hit, got

    d = task(22, "开发", "审核", f"parent: mod:a @ task {uid(11)}")     # 一直存在：0、60 分钟各一次
    sent, st = [], {}
    for m in (0, 20, 40, 60, 80):
        got, st = patrol(d, m, st, idle)
        sent.append(len(got))
    assert sent == [1, 0, 0, 1, 0], sent

    lim = {"session_id": "S-dev", "at": "2026-11-09T03:00:00+00:00", "resets_at": "2026-11-09T04:00:00+00:00"}
    d = task(23, "开发", "开发", f"parent: mod:a @ task {uid(11)}")     # 恢复后又碰到上限：距上次恢复满 60 分钟才再发
    got, st = patrol(d, 0, {}, idle, limit=lim)
    assert got == [("limit_resume", uid(23))], got
    got, st = patrol(d, 20, st, running, limit=None)
    got, st = patrol(d, 40, st, idle, limit=lim)
    assert got == [], got
    got, st = patrol(d, 60, st, idle, limit=lim)
    assert got == [("limit_resume", uid(23))], got

    d = task(24, "开发", "等待决策", f"parent: mod:a @ task {uid(11)}")  # 换过步骤再回来：新的情况，不受上次告警影响
    got, st = patrol(d, 0, {}, idle)
    got, st = patrol(d, 12, st, idle)
    assert got == [("decision_pending", uid(11))], got
    got, st = patrol(d, 20, st, running, step="开发")
    got, st = patrol(d, 25, st, idle, step="等待决策")
    got, st = patrol(d, 37, st, idle)
    assert got == [("decision_pending", uid(11))], got


def test_escalation_needs_continuity():
    """pm_unresponsive：只有信号自上次告警起每次巡检都在，才升级；中途消除过就只重发原信号，再持续 60 分钟才升级。"""
    now = ts("2026-11-09T05:00:00Z")
    pm = task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt")

    def patrol(minutes, st, stuck=True):
        at = now + timedelta(minutes=minutes)
        pm["sessions"] = [{"state": "RUNNING", "updated_at": (at - timedelta(minutes=120 if stuck else 1)).isoformat()}]
        _, alerts, st = evaluate([pm], at, st, uid(1))
        return [a["signal"] for a in alerts], st

    got, st = patrol(0, {})
    assert got == ["running_stale"] and st[uid(1)]["streak"] == "running_stale", (got, st)
    got, st = patrol(20, st, stuck=False)                   # pm 动了一下：信号消除
    assert got == [] and st[uid(1)]["streak"] is None, (got, st)
    got, st = patrol(40, st)                                # 又卡住：60 分钟内不重发
    assert got == [], got
    got, st = patrol(65, st)                                # 到期：重发原信号，不升级
    assert got == ["running_stale"], got
    got, st = patrol(100, st)
    assert got == [], got
    got, st = patrol(130, st)                               # 这次是连续 65 分钟没消除：升级
    assert got == ["pm_unresponsive"], got

    got, st = patrol(0, {})                                 # 对照：一直没消除
    got, st = patrol(30, st)
    got, st = patrol(65, st)
    assert got == ["pm_unresponsive"], got

    old = {uid(1): {"step": "调度", "since": now.isoformat(), "alerts": {"running_stale": now.isoformat()}}}
    got, st = patrol(65, old)                               # 升级前写下的状态文件没有 streak：按一直没消除处理
    assert got == ["pm_unresponsive"], got


def test_parse_reset():
    # 实际出现过的文字（2026-11-09，Asia/Tokyo = UTC+9）
    assert parse_reset("Internal error: You've hit your weekly limit · resets 9pm (Asia/Tokyo)",
                       ts("2026-11-09T11:45:30Z")) == ts("2026-11-09T12:00:00Z")
    assert parse_reset("You've hit your 5-hour limit · resets 11:50pm (Asia/Tokyo)",
                       ts("2026-11-09T12:13:11Z")) == ts("2026-11-09T14:50:00Z")
    assert parse_reset("resets 2:10pm (Asia/Tokyo)", ts("2026-11-09T06:00:00Z")) == ts("2026-11-10T05:10:00Z")  # 已过 → 次日
    assert parse_reset("resets Nov 12, 9pm (Asia/Tokyo)", ts("2026-11-09T12:00:00Z")) == ts("2026-11-12T12:00:00Z")
    assert parse_reset("resets 12am (UTC)", ts("2026-11-09T12:00:00Z")) == ts("2026-11-10T00:00:00Z")
    assert parse_reset("resets soon", ts("2026-11-09T12:00:00Z")) is None
    assert parse_reset("resets 9pm (Mars/Base)", ts("2026-11-09T12:00:00Z")) is None


def limit_status(at="2026-11-09T11:45:39Z", msg="Internal error: You've hit your weekly limit · resets 9pm (Asia/Tokyo)"):
    return {"type": "status", "created_at": at, "session_id": "S1", "content": msg,
            "metadata": {"failure_code": "quota_limited", "scope": "turn", "recovery_actions": False,
                         "provider_error": {"error_kind": "rate_limit", "message": msg}}}


def test_usage_limit():
    agent_msg = {"type": "message", "created_at": "2026-11-09T11:45:30Z", "content": "You've hit your weekly limit"}
    tool = {"type": "tool_execute", "created_at": "2026-11-09T11:45:50Z"}
    lim = usage_limit([tool, limit_status(), agent_msg], "S1")             # 新的在前；工具消息跳过
    assert lim and lim["session_id"] == "S1" and ts(lim["resets_at"]) == ts("2026-11-09T12:00:00Z"), lim
    later = {"type": "message", "created_at": "2026-11-09T15:37:02Z", "content": "continue"}
    assert usage_limit([later, limit_status()], "S1") is None              # 之后已有新消息 → 已恢复
    crash = {"type": "status", "created_at": "2026-11-09T17:22:29Z", "content": "Agent encountered an error: ...",
             "metadata": {"recovery_actions": True, "scope": "session"}}
    assert usage_limit([crash, limit_status()], "S1") is None              # 进程退出类错误不算
    assert usage_limit([], "S1") is None


def test_limit_resume():
    lim = {"session_id": "S-dev", "at": "2026-11-09T11:45:39+00:00", "resets_at": "2026-11-09T12:00:00+00:00"}
    pm = task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt")
    mod = task(11, "模块管理", "等待开发", f"pm: task {uid(1)}")
    dev = task(21, "开发", "开发", f"parent: mod:a @ task {uid(11)}")
    for t in (pm, mod, dev):
        t["sessions"] = [{"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T11:45:39Z", "session_id": f"S{t['id']}"}]
    dev["limit"], pm["limit"] = lim, {**lim, "session_id": "S-pm"}
    tasks = [pm, mod, dev]

    rows, alerts, st = evaluate(tasks, ts("2026-11-09T11:55:00Z"), {}, uid(1))   # 还没到重置时间
    cats = {r["title"]: r["category"] for r in rows}
    assert cats["t21"] == "等上限：等待重置" and cats["t1"] == "等上限：等待重置", cats
    assert alerts == [], alerts                                              # 不打扰上级

    rows, alerts, st = evaluate(tasks, ts("2026-11-09T12:03:00Z"), st, uid(1))   # 已过重置时间 2 分钟以上
    got = {(a["signal"], a["to_task"], a.get("session_id")) for a in alerts}
    assert got == {("limit_resume", uid(21), "S-dev"), ("limit_resume", uid(1), "S-pm")}, got   # 只恢复自己，带会话
    assert all(a["message"].startswith("continue") for a in alerts), alerts

    rows, alerts, st = evaluate(tasks, ts("2026-11-09T12:30:00Z"), st, uid(1))
    assert alerts == [], alerts                                              # 60 分钟内不重复
    rows, alerts, st = evaluate(tasks, ts("2026-11-09T13:10:00Z"), st, uid(1))
    assert {a["signal"] for a in alerts} == {"limit_resume"}, alerts         # pm 也不升级为 pm_unresponsive


def test_should_disable():
    now = ts("2026-11-10T01:00:00Z")
    beat = {"at": "2026-11-10T00:40:00+00:00", "projects": ["P"]}
    done = task(1, "项目管理", "完成", "", state="COMPLETED")
    idle = task(21, "开发", "开发", "")
    idle["sessions"] = [{"state": "WAITING_FOR_INPUT"}]
    running = task(22, "开发", "开发", "")
    running["sessions"] = [{"state": "RUNNING"}]
    limited = task(23, "开发", "开发", "")
    limited["limit"] = {"session_id": "S"}
    assert should_disable(beat, [], [done, idle], now)[0] is True
    assert should_disable(beat, [{"pm_task": "x"}], [done], now)[0] is False          # 还有项目
    assert should_disable(beat, [], [done, running], now)[0] is False                 # 还有会话在运行
    assert should_disable(beat, [], [done, limited], now)[0] is False                 # 停在用量上限不算正常结束
    assert should_disable({**beat, "projects": []}, [], [done], now)[0] is False      # 本来就没有项目
    assert should_disable({**beat, "at": "2026-11-09T17:00:00+00:00"}, [], [done], now)[0] is False   # 心跳太旧
    assert should_disable({}, [], [done], now)[0] is False


def test_steps_v32():
    """各步骤按预期分类；不认识的步骤名不报错。"""
    now = ts("2026-11-09T05:00:00Z")
    idle = [{"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:00:00Z"}]   # 空闲 60 分钟
    cases = [
        ("项目管理", "环境基线", idle, "运行中"),                # v3.1 的步骤（已不支持）：和其他不认识的步骤名一样
        ("项目管理", "模块下发", idle, "等人：空闲未推进"),
        ("项目管理", "接收", idle, "等人：空闲未推进"),          # v3.3 入口：描述还没有 [TASK v1] 头，不告警
        ("项目管理", "接收", [], "排队"),
        ("项目管理", "接收", [{"state": "FAILED", "updated_at": "2026-11-09T04:00:00Z"}], "等人：接收会话失败"),
        ("项目管理", "接收", [{"state": "RUNNING", "updated_at": "2026-11-09T04:00:00Z"}], "等人：接收疑似卡住"),
        ("项目管理", "调度", idle, "常驻"),
        ("项目管理", "人工终审", idle, "等人：人工终审"),
        ("项目管理", "某个未来的步骤", idle, "运行中"),            # 不认识的步骤名不报错
        ("模块管理", "验收调查", idle, "等上级：空闲未推进"),
        ("模块管理", "验收调查", [], "排队"),                      # 每次新会话：还没有会话时排队
        ("模块管理", "等待开发", idle, "常驻"),
        ("开发", "合并", idle, "等上级：空闲未推进"),              # 合并自己完成并进入「完成」；卡住时仍要告警
        ("开发", "合并", [], "排队"),
        ("开发", "等待决策", idle, "等上级：等待决策"),
    ]
    tasks = []
    for i, (wf, step, sessions, _) in enumerate(cases, 1):
        t = task(i, wf, step, "")
        t["sessions"] = [dict(s) for s in sessions]
        tasks.append(t)
    rows, alerts, _ = evaluate(tasks, now, {}, uid(1))
    for (wf, step, _, want), r in zip(cases, rows):
        assert r["category"].startswith(want), (wf, step, r["category"], want)
    assert not any(a["step"] == "接收" for a in alerts), alerts          # 「接收」没有上级，任何情况都不告警
    from stage import header_field
    assert header_field("[TASK v1]\nmgmt_root:\nmode: attended", "mgmt_root") == ""   # 空值不取下一行
    assert header_field("[TASK v1]\nmgmt_root: D:/x \nmode: attended", "mgmt_root") == "D:/x"


def test_pm_unresponsive():
    """pm_unresponsive 只对常驻步骤（调度）触发，并带 return_step；其他步骤到期后重发原信号。"""
    for step, escalates in (("调度", True), ("项目验收", False), ("收尾合并", False)):
        pm = task(1, "项目管理", step, "[TASK v1]\nmgmt_root: D:/p1-mgmt")
        pm["sessions"] = [{"state": "RUNNING", "updated_at": "2026-11-09T03:00:00Z"}]    # RUNNING 但很久没更新
        rows, alerts, st = evaluate([pm], ts("2026-11-09T05:00:00Z"), {}, uid(1))
        assert [(a["signal"], a["to_task"]) for a in alerts] == [("running_stale", uid(1))], (step, alerts)
        rows, alerts, st = evaluate([pm], ts("2026-11-09T05:30:00Z"), st, uid(1))
        assert alerts == [], alerts                                                       # 60 分钟内去重
        rows, alerts, st = evaluate([pm], ts("2026-11-09T06:05:00Z"), st, uid(1))
        assert len(alerts) == 1, alerts
        if escalates:
            assert alerts[0]["signal"] == "pm_unresponsive" and alerts[0]["return_step"] == step, alerts
        else:
            assert alerts[0]["signal"] == "running_stale" and "return_step" not in alerts[0], (step, alerts)


def test_w1_idle_and_decision():
    now = ts("2026-11-09T05:00:00Z")
    idle = [{"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:00:00Z"}]
    # W1 在要求完成信号的步骤空闲：只体现在 stage.md，不告警（评审者 / 机械 agent 的会话，发给 pm 没人处理）
    for step in ("立项规划", "立项评审", "模块下发", "项目验收", "收尾合并"):
        pm = task(1, "项目管理", step, "")
        pm["sessions"] = [dict(s) for s in idle]
        rows, alerts, _ = evaluate([pm], now, {}, uid(1))
        assert alerts == [] and rows[0]["category"] == "等人：空闲未推进", (step, rows, alerts)
        assert step in rows[0]["value"] and "60" in rows[0]["value"], rows
    # W2 / W3 的规则不变
    mod = task(11, "模块管理", "模块规划", f"pm: task {uid(1)}")
    dev = task(21, "开发", "开发", f"parent: mod:a @ task {uid(11)}")
    for t in (mod, dev):
        t["sessions"] = [dict(s) for s in idle]
    rows, alerts, _ = evaluate([task(1, "项目管理", "调度", ""), mod, dev], now, {}, uid(1))
    assert {(a["signal"], a["to_task"]) for a in alerts} == {("idle_no_signal", uid(1)), ("idle_no_signal", uid(11))}, alerts
    # 开发任务在「等待决策」：不是 idle_no_signal；停留 ≥10 分钟向模块 agent 告警一次，60 分钟内不重复
    d = task(22, "开发", "等待决策", f"parent: mod:a @ task {uid(11)}")
    d["sessions"] = [dict(s) for s in idle]
    rows, alerts, st = evaluate([d], now, {}, uid(1))
    assert rows[0]["category"] == "等上级：等待决策" and alerts == [], (rows, alerts)    # 刚进入
    rows, alerts, st = evaluate([d], now + timedelta(minutes=12), st, uid(1))
    assert [(a["signal"], a["to_task"]) for a in alerts] == [("decision_pending", uid(11))], alerts
    rows, alerts, st = evaluate([d], now + timedelta(minutes=40), st, uid(1))
    assert alerts == [], alerts


def test_hold_from_tasks_json():
    """「待开发」的前置只取自 tasks.json 的 status（W3 任务不设 Kandev 的 blocked_by）。"""
    now = ts("2026-11-09T05:00:00Z")
    later = now + timedelta(minutes=15)

    def cat(statuses, step="待开发"):
        h = task(30, "开发", step, f"parent: mod:a @ task {uid(11)}")
        h["blocker_status"] = statuses
        rows, first, st = evaluate([h], now, {}, uid(1))
        rows, second, st = evaluate([h], later, st, uid(1))              # 15 分钟后（去重：同一信号不重复）
        return rows[0]["category"], [(a["signal"], a["to_task"]) for a in first + second]

    assert cat(["merged", "dropped"]) == ("等上级：可放行", [("hold_ready", uid(11))])
    assert cat(["merged", "todo"]) == ("待开发", [])
    assert cat(["merged", None]) == ("待开发", [])                                   # blocked_by 在 tasks.json 里查不到
    assert cat(["merged", "failed"]) == ("等上级：前置失败", [("hold_broken", uid(11))])
    assert cat(["held"]) == ("待开发", [])
    assert cat([]) == ("等上级：可放行", [("hold_ready", uid(11))])                    # 登记了、没有前置，却一直停在「待开发」
    assert cat(None) == ("待开发（tasks.json 中查不到前置）", [])                      # 读不到 tasks.json：只显示，不告警
    # 「开发」步骤里前置未满足、没有会话：不再无声地排队，向模块 agent 告警一次
    c, al = cat(["todo"], step="开发")
    assert c == "等上级：开发步骤前置未满足" and al == [("dev_blocked", uid(11))], (c, al)
    c, al = cat(["merged"], step="开发")                                             # 前置满足：照常排队
    assert c == "排队" and al == [], (c, al)
    c, al = cat(None, step="开发")                                                   # 没有前置信息：照常排队
    assert c == "排队" and al == [], (c, al)


def test_module_prereqs():
    """W2 任务在「模块规划」、Kandev 的 blocked_by 还没解除，会话却被提前启动后空闲（实测：结合测试模块收到 pm 的消息后
    空闲 34 分钟，误报 idle_no_signal）→ 排队：等前置模块，不告警；前置全部完成后照常 idle_no_signal。"""
    from stage import WAIT_PREREQ, kandev_deps, render
    now = ts("2026-11-09T05:00:00Z")
    idle = {"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:26:00Z", "session_id": "s-idle"}
    stale = {"state": "RUNNING", "updated_at": "2026-11-09T03:00:00Z", "session_id": "s-stale"}

    def mod(n, name, step, extra="", state="IN_PROGRESS"):
        t = task(n, "模块管理", step, f"[TASK v1]\nrole: module\nscope: mod:{name}\npm: task {uid(1)}\n{extra}", state)
        t["title"] = f"mod:{name}"
        return t

    def world(base_done=True, auth_done=False, ui_done=False):
        return [task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt"),
                mod(11, "baseline", "完成" if base_done else "等待开发", "kind: baseline\nbranch: mod/baseline base main",
                    "COMPLETED" if base_done else "IN_PROGRESS"),
                mod(12, "auth", "完成" if auth_done else "等待开发", "branch: mod/auth base mod/baseline",
                    "COMPLETED" if auth_done else "IN_PROGRESS"),
                mod(13, "ui", "完成" if ui_done else "模块规划", "branch: mod/ui base mod/auth",
                    "COMPLETED" if ui_done else "IN_PROGRESS"),
                mod(15, "auth-fix-1", "模块规划", "branch: mod/auth-fix-1 base mod/auth"),
                mod(14, "integration-test", "模块规划", "kind: integration\nbranch: mod/integration-test base integration")]

    def check(tasks, sessions=(idle,)):
        tasks[-1]["sessions"] = [dict(s) for s in sessions]
        state = {t["id"]: {"step": t["step"], "since": "2026-11-09T04:20:00+00:00"} for t in tasks}
        rows, alerts, _ = evaluate(tasks, now, state, uid(1))
        it = next(r for r in rows if r["id"] == uid(14))
        return it, [(a["signal"], a["to_task"]) for a in alerts if a["object"].endswith(uid(14))], rows, alerts

    it, al, rows, alerts = check(world())
    assert (it["category"], it["value"], al) == (WAIT_PREREQ, "mod:auth、mod:ui", []), (it, al)   # 修复模块不算前置
    text = render(rows, alerts, "now")
    assert f"- mod:integration-test（模块规划）：{WAIT_PREREQ}（mod:auth、mod:ui）" in text, text
    it, al, *_ = check(world(base_done=False, auth_done=True, ui_done=True))
    assert (it["category"], it["value"]) == (WAIT_PREREQ, "mod:baseline"), it
    it, al, *_ = check(world(auth_done=True, ui_done=True))                                  # 前置全部完成：照常告警
    assert it["category"] == "等上级：空闲未推进" and al == [("idle_no_signal", uid(1))], (it, al)
    it, al, *_ = check(world(), sessions=(stale,))                                           # 会话卡住仍然报
    assert al == [("running_stale", uid(1))], al
    it, al, *_ = check(world(), sessions=())                                                 # 还没有会话
    assert it["category"] == WAIT_PREREQ and al == [], (it, al)

    # 普通模块：依赖 baseline 和 branch 行 base 指向的模块；修复模块、baseline 没有推导出的前置
    w = world()
    w[3]["sessions"] = [dict(idle)]
    rows, alerts, _ = evaluate(w, now, {t["id"]: {"step": t["step"], "since": "2026-11-09T04:20:00+00:00"} for t in w}, uid(1))
    by = {r["id"]: r for r in rows}
    assert (by[uid(13)]["category"], by[uid(13)]["value"]) == (WAIT_PREREQ, "mod:auth"), by[uid(13)]
    assert by[uid(15)]["category"] == "排队", by[uid(15)]

    # Kandev 返回的依赖（没有 scope 也生效）；不属于本项目的 id 忽略
    plain = task(30, "模块管理", "模块规划", f"pm: task {uid(1)}")
    plain.update({"sessions": [dict(idle)], "deps": [uid(12), "ffffffff-0000-0000-0000-000000000000"]})
    rows, alerts, _ = evaluate(world()[:3] + [plain], now, {plain["id"]: {"step": "模块规划", "since": "2026-11-09T04:20:00+00:00"}}, uid(1))
    assert (rows[-1]["category"], rows[-1]["value"]) == (WAIT_PREREQ, "mod:auth") and not alerts, (rows[-1], alerts)
    plain["deps"] = ["ffffffff-0000-0000-0000-000000000000"]
    rows, alerts, _ = evaluate([plain], now, {plain["id"]: {"step": "模块规划", "since": "2026-11-09T04:20:00+00:00"}}, uid(1))
    assert rows[-1]["category"] == "等上级：空闲未推进", rows[-1]

    assert kandev_deps({}) is None and kandev_deps({"blocked_by": []}) == []
    assert kandev_deps({"depends_on": ["a", {"id": "b"}, {"task_id": "c"}, 3]}) == ["a", "b", "c"]


def test_load_blockers():
    import tempfile
    with tempfile.TemporaryDirectory() as root:
        def put(mod, text):
            os.makedirs(os.path.join(root, "modules", mod))
            with open(os.path.join(root, "modules", mod, "tasks.json"), "w", encoding="utf-8") as f:
                f.write(text)
        put("auth", json.dumps({"tasks": [
            {"id": "a-1", "kandev_task_id": "K1", "blocked_by": [], "status": "merged"},
            {"id": "a-2", "kandev_task_id": "K2", "blocked_by": ["a-1", "a-9"], "status": "held"}]}))
        put("auth-fix-1", json.dumps({"tasks": [{"id": "f-1", "kandev_task_id": "K3", "blocked_by": ["f-0"]},
                                                {"id": "f-0", "kandev_task_id": "K4", "status": "failed"}]}))
        put("broken", "{坏的")
        put("weird", json.dumps({"tasks": ["不是对象"]}))
        put("_template", json.dumps({"tasks": [{"id": "x", "kandev_task_id": "KX"}]}))
        got = load_blockers(root)
        assert got == {"K1": [], "K2": ["merged", None], "K3": ["failed"], "K4": []}, got
        assert load_blockers(os.path.join(root, "nope")) == {}


def uid(n):
    return f"00000000-0000-0000-0000-{n:012d}"


def task(n, wf, step, desc, state="IN_PROGRESS"):
    return {"id": uid(n), "title": f"t{n}", "workflow": f"多Agent · {wf}", "step": step, "state": state,
            "description": desc, "sessions": []}


def test_grouping():
    tasks = [
        task(1, "项目管理", "调度", "[TASK v1]\nmgmt_root: D:/p1-mgmt\nparent: user\npm: self"),
        task(2, "项目管理", "立项规划", "[TASK v1]\nmgmt_root: D:/p2-mgmt\npm: self"),
        task(3, "项目管理", "完成", "[TASK v1]\nmgmt_root: D:/old-mgmt", state="COMPLETED"),
        task(11, "模块管理", "等待开发", f"parent: pm @ task {uid(1)}\npm: task {uid(1)}"),
        task(12, "模块管理", "模块规划", f"parent: pm @ task {uid(2)}\npm: task {uid(2)}"),
        task(13, "模块管理", "完成", f"pm: task {uid(3)}", state="COMPLETED"),
        task(21, "开发", "开发", f"parent: mod:a @ task {uid(11)}"),
        task(22, "开发", "待开发", f"parent: mod:b @ task {uid(12)}"),
        task(23, "开发", "完成", f"parent: mod:c @ task {uid(13)}", state="COMPLETED"),
        task(24, "开发", "开发", "parent: 不认识的任务"),
    ]
    got = {p["pm_task"]: (p["mgmt_root"], sorted(t["id"] for t in p["tasks"])) for p in group_projects(tasks)}
    assert got == {
        uid(1): ("D:/p1-mgmt", sorted([uid(1), uid(11), uid(21)])),
        uid(2): ("D:/p2-mgmt", sorted([uid(2), uid(12), uid(22)])),
    }, got                                                   # 已完成的项目和无法归属的任务不出现


def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    assert len(tests) >= 20, "没有找到测试函数"
    for name, fn in tests:
        try:
            fn()
        except Exception:
            print(f"FAIL {name}", file=sys.stderr)
            raise
    print("OK test_stage")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
