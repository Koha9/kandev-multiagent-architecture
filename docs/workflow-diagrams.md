# Workflow v3.1 流程图

**中文** | [English](workflow-diagrams.en.md)

> 配套 [workflow.md](workflow.md)。图用 Mermaid 编写，可在 VS Code（Markdown Preview Mermaid 插件）、GitHub、Typora 中直接渲染，也可以用浏览器打开 `workflow-diagrams.html`。

---

## 图 1：整体视角（入口 / 循环 / 出口）

```mermaid
flowchart TD
  START(["入口：用户新建 pm 任务<br/>[TASK v1]：mode = attended / unattended，plan_only"])

  subgraph W1["W1 项目管理（1 个任务）"]
    P1["立项规划<br/>charter：需求 R-n 原文 + 模块 + PA + ADR"]
    PR["立项评审（独立会话）<br/>需求覆盖表 → charter-review"]
    PRC{"评审结论"}
    P2{"立项确认<br/>（attended 或 plan_only）"}
    P3["环境基线<br/>骨架 / 冒烟 / 检查脚本 / 额度开关<br/>约束清单：禁推送 / owns 检查 / 额度账本"]
    P3C{"冒烟测试通过?"}
    P4["模块下发<br/>create_task × N"]
    P5["调度（常驻）<br/>每条上报 = 一轮"]
    P5C{"所有模块完成?"}
    P6["项目验收（独立会话）<br/>integration + 全量验证 + 逐条核对 R"]
    P6C{"有 fail?"}
    P7{"人工终审"}
    PF["收尾合并（mechanical）<br/>integration → 基线 / 冒烟 / 清理"]
    PFC{"合并 + 冒烟通过?"}
    REF1["刷新（中转）<br/>重置上下文后移回"]
  end

  subgraph W2["W2 模块管理（每模块 1 个，可并行）"]
    M1["模块规划<br/>spec / interfaces / tasks.json<br/>create_task 开发子任务"]
    M2["等待开发（常驻）<br/>答疑 / 处理升级 / 本地合并<br/>放行待开发 / 确认 dropped"]
    M3["验收调查（重置上下文）<br/>先查 FAILED 子任务"]
    M3C{"模块验收通过?"}
    REF2["刷新（中转）"]
  end

  subgraph W3["W3 开发（每子任务独立 worktree，「开发」WIP 4）"]
    D0["待开发（不计 WIP）<br/>有前置的任务停在这里"]
    D1["开发<br/>冒烟 → 实现 → 测试 + owns 检查 → report"]
    R1["审核（新会话，不同 profile）<br/>原样重跑 + 逐条 AC 证据 + 边界抽查"]
    R1C{"审核结论"}
    D3["等待决策"]
    D4["合并到模块分支"]
  end

  FIN(["正常出口：集成分支合入基线，项目完成"])
  ESC(["异常出口：停下交给人<br/>超出上限 / 无法决策 / 收尾合并失败"])
  GUARD["守护（Kandev automation）<br/>每 20 分钟运行 stage.py<br/>→ stage.md + ALERT"]

  START --> P1 --> PR --> PRC
  PRC -->|"阻塞问题（退回 ≤2 次）"| P1
  PRC -->|"通过 · unattended"| P3
  PRC -->|"通过 · attended / plan_only"| P2
  P2 -->|"发消息：带意见"| P1
  P2 -->|"拖到环境基线 = 批准"| P3
  P3 --> P3C
  P3C -->|"否（≤3 次）"| P3
  P3C -->|"是"| P4
  P4 -->|"每个模块"| M1
  P4 --> P5

  M1 -->|"无前置的子任务"| D1
  M1 -->|"有前置的子任务"| D0
  M1 --> M2
  M2 -.->|"前置已合入：放行"| D0
  D0 --> D1
  D1 -.->|"dropped / blocked：ESCALATE"| M2
  D1 -->|"step_complete + handoff"| R1 --> R1C
  R1C -->|"minor（≤3 轮）"| D1
  R1C -->|"direction / 第 3 轮"| D3
  R1C -->|"pass"| D4
  D3 -.->|"ESCALATE"| M2
  M2 -.->|"改契约后退回 / 拆分"| D1
  D4 -->|"on_children_completed"| M3
  M3 --> M3C
  M3C -->|"否：修复子任务"| M2
  M3C -.->|"是：REPORT"| P5

  P5 --> P5C
  P5C -->|"否：继续等"| P5
  P5C -->|"是"| P6 --> P6C
  P6C -->|"是：待修复"| P4
  P6C -->|"否（unverified 列入需要用户处理）"| P7
  P7 -->|"发消息：带意见"| P4
  P7 -->|"拖到收尾合并 = 批准"| PF --> PFC
  PFC -->|"是"| FIN
  PFC -->|"否：停下说明"| ESC

  P5 -.->|"会话过长"| REF1 -.->|"移回"| P5
  M2 -.->|"会话过长"| REF2 -.->|"移回 / 子任务已全终态 → 验收"| M2
  M2 -.->|"跨模块 / 超限"| P5
  P5 -.->|"无法决策"| ESC
  GUARD -.->|"ALERT"| M2
  GUARD -.->|"ALERT"| P5

  classDef entry fill:#d1fae5,stroke:#059669,stroke-width:2px,color:#064e3b
  classDef exit fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a
  classDef exc fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d
  classDef loop fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f
  classDef gate fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95
  classDef aux fill:#f3f4f6,stroke:#6b7280,stroke-dasharray:4 3,color:#111827
  class START entry
  class FIN exit
  class ESC exc
  class PRC,P3C,R1C,M3C,P5C,P6C,PFC loop
  class P2,P7 gate
  class GUARD,REF1,REF2,D0 aux
```

图例：🟩 入口　🟦 正常出口　🟥 异常出口　🟨 循环判定点　🟪 人工门禁　⬜ 辅助（守护 / 刷新）　虚线 = 消息、通知或中转

### 入口

| 入口 | 触发方式 | 进入位置 |
|---|---|---|
| 项目入口 | 用户新建 pm 任务（Start task；或放在「待立项」，之后发消息启动） | W1 立项规划 |
| 模块入口 | pm 调用 `create_task_kandev`；有依赖时，前置模块完成后由 `blocked_by` 自动解除阻塞 | W2 模块规划 |
| 子任务入口 | 模块 agent 调用 `create_task_kandev`（autopilot，`base_branch=mod/<模块>`）；有前置的以 `start_agent=false` 建到「待开发」 | W3 开发 / 待开发 |
| （可选）外部入口 | GitHub Issue Watch 把 issue 导入为任务 | W1 或 W2 |

### 循环

| # | 循环 | 回到哪里 | 结束条件 | 上限，超限后去向 |
|---|---|---|---|---|
| L1 | 立项规划 ↔ 立项评审 | 立项规划 | 评审通过 | 退回 2 次后，第 3 次只记录非阻塞问题并放行 |
| L2 | 立项确认（attended） | 立项规划 | 用户批准 | 由用户决定 |
| L3 | 环境基线自修 | 环境基线 | 冒烟测试通过 | 3 次 → attended 时交给用户，unattended 时写 ADR 并停下 |
| L4 | 开发 ↔ 审核 | 开发（沿用原会话） | pass | 第 3 轮 → 等待决策 |
| L5 | 方向性问题处理 | 开发（契约已改）或新子任务 | 模块 agent 做出决策 | 涉及跨模块 → pm |
| L6 | 模块验收 ↔ 修复子任务 | 等待开发 | 模块验收通过 | 第 3 次 → 升级给 pm |
| L7 | 调度等待 | 调度（每条上报一轮） | 全部模块完成 | 会话过长 → 刷新 |
| L8 | 项目验收 / 终审意见 ↔ 修复 | 模块下发 | 用户批准 | 由用户决定 |
| L9 | 会话刷新 | 刷新步骤 → 原步骤 | 状态已写入 NOW | 刷新后仍过长 → 拆分任务或模块 |

### 出口

| 出口 | 条件 | 结果 |
|---|---|---|
| 正常出口 | 用户在人工终审中把任务拖到「收尾合并」，且合并与冒烟测试都通过 | 集成分支合入基线，临时资源已清理，任务完成 |
| 子任务出口 | 审核通过并合入模块分支 | 子任务结束；全部结束时触发 `on_children_completed` |
| 模块出口 | 模块验收通过并已上报 | 模块任务结束；依赖它的模块解除阻塞 |
| 异常出口 | 超出循环上限、管理层无法决策、收尾合并时冲突或冒烟失败 | 停在当前步骤并说明原因，等人处理 |
| 废弃出口 | 任务过大或方向错误，被 `stop_task_kandev` 停止 | `tasks.json` 中标记 `failed`，由拆分出的新子任务替代 |

---

## 图 2：Agent 视角（lifecycle + 允许的交互）

用时序图表示：每一列是一个 agent。**竖向激活条 = 该 agent 的会话存续期（lifecycle）**；箭头 = **允许的**交互（标注所用工具）。图中没有画出的交互一律不允许。
`loop` 表示循环，`alt` 表示分支，`opt` 表示可选，灰色区块是守护随时可能触发的部分。

```mermaid
sequenceDiagram
  actor U as 👤 用户
  participant PM as 项目管理 agent

  U->>+PM: 建 pm 任务（mode = attended / unattended）【入口】
  Note over PM: 立项规划
  create participant AU as 独立评审 agent（每次新会话）
  PM->>AU: step_complete → 立项评审
  activate AU
  alt 有阻塞问题（退回 ≤2 次）
    AU-->>PM: move_task 退回立项规划（附问题清单）
  else 通过 · unattended
    AU-->>PM: move_task → 环境基线（代替人工确认）
  else 通过 · attended
    AU->>U: step_complete → 立项确认（人工门禁）
    U-->>PM: 拖到环境基线 = 批准；发消息 = 带意见回到立项规划
  end
  deactivate AU
  Note over PM: 环境基线 → 模块下发

  create participant MM as 模块管理 / 验收 agent
  PM->>MM: create_task（前置模块完成后自动启动）
  activate MM
  Note over MM: 模块规划：写 spec / interfaces / tasks.json

  create participant D as 开发 agent
  MM->>D: create_task（autopilot，base_branch=mod/模块）
  activate D
  Note over MM: 等待开发（常驻）

  opt 开发中有疑问
    D->>MM: ask_parent_question
    MM-->>D: message 答复（reply_to_question_id）
  end

  loop 开发 ↔ 审核，最多 3 轮
    create participant R as 审核 agent（每次新会话）
    D->>R: step_complete + handoff（report）
    activate R
    Note over R: 原样重跑测试，逐条 AC 证据，边界抽查
    alt minor
      R-->>D: move_task 退回（附说明），开发沿用原会话
    else direction / 第 3 轮
      R->>MM: KMSG ESCALATE
      Note over D: 等待决策
      MM-->>D: 改契约后 move_task 退回，或 stop_task 后拆分
    else pass
      R-->>D: step_complete → 合并到模块分支
    end
    deactivate R
  end
  deactivate D
  Note over D: 子任务结束（仍可被提问唤醒）
  D-->>MM: 全部子任务结束 → on_children_completed

  rect rgb(243, 244, 246)
    participant G as 守护（Kandev automation）
    G->>MM: KMSG ALERT（只读巡检：会话过长 / 卡住）
    MM-->>D: INSTRUCT 写检查点后带 reset_context 重开，或拆分
    G->>PM: KMSG ALERT（调度会话过长）
    PM->>PM: 写「刷新返回」→ 移到「刷新」→ 重置后移回「调度」
  end

  Note over MM: 验收调查（重置上下文）：先查 FAILED 子任务
  opt 交付物（report / review）不清楚：谁担当就问谁
    MM->>D: KMSG QUESTION（最多 2 轮，不翻对话或代码）
    D-->>MM: KMSG ANSWER（只答不改）
  end
  alt 模块验收不通过（第 3 次进入前）
    MM->>MM: 建修复子任务，回到等待开发
  else 跨模块问题 / 超限
    MM->>PM: KMSG ESCALATE
    PM-->>MM: KMSG DECISION（ADR）
  end
  MM->>PM: KMSG REPORT（模块上报）
  deactivate MM

  Note over PM: 调度：全部模块完成
  PM->>AU: move_task → 项目验收（新会话）
  activate AU
  alt PA 全部通过
    AU->>U: step_complete → 人工终审（final-report 写明运行方式）
  else 有 fail
    AU-->>PM: move_task 回模块下发（建修复任务）
  end
  deactivate AU
  alt 用户批准
    U->>PM: 拖到「收尾合并」
    Note over PM: 收尾合并（mechanical）：integration → 基线、冒烟、清理【正常出口】
  else 用户有意见
    U->>PM: 发消息 → 带意见回到模块下发
  end
  deactivate PM
```

### Agent lifecycle 一览

| Agent | 由谁创建 | 会话寿命 | 何时重开会话 | 何时结束 |
|---|---|---|---|---|
| 项目管理 | 用户 | 长期（整个项目） | 经「刷新」步骤重置 | 收尾合并完成 |
| 独立评审 | workflow（立项评审 / 项目验收） | 一次评审 | 每次都是新会话 | 给出结论 |
| 模块管理 / 验收 | 项目管理 | 模块存续期间 | 经「刷新」步骤重置；进入验收调查时重置 | 模块上报完成 |
| 开发 | 模块管理 | 一个子任务 | 被告警时写检查点后重开 | 合入模块分支，或被 stop 后拆分 |
| 审核 | workflow（审核步骤） | 一次审核 | 每次都是新会话 | 给出结论 |
| 守护 | Kandev automation（cron） | 一次巡检 | 每次都是新会话 | 发出告警，或无事结束 |

### 交互权限矩阵

行 = 发起方，列 = 接收方。✅ 允许　⚠️ 有条件允许　❌ 禁止

| 发起 ↓ / 接收 → | 用户 | 项目管理 | 模块管理 | 开发 | 审核 |
|---|---|---|---|---|---|
| **项目管理** | ⚠️ 仅 attended：提问、门禁 | — | ✅ 建任务、决策 | ❌ | ❌ |
| **独立评审** | ✅ 经门禁步骤 | ✅ 只通过 `move_task`（附意见）和任务文档 | ❌ | ❌ | ❌ |
| **模块管理** | ❌ 经项目管理 | ✅ 上报、升级 | ⚠️ 其他模块：只问事实 | ✅ 建任务、答复、退回、停止、提问 | ⚠️ 读交付物 review；有疑问就问该次审核会话 |
| **开发** | ❌（autopilot 下只能问上级） | ❌ | ✅ `ask_parent_question` | ❌ 开发之间禁止直接通信 | ✅ 只通过 `step_complete` + handoff |
| **审核** | ❌ | ❌ | ✅ ESCALATE | ✅ 只通过 `move_task` 退回（附说明） | — |
| **守护** | ❌ | ✅ ALERT；pm 卡住且无反应时移到「刷新」 | ✅ ALERT | ❌ 经模块管理转达 | ❌ |

### 明确禁止的交互（及理由）

- **开发 ↔ 开发**：并行写者之间会私下协调，结果是重复工作或相互覆盖。需要协调时，经模块管理处理。
- **审核 / 独立评审 ↔ 被评审者对话**：会破坏评审者干净的上下文。评审只能通过结构化结论和退回说明表达意见。
- **开发 / 审核 → 项目管理**：越级上报会让项目管理的上下文膨胀。一律经模块管理汇总。
- **模块之间私下商定接口**：跨模块决策必须写成 ADR，由项目管理拍板。
- **守护直接修复**：守护只做检测和告警，修复由该任务的上级执行。唯一例外是把卡住的 pm 移到「刷新」。
- **替别人查询**：不归你担当的信息，直接问担当者，不要自己翻对话记录或读代码推测。被问到不归自己的事时，转介给担当者。
- **在 GitHub 评论里闲聊**：GitHub 只记录状态变化的摘要，agent 之间的交流留在 Kandev 内部。
