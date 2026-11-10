"""stage.py 的离线回归测试：python kandev/tests/test_stage.py（也由 check_docs.py 调用）。只用标准库。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from stage import evaluate, group_projects, parse_reset, should_disable, ts, usage_limit  # noqa: E402

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
    assert alerts == [("idle_no_signal", PM)], alerts

    cats, alerts, st = run(st, "2026-11-09T05:15:00+00:00")
    assert alerts == [("hold_ready", MOD)], alerts           # pm 的告警 60 分钟内不重复

    cats, alerts, st = run(st, "2026-11-09T06:05:00+00:00")
    assert ("pm_unresponsive", PM) in alerts, alerts         # pm 60 分钟后仍未推进
    assert ("running_stale", MOD) in alerts, alerts
    assert ("hold_ready", MOD) not in alerts, alerts         # 距上次告警 50 分钟，去重
    test_grouping()
    test_parse_reset()
    test_usage_limit()
    test_limit_resume()
    test_should_disable()
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
