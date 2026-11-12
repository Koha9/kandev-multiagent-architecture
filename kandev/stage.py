"""阶段分类：从 Kandev 的结构化状态确定性地判断每个任务"现在在等谁"，生成告警（守护用）。

一个 workspace 只需要一个守护：脚本自己发现所有进行中的项目，不需要按项目配置。
  - 项目 = 「多Agent · 项目管理」中未完成的任务（pm 任务）；mgmt_root 取自它描述中的 [TASK v1] 头
  - 模块任务按 [TASK v1] 头的 pm / parent 归到项目；开发任务按 parent（模块任务）归到项目
  - 管理目录已初始化（有 README.md）时，写 <mgmt_root>/agents/guard/stage.md；未初始化时不写，避免干扰立项规划

用法：
  python stage.py [--ids kandev_ids.json] [--json] [--disable-when-done]        # 所有进行中的项目
  python stage.py --mgmt-root <管理目录> [--json]                               # 只看一个项目
  python stage.py --snapshot snapshot.json --now 2026-11-09T05:00:00+00:00 [--json]   # 离线测试，不连 Kandev
去重状态存在 --state-dir（默认 kandev/guard_state/，不提交），按 pm 任务 id 分文件。
每次（非离线）运行都写心跳 <state-dir>/last_run.json（时间、项目、告警数），用来确认守护还在运行。

用量上限：最新会话停在 WAITING_FOR_INPUT / IDLE 时，读该会话最新的几条消息（只看类型和 metadata）；最新一条是
provider_error.error_kind=rate_limit 的 status 消息 → 判为"到达用量上限"。重置时间从消息文字（"resets 9pm (Asia/Tokyo)"）
解析，解析不了按出错后 60 分钟。恢复方式与用户手动恢复相同：向同一个会话发一条消息（守护用 message_task_kandev
带 session_id），不移动任务、不新建会话。进程退出类错误（metadata 带 session.recover 动作）不属于这一类，不自动恢复。

自动停用（--disable-when-done，只由守护 automation 传入）：上次心跳在 60 分钟内且当时有进行中的项目，这次一个都没有，
并且三套 workflow 中没有运行中或停在用量上限的会话 → 通过外部 MCP 把名为「多Agent 守护」的 automation 设为
enabled=false，并输出一行 signal=guard_disabled。启动新项目前需要重新启用。

规则表（从上到下，第一条匹配的生效；与 mgmt-template/roles/guard.md「阶段分类」一致）：
  1 完成      步骤=完成，或任务 state=COMPLETED
  2 等人      有待处理的权限请求                         → 只写进 stage.md，不发告警
  3 等人      有待处理的提问（ask_user_question）        → 同上
  4 等人      步骤=立项确认 / 人工终审                    → 同上
  4a 等上限   最新会话停在用量上限，已过重置时间 2 分钟   → 恢复该任务自己 limit_resume（不告警上级）
  4b 等上限   最新会话停在用量上限，还没到重置时间        → 只写进 stage.md
  5 等上级    步骤=等待决策，停留 ≥10 分钟                → 告警上级 decision_pending（先于 9，不会再判为空闲未推进）
  6 等上级    最新会话 FAILED / CANCELLED                 → 告警上级 session_failed
  7 等上级    步骤=待开发，前置失败                       → 告警上级 hold_broken
  8 等上级    步骤=待开发，前置全部完成，停留 ≥10 分钟    → 告警上级 hold_ready
              前置关系取自 <mgmt_root>/modules/*/tasks.json（含 -fix-<n> 修复模块）：任务的 blocked_by 中每个任务
              status 都是 merged / dropped → 完成；有 status=failed → 失败。v3.1 任务在 Kandev 里设置的 blocked_by
              仍然有效（FAILED / CANCELLED 为失败，未到「完成」为未完成）。两种来源任一表明未完成就不放行；
              读不到 tasks.json 或解析失败时，只剩 Kandev 来源；两者都没有 → 只在 stage.md 显示，不告警
  8a 等上级   步骤=开发，前置未满足、还没有会话，停留 ≥10 分钟 → 告警上级 dev_blocked（v3.2 不应出现，多见于 v3.1 任务）
  9 等上级    要求完成信号的步骤中会话已空闲 ≥10 分钟     → 告警上级 idle_no_signal
              例外：W1（项目管理）的这类步骤，会话属于 pm 以外的评审者 / 机械 agent，发给 pm 没人处理 →
              归为"等人：空闲未推进"，只写进 stage.md（步骤和空闲分钟数），不告警
 10 等上级    会话 RUNNING 但 ≥45 分钟没有更新            → 告警上级 running_stale
 11 排队      在设了 WIP 的步骤但未获准入，或在 agent 步骤还没有会话
 12 待开发    步骤=待开发（前置未完成）
 13 常驻      步骤=调度 / 等待开发
 14 运行中    其他
上级：开发任务 → [TASK v1] 头 parent 中的模块任务；模块任务 → pm；pm → pm 自己。limit_resume 发给任务自己。
同一任务的同一信号 60 分钟内只告警一次；pm 停在常驻步骤（调度）时，同一信号告警 60 分钟后仍未消除 → pm_unresponsive
（守护把 pm 移到「刷新」，instructions 写「刷新返回：<return_step>」）。pm 在其他步骤不升级，到期后重发原信号。
limit_resume 不升级为 pm_unresponsive：恢复后又碰到上限，就等新的重置时间，且距上次恢复 ≥60 分钟再试。
--json 时标准输出每行一个要发出的告警（带 project、mgmt_root、journal；pm_unresponsive 另带 workflow_id 和
refresh_step_id；pm_unresponsive 另带 return_step = 当前步骤名；limit_resume 另带 session_id 和 message）；否则打印给人看的摘要。没有进行中的项目且没有停用守护时
什么都不输出。只用标准库。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GATES = {"立项确认", "人工终审"}
RESIDENT = {"调度", "等待开发"}
HOLD, DECISION, DONE = "待开发", "等待决策", "完成"
# v3.2 删除了 W1 的「环境基线」；仍在 v3.1 旧 workflow 里运行的项目可能有任务停在这一步，按要求完成信号的步骤处理。
# 步骤名只用于分类，不认识的步骤名落到"运行中"，不会报错。
LEGACY_SIGNAL_STEPS = {"环境基线"}
SIGNAL_STEPS = {"立项规划", "立项评审", "模块下发", "项目验收", "收尾合并",
                "模块规划", "验收调查", "开发", "审核", "合并"} | LEGACY_SIGNAL_STEPS
AGENT_STEPS = SIGNAL_STEPS | RESIDENT | {"刷新"}
IDLE_STATES = {"WAITING_FOR_INPUT", "IDLE", "COMPLETED"}
LIMIT_STATES = {"WAITING_FOR_INPUT", "IDLE"}          # 用量上限停下后会话的状态（实测为 WAITING_FOR_INPUT）
ACTIVE_STATES = {"RUNNING", "STARTING"}
T_IDLE, T_DECISION, T_HOLD, T_STALE, T_DEDUP = 10, 10, 10, 45, 60
T_LIMIT_FALLBACK, T_LIMIT_MARGIN, T_BEAT = 60, 2, 60
PREREQ_DONE = {"merged", "dropped"}      # tasks.json 中算"前置已完成"的 status
GUARD_NAME = "多Agent 守护"
RESUME_TEXT = ("continue\n\n（守护 guard：本会话上一轮因到达用量上限而中断，上限已于 {reset} 重置。请从中断处继续当前步骤："
               "先核对 NOW / now、磁盘与 git 的实际状态，已经完成的操作不要重复。）")
UUID = r"[0-9a-fA-F-]{36}"


# ------------------------------------------------------------------ parsing helpers
def ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    if "." in s:
        head, tail = s.split(".", 1)
        tz = tail[tail.index("+"):] if "+" in tail else "+00:00"
        frac = "".join(c for c in tail.split("+")[0] if c.isdigit())[:6]
        s = f"{head}.{frac}{tz}"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def header_field(desc, name):
    m = re.search(rf"^{name}:\s*(.+)$", desc or "", re.M)
    return m.group(1).strip() if m else ""


def header_task(desc, name):
    m = re.search(rf"task\s+({UUID})", header_field(desc, name))
    return m.group(1) if m else None


def prereq_state(t, by_id):
    """任务前置的状态：(是否有前置信息, 是否有失败的前置, 前置是否全部完成)。
    两个来源：t["blocker_status"]（tasks.json 中 blocked_by 各任务的 status，None 表示读不到）、
    t["blockers"]（v3.1：Kandev 中的前置任务 id，用它们的 step / state 判断）。"""
    statuses, kblockers = t.get("blocker_status") or [], t.get("blockers") or []
    known = bool(statuses or kblockers)
    kb = [by_id.get(b) for b in kblockers]
    failed = "failed" in statuses or any(b and b["state"] in ("FAILED", "CANCELLED") for b in kb)
    done = (all(s in PREREQ_DONE for s in statuses)
            and all(b and (b["step"] == DONE or b["state"] == "COMPLETED") for b in kb))
    return known, failed, done and known


def mins(a, b):
    return int((b - a).total_seconds() // 60) if a and b else -1


MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
RESET = re.compile(r"resets\s+(?:(?P<mon>[A-Z][a-z]{2})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s+(?:at\s+)?)?"
                   r"(?P<h>\d{1,2})(?::(?P<mi>\d{2}))?\s*(?P<ap>am|pm)\s*\((?P<tz>[^)]+)\)", re.I)


def parse_reset(text, at):
    """'You've hit your 5-hour limit · resets 11:50pm (Asia/Tokyo)' → 重置时刻（UTC，aware）。
    没写日期时取 at 之后第一次出现的那个时刻。解析不了返回 None。"""
    m = RESET.search(text or "")
    if not m or not at:
        return None
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(m.group("tz").strip())
    except Exception:  # noqa: BLE001  zoneinfo 缺失或时区名不认识
        return None
    h = int(m.group("h")) % 12 + (12 if m.group("ap").lower() == "pm" else 0)
    mi = int(m.group("mi") or 0)
    local = at.astimezone(tz)
    if m.group("mon") and m.group("mon").title() in MONTHS:
        cand = local.replace(month=MONTHS[m.group("mon").title()], day=int(m.group("day")), hour=h, minute=mi,
                             second=0, microsecond=0)
        if cand < local - timedelta(days=1):
            cand = cand.replace(year=cand.year + 1)
    else:
        cand = local.replace(hour=h, minute=mi, second=0, microsecond=0)
        if cand <= local:
            cand += timedelta(days=1)
    return cand.astimezone(timezone.utc)


def usage_limit(messages, session_id):
    """messages：会话消息，新的在前。最新一条 message/status 是用量上限的 status → dict，否则 None。只看类型和 metadata。"""
    for msg in messages:
        if msg.get("type") not in ("message", "status"):
            continue
        meta = msg.get("metadata") or {}
        pe = meta.get("provider_error") or {}
        if msg.get("type") != "status" or not (pe.get("error_kind") == "rate_limit" or meta.get("failure_code") == "quota_limited"):
            return None
        at = ts(msg.get("created_at"))
        text = pe.get("message") or msg.get("content") or ""
        reset = parse_reset(text, at)
        return {"session_id": msg.get("session_id") or session_id, "at": at.isoformat() if at else None,
                "message": text, "resets_at": reset.isoformat() if reset else None}
    return None


def limit_reset(lim):
    reset = ts(lim.get("resets_at"))
    if reset:
        return reset
    at = ts(lim.get("at"))
    return at + timedelta(minutes=T_LIMIT_FALLBACK) if at else None


# ------------------------------------------------------------------ classification (pure)
def classify(t, now, by_id):
    """t: dict(id, title, workflow, step, state, sessions[{state, updated_at}], perm, question, wip_admitted,
    wip_step, blockers[kandev ids], since). Returns dict(category, signal, value, threshold) — signal None = no alert."""
    step, s0 = t["step"], (t["sessions"][0] if t["sessions"] else None)
    in_step = mins(t.get("since"), now)
    idle = mins(ts(s0.get("updated_at")), now) if s0 else -1

    def r(category, signal=None, value=None, threshold=None):
        return {"category": category, "signal": signal, "value": value, "threshold": threshold}

    if step == DONE or t["state"] == "COMPLETED":
        return r("完成")
    if t.get("perm"):
        return r("等人：权限请求", value=t["perm"])
    if t.get("question"):
        return r("等人：提问")
    if step in GATES:
        return r(f"等人：{step}", value=in_step)
    if t.get("limit"):
        reset = limit_reset(t["limit"])
        shown = reset.astimezone().strftime("%m-%d %H:%M") if reset else "?"
        if reset is None or now >= reset + timedelta(minutes=T_LIMIT_MARGIN):
            return r("等上限：已重置，待恢复", "limit_resume", shown, "-")
        return r("等上限：等待重置", value=shown)
    if step == DECISION:
        return r("等上级：等待决策", "decision_pending" if in_step >= T_DECISION else None, in_step, T_DECISION)
    if s0 and s0.get("state") in ("FAILED", "CANCELLED"):
        return r("等上级：会话失败", "session_failed", s0["state"], "-")
    known, pre_failed, pre_done = prereq_state(t, by_id)
    if step == HOLD:
        if not known:
            return r("待开发（tasks.json 中查不到前置）")
        if pre_failed:
            return r("等上级：前置失败", "hold_broken", "前置 failed / FAILED / CANCELLED", "-")
        if pre_done:
            return r("等上级：可放行", "hold_ready" if in_step >= T_HOLD else None, in_step, T_HOLD)
        return r("待开发")
    if step in SIGNAL_STEPS and s0 and s0.get("state") in IDLE_STATES and idle >= T_IDLE:
        if t["workflow"].endswith("项目管理"):   # 会话是评审者 / 机械 agent / 等 pm 的，告警 pm 没人处理：只给人看
            return r("等人：空闲未推进", value=f"{step}，空闲 {idle} 分钟")
        return r("等上级：空闲未推进", "idle_no_signal", idle, T_IDLE)
    if s0 and s0.get("state") == "RUNNING" and idle >= T_STALE:
        return r("等上级：疑似卡住", "running_stale", idle, T_STALE)
    if step == "开发" and not s0 and known and not pre_done and t["workflow"].endswith("开发"):
        return r("等上级：开发步骤前置未满足", "dev_blocked" if in_step >= T_IDLE else None, in_step, T_IDLE)
    if (t.get("wip_step") and t.get("wip_admitted") is False) or (step in AGENT_STEPS and not s0):
        return r("排队", value=in_step)
    if step in RESIDENT:
        return r("常驻", value=idle)
    return r("运行中", value=idle)


def route(t, pm_task):
    if t["workflow"].endswith("开发"):
        return header_task(t["description"], "parent")
    if t["workflow"].endswith("模块管理"):
        return header_task(t["description"], "pm") or header_task(t["description"], "parent") or pm_task
    return t["id"]


SUGGEST = {"dev_blocked": "unblock", "decision_pending": "unblock", "session_failed": "unblock", "hold_broken": "split",
           "hold_ready": "unblock", "idle_no_signal": "unblock", "running_stale": "refresh", "limit_resume": "continue"}
SELF_SIGNALS = {"limit_resume"}   # 发给任务自己、不升级的信号


def evaluate(tasks, now, state, pm_task):
    """Returns (rows, alerts, new_state)."""
    by_id = {t["id"]: t for t in tasks}
    rows, alerts, new_state = [], [], {}
    for t in tasks:
        prev = state.get(t["id"], {})
        since = prev.get("since") if prev.get("step") == t["step"] else None
        since = ts(since) if since else now
        t["since"] = since
        c = classify(t, now, by_id)
        sent = {k: v for k, v in prev.get("alerts", {}).items() if prev.get("step") == t["step"]}
        if c["signal"]:
            last = ts(sent.get(c["signal"]))
            own = c["signal"] in SELF_SIGNALS
            to_task = t["id"] if own else route(t, pm_task)
            is_pm = to_task == t["id"] and not own
            if last is None or now - last >= timedelta(minutes=T_DEDUP):
                signal = "pm_unresponsive" if (is_pm and last is not None and t["step"] in RESIDENT) else c["signal"]
                al = {"to_task": to_task, "object": f"{t['title']} @ task {t['id']}", "step": t["step"],
                      "signal": signal, "value": c["value"], "threshold": c["threshold"],
                      "suggest": "refresh" if signal == "pm_unresponsive" else SUGGEST[c["signal"]]}
                if signal == "pm_unresponsive":
                    al["return_step"] = t["step"]
                if own:
                    al.update({"session_id": t["limit"].get("session_id"), "message": RESUME_TEXT.format(reset=c["value"])})
                alerts.append(al)
                sent[c["signal"]] = now.isoformat()
        else:
            sent = {}
        new_state[t["id"]] = {"step": t["step"], "since": since.isoformat(), "alerts": sent}
        rows.append({**c, "id": t["id"], "title": t["title"], "workflow": t["workflow"], "step": t["step"]})
    return rows, alerts, new_state


# ------------------------------------------------------------------ data collection
def load_blockers(mgmt_root):
    """kandev task id -> [blocked_by 各任务的 status]，取自 modules/*/tasks.json（含 -fix-<n> 修复模块）。
    blocked_by 中查不到的任务记为 None（视为未完成）。文件不存在或解析失败的模块跳过，不报错。"""
    out = {}
    mods = os.path.join(mgmt_root, "modules")
    if not os.path.isdir(mods):
        return out
    for m in os.listdir(mods):
        p = os.path.join(mods, m, "tasks.json")
        if m.startswith("_") or not os.path.exists(p):
            continue
        try:
            tasks = json.load(open(p, encoding="utf-8")).get("tasks", [])
        except (OSError, json.JSONDecodeError):
            continue
        try:
            status = {t["id"]: t.get("status") for t in tasks}
            for t in tasks:
                if t.get("kandev_task_id"):
                    out[t["kandev_task_id"]] = [status.get(b) for b in t.get("blocked_by") or []]
        except (TypeError, KeyError, AttributeError):
            continue
    return out


def kandev_blockers(t):
    """v3.1：任务在 Kandev 里设置的 blocked_by（list_tasks 返回的字段，形状不确定：id 字符串或带 id 的对象）。"""
    out = []
    for b in t.get("blocked_by") or []:
        bid = b if isinstance(b, str) else (b.get("blocked_by_task_id") or b.get("task_id") or b.get("id")) if isinstance(b, dict) else None
        if bid:
            out.append(bid)
    return out


def kandev():
    from build_workflows import Kandev  # noqa: E402
    return Kandev()


def detect_limit(k, task_id, s0):
    """最新会话停在用量上限 → dict（见 usage_limit），否则 None。只读最新几条消息的类型和 metadata。"""
    if not s0 or s0.get("state") not in LIMIT_STATES or not s0.get("session_id"):
        return None
    try:
        conv = k.call("get_task_conversation_kandev", {"task_id": task_id, "session_id": s0["session_id"],
                                                       "sort": "desc", "limit": 5})
    except RuntimeError:
        return None
    return usage_limit(conv.get("messages", []) if isinstance(conv, dict) else [], s0["session_id"])


def collect(ids):
    k = kandev()
    try:
        pq = k.call("list_pending_questions_kandev", {})
        bundles = pq.get("bundles", pq.get("pending", [])) if isinstance(pq, dict) else []
        pq_tasks = {b.get("task_id") for b in bundles if isinstance(b, dict)}
    except RuntimeError:
        pq_tasks = set()
    tasks = []
    for wname, info in ((n, i) for n, i in ids.items() if not n.startswith("_")):
        names = {v: n for n, v in info["steps"].items()}
        wip_steps = {"开发"} if wname.endswith("开发") else set()
        for t in k.call("list_tasks_kandev", {"workflow_id": info["workflow_id"]}).get("tasks", []):
            step = names.get(t["workflow_step_id"], "?")
            item = {"id": t["id"], "title": t["title"], "workflow": wname, "step": step, "state": t["state"],
                    "description": t.get("description", ""), "wip_admitted": t.get("wip_admitted"),
                    "wip_step": step in wip_steps, "blockers": kandev_blockers(t),
                    "question": t["id"] in pq_tasks, "sessions": [], "perm": 0}
            if step != DONE and t["state"] != "COMPLETED":
                item["sessions"] = k.call("list_task_sessions_kandev", {"task_id": t["id"]}).get("sessions", [])
                try:
                    perms = k.call("list_pending_agent_permissions_kandev", {"task_id": t["id"]})
                    item["perm"] = len(perms.get("requests", perms.get("permissions", []))) if isinstance(perms, dict) else 0
                except RuntimeError:
                    item["perm"] = 0
                item["limit"] = detect_limit(k, t["id"], item["sessions"][0] if item["sessions"] else None)
            tasks.append(item)
    return tasks


def is_done(t):
    return t["step"] == DONE or t["state"] == "COMPLETED"


def busy_tasks(tasks):
    """未完成、且最新会话还在运行或停在用量上限的任务（三套 workflow 全部，不限于进行中的项目）。"""
    out = []
    for t in tasks:
        s0 = t["sessions"][0] if t.get("sessions") else None
        if not is_done(t) and (t.get("limit") or (s0 and s0.get("state") in ACTIVE_STATES)):
            out.append(t)
    return out


def should_disable(prev_beat, projects, tasks, now):
    """守护自动停用的条件。返回 (是否停用, 原因)。"""
    if projects:
        return False, "还有进行中的项目"
    at = ts(prev_beat.get("at")) if prev_beat else None
    if not at or now - at > timedelta(minutes=T_BEAT) or not prev_beat.get("projects"):
        return False, "上次心跳不在 60 分钟内，或当时也没有进行中的项目（可能是新项目还没建 pm 任务）"
    busy = busy_tasks(tasks)
    if busy:
        return False, "仍有运行中或停在用量上限的会话：" + "、".join(t["title"] for t in busy[:5])
    return True, "上次巡检的项目都已结束：" + "、".join(prev_beat["projects"])


def disable_guard(workspace_id):
    """把本 workspace 中名为 GUARD_NAME 的 automation 设为 enabled=false。返回 automation id 列表。"""
    k = kandev()
    res = k.call("list_settings_resources_kandev", {"resource_type": "automation", "workspace_id": workspace_id,
                                                    "limit": 50})
    targets = [r["target"] for r in res.get("resources", []) if r.get("label") == GUARD_NAME]
    if not targets:
        raise RuntimeError(f"workspace {workspace_id} 中找不到名为「{GUARD_NAME}」的 automation")
    for target in targets:
        k.call("update_settings_kandev", {"target": target, "changes": {"enabled": False}})
    return [x["resource_id"] for x in targets]


def norm(path):
    return os.path.normcase(os.path.normpath(path)) if path else ""


def group_projects(tasks):
    """Split tasks into projects. Returns [{pm_task, title, mgmt_root, tasks}] for pm tasks that are not finished.
    Tasks that cannot be attributed to a live project (finished projects, stray tasks) are dropped."""
    pms = {t["id"]: t for t in tasks if t["workflow"].endswith("项目管理") and not is_done(t)}
    project_of = {pid: pid for pid in pms}
    for t in tasks:
        if t["workflow"].endswith("模块管理"):
            pid = header_task(t["description"], "pm") or header_task(t["description"], "parent")
            if pid in pms:
                project_of[t["id"]] = pid
    for t in tasks:
        if t["workflow"].endswith("开发"):
            pid = project_of.get(header_task(t["description"], "parent"))
            if pid:
                project_of[t["id"]] = pid
    out = []
    for pid, pm in pms.items():
        out.append({"pm_task": pid, "title": pm["title"], "mgmt_root": header_field(pm["description"], "mgmt_root"),
                    "tasks": [t for t in tasks if project_of.get(t["id"]) == pid]})
    return out


def initialized(mgmt_root):
    return bool(mgmt_root) and os.path.exists(os.path.join(mgmt_root, "README.md"))


# ------------------------------------------------------------------ output
ORDER = ["等人", "等上限", "等上级", "排队", "待开发", "常驻", "运行中", "完成"]


def render(rows, alerts, now_local):
    groups = {g: [r for r in rows if r["category"].startswith(g)] for g in ORDER}
    out = ["# 现在在等谁", "", f"> 由 kandev/stage.py 生成，不要手改。更新：{now_local}", ""]
    if not groups["等人"] and not groups["等上级"] and not groups["等上限"]:
        out += ["没有需要处理的事项。", ""]
    for g, title in (("等人", "需要用户处理"), ("等上限", "停在用量上限（守护在重置后自动恢复）"),
                     ("等上级", "需要上级 agent 处理")):
        if groups[g]:
            out += [f"## {title}", "", "| 任务 | 步骤 | 状态 | 数值 |", "|---|---|---|---|"]
            out += [f"| {r['title']} | {r['step']} | {r['category']} | {r['value'] if r['value'] is not None else ''} |"
                    for r in groups[g]]
            out.append("")
    counts = " · ".join(f"{g} {len(groups[g])}" for g in ORDER[3:] if groups[g])
    out += ["## 其他", "", counts or "无", ""]
    if alerts:
        out += ["## 本次告警", ""] + [f"- {a['signal']} → task {a['to_task']}：{a['object']}" for a in alerts] + [""]
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ids", default=os.path.join(HERE, "kandev_ids.json"))
    p.add_argument("--mgmt-root", help="只看这个管理目录对应的项目（默认所有进行中的项目）")
    p.add_argument("--state-dir", default=os.path.join(HERE, "guard_state"), help="去重状态目录")
    p.add_argument("--snapshot", help="离线测试：从 JSON 读取任务列表，不连 Kandev")
    p.add_argument("--now", help="离线测试：当前时间（ISO 8601）")
    p.add_argument("--json", action="store_true", help="标准输出每行一个告警 JSON")
    p.add_argument("--disable-when-done", action="store_true",
                   help=f"所有项目正常结束后把「{GUARD_NAME}」automation 设为停用（只由守护 automation 传入）")
    a = p.parse_args()

    now = ts(a.now) if a.now else datetime.now(timezone.utc)
    ids = json.load(open(a.ids, encoding="utf-8")) if os.path.exists(a.ids) else {}
    w1 = ids.get("多Agent · 项目管理", {})
    if a.snapshot:
        tasks = json.load(open(a.snapshot, encoding="utf-8"))["tasks"]
        for t in tasks:
            t.setdefault("description", ""), t.setdefault("sessions", []), t.setdefault("blockers", [])
    else:
        tasks = collect(ids)

    projects = group_projects(tasks)
    if a.mgmt_root:
        projects = [pr for pr in projects if norm(pr["mgmt_root"]) == norm(a.mgmt_root)]
    os.makedirs(a.state_dir, exist_ok=True)
    texts, n_alerts = [], 0
    for pr in projects:
        root, ready = pr["mgmt_root"], initialized(pr["mgmt_root"])
        if ready and not a.snapshot:
            blockers = load_blockers(root)
            for t in pr["tasks"]:
                t["blocker_status"] = blockers.get(t["id"])
        state_path = os.path.join(a.state_dir, f"{pr['pm_task']}.json")
        state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
        rows, alerts, new_state = evaluate(pr["tasks"], now, state, pr["pm_task"])
        n_alerts += len(alerts)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=1)
        text = render(rows, alerts, now.astimezone().strftime("%Y-%m-%d %H:%M"))
        if ready:
            out = os.path.join(root, "agents", "guard", "stage.md")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
        journal = (os.path.join(root, "agents", "guard", "journal.md") if ready
                   else os.path.join(a.state_dir, "journal.md"))
        for al in alerts:
            al.update({"project": pr["title"], "mgmt_root": root, "journal": journal})
            if al["signal"] == "pm_unresponsive":
                al.update({"workflow_id": w1.get("workflow_id"), "refresh_step_id": w1.get("steps", {}).get("刷新")})
            if a.json:
                print(json.dumps(al, ensure_ascii=False))
        texts.append(f"===== {pr['title']} · {root or '（未写 mgmt_root）'}\n{text}")
    beat_path = os.path.join(a.state_dir, "last_run.json")
    disabled = None
    if a.disable_when_done and not a.snapshot and not a.mgmt_root:
        prev = json.load(open(beat_path, encoding="utf-8")) if os.path.exists(beat_path) else {}
        ok, reason = should_disable(prev, projects, tasks, now)
        if ok:
            ws = ids.get("_meta", {}).get("workspace_id")
            disabled = {"to_task": None, "signal": "guard_disabled", "value": reason, "threshold": "-",
                        "suggest": "none", "project": "", "mgmt_root": "",
                        "journal": os.path.join(a.state_dir, "journal.md"),
                        "automation_ids": disable_guard(ws)}
            n_alerts += 1
            if a.json:
                print(json.dumps(disabled, ensure_ascii=False))
            texts.append(f"已停用守护 automation：{reason}")
    if not a.snapshot:   # 心跳：守护是否还在运行，看这个文件的 at 即可
        beat = {"at": now.isoformat(), "projects": [pr["title"] for pr in projects], "alerts": n_alerts,
                "disabled": bool(disabled)}
        with open(beat_path, "w", encoding="utf-8") as f:
            json.dump(beat, f, ensure_ascii=False, indent=1)
    if not a.json:
        print("\n".join(texts) if texts else "没有进行中的项目。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
