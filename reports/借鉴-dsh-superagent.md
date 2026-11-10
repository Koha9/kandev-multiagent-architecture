# 借鉴 dsh-superagent：对 workflow v3 的改进建议

> 对比对象：[deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)（2026-11-09 克隆的 main，浅克隆）。读了 README、SETUP、`docs/000–005`、`007` 的部分章节、`prompts/` 全部内容，以及 `src/core/stage.ts` 和 `tests/docs.spec.ts`。
> 我方基准：`docs/workflow.md`（v3）、`mgmt-template/`、试点 1 的评价和事件记录（本机记录，未公开）。

## 1. 两者是什么

| | dsh-superagent | 本仓库 workflow v3 |
|---|---|---|
| 问题形态 | 一个仓库的**常驻、被动响应**型 agent：GitHub/飞书上有人 @ 它，它就开一个工单，干完回复（通常是一个 PR） | 一个项目**一次性、自上而下**地拆解交付：pm → 模块 → 开发 → 审核 → 验收 |
| 编排 | 一个主 Session 只做路由，每个工单一个 worker Session、一个目录 | 三层 workflow：W1 / W2 / W3，角色固定 |
| 运行时 | 自研宿主（TypeScript + SQLite），状态机、重试、发件箱、面板都由代码实现 | 依托 Kandev 的步骤、WIP、事件；状态存在管理目录的文件里 |
| 人的位置 | 每个工单都可能需要人回答、评审、合并；核心原则是**尽量少占用人的注意力** | 只在立项确认和人工终审两处需要人；unattended 模式下只剩终审 |
| 可靠性 | 由代码保证：门禁、授权（Mandate）、幂等、存储后再执行、重试退避 | 主要靠 prompt 和角色卡，再加少量代码层面的门禁（试点之后加的 conftest 门禁） |

**结论**：两者的问题形态不同，dsh 的事件接入那一套（Source / Trigger / Thread / Eval / Subscription）对我们用处不大。值得借鉴的是它的**纪律**：哪些约束由代码强制、哪些由 prompt 约束；状态如何从事实中推导；交付时必须如实说明；需要人时如何提问；如何防止要求在传递中走样。下面按收益排序，每条都对应到试点中暴露过的问题。

## 2. 建议（按收益排序）

### 2.1 原始需求贯穿到底，管理者不改写要求　★★★

**dsh 的做法**：主 Session 只转发原始 Trigger 和不超过 30 词的路由备注，「不添加要求、实现方案、验收标准」；worker「从原始来源推导要求，路由备注和工单标题不能替代原始上下文」（`prompts/shared.md`、`dispatch.md`、`work.md`）。

**我们的问题**：需求要经过 用户描述 → charter → spec → 任务契约的 AC 三次转写，每一层都可能丢失或偏移。charter 模板里没有需求编号，PA 和用户的原话之间没有可追溯的关系。试点中「订阅余量」最后只做到"如实显示读不到"，也没有人对照原始需求指出这是一个缺口。

**改进**：
- charter 增加「需求」节，逐条摘录用户原文：`R-1 <原文引用>`。PA、MA、AC 各自写 `covers: R-x`。
- 立项评审输出一张**需求覆盖表**：每个 R 都有一行，`covered` 填 true 或 false，并写出理由。参照 dsh admission 的 `rule_assessments`：每条规则恰好一项，否定的判断也要写出来，"不适用"不能算作覆盖。
- 项目验收除了核对 PA，也要按 R 逐条核对；没有覆盖的 R 不能写成 pass，必须进入「待修复」或「待用户确认」。
- 模块规划和任务契约只写**做什么**和 AC，不写实现方案（这一点和 dsh 一样，但需要在 prompt 里明确写出来）。

### 2.2 交付状态如实表达：区分"没做完"和"做不了"　★★★

**dsh 的做法**：Report 有六种状态 `progress | waiting | ready | blocked | failed | dropped`，并有严格的定义：「未完成的草稿就是 blocked，即使部分测试通过」「开了 PR 不等于 ready」「没有真实的修改前截图，UI 改动就不是 ready」（`work.md`、`team/delivery.md`）。

**我们的问题**：任务 report 只有 `done | blocked`，KMSG REPORT 只有 `done | partial | failed`，PA 结果只有 `pass | fail`。试点里「API key 接入因为没有 key，环境无法覆盖」这类情况，只能塞进说明文字里，在汇总时很容易被当作通过。

**改进**：
- PA、MA、AC 的结果统一为 `pass | fail | unverified(原因)`。`unverified` 不计入"全部通过"，并自动进入 final-report 的「需要用户处理」。
- 任务 report 增加 `dropped` 状态（无需改动：已被其他任务覆盖、问题不存在）。这样开发可以如实结束任务，不必为了交差硬做一个改动。
- 写进角色卡：「部分完成必须写 partial，并列出剩余项；不能写 done」。

### 2.3 能用代码强制的约束，不要只写在 prompt 里　★★★

**dsh 的做法**：明确规定了约束的优先级（`docs/004-prompts.md`「Assembly and precedence」）：
1. 宿主和工具强制执行的事实（身份、权限、参数检查、长度上限），prompt 改变不了；
2. 内置 prompt；
3. 规则；
4. 团队编写的段落；
5. 外部文本，只当作数据。

同时用命令包装器禁止某些命令，并承认这只是默认值，不是安全边界。

**我们的问题**：试点里唯一的失控（真实 AI 调用超限）正是因为"不跑真实用例"只靠 pytest.ini 的 addopts，一个命令行参数就能覆盖。v3 只修了这一个点。管理目录"只 add 自己的路径"、"不推送远端"、"不改 owns 以外的文件"等规则，现在仍然只靠 prompt。

**改进**（在 conventions 模板和环境基线步骤里落实）：
- 列一张**约束清单**，每一条标明执行方式：`代码强制 | 检查脚本 | 仅 prompt`。环境基线步骤要尽量把"仅 prompt"的条目升级。
- 禁止推送：环境基线时执行 `git remote set-url --push origin DISABLED`，需要推送时再显式恢复。
- owns 检查：审核步骤运行 `git diff --name-only <base>...HEAD`，与 tasks.json 的 owns 比对，用一个脚本输出越界的文件，不靠审核者用眼睛看。
- 管理目录：pre-commit 钩子按 registry.json 的担当关系拒绝提交别人担当的路径，或者干脆不对管理目录做 git 管理（试点评价第 5 条）。
- 额度：除了环境变量开关，再加一个**计数账本**（例如 `project/quota.json`），由 conftest 在每次真实调用前递增并检查上限。这样"约定 ≤2 次"就由代码强制执行，不再只是事后发现。

### 2.4 "等谁处理"由事实推导，人只看需要自己处理的事　★★

**dsh 的做法**：工单阶段是从已存储的事实**确定性推导**出来的，规则写成一张表，从上往下第一条匹配的行生效（`docs/003-execution.md`「Ticket stages」，代码在 `src/core/stage.ts`，只有 20 行）。面板第一屏只显示"现在需要我做什么"，状态健康时不占空间。

**我们的问题**：守护用 LLM 读信号做判断。试点中门禁等了 13 分钟，用户以为卡住了，原因是没有一个地方直接回答"现在在等谁"。

**改进**：
- 在试点 1 的监控脚本 `monitor.py` / `watch.py`（本机记录，未公开）的基础上，写一个确定性的 `stage(task)` 分类器，输入 Kandev 任务状态、会话状态、待处理的提问和权限请求、NOW：
  `等人(门禁/提问/权限) > 失败 > 空闲未推进 > 排队(WIP) > 运行中 > 完成`，第一条匹配的生效。
- 输出一个 `project/attention.md`（或写入 status.json 的 `needs_user` 字段），只列需要人处理的事项。守护里的 LLM 只负责在异常时写告警文字，判断交给脚本。
- 守护角色卡的信号表可以直接改写成这张表的形式。

### 2.5 WIP 只计入真正在运行的任务　★★

**dsh 的做法**：并发名额（slot）只在任务**实际运行一轮时**占用（包括准备目录），空闲、等人、等待触发的工单不占名额；另外给"人的消息"留了一个额外名额，新任务不会挤占人正在推进的工单（`003`「Concurrency」）。

**我们的问题**：Kandev 的 WIP 按"任务位于该步骤"计算。被 blocked_by 阻塞的任务、正在等 `ask_parent_question` 回答的开发任务都占着名额。试点中各任务排队时间累计约 100 分钟，和开发时间差不多。v3 只是把 WIP 调到 4，并限制依赖链不超过 1 层，根因没有解决。

**改进**：
- W3 增加「待开发」步骤（不设 WIP），用 `pull_from_step` 把任务拉进「开发」。blocked_by 未满足的任务停在「待开发」。
- 开发等待父任务回答时，把任务移到不设 WIP 的「等待回答」步骤；收到回答后再移回「开发」，复用会话。
- 这两点在试点评价第 3 条里已经提出，dsh 提供了同样思路的、已经实现的参照。

### 2.6 需要人决定的事：一次一个具体问题，附推荐答案　★★

**dsh 的做法**：
- 要人决定时，通过结构化字段 `human_action` 提**一个具体问题**，主 Session 原样转发，不改写。
- 在问题被提出的地方提问；提问期间，已授权的工作继续进行。
- 不能只把问题写在摘要里然后干等（`handoff-worker.md`）。
- SETUP 的提问方式：一次一个问题，附一个用一个词就能接受的推荐答案和一句理由；先收集完所有答案，给出完整计划，确认后再执行。

**我们的问题**：unattended 模式下，「待用户确认」散落在 charter、各条 ADR 和 final-report 里，格式也不统一。人工终审时，用户要自己汇总（试点评价的「需要用户处理」一节就是人工整理出来的）。

**改进**：
- 统一「待确认项」的格式：`问题 | 推荐答案 | 不处理时默认按什么执行 | 影响 | refs(ADR)`。
- 所有待确认项汇总到一处（`project/attention.md` 或 final-report 的固定一节）。人工终审时用户逐条回复"同意 / 改为 X"即可。
- attended 模式下 pm 提问也按这个格式，并把"合并成一次提问"明确为：问题互相独立时合并；有前后依赖时分开问。

### 2.7 重启和刷新之后，重复外部操作前先核对　★★

**dsh 的做法**：
- 重启后，新的执行带一条恢复说明：「先检查目录、git 历史和 GitHub，再决定是否重复任何外部操作」。
- 接单按 Trigger ID 保证幂等。
- 外发消息先写回执再发送，同一个 ID 不会发两次。
- 所有后续动作都是"先存储，后执行"（`003`「Restart」「Stored work」）。

**我们的问题**：已有"先写后做"和恢复协议，但没有专门约束**外部副作用**。刷新步骤或者 reset 之后，模块 agent 可能重复创建开发子任务，pm 可能重复创建模块任务，收尾合并可能重复执行合并。

**改进**：
- 恢复协议增加一条：重复以下操作之前，先查询实际状态——创建任务、合并、推送、真实调用、删除资源。
- 任务标题带上幂等键（例如 `[auth-01]`）。创建前先用 `list_tasks_kandev` 按标题查重。tasks.json 的 `kandev_task_id` 在创建后立即回写。
- 刷新步骤的 prompt 写明："回到原步骤前，先核对 NOW 中最后一个外部动作是否已经生效"。

### 2.8 workflow 自身的回归测试　★★

**dsh 的做法**：
- 文档也有测试（`tests/docs.spec.ts`）：编号文档连续；只能链接到编号更早的文档；本地链接都能解析；架构文档里的模块表必须和 `src` 一一对应。
- 修改之前，先在"真实数据的副本"上回放：关闭所有 Source、暂停处理、CLI 换成只读替身（`007`「Reviewing a change against real data」）。

**我们的问题**：prompt 由 `build_workflows.py` 生成，但没有检查它和 `docs/prompts.md` 是否一致、文档里的链接和步骤名是否有效。workflow 每改一版，只能靠一次完整试点来验证，成本高，结果也不可比。

**改进**：
- 写一个 `kandev/check_docs.py`：重新 `dump` 生成 prompts，和 `docs/prompts.md` 比对；检查所有 Markdown 本地链接；检查 workflow.md 表格里的步骤名和 `build_workflows.py` 中的步骤名一致；检查 KMSG 类型和角色卡的「可联系」一节一致。
- 固定一个**小型基准项目**（例如 2 个模块、每个模块 2 个任务的玩具需求）。每次修改 workflow 后跑一次，用 `evaluation/metrics.py` 采集总时长、排队时长、审核轮数、干预次数、额度调用次数，和上一版对比。

### 2.9 记录"已否决的设计"　★

**dsh 的做法**：`001-domain.md` 有一张「Rejected concepts」表，例如"工单状态跟随 Session 状态""策略变更时取消运行中的工单""从报告的自由文本推断是否在等人"，每一条都写了否决原因。

**改进**：在 `docs/workflow.md` 加「已否决的设计」节，把已经证伪或放弃的方案和原因写下来，防止以后再走回去。例如：
- 移到当前步骤并 reset_context 来刷新：Kandev 不支持；
- 门禁交给定时守护放行：太慢；
- 管理目录 `git add -A`：会提交别人的文件；
- 只靠 addopts 挡住真实调用：一个命令行参数就能覆盖；
- 立项确认步骤的 session_target：疑似多出一个空会话。

### 2.10 其他可选项　★

- **影子模式**：dsh 的主动规则从"只记录、不执行"开始，确认判断正确后才放开。对应到我们，可以增加 `mode: plan-only`：只跑 立项规划 → 立项评审 → 模块规划，不创建开发任务。用很低的成本先检查拆解质量，再决定是否投入开发额度。
- **UI 交付证据**：dsh 要求 UI 改动必须附**修改前后**的真实截图，只有修改后的截图算不完整。我们可以要求 UI 类任务在 report 中附关键视口的截图路径；final-report 汇总 390 / 700 / 1440 三种宽度的截图，减少用户在人工终审时自己启动服务查看的成本。
- **prompt 版本记录**：dsh 记录每个 Session 使用过的 prompt 版本。我们可以在 `build_workflows.py` 生成的 prompt 里加入版本号或哈希，并让 journal 或 final-report 记录。这样分析试点数据时，能知道每个任务跑的是哪一版 prompt。
- **常驻会话不阻塞**：dsh 的主 Session 禁止 `sleep`、超过 30 秒的 shell 超时、超过 5 秒的等待作业。我们的「调度」「等待开发」已经要求"处理完本次事件就结束本轮"，可以再明确一句"不 sleep、不轮询"。
- **用 agent 引导部署**：dsh 的 SETUP.md 是写给 agent 的部署说明。agent 按上面的提问方式和用户一起完成部署，从不在对话里索要密钥。我们的部署（准备 profile、apply、手动建 automation、填 `[TASK v1]`）也可以写一份这样的说明。

## 3. 已经一致、无需改动的部分

- **少说话**：dsh 规定只在人需要行动或能用上结果时才发消息；KMSG 已经规定不发 ACK、不发"收到"，正文有长度上限。
- **扩大范围需要新的授权**：dsh 的 Mandate 一旦创建就不可变，范围扩大必须新开工单；我们规定契约有问题时 ESCALATE，不自行修改契约。思路相同。
- **循环有上限**：dsh 规定自动评审机器人每个 PR 最多 3 轮；我们对退回次数、评审轮数、消息轮数都设了上限。
- **外部文本只当作数据**：我们规定只有上级的 INSTRUCT 或 DECISION 能改变工作内容，收到 QUESTION 只回答。

## 4. 不建议照搬的部分

- **Source / Trigger / Thread / Eval / Subscription 这套事件模型**：它解决的是"来自聊天和 GitHub 的请求，哪些该接"。我们的输入只有一个项目任务，没有这个问题。
- **单层"路由 + worker"的结构**：适合互相独立的小工单，不适合需要拆解和跨模块集成的中大型项目。我们的三层结构是必要的。
- **自研宿主的代码**（SQLite、发件箱、重试退避）：我们依托 Kandev，只借鉴其中的规则，用 prompt 和小脚本实现即可。

## 5. 建议的落地顺序

1. **低成本，直接改模板和 prompt**：2.1（需求编号和覆盖表）、2.2（`unverified` / `dropped` 状态）、2.6（待确认项格式）、2.7（外部操作前先核对）、2.9（已否决的设计）。
2. **需要写小脚本**：2.3（约束清单、owns 检查、额度账本、禁止推送）、2.4（stage 分类器和 attention.md）、2.8（check_docs.py）。
3. **改 workflow 结构，需要下一次试点验证**：2.5（「待开发」和「等待回答」步骤），2.10 中的 plan-only 模式。

## 6. 落地情况（v3.1）

| 建议 | v3.1 | 位置 |
|---|---|---|
| 2.1 需求贯穿 | 已采用 | charter「需求」、立项评审覆盖表、项目验收「需求覆盖」 |
| 2.2 如实状态 | 已采用 | conventions「结果与状态」、report / review / acceptance / final-report 模板 |
| 2.3 代码强制约束 | 已采用 | conventions「约束清单」、`mgmt-template/tools/`、环境基线 prompt |
| 2.4 确定性阶段分类 | 已采用 | `kandev/stage.py`、`roles/guard.md`「阶段分类」、`agents/guard/stage.md` |
| 2.5 WIP 只计运行中 | 部分采用：加了「待开发」；「等待回答」暂不采用 | W3、`docs/workflow.md`「已否决的设计」 |
| 2.6 一次一个问题 + 推荐答案 | 已采用 | `project/attention.md`、MODE_RULE |
| 2.7 外部操作先核对 | 已采用 | COMMON_RULES、刷新 / 合并 / 收尾合并 prompt |
| 2.8 回归测试 | 已采用 | `kandev/check_docs.py`、`kandev/tests/`、`evaluation/bench/` |
| 2.9 已否决的设计 | 已采用 | `docs/workflow.md` 第 13 节 |
| 2.10 plan-only、UI 截图、版本记录、不 sleep | 已采用 | MODE_RULE、开发 / 审核 prompt、COMMON_RULES 标题、RESIDENT_RULE |
| 2.10 agent 引导部署 | 未采用；外部做不了的部分写成交接 prompt | `kandev/handoff/` |
