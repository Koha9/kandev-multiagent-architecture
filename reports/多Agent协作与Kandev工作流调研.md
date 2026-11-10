# 用外部真值与单写者驯服多 Agent 工程

多 agent 完成中到大型软件项目已有可核查的成功案例，例如 Anthropic 用 16 个并行 Claude 在两周内写出能编译 Linux 6.9 的约 10 万行 Rust C 编译器，OpenAI 用 Codex 在五个月内交付约百万行、零手写代码的内部产品。这些案例成功的原因并不在 agent 数量。它们共同依赖五样东西：一个接近完美的外部 oracle（测试套件、参考实现、端到端检查），"一个工作单元只有一个写者"的分工，一个上下文干净且被调成多疑的独立评审者，放在仓库里、机器可校验的持久状态，以及频繁重启上下文。代价也很明确：多 agent 的 token 消耗是单 agent 的 1.6 到 6 倍，甚至更高；在 SWE-bench 这类耦合紧密的编码任务上，所有多 agent 变体的得分都略低于单 agent。所以多 agent 只在任务可拆、有 oracle、价值足够高时才划算。Kandev（v0.99.1，2026-11-06）为这种模式提供了大部分原语：按步骤固定 agent profile、显式完成信号 `step_complete_kandev`、一层子任务加 `blocked_by` 依赖链、点对点的 `message_task_kandev`、单份共享 Plan、可移植的 YAML 导出和 GitOps 同步。它的约束同样明确：一个任务同一时刻只能处在一个步骤，没有条件分支，常规 Kanban 只允许一层子任务，共享工作区的多个会话之间没有写隔离，多 agent 的 Office 层仍是实验功能。GitHub 的 issue、sub-issue、PR、review、Actions 适合承载持久、对人可见、需要审核的工件，不适合承载高频的 agent 间对话和认领锁。合理的分工是：GitHub 存规格、PR 和门禁，Kandev 存运行时状态和 agent 间通信，仓库文件存知识与进度。

## 成功案例的规模可观，但每个都建立在 oracle 之上

最严格、最可核查的案例是 Anthropic 的 C 编译器实验。**16 个 Opus 4.6 agent、近 2,000 个 Claude Code 会话、约 20 亿输入 token 与 1.4 亿输出 token、成本略低于 2 万美元，产出约 10 万行代码**。这个编译器能在 x86、ARM、RISC-V 上构建 Linux 6.9，能编译 QEMU、FFmpeg、SQLite、Postgres、Redis，在包括 GCC torture tests 在内的多数编译器测试套件上通过率约 99% ([Anthropic](https://www.anthropic.com/engineering/building-c-compiler))。它的拓扑极简：没有编排者，也没有 agent 间消息。每个 agent 在自己的 Docker 容器里跑一个 `while true` 循环，在 `current_tasks/` 写锁文件来认领任务，并通过一个裸 git 仓库同步，冲突由 agent 自行解决。这套扁平结构之所以能运转，是因为失败的测试数量多且彼此独立，测试本身就在分派任务。作者同样公开了局限：16 位实模式仍要调用 GCC，没有自己的汇编器和链接器，全开优化后的产物还不如 GCC 不开优化。作者坦言，自己对"把测试通过误当成完成"这件事感到不安。

Cursor 走的是规模路线。数百个 worker 在接近一周内为一个从零写的浏览器产出 **100 万行以上、约 1,000 个文件**；同一套系统还完成了自家代码库 Solid 到 React 的迁移，历时三周，改动 +266K/-193K ([Cursor](https://cursor.com/blog/scaling-agents))。这个案例最有价值的部分是它的失败记录。第一版是扁平结构加共享锁，结果"20 个 agent 只发挥出 2 到 3 个的效果"。第二版改成乐观并发，agent 变得规避风险，只做小而安全的改动。最终架构是 Planner、Worker、Judge 三层：Planner 持续生成任务，Worker 之间互不协调，Judge 在每个周期末决定是否继续。专门负责质量与冲突的 integrator 角色反而成了瓶颈，被移除。不过这个浏览器随后被报道主分支 `cargo build` 失败（34 个错误）、CI 为红 ([The Register](https://www.theregister.com/2026/01/22/cursor_ai_wrote_a_browser/))。这说明吞吐量如果没有绿色 CI 门禁兜底，产出就无法验证。

OpenAI 的 "harness engineering" 实验用五个月交付了一个"手写代码为 0 行"的内部 beta 产品，代码库达到约百万行 ([OpenAI 摘录](https://openai.com/index/harness-engineering/))。二手资料补充说，团队从 3 名工程师扩到 7 名，合并约 1,500 个 PR，人均每天约 3.5 个 ([Orbital Witness](https://tech.orbitalwitness.com/posts/2026-07-22-grading-ourselves-against-the-harness-engineering-playbook/))；这组数字未能与英文原文核对，因为原文抓取时返回 403。这个案例最可迁移的经验有两条。第一，AGENTS.md 只写约 100 行，作用是一张地图，指向结构化的 `docs/` 记录系统；一份大而全的 AGENTS.md "以可预见的方式失败"，因为它无法被机械校验。第二，评审工作几乎全部转成 agent 对 agent，人工评审变成可选项 ([OpenAI it-IT](https://openai.com/it-IT/index/harness-engineering/))。

Anthropic 的长时 harness 系列讲清了成本与质量之间的交换。在复古游戏编辑器 RetroForge 上，**单个 Opus 4.5 跑 20 分钟、花 9 美元，核心功能不可用；完整的 planner-generator-evaluator harness 跑 6 小时、花 200 美元，成品明显更完整** ([Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps))。Cognition 在 2025 年发表《Don't Build Multi-Agents》，2026 年修正为"可行的是单写者、多贡献者"：干净上下文的评审循环平均每个 PR 抓到约 2 个 bug，其中约 58% 属于严重问题 ([Cognition](https://cognition.com/blog/multi-agents-working))。

| 案例 | 规模 | 拓扑 | 成功的关键 | 可信度 |
|---|---|---|---|---|
| Anthropic C 编译器 | 16 agent，约 10 万 LOC，约 2 万美元 | 扁平对等，锁文件加 git | 外部测试套件，GCC 差分 oracle，CI 门禁 | 高（外部可复核） |
| Cursor 浏览器等 | 数百 agent，100 万+ LOC | Planner、Worker、Judge | Planner 生成任务，Worker 独立执行 | 中（构建失败受到质疑） |
| OpenAI Codex 产品 | 约 100 万 LOC，5 个月 | agent 写、agent 评 | 短 AGENTS.md 地图，机械化规则 | 中（部分数据来自二手） |
| Anthropic 应用 harness | 单应用 125 到 200 美元 | Planner、Generator、Evaluator | 多疑的 evaluator 加硬阈值 | 高（附对照数据） |
| Cognition Devin | 企业规模使用 | 单写者加干净评审 | 干净上下文的 reviewer | 中（厂商自报） |

这些材料几乎全部来自有商业利益的厂商，而且没有任何一项在同一任务、同一规模下对扁平与层级拓扑做过 A/B 对照。所以表中"成功的关键"一列是跨案例归纳出的共性，并非已被证明的因果关系。

## 质量与稳定来自环境里的真值，不来自 agent 的自我评价

跨案例看，质量保障是分层的。最底层是 oracle。编译器实验强调测试必须"接近完美"，否则 Claude 会去解决错误的问题；当 16 个 agent 在编译内核这个单体任务上撞上同一个 bug、互相覆盖修改时，解决办法不是加一个经理 agent，而是**用 GCC 随机编译一部分文件作为差分 oracle，让不同 agent 撞上不同的 bug** ([Anthropic](https://www.anthropic.com/engineering/building-c-compiler))。第二层是共享分支上的 CI 门禁，用来禁止回归，Cursor 浏览器就是缺少这一层的反例。第三层是独立评审者。Anthropic 发现开箱即用的 Claude 是个糟糕的 QA：它能发现真问题，随后又说服自己放行。"把一个独立 evaluator 调成多疑，远比让 generator 批判自己的工作更可行"。他们的 evaluator 用 Playwright 实际操作应用，每个维度都设有硬阈值，任何一项不达标，整个 sprint 判为失败 ([Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps))。Cognition 的评审 agent 只看 diff，看不到编码者的上下文，他们的结论是"干净上下文带来显著的能力提升" ([Cognition](https://cognition.com/blog/multi-agents-working))。

学术证据支持同一方向。伯克利的 MAST 研究标注了 7 个开源多 agent 框架的 1,600 多条轨迹，**失败率为 41% 到 86.7%**。失败中约 44% 来自系统设计与规格（步骤重复占 15.7%，不清楚终止条件占 12.4%），约 24% 来自验证缺失或验证错误；在 ChatDev 上加一个高层目标验证步骤，任务成功率提升 15.6% ([MAST](https://arxiv.org/html/2503.13657v3))。多 agent 辩论在同等算力下很少能胜过廉价的 self-consistency 投票 ([Huang et al.](https://arxiv.org/pdf/2310.01798), [arXiv 2502.08788](https://arxiv.org/abs/2502.08788v3))。由此可以得出一条明确的立场：需要冗余时，用 best-of-N 加确定性测试；不要让多个 agent 互相辩论。真实世界的数据也给出了警示。AIDev 数据集收录了 45.6 万个 agent PR，在高星仓库中人类 PR 的合并率为 76.8%，Claude Code 为 52.5%，Copilot 为 38.2%；文档类 PR 是例外，agent 的合并率反而更高 ([AIDev](https://arxiv.org/html/2507.15003v1))。agent 最擅长的是窄而定义清晰的任务。

稳定性的关键在于防止循环失控。MAST 中最常见的两种单项失败模式，一是步骤重复，二是不知道何时停止，所以迭代上限和预算上限都不能省。Kim 等人在 260 种配置上做了对照，发现**独立并行结构的错误放大倍数为 17.2 倍，带集中验证的编排结构为 4.4 倍** ([Kim et al.](https://arxiv.org/html/2512.08296v3))。这说明需要有一个中心节点在合并前做验证，但这个中心节点不应该自己写代码。一份 "371 个 git worktree" 的实践报告得出了同样的结论：系统直到强制要求编排者只委派、从不写代码，才稳定下来 ([LevelUp](https://levelup.gitconnected.com/what-371-git-worktrees-taught-me-about-multi-agent-ai-36d4d61acfb5?gi=85d4d05bd94c))。

## 连续性与省 token 取决于什么进入上下文

所有能跨上百次重启存活的系统，都把会话当成一次性的，把持久状态放在模型之外。Anthropic 的长时 harness 先由一个 initializer 生成 `init.sh`、`claude-progress.txt` 和一份 **200 多条、初始全部为 `passes: false` 的 JSON 功能清单**。之所以用 JSON 而不用 Markdown，是因为模型不太会去不当改写 JSON；规则也规定 coding agent 只能翻转 `passes` 字段。此后每个会话都执行固定的启动协议：读 git log 和进度文件，挑一个最高优先级的未完成功能，启动应用并先跑一次冒烟测试，然后一次只做一个功能，完成后提交并更新进度 ([Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents))。单靠 compaction 不够用。Sonnet 4.5 会出现"上下文焦虑"，必须重置上下文；到了 Opus 4.5，这个问题基本消失，重置也随之被移除 ([Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps))。因此 harness 应该在每次模型升级后逐个拆掉组件，看哪些仍在承重。

token 方面，先要承认多 agent 很贵。**Anthropic 测得单 agent 约为聊天的 4 倍 token，多 agent 约为 15 倍** ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system))。Claude Code 的 agent teams 在 plan 模式下约为普通会话的 7 倍 ([Claude Code](https://code.claude.com/docs/en/costs))。Kim 等人测得多 agent 每千 token 的成功率只有单 agent 的 1/2 到 1/5；一旦单 agent 基线超过约 45%，再加 agent 就是负收益 ([Kim et al.](https://arxiv.org/html/2512.08296v3))。省 token 的有效手段集中在上下文入口，有五种。第一，子 agent 做上下文防火墙：探索时用掉几万 token，只返回 1,000 到 2,000 token 的摘要 ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))。第二，用文件而不是完整对话记录做交接。第三，裁剪工具输出：编译器实验只打印几行，细节写进日志，用可 grep 的 `ERROR` 标签标记；Claude Code 文档用 hook 把上万行日志压缩到几百 token。第四，保持字节级稳定的前缀以命中 prompt cache。Manus 称 KV-cache 命中率是生产 agent "最重要的单一指标"，其输入与输出之比约为 100:1 ([Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus))；Claude 的缓存读取价格为基础输入价的 0.1 倍，Opus 5.5 和 Sonnet 5.5 为 0.05 倍，而改动工具定义或 effort 参数会让缓存失效 ([Claude 文档](https://platform.claude.com/docs/en/build-with-claude/prompt-caching))。第五，常驻上下文要小。ICLR 2026 的研究发现，LLM 生成的 AGENTS.md 使成功率略降，开发者手写的也只提升约 4%，两者都让推理成本增加 20% 以上 ([arXiv 2602.11988](https://arxiv.org/abs/2602.11988))。Chroma 测了 18 个模型，**约 300 token 的聚焦提示在所有模型上都显著优于约 11.3 万 token 的完整提示** ([Chroma](https://www.trychroma.com/research/context-rot))，所以裁剪上下文同时提升准确性和降低成本。

上面这一整套里有一个真实分歧。Cognition 主张在需要一致决策时共享完整轨迹，而不是只给摘要，否则就会出现 Flappy Bird 例子里两个子 agent 各做一半、风格对不上的情况 ([Cognition](https://cognition.com/blog/dont-build-multi-agents))。调和的办法不是共享更多上下文，而是缩小需要共享决策的范围：同一份代码只交给一个写者，并行只发生在彼此真正独立的单元之间。

## Kandev 把工作流建模为单任务状态机加 MCP 协作层

以下描述基于 `kdlbs/kandev` 主分支 commit `52309e6`（2026-11-07）。Kandev 是 AGPL-3.0 协议、可自托管的 Go 单二进制，内嵌 React SPA，通过 `agentctl` 在本地、worktree、Docker、Kubernetes、SSH、Sprites 等执行器上运行 20 多种 agent CLI（主要通过 ACP 协议）。它版本迭代极快，九个月内从 0.0.1 发到 0.99.1，共 120 个版本，路线图把"稳定性"列为首要焦点 ([README](https://github.com/kdlbs/kandev/blob/main/README.md), [CHANGELOG](https://github.com/kdlbs/kandev/blob/main/CHANGELOG.md))。任何工作流设计都应锁定版本。

### 步骤与事件决定任务如何流动

一个 Workspace 下有多个 Workflow，一个 Workflow 是一组有序的 Step（即看板列）。每个 Step 可以配置提示词、agent profile 覆盖、WIP 上限、上游取任务的来源步骤（pull-from），以及事件触发器 ([models.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/models.go))。事件触发器有以下几类：`on_enter`（可执行 `auto_start_agent`、`enable_plan_mode`、`reset_agent_context`、`set_session_mode`，代码中还有 `run_code_review`），`on_turn_start`（用户发消息时触发，可移到上一步、下一步或指定步骤），`on_turn_complete`（agent 一轮结束时触发，有待回答的澄清问题时会被阻止），`on_exit`，以及由 PR 轮询器驱动的 `on_pr_merged` 和 `on_pr_closed`。`on_children_completed`、`on_comment` 等属于 Office 阶段的触发器 ([workflow-import-export](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md))。

**`on_children_completed` 的语义容易被误读**：所有直接子任务进入终态（完成、失败或取消）时它就会触发，所以"终态"意味着工作停止了，不意味着全部成功 ([coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md))。动作集合里只有"移到上一步、下一步或指定步骤"，没有"评审 FAIL 走 X、PASS 走 Y"这样的条件分支；社区为此开了 #4378（决策步骤）和 #4481（自动推进前要求明确的 PASS）两个 issue ([Issues](https://github.com/kdlbs/kandev/issues))。

内置模板有五个：Kanban、Plan & Build、Architecture、Feature Dev（Todo → Spec → Work → Review → QA → PR → CI Fixup → Done），以及 PR Review。其中 Feature Dev 的 Review 步骤先 `reset_agent_context` 再自动启动 agent，但**这个模板在各阶段之间不会自动推进** ([workflow-tips](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md))。提示词支持以下变量：`{{task_prompt}}`、`{task_id}`、`{task_title}`、`{step_entry_number}`（任务第几次进入该步骤），以及 `@name` 形式引用的共享提示词。

可靠推进依赖 ADR 0015 定义的显式完成信号。步骤开启 `auto_advance_requires_signal` 后，只有 agent 调用 `step_complete_kandev` 时才会触发流转；提问、限流、崩溃导致的中断都不会推进。信号携带三部分：必填的 `summary`；`handoff`，最多 8,192 字节，只投递到下一步的第一条提示词中，不会继续向后传；`blockers`，只写入流转历史，不发给下一个 agent ([ADR 0015](https://github.com/kdlbs/kandev/blob/main/docs/decisions/0015-explicit-completion-signal-for-auto-advance.md))。文档也明确警告，如果 agent 无法调用这个工具，步骤可能无限期等待。

### 会话传递、子任务与 agent 间通信都是显式的

步骤之间的会话规则如下：有效 profile 相同的相邻步骤沿用同一个会话；profile 不同时，目标步骤的 `profile_session_start_policy` 决定是 `reuse`（复用该 profile 下最新的会话）还是 `new`，源步骤的 `profile_session_end_policy` 决定原会话是 `complete` 还是 `park`；`reset_agent_context` 强制开启全新上下文；`session_target` 可以把某一步路由回任务的初始会话，或路由到更早某一步的会话 ([workflow-tips](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md))。end policy 的默认值在两份文档中互相矛盾，一份说是 `park`，另一份说是 `complete`，使用前需在 UI 或代码中确认。跨步骤的持久上下文有四个来源：每个任务唯一的共享 Plan（带版本历史，人可以编辑），一跳的 `handoff`，workflow 级提示词，以及仓库文件。这样就能原生实现 README 所说的"Claude Code Opus 做计划、Copilot Sonnet 实现、Codex 评审"式的异构管线 ([README](https://github.com/kdlbs/kandev/blob/main/README.md))。

协作有三种边界，见下表 ([coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md))。

| 需求 | 机制 | 文件系统 | 独立的工作流状态 |
|---|---|---|---|
| 另一个 agent 处理同一批文件、同一目标 | 同任务内追加命名会话（`spawn_session_kandev`） | 共享，**无写锁** | 否 |
| 子任务需要看到父任务未提交的改动 | 子任务，`inherit_parent` | 共享父工作区 | 是 |
| 并发写者或跨仓库工作 | 子任务，`new_workspace` | 独立 worktree | 是 |
| 一个交付物涉及多个仓库 | 多仓库任务 | 每个仓库一个 worktree | 否 |

`create_task_kandev` 支持以下参数：`parent_id`、`workspace_mode`、`autopilot`（开启后子任务只能用 `ask_parent_question_kandev`，不能直接问用户）、`agent_profile_id`、`workflow_step_id`、`blocked_by`、`external_id`（幂等键）。**常规 Kanban 只允许一层子任务**，子任务若再创建子任务，会被降级为兄弟任务；更深的树属于 Office。依赖关系与父子关系是两张独立的图：被阻塞的任务不会被任何自动路径启动，只有所有前驱都成功之后才启动，A → B → C 这样的链因此可以自动推进；前驱失败则下游保持阻塞 ([tasks-and-workflows](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md))。

agent 之间的通信是点对点的。`message_task_kandev` 只要知道对方任务的完整 UUID，就能跨工作区投递。目标会话正在运行时，消息进入 FIFO 队列（默认每个会话最多 10 条）；目标空闲时，消息开启新的一轮；只有直接父任务能用 `interrupt` 模式打断子任务。**任务之间没有持久通道，也没有广播**，回复就是反向再发一条消息 ([agent-communication](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md))。

MCP 工具分成几个包。Core 包是必需的，涵盖发现、任务生命周期、协作、Plan 与文档、分支、PR/MR、Canvas 等约 50 个工具。Configuration 包默认关闭，必须由人按任务手动勾选，agent 无法给自己授权；它负责增删改工作流和步骤、导入导出、管理 profile 和设置 ([builtin_catalog.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/mcp/profile/builtin_catalog.go))。此外，外部 MCP 端点允许 Kandev 之外的 agent 回答问题、处理权限请求。

### 人工审核靠"什么都不做"的步骤和 Review 面板

在常规 Kanban 中，人工门禁就是一个 `on_turn_complete` 设为 "Do nothing" 的步骤，"批准"等于人把卡片拖走；没有一等的批准、驳回记录，也没有法定人数（quorum）机制，这些只存在于实验性的 Office。审核界面包括：Plan 面板（可编辑、可评论，可"在全新 agent 中实施"），diff Review（逐行或整文件评论，点 "Fix comments" 打包发给 agent），以及 walkthrough。需要注意，**待提交的 diff 评论只保存在浏览器的 `sessionStorage` 中**，不会写入后端，因此不能当作 agent 之间的持久评审工件 ([sessions-and-review](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md))。PR 面板可以开启"自动修 CI 与处理评论"，约每分钟轮询一次，每个 PR 最多修 10 轮；Review Watch 和 Issue Watch 按 GitHub 搜索条件把 PR 或 issue 自动建成任务 ([integrations](https://github.com/kdlbs/kandev/blob/main/docs/public/integrations.md))。

### 配置可移植，但匹配规则很脆

工作流存放在 SQLite 或 Postgres 中，可以导出为 `type: kandev_workflow` 格式的 YAML，版本有 1、2、3 三种：v2 增加 `session_target`，v3 增加 profile 的 `config_options`，导出器会自动选择能容纳内容的最低版本 ([export.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/export.go))。导入时按工作流名称去重；`move_to_step` 以步骤位置表达，导入后重映射到新 ID；**agent profile 按显示名、模型、模式精确匹配，匹配不上时静默置空**；Office 的参与者和决策记录不可移植。Workflow Sync 可以按固定间隔（默认 300 秒）从 GitHub 或 GitLab 仓库的 `.kandev/workflows` 目录只读同步配置。步骤按名称匹配，所以给步骤改名等于删除再新建；如果旧步骤上还有任务，整个工作流的更新会被跳过 ([workflow-sync](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-sync.md))。

已知限制归纳如下：一个任务同一时刻只在一个步骤，没有并行分支；没有条件路由；只有一层子任务；共享工作区的会话没有写隔离；worktree 只隔离文件，不隔离凭据、端口和后台进程；任务 UUID 本身就是路由凭证，应当视为敏感信息；文档存在漂移，根目录 `docs/` 与 `docs/public/` 互相矛盾。与多 agent 相关的未关闭 bug 集中在步骤提示词的投递上。#3336：没有配置 `auto_start_agent` 时，步骤提示词被静默忽略。#5137、#5178：重启或启动时提示词丢失。#5173：`already_signaled` 会吞掉最新的修正。#4152：多个 agent 同时自动启动时 ACP 初始化失败 ([Issues](https://github.com/kdlbs/kandev/issues))。Windows 支持据社区反馈弱于 macOS 和 Linux，不过这条来源是二手的 ([Reddit 快照](https://reddit.sentinel-team.org/posts/1thyq22/snapshots/2026-05-20T00%3A16%3A29.879841Z))。

## GitHub 擅长持久记录与门禁，不擅长高频的 agent 对话

GitHub 已经把 issue 和 PR 变成了多厂商 agent 的派发界面。2026 年 2 月起，可以在 Assignees 中把同一个 issue 指派给 Copilot、Claude、Codex 中的任意一个或全部三个，再在 PR 评论里用 `@claude`、`@codex` 要求修改，每个会话消耗一次 premium request ([Changelog 02-04](https://github.blog/changelog/2026-02-04-claude-and-codex-are-now-available-in-public-preview-on-github/), [Changelog 02-26](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/))。结构化原语也已具备：每个父 issue 最多 100 个 sub-issue、最多 8 层嵌套，可用 `gh issue edit --add-sub-issue` 添加 ([GitHub Docs](https://docs.github.com/en/enterprise-cloud@latest/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues))；issue 依赖（blocked by / blocking）已 GA，每种关系最多 50 个，支持 API 和 webhook ([Changelog 2025-08-21](https://github.blog/changelog/2025-08-21-dependencies-on-issues/))。GitHub Agentic Workflows（gh-aw）把 Markdown 编译成 Actions：agent 默认只读，所有写操作通过有数量上限的 "safe outputs" 白名单在独立 job 中执行，例如 `add-labels`、`link-sub-issue`、`assign-to-agent`、`dispatch-workflow`。这是目前最成熟的"agent 安全写 GitHub"模式，但其 README 也要求"谨慎的人工监督" ([gh-aw](https://github.com/github/gh-aw), [Safe Outputs](https://github.github.com/gh-aw/reference/safe-outputs/))。

GitHub 的硬约束主要有三类。**第一是速率**。认证用户 REST 每小时 5,000 次，但 Actions 中的 `GITHUB_TOKEN` 每仓库每小时只有 1,000 次，内容创建类请求约每分钟 80 次、每小时 500 次 ([REST 限额](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api))。更隐蔽的是，由 `GITHUB_TOKEN` 产生的事件通常不会触发新的 workflow ([GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token))，基于标签或评论串起来的 agent 链会因此静默断掉。**第二是延迟与原子性**。Copilot 的 Actions 会话上限为 59 分钟；修改 assignee 或标签不是 compare-and-swap 操作，两个 worker 可能同时认领同一个任务。**第三，也是最关键的，是安全**。issue、PR、评论里的文本都是不可信输入。Invariant Labs 演示了恶意 issue 诱导带有私有仓库权限的 agent 把私有数据泄露到公开 PR ([Invariant](https://invariantlabs.ai/blog/mcp-github-vulnerability))；2026 年 4 月的 "Comment and Control" 用 PR 评论让三家厂商的 Action 把 API key 贴进公开评论或日志 ([CSA](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/))。

把这些放在一起看，本地方案与 GitHub 是互补关系，不是替代关系。

| 平台 | 优势 | 劣势 | 适合承载 |
|---|---|---|---|
| GitHub Issues、PR、Actions | 持久、对人可见、webhook、原生 agent 指派、CI 与 ruleset 门禁、审计 | 速率限制、分钟级延迟、认领不原子、通知噪音、注入攻击面、长线程撑大上下文 | 规格与验收标准、sub-issue 树、PR 交接、评审结论、合并门禁 |
| Kandev 自身 | 本地即时、步骤状态机、显式完成信号、点对点消息、worktree 隔离、PR 面板 | 只有一层子任务、无广播、无条件分支、对外不可见 | 运行时状态、会话与交接、agent 间通信、任务与 issue、PR、分支的映射 |
| beads（`bd`） | git 或 Dolt 存储、哈希 ID 防冲突、依赖 DAG 与 `bd ready`、旧任务压缩 | 对非仓库干系人不可见、无 CI 集成、存储后端在变 | 跟代码一起版本化的本地任务图 |
| MCP Agent Mail | 收件箱与线程、带时限的建议性文件租约、存于 git 的审计 | 需另起一个服务、租约只是建议性的、Python 版已弃用 | 文件租约、跨 agent 的会话记录 |
| Markdown 任务文件 | 零基础设施、可 diff、读取便宜 | 无认领和锁、并行时易冲突 | 进度日志、计划、知识地图 |

beads 与 Agent Mail 的资料来自 [steveyegge/beads](https://github.com/steveyegge/beads) 和 [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)。对 Kandev 用户来说，beads 和 Agent Mail 承担的职能（任务状态、依赖、消息）与 Kandev 自身的数据库和 `message_task_kandev` 大量重叠，叠加使用会造成双重事实来源。真正的空白只剩两块。一块是**同一工作区内的文件租约**，Kandev 的同任务多会话没有写锁。另一块是**随仓库版本化的任务图**，Kandev 的状态在 `~/.kandev` 数据库里，不在仓库里。现有资料中没有任何基准测试比较过"GitHub 协调"与"本地协调"两种方式，上表是基于机制的定性判断。

## 面向 Kandev 多 agent workflow 的设计含义（推断，非实施方案）

本节全部是基于上文证据的推断，没有经过 Kandev 实测，目的是为下一阶段修改工作流提供候选方向和待验证问题。

**拓扑上，以"规划者分解、隔离的单写者执行、独立评审、人工合并"为主干，把同一任务内并行多会话作为例外。** 案例证据（Cursor、Cognition、Kim 等人的 4.4 倍对 17.2 倍）和 Kandev 的机制（会话间无写锁，`new_workspace` 子任务有独立 worktree）指向同一个结论。一个候选形态是：父任务走 "Spec → Decompose → Integrate → Human Gate → Done"。Spec 步骤开 plan mode，用最强模型把验收标准写进 Plan。Decompose 步骤由协调 agent 调用 `create_task_kandev`，按 `new_workspace` 创建子任务，并用 `blocked_by` 表达顺序。每个子任务走 "Implement → Verify → Review → PR"。父任务的 Integrate 步骤由 `on_children_completed` 触发，进入后第一件事是检查有没有 FAILED 或 CANCELLED 的子任务，因为终态不等于成功。只有一层子任务的限制，意味着"协调者加工人"两层就是上限，更深的分解要摊平成兄弟任务或依赖链。协调者自己不写代码，这一点应写进它的步骤提示词。

**流转上，所有无人值守的步骤都开启 `auto_advance_requires_signal`，并把 `handoff` 设计成结构化契约，弥补缺少条件分支的问题。** 由于没有 PASS/FAIL 分支，评审步骤可以在提示词里约定：结论为 PASS 时调用 `step_complete_kandev`；结论为 FAIL 时调用 `move_task_kandev` 退回 Implement，并通过 `instructions` 附上具体问题。`{step_entry_number}` 可以充当迭代上限：在提示词中写明，第 N 次进入时停止循环，转人工门禁。这对应 MAST 中最常见的两种失败（步骤重复、不知终止）。`handoff` 只传一跳、上限 8 KB，所以跨多步的事实应写进 Plan 或仓库内的进度文件。另外需要一个看门狗，用来发现等不到信号的步骤，候选做法是定时 automation 加 `list_tasks_kandev`，因为显式信号模式会出现无限等待。

**评审上，用不同的 profile 加 `new` 策略或 `reset_agent_context` 拿到干净上下文，并把确定性检查放在 LLM 评审之前。** Feature Dev 模板的 Review 步骤已经采用 reset 加自动启动的组合，可以直接借鉴。评审者的输入只给 diff 加验收标准，结论通过 `publish_review_findings_kandev` 或任务文档持久化，不要依赖 `sessionStorage` 里的 diff 评论。`run_code_review` 失败时不会阻塞流转，所以它只能作为辅助，不能当门禁用。真正的门禁是测试、lint、类型检查全部通过，以及 GitHub 上的必需检查。

**连续性与 token 上，采用"短地图加结构化状态加稳定前缀"。** workflow 级提示词会在每一步进入时前置注入，应保持简短、稳定、不含时间戳，以保护缓存命中率。同一个 profile 的连续步骤沿用同一会话（`reuse`），可以避免重复加载上下文；跨模型的分层只放在会话边界上，因为会话中途切换模型或工具会让缓存失效。可以借鉴 Anthropic 的 JSON 功能清单（agent 只能翻转 `passes`）和启动协议（读进度、跑冒烟测试、一次只做一个单元）。AGENTS.md 和 CLAUDE.md 控制在约 100 到 200 行，细节放进按需加载的 skill。Configuration 包保持关闭，减少工具定义占用的上下文，也缩小 agent 的权限。仓库里的环境文件（例如 `.conda-env`、`.env.local`）通过 Copy files 预置到 worktree，免得每个 agent 自己去摸索环境。

**GitHub 分工上，坚持"GitHub 存持久工件，Kandev 存运行时"。** 候选做法是：issue 加 sub-issue 承载对人可见的规格与验收标准，用 Issue Watch 导入为 Kandev 任务；每个子任务一个分支、一个 draft PR，作为交接工件；Actions 的必需检查作为合并门禁；`on_pr_merged` 驱动任务完成。agent 之间的对话、认领、重试都留在 Kandev 内部，只在状态迁移时向 issue 或 PR 回写一条摘要，这样能同时控制速率消耗、通知噪音和上下文膨胀。所有读入的 GitHub 文本都按不可信数据处理，评审 agent 使用只读权限。如果需要云端 agent，可以把"指派给 @copilot、@claude、@codex"当作另一种 worker 后端，但要接受每次需要人工批准 workflow 运行带来的延迟。

**交付上，以可移植 YAML 的 v2 或 v3 版本放进仓库的 `.kandev/workflows`，配合 Workflow Sync 管理，并锁定 Kandev 版本。** 目标工作区的 profile 显示名、模型、模式必须与 YAML 完全一致，否则会被静默置空；步骤一旦上线就不要改名。修改工作流之前，应先在当前版本上验证以下问题：end policy 的真实默认值；`on_comment` 等 Office 触发器在常规 Kanban 中是否生效；#3336、#5173 等提示词投递 bug 是否已修复；多个子任务同时自动启动时的稳定性（#4152），候选缓解办法是 `KANDEV_MAX_CONCURRENT_SESSIONS` 或 WIP 上限；以及 Windows 下 worktree 执行器的表现。

## 结论

这次调研最重要的认识转变是：多 agent 编码的核心问题是控制上下文和验证，并行只是附带手段。成功案例里真正承重的是外部 oracle、单写者边界、干净的评审者和仓库内的持久状态，agent 数量只是放大器，而且每多一个 agent，token 账单接近线性增长，错误也可能被放大。所以给 Kandev 设计工作流时，衡量标准应该是"每个步骤是否有一个机器可判定的完成条件，以及它的上下文是否只装了必要的东西"，而不是"能同时跑多少个 agent"。

Kandev 的步骤状态机加显式信号，在机制上已经接近 Anthropic 和 Cursor 手工搭的 harness，缺的主要是条件路由、写隔离之外的租约，以及失败感知的汇合。这三项都能先用提示词约定、子任务隔离和 Integrate 步骤里的显式检查来近似。GitHub 应该成为这套系统的"公共账本"，而不是它的"神经系统"。下一阶段最值得先做的是一个小规模试点：两到三个子任务，接入完成信号、迭代上限、干净评审和 CI 门禁，并记录 token、返工轮数和合并率。现有文献恰好缺少这类数据，而且它比任何二手经验都更能决定这套工作流该保留哪些组件。
