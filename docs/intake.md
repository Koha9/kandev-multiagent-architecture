# 接收：把用户输入整理成 [TASK v1] 任务描述

> 读者：W1「接收」步骤的 agent（步骤 prompt 指向本文件），以及想知道启动项目需要哪些参数的人。
> 本文件是 `[TASK v1]` 头（pm 任务）各字段的说明：含义、怎么推导、缺省值、要不要问用户、怎么问、怎么校验、最后写成什么样。
> 各字段对后续流程的影响见 [workflow.md](workflow.md)「运行模式」和「部署与启动」。

## 1. 直接放行

任务描述同时满足下面几条时，它已经是完整的 `[TASK v1]` 描述：**不改、不提问，直接完成本步骤**。

- 第一个非空行是 `[TASK v1]`。
- 头里有这些字段且值不为空、不是 `<...>` 占位：`project`、`mode`（attended 或 unattended）、`mgmt_root`、`mgmt_template`、`repo`、`role: pm`、`branch`（含 `base <分支>`）。`branch` 行里的 `<自动>` 是固定写法，不算占位。
- 有一行 `---`，它之后有需求正文。
- `plan_only`、`integration_test`、`scope`、`parent`、`pm` 可以没有（pm 按缺省值处理）。

放行前只做第 5 节中标"放行时也查"的两项检查。不通过时只改那一行（按第 5 节：能自动改正的改正并在回复中说明，否则就那一项提问），其余原样保留。

## 2. 不完整时的处理顺序

1. 用户已写明的值（包括写了一部分的 `[TASK v1]` 头，以及自然语言）照用，不改。
2. 能推导的自己推导（第 3 节「推导」）。
3. 有缺省值且标"不问"的直接用缺省值。
4. 剩下标"要问"的才提问（第 4 节）。
5. 校验（第 5 节）→ 组装（第 6 节）→ 写回任务描述。

自然语言的对应关系：

| 用户的说法 | 字段 |
|---|---|
| 无人值守、不用问我、全自动、我不在、unattended | `mode: unattended` |
| 有问题问我、关键节点等我、半值守、attended | `mode: attended` |
| 先只出计划、先看方案、先不开发、plan only | `plan_only: true` |
| 不做结合测试、不要集成测试、跳过 e2e | `integration_test: off` |
| 管理目录放在 X、mgmt 放 X | `mgmt_root: X` |
| 基于 X 分支、从 X 切出、合回 X | `branch: <自动> base X` |
| 项目叫 X、项目名 X | `project: X` |

用户写明"不要提问"或 `mode` 已确定为 unattended 时：不提问，标"要问"的字段全部采用第 3 节的缺省值（不是提问时的推荐答案：unattended 下 `plan_only: true` 会让项目停在门禁等人），并写进「接收时采用的缺省值」。唯一的例外是需求（见 Q1）。用户在 Q2 选了 unattended 之后同样不再发后续批次。

不提问时，没有缺省值的字段（`repo`、基线分支）推导不出或校验不通过：停下说明原因，不完成本步骤，不编造值。第 5 节中"问 Qn"的处理在不提问时都按这一条。

## 3. 字段

| 字段 | 含义 | 推导 | 缺省值 | 缺少时 |
|---|---|---|---|---|
| `project` | 项目名，用于标题和报告 | 用户写的名称；否则 `repo` 的目录名 | repo 目录名 | 不问 |
| `mode` | attended：关键节点等用户；unattended：全程不提问，决定写 ADR 等事后追认 | 见第 2 节的对应关系 | attended | **要问**（Q2） |
| `plan_only` | true：立项评审通过后停在「立项确认」，用户看过计划再投入开发额度 | 见第 2 节 | false | `mode` 也未知时**要问**（Q3）；`mode` 已知时不问，用缺省值 |
| `integration_test` | auto：其他模块完成后自动做结合测试；off：不做 | 见第 2 节 | auto | **要问**（Q4） |
| `repo` | 主仓库的绝对路径（不是任务的 worktree） | 在当前工作目录运行 `git rev-parse --path-format=absolute --git-common-dir`，取结果的上级目录（去掉末尾的 `.git`）；失败时用 `list_repositories_kandev` 找本任务的仓库 | — | 推导不出才问（Q6） |
| `branch` | 固定写成 `<自动> base <基线分支>`。基线分支是最终合入的分支，在「收尾合并」之前不被改动 | 用户写明的；否则本任务创建时选的 base branch（`list_tasks_kandev` 返回的任务信息里有就用）；否则 `git -C <repo> symbolic-ref --short HEAD`（主仓库当前检出的分支） | — | 推导结果不是 `main` / `master`、且用户没提到它时确认一次（Q5）；推导不出也问 Q5 |
| `mgmt_root` | 本项目的管理目录（绝对路径）。必须在 `repo` 和所有 worktree 之外 | 用户写明的；否则 `<repo 的上级目录>/<repo 目录名>-mgmt` | 同左 | 不问。缺省路径已存在且不是空目录时：其中 `project/registry.json` 的 `project` 与本项目相同 → 保留（继续同一个项目）；否则改用 `<缺省路径>-<yyyyMMdd-HHmm>`，写进缺省值清单；仍不可用才问（Q7） |
| `mgmt_template` | 管理目录模板 | `<arch_root>/mgmt-template`（arch_root 见步骤 prompt） | 同左 | 不问 |
| `role` | 固定 `pm` | — | pm | 不问 |
| `scope` | 固定 `pm` | — | pm | 不问 |
| `parent` | 固定 `user` | — | user | 不问 |
| `pm` | 固定 `self` | — | self | 不问 |
| 需求正文 | `---` 之后的内容：项目目标、需求、约束、技术栈与环境要求、额度约定 | 用户原文，一字不改 | — | 没有可执行的需求时**要问**（Q1） |
| 额度约定 | 是否允许消耗额度的真实调用（真实 AI、付费 API、部署、推送远端）以及次数上限，写在需求正文里 | 用户写明的 | 一律不允许（开关默认关闭） | 只有需求明显依赖这类调用、而用户没写时才问（Q8） |

技术栈、环境要求、需求的优先级和取舍**不由接收步骤询问**：它们是 pm 在「立项规划」的工作（attended 时 pm 会合并提问，unattended 时写 ADR）。接收步骤只保证 pm 拿到完整的头和用户原话。

"可执行的需求"：读完能知道要做出什么东西。只有一个标题（"做个网站"）、只有参数没有正文、或正文只是"见附件"而没有附件内容，都算没有。

## 4. 提问

用 `ask_user_question_kandev`。**一次调用最多 4 个问题**。把需要问的问题按 Q1 → Q8 的顺序排好，每 4 个一批；上一批得到回答后再发下一批；最多 3 批。不需要问的问题不占位置（例如只缺 mode 和 plan_only 时，一批 2 个问题）。

每个问题：一句话说明这个选择影响什么，给出选项，把推荐答案放在第一个并标"（推荐）"，附一句理由。选项之外用户可以自己填写。

| # | 什么时候问 | 问题 | 选项（第一个是推荐） |
|---|---|---|---|
| Q1 | 没有可执行的需求 | 这个项目要做什么？请按重要度逐条写出需求（一条一行），以及约束和不做的事。 | 自由填写（选项给："我现在补充需求"、"取消，稍后重新建任务"） |
| Q2 | `mode` 未知 | 运行过程中需要你决定的事怎么处理？ | attended（推荐）：关键节点合并成一次提问等你回答，适合第一次用或需求还有歧义 / unattended：全程不提问，agent 自行决定并记入 attention.md，等你事后追认 |
| Q3 | `plan_only` 和 `mode` 都未知（`mode` 已知为 attended 时两种取值都会停在「立项确认」，不用问） | 立项计划出来后要不要先停下来给你看？ | 先看计划再开发（plan_only: true，推荐：开发会消耗大量模型额度，先确认模块划分和验收标准）/ 评审通过后直接开发（plan_only: false；attended 时仍会在「立项确认」等你） |
| Q4 | `integration_test` 未知 | 所有模块完成后，是否自动做跨模块的结合测试？ | auto（推荐）：自动合并各模块并写、跑自动化结合测试，能发现模块各自通过但组装后不能用的问题 / off：不做，省额度，适合单模块或纯库项目 |
| Q5 | 基线分支需要确认或推导不出 | 以哪个分支为基线？完成后合回这个分支，合回之前它不会被改动。 | 推导出的分支（推荐）/ `main` / 仓库中其他最近更新的分支（最多列 2 个，`git -C <repo> branch --sort=-committerdate`） |
| Q6 | `repo` 推导不出 | 目标仓库在本机的绝对路径是什么？ | `list_repositories_kandev` 返回的仓库路径（最多 3 个）；自由填写 |
| Q7 | `mgmt_root` 的缺省路径和带时间后缀的路径都不可用 | 管理目录放在哪里？必须在仓库和 worktree 之外。 | 自由填写（选项给一个你能找到的可写位置） |
| Q8 | 需求明显依赖消耗额度的调用而没有约定 | 是否允许测试和验收时做真实调用（会产生费用）？ | 不允许，全部用 mock（推荐，可以事后再开）/ 允许，每种调用最多 N 次（请填 N） |

提问次数的上限：同一个字段最多问 2 次（第二次只在校验不通过时）。3 批之后仍缺的字段采用第 3 节的缺省值并写进缺省值清单；缺的是需求或 `repo` 时不采用缺省值，停下并说明（不调用 step_complete_kandev）。

用户在回答里顺带写了别的要求：原话记入第 6 节的「补充」，不自己解读成字段以外的决定。

## 5. 校验

| 检查 | 不通过时 | 放行时也查 |
|---|---|---|
| `repo` 存在，且 `git -C <repo> rev-parse --git-dir` 成功 | 问 Q6 | 是 |
| `mgmt_template` 存在且其中有 `README.md` | 改为 `<arch_root>/mgmt-template`（放行时也只改这一行，并在回复中说明）；它也不存在 → 停下说明 | 是 |
| 基线分支存在：`git -C <repo> rev-parse --verify <分支>` | 问 Q5 | 否 |
| `mgmt_root` 是绝对路径，不在 `repo` 之内，也不在当前工作目录（任务 worktree）之内 | 改用缺省路径；仍不行问 Q7 | 否 |
| `mgmt_root` 已存在且不是空目录 | 有 `project/registry.json` 且其中的 `project` 与本项目相同 → 保留（这是在继续同一个项目）；否则：用户写明的路径 → 问 Q7，缺省路径 → 按第 3 节换成带时间后缀的路径 | 否 |
| `mode` 是 attended / unattended；`plan_only` 是 true / false；`integration_test` 是 auto / off | 按第 2 节的对应关系改写；对应不上问对应的问题 | 否 |

只读检查，不创建目录、不建分支、不改仓库。路径统一写成绝对路径；Windows 上用反斜杠或正斜杠都可以，保持用户写的样子。

## 6. 输出格式

新的任务描述（整体替换原描述）：

```
[TASK v1]
project: <项目名>
mode: attended | unattended
plan_only: true | false
integration_test: auto | off
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

补充（接收步骤提问所得，用户原话）：
- Q：<问题> A：<回答原话>

接收时采用的缺省值（未询问用户）：
- <字段>: <值>（<推导方式或"缺省">）
```

- `branch` 一行里的 `<自动>` 照写这三个字符（任务分支由 Kandev 自动创建）。
- 头里每行一个字段，`字段: 值`，不加注释、不加引号、不加粗；守护脚本按行首的 `mgmt_root:` 解析。
- 「补充」和「接收时采用的缺省值」没有内容时整节省略。
- Q1 的回答（需求）写在「补充」里，原话照录；不改写、不合并、不排序。
- 任务标题不改。

## 7. 例子

用户输入：

```
给这个仓库加一个待办应用：能新增、勾选完成、删除，数据存在本地。无人值守跑完，不用问我。
```

接收步骤：`mode` 从"无人值守""不用问我"得到 unattended，因此不提问；其余字段推导或取缺省值。写回的任务描述：

```
[TASK v1]
project: todo-app
mode: unattended
plan_only: false
integration_test: auto
mgmt_root: D:\work\todo-app-mgmt
mgmt_template: D:/tools/kandev-multiagent-architecture/mgmt-template
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
- mgmt_root: D:\work\todo-app-mgmt（仓库上级目录）
- branch base: main（主仓库当前分支）
```

同样的输入去掉"无人值守跑完，不用问我"：缺 `mode`、`plan_only`、`integration_test` 三项，一批问完（Q2、Q3、Q4），不需要第二批。
