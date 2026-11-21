"""安装清单（ma-manifest.json）与部署提问清单（deploy_questions.json）的读写和校验。ma.py 与 build_workflows.py 共用。

ma-manifest.json 放在安装目录（独立安装）或本仓库（链接模式）的根目录，不提交：
  version      安装的 workflow 版本
  mode         standalone（复制到安装目录）| link（直接使用源仓库）
  source       安装来源（路径、commit）
  files        独立安装时每个出厂文件的 sha256：升级时用来判断用户是否改过
  deployments  每个 workspace 一条：用户对提问清单的回答、ids / profiles 文件名、已部署的版本和 prompt 哈希
"""
import fnmatch
import hashlib
import json
import os

NAME = "ma-manifest.json"
HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(HERE, "deploy_questions.json")
STAGES = ("install", "customize", "redeploy", "upgrade")

# 不随安装复制的内容：本机文件、运行时状态、调研材料、用户的定制
SKIP_DIR_NAMES = {".git", ".claude", "__pycache__", "node_modules"}
SKIP_TOP = {"reports", "research_notes", "custom"}
SKIP_PREFIX = ("kandev/guard_state/", "evaluation/pilot-")
SKIP_FILES = ("*.local.md", "*.local.json", "kandev/kandev_ids*.json", NAME, "*.pyc", "*.new", "*.mine", "*.bak",
              ".conda-env")
GENERATED = ("docs/prompts.md", "kandev/export/*.json")   # 部署时重新生成，升级时直接覆盖

REQUIRED_ROLES = ("pm", "auditor", "developer", "reviewer", "mechanical")
OPTIONAL_ROLES = {"module": "pm", "module_auditor": "auditor", "plan_auditor": "auditor", "intake": "mechanical"}
DISTINCT = (("pm", "auditor"), ("pm", "plan_auditor"), ("module", "module_auditor"), ("developer", "reviewer"))


def norm(path):
    return os.path.abspath(os.path.expanduser(path)).replace("\\", "/")


def load(root):
    p = os.path.join(root, NAME)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def save(root, m):
    with open(os.path.join(root, NAME), "w", encoding="utf-8", newline="\n") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
        f.write("\n")


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


def check_profiles(p):
    problems = []
    if not isinstance(p, dict):
        return ["profiles 必须是 {角色: agent profile id} 的对象"]
    missing = [r for r in REQUIRED_ROLES if not p.get(r) or "<" in str(p.get(r))]
    if missing:
        problems.append(f"profiles 缺少必填角色或还是占位：{missing}")
    unknown = set(p) - set(REQUIRED_ROLES) - set(OPTIONAL_ROLES)
    if unknown:
        problems.append(f"profiles 中有不认识的角色：{sorted(unknown)}")
    full = dict(p)
    for role, fallback in OPTIONAL_ROLES.items():
        full.setdefault(role, full.get(fallback))
    for a, b in DISTINCT:
        if full.get(a) and full.get(a) == full.get(b):
            problems.append(f"profiles 的 {a} 与 {b} 必须是不同的 profile")
    return problems


def validate(answers, stage="install"):
    """按提问清单校验答案。返回 (补全了推荐值的答案, 问题列表)。"""
    out, problems = dict(answers), []
    custom = answers.get("setup_style") == "custom"
    for q in questions(stage):
        key, has = q["key"], q["key"] in answers and answers[q["key"]] not in (None, "")
        if not has:
            if q["ask"] == "always" or (custom and "recommended" not in q):
                problems.append(f"{key}：必须向用户确认——{q['question']}")
                continue
            if custom:
                problems.append(f"{key}：用户选了自定义，这一项也要问——{q['question']}（推荐：{q.get('recommended')}）")
                continue
            out[key] = q.get("recommended")
            continue
        val = answers[key]
        if q.get("type") == "list":
            bad = [v for v in (val if isinstance(val, list) else [val]) if v not in q.get("options", [])]
            if bad or not isinstance(val, list):
                problems.append(f"{key}：应为列表，可选值 {q.get('options')}，收到 {val!r}")
        elif q.get("options") and val not in q["options"]:
            problems.append(f"{key}：可选值 {q['options']}，收到 {val!r}")
    if stage == "install" and "profiles" in answers:
        problems += check_profiles(answers["profiles"])
    return out, problems


def deployment(m, workspace):
    return (m or {}).get("deployments", {}).get(workspace)


def missing_answers(root, workspace):
    """workspace 的部署还缺哪些必问项的答案（空列表 = 可以部署）。"""
    dep = deployment(load(root), workspace)
    if not dep:
        return [f"{q['key']}：{q['question']}" for q in questions("install") if q["ask"] == "always"]
    return validate(dep.get("answers", {}), "install")[1]
