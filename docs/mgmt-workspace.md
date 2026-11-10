# 管理 workspace 构造（抗压缩版）

> 配套 [workflow.md](workflow.md)。可直接复制的模板在 `mgmt-template/`，消息格式在 `mgmt-template/protocol/message.md`，各步骤的 prompt 在 [prompts.md](prompts.md)。

## 1. 目标

无论 agent 在哪个时刻被压缩、重置或重启，都能在 **3 次以内的文件读取**中恢复以下 4 件事：

1. 我是谁（scope、角色）
2. 我正在做什么（当前目标）
3. 下一步做什么
4. 我在等谁、等什么

恢复过程**不依赖对话历史**。对话历史被压缩后不可靠，而且读起来很贵。

---

## 2. 抗压缩的 3 条硬规则

| # | 规则 | 做法 | 防止什么 |
|---|---|---|---|
| R1 | **先写后做** | 任何有外部效果的动作（`create_task`、发消息、`move_task`、`step_complete`），执行前先在 NOW 的「未确认的意图」登记，执行后删除这条并写 journal | 被压缩在动作前后时，不知道这个动作做没做 |
| R2 | **每轮结束前落盘** | 一轮结束前必须刷新 NOW | 被压缩时最多丢一轮的过程，不丢状态 |
| R3 | **恢复只读文件** | 恢复时只读 README → 角色卡 → 自己的 NOW | 依赖对话摘要导致的偏差，以及重复调查 |

R1 的配套机制是**幂等**：
- `create_task_kandev` 一律带 `external_id`（模块用 `mod-<模块>`，开发任务用任务 ID）。恢复时如果看到未确认的创建意图，用相同的 `external_id` 重新调用即可，不会重复建任务。
- 消息带唯一的 `id`，接收方按 id 去重。
- `move_task_kandev` 和 `step_complete_kandev` 重做之前，先确认任务当前所在的步骤。这是检查自己动作的结果，不属于"查询别人"。

---

## 3. 恢复协议（写进 README 和每个 workflow prompt）

```
1. 从任务描述的 [TASK v1] 头确认自己的 scope 和 mgmt_root
2. 读 <mgmt_root>/roles/<角色>.md
3. 读自己的 NOW
   - 管理类：<mgmt_root>/agents/<scope>/NOW.md
   - 开发：Kandev 任务文档 now
   - 审核、守护：没有 NOW，直接从头开始（这两类工作本身是幂等的）
4. 处理「未确认的意图」：用相同幂等键重做，或确认已完成后删除
5. 处理「等待中」：看对话里有没有回复；超时则按消息协议重发或升级
6. 从「下一步」第 1 条继续
```

---

## 4. 目录结构与写者

```
<project>-mgmt/                         放在开发 worktree 之外
├─ README.md                 地图 + 恢复协议                 PM（初始化后基本不改）
├─ roles/                    角色卡（全量规则）              只读（从模板复制）
│   ├─ pm.md
│   ├─ module.md
│   ├─ developer.md
│   ├─ reviewer.md
│   └─ guard.md
├─ protocol/
│   └─ message.md            消息与交接格式                  只读（从模板复制）
├─ tools/                    check_owns / quota / mgmt_precommit  只读（从模板复制）
├─ project/
│   ├─ charter.md            需求原文 R-n、目标、范围、模块、PA  PM
│   ├─ attention.md          需要用户处理的事（附推荐答案）  PM
│   ├─ conventions.md        协作规范、约束清单              PM
│   ├─ environment.md        环境基线、命令、冒烟测试        PM
│   ├─ registry.json         担当表（谁负责什么、task id）   PM
│   ├─ status.json           全局状态快照                    PM
│   ├─ final-report.md       项目验收报告                    项目验收步骤（auditor）；「收尾」节由收尾合并步骤写
│   └─ decisions/
│       └─ ADR-0001-*.md     跨模块决策，一事一文件          PM
├─ agents/                   管理类 agent 的私有状态
│   ├─ pm/
│   │   ├─ NOW.md                                             PM
│   │   └─ journal.md                                         PM
│   ├─ mod-<模块>/
│   │   ├─ NOW.md                                             该模块 agent
│   │   └─ journal.md                                         该模块 agent
│   └─ guard/
│       ├─ journal.md                                         守护
│       └─ stage.md          现在在等谁                      kandev/stage.py 生成（去重状态在架构仓库的 kandev/guard_state/）
├─ modules/<模块>/
│   ├─ spec.md               模块目标 + 模块验收标准         该模块 agent
│   ├─ interfaces.md         接口契约（对外 + 任务之间）      该模块 agent
│   ├─ tasks.json            开发任务清单                    该模块 agent
│   └─ acceptance.md         验收记录（只追加）              该模块 agent
├─ evidence/<任务id>/        界面截图                        该任务的开发
└─ quota/ledger.json         额度账本                        只由 tools/quota.py 写
```

开发和审核**不写管理目录**（截图 `evidence/<任务id>/` 和额度账本由脚本写入除外）。它们的状态和交付物放在**各自 Kandev 任务的任务文档**里：

| 任务文档 | 写者 | 读者 | 用途 | 模板 |
|---|---|---|---|---|
| `now` | 开发 | 开发自己 | 私有检查点 | `mgmt-template/task-docs/now.md` |
| `report` | 开发 | 审核、模块 agent | 上报契约 | `mgmt-template/task-docs/report.md` |
| `review` | 审核 | 开发、模块 agent | 审核结论 | `mgmt-template/task-docs/review.md` |
| `charter-review` | 立项评审（pm 任务中） | pm | 立项评审记录 | 无固定模板：逐条结论、阻塞问题、建议 |

任务契约本身写在**任务描述**里（`[TASK v1]` 头加契约正文），由创建者写入，之后只读。这样不需要跨任务写文档。

**单写者规则**：每个文件只有一个写者。想改别人的文件，就给它的担当者发消息，由对方修改。

---

## 5. 写入时机

| 时机 | 写什么 |
|---|---|
| 进入步骤 | NOW：step、entry、当前目标、下一步 |
| 外部动作前 | NOW「未确认的意图」加一行 |
| 外部动作后 | 删掉这条意图；journal 记一行 |
| 发出需要回复的消息 | NOW「等待中」加一行（发出前登记，同样遵守 R1） |
| 收到消息并处理后 | journal 记一行；计划有变才改 NOW |
| 一轮结束前 | 刷新 NOW 全文 |
| 步骤结束 | 把成果汇总进对应的担当文件（status.json、tasks.json、acceptance.md），NOW 改写为下一步骤的内容 |

---

## 6. 大小上限（保证读得快）

| 文件 | 上限 | 超出时 |
|---|---|---|
| README.md | 60 行 | 细节移到 roles 或 project |
| roles/*.md | 80 行 | — |
| NOW.md / now | 40 行 | 删除已完成的细节，只留指针 |
| journal.md | 恢复时只读最后 30 行 | 超过 200 行时，把旧内容滚动到 `journal-<n>.md` |
| spec.md / interfaces.md | 150 行 | 按子域拆分文件 |
| ADR | 40 行 | — |
| 消息正文 | 30 行 | 改用 refs 指向文件 |

---

## 7. 格式约定

- **机器要判断的状态用 JSON**（registry.json、status.json、tasks.json）。字段固定，只允许修改"状态类字段"（见第 8 节）。参考 Anthropic 的经验：模型乱改 JSON 的倾向比乱改 Markdown 小。
- **叙述内容用 Markdown，标题固定**。agent 靠标题定位内容，**不准改标题名**；没有内容的节写"无"，不要删掉。
- **日志只追加**，一行一个事件，不回头修改：`YYYY-MM-DD HH:MM | 类型 | 内容 | 指针`。
- **时间戳取自系统时钟**，不要推断。
- **管理目录如果用 git 管理，只 `git add` 自己担当的路径**。单写者规则管的是文件，`git add -A` 会把别人的文件一起提交。用 `tools/mgmt_precommit.py` 钩子强制：提交时用 `MGMT_SCOPE` 声明 scope，越界的文件被拒绝。
- **结论如实**：验收类结论只用 `pass` / `fail` / `unverified(原因)`；部分完成写 `partial`。
- **临时资源登记**：临时目录、worktree、后台进程、端口写进自己的 NOW「注意」节，用完清理；留给终审的写进 final-report「临时资源」，由收尾合并步骤清理。
- **引用用路径或 ID**（`modules/auth/interfaces.md#login`、`ADR-0003`、`M-mod.auth-261109-102000`），不复制原文。
- **不记录原始代码**，只记录路径、命令和结论。
- 时间格式统一为 `YYYY-MM-DD HH:MM`，用本地时区。

ID 规则：

| 对象 | 格式 | 例 |
|---|---|---|
| scope | `pm` / `mod:<模块>` / `dev:<任务id>` / `rev:<任务id>` / `guard` | `dev:auth-02` |
| 模块 | 小写英文 | `auth` |
| 开发任务 | `<模块>-<两位序号>` | `auth-02` |
| 需求（原文摘录） | `R-<n>` | `R-4` |
| 待用户确认 / 无法验证 | `Q-<n>` / `U-<n>` | `Q-2` |
| 项目验收标准 | `PA-<n>` | `PA-3` |
| 模块验收标准 | `MA-<n>` | `MA-1` |
| 任务验收标准 | `AC-<n>` | `AC-2` |
| 消息 | `M-<scope，冒号换成点>-<YYMMDD-HHMMSS>` | `M-dev.auth-02-261109-142530` |
| ADR | `ADR-<4位序号>-<短标题>` | `ADR-0003-token-format` |

---

## 8. JSON 字段说明

### registry.json（担当表，PM 写）

| 字段 | 说明 | 可改 |
|---|---|---|
| `project`、`mgmt_root`、`repo`、`base_branch` | 项目常量 | 初始化后不改 |
| `agents[].scope` | 唯一标识 | 否 |
| `agents[].role` | `pm` / `module` / `guard` | 否 |
| `agents[].kandev_task_id` | 创建后回填 | 是 |
| `agents[].owns` | 担当范围（文件或职责），用于"问谁" | 需 ADR |
| `agents[].branch` | 模块分支 | 否 |
| `agents[].status` | `active` / `done` / `failed` | 是 |

开发任务的担当关系不进 registry，记在对应模块的 `tasks.json`。

### status.json（全局快照，PM 写）

| 字段 | 说明 |
|---|---|
| `phase` | `planning` / `baseline` / `dispatch` / `developing` / `project-acceptance` / `final-review` / `done` |
| `modules[]` | `name`、`kandev_task_id`、`status`（`blocked` / `planning` / `developing` / `accepting` / `reported` / `done` / `failed`）、`done`、`total`、`last_report`（消息 id）、`blocked_reason` |
| `open_escalations[]` | 待处理的升级：`msg`、`from`、`topic`、`since` |
| `open_decisions[]` | 讨论中的 ADR 编号 |

### tasks.json（模块任务清单，模块 agent 写）

| 字段 | 说明 | 可改 |
|---|---|---|
| `id`、`title` | 任务标识 | 否 |
| `owns` | 这个任务允许修改的路径，也就是它的担当范围 | 需重新规划 |
| `blocked_by` | 前置任务 id | 需重新规划 |
| `acceptance` | AC 列表，每条写 `covers: MA-n` | 需重新规划，并在 acceptance.md 记一笔 |
| `refs` | 需求出处（charter 的 R 编号） | 需重新规划 |
| `ui` | 是否改动界面；true 时 report 要附截图 | 需重新规划 |
| `kandev_task_id` | 创建后回填 | 是 |
| `status` | `planned` / `creating` / `held`（在「待开发」等前置）/ `todo` / `merged` / `dropped` / `failed` | 是 |
| `passes` | 模块验收时由模块 agent 置为 true | 是 |
| `review_rounds` | 审核轮数 | 是 |
| `note` | 一行备注 | 是 |

---

## 9. 初始化顺序

1. **用户**：在 Kandev 创建项目管理任务，任务描述写 `[TASK v1]` 头（含 `mgmt_root`、`mgmt_template`、`repo`）。
2. **PM（立项规划）**：发现 `mgmt_root` 不存在 → 从 `mgmt-template/` 整体复制 → 回填 registry.json 中的常量和自己的 task id。
3. **PM（模块下发）**：每创建一个模块任务，就在 registry.json 里加一个条目。
4. **模块 agent（模块规划）**：复制 `agents/_template/` → `agents/mod-<模块>/`，复制 `modules/_template/` → `modules/<模块>/`。
5. 模板目录 `agents/_template/`、`modules/_template/` 留在原处不改，作为后续复制的来源。

---

## 10. 设计取舍

- **立项规划不开 plan mode**：Claude Code 的 plan mode 不能写文件，而立项规划的产出就是管理文件。用户审核放在「立项确认」步骤。
- **开发和审核的状态放在 Kandev 任务文档里，不放管理目录**：管理目录在 worktree 外面，而开发 agent 只需要自己的那份状态。
- **谁担当就问谁**：不让 agent 先翻对话记录、读代码去找答案，而是查担当表后直接问担当者（详见 `protocol/message.md` 第 1 节）。
