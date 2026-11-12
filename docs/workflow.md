# 多 Agent 开发 Workflow（v3.2）

**中文** | [English](workflow.en.md)

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
3. **评审者上下文干净**：审核、立项评审、模块验收、项目验收都换 profile、开新会话，只看交付物和验收标准。验证者不自己定标准，执行上一层写好的标准，并把不通过项写成可直接下发的修复项。
4. **状态存文件，会话可抛弃**：任何会话随时可以重置，靠管理目录和任务文档恢复（恢复协议）。
5. **管理者不写代码**：项目管理和模块管理只做规划、委派和记录；环境和骨架也由 baseline 模块经开发任务完成。
6. **每个循环都有上限**：退回次数、评审轮数、消息轮数都有硬上限，超出就交给上一级或交给人。
7. **门禁在 workflow 内部**：无人值守时，由独立评审步骤代替人工门禁放行，不依赖外部守护轮询。
8. **有副作用的操作默认关闭**：消耗额度或影响外部的操作只能由显式开关打开；具体有哪些、怎么开，由各项目按 [开发项目约定](project-conventions.md) 规定。
9. **需求原文贯穿到底**：用户需求逐条摘录为 R-n，PA、MA、AC 都写明覆盖哪条；需求原文不改写；实现方案留给下一级决定，上级最多附参考建议。
10. **能用代码强制的约束不只写在 prompt 里**：每条约束标明执行方式（代码强制 / 检查脚本 / 仅 prompt），被代码拦下时停下上报，不绕过。
11. **结论如实**：验收结论只有 pass / fail / unverified(原因)；部分完成写 partial；无需改动可以如实 dropped。需要用户处理的事集中到一处，每项附推荐答案。
12. **边界要硬，方案要松**：边界（owns、单写者、额度开关、上报规则）管"能改哪里"，不管"怎么做"。prompt 只写边界、交付物和完成条件，规划与方案交给 agent 自己判断；需求和 AC 是下限，按意图做好。charter 用「产品意图」写出对需求的理解，契约写 intent。
13. **按知识边界分工**：项目层（pm）只持有需求原文、产品意图、模块清单、模块之间的边界（B-n）、项目验收标准和决策；模块层持有本模块的规格、接口、任务和代码，其他模块只看公开接口；开发任务只需要一份自包含的契约和自己的 owns。常驻会话（调度、等待开发）只做路由，调查、验收、写代码都在一次性会话里做，结果写成文件。

## 2. 整体结构

```
项目管理任务（W1，根任务，1 个）
 ├─ 创建 → 模块管理任务（W2，独立任务；baseline 最先，其他模块 blocked_by baseline，可并行）
 │          └─ 子任务 → 开发任务（W3，独立 worktree，base_branch=mod/<模块>）
 └─ 守护（Kandev automation，定时只读巡检，向上级告警）
```

- 模块任务**不挂在**项目任务下面。Kandev 常规看板的子任务只有一层，所以模块用 `message_task_kandev` 向 pm 上报。
- **知识分层**：

  | 层 | 持有的知识 | 不碰 |
  |---|---|---|
  | 项目层（pm） | 需求原文、产品意图、模块清单、模块边界（charter「模块边界」B-n）、项目验收标准、决策 | 模块内部、任务细节、代码 |
  | 模块层（模块 agent） | 本模块的规格、接口、任务、代码 | 其他模块的内部（只看公开接口） |
  | 任务层（开发） | 一份自包含的契约（接口片段和需求原话已摘入）和自己的 owns | 其他任务 |

  跨模块信息按顺序取得：① 读对方的 `interfaces.md` 和 charter「模块边界」；② 不够 → 向担当模块发 QUESTION，只问事实，回答给文件指针，提问方记进自己 spec 的「依赖」节；③ 对方已完成 → 读它的 `acceptance.md` 和模块分支上的代码，仍不清楚问 pm；④ 变更接口只能经 pm（ESCALATE → DECISION + ADR）。
- **baseline 模块**：模块清单第一个固定是 `baseline`（`kind: baseline`），走普通的 W2 + W3，契约是原「环境基线」步骤的要求（environment.md、AGENTS.md、冒烟测试、检查脚本、共享骨架、显式开关、约束落实、结合测试工具）。环境和骨架因此也经过审核和验收。其他模块都依赖它，分支从 `mod/baseline`（或所依赖的功能模块的分支）切出。
- **结合测试模块**（`integration_test` 不是 off 时）：模块清单最后一个模块 `integration-test`，依赖全部其他模块。其他模块完成后它自动启动，把所有模块分支合并到集成分支，对组装起来的产品写并运行自动化结合测试；测出的缺陷经 pm 交给担当模块的修复模块任务。见第 4–6 节。
- **常驻会话只做路由**：W1「调度」和 W2「等待开发」不论对话历史是否还在，都以 NOW 和文件为准，按事件转交；调查、验收、写代码都在一次性会话里做，结果写成文件。
- **合并冲突也是修复项**：结合测试模块、重新合并、项目验收遇到冲突都不自行解决：`merge --abort`，写成修复项（冲突的文件、两个模块，担当 = 后合入的模块），由 pm 建修复模块任务（从集成分支切出，合入担当模块的分支并解决冲突）。
- **修复模块做轻**：scope `mod:<模块>-fix-<n>`，用自己的 `modules/<模块>-fix-<n>/`，原模块目录只读；通常一个任务；验收只复跑修复项对应的失败测试和合并门禁。认为缺陷归属判错（不归本模块或是测试写错）时带证据报 misrouted，pm 转回结合测试模块重新判断，这一轮不计入修复轮数。
- **修复项与路由备注**：验证者（审核、模块验收、项目验收）把每个不通过项写成可直接下发的修复项（编号、担当模块或任务、复现步骤、期望、实际、疑似位置、对应的失败测试或验收条目）；与本步骤无关的 KMSG 不处理，原文记入本轮记录的「转交」节。常驻会话和 pm 下发修复时，契约 = 指向原修复项或缺陷的指针（文件 + 编号）+ 不超过两句的备注，不改写、不追加要求。

### 角色与 profile

| 角色（profiles.json 的键） | 用在哪里 | 模型建议 | 会话 |
|---|---|---|---|
| `pm` | W1 立项规划 / 模块下发 / 调度 / 刷新 | 强模型 | 长期存在；调度进入时重置上下文 |
| `plan_auditor`（可选，缺省 = auditor） | W1 立项评审 | 上下文小、影响最大，适合最强模型；profile 必须与 pm 不同 | 每次新会话 |
| `auditor` | W1 项目验收 | 强模型，profile 必须与 pm 不同 | 每次新会话 |
| `module`（可选，缺省 = pm） | W2 模块规划 / 等待开发 / 刷新 | 强模型 | 一个模块一个会话；等待开发进入时重置上下文 |
| `module_auditor`（可选，缺省 = auditor） | W2 验收调查 | 强模型，profile 必须与 module 不同 | 每次新会话 |
| `developer` | W3 开发 | 主力编码模型 | 一个任务一个会话，被退回时复用 |
| `reviewer` | W3 审核 | profile 必须与 developer 不同，最好换厂商 | 每次新会话 |
| `mechanical` | W3 合并（合并门禁）、W1 收尾合并 | 编码模型（要能读懂失败输出、在自己范围内解决冲突） | 每次新会话；用机械工作的短头部，NOW 只读不执行 |
| 守护 | Kandev automation；判断由 `kandev/stage.py` 完成 | 便宜模型 | 每次运行一个新会话 |

## 3. 运行模式

pm 任务描述的 `[TASK v1]` 头写 `mode: attended | unattended`，模块任务和开发任务继承同一个值。

| | attended（默认） | unattended |
|---|---|---|
| 立项确认 | 立项评审通过后，等用户确认 | 立项评审通过后直接进入模块下发 |
| 向用户提问 | 可以，合并成一次提问（每题附推荐答案） | 不提问。自行决定，写 ADR，登记到 `project/attention.md` |
| 环境需要用户配置（例如 Copy files） | baseline 模块升级给 pm，pm 请用户配置 | 选择不依赖用户配置的方案，pm 写 ADR |
| 人工终审 | 用户 | 用户（回来后处理） |

**plan_only**（`[TASK v1]` 头 `plan_only: true`）：不论 mode，立项评审通过后都停在「立项确认」。用户先检查 charter 和需求覆盖表，满意后拖到「模块下发」继续，再投入开发额度。

**integration_test**（`[TASK v1]` 头 `integration_test: auto | off`，缺省 auto）：auto 时 pm 在 charter 中加入结合测试模块，其他模块全部完成后自动开始结合测试；off 时不加，各模块分支在项目验收时才第一次合并。

用户只需要看两处：`project/attention.md`（需要用户决定的事，每项附推荐答案和默认做法）和 `agents/guard/stage.md`（系统现在在等谁，由守护脚本生成）。

## 4. W1 项目管理

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | 待立项 | — | 停放 | 发消息 → 立项规划 |
| 1 | **立项规划** | pm | 初始化管理目录；写 charter（需求 R-n 原文、模块清单（baseline 最先、结合测试模块最后）、模块边界 B-n、PA 及 covers）、conventions、ADR、attention；不写代码 | 完成信号 → 立项评审 |
| 2 | 立项评审 | plan_auditor | 独立评审 charter：需求覆盖表（每条 R 一行）+ 第 1–6 项每项一行结论（含模块规模、模块边界覆盖、baseline 模块），写进任务文档 `charter-review` | 退回 → 立项规划（≤2 次）；第 3 次仍有阻塞问题 → 写进 charter-review，立项确认（不论 mode）；通过：plan_only 或 attended → 立项确认，unattended → 模块下发 |
| 3 | 立项确认 | 人（会话绑定 pm） | 门禁（attended 或 plan_only） | 拖到模块下发 = 批准；在 pm 会话发消息 = 带意见回到立项规划 |
| 4 | 模块下发 | pm | 按状态，不按进入次数：先创建还没建的模块（建 `mod/baseline` 分支，baseline 最先，契约为脚本中的固定文本；其余模块 blocked_by baseline，从 `mod/baseline` 或所依赖的模块分支切出；结合测试模块最后）；再把待修复项和终审意见按指针下发为修复模块任务；都没有才是无事可做 | 完成信号 → 调度 |
| 5 | 调度 | pm | 常驻、只做路由（进入时重置上下文）：处理上报、升级、提问、告警；结合测试缺陷或合并冲突 → 为担当模块建修复模块任务，修完通知结合测试模块重跑；影响到已完成模块的决策也建修复模块任务 | 全部模块完成后，agent 自己移到项目验收 |
| 6 | 项目验收 | auditor | 建立或更新集成分支（从基线分支切出），合并全部模块分支，运行全量测试和结合测试，验证 PA，逐条核对 R；写 final-report（含额度用量、终审运行方式、需要用户处理、临时资源）；fail 和合并冲突写成修复项 | 没有 fail，或第 3 次仍有 fail（列入需要用户处理）→ 人工终审；有 fail → 模块下发 |
| 7 | 人工终审 | 人（会话绑定 pm） | 门禁 | **拖到收尾合并 = 批准**；在 pm 会话发消息 = 带意见回到模块下发 |
| 8 | 收尾合并 | mechanical | 集成分支合入基线分支、跑冒烟测试、清理临时资源、按记录恢复推送地址、把 status 设为 done | 完成信号 → 完成 |
| 9 | 完成 | — | 任务完成 | — |
| 10 | 刷新 | pm | 重置上下文后，移回原步骤（移动 instructions 中的 `刷新返回：` 优先，其次 NOW） | agent 自己移动 |

## 5. W2 模块管理

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | **模块规划** | module | 写 spec（MA 及 covers，覆盖契约的验收要点和相关 B-n）/ interfaces（落实本模块提供的 B-n）/ tasks.json（每个任务带 `tests`、`boundaries`）；运行 `tools/check_tasks.py`；创建自包含契约的开发子任务：无前置的进「开发」，有前置的进「待开发」 | 完成信号 → 等待开发 |
| 1 | 等待开发 | module | 常驻、只做路由：回答子任务提问；处理「等待决策」中的任务和合并门禁升级（移回「开发」并带 instructions、移到「完成」或拆分）；REPORT 到达时更新 tasks.json，放行前置已合入的「待开发」任务；按验收者的修复项建修复子任务 | 子任务全部终态（on_children_completed），或每轮结束前自己判断全部终态、无 held、无等待中的 DECISION → 验收调查 |
| 2 | 验收调查 | module_auditor | 独立的模块验收者（新会话）：先查子任务状态（tasks.json 标了 failed / dropped 的不算问题）；覆盖核对；跑模块测试，逐条判定 MA（pm 已接受的已知问题记 unverified）；写 acceptance.md 本轮一节和修复项。修复模块只核对修复项 | 通过 → REPORT 给 pm，完成；有 fail → 等待开发（第 3 轮或涉及其他模块时先 ESCALATE 给 pm） |
| 3 | 完成 | — | | |
| 4 | 刷新 | module | 重置上下文后移回原步骤（instructions 优先，其次 NOW）；如果子任务已全部终态，直接去验收调查 | agent 自己移动 |

验收者不写 tasks.json（单写者）：退回时模块 agent 按 acceptance.md 回写 `passes`；验收通过后模块随即结束，以 acceptance.md 最后一轮为准。

**baseline 模块**（任务描述头有 `kind: baseline`）：模块 agent 写 `project/environment.md`（命令和结果取自子任务的 report），执行不属于代码的落实动作（`git remote set-url --push`、初始化额度账本）；仓库中的文件由开发子任务完成，经审核和合并门禁。需要用户配置（Copy files）时升级给 pm。验收者在全新 worktree 中运行冒烟测试和检查脚本。

**结合测试模块**（任务描述头有 `kind: integration`）走同样的步骤，内容不同：

| 步骤 | 不同之处 |
|---|---|
| 模块规划 | 先在自己的任务 worktree 中建立或更新集成分支，合并所有其他模块的分支（冲突写成修复项交 pm），再从它切出 `mod/integration-test`（所以它拿到的是全部模块的最新代码）。MA 是跨模块的用户场景；子任务是结合测试任务（`kind: integration-test`，owns 在结合测试目录内） |
| 等待开发 | 结合测试任务上报缺陷（每条写明担当模块，任务停在「等待决策」）时，不自己修、不自行确认：ESCALATE 给 pm。pm 通知修复完成后，把修复分支合并进集成分支和 `mod/integration-test`，把该任务移回「开发」重跑；pm 转来 misrouted 时同样移回，让测试任务重新判断 |
| 验收调查 | 运行全量测试和结合测试命令，逐条场景核对 |

## 6. W3 开发

| # | 步骤 | 角色 | 做什么 | 流转 |
|---|---|---|---|---|
| 0 | 待开发 | — | 停放有前置任务的子任务（不计 WIP，不启动会话） | 前置合入后由模块 agent 移到开发 |
| 1 | **开发**（WIP 4） | developer | 冒烟测试（还没有时跳过）→ 按自包含的契约实现（`shared` 文件只追加条目）→ 测试 + owns 检查 → 写 report → commit；无需改动 → 建议 dropped；做不完 → blocked | 完成信号 → 审核；dropped / blocked / 缺陷 → 向模块 agent 发 ESCALATE（message_task），自己移到等待决策；普通提问留在开发 |
| 2 | 审核 | reviewer | 原样重跑测试和 owns 检查；每条 AC 写出亲自确认的证据（不能确认的写 unverified），至少抽查 1 个边界情况；写 review | pass → 合并；minor → 开发（≤3 轮，从模块 agent 最近一次 INSTRUCT / 改契约之后算起）；direction → 等待决策并 ESCALATE |
| 3 | 等待决策 | — | 不计 WIP；审核方向性问题、开发的 blocked / dropped / 缺陷上报在此等模块 agent | 模块 agent 带 instructions 移回开发，或移到完成 |
| 4 | 合并 | mechanical | 合并门禁：先核对是否已合入；rebase 到最新模块分支；运行 environment.md「合并门禁」的命令和 owns 检查；通过后本地方式自己快进合入模块分支，PR 方式提 PR；都向模块 agent 发 REPORT | 本地合入 → 完成；PR 合并 → 完成；门禁失败 → 开发（第 3 次 ESCALATE 给模块 agent） |
| 5 | 完成 | — | | |

**结合测试任务**（契约标注 `kind: integration-test`）：开发按 environment.md「结合测试」的工具，对真实组装的应用写自动化测试，断言用户可见的结果和数据状态；自动化工具做不到的场景才手动操作产品，并写明原因和证据。测试因为产品缺陷失败时，保留失败的用例，report 写 `result=blocked` 和 `defects`（每条写明担当模块和疑似位置），上报模块 agent，不改断言、不加 mock、不跳过。审核核对测试跑的是真实应用，没有用 mock、skip 或放宽断言换取通过。

开发和审核在测试、截图等方面的具体要求见 [开发项目约定](project-conventions.md)。

## 7. 上下文与连续性

任务文档通过当前 Kandev 的任务计划保存：`## task-doc: now` / `report` / `review` / `charter-review`。先读取完整计划和版本，创建或精确更新所属命名章节；保留其他章节及用户内容，冲突重读合并，保存后读回。开发写 now/report，审核写 review，立项评审写 charter-review；模块按子任务 ID 读取交付章节。旧的 `write_task_document_kandev` / `get_task_document_kandev` 不作为必需接口。

- **预防**：按知识边界分工，每个 agent 只读自己这一层需要的文件；一个任务一个会话；跨步骤靠 handoff、任务文档和管理目录传递信息；常驻上下文保持很小（AGENTS.md ≤150 行，prompt 稳定、不含时间戳，这样有利于缓存命中）。
- **常驻步骤以文件为准**：「调度」「等待开发」的 on_enter 带 reset_agent_context；但从「验收调查」回到「等待开发」时发生 profile 切换，平台可能不执行重置，所以 prompt 写的是"不论对话历史是否还在，都以 NOW 和文件为准"。
- **刷新**：常驻步骤的会话过长时，agent 先把 `刷新返回：<步骤>` 写进 NOW，再移到「刷新」步骤；守护把无响应的 pm 移到「刷新」时，把 `刷新返回：<原步骤>` 写在移动的 instructions 里（刷新步骤优先读它）。刷新步骤进入时重置上下文，然后移回原步骤。Kandev 不允许把任务移到当前步骤，所以必须经过这个中转步骤。
- **守护**：每个 workspace 一个 Kandev automation，每 15–20 分钟运行一次，自己发现所有进行中的项目，只读巡检，向上级发 ALERT。由 `kandev/stage.py` 按固定的规则表判断每个任务"在等谁"（第一条匹配的生效），守护只执行脚本给出的告警，并生成 `agents/guard/stage.md` 给用户看。规则见 `mgmt-template/roles/guard.md`「阶段分类」。
- **恢复时先核对外部状态**：重复创建任务、合并、推送、真实调用、删除资源之前，先查实际状态，已经生效的不再做。刷新步骤先核对 NOW「未确认的意图」。

## 8. 并发与 WIP

- 「开发」步骤的 WIP 是所有模块共用的全局上限（默认 4），用来控制本机同时运行的 agent 数量。
- Kandev 的 WIP 按"任务在这个步骤里"计数，被 blocked_by 阻塞的任务也会占名额，并行会被依赖链拖成串行。所以 W3 有一个不计 WIP 的「待开发」步骤：有前置的任务以 `start_agent=false`、`start_when_unblocked=false` 创建在那里，前置合入后由模块 agent 移到「开发」。
- 依赖链仍建议尽量浅，必须串行的工作合并成一个任务。
- 所有模块都 blocked_by baseline；其余模块之间有依赖关系的用 blocked_by（并从依赖模块的分支切出），能在骨架上并行的不设依赖。
- 等模块 agent 决定的开发任务（blocked / dropped / 缺陷上报）移到不计 WIP 的「等待决策」，不占「开发」的名额。

## 9. 分支与合并

```
基线分支 ← 收尾合并 ← integration ← 项目验收 ← mod/<模块> ← 合并门禁（快进）/ PR ← 开发 worktree 分支
                                                  ↑ 从 mod/baseline 切出（mod/baseline 从基线分支切出）
```

- 「模块下发」从基线分支建立 `mod/baseline`；没有功能依赖的模块分支从 `mod/baseline` 切出，依赖其他功能模块的从所依赖的模块分支切出（多个依赖时 base 写其中一个，其余在模块规划第 1 步合并进来），这样界面模块能对着真实的后端代码开发。用户的基线分支在「收尾合并」之前不被改动。
- 合并冲突（模块规划、结合测试模块、项目验收）不自行解决，写成修复项交 pm，见第 2 节。
- 开发子任务通过 `base_branch=mod/<模块>` 从模块分支切出。合并步骤 rebase 到最新模块分支、通过合并门禁后，本地方式自己快进合入（例如 `git fetch . HEAD:mod/<模块>`，只允许快进；失败说明别的任务先合入，重新 rebase），PR 方式提 PR。
- 结合测试模块在规划时建立 integration 分支（从基线分支切出），合并所有其他模块的分支（包括 `mod/baseline`），`mod/integration-test` 从 integration 切出。
- 修复模块任务（`mod/<模块>-fix-<n>`）从集成分支切出；修完后由结合测试模块（或项目验收）合并进集成分支。
- 项目验收更新 integration 分支，合并 registry 中的全部模块分支；没有结合测试模块时由项目验收建立。
- 用户在人工终审中批准后，「收尾合并」把 integration 合入基线分支，并按 environment.md「约束落实」的记录恢复各 remote 的推送地址（baseline 模块禁用推送时记下原地址；项目结束后仓库归还用户）。
- 合并方式（本地或 PR）、合并门禁命令、是否推送远端，由各项目的 environment.md 规定，见 [开发项目约定](project-conventions.md)。

## 10. 与开发项目的边界

架构只规定**谁、在哪一步、怎样**处理项目约定，具体内容（额度、副作用、约束清单、测试命令、截图、合并与推送）属于每个被开发项目，见 [开发项目约定](project-conventions.md)。

| 架构规定的 | 位置 |
|---|---|
| 立项规划把约定写进项目的 conventions；baseline 模块把能强制的约束落实为代码 | W1 立项规划；baseline 模块（W2 + W3） |
| 开发上报前、审核时运行检查脚本；合并前运行合并门禁；复跑测试按 environment.md 原样执行；environment.md「共享文件」列出多个任务都要追加条目的文件（tasks.json `shared`） | W3 开发、审核、合并 |
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
integration_test: auto      # auto：其他模块完成后自动做结合测试；off：不做
mgmt_root: <管理目录绝对路径，放在仓库与 worktree 之外>
mgmt_template: <本仓库 mgmt-template 的绝对路径>
repo: <主仓库绝对路径>
role: pm
scope: pm
parent: user
pm: self
branch: <自动> base <基线分支>
---
<项目目标、需求（按重要度排序，一条一行，pm 会逐条摘录为 R-n）、约束、技术栈与环境要求（交给 baseline 模块落实）、额度约定（见开发项目约定）>
```

pm 创建的模块任务头示例（baseline / 普通模块）：

```
[TASK v1]
role: module
scope: mod:baseline            # 普通模块：mod:<模块>
kind: baseline                 # 普通模块省略；结合测试模块：integration
mode: <同 pm>
mgmt_root: <同 pm>
parent: pm @ task <pm 任务 id>
pm: task <pm 任务 id>
branch: mod/baseline base <基线分支>   # 普通模块：mod/<模块> base mod/baseline（依赖其他功能模块时 base mod/<依赖模块>）
---
<模块契约>
```

## 12. 已知限制

- 外部 MCP 没有 `message_task_kandev`，也不能创建 automation。外部的守护或观察者只能移动任务、代答提问和权限请求。需要这些能力的工作写成交接 prompt（`kandev/handoff/`），交给 Kandev 内部的 agent 执行。
- `on_children_completed` 只在任务处于「等待开发」时生效。刷新步骤会检查子任务状态，补上这个缺口。
- 会话里的上下文用量 Kandev 有记录，但 MCP 读不到，所以守护只能看间接信号。
- 导出的 workflow 文件只按 model / mode 记录 profile。同模型的 profile 有多个时可能匹配错，所以部署用 `build_workflows.py`，它按 ID 绑定。
- 门禁中的用户消息投递给用户所在的会话标签，而不是下一步骤的会话；由用户消息触发的移动也不一定会把下一步的步骤 prompt 送达。所以：门禁步骤绑定 pm profile（进入门禁时评审会话关闭，当前会话换成 pm 的）；pm 收到用户直接消息时自己判断所处步骤并处理（【用户直接消息】）；评审会话万一收到，就转发给 pm 会话（registry 中的 `kandev_session_id`）；pm 再次进入「立项规划」「模块下发」时从多个来源收集意见。如果 pm 仍没有开始工作，把任务移到门禁再移回该步骤，并在 instructions 中附上意见原话。
- 「待开发」依赖两点 Kandev 行为，部署后要先验证（见 [AGENTS.md](../AGENTS.md)「验收部署」）：`create_task_kandev` 带 `workflow_step_id`、`start_agent=false`、`start_when_unblocked=false` 时任务停在该步骤、不启动会话，前置完成时也不自动启动；从无 agent 步骤移到「开发」会触发 on_enter 的 auto_start。PR 方式下模块 agent 不会被 PR 合并事件唤醒，靠守护的 `hold_ready` 告警放行。
- 合并步骤发 REPORT 后才调用 step_complete_kandev，所以放行的条件是"前置的 REPORT 已到且提交已在模块分支上"，不等 Kandev 状态；移动被平台拒绝（前置还没到「完成」）时本轮结束前再试一次，仍不行靠下一次唤醒（其他事件或守护的 `hold_ready`）。
- 「等待开发」和「验收调查」交替时，模块 agent 的会话（profile `module`）和验收者的会话（profile `module_auditor`）在同一个 Kandev 任务里轮换；等待开发以 NOW 和文件为准，不依赖之前的对话。

## 13. 已否决的设计

试过或评估后放弃的方案，留下原因，避免以后再走回去。

| 方案 | 否决原因 | 现在的做法 |
|---|---|---|
| 常驻步骤"移到本步骤 + reset_context"来刷新 | Kandev 的 entry_options 要求真的换步骤，移到当前步骤是 no-op | 「刷新」中转步骤 |
| 门禁交给外部定时守护放行 | 轮询间隔 20 分钟，门禁平均要等约 10 分钟 | 立项评审在 workflow 内放行 |
| 只靠测试配置的默认值挡住消耗额度的调用 | 一个命令行参数就能覆盖，实跑中出现过真实调用超限 | 显式开关 + 代码检查 + 额度账本 |
| 管理目录 `git add -A` | 会把别人担当的文件一起提交 | 只 add 自己的路径 + pre-commit 钩子 |
| 立项确认设置 session_target | 疑似多出一个空会话 | 不设置；改为给门禁步骤绑定 pm profile |
| 门禁步骤不绑定 profile，靠 on_turn_start 把消息带回 pm 的步骤 | 门禁继承了评审的会话，用户在评审会话里回复，消息留在评审那里，pm 会话被唤醒却没收到 prompt（实测） | 门禁绑定 pm profile + pm 多来源收集意见 + 评审转发 |
| prompt 里大量限制性条款（只做契约内的事、不做顺手优化、不写实现方案、不提风格、只核对字面条件、模块数和依赖层数写死） | 字面全部通过但用户觉得简陋，mock 下通过的功能在真实使用中失败（实测）；限制压制了模型本身的判断力 | 原则 12：只保留边界和完成条件，方案交给 agent；一条简短的【主动性】规则 |
| 有前置的任务直接放在「开发」用 blocked_by 等待 | 阻塞的任务也占 WIP，并行被依赖链拖成串行 | 停在不计 WIP 的「待开发」，由模块 agent 放行 |
| 用 Kandev 的 pull_from_step 把任务从「待开发」拉进「开发」 | 不确定拉取时是否检查 blocked_by；放行条件（前置已合入）由模块 agent 判断更明确 | 模块 agent 移动 |
| 开发等待模块回答时移到不计 WIP 的「等待回答」步骤 | 回答通过 message_task 开启新一轮，在无 agent 步骤里的行为没有验证 | 暂不采用 |
| 守护用 LLM 读信号做判断 | 不可重复、难测试 | `stage.py` 规则表 + 回归测试 |
| 每个项目单独创建一个守护 automation | 每次启动项目都要手动配置，项目结束还要清理 | 每个 workspace 一个守护，从 pm 任务的 `[TASK v1]` 头自己发现项目 |
| 从对话正文或报告自由文本推断"是否在等人" | 需要结构化事实 | 只用 Kandev 状态、待处理的提问和权限请求 |
| 各模块分支到项目验收才第一次合并，验收只运行已有测试 | 没有任何任务负责写跨模块测试，验收者也不能写代码；各模块都通过，但界面删除后仍然显示、无法删除（实测） | 结合测试模块：其他模块完成后合并、写自动化结合测试 |
| 所有模块完成后由 pm 在「调度」再下发结合测试任务 | 「模块下发」的再次进入已用于待修复项和终审意见，要多一种进入原因和一个 W1 循环 | 首次下发时就创建，blocked_by 全部其他模块；分支在它启动时才建立，所以仍能拿到最新代码 |
| pm 自己做环境基线（W1「环境基线」步骤） | pm 要写代码，骨架和脚本没有审核和验收，pm 的上下文里堆满环境细节 | baseline 模块走 W2 + W3，经审核、合并门禁和模块验收 |
| 模块 agent 自己验收自己的模块 | 规划者验收自己的规划，容易只核对自己写下的 MA，漏掉契约要点和模块边界；常驻上下文也越积越多 | 「验收调查」由独立的模块验收者（module_auditor，新会话）做，先做覆盖核对 |
| 模块 agent 逐个合并子任务分支 | 常驻会话要读 diff、跑测试、处理冲突，上下文膨胀，也成为串行瓶颈 | 合并步骤自己跑合并门禁并快进合入，模块 agent 只更新 tasks.json |
| 小项目变体：去掉 W2，pm 直接创建开发子任务 | prompt 里没有这条路径，pm 也不持有模块内部的知识；为它单独维护一套流程不划算 | 模块少也走 W2；模块可以只有一两个任务 |
| 结合测试模块自己修复缺陷 | 它不持有其他模块的知识，修复时要读别的模块内部，违反知识边界 | 缺陷写明担当模块，经 pm 交给担当模块的修复模块任务 |
