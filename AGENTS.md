# AGENTS.md：给 agent 的入口

本仓库是一套在 [Kandev](https://github.com/kdlbs/kandev) 上运行的多 agent 开发 workflow：三套 Kandev workflow（项目管理 / 模块管理 / 开发）、每个项目一个管理目录、一个守护 automation。给人看的介绍在 [README.md](README.md)。

你可能被要求做下面 A–G 中的一项或几项。先读对应的小节，再动手。

## 源仓库与安装目录

这份文件可能在两种地方：

- **源仓库**：从 GitHub 克隆下来的本仓库。用来安装（A）、升级（G）、修改 workflow 本身（E）。
- **安装目录**（下文写作 `<home>`）：`ma.py install` 复制出来的目录，缺省 `~/.kandev-ma/<workspace id 前 8 位>/`，根目录有 `ma-manifest.json`。Kandev 里的 workflow 和守护只依赖它，安装后删除源仓库不影响运行。部署、验收、启动项目、定制（A 第 4 步起、B、C、F）都在安装目录里做。

用户选了链接模式时没有单独的安装目录，`<home>` 就是源仓库。判断方法：根目录有 `ma-manifest.json` 且其中 `mode` 是 `standalone` → 你在安装目录里；`link` 或没有这个文件 → 你在源仓库里。

## 先读这些

| 文件 | 什么时候读 |
|---|---|
| [docs/workflow.md](docs/workflow.md) | 任何任务都先读：角色、三套 workflow 的步骤、门禁、并发、已知限制 |
| [kandev/README.md](kandev/README.md) | 部署（A）、修改 workflow（E） |
| [kandev/deploy_questions.json](kandev/deploy_questions.json) | 部署、定制、升级前：必须向用户确认的事项（用 `ma.py questions` 查看） |
| [rules/README.md](rules/README.md) | 定制（F）：可以定制的规则槽位 |
| [docs/intake.md](docs/intake.md) | 启动项目（C）时：`[TASK v1]` 头的字段、缺省值、提问方式；「接收」步骤的 agent 也读它 |
| [docs/prompts.md](docs/prompts.md) | 需要知道某个步骤的 agent 具体会收到什么 prompt 时 |
| [mgmt-template/README.md](mgmt-template/README.md) | 启动项目（C）或检查项目进度时：管理目录的结构 |
| [evaluation/bench/README.md](evaluation/bench/README.md) | 跑基准（D） |

## 规则

- **按提问清单问用户**：部署、定制、重新部署、升级之前，先运行 `python kandev/ma.py questions --stage <install|customize|redeploy|upgrade>`，把其中的事项向用户问清楚。标「必须问」的项要有用户的明确回答，不能替用户填；标「选了自定义才问」的项，用户选快速安装时用推荐值。相关问题合并成一次提问，每题给选项、推荐答案和一句理由。答案不全时 `ma.py` 会拒绝执行并列出缺哪几项。
- **改动 Kandev 之前先问用户**：导入或改名 workflow、创建任务、启动会话、创建 automation，都要先说明要做什么、影响哪个 workspace，得到同意再做。只读查询不用问。
- **会产生费用的操作单独确认**：启动 agent 会话（验收 B3、启动项目、跑基准）会消耗用户的模型额度。
- **不删除任何东西**。脚本也不删除。需要删除的（例如临时任务、旧 workflow、合并后的 `.new` 文件）列出来交给用户，或在用户明确同意后再做。
- **prompt 的唯一来源是 `kandev/build_workflows.py` 和 `rules/`**。不要手改 `docs/prompts.md` 或 `kandev/export/*.json`，它们都是生成的。
- **定制不改出厂文件**：规则槽位的定制写在 `custom/rules/`，不改 `rules/` 里的文件（见 F）。
- **本机文件不提交**：`ma-manifest.json`、`custom/`、`kandev/profiles*.local.json`、`kandev/kandev_ids*.json`、`kandev/answers*.local.json`、`kandev/guard_state/`、`*.local.md`、`*.new`、`*.mine`、`*.bak`。
- 运行脚本用本机的 Python 3 解释器（只用标准库），下文写作 `python`。
- Kandev 外部 MCP 默认在 `http://localhost:38429/mcp`。你自己有 kandev MCP 工具时可以直接调用；没有时，脚本里的 `Kandev` 类可以调用任何工具：
  ```
  python -c "import sys,json; sys.path.insert(0,'kandev'); from kandev_client import Kandev; print(json.dumps(Kandev().call('list_workspaces_kandev', {}), ensure_ascii=False, indent=1))"
  ```

## A. 部署到 Kandev workspace

前提：源仓库在运行 Kandev 的那台机器上（安装目录也会建在这台机器上；守护每 20 分钟要在本机运行 `<home>/kandev/stage.py`）。

1. **确认 Kandev**：调用 `list_workspaces_kandev`。连不上就停下，请用户启动 Kandev 或给出 MCP 地址。
2. **提问**：运行 `python kandev/ma.py questions --stage install`，按清单问用户。其中几项要先查再问：
   - `workspace_id`：把 `list_workspaces_kandev` 的结果列给用户选。
   - `profiles`：调用 `list_agent_profiles_kandev`，为 5 个必填角色各选一个 profile，4 个可选角色按需要选（不填时用括号中的缺省），规则见 [docs/workflow.md](docs/workflow.md)「角色与 profile」：
     - `pm`、`auditor`：强模型，**两者必须是不同的 profile**
     - `plan_auditor`（缺省 = auditor）：立项评审，上下文小、影响最大，适合最强模型；**必须与 pm 不同**
     - `module`（缺省 = pm）：模块管理，强模型；`module_auditor`（缺省 = auditor）：模块验收，强模型，**必须与 module 不同**
     - `developer`：主力编码模型；`reviewer`：**与 developer 不同的 profile**，最好不同厂商
     - `mechanical`：合并门禁和收尾合并，编码模型
     - `intake`（缺省 = mechanical）：W1 第 0 步「接收」，只整理启动参数和提问，轻量模型即可（例如 Sonnet）
     - mode 应能无人值守执行（不会每步都等权限确认）

     把你的选择列成表交给用户确认。缺合适的 profile 时，告诉用户需要新建什么样的 profile，不要自己创建。
   - `existing_workflows`：调用 `list_workflows_kandev`。没有「多Agent · 项目管理 / 模块管理 / 开发」填 `none`；有且 description 里的版本号属于同一系列（major.minor 相同，例如 `[v3.3]` 和 `[v3.3.1]`）只能 `update`（就地更新 prompt、profile、description 和步骤结构，步骤 ID 和任务不变）；其他系列只能 `retire`（旧版改名为"<名称> (<旧版本号>)"，任务保留）。workspace 里有进行中的项目时向用户说明影响。
3. **安装**：把答案写成 JSON 文件（例如 `kandev/answers.local.json`，键见清单），运行：
   ```
   python kandev/ma.py install --answers kandev/answers.local.json
   ```
   独立安装（缺省）会把运行所需的文件复制到 `<home>` 并写出 `<home>/ma-manifest.json`；链接模式只在本仓库写出 `ma-manifest.json`。`<home>` 已存在且不为空时它会停下，不覆盖。之后的命令都在 `<home>` 中运行。
4. **定制**（用户选了自定义时）：做 F 的第 1–3 步。
5. **部署**：
   ```
   python <home>/kandev/ma.py diff
   python <home>/kandev/ma.py apply
   ```
   `apply` 依次做：重新生成 `docs/prompts.md` → `check_docs.py` 自检（必须全部 OK）→ 导入或就地更新三套 workflow 并写出 ids 文件 → 生成守护交接文件 → 重新导出 `kandev/export/`。就地更新已有的 workflow 时，它要求先运行 `diff` 把变化给用户看，再带上 `--confirmed <diff 打印的值>`；有进行中的项目时还要用户同意后加 `--with-running`。
   - 同一个目录部署到多个 workspace（链接模式）时，每个 workspace 一份答案，`install` 会给后面的 workspace 用带前 8 位 id 的 ids / profiles 文件名；命令加 `--workspace <id>`。独立安装是每个 workspace 一个安装目录。
6. **守护 automation**（每个 workspace 一个）：`apply` 结束时打印了交接文件的路径（`<home>/kandev/handoff/guard-handoff.<前 8 位>.local.md`，占位已填好）。按用户对 `guard_automation` 的回答做：
   - `create`，且你在 Kandev 内部运行、有 `create_automation_kandev`：按交接文件中的「交接 prompt」执行。
   - `create` 但没有这个工具（外部 MCP 没有），或 `manual`：把交接文件的路径交给用户，请用户在任一 Kandev 任务里把「交接 prompt」交给 agent，或在 Kandev 设置 → Automations 手动建。
7. 接着做 B。

## B. 验收部署

逐项核对，最后用一张表汇报每项 pass / fail / unverified（附原因）。下面的路径都相对 `<home>`。

1. **自检**：`python kandev/check_docs.py` 全部 OK；`python kandev/tests/test_stage.py` 输出 `OK test_stage`；`python kandev/ma.py doctor` 没有 FAIL（WARN 逐条说明）。
2. **结构**：`python kandev/verify_export.py` 的输出中：
   - W1 有 11 个步骤（0 接收 … 9 刷新、10 完成，没有「待立项」「环境基线」）；`8 收尾合并` 的 on_turn_complete 是 `move_to_step {'step_position': 10}`，「接收」start=True、on_enter 是 auto_start_agent、on_turn_complete 是 move_to_next，「立项规划」start=False；接收、立项评审、项目验收、收尾合并的会话策略是 `new/complete`；`5 调度` 的 on_enter 是 reset_agent_context + auto_start_agent；`3 立项确认` 的 on_turn_start 是 `move_to_step {'step_position': 1}`，`7 人工终审` 的是 `move_to_step {'step_position': 4}`。
   - W2 有 5 个步骤（`3 刷新`、`4 完成`），「等待开发」的事件含 reset_agent_context + auto_start_agent 和 `on_children_completed: move_to_next`；「验收调查」的会话策略是 `new/complete`，on_turn_complete 是 `move_to_step {'step_position': 4}`。
   - 三套 workflow 都是：最后一个步骤是「完成」且 `done=True`，其他步骤 `done=False`（Kandev 只对最后一个步骤执行 complete_task_on_enter；不满足时模块任务不会变成 COMPLETED，依赖它的模块不启动）。
   - W3：`0 待开发`（无 prompt、无事件、wip=0）、`1 开发`（start=True，wip=4，定制了 `dev_wip` 时是定制的值）、`2 审核` 的 on_turn_complete 是 `move_to_step {'step_position': 4}`、`4 合并` 的 on_turn_complete 是 `move_to_step {'step_position': 5}`（没有 on_pr_merged）。
   - 所有 agent 步骤的 profile 是第 A2 步确认的那几个模型，不是 `-`（接收 = intake，立项评审 = plan_auditor，W2 验收调查 = module_auditor，W2 其余 = module）。
   - `kandev/export/W1-project.json` 的「接收」prompt 中出现 `<ARCH_ROOT>/docs/intake.md`（部署的 prompt 里是 `<home>` 的绝对路径，导出时被替换回占位符）；这个路径在运行 Kandev 的机器上存在。
   - `kandev/export/W2-module.json` 中出现 `<W3_DEV_STEP_ID>`、`<W3_HOLD_STEP_ID>`（说明部署的 prompt 里写入了真实 ID，导出时被替换回占位符）。
3. **「待开发」行为**（会启动一次真实会话；用户对 `acceptance_run` 回答 `no` 时不做，记为 unverified）：
   | # | 操作 | 期望 |
   |---|---|---|
   | a | 在 W3 建临时任务 A：`workflow_step_id`=「待开发」，`start_agent=false`，不设 blocked_by，prompt="只回复 OK，然后结束本轮，不做任何其他事" | A 停在「待开发」，没有会话 |
   | b | 等 1 分钟后再看 A | A 仍在「待开发」，没有被自动启动 |
   | c | 把 A 移到「开发」 | A 启动会话（on_enter auto_start，对应 workflow.md「部署后需要实测的平台行为」a）；回复 OK 后因为没有完成信号停在「开发」 |
   | d | 给 A 发消息"把自己移到「等待决策」后结束本轮"；A 移过去后再把它移回「开发」 | 移回后沿用原来的开发会话（同上 b），不新建会话 |
   | e | 请用户删除 A（或经同意后删除） | 不留下 worktree 或分支 |

   任一项不符合期望：记为 fail，不要启动项目，回报给用户。
4. **守护**：`list_settings_resources_kandev`（`resource_type=automation`）中有「多Agent 守护」且已启用；`python kandev/stage.py --ids <ids 文件> --json` 退出码 0（没有进行中的项目时无输出）；守护运行过一次后，`kandev/guard_state/last_run.json` 的 `at` 在 20 分钟以内。
5. **端到端**（可选，费用较高）：做 D。

## C. 启动一个项目

用户自己在 Kandev 里新建任务时只需要写需求：W1 的「接收」步骤会推导参数、向用户提问并补全 `[TASK v1]` 头（见 [docs/intake.md](docs/intake.md)）。你代用户启动项目时按下面的步骤写好完整的头，「接收」会原样放行，不再提问。

1. 向用户确认：目标仓库（本机绝对路径和基线分支）、需求（按重要度排序，一条一行）、`mode`（attended：关键节点等用户；unattended：全程不提问）、是否 `plan_only`（只做到规划，先看计划再投入开发额度）、`integration_test`（auto：其他模块完成后自动做结合测试，缺省；off：不做）、技术栈与环境要求（pm 写进 charter，由 baseline 模块落实；用户的基线分支在「收尾合并」之前不会被改动）、额度约定（见 [docs/project-conventions.md](docs/project-conventions.md)）。
2. 在「多Agent · 项目管理」中创建任务（`create_task_kandev`，`workflow_id` 取自 `<home>/kandev/` 下该 workspace 的 ids 文件，选好仓库），描述用 [docs/workflow.md](docs/workflow.md)「部署与启动」中的 `[TASK v1]` 模板（字段说明和缺省值见 [docs/intake.md](docs/intake.md)）。`mgmt_root` 放在仓库和 worktree 之外；`mgmt_template` 写 `<home>/mgmt-template` 的绝对路径。
3. 经用户同意后启动任务。之后用户只需要看两处：`<mgmt_root>/project/attention.md`（需要用户决定的事）和 `<mgmt_root>/agents/guard/stage.md`（现在在等谁）。
4. 守护如果在上一个项目结束后自动停用了，提醒用户在 Kandev 设置 → Automations 重新启用「多Agent 守护」。

## D. 跑基准项目

按 [evaluation/bench/README.md](evaluation/bench/README.md)：用固定的待办应用需求启动一个 unattended 项目，到达「人工终审」后用 `evaluation/metrics.py` 采集指标，在 `evaluation/bench/results.md` 追加一行。预计 30–45 分钟，会产生真实费用，先征得用户同意。

## E. 修改 workflow 本身

在源仓库里做（用它直接部署时用链接模式）。只想调整规则、角色卡或参数的用户不需要做这一节，做 F。

1. 只改 `kandev/build_workflows.py`（结构和 prompt）、`rules/`（槽位的出厂内容）与 `mgmt-template/`（模板、角色卡）。改了 `[TASK v1]` 头的字段或缺省值时，同步 [docs/intake.md](docs/intake.md)（「接收」步骤运行时直接读它，改完即生效，不需要重新部署）。改结构或改了需要用户知道的行为时，同步 [docs/workflow.md](docs/workflow.md)。
2. `python kandev/build_workflows.py dump --out docs/prompts.md`
3. `python kandev/check_docs.py` 全部 OK；改了 `stage.py` 时同步更新 `kandev/tests/`。新增规则槽位或 `rules/params.json` 的键时，在 `kandev/deploy_questions.json` 的 `customize` 项的 `covers` 里登记（自检会检查）。
4. 部署到 Kandev 前按 `redeploy` 阶段的清单征得用户同意（`ma.py diff` → `ma.py apply --confirmed`）；部署后做 B。已有独立安装目录的，按 G 升级它。
5. 改了 workflow 的版本号（`build_workflows.py` 的 `VERSION`）时，同步 `docs/workflow.md` 标题中的版本号和 `mgmt-template/VERSION`。

## F. 定制规则、角色卡和参数

在 `<home>` 中做。能定制的东西和格式见 [rules/README.md](rules/README.md)。

1. 运行 `python kandev/ma.py questions --stage customize`，问用户要定制哪几项、每项的具体要求。
2. 按用户的要求写文件：
   - 规则槽位（`git`、`coding`、`testing`、`workspace`、`quality`）：把 `rules/<槽位>.md` 复制到 `custom/rules/<槽位>.md`，在副本的 `---` 之后写正文。不改 `rules/` 里的出厂文件。
   - 参数：新建 `custom/rules/params.json`，只写要改的键（`dev_wip`、`refresh_wakes`、`guard`）。
   - 角色卡、消息协议、项目模板（`mgmt-template/`）和「接收」的参数缺省值（`docs/intake.md`）：独立安装时直接改 `<home>` 里的文件，升级时改过的文件会保留。它们在新项目启动时生效，不需要重新部署；进行中的项目用的是启动时复制到管理目录里的那一份。
   - 引擎不在定制范围内：步骤结构、消息协议的格式、分支拓扑、`stage.py` 的判断规则。用户要改这些时说明属于 E。
3. 用 `python kandev/ma.py answer --set customize='["git","params"]'` 记录定制了哪些项。
4. 规则槽位和参数要重新部署才生效：`python kandev/ma.py diff` 把 prompt 的变化讲给用户，同意后 `python kandev/ma.py apply --confirmed <值>`。
5. `python kandev/ma.py doctor` 没有 FAIL。

## G. 升级

1. 取得新版源仓库（已有克隆时 `git pull`；源仓库已被删除时重新克隆）。
2. 链接模式：更新仓库后直接做第 4 步。
3. 独立安装：在新版源仓库中运行 `python kandev/ma.py upgrade --home <home> --dry-run` 看会改什么，再去掉 `--dry-run` 运行。
   - 用户没改过的出厂文件直接更新；用户改过而新版没变的保留；两边都改了的是冲突：它会停下并列出文件，按 `upgrade` 阶段的清单问用户后加 `--conflicts keep`（保留用户的版本，新版写成同名的 `.new`）或 `--conflicts take-new`（采用新版，用户的版本另存为 `.mine`）。选 keep 时可以帮用户把 `.new` 里的变化逐个合并进去。
   - `custom/`、ids 文件、守护状态、答案都不动。
   - 守护最近一次巡检时有进行中的项目，它会停下：升级安装目录立刻影响这些项目的守护和「接收」步骤，问过用户后加 `--with-running`。新版属于另一个系列（major.minor 不同）时建议等项目结束。
4. 升级只改文件，Kandev 里的 workflow 还是旧的：在 `<home>` 中运行 `python kandev/ma.py diff`，把变化讲给用户，同意后 `python kandev/ma.py apply --confirmed <值>`（新版属于另一个系列时先 `ma.py answer --set existing_workflows=retire`，同样要先问用户）。
5. 守护的 prompt 变了时（`diff` 的 confirm 值变化但三套 workflow 的 prompt 没变，或发行说明提到），按 A6 用新的交接文件更新 automation。
6. 做 B 的第 1、2、4 项。
