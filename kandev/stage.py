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
  0 等上级    开发任务在「完成」/ COMPLETED，但它在 tasks.json 中的 status 不是 merged / dropped / failed，停留 ≥10 分钟，
              且模块任务在「等待开发 / 刷新 / 模块规划」→ 告警上级 child_unrecorded（合并的 REPORT 没有送达时的兜底）。
              tasks.json 中查不到该任务时不告警；模块任务在其他步骤或已完成时只在 stage.md 显示"完成（tasks.json 未登记）"。
              since 是守护第一次看到它在这一步的时间，所以实际要连续两次巡检（20–40 分钟）都看到才告警，
              覆盖了合并 → 模块 agent 处理 REPORT 之间的正常间隔
  1 完成      步骤=完成，或任务 state=COMPLETED
  2 等人      有待处理的权限请求                         → 只写进 stage.md，不发告警
  3 等人      有待处理的提问（ask_user_question）        → 同上
  4 等人      步骤=立项确认 / 人工终审                    → 同上
              W1「接收」（v3.3）中的任务还没有 [TASK v1] 头（mgmt_root 为空）：按项目列出，不写 stage.md；
              在等用户回答时归第 3 条，空闲未推进时归第 9 条的例外（只给人看）；会话失败或疑似卡住也只给人看
              （这一步没有上级，接收会话也不认识 KMSG），归为"等人：接收会话失败 / 接收疑似卡住"
  4a 等上限   最新会话停在用量上限，已过重置时间 2 分钟   → 恢复该任务自己 limit_resume（不告警上级）
  4b 等上限   最新会话停在用量上限，还没到重置时间        → 只写进 stage.md
  4c 等上级   有一个不是最新的会话 RUNNING 但 ≥45 分钟没有更新（那一轮不会结束，发给它的消息一直排队）；
              模块任务完成后也检查它的全部会话                → 告警 pm session_stuck（v3.3.3；不升级为 pm_unresponsive）
  4d 等上级   开发任务未结束而它的模块任务已完成，停留 ≥10 分钟 → 告警 pm parent_done（v3.3.3）
  5 等上级    步骤=等待决策，停留 ≥10 分钟                → 告警上级 decision_pending（先于 9，不会再判为空闲未推进）
  6 等上级    最新会话 FAILED / CANCELLED                 → 告警上级 session_failed
  6a 等上级   任务 state=SCHEDULING、在 agent 步骤、没有运行中的会话、不是 WIP 排队，停留 ≥10 分钟
              → 开发任务告警上级 session_not_started（Kandev 准备会话失败后会静默停在这里）；W1 / W2 任务只写进 stage.md
              （"等人：会话未启动"）。排在第 9 条之前：否则上一步骤留下的空闲会话会被误判为 idle_no_signal
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
 13a 常驻     步骤=调度 / 等待开发，常驻会话自上次上下文重置以来已被唤醒 ≥15 次
              → 告警任务自己 session_long（带 session_id，建议 refresh；v3.3.3）。唤醒 = 该会话里用户侧的 message
              （步骤 prompt、KMSG、用户输入）；重置标记 = 内容以 "Context reset" 开头的 status。只读消息的类型、作者和这个标记
 13 常驻      步骤=调度 / 等待开发
 14 运行中    其他
上级：开发任务 → [TASK v1] 头 parent 中的模块任务；模块任务 → pm；pm → pm 自己。limit_resume、session_long 发给任务自己；
session_stuck、parent_done 一律发给 pm。发给模块任务的告警带 session_id（modules/*/tasks.json 顶层的 module_session_id）。
连不上 Kandev 时退出码 1：last_run.json 记连续失败次数，上次巡检过的各项目 stage.md 标题下加一行"守护故障"（note_failure）。
v3.3.2 新增的信号（child_unrecorded、session_not_started）的 suggest 是完整的处理方法，旧版 prompt 的 agent 收到也能照做。
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
HOLD, DECISION, DONE, INTAKE = "待开发", "等待决策", "完成", "接收"
# v3.2 删除了 W1 的「环境基线」；仍在 v3.1 旧 workflow 里运行的项目可能有任务停在这一步，按要求完成信号的步骤处理。
# 步骤名只用于分类，不认识的步骤名落到"运行中"，不会报错。
LEGACY_SIGNAL_STEPS = {"环境基线"}
SIGNAL_STEPS = {"接收", "立项规划", "立项评审", "模块下发", "项目验收", "收尾合并",
                "模块规划", "验收调查", "开发", "审核", "合并"} | LEGACY_SIGNAL_STEPS
AGENT_STEPS = SIGNAL_STEPS | RESIDENT | {"刷新"}
IDLE_STATES = {"WAITING_FOR_INPUT", "IDLE", "COMPLETED"}
LIMIT_STATES = {"WAITING_FOR_INPUT", "IDLE"}          # 用量上限停下后会话的状态（实测为 WAITING_FOR_INPUT）
ACTIVE_STATES = {"RUNNING", "STARTING"}
T_IDLE, T_DECISION, T_HOLD, T_STALE, T_DEDUP = 10, 10, 10, 45, 60
T_LIMIT_FALLBACK, T_LIMIT_MARGIN, T_BEAT = 60, 2, 60
T_WAKES = 15                              # 常驻会话自上次重置被唤醒这么多次 → session_long（与 build_workflows.REFRESH_WAKES 相同）
WAKE_PAGE, WAKE_PAGES = 100, 5            # 数唤醒次数时每页条数、最多翻几页（实测 Kandev 每页只返回约 40 条，15 次唤醒约 1–2 页）
FAIL_MARK = "> **守护故障**"              # note_failure 写进 stage.md 的那一行的开头
RESET_MARK = "Context reset"             # Kandev 重置上下文时写入会话的 status 消息的开头（实测："Context reset — new conversation started"）
PREREQ_DONE = {"merged", "dropped"}      # tasks.json 中算"前置已完成"的 status
RECORDED = PREREQ_DONE | {"failed"}      # 开发任务进入「完成」后 tasks.json 应有的 status
MOD_LIVE = {"等待开发", "刷新", "模块规划"}   # 模块 agent 能处理 child_unrecorded 的步骤（验收调查会自己退回）
SCHEDULING_STATES = {"SCHEDULING"}       # Kandev 为步骤准备会话时的任务状态（v3.3.1 事故中观察到；未在其他场景验证）
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
    m = re.search(rf"^{name}:[ \t]*(.+)$", desc or "", re.M)   # 值为空时不跨行取下一行
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


LIMIT_TEXT = re.compile(r"hit your .{0,40}limit", re.I)


def usage_limit(messages, session_id):
    """messages：会话消息，新的在前。最新一条 message/status 是用量上限的 status → dict，否则 None。只看类型和 metadata
    （唯一的例外：内容就是上限提示的 agent 消息会被跳过）。"""
    for msg in messages:
        if msg.get("type") not in ("message", "status"):
            continue
        if (msg.get("type") == "message" and msg.get("author_type") != "user"
                and LIMIT_TEXT.search(msg.get("content") or "")):
            continue    # 上限文字有时还会以普通 agent 消息再出现一次，排在那条 status 之后：跳过它继续往前找（v3.3.3）
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


def wakes_since_reset(messages):
    """messages：会话消息，新的在前。返回 (最近一次上下文重置之后的唤醒次数, 是否看到了重置标记)。
    唤醒 = 用户侧的 message（步骤 prompt、KMSG、用户输入）。只看类型、作者和重置标记，不读正文。"""
    n = 0
    for msg in messages:
        if msg.get("type") == "status" and (msg.get("content") or "").startswith(RESET_MARK):
            return n, True
        if msg.get("type") == "message" and msg.get("author_type") == "user":
            n += 1
    return n, False


def limit_reset(lim):
    reset = ts(lim.get("resets_at"))
    if reset:
        return reset
    at = ts(lim.get("at"))
    return at + timedelta(minutes=T_LIMIT_FALLBACK) if at else None


def stuck_session(sessions, now, skip):
    """sessions[skip:] 中有 RUNNING 但 ≥45 分钟没有更新的会话 → "<会话 id 前 8 位>，<分钟> 分钟"，否则 None。
    这样的会话那一轮不会结束，发给它的消息会一直排队（v3.3.1 出现过，停了 9 小时）。"""
    for s in sessions[skip:]:
        idle = mins(ts(s.get("updated_at")), now)
        if s.get("state") == "RUNNING" and idle >= T_STALE:
            return f"{(s.get('session_id') or '?')[:8]}，{idle} 分钟"
    return None


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
        stuck = stuck_session(t["sessions"], now, 0)     # 只有模块任务完成后还会带着会话列表（见 collect）
        if stuck:
            return r("等上级：已完成但会话卡住", "session_stuck", stuck, T_STALE)
        own = t.get("own_status")         # None = tasks.json 中查不到这个任务（或读不到 tasks.json）：不告警
        if t["workflow"].endswith("开发") and own is not None and own not in RECORDED:
            parent = by_id.get(header_task(t.get("description"), "parent"))
            if parent and not is_done(parent) and parent["step"] in MOD_LIVE:
                return r("等上级：完成未登记", "child_unrecorded" if in_step >= T_IDLE else None, own or "(空)", T_IDLE)
            return r("完成（tasks.json 未登记）", value=own or "(空)")
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
    stuck = stuck_session(t["sessions"], now, 1)         # 最新会话卡住归第 10 条；这里查更早的会话
    if stuck:
        return r("等上级：旧会话卡住", "session_stuck", stuck, T_STALE)
    if t["workflow"].endswith("开发"):
        parent = by_id.get(header_task(t.get("description"), "parent"))
        if parent and is_done(parent):
            return r("等上级：模块已完成", "parent_done" if in_step >= T_IDLE else None, parent["title"], T_IDLE)
    if step == INTAKE and s0 and s0.get("state") in ("FAILED", "CANCELLED"):
        return r("等人：接收会话失败", value=s0["state"])
    if step == INTAKE and s0 and s0.get("state") == "RUNNING" and idle >= T_STALE:
        return r("等人：接收疑似卡住", value=idle)
    if step == DECISION:
        return r("等上级：等待决策", "decision_pending" if in_step >= T_DECISION else None, in_step, T_DECISION)
    if s0 and s0.get("state") in ("FAILED", "CANCELLED"):
        return r("等上级：会话失败", "session_failed", s0["state"], "-")
    if (t["state"] in SCHEDULING_STATES and step in AGENT_STEPS and not (s0 and s0.get("state") in ACTIVE_STATES)
            and not (t.get("wip_step") and t.get("wip_admitted") is False)):
        if not t["workflow"].endswith("开发"):     # W1 / W2 没有「等待决策」可用来重启会话：只给人看
            return r("等人：会话未启动", value=f"{step}，{in_step} 分钟")
        return r("等上级：会话未启动", "session_not_started" if in_step >= T_IDLE else None, step, T_IDLE)
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
        wakes = (t.get("long") or {}).get("wakes", 0)
        if wakes >= T_WAKES:
            return r("常驻：会话过长", "session_long", wakes, T_WAKES)
        return r("常驻", value=idle)
    return r("运行中", value=idle)


def route(t, pm_task):
    if t["workflow"].endswith("开发"):
        return header_task(t["description"], "parent")
    if t["workflow"].endswith("模块管理"):
        return header_task(t["description"], "pm") or header_task(t["description"], "parent") or pm_task
    return t["id"]


SUGGEST = {"dev_blocked": "unblock", "decision_pending": "unblock", "session_failed": "unblock", "hold_broken": "split",
           "hold_ready": "unblock", "idle_no_signal": "unblock", "running_stale": "refresh", "limit_resume": "continue",
           # v3.3.2 新增的信号：建议写成完整的处理方法，旧版 prompt 的模块 agent 收到也能照做
           "child_unrecorded": ("该开发任务已在「完成」，但 tasks.json 没有登记（合并的 REPORT 可能没有送达）："
                                "`git log mod/<模块> --oneline --grep \"^<任务id>\"` 有提交 → tasks.json 记 merged，"
                                "再检查 held 任务能否放行；没有提交 → 查 NOW「未确认的意图」，仍不清楚就 ESCALATE 给 pm，不要猜 merged"),
           "session_not_started": ("该任务进入当前步骤后一直没有启动会话（Kandev 停在 SCHEDULING）：先 move_task_kandev 到"
                                   "「等待决策」再移回当前步骤一次；再次收到本告警 → 新建任务取代它（workspace_mode=new_workspace、"
                                   "autopilot=true、base_branch=mod/<模块>），原任务移到「完成」并在 tasks.json 标 failed"),
           # v3.3.3：同样写成完整的处理方法
           "session_long": ("refresh：本会话自上次上下文重置以来被唤醒的次数已到上限（见数值）。处理完手头的事件后，把未落盘的状态写入 NOW.md，"
                            "在 NOW「注意」节写一行 `刷新返回：<当前步骤名>`，再 move_task_kandev 把本任务移到本 workflow 的「刷新」"),
           "session_stuck": ("该任务有一个会话一直 RUNNING 但很久没有输出（数值是会话 id 前 8 位和分钟数），那一轮不会自己结束，"
                             "发给这个会话的消息会一直排队。agent 取消不了它：在 attention.md 登记一条，请用户在 Kandev 界面打开该任务的"
                             "这个会话并取消当前这一轮；在此之前不要再给这个会话发消息，要它做的事等取消后重发"),
           "parent_done": ("该开发任务还没结束，但它的模块任务已经完成（数值是模块任务标题），没有模块 agent 会处理它的 REPORT、提问和放行，"
                           "也不能给已完成的模块发指令。它如果是多余的 → 请用户取消；它的工作还需要 → 为这个模块建修复模块任务接手，"
                           "契约写明接手这个任务（任务 id、分支），原任务请用户取消")}
SELF_SIGNALS = {"limit_resume"}   # 发给任务自己、不升级的信号
SELF_ALERTS = {"session_long"}    # 发给任务自己的告警（带常驻会话的 session_id）；pm 不处理时照常升级为 pm_unresponsive
PM_SIGNALS = {"session_stuck", "parent_done"}   # 不论对象是谁都发给 pm（上级模块可能已完成，或处理不了）；不升级为 pm_unresponsive


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
            to_self = c["signal"] in SELF_ALERTS
            to_pm = c["signal"] in PM_SIGNALS
            to_task = t["id"] if (own or to_self) else pm_task if to_pm else route(t, pm_task)
            is_pm = to_task == t["id"] and not own and not to_pm and t["workflow"].endswith("项目管理")
            if last is None or now - last >= timedelta(minutes=T_DEDUP):
                signal = "pm_unresponsive" if (is_pm and last is not None and t["step"] in RESIDENT) else c["signal"]
                al = {"to_task": to_task, "object": f"{t['title']} @ task {t['id']}", "step": t["step"],
                      "signal": signal, "value": c["value"], "threshold": c["threshold"],
                      "suggest": "refresh" if signal == "pm_unresponsive" else SUGGEST[c["signal"]]}
                if signal == "pm_unresponsive":
                    al["return_step"] = t["step"]
                if own:
                    al.update({"session_id": t["limit"].get("session_id"), "message": RESUME_TEXT.format(reset=c["value"])})
                if to_self and signal != "pm_unresponsive":
                    al["session_id"] = (t.get("long") or {}).get("session_id")
                # 发给模块任务的告警带上模块 agent 的会话 id：不带时消息进主会话，模块进过「验收调查」后那是验收者的
                mod_session = (by_id.get(to_task) or {}).get("module_session")
                if mod_session and not al.get("session_id") and signal != "pm_unresponsive":
                    al["session_id"] = mod_session
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


def load_statuses(mgmt_root):
    """kandev task id -> 该任务自己在 tasks.json 中的 status（没有 status 字段记为 ""）。来源和容错同 load_blockers。
    查不到的任务不在结果里（调用方得到 None，不据此告警）。"""
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
            for t in tasks:
                if t.get("kandev_task_id"):
                    out[t["kandev_task_id"]] = t.get("status") or ""
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            continue
    return out


def load_module_sessions(mgmt_root):
    """模块任务的 kandev task id -> 模块 agent 的会话 id，取自 modules/*/tasks.json 顶层的 module_task_id / module_session_id
    （v3.3.3 起模块 agent 在「模块规划」写入）。没写的模块不在结果里。容错同 load_blockers。"""
    out = {}
    mods = os.path.join(mgmt_root, "modules")
    if not os.path.isdir(mods):
        return out
    for m in os.listdir(mods):
        p = os.path.join(mods, m, "tasks.json")
        if m.startswith("_") or not os.path.exists(p):
            continue
        try:
            doc = json.load(open(p, encoding="utf-8"))
            if doc.get("module_task_id") and doc.get("module_session_id"):
                out[doc["module_task_id"]] = doc["module_session_id"]
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            continue
    return out


def note_failure(state_dir, now, err):
    """连不上 Kandev 时留痕：心跳文件记连续失败次数（at 不更新，仍表示最后一次成功），并在上次巡检过的各项目
    stage.md 标题下面加一行故障提示（用户看的就是这个文件；下次成功运行会整份重写，提示随之消失）。返回连续失败次数。"""
    beat_path = os.path.join(state_dir, "last_run.json")
    try:
        beat = json.load(open(beat_path, encoding="utf-8")) if os.path.exists(beat_path) else {}
    except (OSError, json.JSONDecodeError):
        beat = {}
    beat["failures"] = int(beat.get("failures") or 0) + 1
    beat["failed_at"], beat["last_error"] = now.isoformat(), str(err)[:300]
    os.makedirs(state_dir, exist_ok=True)
    with open(beat_path, "w", encoding="utf-8") as f:
        json.dump(beat, f, ensure_ascii=False, indent=1)
    banner = (f"{FAIL_MARK} 守护连不上 Kandev，已连续 {beat['failures']} 次（最近一次 "
              f"{now.astimezone().strftime('%Y-%m-%d %H:%M')}）：{beat['last_error']}。下面的内容是最后一次成功巡检时的，可能已经过时。")
    for root in beat.get("mgmt_roots") or []:
        path = os.path.join(root, "agents", "guard", "stage.md")
        try:
            lines = [l for l in open(path, encoding="utf-8").read().split("\n") if not l.startswith(FAIL_MARK)]
            lines[1:1] = [banner]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError:
            continue
    return beat["failures"]


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


def detect_long(k, task_id, sessions):
    """常驻步骤的任务：常驻会话空闲时，数它自上次上下文重置以来被唤醒了几次 → {"session_id", "wakes"}，否则 None。
    常驻会话 = 最新的一个还活着的会话（WAITING_FOR_INPUT / IDLE / RUNNING / STARTING；验收等一次性会话结束后是
    COMPLETED，不会被选中）。正在运行时也数：告警是排队送达的，而且这样去重状态不会因为某次巡检碰上它在运行而被清掉。
    最多翻 WAKE_PAGES 页；翻完还没看到重置标记时，按已数到的次数算。"""
    alive = LIMIT_STATES | ACTIVE_STATES
    s = next((s for s in sessions if s.get("state") in alive and s.get("session_id")), None)
    if not s:
        return None
    wakes, before = 0, None
    for _ in range(WAKE_PAGES):
        args = {"task_id": task_id, "session_id": s["session_id"], "sort": "desc", "limit": WAKE_PAGE,
                "message_types": ["message", "status"]}
        if before:
            args["before"] = before
        try:
            conv = k.call("get_task_conversation_kandev", args)
        except RuntimeError:
            return None
        msgs = conv.get("messages", []) if isinstance(conv, dict) else []
        n, seen = wakes_since_reset(msgs)
        wakes += n
        if seen or wakes >= T_WAKES or not msgs or not conv.get("has_more"):
            break
        before = msgs[-1].get("id")
    return {"session_id": s["session_id"], "wakes": wakes}


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
            live = step != DONE and t["state"] != "COMPLETED"
            if live or wname.endswith("模块管理"):     # 已完成的模块任务也取会话：完成后仍可能留着一个卡住的会话（session_stuck）
                item["sessions"] = k.call("list_task_sessions_kandev", {"task_id": t["id"]}).get("sessions", [])
            if live:
                try:
                    perms = k.call("list_pending_agent_permissions_kandev", {"task_id": t["id"]})
                    item["perm"] = len(perms.get("requests", perms.get("permissions", []))) if isinstance(perms, dict) else 0
                except RuntimeError:
                    item["perm"] = 0
                item["limit"] = detect_limit(k, t["id"], item["sessions"][0] if item["sessions"] else None)
                if step in RESIDENT and not item["limit"]:
                    item["long"] = detect_long(k, t["id"], item["sessions"])
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
        try:
            tasks = collect(ids)
        except (OSError, RuntimeError) as e:      # 连不上 Kandev MCP（URLError 是 OSError）或工具调用失败
            n = note_failure(a.state_dir, now, e)
            print(f"stage.py：连不上 Kandev 或查询失败（连续第 {n} 次）：{e}", file=sys.stderr)
            return 1

    projects = group_projects(tasks)
    if a.mgmt_root:
        projects = [pr for pr in projects if norm(pr["mgmt_root"]) == norm(a.mgmt_root)]
    os.makedirs(a.state_dir, exist_ok=True)
    texts, n_alerts = [], 0
    for pr in projects:
        root, ready = pr["mgmt_root"], initialized(pr["mgmt_root"])
        if ready and not a.snapshot:
            blockers, statuses, mod_sessions = load_blockers(root), load_statuses(root), load_module_sessions(root)
            for t in pr["tasks"]:
                t["blocker_status"] = blockers.get(t["id"])
                t["own_status"] = statuses.get(t["id"])
                t["module_session"] = mod_sessions.get(t["id"])
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
                "disabled": bool(disabled),
                "mgmt_roots": [pr["mgmt_root"] for pr in projects if initialized(pr["mgmt_root"])]}   # note_failure 用
        with open(beat_path, "w", encoding="utf-8") as f:
            json.dump(beat, f, ensure_ascii=False, indent=1)
    if not a.json:
        print("\n".join(texts) if texts else "没有进行中的项目。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
