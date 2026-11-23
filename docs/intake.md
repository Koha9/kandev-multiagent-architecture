# 接收：把用户输入整理成 [TASK v1] 任务描述

> 读者：W1「接收」步骤的 agent（步骤 prompt 指向本文件），以及想知道启动项目需要哪些参数的人。
> 本文件是 `[TASK v1]` 头（pm 任务）各字段的说明：含义、怎么推导、缺省值、要不要问用户、怎么问、怎么校验、最后写成什么样。
> 各字段对后续流程的影响见 [workflow.md](workflow.md)「运行模式」和「部署与启动」。

## 1. 直接放行

任务描述同时满足下面几条时，它已经是完整的 `[TASK v1]` 描述：**不改、不提问，直接完成本步骤**。

- 第一个非空行是 `[TASK v1]`。
- 头里有这些字段且值不为空、不是 `<...>` 占位：`project`、`mode`（attended 或 unattended）、`mgmt_root`、`mgmt_template`、`repo`、`role: pm`、`branch`（含 `base <分支>`）。`branch` 行里的 `<自动>` 是固定写法，不算占位。
- 有一行 `---`，它之后有需求正文。
- `autonomy`、`plan_only`、`integration_test`、`remote`、`push_branch`、`ci`、`scope`、`parent`、`pm` 可以没有（pm 按缺省值处理：没有 `autonomy` 时 attended 按 2、unattended 按 4；没有 `remote`、`ci` 时按 none）。

放行前只做第 5 节中标"放行时也查"的三项检查。不通过时只改那一行（按第 5 节：能自动改正的改正并在回复中说明，否则就那一项提问），其余原样保留。

## 2. 不完整时的处理顺序

1. 用户已写明的值（包括写了一部分的 `[TASK v1]` 头，以及自然语言）照用，不改。
2. 能推导的自己推导（第 3 节「推导」）。
3. 部署缺省值（见下）中的具体值直接用。
4. 有缺省值且标"不问"的直接用缺省值。
5. 剩下标"要问"的按第 4 节逐轮提问，最后请用户确认汇总。
6. 校验（第 5 节）→ 组装（第 6 节）→ 写回任务描述。

自然语言的对应关系：

| 用户的说法 | 字段 |
|---|---|
| 每一步都问我、逐步确认、我要盯着 | `autonomy: 1` |
| 有问题问我、关键节点等我、半值守、attended | `autonomy: 2` |
| 你自己决定、推送和花钱前问我、大部分自己定 | `autonomy: 3` |
| 无人值守、不用问我、全自动、我不在、unattended | `autonomy: 4` |
| 先只出计划、先看方案、先不开发、plan only | `plan_only: true` |
| 不做结合测试、不要集成测试、跳过 e2e | `integration_test: off` |
| 推到远端、push 到 GitHub、我要在 GitHub 上看 | `remote: push` |
| 开 PR、提 PR、发 pull request | `remote: pr` |
| 推到 X 分支、交付到 X 分支 | `push_branch: X` |
| 只在本地、不要推送 | `remote: none` |
| 本地跑 CI、合并前跑 CI 检查 | `ci: local` |
| 等 CI 结果、看 GitHub Actions 过没过 | `ci: remote` |
| 管理目录放在 X、mgmt 放 X | `mgmt_root: X` |
| 基于 X 分支、从 X 切出、合回 X | `branch: <自动> base X` |
| 项目叫 X、项目名 X | `project: X` |

用户只写了 `mode`：attended 按 `autonomy: 2`，unattended 按 `autonomy: 4`。

用户写明"不要提问"或 `autonomy` 已确定为 4 时：不提问、不做确认汇总，标"要问"的字段全部采用部署缺省值中的具体值，没有具体值的采用第 3 节的缺省值（不是提问时的推荐答案：autonomy 4 下 `plan_only: true` 会让项目停在门禁等人），并写进「接收时采用的缺省值」。唯一的例外是需求（见 Q1）。用户在 Q2 选了 4 之后同样不再提问。

不提问时，没有缺省值的字段（`repo`、基线分支）推导不出或校验不通过：流程只能停下等人，这时仍然只就这些字段提问（说明原因），不编造值；得不到可用的值就不完成本步骤。第 5 节中"问 Qn"的处理在不提问时都按这一条。

### 部署缺省值

部署时 `ma.py install` 可以在 `<arch_root>/custom/project-defaults.json` 写下各项目的缺省做法（值都是字符串）：

```json
{"remote": "auto", "ci": "auto", "autonomy": "ask", "plan_only": "ask", "integration_test": "ask", "paid_calls": "ask"}
```

文件不存在、读不出、缺某个键：该项按 `ask`（`remote`、`ci` 按 `auto`）。

| 值 | 做法 |
|---|---|
| 具体值（如 `"2"`、`"false"`、`"off"`、`"pr"`） | 直接用，不提问；用户在需求里写了不同的说法时以用户为准。来源记"部署缺省"，确认汇总里照样列出 |
| `ask` | 按第 3 节「缺少时」的规则提问（autonomy 4 或不提问时用第 3 节的缺省值） |
| `auto`（只用于 `remote`、`ci`） | 先检测：`remote` 看 `git -C <repo> remote -v`，没有远端 → none，有 → 问 Q9；`ci` 看仓库里有没有 CI 配置（`.github/workflows/`、`.gitlab-ci.yml`、`azure-pipelines.yml`、`Jenkinsfile`、`.circleci/`），没有 → none，有 → 问 Q10。不提问时：`remote` 取 none，`ci` 有配置取 local、没有取 none |

`paid_calls`：`deny` → 额度约定写"不允许真实调用"；`allow` → "允许真实调用，每种最多 2 次"（用户写了次数时以用户为准）；`ask` → 按 Q8 的条件提问。都记进「接收时采用的缺省值」。

## 3. 字段

| 字段 | 含义 | 推导 | 缺省值 | 缺少时 |
|---|---|---|---|---|
| `project` | 项目名，用于标题和报告 | 用户写的名称；否则 `repo` 的目录名 | repo 目录名 | 不问 |
| `autonomy` | pm 自己决定到什么程度，1–4，见下表 | 见第 2 节的对应关系；用户只写了 mode 时由 mode 推出 | 2 | **要问**（Q2） |
| `mode` | 引擎和模块任务用的运行模式，由 autonomy 导出：1、2 → attended；3、4 → unattended | 由 autonomy 导出，不单独取值 | attended | 不问 |
| `plan_only` | true：立项评审通过后停在「立项确认」，用户看过计划再投入开发额度 | 见第 2 节；autonomy 1 固定为 true | false | 只在 autonomy 3 时**要问**（Q3）；autonomy 2 时两种取值都会停在「立项确认」，不问 |
| `integration_test` | auto：其他模块完成后自动做结合测试；off：不做 | 见第 2 节 | auto | autonomy 1–3 时**要问**（Q4） |
| `remote` | 交付方式。none：只在本地合入基线分支；push：收尾合并后推送 `push_branch`；pr：推送 `push_branch` 并开 PR，不在本地合入基线分支 | 见第 2 节；部署缺省值 | none | 按部署缺省值的规则（缺省 auto）；要问时 Q9 |
| `push_branch` | 交付到远端的哪个分支（只在 remote 不是 none 时写）。是基线分支时本地合入后推送基线分支；不是时把集成分支推送成这个分支（不在本地合入基线分支） | 用户写明的 | push：基线分支；pr：`ma/<project>` | 随 Q9 一起定，不单独问 |
| `ci` | none：不管 CI；local：仓库 CI 配置里的检查写进合并门禁，本地跑；remote：推送后等远端 CI 结果，写进 final-report（需要 remote 不是 none） | 见第 2 节；部署缺省值 | none | 按部署缺省值的规则（缺省 auto）；要问时 Q10 |
| `repo` | 主仓库的绝对路径（不是任务的 worktree） | 在当前工作目录运行 `git rev-parse --path-format=absolute --git-common-dir`，取结果的上级目录（去掉末尾的 `.git`）；失败时用 `list_repositories_kandev` 找本任务的仓库 | — | 推导不出才问（Q6） |
| `branch` | 固定写成 `<自动> base <基线分支>`。基线分支是最终合入的分支，在「收尾合并」之前不被改动 | 用户写明的；否则本任务创建时选的 base branch（`list_tasks_kandev` 返回的任务信息里有就用）；否则 `git -C <repo> symbolic-ref --short HEAD`（主仓库当前检出的分支） | — | 推导结果不是 `main` / `master`、且用户没提到它时确认一次（Q5，autonomy 4 时不问，记进缺省值清单）；推导不出也问 Q5 |
| `mgmt_root` | 本项目的管理目录（绝对路径）。必须在 `repo` 和所有 worktree 之外 | 用户写明的；否则 `<repo 的上级目录>/<repo 目录名>-mgmt` | 同左 | 不问。缺省路径已存在且不是空目录时：其中 `project/registry.json` 的 `project` 与本项目相同 → 保留（继续同一个项目）；否则改用 `<缺省路径>-<yyyyMMdd-HHmm>`，写进缺省值清单；仍不可用才问（Q7） |
| `mgmt_template` | 管理目录模板 | `<arch_root>/mgmt-template`（arch_root 见步骤 prompt） | 同左 | 不问 |
| `role` | 固定 `pm` | — | pm | 不问 |
| `scope` | 固定 `pm` | — | pm | 不问 |
| `parent` | 固定 `user` | — | user | 不问 |
| `pm` | 固定 `self` | — | self | 不问 |
| 需求正文 | `---` 之后的内容：项目目标、需求、约束、技术栈与环境要求、额度约定 | 用户原文，一字不改 | — | 没有可执行的需求时**要问**（Q1） |
| 额度约定 | 是否允许消耗额度的真实调用（真实 AI、付费 API、部署）以及次数上限 | 用户写明的；部署缺省值 `paid_calls` | 一律不允许（开关默认关闭） | 只有需求明显依赖这类调用、而用户没写时才问（Q8） |
| 运行策略 | 用户事先做的三项决定，写在正文的「运行策略」节，pm 照此执行：运行中发现的真实缺陷本轮修还是只记录；旧代码、旧产物保留还是删除；是否允许改变已有行为 | 用户写明的 | 不写（pm 按 autonomy 自己决定） | autonomy 1–3 时**要问**（Q11–Q13） |

autonomy 各级：

| autonomy | 名称 | mode | 做法 |
|---|---|---|---|
| 1 | 逐步确认 | attended | plan_only 固定为 true，停在「立项确认」；另外改模块清单或范围、对每个 ESCALATE 的决定，pm 都先问你 |
| 2 | 关键节点确认 | attended | 关键事项合并成一次提问；立项评审通过后在「立项确认」等你 |
| 3 | 自主决策 | unattended | 可撤回的取舍自己决定（写 ADR、登记 attention.md 等你追认）；不可逆或花钱的事先问你：推送远端或开 PR、超出额度约定的真实调用、删除数据、删减需求、改基线分支 |
| 4 | 完全无人值守 | unattended | 全程不提问，决定都写 ADR 等你追认；推送按 `remote` 直接做 |

不论哪一级，「人工终审」都等你批准；流程停下等人时（门禁、交给你的决策）都会提问。autonomy ≤3 且 remote 不是 none 时，人工终审还会问这次推不推送。

技术栈、环境要求、需求的优先级和取舍**不由接收步骤询问**：它们是 pm 在「立项规划」的工作（attended 时 pm 会合并提问，unattended 时写 ADR）。接收步骤只保证 pm 拿到完整的头、运行策略和用户原话。

"可执行的需求"：读完能知道要做出什么东西。只有一个标题（"做个网站"）、只有参数没有正文、或正文只是"见附件"而没有附件内容，都算没有。

## 4. 提问

用 `ask_user_question_kandev`。**一次调用最多 4 个问题**，上一轮得到回答后再决定下一轮问什么。不需要问的问题不占位置。

每个问题：一句话说明这个选择影响什么，给出选项，把推荐答案放在第一个并标"（推荐）"，附一句理由。选项之外用户可以自己填写。

轮次：

1. **第 1 轮**：Q1（没有需求时）、Q6（repo 推导不出时）、Q2（autonomy 未知时）。都不需要问就跳过这一轮。
2. autonomy 是 4（或用户要求不提问）：不再提问，其余按第 2 节取缺省值，不做确认汇总。
3. autonomy 是 1–3：**后续轮次**按 Q5、Q3、Q4、Q9、Q10、Q8、Q11、Q12、Q13 的顺序，只排仍需要问的，每 4 个一轮。Q10 和 Q9 在同一轮时，ci 的 remote 选项注明"需要推送"。
4. **确认汇总**（autonomy 1–3，最后一轮，只有这一个问题 QF）：题干不超过 8 行，写出所有参数和会发生什么：
   - 自主程度和会在哪里停下等你（立项确认：是 / 否；人工终审：一律），运行中会问你哪类事。
   - 基线分支；交付：只在本地合入 / 本地合入后推送 `<远端>/<push_branch>` / 推送 `<push_branch>` 并开 PR；推送前会不会再问（autonomy ≤3 时在人工终审再问）。
   - ci、integration_test、额度约定、运行策略。
   - 本项目 attention.md 的绝对路径（`<mgmt_root>/project/attention.md`）；mgmt_root 沿用已有目录时写明"继续已有项目"。
   - 选项：按这样启动（推荐）/ 修改某项（在补充说明里写改什么）/ 取消。
   - 选了修改：按用户的话改对应字段（说得不清楚的只就这一项再问），然后再做一次确认汇总。
   - 选了取消：不调用 step_complete_kandev，回复一句"已取消；修改任务描述后把任务移回「接收」可以重新开始"，不再提问。

上限：

- 整个步骤最多调用 6 次 `ask_user_question_kandev`（含确认汇总和校验后的重问）。快到上限时，没问到的非必需字段采用缺省值（写进缺省值清单），把最后一次留给确认汇总。最后一次确认的答复仍是修改：按修改后的值写回，不再确认，摘要第一行写明"按你最后的修改启动，未再确认"。
- 同一个字段最多问 2 次（第二次只在回答不清楚或校验不通过时）。仍缺的字段采用第 3 节的缺省值并写进缺省值清单；缺的是需求或 `repo` 时不采用缺省值，停下并说明（不调用 step_complete_kandev）。

| # | 什么时候问 | 问题 | 选项（第一个是推荐） |
|---|---|---|---|
| Q1 | 没有可执行的需求 | 这个项目要做什么？请按重要度逐条写出需求（一条一行），以及约束和不做的事。 | 自由填写（选项给："我现在补充需求"、"取消，稍后重新建任务"） |
| Q2 | `autonomy` 未知 | 运行过程中，管理 agent 自己决定到什么程度？ | 2 关键节点确认（推荐：关键事项合并提问，适合第一次用或需求还有歧义）/ 1 逐步确认：先停下给你看计划，改范围和处理升级都先问你 / 3 自主决策：可撤回的事自己定、事后追认，推送、花钱、删除、删减需求前问你 / 4 完全无人值守：全程不问，事后追认 |
| Q3 | autonomy 3 且 `plan_only` 未知 | 立项计划出来后要不要先停下来给你看？ | 评审通过后直接开发（plan_only: false，推荐：自主决策时不在门禁等人）/ 先看计划再开发（plan_only: true：先确认模块划分和验收标准，再投入开发额度） |
| Q4 | `integration_test` 未知 | 所有模块完成后，是否自动做跨模块的结合测试？ | auto（推荐）：自动合并各模块并写、跑自动化结合测试，能发现模块各自通过但组装后不能用的问题 / off：不做，省额度，适合单模块或纯库项目 |
| Q5 | 基线分支需要确认或推导不出 | 以哪个分支为基线？完成后合回这个分支，合回之前它不会被改动。 | 推导出的分支（推荐）/ `main` / 仓库中其他最近更新的分支（最多列 2 个，`git -C <repo> branch --sort=-committerdate`） |
| Q6 | `repo` 推导不出 | 目标仓库在本机的绝对路径是什么？ | `list_repositories_kandev` 返回的仓库路径（最多 3 个）；自由填写 |
| Q7 | `mgmt_root` 的缺省路径和带时间后缀的路径都不可用 | 管理目录放在哪里？必须在仓库和 worktree 之外。 | 自由填写（选项给一个你能找到的可写位置） |
| Q8 | 需求明显依赖消耗额度的调用而没有约定，且部署缺省值 `paid_calls` 是 ask | 是否允许测试和验收时做真实调用（会产生费用）？ | 不允许，全部用 mock（推荐，可以事后再开）/ 允许，每种调用最多 N 次（请填 N） |
| Q9 | `remote` 要问（检测到远端） | 完成后怎么交付？（远端：`<远端名> <地址>`） | 基线分支有 upstream 时推荐 pr：推送 `ma/<project>` 并开 PR，基线分支不动，在网页上审查后合并 / push：本地合入后推送基线分支（想推送到别的分支时在补充说明里写分支名）/ none：只在本地合入，不推送（没有 upstream 时推荐） |
| Q10 | `ci` 要问（检测到 CI 配置） | 仓库有 CI 配置（`<文件>`），要不要用？ | local（推荐）：把其中的检查写进合并门禁，在本地跑 / remote：推送后等远端 CI 结果，写进最终报告（需要推送）/ none：不管 CI |
| Q11 | 运行策略未定 | 运行中发现的真实缺陷（需求之外、但确实是 bug）怎么处理？ | 记录下来，留给终审决定（推荐：不扩大范围）/ 本轮顺手修掉 |
| Q12 | 运行策略未定 | 仓库里的旧代码、旧产物（被新实现取代的）怎么处理？ | 保留（推荐：可以事后再删）/ 删除（视为已授权，限被本次替换的部分） |
| Q13 | 运行策略未定 | 是否允许改变已有功能的行为？ | 只在需求明确要求时（推荐）/ 允许，pm 认为合理时就改（写 ADR） |
| QF | autonomy 1–3，其他问题都问完后 | 按这样启动吗？（题干：参数汇总，见上面「确认汇总」） | 按这样启动（推荐）/ 修改某项 / 取消 |

用户在回答里顺带写了别的要求：原话记入第 6 节的「补充」，不自己解读成字段以外的决定。

## 5. 校验

| 检查 | 不通过时 | 放行时也查 |
|---|---|---|
| `repo` 存在，且 `git -C <repo> rev-parse --git-dir` 成功 | 问 Q6 | 是 |
| `mgmt_template` 存在且其中有 `README.md` | 改为 `<arch_root>/mgmt-template`（放行时也只改这一行，并在回复中说明）；它也不存在 → 停下说明 | 是 |
| 有 `autonomy` 时，`mode` 与它一致（1、2 → attended；3、4 → unattended），autonomy 1 时 `plan_only: true` | 按 autonomy 改正 `mode` / `plan_only` 那一行，并在回复中说明 | 是 |
| 基线分支存在：`git -C <repo> rev-parse --verify <分支>` | 问 Q5 | 否 |
| `mgmt_root` 是绝对路径，不在 `repo` 之内，也不在当前工作目录（任务 worktree）之内 | 改用缺省路径；仍不行问 Q7 | 否 |
| `mgmt_root` 已存在且不是空目录 | 有 `project/registry.json` 且其中的 `project` 与本项目相同 → 保留（这是在继续同一个项目）；否则：用户写明的路径 → 问 Q7，缺省路径 → 按第 3 节换成带时间后缀的路径 | 否 |
| `autonomy` 是 1–4；`plan_only` 是 true / false；`integration_test` 是 auto / off；`remote` 是 none / push / pr；`ci` 是 none / local / remote | 按第 2 节的对应关系改写；对应不上问对应的问题 | 否 |
| remote 不是 none 时仓库有远端（`git -C <repo> remote` 不为空）；pr 时 `push_branch` 不是基线分支 | 没有远端 → 改为 none 并在摘要中说明；pr 的 push_branch 是基线分支 → 改为 `ma/<project>` | 否 |
| `ci: remote` 时 remote 不是 none | 改为 local，记进缺省值清单 | 否 |

只读检查，不创建目录、不建分支、不改仓库。路径统一写成绝对路径；Windows 上用反斜杠或正斜杠都可以，保持用户写的样子。

## 6. 输出格式

新的任务描述（整体替换原描述）：

```
[TASK v1]
project: <项目名>
autonomy: 1 | 2 | 3 | 4
mode: attended | unattended
plan_only: true | false
integration_test: auto | off
remote: none | push | pr
push_branch: <分支>
ci: none | local | remote
mgmt_root: <管理目录绝对路径>
mgmt_template: <arch_root>/mgmt-template
repo: <主仓库绝对路径>
role: pm
scope: pm
parent: user
pm: self
branch: <自动> base <基线分支>
---
<用户原文，一字不改。原文里已有的 [TASK v1] 头部行（写了一部分的头）移到上面，不在这里重复>

运行策略（用户已决定，pm 照此执行，不再问）：
- 运行中发现的真实缺陷：只记录 | 本轮修
- 旧代码、旧产物：保留 | 删除（限被本次替换的部分）
- 改变已有行为：只在需求明确要求时 | 允许（写 ADR）

补充（接收步骤提问所得，用户原话）：
- Q：<问题> A：<回答原话>

接收时采用的缺省值（未询问用户）：
- <字段>: <值>（<推导方式、"部署缺省"或"缺省">）
```

- `branch` 一行里的 `<自动>` 照写这三个字符（任务分支由 Kandev 自动创建）。
- `push_branch` 只在 remote 不是 none 时写。
- 头里每行一个字段，`字段: 值`，不加注释、不加引号、不加粗；守护脚本按行首的 `mgmt_root:` 解析。
- 「运行策略」「补充」「接收时采用的缺省值」没有内容时整节省略。
- Q1 的回答（需求）写在「补充」里，原话照录；不改写、不合并、不排序。
- 任务标题不改。

## 7. 例子

用户输入：

```
给这个仓库加一个待办应用：能新增、勾选完成、删除，数据存在本地。无人值守跑完，不用问我。
```

接收步骤：`autonomy` 从"无人值守""不用问我"得到 4，因此不提问、不做确认汇总；没有部署缺省值文件，仓库有远端 → remote 取 none，没有 CI 配置 → ci 取 none；其余字段推导或取缺省值。写回的任务描述：

```
[TASK v1]
project: todo-app
autonomy: 4
mode: unattended
plan_only: false
integration_test: auto
remote: none
ci: none
mgmt_root: D:\work\todo-app-mgmt
mgmt_template: C:/Users/me/.kandev-ma/7f64865e/mgmt-template
repo: D:\work\todo-app
role: pm
scope: pm
parent: user
pm: self
branch: <自动> base main
---
给这个仓库加一个待办应用：能新增、勾选完成、删除，数据存在本地。无人值守跑完，不用问我。

接收时采用的缺省值（未询问用户）：
- project: todo-app（仓库目录名）
- plan_only: false（缺省；用户要求不提问）
- integration_test: auto（缺省；用户要求不提问）
- remote: none（不提问时不推送）
- ci: none（仓库没有 CI 配置）
- mgmt_root: D:\work\todo-app-mgmt（仓库上级目录）
- branch base: main（主仓库当前分支）
```

同样的输入去掉"无人值守跑完，不用问我"，仓库有带 upstream 的远端和 `.github/workflows/ci.yml`，部署缺省值都是 ask / auto：

1. 第 1 轮：Q2。用户选 2。
2. 第 2 轮：Q4、Q9、Q10、Q11（plan_only 在 autonomy 2 时不问）。用户选 auto、pr、local、只记录。
3. 第 3 轮：Q12、Q13。
4. 第 4 轮：确认汇总 QF，例如：

```
自主程度 2（关键节点确认）：立项评审后在「立项确认」等你批准；运行中关键取舍合并提问；人工终审等你批准。
基线分支 main；交付：推送 ma/todo-app 到 origin 并开 PR（人工终审时再问一次是否推送），main 不在本地改动。
CI：.github/workflows/ci.yml 的检查写进合并门禁；结合测试：自动；真实调用：不允许。
运行策略：发现的缺陷只记录；旧产物保留；只在需求要求时改变已有行为。
要你决定的事看 D:\work\todo-app-mgmt\project\attention.md（新建的管理目录）。
```

用户选"按这样启动"后写回，头里是 `autonomy: 2`、`mode: attended`、`remote: pr`、`push_branch: ma/todo-app`、`ci: local`，正文带「运行策略」节。
