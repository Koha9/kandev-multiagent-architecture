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
ASKS = ("always", "custom", "when_prompted")

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


def validate(answers):
    """按提问清单校验 install 阶段的答案（只有这一阶段的答案会被记录）。
    返回 (补全了推荐值的答案, [(key, 问题说明)])。"""
    out, problems = dict(answers), []
    qs = {q["key"]: q for q in questions("install")}
    problems += [(k, f"不认识的键（可用：{sorted(qs)}）") for k in answers if k not in qs]
    custom, link = answers.get("setup_style") == "custom", answers.get("install_mode") == "link"
    for key, q in qs.items():
        if key == "home" and link:              # 链接模式的安装目录就是本仓库
            out.pop("home", None)
            continue
        if answers.get(key) in (None, ""):
            if q["ask"] == "always":
                problems.append((key, f"必须向用户确认——{q['question']}"))
            elif custom:
                problems.append((key, f"用户选了自定义，这一项也要问——{q['question']}（推荐：{q['recommended']}）"))
            else:
                out[key] = q["recommended"]
            continue
        val = answers[key]
        if not isinstance(val, TYPES.get(q.get("type"), str)):
            problems.append((key, f"类型应为 {q.get('type', 'string')}，收到 {val!r}"))
        elif q.get("options") and val not in q["options"]:
            problems.append((key, f"可选值 {q['options']}，收到 {val!r}"))
        elif key == "profiles":
            problems += [(key, p) for p in check_profiles(val)]
    return out, problems


def deployment(m, workspace):
    return (m or {}).get("deployments", {}).get(workspace)


def missing_answers(root, workspace):
    """workspace 的部署还缺哪些必问项的答案（空列表 = 可以部署）。"""
    dep = deployment(load(root), workspace)
    if not dep:
        return [f"{q['key']}：{q['question']}" for q in questions("install") if q["ask"] == "always"]
    return [f"{k}：{msg}" for k, msg in validate(dep.get("answers", {}))[1]]
