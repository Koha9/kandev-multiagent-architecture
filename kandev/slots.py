"""规则槽位：用户可以定制、构建时内联进步骤 prompt 的规则和参数。build_workflows.py 与 stage.py 共用。

出厂文件在 <root>/rules/；用户的覆盖放在 <root>/custom/rules/ 的同名文件里（custom/ 不随升级改动，本仓库中不提交）。
- <槽位>.md：第一行 `---` 之前是给人看的说明，之后是正文；正文为空表示不注入任何内容。
- params.json：数值参数；custom 中只写要改的键。
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES, CUSTOM = os.path.join(ROOT, "rules"), os.path.join(ROOT, "custom", "rules")
SLOTS = ("workspace", "git", "coding", "testing", "quality")
TITLES = {"git": "Git 规则", "coding": "编码规则"}
GUARD_PARAMS = ("T_IDLE", "T_DECISION", "T_HOLD", "T_STALE", "T_DEDUP")


def slot_path(name, root=None):
    """生效的槽位文件：custom 中有就用 custom 的。"""
    rules, custom = (os.path.join(root, "rules"), os.path.join(root, "custom", "rules")) if root else (RULES, CUSTOM)
    p = os.path.join(custom, name + ".md")
    return p if os.path.exists(p) else os.path.join(rules, name + ".md")


def body(text):
    """槽位文件的正文：第一行 `---` 之后的内容，去掉首尾空白。没有 `---` 时整份都是正文。"""
    lines = text.replace("\r\n", "\n").split("\n")
    if "---" in lines:
        lines = lines[lines.index("---") + 1:]
    return "\n".join(lines).strip()


def slot(name, root=None):
    return body(open(slot_path(name, root), encoding="utf-8").read())


def is_custom(name, root=None):
    r = root or ROOT
    p = os.path.join(r, "custom", "rules", name + (".json" if name == "params" else ".md"))
    return os.path.exists(p)


def params(root=None):
    r = root or ROOT
    out = json.load(open(os.path.join(r, "rules", "params.json"), encoding="utf-8"))
    p = os.path.join(r, "custom", "rules", "params.json")
    if os.path.exists(p):
        mine = json.load(open(p, encoding="utf-8"))
        unknown = set(mine) - set(out)
        if unknown:
            raise SystemExit(f"custom/rules/params.json 中有不认识的键：{sorted(unknown)}")
        bad = set(mine.get("guard", {})) - set(GUARD_PARAMS)
        if bad:
            raise SystemExit(f"custom/rules/params.json 的 guard 中有不认识的键：{sorted(bad)}（可用：{GUARD_PARAMS}）")
        out.update({k: v for k, v in mine.items() if k != "guard"})
        out["guard"] = {**out.get("guard", {}), **mine.get("guard", {})}
    return out


def custom_block(*names):
    """非空的定制槽位拼成的段落（前面带换行）；都为空时返回空串，prompt 与出厂完全相同。"""
    parts = [f"【{TITLES[n]}】（本机定制，与契约或 environment.md 冲突时以它们为准并上报）\n{slot(n)}" for n in names if slot(n)]
    return "".join("\n" + p for p in parts)
