# AGENTS.md：给 agent 的入口

本仓库是一套在 [Kandev](https://github.com/kdlbs/kandev) 上运行的多 agent 开发 workflow：三套 Kandev workflow（项目管理 / 模块管理 / 开发）、每个项目一个管理目录、一个守护 automation。给人看的介绍在 [README.md](README.md)。

你可能被要求做下面 A–G 中的一项或几项。先读对应的小节，再动手。

## 源仓库与安装目录

- **源仓库**：从 GitHub 克隆下来的本仓库。用来安装（A 的前 3 步）、升级（G）、修改 workflow 本身（E）。
- **安装目录**（下文写作 `<home>`）：`ma.py install` 复制出来的目录，缺省 `~/.kandev-ma/<workspace id 前 8 位>/`。Kandev 里的 workflow 和守护只依赖它，安装后删除源仓库不影响运行。部署、验收、启动项目、定制（A 第 4 步起、B、C、D、F）都在安装目录里做。

用户选了链接模式时没有单独的安装目录，`<home>` 就是源仓库。不确定自己在哪里时运行 `python kandev/ma.py doctor --offline`：第一行写着 `standalone`（安装目录）或 `link`；报"没有 ma-manifest.json"说明这是还没安装过的源仓库。

## 先读这些

| 文件 | 什么时候读 |
|---|---|
| [kandev/README.md](kandev/README.md) | 部署（A）：`ma.py` 各命令和答案文件 |
| [rules/README.md](rules/README.md) | 定制（F）：可以定制的规则槽位 |
| [docs/intake.md](docs/intake.md) | 启动项目（C）：`[TASK v1]` 头的字段、缺省值、提问方式 |
| [docs/workflow.md](docs/workflow.md) | 修改 workflow（E）时全读；选 profile 时读「角色与 profile」；其他任务不需要先读 |
| [docs/prompts.md](docs/prompts.md) | 需要知道某个步骤的 agent 具体会收到什么 prompt 时 |
| [mgmt-template/README.md](mgmt-template/README.md) | 检查项目进度时：管理目录的结构 |
| [evaluation/bench/README.md](evaluation/bench/README.md) | 跑基准（D） |

## 规则

- **按提问清单问用户**。部署、定制、升级之前运行 `python kandev/ma.py questions --stage <install|customize|redeploy|upgrade>`：
  - 「必须问」的项要有用户的明确回答，不能替用户填；「选了自定义才问」的项，用户选快速安装时用推荐值。
  - 「ma.py 停下来时才问」的项平时不用问：`ma.py` 遇到那种情况会停下并说明，这时问用户，同意后带上它给出的参数重新运行。
  - 相关问题合并成一次提问，每题给选项、推荐答案和一句理由。
- **改动 Kandev 之前先说明**要做什么、影响哪个 workspace。导入或更新 workflow 由上面的清单覆盖；清单之外的改动（创建任务、启动会话、创建 automation）单独征得同意。只读查询不用问。
- **会产生费用的操作单独确认**：启动 agent 会话（验收 B3、启动项目、跑基准）会消耗用户的模型额度。
- **不删除任何东西**。脚本也不删除。需要删除的（临时任务、旧 workflow、合并后的 `.new` 文件）列出来交给用户，或在用户明确同意后再做。
- **生成的文件不手改**：`docs/prompts.md`、`kandev/export/*.json` 由脚本生成，prompt 的来源是 `kandev/prompts.py` 和 `rules/`。
- **本机文件不提交、不手改**：`.gitignore` 列出的那些（`ma-manifest.json`、ids、答案、`custom/`、`*.local.*`、`.new` / `.mine` / `.bak`）。
- 运行脚本用本机的 Python 3 解释器（只用标准库），下文写作 `python`。
- Kandev 外部 MCP 默认在 `http://localhost:38429/mcp`。你自己有 kandev MCP 工具时直接调用；没有时用脚本里的客户端：
  ```
  python -c "import sys,json; sys.path.insert(0,'kandev'); from kandev_client import Kandev; print(json.dumps(Kandev().call('list_workspaces_kandev', {}), ensure_ascii=False, indent=1))"
  ```

## A. 部署到 Kandev workspace

前提：源仓库在运行 Kandev 的那台机器上（安装目录也建在这台机器上，守护每 20 分钟要运行其中的脚本）。

1. **确认 Kandev**：调用 `list_workspaces_kandev`。连不上就停下，请用户启动 Kandev 或给出 MCP 地址（地址不是默认值时写进答案的 `kandev_url`）。
2. **提问**（问题树，逐批问）：先运行 `python kandev/ma.py questions --stage install` 看整棵树，再逐批问：
   - 第一批固定是 `setup_style`、`workspace_id`、`guard_automation`。`workspace_id` 先调用 `list_workspaces_kandev` 列给用户选；`setup_style` 第一次部署推荐 guided，并说明 quick 会由你按推荐值和检测结果决定其余各项，最后给一张总表确认。
   - 每批回答后写进答案文件（例如 `kandev/answers.local.json`），运行 `python kandev/ma.py questions --stage install --answers kandev/answers.local.json`，它只列出现在该问的项。照着问下一批，直到它打印「没有待问的问题」。每批合并成一次提问（一次最多 4 题时按顺序分几次），每题给选项、推荐答案和一句理由。
   - `profiles`：先调用 `list_agent_profiles_kandev`，按 `model_strategy` 的答案选。auto：按 [docs/workflow.md](docs/workflow.md)「角色与 profile」选；vendor：只在用户选的厂商里选，`reviewer_cross_vendor=yes` 时 reviewer、auditor 换厂商；per_role：逐个角色请用户选。无论哪种都把结果列成表给用户确认（mode 应能无人值守执行；缺合适的 profile 时告诉用户需要新建什么样的，不要自己创建）。
   - `project_defaults.*` 是之后每个项目的缺省值（推送、CI、自主程度、plan_only、结合测试、付费调用），由「接收」读取；`ask` 表示每个项目再问。
   - 最后把 `questions --answers` 打印的总表给用户确认。quick 时必须做：表里标「推荐值」的项是你决定的。
3. **安装**：把答案写成 JSON 文件（留在源仓库，例如 `kandev/answers.local.json`，格式见 [kandev/README.md](kandev/README.md)），运行：
   ```
   python kandev/ma.py install --answers kandev/answers.local.json
   ```
   答案不合格（缺必问项、profile 违反"必须不同"的约束、路径含空格等）时它会逐条列出，照着问用户或改正。独立安装会把文件复制到 `<home>`；`<home>` 已存在且不为空时它会停下，不覆盖。之后的命令都在 `<home>` 中运行。
4. **定制**（用户选了自定义时）：做 F 的第 1、2 步。
5. **部署**：
   ```
   python <home>/kandev/ma.py diff
   python <home>/kandev/ma.py apply
   ```
   `diff` 说明 workspace 里的现状（没有同名 workflow / 可以就地更新 / 属于另一个系列）和将要改变的内容。`apply` 做自检、导入或就地更新、生成守护交接文件、重新导出。它停下来要求 `--confirmed`、`--with-running` 或 `--retire` 时，按它的说明问用户后再带上参数运行。
   - 链接模式下同一个仓库可以部署到多个 workspace：每个 workspace 写一份答案各 `install` 一次，之后的命令加 `--workspace <id>`。独立安装是每个 workspace 一个安装目录。
6. **守护**：按 `apply` 结尾打印的说明做。用户选了 `yes`：你在 Kandev 内部且有 `create_automation_kandev` 时，执行交接文件（`<home>/kandev/handoff/guard-handoff.<前 8 位>.local.md`）里的「交接 prompt」；没有这个工具（外部 MCP 没有）时把交接文件的路径交给用户，请用户在任一 Kandev 任务里把「交接 prompt」交给 agent。用户选了 `skip`：不建，提醒用户项目卡住时不会有告警。
7. 接着做 B，最后把安装目录的路径告诉用户。

## B. 验收部署

逐项核对，最后用一张表汇报每项 pass / fail / unverified（附原因）。路径相对 `<home>`。

1. **自检**：`python kandev/check_docs.py` 全部 OK。
2. **部署一致**：`python kandev/ma.py doctor` 没有 FAIL，WARN 逐条说明。它核对：已部署的三套 workflow（prompt、步骤顺序、事件、开关、会话策略）与安装目录一致；写进 Kandev 的路径指向本目录；ids 文件里的步骤与脚本一致；守护 automation 存在。再看一眼 `python kandev/verify_export.py --ids <ids 文件>` 的输出：所有带 prompt 的步骤 `prof=` 不是 `-`，并且是第 A2 步确认的模型（接收 = intake，立项评审 = plan_auditor，W2 验收调查 = module_auditor，W2 其余 = module）。
3. **「待开发」行为**（会启动一次真实会话：先问用户，不做就记 unverified）：
   | # | 操作 | 期望 |
   |---|---|---|
   | a | 在 W3 建临时任务 A：`workflow_step_id`=「待开发」，`start_agent=false`，不设 blocked_by，prompt="只回复 OK，然后结束本轮，不做任何其他事" | A 停在「待开发」，没有会话 |
   | b | 等 1 分钟后再看 A | A 仍在「待开发」，没有被自动启动 |
   | c | 把 A 移到「开发」 | A 启动会话；回复 OK 后因为没有完成信号停在「开发」 |
   | d | 给 A 发消息"把自己移到「等待决策」后结束本轮"；A 移过去后再把它移回「开发」 | 移回后沿用原来的开发会话，不新建会话 |
   | e | 请用户删除 A（或经同意后删除） | 不留下 worktree 或分支 |

   任一项不符合期望：记为 fail，不要启动项目，回报给用户。
4. **守护**（用户选了 `skip` 时记 unverified）：`list_settings_resources_kandev`（`resource_type=automation`）中有「多Agent 守护」且已启用；`python kandev/stage.py --ids <ids 文件> --json --dry-run` 退出码 0（`--dry-run` 不能省：不带它，这次看到的告警会被记成已发，守护 60 分钟内不再发）；守护运行过一次后，`kandev/guard_state/` 下的心跳文件（`last_run*.json`）的 `at` 在 40 分钟以内。
5. **端到端**（可选，费用较高）：做 D。

## C. 启动一个项目

用户自己在 Kandev 里新建任务时只需要写需求：W1 的「接收」步骤会推导参数、向用户提问并补全 `[TASK v1]` 头。你代用户启动项目时写好完整的头，「接收」会原样放行，不再提问。

1. 按 [docs/intake.md](docs/intake.md) 第 3 节的字段逐项向用户确认：
   - 目标仓库和基线分支；需求（按重要度排序，一条一行）。
   - `autonomy`（1–4）。`mode` 由它导出：1、2 → attended，3、4 → unattended；1 时 `plan_only: true`。
   - `plan_only`、`integration_test`。
   - 交付方式：`remote`（none / push / pr）与 `push_branch`，以及 `ci`。
   - autonomy 1–3 时的运行策略：缺陷本轮修还是只记录、旧产物保留还是删除、是否允许改变已有行为。写进正文「运行策略」节。
   - 技术栈与环境要求、额度约定（见 [docs/project-conventions.md](docs/project-conventions.md)）。

   安装目录有 `custom/project-defaults.json` 时，其中的具体值作为推荐答案。
2. 在「多Agent · 项目管理」中创建任务（`create_task_kandev`，`workflow_id` 取自 `<home>/kandev/` 下该 workspace 的 ids 文件，选好仓库），描述按 intake.md 第 6 节的格式。`mgmt_root` 放在仓库和 worktree 之外；`mgmt_template` 写 `<home>/mgmt-template` 的绝对路径。头写全（含 autonomy、remote、ci）时「接收」不提问，只校验 autonomy 与 mode / plan_only 是否一致。
3. 经用户同意后启动任务。之后用户只需要看两处：`<mgmt_root>/project/attention.md`（需要用户决定的事）和 `<mgmt_root>/agents/guard/stage.md`（现在在等谁）。

## D. 跑基准项目

按 [evaluation/bench/README.md](evaluation/bench/README.md)：用固定的待办应用需求启动一个 unattended 项目，到达「人工终审」后用 `evaluation/metrics.py` 采集指标。会产生真实费用，先征得用户同意（耗时见该文档；加上 baseline 和结合测试模块后还没有实测）。

## E. 修改 workflow 本身

在源仓库里做（用它直接部署时用链接模式）。只想调整规则、角色卡或参数的用户不需要做这一节，做 F。

1. 只改 `kandev/prompts.py`（结构和 prompt；写法见它开头的说明，`python kandev/build_workflows.py stats` 看每个步骤的字符数和携带的共享块）、`rules/`（槽位的出厂内容）与 `mgmt-template/`（模板、角色卡）。改了 `[TASK v1]` 头的字段或缺省值时同步 [docs/intake.md](docs/intake.md)；改结构或改了需要用户知道的行为时同步 [docs/workflow.md](docs/workflow.md)。
2. `python kandev/build_workflows.py dump --out docs/prompts.md`
3. `python kandev/check_docs.py` 全部 OK。它会检查：步骤名与 `stage.py`、文档一致，prompt 里的占位符，新增的规则槽位已在 `kandev/deploy_questions.json` 登记。改了 `stage.py` 或 `ma.py` 时同步更新 `kandev/tests/`。
4. 改了版本号（`prompts.py` 的 `VERSION`）时，同步 `docs/workflow.md` 标题和 `mgmt-template/VERSION`，并在 `CHANGELOG.md` 写一节（改了什么、为什么、代价、升级注意、守护 prompt 是否变化）。
5. 部署：`ma.py diff` → 问用户 → `ma.py apply --confirmed <值>`，然后做 B。已有独立安装目录的，按 G 升级它。

## F. 定制规则、角色卡和参数

在 `<home>` 中做。能定制的东西和格式见 [rules/README.md](rules/README.md)。

1. 运行 `python kandev/ma.py questions --stage customize`，问用户要定制哪几项、每项的具体要求。
2. 按用户的要求写文件：
   - 规则槽位（`git`、`coding`、`testing`、`workspace`、`quality`）：把 `rules/<槽位>.md` 复制到 `custom/rules/<槽位>.md`，在副本的 `---` 之后写正文。不改 `rules/` 里的出厂文件。
   - 参数：新建 `custom/rules/params.json`，只写要改的键（`dev_wip`、`refresh_wakes`、`guard`）。
   - 角色卡、消息协议、项目模板（`mgmt-template/`）和「接收」的参数缺省值（`docs/intake.md`）：独立安装时直接改 `<home>` 里的文件，升级时改过的文件会保留。它们在新项目启动时生效，不需要重新部署；进行中的项目用的是启动时复制到管理目录里的那一份。
   - 步骤结构、消息协议的格式、分支拓扑、`stage.py` 的判断规则属于引擎，不在定制范围内。用户要改这些时说明属于 E。
3. 规则槽位和参数要重新部署才生效：`python kandev/ma.py diff` 把变化讲给用户，同意后 `python kandev/ma.py apply --confirmed <值>`。
4. `python kandev/ma.py doctor` 没有 FAIL（它会列出定制了哪些槽位）。

## G. 升级

1. 取得新版源仓库（已有克隆时 `git pull`；源仓库已被删除时重新克隆）。
2. 独立安装：在新版源仓库中运行 `python kandev/ma.py upgrade --home <home> --dry-run` 看会改什么，再去掉 `--dry-run` 运行。用户没改过的出厂文件直接更新，改过而新版没变的保留，`custom/`、ids、守护状态、答案都不动。它因为冲突或进行中的项目停下时，按说明问用户后带上参数重新运行；选了保留用户版本时，可以帮用户把 `.new` 里的变化合并进去。链接模式跳过这一步。
3. 升级只改文件，Kandev 里的 workflow 还是旧的：在 `<home>` 中运行 `python kandev/ma.py diff`，把变化讲给用户，同意后 `python kandev/ma.py apply --confirmed <值>`。
4. 守护：`apply` 结尾会说守护 prompt 有没有变化；变了就按 A6 用新的交接文件更新 automation。
5. 做 B 的第 1、2、4 项。
