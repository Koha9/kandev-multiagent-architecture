# <project> 管理 workspace

> 地图 + 恢复协议，≤60 行。**任何 agent 恢复上下文时先读这一份。**

## 恢复协议（任何 agent、任何时候）

1. 从任务描述的 `[TASK v1]` 头确认自己的 scope。
2. 读 `roles/<角色>.md`。
3. 读自己的 NOW：
   - 管理类：`agents/<scope>/NOW.md`（scope 里的冒号换成横线，例如 `mod:auth` 对应 `agents/mod-auth/`）
   - 开发：Kandev 任务文档 `now`
   - 审核、守护：没有 NOW，直接从头开始
4. 处理「未确认的意图」：用相同的幂等键重做，或确认已完成后删除。
5. 处理「等待中」：看对话里有没有回复；超时则按 `protocol/message.md` 重发或升级。
6. 从「下一步」第 1 条继续。

**不要**为了恢复去翻对话历史、读别人的文件或代码。

## 目录

| 路径 | 内容 | 写者 |
|---|---|---|
| `roles/` | 角色卡 | 只读 |
| `protocol/message.md` | 消息与交接格式 | 只读 |
| `project/charter.md` | 需求原文（R-n）、目标、范围、模块、项目验收标准 | pm |
| `project/attention.md` | 需要用户处理的事：待确认的问题（附推荐答案）、无法验证的项 | pm |
| `project/conventions.md` | 协作规范 | pm |
| `project/environment.md` | 环境、命令、冒烟测试 | pm |
| `project/registry.json` | 担当表：谁负责什么 | pm |
| `project/status.json` | 全局状态 | pm |
| `project/final-report.md` | 项目验收报告 | pm |
| `project/decisions/` | ADR | pm |
| `agents/<scope>/` | NOW.md、journal.md | 本人 |
| `agents/guard/stage.md` | 现在在等谁（门禁、权限请求、卡住的任务） | `kandev/stage.py` 生成 |
| `modules/<模块>/` | spec、interfaces、tasks.json、acceptance | 该模块 agent |
| `evidence/<任务id>/` | 界面截图 | 该任务的开发 |
| `quota/ledger.json` | 额度账本 | 只由 `tools/quota.py` 写 |
| `tools/` | check_owns、quota、mgmt_precommit 脚本 | 只读 |
| `agents/_template/`、`modules/_template/` | 复制源 | 不改 |

## 单写者

每个文件只有上表写明的写者。想改别人的文件，就给它的担当者发消息。

## 找担当者（谁担当就问谁）

1. 模块级、项目级：查 `project/registry.json` 的 `owns`。
2. 任务级：查 `modules/<模块>/tasks.json` 的 `owns`。
3. 查不到：问自己的上级"这归谁"，不要猜，也不要自己去查。

## 当前阶段

见 `project/status.json` 的 `phase`。运行模式（attended / unattended）见 pm 任务描述的 `[TASK v1]` 头。

## 记录约定

时间戳取自系统时钟；管理目录如果用 git 管理，只 `git add` 自己担当的路径，提交时设置 `MGMT_SCOPE`（钩子见 `tools/mgmt_precommit.py`）；临时资源登记到自己的 NOW，用完清理。

需要用户处理的事看 `project/attention.md`；系统现在在等谁看 `agents/guard/stage.md`。
