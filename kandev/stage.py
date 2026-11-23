"""阶段分类：从 Kandev 的结构化状态确定性地判断每个任务"现在在等谁"，生成告警（守护用）。

规则（分类的先后、阈值、每个信号发给谁、去重与升级、用量上限、自动停用）只有一份给人看的说明：
mgmt-template/roles/guard.md。代码里对应的是 classify（先后）、SIGNALS（发给谁、是否升级、建议）和 evaluate（去重、升级）。
改规则时这几处和 tests/test_stage.py 一起改；check_docs.py 会核对 guard.md 里的信号与 SIGNALS 一致。

一个 workspace 只需要一个守护：脚本自己发现所有进行中的项目，不需要按项目配置。
  - 项目 = 「多Agent · 项目管理」中未完成的任务（pm 任务）；mgmt_root 取自它描述中的 [TASK v1] 头
  - 模块任务按 [TASK v1] 头的 pm / parent 归到项目；开发任务按 parent（模块任务）归到项目
  - 管理目录已初始化（有 README.md）时，写 <mgmt_root>/agents/guard/stage.md；未初始化时不写，避免干扰立项规划

用法：
  python stage.py [--ids kandev_ids.json] [--json] [--disable-when-done]        # 所有进行中的项目（守护 automation 这样调用）
  python stage.py --dry-run                                                     # 人工查看：不写去重状态、心跳和 stage.md
  python stage.py --mgmt-root <管理目录> [--json]                               # 只看一个项目
  python stage.py --snapshot snapshot.json --now 2026-11-09T05:00:00+00:00 [--json]   # 离线测试，不连 Kandev

输出：--json 时标准输出每行一个要发出的告警（to_task、object、step、signal、value、threshold、suggest、project、mgmt_root、
journal；limit_resume 另带 session_id 和 message，pm_unresponsive 另带 return_step、workflow_id、refresh_step_id，
发给模块任务或常驻会话的另带 session_id）；否则打印给人看的摘要。退出码 1：连不上 Kandev，或有项目巡检失败。
状态：去重状态在 --state-dir（默认 kandev/guard_state/，不提交），按 pm 任务 id 分文件；心跳是同目录的 last_run.json
（非缺省的 ids 文件是 last_run.<workspace 前 8 位>.json，见 beat_name）。不带 --dry-run 的运行会把看到的告警记为已发。
只用标准库。
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import slots  # noqa: E402

PARAMS = slots.params()   # rules/params.json，可被 custom/rules/params.json 覆盖

GATE_PLAN = "立项确认"
GATES = {GATE_PLAN, "人工终审"}
RESIDENT = {"调度", "等待开发"}
HOLD, DECISION, DONE, INTAKE, MOD_PLAN = "待开发", "等待决策", "完成", "接收", "模块规划"
WAIT_PREREQ = "排队：等前置模块"         # W2 任务在「模块规划」、前置模块没有全部完成（不告警；数值是未完成的前置模块标题）
# 步骤名只用于分类，不认识的步骤名落到"运行中"，不会报错。与 build_workflows.py 的一致性由 check_docs.py「步骤名同步」核对。
SIGNAL_STEPS = {"接收", "立项规划", "立项评审", "模块下发", "项目验收", "收尾合并",
                "模块规划", "验收调查", "开发", "审核", "合并"}
AGENT_STEPS = SIGNAL_STEPS | RESIDENT | {"刷新"}
IDLE_STATES = {"WAITING_FOR_INPUT", "IDLE", "COMPLETED"}
LIMIT_STATES = {"WAITING_FOR_INPUT", "IDLE"}          # 用量上限停下后会话的状态（实测为 WAITING_FOR_INPUT）
ACTIVE_STATES = {"RUNNING", "STARTING"}
T_IDLE, T_DECISION, T_HOLD, T_STALE, T_DEDUP = 10, 10, 10, 45, 60
T_GATE = 30                               # autonomy 2 的任务在「立项确认」的提问挂了这么久（最新会话没有更新）→ gate_timeout（0 = 关闭）
T_LIMIT_FALLBACK, T_LIMIT_MARGIN, T_BEAT = 60, 2, 60
T_WAKES = PARAMS["refresh_wakes"]         # 常驻会话自上次重置被唤醒这么多次 → session_long（与 build_workflows.REFRESH_WAKES 同一个参数）
globals().update({k: v for k, v in PARAMS.get("guard", {}).items() if k in slots.GUARD_PARAMS})   # 用户定制的守护阈值（分钟）
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
BEAT_NAME = "last_run.json"              # 心跳文件名；main() 按 workspace 改（见 beat_name）
KANDEV_URL = None                        # main() 从 ids 文件的 _meta.url 取；None 表示默认地址


# ------------------------------------------------------------------ parsing helpers
def ts(s):
    if not s:
        return None
    m = re.match(r"^(.*?)(\.\d+)?(Z|[+-]\d\d:?\d\d)?$", s.strip())
    head, frac, tz = m.group(1), m.group(2) or "", m.group(3) or ""
    dt = datetime.fromisoformat(head + frac[:7] + ("+00:00" if tz == "Z" else tz))   # 小数秒截到 6 位
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def header_field(desc, name):
    m = re.search(rf"^{name}:[ \t]*(.+)$", desc or "", re.M)   # 值为空时不跨行取下一行
    return m.group(1).strip() if m else ""


def header_task(desc, name):
    m = re.search(rf"task\s+({UUID})", header_field(desc, name))
    return m.group(1) if m else None


def prereq_state(t):
    """任务前置的状态：(是否有前置信息, 是否有失败的前置, 前置是否全部完成)。
    来源只有 t["blocker_status"]：tasks.json 中 blocked_by 各任务的 status（[] = 登记了、没有前置；None = 查不到这个任务
    或读不到 tasks.json）。W3 任务不设 Kandev 的 blocked_by（docs/workflow.md 第 8、13 节），所以不看 Kandev 的依赖。"""
    statuses = t.get("blocker_status")
    if statuses is None:
        return False, False, False
    return True, "failed" in statuses, all(x in PREREQ_DONE for x in statuses)


def module_name(t):
    s = header_field(t.get("description"), "scope")
    return s[4:].strip() if s.startswith("mod:") else ""


def module_prereqs(t, by_id):
    """W2 任务的前置模块任务（by_id 中的任务 id）。两个来源取并集：
      - t["deps"]：Kandev 返回的依赖（collect 从任务的 blocked_by / depends_on 取；没有这个字段时为 None）
      - 按「模块下发」的建任务规则从 [TASK v1] 头推导（Kandev 不返回依赖时也能判断）：同一个 pm 下，
        baseline 和修复模块（scope 含 -fix-）没有前置；integration（kind 以 integration 开头）依赖其他全部非修复模块；
        其余模块依赖 baseline，以及 branch 行 `base mod/<模块>` 指向的那个模块
    查不到的 id（不属于这个项目）忽略。"""
    out = [d for d in (t.get("deps") or []) if d in by_id and d != t["id"]]
    desc = t.get("description")
    name, kind = module_name(t), header_field(desc, "kind")
    if not name or kind == "baseline" or "-fix-" in name:
        return out
    pm = header_task(desc, "pm")
    mods = {module_name(m): m["id"] for m in by_id.values()
            if m["workflow"].endswith("模块管理") and m["id"] != t["id"] and module_name(m)
            and header_task(m.get("description"), "pm") == pm}
    if kind.startswith("integration"):
        derived = [i for n, i in mods.items() if "-fix-" not in n]
    else:
        base = re.search(r"\bbase\s+mod/([\w.-]+)", header_field(desc, "branch"))
        derived = [mods[n] for n in ("baseline", base and base.group(1)) if n in mods]
    return out + [i for i in derived if i not in out]


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


# ------------------------------------------------------------------ signals
# 信号表：每个信号发给谁、会不会升级、带哪个会话 id、建议怎么处理，都只写在这里。
# 新增信号：在这里加一行，在 classify 里加一个分支，在 mgmt-template/roles/guard.md 的两张表里各加一行
# （check_docs.py「信号表」会核对），在 tests/test_stage.py 的 PRIORITY 里加一行。
#   to        SUPERIOR  被告警对象的上级（见 route：开发任务 → 模块任务；模块任务 → pm；pm → pm 自己）
#             SELF      任务自己
#             TO_PM     不论对象是谁都发给 pm（上级模块可能已完成，或处理不了）
#   escalate  告警发给了 pm 自己、pm 停在常驻步骤、信号自上次告警起一直没消除 → T_DEDUP 分钟后改发 pm_unresponsive
#   suggest   告警里的建议。只写一个词的是各角色 prompt 里已有的处理方法；写成整段的是完整的处理方法，
#             旧版 prompt 的 agent 收到也能照做
#   session   告警带的 session_id 取自任务的哪个字段（"limit" / "long"，见 collect）；None = 不带，
#             发给模块任务时由 evaluate 补上模块 agent 的会话 id
#   message   守护原样发到该会话的消息（只有用量上限恢复用）
Sig = namedtuple("Sig", "to escalate suggest session message", defaults=(None, None))
SUPERIOR, SELF, TO_PM = "superior", "self", "pm"
ESCALATED, DISABLED = "pm_unresponsive", "guard_disabled"     # 不由 classify 产生的两个信号：evaluate 升级、main 自动停用
SIGNALS = {
    "child_unrecorded": Sig(SUPERIOR, True, (
        "该开发任务已在「完成」，但 tasks.json 没有登记（合并的 REPORT 可能没有送达）："
        "`git log mod/<模块> --oneline --grep \"^<任务id>\"` 有提交 → tasks.json 记 merged，"
        "再检查 held 任务能否放行；没有提交 → 查 NOW「未确认的意图」，仍不清楚就 ESCALATE 给 pm，不要猜 merged")),
    "limit_resume": Sig(SELF, False, "continue", session="limit", message=RESUME_TEXT),
    "session_stuck": Sig(TO_PM, False, (
        "该任务有一个会话一直 RUNNING 但很久没有输出（数值是会话 id 前 8 位和分钟数），那一轮不会自己结束，"
        "发给这个会话的消息会一直排队。agent 取消不了它：在 attention.md 登记一条，请用户在 Kandev 界面打开该任务的"
        "这个会话并取消当前这一轮；在此之前不要再给这个会话发消息，要它做的事等取消后重发")),
    "parent_done": Sig(TO_PM, False, (
        "该开发任务还没结束，但它的模块任务已经完成（数值是模块任务标题），没有模块 agent 会处理它的 REPORT、提问和放行，"
        "也不能给已完成的模块发指令。它如果是多余的 → 请用户取消；它的工作还需要 → 为这个模块建修复模块任务接手，"
        "契约写明接手这个任务（任务 id、分支），原任务请用户取消")),
    "gate_timeout": Sig(SELF, False, (
        "立项确认的提问已挂了很久（见数值，分钟）而用户没有答复：按「立项确认」步骤 prompt 第 6 步处理"
        "（评审通过、未答复的项都有推荐答案且不涉及额度授权、删除数据、删减需求 → 按推荐答案继续并登记\"默认采用\"；否则保持停下）")),
    "decision_pending": Sig(SUPERIOR, True, "unblock"),
    "session_failed": Sig(SUPERIOR, True, "unblock"),
    "session_not_started": Sig(SUPERIOR, True, (
        "该任务进入当前步骤后一直没有启动会话（Kandev 停在 SCHEDULING）：先 move_task_kandev 到"
        "「等待决策」再移回当前步骤一次；再次收到本告警 → 新建任务取代它（workspace_mode=new_workspace、"
        "autopilot=true、base_branch=mod/<模块>），原任务移到「完成」并在 tasks.json 标 failed")),
    "hold_broken": Sig(SUPERIOR, True, "split"),
    "hold_ready": Sig(SUPERIOR, True, "unblock"),
    "idle_no_signal": Sig(SUPERIOR, True, "unblock"),
    "running_stale": Sig(SUPERIOR, True, "refresh"),
    "dev_blocked": Sig(SUPERIOR, True, "unblock"),
    "session_long": Sig(SELF, True, (
        "refresh：本会话自上次上下文重置以来被唤醒的次数已到上限（见数值）。处理完手头的事件后，把未落盘的状态写入 NOW.md，"
        "在 NOW「注意」节写一行 `刷新返回：<当前步骤名>`，再 move_task_kandev 把本任务移到本 workflow 的「刷新」"), session="long"),
}


def verdict(category, signal=None, value=None, threshold=None, due=True):
    """classify 的返回值。signal 必须在 SIGNALS 里（写错或漏登记时立即报错，不等到阈值满足的那一次）；
    due=False：条件成立但停留时间还没到阈值，这次不告警（signal 记为 None）。"""
    if signal is not None and signal not in SIGNALS:
        raise KeyError(f"classify 给出了信号表 SIGNALS 里没有的信号：{signal}")
    return {"category": category, "signal": signal if due else None, "value": value, "threshold": threshold}


# ------------------------------------------------------------------ classification (pure)
def classify(t, now, by_id):
    """t: dict(id, title, workflow, step, state, sessions[{state, updated_at}], perm, question, wip_admitted,
    wip_step, blocker_status, own_status, limit, long, module_session, deps, since). Returns dict(category, signal, value, threshold) — signal None = no alert.
    规则从上到下，第一条匹配的生效；给人看的规则表在 mgmt-template/roles/guard.md「阶段分类」，两处一起改。"""
    step, s0 = t["step"], (t["sessions"][0] if t["sessions"] else None)
    in_step = mins(t.get("since"), now)
    idle = mins(ts(s0.get("updated_at")), now) if s0 else -1
    r = verdict

    if step == DONE or t["state"] == "COMPLETED":
        stuck = stuck_session(t["sessions"], now, 0)     # 只有模块任务完成后还会带着会话列表（见 collect）
        if stuck:
            return r("等上级：已完成但会话卡住", "session_stuck", stuck, T_STALE)
        own = t.get("own_status")         # None = tasks.json 中查不到这个任务（或读不到 tasks.json）：不告警
        if t["workflow"].endswith("开发") and own is not None and own not in RECORDED:
            parent = by_id.get(header_task(t.get("description"), "parent"))
            if parent and not is_done(parent) and parent["step"] in MOD_LIVE:
                return r("等上级：完成未登记", "child_unrecorded", own or "(空)", T_IDLE, due=in_step >= T_IDLE)
            return r("完成（tasks.json 未登记）", value=own or "(空)")
        return r("完成")
    if t.get("perm"):
        return r("等人：权限请求", value=t["perm"])
    # 立项确认超时：只在 pm 的门禁提问还挂着（用户没有答复）时成立，时间从最新会话最后一次更新算起，
    # 所以"先不决定"（没有待答提问）和刚发出下一批提问（会话刚更新）都不会触发。排在"提问"之前。
    if (step == GATE_PLAN and T_GATE and t.get("question") and idle >= T_GATE
            and header_field(t.get("description"), "autonomy") == "2"
            and header_field(t.get("description"), "plan_only") != "true"):
        return r("等人：立项确认（超时）", "gate_timeout", idle, T_GATE)
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
            return r("等上级：模块已完成", "parent_done", parent["title"], T_IDLE, due=in_step >= T_IDLE)
    if step == INTAKE and s0 and s0.get("state") in ("FAILED", "CANCELLED"):
        return r("等人：接收会话失败", value=s0["state"])
    if step == INTAKE and s0 and s0.get("state") == "RUNNING" and idle >= T_STALE:
        return r("等人：接收疑似卡住", value=idle)
    if step == DECISION:
        return r("等上级：等待决策", "decision_pending", in_step, T_DECISION, due=in_step >= T_DECISION)
    if s0 and s0.get("state") in ("FAILED", "CANCELLED"):
        return r("等上级：会话失败", "session_failed", s0["state"], "-")
    if (t["state"] in SCHEDULING_STATES and step in AGENT_STEPS and not (s0 and s0.get("state") in ACTIVE_STATES)
            and not (t.get("wip_step") and t.get("wip_admitted") is False)):
        if not t["workflow"].endswith("开发"):     # W1 / W2 没有「等待决策」可用来重启会话：只给人看
            return r("等人：会话未启动", value=f"{step}，{in_step} 分钟")
        return r("等上级：会话未启动", "session_not_started", step, T_IDLE, due=in_step >= T_IDLE)
    known, pre_failed, pre_done = prereq_state(t)
    if step == HOLD:
        if not known:
            return r("待开发（tasks.json 中查不到前置）")
        if pre_failed:
            return r("等上级：前置失败", "hold_broken", "前置 failed", "-")
        if pre_done:
            return r("等上级：可放行", "hold_ready", in_step, T_HOLD, due=in_step >= T_HOLD)
        return r("待开发")
    if (t["workflow"].endswith("模块管理") and step == MOD_PLAN
            and not (s0 and s0.get("state") in ACTIVE_STATES)):
        # Kandev 的 blocked_by 还没解除，但会话被提前启动了（例如 pm 给它发了消息）：空闲是在等前置，不是没推进
        waiting = [by_id[i]["title"] for i in module_prereqs(t, by_id) if not is_done(by_id[i])]
        if waiting:
            return r(WAIT_PREREQ, value="、".join(waiting))
    if step in SIGNAL_STEPS and s0 and s0.get("state") in IDLE_STATES and idle >= T_IDLE:
        if t["workflow"].endswith("项目管理"):   # 会话是评审者 / 机械 agent / 等 pm 的，告警 pm 没人处理：只给人看
            return r("等人：空闲未推进", value=f"{step}，空闲 {idle} 分钟")
        return r("等上级：空闲未推进", "idle_no_signal", idle, T_IDLE)
    if s0 and s0.get("state") == "RUNNING" and idle >= T_STALE:
        return r("等上级：疑似卡住", "running_stale", idle, T_STALE)
    if step == "开发" and not s0 and known and not pre_done and t["workflow"].endswith("开发"):
        return r("等上级：开发步骤前置未满足", "dev_blocked", in_step, T_IDLE, due=in_step >= T_IDLE)
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


def evaluate(tasks, now, state, pm_task):
    """Returns (rows, alerts, new_state)。new_state 每个任务一条：
      step / since  所在步骤和守护第一次看到它在这一步的时间（换步骤后下面两项清空：算新的情况）
      alerts        信号 -> 上次告警的时间。满 T_DEDUP 分钟才删除，信号中途消失也不删：
                    时有时无的信号（空闲 ↔ 运行、恢复后又碰到上限）在 T_DEDUP 分钟内不会重发
      streak        已告警、并且之后每次巡检都还在的那个信号（没有则为 None）。升级为 pm_unresponsive 要求它没有中断过"""
    by_id = {t["id"]: t for t in tasks}
    rows, alerts, new_state = [], [], {}
    dedup = timedelta(minutes=T_DEDUP)
    for t in tasks:
        prev = state.get(t["id"], {})
        same = prev.get("step") == t["step"]
        since = prev.get("since") if same else None
        since = ts(since) if since else now
        t["since"] = since
        c = classify(t, now, by_id)
        cur, streak = c["signal"], None
        sent = dict(prev.get("alerts") or {}) if same else {}
        if cur:
            sig = SIGNALS[cur]
            last = ts(sent.get(cur))
            # 旧版状态文件没有 streak：旧版在信号消失时清空 alerts，所以记录还在就说明一直没消除
            unbroken = same and last is not None and prev.get("streak", cur) == cur
            streak = cur if unbroken else None
            if last is None or now - last >= dedup:
                to_task = t["id"] if sig.to == SELF else pm_task if sig.to == TO_PM else route(t, pm_task)
                escalated = (sig.escalate and unbroken and to_task == t["id"] and t["workflow"].endswith("项目管理")
                             and t["step"] in RESIDENT)
                al = {"to_task": to_task, "object": f"{t['title']} @ task {t['id']}", "step": t["step"],
                      "signal": ESCALATED if escalated else cur, "value": c["value"], "threshold": c["threshold"],
                      "suggest": "refresh" if escalated else sig.suggest}
                if escalated:
                    al["return_step"] = t["step"]
                else:
                    if sig.session:
                        al["session_id"] = (t.get(sig.session) or {}).get("session_id")
                    if sig.message:
                        al["message"] = sig.message.format(reset=c["value"])
                    # 发给模块任务的告警带上模块 agent 的会话 id：不带时消息进主会话，模块进过「验收调查」后那是验收者的
                    mod_session = (by_id.get(to_task) or {}).get("module_session")
                    if mod_session and not al.get("session_id"):
                        al["session_id"] = mod_session
                alerts.append(al)
                sent[cur], streak = now.isoformat(), cur
        sent = {k: v for k, v in sent.items() if ts(v) and now - ts(v) < dedup}
        new_state[t["id"]] = {"step": t["step"], "since": since.isoformat(), "alerts": sent, "streak": streak}
        rows.append({**c, "id": t["id"], "title": t["title"], "workflow": t["workflow"], "step": t["step"]})
    return rows, alerts, new_state


# ------------------------------------------------------------------ data collection
def read_json(path, default=None):
    """读 JSON 文件；不存在、编码不对（带 BOM 可以）、内容损坏都返回 default，不抛错。"""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    """先写临时文件再替换：中途被杀不会留下半截文件。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_modules(mgmt_root):
    """读一遍 modules/*/tasks.json（含 -fix-<n> 修复模块），返回：
      blockers   kandev task id -> [blocked_by 各任务的 status]（查不到的任务记为 None，视为未完成）
      statuses   kandev task id -> 该任务自己的 status（没有 status 字段记为 ""）
      sessions   模块任务的 kandev task id -> 模块 agent 的会话 id（顶层 module_task_id / module_session_id）
      unreadable 读不了或形状不对的模块名：这些模块的放行和未登记检查这次不生效，stage.md 里会提示
    """
    out = {"blockers": {}, "statuses": {}, "sessions": {}, "unreadable": []}
    mods = os.path.join(mgmt_root, "modules")
    if not os.path.isdir(mods):
        return out
    for m in sorted(os.listdir(mods)):
        p = os.path.join(mods, m, "tasks.json")
        if m.startswith("_") or not os.path.exists(p):
            continue
        doc = read_json(p)
        try:
            tasks = doc.get("tasks", [])
            status = {t["id"]: t.get("status") for t in tasks}
            blockers = {t["kandev_task_id"]: [status.get(b) for b in t.get("blocked_by") or []]
                        for t in tasks if t.get("kandev_task_id")}
            statuses = {t["kandev_task_id"]: t.get("status") or "" for t in tasks if t.get("kandev_task_id")}
        except (TypeError, KeyError, AttributeError):
            out["unreadable"].append(m)
            continue
        out["blockers"].update(blockers)
        out["statuses"].update(statuses)
        if doc.get("module_task_id") and doc.get("module_session_id"):
            out["sessions"][doc["module_task_id"]] = doc["module_session_id"]
    return out


def load_blockers(mgmt_root):
    return load_modules(mgmt_root)["blockers"]


def load_statuses(mgmt_root):
    return load_modules(mgmt_root)["statuses"]


def load_module_sessions(mgmt_root):
    return load_modules(mgmt_root)["sessions"]


def note_failure(state_dir, now, err):
    """连不上 Kandev 时留痕：心跳文件记连续失败次数（at 不更新，仍表示最后一次成功），并在上次巡检过的各项目
    stage.md 标题下面加一行故障提示（用户看的就是这个文件；下次成功运行会整份重写，提示随之消失）。返回连续失败次数。"""
    beat_path = os.path.join(state_dir, BEAT_NAME)
    beat = read_json(beat_path, {}) or {}
    beat["failures"] = int(beat.get("failures") or 0) + 1
    beat["failed_at"], beat["last_error"] = now.isoformat(), str(err)[:300]
    write_json(beat_path, beat)
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


def kandev():
    from kandev_client import Kandev  # noqa: E402
    return Kandev(KANDEV_URL, client="ma-guard")


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
    COMPLETED，不会被选中）。正在运行时也数：告警是排队送达的，而且这样 pm 的 session_long 不会因为某次巡检碰上它在运行
    而被算作"中途消除过"（那样就不升级为 pm_unresponsive 了）。
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


def kandev_deps(t):
    """list_tasks_kandev 返回的任务依赖（前置任务 id 列表）；响应里没有依赖字段时返回 None。
    字段名未在真实接口上核实过，所以 blocked_by / depends_on 都认，元素是字符串或带 id / task_id 的对象都可以。"""
    for key in ("blocked_by", "depends_on", "dependencies"):
        v = t.get(key)
        if isinstance(v, list):
            return [x if isinstance(x, str) else (x.get("id") or x.get("task_id") or x.get("depends_on_task_id"))
                    for x in v if isinstance(x, (str, dict))]
    return None


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
                    "wip_step": step in wip_steps,
                    "question": t["id"] in pq_tasks, "sessions": [], "perm": 0, "deps": kandev_deps(t)}
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


def beat_name(ids_path, ids):
    """心跳文件名。缺省的 ids 文件（kandev_ids.json）用 last_run.json；同一目录部署了多个 workspace 时，
    其他 workspace 的 ids 文件名带前 8 位 id，心跳也带，避免互相覆盖（自动停用和故障计数都读它）。"""
    ws = (ids.get("_meta") or {}).get("workspace_id") or ""
    return "last_run.json" if os.path.basename(ids_path) == "kandev_ids.json" or not ws else f"last_run.{ws[:8]}.json"


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


NOTICE_MARKS = ("未登记", "查不到前置", "会话过长", "等前置模块")     # 分类名里带这些字样的行在 stage.md 单列出来


def render(rows, alerts, now_local, unreadable=None):
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
    notice = [r for r in rows if any(k in r["category"] for k in NOTICE_MARKS)]
    if notice or unreadable:
        out += ["## 留意（不告警）", ""] + [f"- {r['title']}（{r['step']}）：{r['category']}"
                                         + (f"（{r['value']}）" if r["category"] == WAIT_PREREQ else "") for r in notice]
        out += [f"- modules/{m}/tasks.json 读不了或格式不对：这个模块的放行和未登记检查这次没有生效" for m in unreadable or []]
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
    p.add_argument("--dry-run", action="store_true",
                   help="只看不记：不写去重状态、心跳和 stage.md。人工查看或验收时用，否则这次看到的告警会被记为已发，守护 60 分钟内不再发")
    p.add_argument("--disable-when-done", action="store_true",
                   help=f"所有项目正常结束后把「{GUARD_NAME}」automation 设为停用（只由守护 automation 传入）")
    a = p.parse_args()

    now = ts(a.now) if a.now else datetime.now(timezone.utc)
    ids = json.load(open(a.ids, encoding="utf-8")) if os.path.exists(a.ids) else {}
    global KANDEV_URL
    KANDEV_URL = ids.get("_meta", {}).get("url")
    w1 = ids.get("多Agent · 项目管理", {})
    if a.snapshot:
        tasks = json.load(open(a.snapshot, encoding="utf-8"))["tasks"]
        for t in tasks:
            t.setdefault("description", ""), t.setdefault("sessions", [])
    else:
        try:
            tasks = collect(ids)
        except Exception as e:      # 连不上 Kandev MCP、工具调用失败、响应缺字段：都留痕，不让守护无声退出
            n = note_failure(a.state_dir, now, e) if not a.dry_run else 0
            print(f"stage.py：连不上 Kandev 或查询失败（连续第 {n} 次）：{e}", file=sys.stderr)
            return 1

    global BEAT_NAME
    BEAT_NAME = beat_name(a.ids, ids)
    explicit_state = any(x == "--state-dir" or x.startswith("--state-dir=") for x in sys.argv[1:])
    write = not a.dry_run and not (a.snapshot and not explicit_state)     # 离线快照不往真实状态目录写
    unknown = [t["title"] for t in tasks if t["step"] == "?"]
    if unknown:
        print(f"stage.py：{len(unknown)} 个任务所在的步骤不在 ids 文件 {a.ids} 里（ids 可能过期或指错了 workspace），"
              f"它们不会被正确分类：{'、'.join(unknown[:5])}", file=sys.stderr)
    projects = group_projects(tasks)
    if a.mgmt_root:
        projects = [pr for pr in projects if norm(pr["mgmt_root"]) == norm(a.mgmt_root)]
    texts, n_alerts, failed = [], 0, 0
    for pr in projects:
        try:
            root, ready = pr["mgmt_root"], initialized(pr["mgmt_root"])
            mods = load_modules(root) if ready and not a.snapshot else None
            if mods:
                for t in pr["tasks"]:
                    t["blocker_status"] = mods["blockers"].get(t["id"])
                    t["own_status"] = mods["statuses"].get(t["id"])
                    t["module_session"] = mods["sessions"].get(t["id"])
            state_path = os.path.join(a.state_dir, f"{pr['pm_task']}.json")
            state = read_json(state_path, {}) or {}       # 损坏的状态文件按空处理：代价是告警重发一次
            rows, alerts, new_state = evaluate(pr["tasks"], now, state, pr["pm_task"])
            text = render(rows, alerts, now.astimezone().strftime("%Y-%m-%d %H:%M"), mods and mods["unreadable"])
            journal = (os.path.join(root, "agents", "guard", "journal.md") if ready
                       else os.path.join(a.state_dir, "journal.md"))
            for al in alerts:
                al.update({"project": pr["title"], "mgmt_root": root, "journal": journal})
                if al["signal"] == ESCALATED:
                    al.update({"workflow_id": w1.get("workflow_id"), "refresh_step_id": w1.get("steps", {}).get("刷新")})
                if a.json:
                    print(json.dumps(al, ensure_ascii=False))
            n_alerts += len(alerts)
            # 告警已经输出，再记"已发"和 stage.md：这两步失败最多让告警重发一次，不会把没发出的告警记成已发
            if write:
                if ready:
                    out = os.path.join(root, "agents", "guard", "stage.md")
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out, "w", encoding="utf-8") as f:
                        f.write(text)
                write_json(state_path, new_state)
            texts.append(f"===== {pr['title']} · {root or '（未写 mgmt_root）'}\n{text}")
        except Exception as e:      # 一个项目的管理目录有问题不能挡住其他项目
            failed += 1
            print(f"stage.py：项目「{pr.get('title')}」巡检失败，已跳过：{type(e).__name__}: {e}", file=sys.stderr)
    beat_path = os.path.join(a.state_dir, BEAT_NAME)
    disabled = None
    if a.disable_when_done and write and not a.snapshot and not a.mgmt_root and not failed:
        prev = read_json(beat_path, {}) or {}
        ok, reason = should_disable(prev, projects, tasks, now)
        if ok:
            ws = ids.get("_meta", {}).get("workspace_id")
            disabled = {"to_task": None, "signal": DISABLED, "value": reason, "threshold": "-",
                        "suggest": "none", "project": "", "mgmt_root": "",
                        "journal": os.path.join(a.state_dir, "journal.md"),
                        "automation_ids": disable_guard(ws)}
            n_alerts += 1
            if a.json:
                print(json.dumps(disabled, ensure_ascii=False))
            texts.append(f"已停用守护 automation：{reason}")
    if write and not a.snapshot and not a.mgmt_root:   # 心跳：守护是否还在运行，看这个文件的 at 即可
        beat = {"at": now.isoformat(), "projects": [pr["title"] for pr in projects], "alerts": n_alerts,
                "disabled": bool(disabled), "failed_projects": failed,
                "mgmt_roots": [pr["mgmt_root"] for pr in projects if initialized(pr["mgmt_root"])]}   # note_failure 用
        write_json(beat_path, beat)
    if not a.json:
        print("\n".join(texts) if texts else "没有进行中的项目。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
