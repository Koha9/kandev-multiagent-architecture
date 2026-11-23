# <project> 管理 workspace

> 本目录的地图，≤60 行。**任何 agent 恢复上下文时先读这一份。** 流程、参数和判定标准以步骤 prompt 为准。

## 目录

| 路径 | 内容 | 写者 |
|---|---|---|
| `roles/` | 角色卡：pm、module、module-auditor、developer、reviewer、guard | 只读 |
| `protocol/message.md` | 消息（KMSG v1）与交接（HANDOFF v1）格式 | 只读 |
| `task-docs/` | 任务文档 `now`、`report`、`review` 的内容模板（任务文档本身存在 Kandev 任务计划里，见下） | 只读 |
| `project/charter.md` | 需求原文（R-n）、产品意图、范围、模块清单、模块边界（B-n）、项目验收标准（PA-n） | pm |
| `project/attention.md` | 需要用户处理的事（待确认的问题附推荐答案、无法验证的项），以及 pm 按【遗留分诊】自己处理的记录（自修清单、待核对、已自行处理） | pm |
| `project/workflow-feedback.md` | 多 agent 工作流本身的问题（给工作流维护者，不问用户） | pm |
| `project/feedback.md` | 用户在门禁中的意见原话及去向 | pm |
| `project/conventions.md` | 协作规范、约束清单 | pm |
| `project/environment.md` | 环境、命令、冒烟测试、结合测试、共享文件、合并方式、合并门禁、约束落实、截图 | baseline 模块 agent（mod:baseline 或 mod:baseline-fix-<n>） |
| `project/registry.json` | 担当表：谁负责什么、各模块的当前分支、pm 的会话 id | pm |
| `project/status.json` | 全局状态：阶段、各模块状态、修复轮数、待处理的升级 | pm（收尾合并步骤以 pm 的 scope 写 phase） |
| `project/final-report.md` | 项目验收报告 | 项目验收者（audit）；「收尾」节由收尾合并步骤写 |
| `project/decisions/` | ADR（`ADR-0000-template.md` 是模板） | pm |
| `agents/<scope>/` | NOW.md、journal.md（scope 里的冒号换成横线：`mod:auth` → `agents/mod-auth/`） | 本人 |
| `agents/guard/` | `stage.md`：现在在等谁（门禁、权限请求、卡住的任务）；`journal.md`：守护的记录 | `stage.md` 由守护脚本生成，`journal.md` 由守护写 |
| `modules/<模块>/` | spec.md、interfaces.md、tasks.json（修复模块用自己的 `modules/<模块>-fix-<n>/`） | 该模块 agent |
| `modules/<模块>/acceptance.md` | 模块验收记录与修复项 | 该模块的验收者（mod-audit:<模块>） |
| `evidence/<任务id>/` | 界面截图 | 该任务的开发 |
| `quota/ledger.json` | 额度账本 | 只由 `tools/quota.py` 写 |
| `tools/` | check_owns、check_tasks、quota、mgmt_precommit 脚本 | 只读 |
| `agents/_template/`、`modules/_template/` | 复制源 | 不改 |
| `VERSION` | 本目录来自哪个版本的模板 | 只读 |

## 恢复协议

步骤以步骤 prompt 的【恢复协议】为准。prompt 里没有写的：
- NOW 在哪：管理类角色是 `agents/<scope>/NOW.md`；开发是 Kandev 任务文档 `now`；审核、评审、模块验收、合并、守护没有 NOW，直接从头开始。
- 「未确认的意图」先查实际状态：已生效的删除，没有生效的用相同的幂等键重做。「等待中」到期没有回复的，按 `protocol/message.md` 重发或升级。journal 只读最后 30 行。
- **不要**为了恢复去翻对话历史或别人的 NOW。理解问题需要时，读仓库代码、文档、运行产品都可以。

## 任务文档

`now`、`report`、`review`、`charter-review`、`intake` 是 Kandev 任务计划中的章节 `## task-doc: <名称>`，不在本目录里；读写方法见步骤 prompt【任务文档】。开发写 now / report，审核写 review，立项评审写 charter-review，「接收」写 intake。

## 单写者与找担当者

每个文件只有上表写明的写者；想改别人的文件，给它的担当者发消息。找担当者：模块级、项目级查 `project/registry.json` 的 `owns`，任务级查 `modules/<模块>/tasks.json` 的 `owns`；查不到就问上级"这归谁"，不要猜。

## 现在的状态看哪里

当前阶段：`project/status.json` 的 `phase`；运行模式：pm 任务描述的 `[TASK v1]` 头；需要用户处理的事：`project/attention.md`；系统现在在等谁：`agents/guard/stage.md`。时间戳、临时资源、管理目录的 git 提交见步骤 prompt【通用规则】（提交钩子是 `tools/mgmt_precommit.py`）。
