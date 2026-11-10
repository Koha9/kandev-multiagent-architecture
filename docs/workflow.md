# 多 Agent 开发 Workflow（v3.1）

> 本文件讲多 agent 架构本身：角色、workflow、步骤、通信、状态与恢复、门禁、并发。
> 配套文档：
> - [workflow-diagrams.md](workflow-diagrams.md)：流程图
> - [prompts.md](prompts.md)：各步骤 prompt 与配置，由脚本生成
> - [mgmt-workspace.md](mgmt-workspace.md)：管理目录的构造
> - [project-conventions.md](project-conventions.md)：被开发项目一侧的约定（额度、副作用、约束清单、测试、截图、合并与推送）
> - [../mgmt-template/](../mgmt-template/README.md)：文档模板、角色卡、消息协议
> - [../kandev/](../kandev/README.md)：部署脚本

## 1. 设计原则

1. **单写者**：同一份代码、同一个文件，同一时刻只有一个 agent 写。并行只发生在相互独立的任务之间，每个任务用独立的 worktree。
2. **测试是裁判**：每个任务都有机器可判定的完成条件（测试、lint、构建）。agent 的自我评价不算数。
3. **评审者上下文干净**：审核、立项评审、项目验收都换 profile、开新会话，只看交付物和验收标准。
4. **状态存文件，会话可抛弃**：任何会话随时可以重置，靠管理目录和任务文档恢复（恢复协议）。
5. **管理者不写代码**：项目管理和模块管理只做规划、委派、验收和记录。
6. **每个循环都有上限**：退回次数、评审轮数、消息轮数都有硬上限，超出就交给上一级或交给人。
7. **门禁在 workflow 内部**：无人值守时，由独立评审步骤代替人工门禁放行，不依赖外部守护轮询。
8. **有副作用的操作默认关闭**：消耗额度或影响外部的操作只能由显式开关打开；具体有哪些、怎么开，由各项目按 [开发项目约定](project-conventions.md) 规定。
9. **需求原文贯穿到底**：用户需求逐条摘录为 R-n，PA、MA、AC 都写明覆盖哪条；管理者只拆分"做什么"，不写实现方案，也不改写需求。
10. **能用代码强制的约束不只写在 prompt 里**：每条约束标明执行方式（代码强制 / 检查脚本 / 仅 prompt），被代码拦下时停下上报，不绕过。
11. **结论如实**：验收结论只有 pass / fail / unverified(原因)；部分完成写 partial；无需改动可以如实 dropped。需要用户处理的事集中到一处，每项附推荐答案。

## 2. 整体结构

```
项目管理任务（W1，根任务，1 个）
 ├─ 创建 → 模块管理任务（W2，独立任务，可并行；有依赖时用 blocked_by）
 │          └─ 子任务 → 开发任务（W3，独立 worktree，base_branch=mod/<模块>）
 └─ 守护（Kandev automation，定时只读巡检，向上级告警）
```

- 模块任务**不挂在**项目任务下面。Kandev 常规看板的子任务只有一层，所以模块用 `message_task_kandev` 向 pm 上报。
- **小项目变体**：模块不超过 3 个、每个模块不超过 2 个任务时，可以去掉 W2，让 pm 直接创建开发子任务，模块验收合并进项目验收。

### 角色与 profile

| 角色（profiles.json 的键） | 用在哪里 | 模型建议 | 会话 |
|---|---|---|---|
| `pm` | W1 立项规划 / 环境基线 / 模块下发 / 调度 / 刷新；W2 全部 agent 步骤 | 强模型 | 长期存在，可刷新 |
| `auditor` | W1 立项评审、项目验收 | 强模型，profile 必须与 pm 不同 | 每次新会话 |
| `developer` | W3 开发 | 主力编码模型 | 一个任务一个会话，被退回时复用 |
| `reviewer` | W3 审核 | profile 必须与 developer 不同，最好换厂商 | 每次新会话 |
| `mechanical` | W3 合并、W1 收尾合并 | 便宜模型即可 | 每次新会话 |
| 守护 | Kandev automation；判断由 `kandev/stage.py` 完成 | 便宜模型 | 每次运行一个新会话 |

## 3. 运行模式

pm 任务描述的 `[TASK v1]` 头写 `mode: attended | unattended`，模块任务和开发任务继承同一个值。

| | attended（默认） | unattended |
|---|---|---|
| 立项确认 | 立项评审通过后，等用户确认 | 立项评审通过后直接进入环境基线 |
| 向用户提问 | 可以，合并成一次提问（每题附推荐答案） | 不提问。自行决定，写 ADR，登记到 `project/attention.md` |
| 环境需要用户配置（例如 Copy files） | 请用户配置 | 选择不依赖用户配置的方案，并写 ADR |
| 人工终审 | 用户 | 用户（回来后处理） |

**plan_only**（`[TASK v1]` 头 `plan_only: true`）：不论 mode，立项评审通过后都停在「立项确认」。用户先检查 charter 和需求覆盖表，满意后拖到「环境基线」继续，再投入开发额度。

用户只需要看两处：`project/attention.md`（需要用户决定的事，每项附推荐答案和默认做法）和 `agents/guard/stage.md`（系统现在在等谁，由守护脚本生成）。

## 4. W1 项目管理

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | 待立项 | — | 停放 | 发消息 → 立项规划 |
| 1 | **立项规划** | pm | 初始化管理目录；写 charter（需求 R-n 原文、模块、PA 及 covers）、conventions、ADR、attention | 完成信号 → 立项评审 |
| 2 | 立项评审 | auditor | 独立评审 charter：需求覆盖表（每条 R 一行）+ 每项检查一行结论，写进任务文档 `charter-review` | 退回 → 立项规划（≤2 次）；通过：plan_only 或 attended → 立项确认，unattended → 环境基线 |
| 3 | 立项确认 | 人 | 门禁（attended 或 plan_only） | 拖到环境基线 = 批准；发消息 = 带意见回到立项规划 |
| 4 | 环境基线 | pm | 按开发项目约定建立环境、骨架、冒烟测试、检查脚本，落实约束清单，写明合并方式 | 完成信号 → 模块下发 |
| 5 | 模块下发 | pm | 创建模块任务；再次进入时处理待修复项和终审意见 | 完成信号 → 调度 |
| 6 | 调度 | pm | 常驻，处理上报、升级、提问、告警 | 全部模块完成后，agent 自己移到项目验收 |
| 7 | 项目验收 | auditor | 合并集成分支，全量验证 PA，逐条核对 R；写 final-report（含额度用量、终审运行方式、需要用户处理、临时资源） | 没有 fail → 人工终审；有 fail → 模块下发 |
| 8 | 人工终审 | 人 | 门禁 | **拖到收尾合并 = 批准**；发消息 = 带意见回到模块下发 |
| 9 | 收尾合并 | mechanical | 集成分支合入基线分支、跑冒烟测试、清理临时资源、把 status 设为 done | 完成信号 → 完成 |
| 10 | 完成 | — | 任务完成 | — |
| 11 | 刷新 | pm | 重置上下文后，移回 NOW 记录的原步骤 | agent 自己移动 |

## 5. W2 模块管理

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | **模块规划** | pm | 写 spec（MA 及 covers）/ interfaces / tasks.json；创建开发子任务（base_branch=mod/<模块>，autopilot）：无前置的进「开发」，有前置的进「待开发」 | 完成信号 → 等待开发 |
| 1 | 等待开发 | pm | 常驻：回答子任务提问，处理审核升级和 dropped / blocked，本地合并子任务分支，放行前置已完成的「待开发」任务 | 子任务全部终态（on_children_completed）→ 验收调查 |
| 2 | 验收调查 | pm | 重置上下文；先查 FAILED / CANCELLED 的子任务；跑模块测试，逐条核对 MA；上报 pm | 完成信号 → 完成；有问题 → 等待开发 |
| 3 | 完成 | — | | |
| 4 | 刷新 | pm | 重置上下文后移回原步骤；如果子任务已全部终态，直接去验收调查 | agent 自己移动 |

## 6. W3 开发

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | 待开发 | — | 停放有前置任务的子任务（不计 WIP，不启动会话） | 前置完成后由模块 agent 移到开发 |
| 1 | **开发**（WIP 4） | developer | 冒烟测试 → 实现 → 测试 + owns 检查 → 写 report → commit；无需改动 → 建议 dropped；做不完 → blocked | 完成信号 → 审核；dropped / blocked → ESCALATE 给模块 agent |
| 2 | 审核 | reviewer | 原样重跑测试和 owns 检查；每条 AC 写出亲自确认的证据（不能确认的写 unverified），至少抽查 1 个边界情况；写 review | pass → 合并；minor → 开发（≤3 轮）；direction → 等待决策并 ESCALATE |
| 3 | 等待决策 | — | 由模块 agent 处理 | 模块 agent 移动 |
| 4 | 合并 | mechanical | 先核对是否已合并；rebase、测试；提 PR，或交给模块 agent 本地合并；两种方式都向模块 agent 发 REPORT | PR 合并 → 完成；本地合并时由模块 agent 移到完成 |
| 5 | 完成 | — | | |

开发和审核在测试、截图等方面的具体要求见 [开发项目约定](project-conventions.md)。

## 7. 上下文与连续性

- **预防**：一个任务一个会话；跨步骤靠 handoff、任务文档和管理目录传递信息；常驻上下文保持很小（AGENTS.md ≤150 行，prompt 稳定、不含时间戳，这样有利于缓存命中）。
- **刷新**：常驻步骤（调度、等待开发）的会话过长时，agent 先把 `刷新返回：<步骤>` 写进 NOW，再移到「刷新」步骤。刷新步骤进入时重置上下文，然后移回原步骤。Kandev 不允许把任务移到当前步骤，所以必须经过这个中转步骤。
- **守护**：每个 workspace 一个 Kandev automation，每 15–20 分钟运行一次，自己发现所有进行中的项目，只读巡检，向上级发 ALERT。由 `kandev/stage.py` 按固定的规则表判断每个任务"在等谁"（第一条匹配的生效），守护只执行脚本给出的告警，并生成 `agents/guard/stage.md` 给用户看。规则见 `mgmt-template/roles/guard.md`「阶段分类」。
- **恢复时先核对外部状态**：重复创建任务、合并、推送、真实调用、删除资源之前，先查实际状态，已经生效的不再做。刷新步骤先核对 NOW「未确认的意图」。

## 8. 并发与 WIP

- 「开发」步骤的 WIP 是所有模块共用的全局上限（默认 4），用来控制本机同时运行的 agent 数量。
- Kandev 的 WIP 按"任务在这个步骤里"计数，被 blocked_by 阻塞的任务也会占名额，并行会被依赖链拖成串行。所以 W3 有一个不计 WIP 的「待开发」步骤：有前置的任务以 `start_agent=false`、`start_when_unblocked=false` 创建在那里，前置合入后由模块 agent 移到「开发」。
- 依赖链仍建议不超过 1 层，必须串行的工作合并成一个任务。
- 有依赖关系的模块之间用 blocked_by；能在共享骨架上并行的模块不设依赖。

## 9. 分支与合并

```
基线分支 ← 收尾合并 ← integration ← 项目验收 ← mod/<模块> ← 模块 agent / PR ← 开发 worktree 分支
```

- 环境基线把骨架合入基线分支，模块分支从基线分支切出。
- 开发子任务通过 `base_branch=mod/<模块>` 从模块分支切出，完成后合回模块分支。
- 项目验收建立 integration 分支，合并所有模块分支。
- 用户在人工终审中批准后，「收尾合并」把 integration 合入基线分支。
- 合并方式（本地或 PR）、是否推送远端，由各项目的 environment.md 规定，见 [开发项目约定](project-conventions.md)。

## 10. 与开发项目的边界

架构只规定**谁、在哪一步、怎样**处理项目约定，具体内容（额度、副作用、约束清单、测试命令、截图、合并与推送）属于每个被开发项目，见 [开发项目约定](project-conventions.md)。

| 架构规定的 | 位置 |
|---|---|
| 立项规划把约定写进项目的 conventions；环境基线把能强制的约束落实为代码 | W1 立项规划、环境基线 |
| 开发上报前、审核时运行检查脚本；复跑测试按 environment.md 原样执行 | W3 开发、审核 |
| 被代码强制的约束拦下时停下上报，不绕过；不能强制的标"仅 prompt" | 所有 prompt 的【通用规则】 |
| 项目验收报告额度用量 | W1 项目验收 |


## 11. 部署与启动

部署步骤见 [kandev/README.md](../kandev/README.md)，让 agent 代为部署和验收见 [AGENTS.md](../AGENTS.md)。

启动项目：在「多Agent · 项目管理」新建任务，选好仓库，描述写成下面的格式，然后选择 Start task。

```
[TASK v1]
project: <项目名>
mode: attended | unattended
plan_only: false            # true：立项评审通过后停在「立项确认」
mgmt_root: <管理目录绝对路径，放在仓库与 worktree 之外>
mgmt_template: <本仓库 mgmt-template 的绝对路径>
repo: <主仓库绝对路径>
role: pm
scope: pm
parent: user
pm: self
branch: <自动> base <基线分支>
---
<项目目标、需求（按重要度排序，一条一行，pm 会逐条摘录为 R-n）、约束、环境与限制、额度约定（见开发项目约定）>
```

## 12. 已知限制

- 外部 MCP 没有 `message_task_kandev`，也不能创建 automation。外部的守护或观察者只能移动任务、代答提问和权限请求。需要这些能力的工作写成交接 prompt（`kandev/handoff/`），交给 Kandev 内部的 agent 执行。
- `on_children_completed` 只在任务处于「等待开发」时生效。刷新步骤会检查子任务状态，补上这个缺口。
- 会话里的上下文用量 Kandev 有记录，但 MCP 读不到，所以守护只能看间接信号。
- 导出的 workflow 文件只按 model / mode 记录 profile。同模型的 profile 有多个时可能匹配错，所以部署用 `build_workflows.py`，它按 ID 绑定。
- 「待开发」依赖两点 Kandev 行为，部署后要先验证（见 [AGENTS.md](../AGENTS.md)「验收部署」）：`create_task_kandev` 带 `workflow_step_id`、`start_agent=false`、`start_when_unblocked=false` 时任务停在该步骤、不启动会话，前置完成时也不自动启动；从无 agent 步骤移到「开发」会触发 on_enter 的 auto_start。PR 方式下模块 agent 不会被 PR 合并事件唤醒，靠守护的 `hold_ready` 告警放行。

## 13. 已否决的设计

试过或评估后放弃的方案，留下原因，避免以后再走回去。

| 方案 | 否决原因 | 现在的做法 |
|---|---|---|
| 常驻步骤"移到本步骤 + reset_context"来刷新 | Kandev 的 entry_options 要求真的换步骤，移到当前步骤是 no-op | 「刷新」中转步骤 |
| 门禁交给外部定时守护放行 | 轮询间隔 20 分钟，门禁平均要等约 10 分钟 | 立项评审在 workflow 内放行 |
| 只靠测试配置的默认值挡住消耗额度的调用 | 一个命令行参数就能覆盖，实跑中出现过真实调用超限 | 显式开关 + 代码检查 + 额度账本 |
| 管理目录 `git add -A` | 会把别人担当的文件一起提交 | 只 add 自己的路径 + pre-commit 钩子 |
| 立项确认设置 session_target | 疑似多出一个空会话 | 不设置 |
| 有前置的任务直接放在「开发」用 blocked_by 等待 | 阻塞的任务也占 WIP，并行被依赖链拖成串行 | 停在不计 WIP 的「待开发」，由模块 agent 放行 |
| 用 Kandev 的 pull_from_step 把任务从「待开发」拉进「开发」 | 不确定拉取时是否检查 blocked_by；放行条件（前置已合入）由模块 agent 判断更明确 | 模块 agent 移动 |
| 开发等待模块回答时移到不计 WIP 的「等待回答」步骤 | 回答通过 message_task 开启新一轮，在无 agent 步骤里的行为没有验证 | 暂不采用 |
| 守护用 LLM 读信号做判断 | 不可重复、难测试 | `stage.py` 规则表 + 回归测试 |
| 每个项目单独创建一个守护 automation | 每次启动项目都要手动配置，项目结束还要清理 | 每个 workspace 一个守护，从 pm 任务的 `[TASK v1]` 头自己发现项目 |
| 从对话正文或报告自由文本推断"是否在等人" | 需要结构化事实 | 只用 Kandev 状态、待处理的提问和权限请求 |
