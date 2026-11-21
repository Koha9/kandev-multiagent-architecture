# Workflow 流程图

> 配套 [workflow.md](workflow.md)，步骤和流转以它第 4–6 节的表格为准。图用 Mermaid 编写，GitHub、VS Code（Markdown Preview Mermaid 插件）、Typora 都能直接渲染。
> 颜色：蓝 = 管理者（pm / module），紫 = 独立的验证者（每次新会话、换 profile），绿 = 开发，灰 = intake / mechanical，黄 = 人工门禁，虚线框 = 没有 agent 的步骤。虚线箭头 = 消息或由 agent 自己移动。

## 图 1：整体结构

```mermaid
flowchart TD
  U(["用户：新建项目任务，只写需求"])
  subgraph W1["W1 项目管理（1 个任务）"]
    PM["pm：立项、模块下发、调度"]
    AUD["独立验证：立项评审、项目验收"]
  end
  subgraph W2["W2 模块管理（每模块 1 个任务）"]
    BASE["baseline 模块<br/>环境、骨架、检查脚本（最先）"]
    MODS["功能模块 × N<br/>blocked_by baseline，可并行"]
    IT["结合测试模块<br/>blocked_by 全部其他模块（最后）"]
    FIX["修复模块 mod:&lt;模块&gt;-fix-n<br/>只为 fail 建立"]
  end
  subgraph W3["W3 开发（每子任务 1 个 worktree）"]
    DEV["开发 → 审核 → 合并门禁<br/>快进合入 mod/&lt;模块&gt;"]
  end
  MGMT[("管理目录 mgmt_root<br/>charter、registry、tasks.json、NOW、attention.md、stage.md")]
  GUARD["守护 automation<br/>每 20 分钟运行 stage.py"]

  U --> PM
  PM -->|"create_task"| BASE
  PM -->|"create_task"| MODS
  PM -->|"create_task"| IT
  BASE -->|"完成后解除阻塞"| MODS
  MODS -->|"全部完成后解除阻塞"| IT
  BASE & MODS & IT & FIX -->|"子任务"| DEV
  MODS & BASE & IT & FIX -.->|"REPORT / ESCALATE"| PM
  IT -.->|"缺陷、合并冲突：ESCALATE"| PM
  PM -->|"修复项按指针下发"| FIX
  AUD -.->|"fail：修复项"| PM
  PM & MODS <--> MGMT
  GUARD -.->|"ALERT"| PM
  GUARD -.->|"ALERT（带 session_id）"| MODS
  GUARD -.->|"写 stage.md"| MGMT

  classDef mgr fill:#ddf4ff,stroke:#54aeff,color:#0a3069
  classDef ver fill:#fbefff,stroke:#c297ff,color:#512a97
  classDef dev fill:#dafbe1,stroke:#4ac26b,color:#044f1e
  classDef aux fill:#f6f8fa,stroke:#8c959f,stroke-dasharray:4 3,color:#1f2328
  class PM,BASE,MODS,IT,FIX mgr
  class AUD ver
  class DEV dev
  class GUARD,MGMT aux
```

分支：`基线分支 ← 收尾合并 ← integration ← mod/<模块> ← 开发 worktree 分支`，`mod/baseline` 从基线分支切出，其他模块分支从 `mod/baseline`（或所依赖的模块分支）切出。详见 workflow.md 第 9 节。

## 图 2：W1 项目管理

```mermaid
flowchart TD
  S0["0 接收（intake）<br/>补全 [TASK v1] 头；完整的原样放行"]
  S1["1 立项规划（pm）<br/>charter：R-n、模块清单、B-n、PA"]
  S2["2 立项评审（plan_auditor）<br/>需求覆盖表 → charter-review"]
  S3{{"3 立项确认（人）"}}
  S4["4 模块下发（pm）<br/>建未建的模块；下发修复项和终审意见"]
  S5["5 调度（pm，常驻）<br/>只做路由"]
  S6["6 项目验收（auditor）<br/>合并各模块当前分支、全量测试、逐条核对 R"]
  S7{{"7 人工终审（人）"}}
  S8["8 收尾合并（mechanical）<br/>integration → 基线分支、冒烟、清理"]
  S9["9 刷新（pm）<br/>重置上下文后移回"]
  S10(["10 完成"])

  S0 --> S1 --> S2
  S2 -->|"有阻塞问题（退回 ≤2 次）"| S1
  S2 -->|"通过 · attended 或 plan_only；第 3 次仍有阻塞"| S3
  S2 -->|"通过 · unattended"| S4
  S3 -->|"拖到模块下发 = 批准"| S4
  S3 -.->|"发消息 = 带意见退回"| S1
  S4 --> S5
  S5 -.->|"全部模块完成，自己移动"| S6
  S6 -->|"有 fail：修复项"| S4
  S6 -->|"没有 fail，或第 3 次仍有 fail"| S7
  S7 -->|"拖到收尾合并 = 批准"| S8
  S7 -.->|"发消息 = 带意见退回"| S4
  S8 --> S10
  S5 -.->|"唤醒计数到阈值 / 守护告警"| S9
  S9 -.->|"移回原步骤"| S5

  classDef mgr fill:#ddf4ff,stroke:#54aeff,color:#0a3069
  classDef ver fill:#fbefff,stroke:#c297ff,color:#512a97
  classDef mech fill:#eff2f5,stroke:#afb8c1,color:#424a53
  classDef gate fill:#fff8c5,stroke:#d4a72c,color:#4d2d00
  class S1,S4,S5,S9 mgr
  class S2,S6 ver
  class S0,S8 mech
  class S3,S7 gate
```

## 图 3：W2 模块管理

```mermaid
flowchart TD
  M0["0 模块规划（module）<br/>spec / interfaces / tasks.json；建开发子任务"]
  M1["1 等待开发（module，常驻）<br/>只做路由：答疑、处理等待决策、对账并放行待开发、建修复子任务"]
  M2["2 验收调查（module_auditor，新会话）<br/>覆盖核对、跑模块测试、逐条判定 MA、写修复项"]
  M3["3 刷新（module）<br/>重置上下文后移回"]
  M4(["4 完成<br/>依赖它的模块随之启动"])
  PMX(["pm（W1 调度）"])

  M0 --> M1
  M1 -->|"子任务全部终态（on_children_completed）"| M2
  M2 -->|"有 fail：修复项"| M1
  M2 -->|"通过"| M4
  M2 -.->|"通过：REPORT；第 3 轮或涉及其他模块：ESCALATE"| PMX
  M1 -.->|"跨模块问题、接口变更：ESCALATE"| PMX
  PMX -.->|"DECISION / NOTICE"| M1
  M1 -.->|"唤醒计数到阈值 / 守护告警"| M3
  M3 -.->|"移回；子任务已全部终态 → 验收调查"| M1

  classDef mgr fill:#ddf4ff,stroke:#54aeff,color:#0a3069
  classDef ver fill:#fbefff,stroke:#c297ff,color:#512a97
  class M0,M1,M3 mgr
  class M2 ver
```

baseline 模块（`kind: baseline`）和结合测试模块（`kind: integration`）走同样的步骤，内容上的差别见 workflow.md 第 5 节。结合测试任务报告的缺陷不在本模块修：ESCALATE 给 pm，由担当模块的修复模块修完后再重跑。

## 图 4：W3 开发

```mermaid
flowchart TD
  D0["0 待开发<br/>无 agent，不计 WIP"]
  D1["1 开发（developer）<br/>实现契约 → 测试 + owns 检查 → report"]
  D2["2 审核（reviewer，新会话）<br/>原样重跑测试，逐条 AC 写证据"]
  D3["3 等待决策<br/>无 agent，不计 WIP"]
  D4["4 合并（mechanical）<br/>rebase、合并门禁、快进合入 mod/&lt;模块&gt;"]
  D5(["5 完成"])
  MA(["模块 agent（W2 等待开发）"])

  MA -->|"建子任务：先建在待开发，读回核对"| D0
  D0 -.->|"模块 agent 移动：无前置，或前置已 merged / dropped"| D1
  D1 --> D2
  D2 -->|"pass"| D4
  D2 -->|"minor（≤3 轮），沿用原开发会话"| D1
  D2 -->|"direction"| D3
  D1 -.->|"blocked / dropped / 缺陷：自己移动"| D3
  D3 -.->|"ESCALATE"| MA
  MA -.->|"带 instructions 移回开发，或移到完成"| D3
  D4 -->|"门禁失败（第 3 次 ESCALATE）"| D1
  D4 -->|"已合入"| D5
  D4 -.->|"REPORT"| MA

  classDef dev fill:#dafbe1,stroke:#4ac26b,color:#044f1e
  classDef ver fill:#fbefff,stroke:#c297ff,color:#512a97
  classDef mech fill:#eff2f5,stroke:#afb8c1,color:#424a53
  classDef hold fill:#ffffff,stroke:#8c959f,stroke-dasharray:4 3,color:#59636e
  class D1 dev
  class D2 ver
  class D4 mech
  class D0,D3 hold
```

## 图 5：消息与升级路径

图中没有画出的通信一律不允许。消息格式见 [../mgmt-template/protocol/message.md](../mgmt-template/protocol/message.md)。

```mermaid
flowchart LR
  USER(["用户"])
  PM["pm"]
  MOD["模块 agent"]
  OTHER["其他模块 agent"]
  MAUD["模块验收者"]
  DEV["开发"]
  REV["审核"]
  MRG["合并"]
  GUARD["守护"]

  DEV -->|"提问：ask_parent_question"| MOD
  DEV -->|"blocked / dropped / 缺陷：ESCALATE"| MOD
  REV -->|"方向性问题：ESCALATE"| MOD
  MRG -->|"REPORT；门禁第 3 次失败：ESCALATE"| MOD
  MOD -->|"答复、INSTRUCT、移动任务"| DEV
  MOD -->|"QUESTION（只问事实）"| OTHER
  MOD -->|"REPORT / ESCALATE"| PM
  MAUD -->|"通过：REPORT；第 3 轮或跨模块：ESCALATE"| PM
  MAUD -->|"误投的消息转交"| MOD
  PM -->|"DECISION（ADR）、NOTICE、建修复模块"| MOD
  PM -->|"attention.md；attended 时提问"| USER
  USER -->|"门禁：拖动 = 批准，发消息 = 退回"| PM
  GUARD -->|"ALERT"| PM
  GUARD -->|"ALERT（带 session_id）"| MOD
```

| 规则 | 理由 |
|---|---|
| 开发之间不直接通信 | 并行写者私下协调会造成重复工作或相互覆盖；任务之间的依赖只通过 `interfaces.md`，由模块 agent 协调 |
| 验证者不与被验证者对话 | 会破坏验证者干净的上下文；结论只通过任务文档、修复项和退回说明表达 |
| 开发、审核不越级找 pm | 一律经模块 agent 汇总，pm 的上下文不被任务细节填满 |
| 模块之间只问事实，不私下商定接口 | 变更接口只能经 pm（ESCALATE → DECISION + ADR） |
| 发给模块任务的消息带模块 agent 的 `session_id` | 不带时消息进任务的主会话，可能是验收者的 |
| 已完成（COMPLETED）的模块任务不发消息 | 只会排队；需要它再做事由 pm 建修复模块任务 |
| 守护只检测和告警，不修复 | 唯一的例外：把没有响应的 pm 移到「刷新」；用量上限重置后在原会话里继续 |
| 只有 pm 和「接收」能向用户提问 | 需要用户处理的事集中到 `project/attention.md` |
