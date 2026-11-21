"""stage.py 的离线回归测试：python kandev/tests/test_stage.py（也由 check_docs.py 调用）。只用标准库。"""
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
        t.setdefault("description", ""), t.setdefault("sessions", []), t.setdefault("blockers", [])
    rows, alerts, new_state = evaluate(snap["tasks"], ts(now), state, snap["pm_task"])
    return {r["title"]: r["category"] for r in rows}, [(a["signal"], a["to_task"]) for a in alerts], new_state


def main():
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
    test_grouping()
    test_parse_reset()
    test_usage_limit()
    test_limit_resume()
    test_should_disable()
    test_steps_v32()
    test_pm_unresponsive()
    test_w1_idle_and_decision()
    test_hold_from_tasks_json()
    test_load_blockers()
    test_child_unrecorded()
    test_session_not_started()
    test_load_statuses()
    test_suggest_complete()
    test_session_long()
    test_stuck_and_parent_done()
    test_module_session_routing()
    test_note_failure()
    print("OK test_stage")


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


def test_suggest_complete():
    """每个可能发出的信号都有建议（evaluate 用 SUGGEST[...] 取值，缺了会 KeyError）。"""
    import inspect
    import re
    import stage
    src = inspect.getsource(stage.classify)                       # classify 产生的信号都要在 SUGGEST 里
    signals = set(re.findall(r'"([a-z_]+)" if ', src)) | set(re.findall(r'r\("[^"]+", "([a-z_]+)"', src))
    assert signals and signals <= set(stage.SUGGEST), signals - set(stage.SUGGEST)


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
    """v3.2 的步骤（无「环境基线」）与 v3.1 兼容：旧步骤名不报错，新步骤按预期分类。"""
    now = ts("2026-11-09T05:00:00Z")
    idle = [{"state": "WAITING_FOR_INPUT", "updated_at": "2026-11-09T04:00:00Z"}]   # 空闲 60 分钟
    cases = [
        ("项目管理", "环境基线", idle, "等人：空闲未推进"),      # v3.1 旧 workflow 中的任务仍要能分类
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
    """v3.2：「待开发」的前置取自 tasks.json 的 status；v3.1 的 Kandev 前置仍然有效。"""
    now = ts("2026-11-09T05:00:00Z")
    later = now + timedelta(minutes=15)

    def cat(statuses, kblockers=(), extra=(), step="待开发"):
        h = task(30, "开发", step, f"parent: mod:a @ task {uid(11)}")
        h["blocker_status"], h["blockers"] = statuses, list(kblockers)
        rows, first, st = evaluate([h, *extra], now, {}, uid(1))
        rows, second, st = evaluate([h, *extra], later, st, uid(1))      # 15 分钟后（去重：同一信号不重复）
        return rows[0]["category"], [(a["signal"], a["to_task"]) for a in first + second]

    assert cat(["merged", "dropped"]) == ("等上级：可放行", [("hold_ready", uid(11))])
    assert cat(["merged", "todo"]) == ("待开发", [])
    assert cat(["merged", None]) == ("待开发", [])                                   # blocked_by 在 tasks.json 里查不到
    assert cat(["merged", "failed"]) == ("等上级：前置失败", [("hold_broken", uid(11))])
    assert cat(["held"]) == ("待开发", [])
    assert cat(None) == ("待开发（tasks.json 中查不到前置）", [])                      # 读不到 tasks.json：只显示，不告警
    # v3.1：Kandev 里的前置
    k_done = task(40, "开发", "完成", "", state="COMPLETED")
    k_run = task(41, "开发", "开发", "")
    k_bad = task(42, "开发", "开发", "", state="FAILED")
    assert cat(None, [uid(40)], [k_done]) == ("等上级：可放行", [("hold_ready", uid(11))])
    assert cat(None, [uid(40), uid(41)], [k_done, k_run]) == ("待开发", [])
    assert cat(None, [uid(42)], [k_bad]) == ("等上级：前置失败", [("hold_broken", uid(11))])
    # 两种来源任一表明未完成就不放行
    assert cat(["merged"], [uid(41)], [k_run]) == ("待开发", [])
    assert cat(["todo"], [uid(40)], [k_done]) == ("待开发", [])
    # 「开发」步骤里前置未满足、没有会话：不再无声地排队，向模块 agent 告警一次
    c, al = cat(["todo"], step="开发")
    assert c == "等上级：开发步骤前置未满足" and al == [("dev_blocked", uid(11))], (c, al)
    c, al = cat(["merged"], step="开发")                                             # 前置满足：照常排队
    assert c == "排队" and al == [], (c, al)
    c, al = cat(None, step="开发")                                                   # 没有前置信息：照常排队
    assert c == "排队" and al == [], (c, al)


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
            "description": desc, "sessions": [], "blockers": []}


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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
