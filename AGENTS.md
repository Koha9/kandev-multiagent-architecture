# AGENTS.md：给 agent 的入口

本仓库是一套在 [Kandev](https://github.com/kdlbs/kandev) 上运行的多 agent 开发 workflow：三套 Kandev workflow（项目管理 / 模块管理 / 开发）、每个项目一个管理目录、一个守护 automation。给人看的介绍在 [README.md](README.md)。

你可能被要求做下面 A–E 中的一项或几项。先读对应的小节，再动手。

## 先读这些

| 文件 | 什么时候读 |
|---|---|
| [docs/workflow.md](docs/workflow.md) | 任何任务都先读：角色、三套 workflow 的步骤、门禁、并发、已知限制 |
| [kandev/README.md](kandev/README.md) | 部署（A）、修改 workflow（E） |
| [docs/prompts.md](docs/prompts.md) | 需要知道某个步骤的 agent 具体会收到什么 prompt 时 |
| [mgmt-template/README.md](mgmt-template/README.md) | 启动项目（C）或检查项目进度时：管理目录的结构 |
| [evaluation/bench/README.md](evaluation/bench/README.md) | 跑基准（D） |

## 规则

- **改动 Kandev 之前先问用户**：导入或改名 workflow、创建任务、启动会话、创建 automation，都要先说明要做什么、影响哪个 workspace，得到同意再做。只读查询不用问。
- **会产生费用的操作单独确认**：启动 agent 会话（验收 A3、启动项目、跑基准）会消耗用户的模型额度。
- **不删除任何东西**。脚本也不删除。需要删除的（例如临时任务、旧 workflow）列出来交给用户，或在用户明确同意后再做。
- **prompt 的唯一来源是 `kandev/build_workflows.py`**。不要手改 `docs/prompts.md` 或 `kandev/export/*.json`，它们都是生成的。
- **本机文件不提交**：`kandev/profiles.local.json`、`kandev/kandev_ids.json`、`kandev/guard_state/`、`*.local.md`。
- 运行脚本用本机的 Python 3 解释器（只用标准库），下文写作 `python`。
- Kandev 外部 MCP 默认在 `http://localhost:38429/mcp`。你自己有 kandev MCP 工具时可以直接调用；没有时，脚本里的 `Kandev` 类可以调用任何工具：
  ```
  python -c "import sys,json; sys.path.insert(0,'kandev'); from build_workflows import Kandev; print(json.dumps(Kandev().call('list_workspaces_kandev', {}), ensure_ascii=False, indent=1))"
  ```

## A. 部署到 Kandev workspace

前提：本仓库已克隆到运行 Kandev 的那台机器上（守护每 20 分钟要在本机运行 `kandev/stage.py`，它读本地的 `kandev_ids.json`）。

1. **确认 Kandev**：调用 `list_workspaces_kandev`。连不上就停下，请用户启动 Kandev 或给出 MCP 地址（脚本都支持 `--url`）。有多个 workspace 时问用户用哪个。
2. **选 profile**：调用 `list_agent_profiles_kandev`，为 5 个必填角色各选一个 profile，3 个可选角色按需要选（不填时用括号中的缺省），规则见 [docs/workflow.md](docs/workflow.md)「角色与 profile」：
   - `pm`、`auditor`：强模型，**两者必须是不同的 profile**
   - `plan_auditor`（缺省 = auditor）：立项评审，上下文小、影响最大，适合最强模型；**必须与 pm 不同**
   - `module`（缺省 = pm）：模块管理，强模型；`module_auditor`（缺省 = auditor）：模块验收，强模型，**必须与 module 不同**
   - `developer`：主力编码模型；`reviewer`：**与 developer 不同的 profile**，最好不同厂商
   - `mechanical`：合并门禁和收尾合并，编码模型
   - mode 应能无人值守执行（不会每步都等权限确认）

   把你的选择列成表交给用户确认，然后写进 `kandev/profiles.local.json`（格式见 `kandev/profiles.example.json`）。缺合适的 profile 时，告诉用户需要新建什么样的 profile，不要自己创建。
3. **检查同名 workflow**：`list_workflows_kandev` 中已有「多Agent · 项目管理 / 模块管理 / 开发」时：
   - description 里带同一版本号（例如 `[v3.2]`）：直接 `apply` 只会同步 prompt 和 profile。
   - 其他版本：要加 `--retire-existing`（旧版改名为"<名称> (<旧版本号>)"，例如"(v3.1)"，任务保留）。先征得用户同意。
   - 同一台机器部署到多个 workspace 时，每个 workspace 用自己的 ids 文件：`apply --ids-out kandev_ids.<workspace 前 8 位>.json`，该 workspace 的守护用 `stage.py --ids` 指向它（这些文件不提交）。
4. **部署**（在 `kandev/` 下）：
   ```
   python check_docs.py
   python build_workflows.py apply --workspace <workspace_id> --profiles profiles.local.json
   python verify_export.py
   ```
   `check_docs.py` 必须全部 OK 才继续。`apply` 会写出 `kandev_ids.json`。
5. **守护 automation**（每个 workspace 一个）：复制 `kandev/handoff/guard-automation.md` 为 `kandev/handoff/guard-automation.local.md`，把所有 `{大写占位}` 填好（`{GUARD_PROFILE_ID}` 用 `mechanical` 的 profile）。
   - 你在 Kandev 内部运行、有 `create_automation_kandev`：经用户同意后，按副本中的「交接 prompt」执行。
   - 没有这个工具（外部 MCP 没有）：把副本路径交给用户，请用户在任一 Kandev 任务里把「交接 prompt」交给 agent，或在 Kandev 设置 → Automations 手动建。
6. 接着做 B。

## B. 验收部署

逐项核对，最后用一张表汇报每项 pass / fail / unverified（附原因）。

1. **自检**：`python kandev/check_docs.py` 全部 OK；`python kandev/tests/test_stage.py` 输出 `OK test_stage`。
2. **结构**：`python kandev/verify_export.py` 的输出中：
   - W1 有 11 个步骤（0 待立项 … 9 完成、10 刷新，没有「环境基线」），「立项规划」start=True；立项评审、项目验收、收尾合并的会话策略是 `new/complete`；`5 调度` 的 on_enter 是 reset_agent_context + auto_start_agent；`3 立项确认` 的 on_turn_start 是 `move_to_step {'step_position': 1}`，`7 人工终审` 的是 `move_to_step {'step_position': 4}`。
   - W2 有 5 个步骤，「等待开发」的事件含 reset_agent_context + auto_start_agent 和 `on_children_completed: move_to_next`；「验收调查」的会话策略是 `new/complete`。
   - W3：`0 待开发`（无 prompt、无事件、wip=0）、`1 开发`（start=True，wip=4）、`2 审核` 的 on_turn_complete 是 `move_to_step {'step_position': 4}`、`4 合并` 的 on_turn_complete 是 `move_to_step {'step_position': 5}`（没有 on_pr_merged）。
   - 所有 agent 步骤的 profile 是第 A2 步确认的那几个模型，不是 `-`（立项评审 = plan_auditor，W2 验收调查 = module_auditor，W2 其余 = module）。
   - `kandev/export/W2-module.json` 中出现 `<W3_DEV_STEP_ID>`、`<W3_HOLD_STEP_ID>`（说明部署的 prompt 里写入了真实 ID，导出时被替换回占位符）。
3. **「待开发」行为**（会启动一次真实会话，先征得用户同意）：
   | # | 操作 | 期望 |
   |---|---|---|
   | a | 在 W3 建临时任务 A：`workflow_step_id`=「待开发」，`start_agent=false`，不设 blocked_by，prompt="只回复 OK，然后结束本轮，不做任何其他事" | A 停在「待开发」，没有会话 |
   | b | 等 1 分钟后再看 A | A 仍在「待开发」，没有被自动启动 |
   | c | 把 A 移到「开发」 | A 启动会话（on_enter auto_start，对应 workflow.md「部署后需要实测的平台行为」a）；回复 OK 后因为没有完成信号停在「开发」 |
   | d | 给 A 发消息"把自己移到「等待决策」后结束本轮"；A 移过去后再把它移回「开发」 | 移回后沿用原来的开发会话（同上 b），不新建会话 |
   | e | 请用户删除 A（或经同意后删除） | 不留下 worktree 或分支 |

   任一项不符合期望：记为 fail，不要启动项目，回报给用户。
4. **守护**：`list_settings_resources_kandev`（`resource_type=automation`）中有「多Agent 守护」且已启用；`python kandev/stage.py --json` 退出码 0（没有进行中的项目时无输出）；守护运行过一次后，`kandev/guard_state/last_run.json` 的 `at` 在 20 分钟以内。
5. **端到端**（可选，费用较高）：做 D。

## C. 启动一个项目

1. 向用户确认：目标仓库（本机绝对路径和基线分支）、需求（按重要度排序，一条一行）、`mode`（attended：关键节点等用户；unattended：全程不提问）、是否 `plan_only`（只做到规划，先看计划再投入开发额度）、`integration_test`（auto：其他模块完成后自动做结合测试，缺省；off：不做）、技术栈与环境要求（pm 写进 charter，由 baseline 模块落实；用户的基线分支在「收尾合并」之前不会被改动）、额度约定（见 [docs/project-conventions.md](docs/project-conventions.md)）。
2. 在「多Agent · 项目管理」中创建任务（`create_task_kandev`，`workflow_id` 取自 `kandev/kandev_ids.json`，选好仓库），描述用 [docs/workflow.md](docs/workflow.md)「部署与启动」中的 `[TASK v1]` 模板。`mgmt_root` 放在仓库和 worktree 之外；`mgmt_template` 写本仓库 `mgmt-template/` 的绝对路径。
3. 经用户同意后启动任务。之后用户只需要看两处：`<mgmt_root>/project/attention.md`（需要用户决定的事）和 `<mgmt_root>/agents/guard/stage.md`（现在在等谁）。
4. 守护如果在上一个项目结束后自动停用了，提醒用户在 Kandev 设置 → Automations 重新启用「多Agent 守护」。

## D. 跑基准项目

按 [evaluation/bench/README.md](evaluation/bench/README.md)：用固定的待办应用需求启动一个 unattended 项目，到达「人工终审」后用 `evaluation/metrics.py` 采集指标，在 `evaluation/bench/results.md` 追加一行。预计 30–45 分钟，会产生真实费用，先征得用户同意。

## E. 修改 workflow

1. 只改 `kandev/build_workflows.py`（结构和 prompt）与 `mgmt-template/`（模板、角色卡）。改结构或改了需要用户知道的行为时，同步 [docs/workflow.md](docs/workflow.md)。
2. `python kandev/build_workflows.py dump --out docs/prompts.md`
3. `python kandev/check_docs.py` 全部 OK；改了 `stage.py` 时同步更新 `kandev/tests/`。
4. 部署到 Kandev 前按 A3、A4 征得用户同意；部署后做 B，并重新导出 `kandev/export/`。
5. 改了 workflow 的版本号（`build_workflows.py` 的 `VERSION`）时，同步 `docs/workflow.md` 标题中的版本号。
