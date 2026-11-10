# 平台选型：要不要从 Kandev 换到别的平台

> 2026-11-09。依据：本仓库的调研报告（`reports/多Agent协作与Kandev工作流调研.md`）、试点 1 的评价和事件记录，以及当天查到的各平台文档和评测（见文末「来源」）。

## 结论

**现在不整体切换。** 下一步先做一次**对照试验**：Kandev 上的 v3.1，对比 Claude Code 动态工作流（dynamic workflows）实现的同一套流程，在同一个基准项目上比较。另外，审核和验收这两个步骤可以先用工作流做多角度的交叉核查，风险低，马上就能改善审核偏浅的问题。

理由有三条：

1. **试点暴露的问题大多和平台无关。** 试点中浪费最大的两处，一是门禁等待 13 分钟，v3 已经修了；二是 WIP 排队累计约 100 分钟，在 Kandev 里加一个不设 WIP 的步骤就能解决。质量方面的问题，比如需求在逐层转写中走样、额度只靠 prompt 约束、审核偏浅，换到任何平台都会遇到，要靠改流程设计来解决（见 `reports/借鉴-dsh-superagent.md`）。
2. **换平台会丢掉一些现在依赖的能力。**
   - 按步骤绑定不同厂商的 agent profile。审核要求最好换厂商，这条依赖它。
   - 看板上能直接看到进度和门禁。
   - 每个任务一个 worktree，任务状态写在数据库里，机器重启后还在。
   - 试点已经验证过的三层结构。
3. **候选平台中真正成熟、又适合本机（Windows、无人值守、一小时以上）的不多**，详见下表。唯一值得认真比较的是 Claude Code 动态工作流，但它也有硬限制：运行中途不能等人输入，worker 只能是 Claude，只能在同一个会话里续跑。

## 候选平台

| 平台 | 是什么 | 对我们的适配度 | 主要问题 |
|---|---|---|---|
| **Claude Code 动态工作流**（`Workflow`，ultracode） | 由脚本编排几十到上百个子 agent。脚本里可以写分支、循环、并行和流水线；子 agent 可以返回符合 JSON schema 的结构化结果；在同一会话内可以续跑。所有付费套餐都能用 | **高**（只用于执行层） | 运行中途不能等人输入，门禁只能放在两次运行之间；worker 只能是 Claude；会话结束后要靠 `--resume` 才能续跑；默认最多 16 个 agent 并发，每次运行最多 1,000 个 |
| Claude Code agent teams | 一个 lead 带若干 teammate，有共享任务列表，teammate 之间可以直接发消息 | 低 | **实验功能，默认关闭**；没有 worktree 隔离；不能嵌套；in-process teammate 无法恢复；文档自己写明"无人值守跑太久会浪费" |
| Claude Code Projects | 一个持续的对话，在云端开多个并行线程，有共享记忆和「需要你处理」的总览 | 中低（以后可以再看） | **公开 beta**，只开放给 Pro、Max、Ultra；线程默认跑在云端，用不到本机的 CLI 登录状态和本地路径；"同时最多跑 N 个线程"只是偏好，不是硬上限 |
| OpenAI Codex（subagents、cloud tasks、Codex app） | 一个主 agent 把任务分派给多个子 agent，在云端沙箱里并行，最后提 PR | 中 | 云端执行，和本机环境不同；只能用 Codex；适合定义清楚的独立任务，不适合跨模块集成 |
| OpenAI Symphony | 一份规格加 Elixir 参考实现，把 Linear 看板当作 Codex 的控制面 | 低（只作参考） | 官方表示不打算作为产品维护；v1 只支持 Linear |
| GitHub Agent HQ / Copilot coding agent | 在 GitHub 上把 issue 指派给 Copilot、Claude、Codex 等多家 agent，由 Mission Control 统一管理 | 中（只适合做公共账本或备用的 worker 后端） | 速率限制、分钟级延迟、认领不是原子操作、注入攻击面大（见之前的调研报告）；不适合高频的 agent 间协作 |
| Gas Town（Steve Yegge） | Mayor 拆任务，Polecat 执行，Witness 监控，Refinery 管合并；用 beads 存任务，能协调 20–30 个 agent | 低（借鉴概念） | 作者自称"100% vibecoded"，复杂度高，学习曲线陡；依赖 tmux，Windows 支持存疑 |
| Microsoft Conductor | 用 YAML 定义多 agent 工作流，支持条件路由和子工作流，跨平台 | 低（关注即可） | 还在 v0.1.x，迭代很快 |
| Vibe Kanban | 和 Kandev 类似：看板加每任务一个 worktree | **不推荐** | Bloop 在 2026-04-10 宣布关停，现在由社区维护 |
| Conductor（conductor.build）、Claude Squad、Crystal | 桌面端或终端的并行会话管理器 | **不推荐** | Conductor 只支持 macOS；Claude Squad 依赖 tmux，没有原生 Windows 支持；Crystal 已在 2026 年 2 月弃用。三者都没有层级结构，也没有门禁 |
| dsh-superagent | 常驻在单个仓库的被动响应 agent | 不适用 | 依赖 DeepSeek Harness，形态是"有人提需求才接单"，不是项目拆解 |

## 唯一值得比较的候选：Claude Code 动态工作流

### 它能解决的 Kandev 痛点

| Kandev 上的问题（调研或试点中发现） | 动态工作流的做法 |
|---|---|
| 没有条件分支，审核的 PASS/FAIL 只能靠 prompt 约定调用 `step_complete` 还是 `move_task` | 分支写在脚本里：`if (review.verdict === 'pass')`，由代码执行，不靠模型记住规则 |
| 退回上限、评审轮数上限靠 prompt 和 `{step_entry_number}` 控制 | 用 `for` 循环加计数，真正的硬上限 |
| WIP 按"任务在哪个步骤"计数，被阻塞的任务也占名额（试点中排队约 100 分钟） | 并发只计入正在运行的 agent；依赖顺序就是 `await` 的顺序 |
| 完成信号必须由 agent 调用工具发出；已知有提示词投递丢失和启动失败的 bug（#3336、#5137、#5173、#4152） | `agent()` 返回就算完成；输出不符合 schema 会自动重试，最多 5 次；agent 卡住会自动重启，最多重启 5 次 |
| report、review 依赖 agent 自觉按格式写 | `schema` 强制结构化输出：verdict、AC 证据、boundary_check 等字段缺一不可 |
| 守护每 20 分钟巡检一次，门禁响应慢 | 编排本身就是确定性的，不需要守护代为推进；`/workflows` 能看到每个阶段、每个 agent 的状态和 token 用量 |
| 常驻会话变长，需要专门的「刷新」中转步骤 | 每个 `agent()` 都从全新上下文开始，中间结果放在脚本变量里，不进上下文 |

### 它的代价

- **门禁要拆成多次运行。** 运行中途不能等人输入，所以流程要拆成：「立项」一次运行 → 人确认 → 「开发」一次运行 → 人工终审 → 「收尾」一次运行。unattended 模式下中间不停，影响不大。
- **只能用 Claude。** 可以让审核 agent 在 shell 里调用 `codex exec`，或者通过 MCP 接入其他厂商来保留"换厂商审核"，但这条还没验证。
- **持久性比 Kandev 弱。** 续跑只能在同一个会话里进行，退出后要靠 `claude --resume`。还有一条：中途某个 agent 失败，续跑时它之后启动的 agent 都会重跑。这意味着管理目录、tasks.json、git 仍然是事实来源，恢复协议照旧需要。
- **可见性降低。** 没有看板，只有 `/workflows` 进度视图和管理目录里的文件。
- **成本。** 每个 agent 都是全新上下文，同一个 profile 跨步骤复用会话的缓存收益没有了；同一次运行里配置相同的 agent 之间可以共享 prompt cache。运行超过 25 个 agent 或预计超过 150 万 token 时会给出提示。

### 能带来的提升（估计，待试验验证）

- **时间**：试点评价估计，去掉门禁等待和 WIP 排队后，98 分钟可以降到约 70 分钟。这部分收益在 Kandev 里修好 WIP 也能拿到。动态工作流额外的收益，来自"准备好就并行开始"、不需要守护、少了等完成信号的空转，粗估再省 10%–20%。
- **稳定性**：分支、上限、结构化输出都由代码保证，可以避开 Kandev 上提示词投递和完成信号相关的 bug。这一项最有价值，但收益大小要看下一次试点有没有碰到这些 bug（试点 1 没碰到致命的）。
- **质量**：最直接的提升是**多角度对抗式审核**：同一个 diff 分别从 AC 符合度、边界和错误路径、越权和 owns 越界、额度和副作用几个角度并行审核，再交叉核实各自的发现。这对应试点中"审核大多只用 1–2 分钟"的问题，而且不需要换平台，见下一节。

## 建议的行动

1. **先在 Kandev 里修**（不换平台，成本最低）：
   - v3.1：加「待开发」「等待回答」两个不设 WIP 的步骤；
   - 落实 `借鉴-dsh-superagent.md` 里第一批的模板和 prompt 修改。
2. **只在步骤内部引入工作流**（低风险，收益直接）：
   - 「审核」「项目验收」两个步骤中，如果 profile 是 Claude Code，就在步骤内用一个工作流做多角度审核和交叉核实，结论仍写进 `review` 或 final-report；
   - **前提要先验证**：Kandev 通过 ACP 启动的 Claude Code 会话里能否使用 `Workflow` 工具。非交互模式下需要在权限规则里加 `Workflow` 才能启动。
3. **做对照试验**，决定执行层要不要迁移：
   - 固定一个小型基准项目（2 个模块、每个模块 2–3 个任务），先在 Kandev v3.1 上跑一次；
   - 再用一个动态工作流脚本实现 W2/W3：模块规划 → 每个任务"开发 → 审核"循环（最多 3 轮）→ 模块验收。W1 的门禁仍放在 Kandev，或者拆成多次运行；
   - 两边都用 `evaluation/metrics.py` 采集：总时长、排队时长、token 或费用、审核轮数、审核发现的缺陷数、PA 通过率、人工干预次数。
   - **迁移门槛**：总时长少 30% 以上，且 PA 通过率不降、token 增加不超过 20%，就把 W2/W3 迁到工作流，W1 留在 Kandev 承担门禁和可见性；达不到就保持现状。
4. **暂不考虑**：agent teams（实验功能）、Projects（公开 beta，并且以云端为主）、Vibe Kanban、Conductor、Claude Squad。Gas Town 和 Symphony 只借鉴概念：Refinery 式的合并队列、"proof of work" 交付证据、用看板做控制面。

## 需要先验证的事

- Kandev 通过 ACP 启动的 Claude Code 能否使用 `Workflow` 工具，以及子 agent 的权限和 worktree 隔离在这种方式下怎样表现。
- 在工作流里，审核 agent 调用 `codex exec` 做跨厂商审核是否可行、成本多少。
- 动态工作流在 Windows 上长时间（一小时以上）运行的稳定性。文档写明 split-pane 显示模式不支持 Windows Terminal，工作流本身没有这个限制，但没有实测数据。

## 来源

- Claude Code 文档：[Run agents in parallel](https://code.claude.com/docs/en/agents.md)、[Dynamic workflows](https://code.claude.com/docs/en/workflows.md)、[Agent teams](https://code.claude.com/docs/en/agent-teams.md)、[Projects](https://code.claude.com/docs/en/claude-projects.md)
- 开源编排器综述：[Augment Code, 9 Open-Source Agent Orchestrators (2026)](https://www.augmentcode.com/tools/open-source-agent-orchestrators)、[Nimbalyst: Conductor vs Vibe Kanban vs Nimbalyst](https://nimbalyst.com/compare/nimbalyst-vs-conductor-vs-vibe-kanban/)、[amux: Best Multi-Agent Coding Orchestrators 2026](https://amux.io/blog/best-multi-agent-orchestrators-2026/)
- OpenAI：[Symphony 报道（Help Net Security）](https://www.helpnetsecurity.com/2026/04/28/openai-symphony-codex-orchestration-linear/)、[Three-Tier Agent Orchestration（Codex）](https://codex.danielvaughan.com/2026/04/09/three-tier-agent-orchestration/)、[OpenAI Codex App 指南](https://intuitionlabs.ai/articles/openai-codex-app-ai-coding-agents)
- GitHub：[Introducing Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/)
- Gas Town：[heise: Gas Town Orchestrates Ten or More Coding Agents](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html?view=print)、[gastown.dev](https://gastown.dev/docs/intro)
- OpenHands：[OpenHands SDK](https://www.openhands.dev/product/sdk)

上述第三方评测和二手报道里的日期、星标数有互相矛盾的地方，表格只采用多个来源一致的结论。Codex subagents 的 GA 日期等细节没有核对 OpenAI 的原始发布说明。
