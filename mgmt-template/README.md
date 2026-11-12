# <project> 管理 workspace

> 地图 + 恢复协议，≤60 行。**任何 agent 恢复上下文时先读这一份。**

## 恢复协议（任何 agent、任何时候）

1. 从任务描述的 `[TASK v1]` 头确认自己的 scope。
2. 读 `roles/<角色>.md`。
3. 读自己的 NOW：
   - 管理类：`agents/<scope>/NOW.md`（scope 里的冒号换成横线，例如 `mod:auth` 对应 `agents/mod-auth/`）
   - 开发：Kandev 任务文档 `now`
   - 审核、评审、模块验收、守护：没有 NOW，直接从头开始
4. 处理「未确认的意图」：用相同的幂等键重做，或确认已完成后删除。
5. 处理「等待中」：看对话里有没有回复；超时则按 `protocol/message.md` 重发或升级。
6. 从「下一步」第 1 条继续。

**不要**为了恢复去翻对话历史或别人的 NOW。理解问题需要时，读仓库代码、文档、运行产品都可以。

## 目录

| 路径 | 内容 | 写者 |
|---|---|---|
| `roles/` | 角色卡 | 只读 |
| `protocol/message.md` | 消息与交接格式 | 只读 |
| `project/charter.md` | 需求原文（R-n）、目标、范围、模块、模块边界（B-n）、项目验收标准 | pm |
| `project/attention.md` | 需要用户处理的事：待确认的问题（附推荐答案）、无法验证的项 | pm |
| `project/feedback.md` | 用户在门禁中的意见原话及去向 | pm |
| `project/conventions.md` | 协作规范 | pm |
| `project/environment.md` | 环境、命令、冒烟测试、合并门禁 | baseline 模块 agent（mod:baseline） |
| `project/registry.json` | 担当表：谁负责什么 | pm |
| `project/status.json` | 全局状态 | pm |
| `project/final-report.md` | 项目验收报告 | pm |
| `project/decisions/` | ADR | pm |
| `agents/<scope>/` | NOW.md、journal.md | 本人 |
| `agents/guard/stage.md` | 现在在等谁（门禁、权限请求、卡住的任务） | `kandev/stage.py` 生成 |
| `modules/<模块>/` | spec、interfaces、tasks.json | 该模块 agent |
| `modules/<模块>/acceptance.md` | 模块验收记录与修复项 | 该模块的验收者（mod-audit:<模块>） |
| `evidence/<任务id>/` | 界面截图 | 该任务的开发 |
| `quota/ledger.json` | 额度账本 | 只由 `tools/quota.py` 写 |
| `tools/` | check_owns、check_tasks、quota、mgmt_precommit 脚本 | 只读 |
| `agents/_template/`、`modules/_template/` | 复制源 | 不改 |

## 任务文档存储

任务文档 `now`、`report`、`review`、`charter-review` 是对应 Kandev 任务计划中的命名章节：`## task-doc: <名称>`。先读完整计划及版本；无计划则创建，已有则精确修改所属章节或追加新章节，保留其他角色章节及用户内容。冲突重读合并，分片不得覆盖整份计划。保存后读回；refs / handoff 包含 task_id 与章节名。开发写 now/report，审核写 review，立项评审写 charter-review；模块通过子任务 task_id 读取交付章节。`task-docs/` 仍是章节内容模板。

## 单写者

每个文件只有上表写明的写者。想改别人的文件，就给它的担当者发消息。

## 找担当者（谁担当就问谁）

1. 模块级、项目级：查 `project/registry.json` 的 `owns`。
2. 任务级：查 `modules/<模块>/tasks.json` 的 `owns`。
3. 查不到：问自己的上级"这归谁"，不要猜。

## 当前阶段

见 `project/status.json` 的 `phase`。运行模式（attended / unattended）见 pm 任务描述的 `[TASK v1]` 头。

## 记录约定

时间戳取自系统时钟；管理目录如果用 git 管理，只 `git add` 自己担当的路径，提交时设置 `MGMT_SCOPE`（钩子见 `tools/mgmt_precommit.py`）；临时资源登记到自己的 NOW，用完清理。

需要用户处理的事看 `project/attention.md`；系统现在在等谁看 `agents/guard/stage.md`。
