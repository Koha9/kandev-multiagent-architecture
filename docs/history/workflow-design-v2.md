> **已被 [docs/workflow.md](../workflow.md)取代**，本文件仅作为设计演进记录保留。

# 多 Agent 开发 Workflow v2（优化稿）

> 基于 `workflow-draft-v1.md` 修改，依据见 `reports/多Agent协作与Kandev工作流调研.md`。
> Kandev 机制以 v0.99.1（commit 52309e6）为准。标 **[待验证]** 的地方需要在你的 Kandev 上实测。

---

## 0. 相对原稿的主要改动

| 原稿 | 改动 | 理由 |
|---|---|---|
| 管理流程是一个 workflow，同时包含规划、分发、按模块验收 | 拆成 **项目管理 / 模块管理 / 开发** 三个 workflow | Kandev 子任务只有一层；"规划者 → 子规划者 → 执行者"是 Cursor 等案例里跑通的拓扑 |
| 有一个独立的"task 分发 agent" | **取消**，分发并入模块管理的"模块规划"步骤；先后顺序交给 `blocked_by`，并发量交给 WIP 上限 | 少一次交接、少一个会话；排序和排队用 Kandev 的确定性机制，不需要 LLM |
| 审核之后上报给"xxx" | 三种结论分别对应：①退回开发 ②进入"等待决策"并上报模块管理 ③发完成信号 | Kandev 没有条件分支，路由要由 agent 调用 `move_task_kandev` 或 `step_complete_kandev` 实现 |
| 开发完成后直接进审核 | 开发步骤必须先跑测试，并按**上报契约**写报告，否则不能发完成信号 | 外部判定标准（测试）是所有成功案例的基础；"信息不全"要在源头解决，不能靠事后追问 |
| 验收调查 agent 可以随意找人沟通 | 改为**谁担当就问谁**：查担当表后直接问担当者，不自行翻对话或代码；统一消息格式，并限制轮数 | 防止对话爆炸和重复调查（MAST 统计里最常见的失败是步骤重复） |
| 管理目录未定 | 定为**单写者**目录结构，任务清单用 JSON | 防止并发写冲突；JSON 能被程序检查，模型也较少乱改 |
| 上下文守护：每个 task 一个，或 30 分钟轮询 | **预防为主**：会话短、状态存文件。检测用一个全局守护（定时任务 + 便宜模型），只看结构化信号 | 每个 task 配一个守护会让会话数翻倍；Kandev 的 MCP 目前读不到上下文用量百分比 |

---

## 1. 设计原则（6 条）

1. **单写者**：同一份代码、同一个文件，在同一时刻只有一个 agent 写。并行只发生在相互独立的任务之间，每个任务用独立 worktree。
2. **测试是裁判**：每个任务都必须有机器可判定的完成条件（测试、lint、类型检查）。agent 的自我评价不算数。
3. **评审者上下文干净**：审核 agent 换一个 profile 或重置上下文，只看 diff、验收标准和报告，看不到开发过程。
4. **状态存文件，会话可抛弃**：任何 agent 的会话随时可以重开，重开后读文件即可恢复。
5. **管理者不写代码**：项目管理和模块管理 agent 只做规划、委派、验收和记录。
6. **每个循环都有上限**：退回次数、消息轮数、预算都有硬上限，超出就交给上一级或人。

---

## 2. 整体结构

```
项目管理任务（W1，1 个，根任务）
 ├─ 创建 → 模块管理任务 A（W2，独立根任务，不设 parent）
 │          ├─ 子任务 → 开发任务 A-1（W3，独立 worktree）
 │          ├─ 子任务 → 开发任务 A-2（W3，blocked_by A-1）
 │          └─ ...
 ├─ 创建 → 模块管理任务 B（W2，blocked_by A，如果 B 依赖 A）
 └─ ...
```

- 模块任务**不设 parent**：设了就成了项目任务的子任务，而常规 Kanban 的子任务再建子任务会被降级为兄弟任务。
- 所以模块向项目上报不能靠 `on_children_completed`，改用 `message_task_kandev`（创建模块任务时把项目任务的 UUID 写进它的提示词）。
- **小项目变体**：模块不多（≤3 个）时去掉 W2，项目任务直接创建开发子任务，模块验收改为项目任务里的一个步骤。

### 角色表

| 角色 | 所在位置 | 写权限 | 模型建议 | 上下文策略 |
|---|---|---|---|---|
| 项目管理 agent | W1 任务 | 管理目录的项目级文件 | 最强模型 | 无状态设计，可随时刷新 |
| 模块管理/验收调查 agent | W2 任务（每模块 1 个） | `modules/<模块>/` | 中高档模型 | 规划和验收用不同会话 |
| 开发 agent | W3「开发」步骤 | 只写自己 worktree 里的代码 | 主力编码模型 | 一个任务一个会话 |
| 审核 agent | W3「审核」步骤 | 只写评审结论（不改代码） | **与开发不同**的模型或厂商 | 每次进入都是新会话 |
| 上下文守护 | Kandev 定时 automation | 只能发消息 | 便宜模型 | 每次运行都是新会话 |

---

## 3. W1 项目管理流程

workspace：主仓库（只读为主）+ 管理目录。lifecycle：整个项目从立项到交付。

| # | 步骤 | 做什么 | Kandev 配置要点 |
|---|---|---|---|
| 1 | 立项规划 | 把目标具体化为模块，并为每个模块写验收标准；确定技术栈和规范；写 `project/charter.md`、`conventions.md` | `auto_start_agent`；**不开 plan mode**（plan mode 下不能写文件）；要求完成信号 |
| 2 | 人工确认 | 你审核模块划分和验收标准 | `on_turn_complete` = 不做任何事（人工门禁） |
| 3 | 环境基线 | 配好开发环境和工具；写 `init` 脚本和**冒烟测试**；配置 CI 和 lint；把 `.conda-env`、`.env.local` 等加入 Copy files | 要求完成信号；完成条件是冒烟测试通过 |
| 4 | 模块下发 | 为每个模块调用 `create_task_kandev` 创建 W2 任务，模块之间用 `blocked_by`；用 `external_id` 做幂等键；更新 `status.json` | 要求完成信号 |
| 5 | 调度 | 常驻在这一步。模块上报以消息形式到达，每条消息开启新的一轮：更新 `status.json`，处理升级问题，必要时写决策记录（ADR）。全部模块完成后自己 `move_task_kandev` 到下一步 | `on_turn_complete` = 不做任何事；每一轮只处理一条上报，不重新回顾全部历史 |
| 6 | 项目验收 | 跑全量测试和跨模块集成测试，逐条对照 `project/charter.md` 的验收标准，写最终报告 | 用不同 profile，`reset_agent_context`；要求完成信号 |
| 7 | 人工终审 → 完成 | 你合并到主分支并归档 | 人工门禁 |

要点：
- 立项时**环境基线 = AGENTS.md（≤100～200 行，作为地图）+ 冒烟测试 + CI**。后面所有开发会话都靠这三样快速进入状态。
- 调度步骤的会话会随着上报不断变长，是守护重点关注的对象（见第 8 节）。

---

## 4. W2 模块管理流程（原稿的"task 分发"和"接收上报"）

workspace：模块分支（见第 9 节）+ 管理目录 `modules/<模块>/`。lifecycle：一个模块从拆分到验收上报。

| # | 步骤 | 做什么 | Kandev 配置要点 |
|---|---|---|---|
| 1 | 模块规划 | 读 `project/charter.md` 中本模块的部分，写 `spec.md`、`interfaces.md`、`tasks.json`；为每个开发任务调用 `create_task_kandev`（见下方参数）。不排优先级，靠 `blocked_by` 和 WIP 上限 | 要求完成信号 |
| 2 | 等待开发 | 什么都不做，等子任务全部结束。期间回答子任务的 `ask_parent_question_kandev`，处理审核上报的方向性问题 | `on_turn_complete` = 不做任何事；`on_children_completed` → 移到下一步 |
| 3 | 验收调查 | **第一件事是检查有没有 FAILED 或 CANCELLED 的子任务**，因为"全部结束"不等于"全部成功"。然后做模块级验收：集成测试、接口契约、任务之间是否一致。交付物不清楚时，直接问担当的开发 agent（第 6 节），结果写入 `acceptance.md` | `reset_agent_context` + 自动启动；要求完成信号 |
| 4 | 上报 → 完成 | 通过 `message_task_kandev` 向项目任务发送模块报告（≤20 行，附文件路径），然后发完成信号 | 并入第 3 步的末尾，少开一个会话 |

创建开发子任务时的参数：

```
create_task_kandev(
  parent_id: "self",
  workspace_mode: "new_workspace",   # 并发写者必须用独立 worktree
  autopilot: true,                   # 子任务的问题先问模块 agent（ask_parent_question_kandev）
  workflow_step_id: <W3 开发步骤>,
  blocked_by: [...],
  external_id: "<模块>-<序号>",      # 重复创建不会产生重复任务
)
```

验收不通过时：
- 能定位到具体问题：创建修复子任务，然后 `move_task_kandev` 回到「等待开发」。
- 退回超过 2 次（看 `{step_entry_number}`），或者问题涉及其他模块：上报项目管理，模块保持当前状态等待决策。

验收调查 agent 与审核 agent 的分工（避免重复审）：
- **审核 agent**：单个任务级别。检查 diff 是否符合任务契约和测试。
- **验收调查 agent**：模块级别。检查多个任务合起来是否满足模块验收标准，接口是否一致。**不重新审每个任务的代码。**

---

## 5. W3 开发流程

workspace：任务自己的 worktree（从模块分支切出）。lifecycle：一个任务从接收、开发、审查到完成。

| # | 步骤 | 做什么 | Kandev 配置要点 |
|---|---|---|---|
| 1 | 开发 | 按固定启动协议执行（见下）；完成后按上报契约写报告并发完成信号 | 开发 profile；`auto_start_agent`；要求完成信号 |
| 2 | 审核 | 先**重跑**测试、lint、类型检查；再对照契约逐条核查；按下表三种结论路由 | **不同的 profile**，start policy 设为 `new`（或 `reset_agent_context`）；`auto_start_agent`；要求完成信号 |
| 3 | 等待决策 | 方向性问题在这里等模块 agent 处理 | `on_turn_complete` = 不做任何事 |
| 4 | 合并 / 完成 | 建 PR 合入模块分支（或由模块 agent 在本地合并）；`on_pr_merged` → 完成 | 可选开启 Kandev 的 auto-fix CI |

### 开发 agent 启动协议（写进步骤提示词）

1. 读任务契约（任务的 Plan 或任务文档）以及 `modules/<模块>/interfaces.md`。
2. 跑冒烟测试。失败就先修复或上报，不要在坏的基线上开发。
3. 只做这一个任务，不顺手改别的。
4. 跑测试，按上报契约写报告，然后调用 `step_complete_kandev`。

### 上报契约（开发 → 审核 → 模块）

放进 `step_complete_kandev` 的 `handoff`（≤8KB，只传给下一步），同时用 `write_task_document_kandev` 存一份 `report`（持久保存，供模块 agent 读取）：

```yaml
task: <external_id>
result: done | blocked
changes:            # 改了什么，按文件或模块写，不贴代码
  - path: src/xxx
    summary: ...
tests:
  command: <可直接复制运行的命令>
  result: <通过数/失败数>
acceptance:         # 每条验收标准对应的证据
  - criterion: ...
    evidence: <测试名 / 命令输出摘要>
deviations: []      # 与契约不一致的地方及原因
interface_changes: []  # 对外接口有任何变化都必须写在这里
open_questions: []
```

### 审核结论路由（填上原稿的 xxx）

| 结论 | 判断标准 | 动作 |
|---|---|---|
| ① 小问题 | 局部缺陷、测试漏写、不符合契约但改动范围清楚 | `move_task_kandev` 回到「开发」，`instructions` 写具体问题。开发步骤沿用同一个开发会话，不重新加载上下文 |
| ② 方向性/关联性问题 | 契约本身有问题、需要改接口、影响其他任务或模块 | 把结论写进任务文档 `review`，用 `message_task_kandev` 向模块任务发 ESCALATE，然后把任务移到「等待决策」 |
| ③ 通过 | 测试全绿，验收标准逐条有证据 | `step_complete_kandev`，进入合并 |

- **退回上限**：「开发」的 `{step_entry_number}` ≥ 3 时，第 ① 种结论也按第 ② 种处理，防止开发和审核之间无限来回。
- 审核关注的是契约、测试、明显的缺陷和安全问题。原稿"不干预内部实现"保留，也就是不提风格偏好；但发现 bug 必须指出。
- 评审结论不要写在 diff 评论里，那只存在浏览器的 sessionStorage 中。

---

## 6. Agent 间通信协议（原稿未定项 1）

> 完整定义见 `mgmt-template/protocol/message.md`（KMSG v1）。下面只列要点。

核心思路有两条：一是**"信息不全"主要靠上报契约在源头解决**；二是剩下的问题按**谁担当就问谁**处理。原先"先自己翻对话、读代码"的询问阶梯已取消。

- 查担当表（`registry.json` 和 `tasks.json` 的 `owns`），直接问担当者。不翻别人的对话记录，不读别人的代码去推测。
- 不用问、可以直接读的只有：自己的状态文件、上级下发的契约、别人交付给你的交付物（report、review）、公共规范。
- 自己本职内的验证（重跑测试）不算查询。
- 不知道该问谁，就问上级；被问到不归自己的事，转介给担当者，不替别人去查。
- 消息统一用 `[KMSG v1]` 信封：id / type / from / to / reply / reply_to / due / refs。
- 一条消息一个主题，最多 3 个问题，同一主题最多来回 2 轮，超时重发一次后升级。
- 跨模块的**事实**可以直接问；跨模块的**决策**必须由项目管理写成 ADR 拍板。

---

## 7. 管理目录结构与格式（原稿未定项 2）

> **已被 `docs/mgmt-workspace.md`（抗压缩版构造）和 `mgmt-template/`（各文档模板）取代，以那两处为准。** 下面是初版草案，保留作对照。

位置建议：**放在开发 worktree 之外**，例如 `D:\WorkSpace\<项目>-mgmt\`（可以单独建一个 git 仓库做版本记录），在 workflow 级提示词里写明绝对路径。
如果放在主仓库内，各个 worktree 看到的只是切分支那一刻的快照，多个 agent 同时提交还会冲突。**[待验证]** worktree 执行器下的 agent 能否读写仓库外的绝对路径。Docker 执行器下不行。

```
<项目>-mgmt/
├─ README.md              # 地图，≤100 行：目录说明 + 当前阶段
├─ project.md             # 目标、模块清单、项目级验收标准         写：项目管理
├─ conventions.md         # 开发规范（或链接到 AGENTS.md）          写：项目管理
├─ status.json            # 全局状态快照                            写：项目管理
├─ decisions/
│   └─ ADR-0001-<标题>.md # 跨模块决策，一事一文件                  写：项目管理
├─ modules/<模块>/
│   ├─ spec.md            # 模块目标 + 验收标准                     写：该模块 agent
│   ├─ interfaces.md      # 对外接口契约                            写：该模块 agent
│   ├─ tasks.json         # 任务清单                                写：该模块 agent
│   └─ log.md             # 验收调查记录，只追加，不记录原始代码    写：该模块 agent
└─ guard/
    └─ events.md          # 守护发现和处理记录，只追加              写：守护
```

**单写者规则**：每个文件只有表中写明的那个角色能写，其他角色只读。开发 agent 和审核 agent 不写管理目录，它们的产出放在 Kandev 任务文档里，由模块 agent 汇总进来。

`tasks.json`（参考 Anthropic 的功能清单：agent 只能修改状态类字段）：

```json
{
  "module": "auth",
  "tasks": [
    {
      "id": "auth-01",
      "kandev_task_id": "<uuid>",
      "title": "登录接口",
      "blocked_by": [],
      "acceptance": ["POST /login 返回 token", "错误密码返回 401"],
      "status": "todo | doing | review | blocked | done | failed",
      "passes": false,
      "review_rounds": 0
    }
  ]
}
```

`status.json`：

```json
{
  "phase": "开发中",
  "modules": [
    {"name": "auth", "kandev_task_id": "<uuid>", "status": "doing", "done": 3, "total": 5, "blocked_reason": null}
  ],
  "open_decisions": ["ADR-0003"]
}
```

`log.md` 每条记录的格式：

```
## 2026-11-09 auth-02 验收
- 结论：通过 / 退回 / 升级
- 依据：<测试命令与结果、对照的验收标准>
- 发现：...
- 问答：Q-auth-03 → 结论一句话
```

---

## 8. 上下文守护（原稿第三部分）

### 8.1 先预防（不需要守护就能省大部分 token）

- **会话短**：一个开发任务的规模控制在一个会话内能完成；粗略标准是改动集中在少数文件、只有一个明确的验收点。太大就在模块规划时拆开。
- **步骤边界换会话**：审核每次都开新会话；验收调查进入时 `reset_agent_context`。
- **状态存文件**：跨步骤的信息走 `handoff`、任务文档和管理目录，不依赖对话历史。
- **常驻上下文小**：AGENTS.md ≤100～200 行；workflow 级提示词短而稳定，**不放时间戳**，以保持 prompt cache 命中；Kandev 的 Configuration 工具包保持关闭，减少工具定义占用的 token。
- agent CLI 自带的自动压缩（例如 Claude Code 的 auto-compact）作为最后一道保险，但不要依赖它：压缩后质量会下降。

### 8.2 再检测：怎么判断"过长"

Kandev 后端会记录每个会话的 `context_window_used` 和 `size`，界面上能看到。但 **v0.99.1 的 MCP 工具不返回这项数据**（在源码中未找到）。因此守护 agent 只能看替代信号：

| 信号 | 阈值（初始值，试点后调整） | 来源 |
|---|---|---|
| 同一步骤停留时间长且没有完成信号 | > 60 分钟 | `list_tasks_kandev` |
| 审核退回次数 | 「开发」的 `step_entry_number` ≥ 3 | 任务状态和 `tasks.json` |
| 管理任务处理的上报条数（调度、等待开发步骤） | 自上次刷新后 > 15 条 | `get_task_conversation_kandev` 的消息数 |
| 上下文用量（如果能读到） | > 60% 预警，> 75% 处理 | 界面，或通过 Kandev API 自写脚本 **[待验证]** |

60% 这个阈值的依据：实践报告称上下文填充约 60% 后质量开始下降（Yegge 的 Gas Town）；Chroma 的测试也表明输入越长效果越差。

### 8.3 位置与触发方式（回答原稿的两个问号）

- **全局只设一个守护，不给每个 task 配一个**。每个 task 一个守护会让会话数翻倍，而且守护自己也会消耗上下文。
- 实现方式：Kandev automation，schedule 触发（cron，**每 20～30 分钟**），目标是隐藏的 automation run，用便宜模型。
- 守护只读结构化列表，判断后发消息，**自己不做压缩或修复**。没有发现异常就直接结束，几乎不花 token。
- 注意：automation 默认并发数为 1；运行结束后会停在 `WAITING_FOR_INPUT`。**[待验证]** 下一次定时触发是否会被它挡住。

### 8.4 处理流程

**开发流程中的任务：**
1. 守护 → 用 `message_task_kandev` 通知该任务所属的模块任务（附上信号和数值）。
2. 模块 agent 判断原因：
   - **会话太长，但任务本身合理**：让开发 agent 把检查点写进任务文档（做了什么、还剩什么），然后 `move_task_kandev` 回到「开发」并带上 `reset_context`。新会话读检查点继续。
   - **任务太大或方向有问题**：`stop_task_kandev` 停掉它，拆成更小的子任务（`blocked_by` 接到原来的位置），在 `tasks.json` 里标记原任务 `failed` 并写明原因。
   - **审核反复退回**：按审核结论 ② 升级处理。

**管理流程（项目或模块任务）本身：**
- 管理 agent 按**无状态**设计，所有状态都在管理目录里，因此"压缩"就等于刷新会话。
- 流程：守护通知该管理任务 → 它在当前这一轮里把未写入文件的状态补写完整 → 调用 `move_task_kandev` 移回当前步骤，并带上 `reset_context`。新会话先读 `README.md` 和 `status.json`，然后继续。**[待验证]** Kandev 是否允许移到当前步骤；如果不允许，就设一个「刷新」中转步骤，进入后立即移回原步骤。
- 如果项目管理任务连刷新后也很快变长，说明模块划分太粗，应在 W1 里把模块拆得更细。
- 项目根任务的刷新失败时，通过 Kandev 通知（Apprise/webhook）交给你处理。

---

## 9. 分支与合并

```
main ← 模块分支 mod/<模块> ← 开发分支（每个开发任务一个 worktree）
```

- 开发任务从模块分支切出，合回模块分支。模块验收在模块分支上运行。模块分支合入 main 由你人工合并。
- 合入模块分支的两种方式：
  - 有 GitHub：PR + 必需检查 + auto-merge。
  - 纯本地：由模块 agent 合并，因为它是模块分支唯一的写者。
- **[待验证]** 创建子任务时能否把 base branch 设为模块分支（相关工具是 `update_repository_base_branch_kandev`）。

---

## 10. GitHub 的用法（可选）

- GitHub 只当**公开账本**用：模块对应 issue，开发任务对应 sub-issue；PR 用于交接；CI 必需检查作为合并门禁。可以用 Kandev 的 Issue Watch 把 issue 导入为任务。
- agent 之间的问答、认领、重试**不放到 GitHub 上**。只在状态变化时回写一条摘要，这样能省 API 额度、减少通知噪音、避免上下文膨胀。
- issue 和 PR 里的文本一律当作不可信输入（存在提示注入风险）。审核 agent 用只读权限。

---

## 11. 并发与成本控制

- 先小规模起步：同时运行 **2～3 个**开发任务。用 WIP 上限加 `KANDEV_MAX_CONCURRENT_SESSIONS` 控制并发（多个 agent 同时自动启动有已知 bug，issue #4152）。
- 模型分层只在会话边界切换，会话中途换模型会让缓存失效。
- 预期成本：多 agent 的 token 消耗大约是单 agent 的 2～15 倍。所以**只有能拆、有测试、价值够高的工作**才走这套流程，小改动直接用单个 agent。

---

## 12. 落地前需要实测的点

1. `auto_advance_requires_signal` 加 `step_complete_kandev` 在你使用的 agent CLI 上是否稳定（有已知 bug #3336、#5173）。
2. 能否 `move_task_kandev` 到当前步骤并带上 `reset_context`。
3. 子任务的 base branch 能否指定为模块分支。
4. worktree 执行器下能否读写仓库外的管理目录。
5. Windows 上 worktree 执行器的表现（据二手资料，成熟度不如 macOS/Linux）。
6. 会话结束策略（end policy）的默认值到底是 `park` 还是 `complete`（两份文档说法矛盾）。
7. 导入 workflow YAML 时，agent profile 的名称、模型、模式要完全一致，否则会被静默置空。

建议的试点：1 个模块、2～3 个开发任务。记录每个任务的 token 用量、审核退回轮数、守护触发次数和最终合并率，再决定哪些组件值得保留。
