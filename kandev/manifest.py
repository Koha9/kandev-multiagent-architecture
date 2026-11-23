"""安装清单（ma-manifest.json）与部署提问清单（deploy_questions.json）的读写和校验。ma.py 与 build_workflows.py 共用。

ma-manifest.json 放在安装目录（独立安装）或本仓库（链接模式）的根目录，不提交：
  version      安装的 workflow 版本
  mode         standalone（复制到安装目录）| link（直接使用源仓库）
  source       安装来源（路径、commit）
  files        独立安装时每个出厂文件的 sha256：升级时用来判断用户是否改过
  deployments  每个 workspace 一条：用户对 install 阶段提问的回答、ids / profiles 文件名、已部署的版本和指纹
"""
import fnmatch
import hashlib
import json
import os

NAME = "ma-manifest.json"
HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(HERE, "deploy_questions.json")
STAGES = ("install", "customize", "redeploy", "upgrade")
ASKS = ("always", "guided", "custom", "when_prompted")
STYLE_LEVEL = {"quick": 0, "guided": 1, "custom": 2}       # setup_style 选了哪种，问到哪一级
ASK_LEVEL = {"always": 0, "guided": 1, "custom": 2, "when_prompted": 9}
GROUPS = ("project_defaults",)                              # 答案里可以写成嵌套对象的键组
PROJECT_DEFAULTS = "custom/project-defaults.json"

# 不随安装复制的内容：本机文件、运行时状态、调研材料、用户的定制
SKIP_DIR_NAMES = {".git", ".claude", "__pycache__", "node_modules"}
SKIP_TOP = {"reports", "research_notes", "custom"}
SKIP_PREFIX = ("kandev/guard_state/", "kandev/export.local/", "evaluation/pilot-")
SKIP_FILES = ("*.local.md", "*.local.json", "kandev/kandev_ids*.json", NAME, "*.pyc", "*.new", "*.new.*", "*.mine",
              "*.mine.*", "*.bak", "*.tmp", ".conda-env")
GENERATED = ("docs/prompts.md", "kandev/export/*.json")   # 部署时重新生成，升级时直接覆盖

# 角色：必填 / 可选（缺省取另一个角色）/ 必须互不相同的组合。build_workflows.py 也用这三张表。
REQUIRED_ROLES = ("pm", "auditor", "developer", "reviewer", "mechanical")
OPTIONAL_ROLES = {"module": "pm", "module_auditor": "auditor", "plan_auditor": "auditor", "intake": "mechanical"}
DISTINCT = (("pm", "auditor"), ("pm", "plan_auditor"), ("module", "module_auditor"), ("developer", "reviewer"))
TYPES = {"string": str, "object": dict, "list": list}


def norm(path):
    return os.path.abspath(os.path.expanduser(path)).replace("\\", "/")


def load(root):
    p = os.path.join(root, NAME)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def save(root, m):
    """先写临时文件再替换：清单里有全部答案，不能留下半截文件。"""
    p = os.path.join(root, NAME)
    with open(p + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(p + ".tmp", p)


def sha(path):
    """文本文件按 LF 计算，避免 git 的换行转换让没改过的文件看起来被改了。"""
    data = open(path, "rb").read()
    if b"\0" not in data[:8192]:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def is_generated(rel):
    return any(fnmatch.fnmatch(rel, g) for g in GENERATED)


def shipped_files(root):
    """随安装复制的文件（相对路径，正斜杠，排序）。"""
    out = []
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root).replace("\\", "/")
        rel_d = "" if rel_d == "." else rel_d + "/"
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIR_NAMES and not (rel_d == "" and x in SKIP_TOP)
                         and not (rel_d + x + "/").startswith(SKIP_PREFIX))
        for f in sorted(files):
            rel = rel_d + f
            if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f, pat) for pat in SKIP_FILES):
                continue
            out.append(rel)
    return out


def questions(stage=None):
    qs = json.load(open(QUESTIONS, encoding="utf-8"))["questions"]
    return [q for q in qs if stage is None or q["stage"] == stage]


def full_profiles(p):
    """补上可选角色的缺省值。"""
    full = dict(p)
    for role, fallback in OPTIONAL_ROLES.items():
        full.setdefault(role, full.get(fallback))
    return full


def check_profiles(p):
    if not isinstance(p, dict):
        return ["必须是 {角色: agent profile id} 的对象"]
    problems = []
    missing = [r for r in REQUIRED_ROLES if not p.get(r) or "<" in str(p.get(r))]
    if missing:
        problems.append(f"缺少必填角色或还是占位：{missing}")
    unknown = set(p) - set(REQUIRED_ROLES) - set(OPTIONAL_ROLES)
    if unknown:
        problems.append(f"有不认识的角色：{sorted(unknown)}")
    full = full_profiles(p)
    problems += [f"{a} 与 {b} 必须是不同的 profile" for a, b in DISTINCT if full.get(a) and full.get(a) == full.get(b)]
    return problems


def flatten(answers):
    """{"project_defaults": {"remote": "pr"}} → {"project_defaults.remote": "pr"}（带点的键原样保留）。"""
    out = {}
    for k, v in answers.items():
        if k in GROUPS and isinstance(v, dict):
            out.update({f"{k}.{k2}": v2 for k2, v2 in v.items()})
        else:
            out[k] = v
    return out


def nest(flat):
    out = {}
    for k, v in flat.items():
        group, dot, sub = k.partition(".")
        if dot and group in GROUPS:
            if not isinstance(out.get(group), dict):      # 写错成非对象的组（validate 已报错）
                out[group] = {}
            out[group][sub] = v
        else:
            out[k] = v
    return out


def _value(q, val):
    """校验一个答案，返回 (规范化后的值, 问题说明或 None)。有 options 的项接受 JSON 的数字和布尔值，记成字符串。"""
    if q.get("options") and isinstance(val, (bool, int)):
        val = str(val).lower()
    if not isinstance(val, TYPES.get(q.get("type"), str)):
        return val, f"类型应为 {q.get('type', 'string')}，收到 {val!r}"
    if q.get("options") and val not in q["options"]:
        return val, f"可选值 {q['options']}，收到 {val!r}"
    if q.get("type") == "list" and (not val or not all(isinstance(x, str) and x for x in val)):
        return val, f"应为非空的字符串列表，收到 {val!r}"
    if q["key"] == "profiles":
        p = check_profiles(val)
        return val, "；".join(p) if p else None
    return val, None


def walk(answers, strict=True):
    """按提问树的顺序走一遍 install 阶段的提问。
    strict=True（install、questions）：按 setup_style 决定哪些项要问；False（已记录的答案：apply、doctor、answer）：
    只有 always 项和没有推荐值的适用项必须有答案，其余缺的补推荐值（兼容在新增提问之前安装的答案）。
    返回 (补全后的扁平答案, [(问题, 状态, 说明)])。状态：answered / invalid / pending（现在该问）/
    deferred（取决于还没回答的项）/ default（没问，用推荐值）/ skipped（when 不匹配，不适用）。"""
    flat = flatten(answers)
    out, items, open_keys = dict(flat), [], set()
    style = flat.get("setup_style")
    for q in questions("install"):
        key = q["key"]
        deps = set(q.get("when", {})) | set(q.get("after", [])) | ({"setup_style"} if q["ask"] != "always" else set())
        if deps & open_keys:
            items.append((q, "deferred", "先回答 " + "、".join(sorted(deps & open_keys))))
            open_keys.add(key)
            continue
        cond = {k: v if isinstance(v, list) else [v] for k, v in q.get("when", {}).items()}
        if any(out.get(k) not in v for k, v in cond.items()):
            if "otherwise" in q:
                out[key] = q["otherwise"]
            else:
                out.pop(key, None)
            items.append((q, "skipped", ""))
            continue
        if flat.get(key) in (None, ""):
            level_asked = strict and STYLE_LEVEL.get(style, 0) >= ASK_LEVEL[q["ask"]]
            if q["ask"] == "always" or "recommended" not in q or level_asked:
                items.append((q, "pending", ""))
                open_keys.add(key)
            else:
                out[key] = q["recommended"]
                items.append((q, "default", ""))
            continue
        out[key], problem = _value(q, flat[key])
        items.append((q, "invalid" if problem else "answered", problem or ""))
        if problem:
            open_keys.add(key)
    return out, items


def validate(answers, strict=True):
    """按提问清单校验 install 阶段的答案（只有这一阶段的答案会被记录）。
    返回 (补全了推荐值的答案（project_defaults 为嵌套对象）, [(key, 问题说明)])。"""
    qs = {q["key"] for q in questions("install")}
    problems = [(k, f"不认识的键（可用：{sorted(qs)}）") for k in flatten(answers) if k not in qs]
    problems += [(g, "应为 {键: 值} 的对象") for g in GROUPS if g in answers and not isinstance(answers[g], dict)]
    out, items = walk(answers, strict)
    flat = flatten(answers)
    for q, status, msg in items:
        if status == "invalid":
            problems.append((q["key"], msg))
        elif status == "pending" or (status == "deferred" and q["ask"] == "always" and flat.get(q["key"]) in (None, "")):
            how = "必须向用户确认" if q["ask"] == "always" or "recommended" not in q else \
                f"setup_style={out.get('setup_style')} 时这一项也要问（推荐：{q['recommended']}）"
            problems.append((q["key"], f"{how}——{q['question']}"))
    return nest(out), problems


def project_defaults(answers):
    """custom/project-defaults.json 的内容（W1「接收」读取）。值都是字符串；remote=none 时 ci=none。"""
    pd = flatten(validate(answers, strict=False)[0])
    out = {"_source": "ma.py install 根据部署提问的答案生成；改用 ma.py answer --set project_defaults.<键>=<值>"}
    for q in questions("install"):
        if q["key"].startswith("project_defaults."):
            out[q["key"].split(".", 1)[1]] = str(pd.get(q["key"], q.get("recommended")))
    if out.get("remote") == "none":
        out["ci"] = "none"
    return out


def deployment(m, workspace):
    return (m or {}).get("deployments", {}).get(workspace)


def missing_answers(root, workspace):
    """workspace 的部署还缺哪些必问项的答案（空列表 = 可以部署）。"""
    dep = deployment(load(root), workspace)
    if not dep:
        return [f"{q['key']}：{q['question']}" for q in questions("install") if q["ask"] == "always"]
    return [f"{k}：{msg}" for k, msg in validate(dep.get("answers", {}), strict=False)[1]]
