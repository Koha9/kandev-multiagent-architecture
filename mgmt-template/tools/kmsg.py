"""生成 W3「合并」步骤发给模块 agent 的 KMSG v1 消息（REPORT / ESCALATE），并给出 message_task_kandev 的参数。

用法（写在一行里；--parent 传任务描述 [TASK v1] 头里 parent 行的原文）：
  python <mgmt_root>/tools/kmsg.py report --self-scope dev:<任务id> --self-task <本任务 UUID> --parent "<parent 行原文>"
         --refs <合入的 commit> --evidence "<commit>；合并门禁 <命令>：通过" [--summary "<一句>"]
  python <mgmt_root>/tools/kmsg.py escalate --self-scope dev:<任务id> --self-task <本任务 UUID> --parent "<parent 行原文>"
         --problem "<一句>" --impact "<哪些任务或模块>" --option "A. ...（推荐，理由）" --option "B. ..." [--refs <指针>]

parent 行形如 `parent: mod:<模块> @ task <UUID> session <id>`；也接受 `parent=`、没有 `parent:` 前缀、没有 session 段、多余空格。
--summary 缺省为 "<任务id> 已合入 mod/<模块>"（任务id 取自 --self-scope 的 dev: 之后，模块取自 parent 的 mod: 之后）。
--option 没有写 "A. " 这样的编号时按顺序补上。消息 id 的时间取自系统时钟。
输出：标准输出一个 JSON 对象 {"task_id", "session_id", "prompt"}：task_id / session_id（parent 行没有 session 段时为 null，
这时调用 message_task_kandev 不传 session_id）原样作为参数，prompt 是完整的 KMSG 正文。格式见 protocol/message.md。
退出码：0 成功；2 参数错误（parent 行里找不到 task UUID、缺必填项）。只用标准库。
"""
import argparse
import json
import re
import sys
from datetime import datetime

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


class ArgError(Exception):
    pass


def parse_parent(line):
    """parent 行 → (scope, task_id, session_id 或 None)。找不到 task UUID 或 scope 时抛 ArgError。"""
    text = (line or "").strip()
    text = re.sub(r"^\s*parent\s*[:=：]\s*", "", text, flags=re.I)
    task = re.search(rf"\btask\s*[:=]?\s*({UUID})", text, re.I)
    if not task:
        raise ArgError(f"parent 行里找不到 `task <UUID>`：{line!r}。请从任务描述 [TASK v1] 头逐字复制 parent 行")
    scope = re.search(r"([^\s@]+)\s*@\s*task\b", text, re.I)
    if not scope:
        raise ArgError(f"parent 行里找不到上级的 scope（`mod:<模块> @ task ...`）：{line!r}")
    # session 要紧跟在 task UUID 之后，本身像一个 id（至少 8 个字符，不含 <>、中文、空格）：没填的占位（<本会话的 … ID>）当作没有
    sess = re.match(r"\s*[,，]?\s*session\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9_.:-]{7,})(?=\s|$|[,，（(])", text[task.end():], re.I)
    return scope.group(1), task.group(1), (sess.group(1) if sess else None)


def msg_id(self_scope, now=None):
    return f"M-{self_scope.replace(':', '.')}-{(now or datetime.now()).strftime('%y%m%d-%H%M%S')}"


def envelope(kind, self_scope, self_task, parent_scope, parent_task, reply, due, refs, now=None):
    return "\n".join([
        "[KMSG v1]",
        f"id: {msg_id(self_scope, now)}",
        f"type: {kind}",
        f"from: {self_scope} @ task {self_task}",
        f"to: {parent_scope} @ task {parent_task}",
        f"reply: {reply}",
        "reply_to: -",
        f"due: {due}",
        f"refs: {refs}",
        "---",
    ])


def after(prefix, scope):
    return scope[len(prefix):] if scope.startswith(prefix) else scope


def report(a, parent, now=None):
    p_scope, p_task, _ = parent
    summary = a.summary or f"{after('dev:', a.self_scope)} 已合入 mod/{after('mod:', p_scope)}"
    body = [
        "结果：done",
        f"摘要：{summary}",
        f"证据：{a.evidence}",
        "偏差：无",
        "未完成 / 无法验证：无",
        "需要决定：无",
    ]
    return envelope("REPORT", a.self_scope, a.self_task, p_scope, p_task, "none", "-", a.refs, now) + "\n" + "\n".join(body)


def escalate(a, parent, now=None):
    p_scope, p_task, _ = parent
    opts = []
    for i, o in enumerate(a.option):
        o = o.strip()
        label = chr(ord("A") + i)
        opts.append("  " + (o if re.match(r"^[A-Z][.．、]\s*", o) else f"{label}. {o}"))
    body = [f"问题：{a.problem}", f"影响：{a.impact}", "选项：", *opts,
            f"需要谁决定：{p_scope}", "等待期间我将：暂停"]
    return (envelope("ESCALATE", a.self_scope, a.self_task, p_scope, p_task, "required", "next-wake", a.refs or "-", now)
            + "\n" + "\n".join(body))


def parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="kind", required=True)
    for name in ("report", "escalate"):
        s = sub.add_parser(name)
        s.add_argument("--self-scope", required=True, help="本任务的 scope，例如 dev:auth-02")
        s.add_argument("--self-task", required=True, help="本任务的 Kandev task UUID")
        s.add_argument("--parent", required=True, help="[TASK v1] 头里 parent 行的原文")
        if name == "report":
            s.add_argument("--refs", required=True, help="合入的 commit")
            s.add_argument("--evidence", required=True, help="证据一句：<commit>；合并门禁 <命令>：<结果>")
            s.add_argument("--summary", help="摘要一句（缺省：<任务id> 已合入 mod/<模块>）")
        else:
            s.add_argument("--problem", required=True)
            s.add_argument("--impact", required=True)
            s.add_argument("--option", action="append", required=True, help="可重复；第一项写推荐和理由")
            s.add_argument("--refs", default="-")
    return p


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    a = parser().parse_args(argv)
    try:
        if not a.self_scope.strip() or not a.self_task.strip():
            raise ArgError("--self-scope 和 --self-task 不能为空")
        if not re.fullmatch(UUID, a.self_task.strip()):
            raise ArgError(f"--self-task 要是本任务的 UUID（步骤 prompt 第一行「运行在 Kandev 任务 …」中的那个）：{a.self_task!r}")
        parent = parse_parent(a.parent)
        text = report(a, parent) if a.kind == "report" else escalate(a, parent)
    except ArgError as e:
        print(f"kmsg.py：{e}", file=sys.stderr)
        return 2
    print(json.dumps({"task_id": parent[1], "session_id": parent[2], "prompt": text}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
