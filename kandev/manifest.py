"""安装清单（ma-manifest.json）与部署提问清单（deploy_questions.json）的读写和校验。ma.py 与 build_workflows.py 共用。

ma-manifest.json 放在安装目录（独立安装）或本仓库（链接模式）的根目录，不提交：
  version      安装的 workflow 版本
  mode         standalone（复制到安装目录）| link（直接使用源仓库）
  source       安装来源（路径、commit）
  files        独立安装时每个出厂文件的 sha256：升级时用来判断用户是否改过
  deployments  每个 workspace 一条：install 阶段提问的答案（answers，补全了推荐值）、其中哪些是答案文件里写明的
               （explicit；其余是推荐值，前面的答案改了会跟着变）、哪些是 agent 检测后填的（agent）、
               ids / profiles 文件名、已部署的版本和指纹
"""
import fnmatch
import hashlib
import json
import os
import sys

NAME = "ma-manifest.json"
HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(HERE, "deploy_questions.json")
STAGES = ("install", "customize", "redeploy", "upgrade")
ASKS = ("always", "guided", "custom", "detect", "when_prompted")
STYLE_LEVEL = {"quick": 0, "guided": 1, "custom": 2}       # setup_style 选了哪种，问到哪一级
ASK_LEVEL = {"always": 0, "guided": 1, "custom": 2, "detect": 9, "when_prompted": 9}   # detect：从不问，agent 检测后填
GROUPS = ("project_defaults",)                              # 答案里可以写成嵌套对象的键组
PROJECT_DEFAULTS = "custom/project-defaults.json"
PROJECT_DEFAULTS_SCHEMA = "2"                               # 与 W1「接收」的约定（docs/intake.md「部署缺省值」）
AGENT_KEY = "_agent"                                        # 答案文件里的保留键：agent 检测后自己填、没问用户的键
# 旧版答案的兼容：已删除的提问静默丢弃，改了名的取值换成新值
LEGACY_KEYS = ("vendors", "reviewer_cross_vendor")
LEGACY_VALUES = {("model_strategy", "vendor"): "scoped", ("project_defaults.integration_test", "ask"): "auto"}

# 不随安装复制的内容：本机文件、运行时状态、调研材料、用户的定制
SKIP_DIR_NAMES = {".git", ".claude", "__pycache__", "node_modules"}
SKIP_TOP = {"reports", "research_notes", "custom"}
SKIP_PREFIX = ("kandev/guard_state/", "kandev/export.local/", "evaluation/pilot-")
SKIP_FILES = ("*.local.md", "*.local.json", "kandev/kandev_ids*.json", NAME, "*.pyc", "*.new", "*.new.*", "*.mine",
              "*.mine.*", "*.bak", "*.tmp", ".conda-env")
GENERATED = ("docs/prompts.md", "kandev/export/*.json")   # 部署时重新生成，升级时直接覆盖

# 角色：必填 / 可选（缺省取另一个角色）/ 必须互不相同的组合。build_workflows.py 也用这三张表。
REQUIRED_ROLES = ("pm", "auditor", "developer", "reviewer", "mechanical")
# guard（守护 automation，不绑定任何步骤）排在 intake 之后：没写时取 intake，intake 也没写时取 mechanical。
OPTIONAL_ROLES = {"module": "pm", "module_auditor": "auditor", "plan_auditor": "auditor", "intake": "mechanical",
                  "guard": "intake"}
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


def tree():
    """install 阶段会记录答案的提问（提问树）；when_prompted 的项不在树里。"""
    return [q for q in questions("install") if q["ask"] != "when_prompted"]


def recommended(q, out):
    """这一项的推荐值：recommended_when 里第一条与前面的答案匹配的 value，否则 recommended。"""
    for r in q.get("recommended_when", []):
        if all(out.get(k) in (v if isinstance(v, list) else [v]) for k, v in r["when"].items()):
            return r["value"]
    return q.get("recommended")


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
    """{"project_defaults": {"remote": "pr"}} → {"project_defaults.remote": "pr"}（带点的键原样保留）。
    以 _ 开头的顶层键（_agent、注释）不是答案，去掉；旧版的键和取值按 LEGACY_* 换成现在的。"""
    out = {}
    for k, v in answers.items():
        if k.startswith("_"):
            continue
        if k in GROUPS and isinstance(v, dict):
            out.update({f"{k}.{k2}": v2 for k2, v2 in v.items()})
        else:
            out[k] = v
    for k in LEGACY_KEYS:
        out.pop(k, None)
    for (k, old), new in LEGACY_VALUES.items():
        if isinstance(out.get(k), str) and out[k] == old:
            out[k] = new
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
    later（适用、要问，但属于后面的批次）/ deferred（取决于还没回答的项）/ default（没问，用推荐值）/
    skipped（when 不匹配，不适用）。一批 = 一个 group：按清单顺序第一个还有 pending 或 invalid 的 group 是这一批。"""
    flat = flatten(answers)
    out, items, open_keys = dict(flat), [], set()
    style = flat.get("setup_style")
    for q in tree():
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
                out[key] = recommended(q, out)
                items.append((q, "default", ""))
            continue
        out[key], problem = _value(q, flat[key])
        items.append((q, "invalid" if problem else "answered", problem or ""))
        if problem:
            open_keys.add(key)
    batch = next((q.get("group") for q, st, _ in items if st in ("pending", "invalid")), None)
    items = [(q, "later" if st == "pending" and q.get("group") != batch else st, msg) for q, st, msg in items]
    return out, items


def cross_checks(flat):
    """几项答案之间的约束。返回 (问题 [(key, 说明)], 提示 [说明])：问题拒绝安装，提示只在总表后面列出。"""
    pd = lambda k: flat.get("project_defaults." + k)       # noqa: E731
    problems, notes = [], []
    if pd("ci") == "remote" and pd("remote") == "none":
        problems.append(("project_defaults.ci", "ci=remote 要等远端 CI 的结果，交付方式（project_defaults.remote）不能是 none："
                                                "把 ci 改成 local，或把 remote 改成 auto / push / pr"))
    if flat.get("review_access") == "remote_only" and pd("remote") == "none":
        problems.append(("project_defaults.remote", "review_access=remote_only（只能在远端看结果）时交付方式不能是 none："
                                                    "改成 pr / push / auto，或把 review_access 改成 local / ask"))
    if pd("autonomy") == "4" and pd("plan_only") == "true":
        notes.append("autonomy=4 且 plan_only=true：完全无人值守的项目也会停在「立项确认」等用户批准。")
    if pd("autonomy") == "4" and pd("remote") == "push":
        notes.append("autonomy=4 且 remote=push：人工终审仍会等你批准，但批准后直接推送基线分支，不再单独问这次推不推送；想先在网页上审查就改成 pr。")
    return problems, notes


def explicit_keys(answers):
    """答案里写明且合格的键（其余的值是推荐值或 otherwise，不算用户的答案）。"""
    return [q["key"] for q, st, _ in walk(answers, strict=False)[1] if st == "answered"]


def agent_keys(answers):
    """答案文件的 _agent 里列出、且确实写了值的键：agent 检测后自己填的，没问用户。"""
    listed = answers.get(AGENT_KEY)
    return [k for k in explicit_keys(answers) if isinstance(listed, list) and k in listed]


def validate(answers, strict=True):
    """按提问清单校验 install 阶段的答案（只有这一阶段的答案会被记录）。
    返回 (补全了推荐值的答案（project_defaults 为嵌套对象）, [(key, 问题说明)])。"""
    qs = {q["key"]: q for q in tree()}
    problems = [(k, f"不认识的键（可用：{sorted(qs)}）") for k in flatten(answers) if k not in qs]
    problems += [(g, "应为 {键: 值} 的对象") for g in GROUPS if g in answers and not isinstance(answers[g], dict)]
    listed = answers.get(AGENT_KEY)
    if listed is not None:
        if not isinstance(listed, list) or not all(isinstance(k, str) for k in listed):
            problems.append((AGENT_KEY, "应为键名的列表（agent 检测后自己填、没问用户的键）"))
        else:
            problems += [(AGENT_KEY, f"不认识的键 {k}") for k in listed if k not in qs]
            problems += [(AGENT_KEY, f"{k} 是必须问用户的项，不能由 agent 决定") for k in listed
                         if k in qs and qs[k]["ask"] == "always"]
    out, items = walk(answers, strict)
    flat = flatten(answers)
    for q, status, msg in items:
        if status == "invalid":
            problems.append((q["key"], msg))
        elif status in ("pending", "later") or (status == "deferred" and q["ask"] == "always"
                                                and flat.get(q["key"]) in (None, "")):
            how = "必须向用户确认" if q["ask"] == "always" or "recommended" not in q else \
                f"setup_style={out.get('setup_style')} 时这一项也要问（推荐：{recommended(q, out)}）"
            problems.append((q["key"], f"{how}——{q['question']}"))
    if not problems:
        problems += cross_checks(out)[0]
    return nest(out), problems


def project_defaults(answers):
    """custom/project-defaults.json 的内容（W1「接收」读取；键和取值是与 docs/intake.md「部署缺省值」的约定）。
    值都是字符串。review_access 是部署提问的顶层键，也写进来：「接收」靠它决定 remote=auto 时怎么交付。"""
    pd = flatten(validate(answers, strict=False)[0])
    by_key = {q["key"]: q for q in tree()}
    out = {"_schema": PROJECT_DEFAULTS_SCHEMA,
           "_source": "ma.py install 根据部署提问的答案生成；改用 ma.py answer --set project_defaults.<键>=<值>"
                      "（review_access 用 --set review_access=<值>）"}
    for key in ["review_access"] + [k for k in by_key if k.startswith("project_defaults.")]:
        out[key.split(".", 1)[-1]] = str(pd.get(key, by_key[key].get("recommended")))
    return out


def resolve(full, root):
    """把 python、home 的占位换成实际的值。full：validate 补全后的答案；root：运行 ma.py 的仓库（链接模式的 home）。"""
    a = dict(full)
    if str(a.get("python") or "").startswith("<"):
        a["python"] = sys.executable.replace("\\", "/")
    if a.get("install_mode") == "link":
        a["home"] = root
    elif a.get("home"):
        a["home"] = norm(a["home"].replace("<workspace id 前 8 位>", str(a.get("workspace_id") or "")[:8]))
    return a


def deployment(m, workspace):
    return (m or {}).get("deployments", {}).get(workspace)


def missing_answers(root, workspace):
    """workspace 的部署还缺哪些必问项的答案（空列表 = 可以部署）。"""
    dep = deployment(load(root), workspace)
    if not dep:
        return [f"{q['key']}：{q['question']}" for q in tree() if q["ask"] == "always"]
    return [f"{k}：{msg}" for k, msg in validate(dep.get("answers", {}), strict=False)[1]]
