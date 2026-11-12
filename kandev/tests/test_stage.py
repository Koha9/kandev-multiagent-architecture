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
    print("OK test_stage")


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
    rows, _, _ = evaluate(tasks, now, {}, uid(1))
    for (wf, step, _, want), r in zip(cases, rows):
        assert r["category"].startswith(want), (wf, step, r["category"], want)


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
