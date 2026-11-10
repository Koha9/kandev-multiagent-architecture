# 升级到 v3.1

> 本文件用占位符：`<python>` 为本机 Python 解释器，`<workspace_id>` 为 Kandev workspace id。本机的执行记录可以写在同目录的 `UPGRADE-v3.1.local.md`（已被 git 忽略）。
> 第 3 步的 a、b、c 三项已在一次实际升级中验证符合期望。

> v3.1 是小版本：三套 workflow 的名称、角色、门禁不变。结构上只有 W3 多了一个「待开发」步骤（位置 0，其余步骤后移一位）。其余改动都在 prompt、模板和脚本里。
> 改动内容见 [docs/workflow.md](../docs/workflow.md)「变更记录」v3.1 各行；依据见 [reports/借鉴-dsh-superagent.md](../reports/借鉴-dsh-superagent.md)。

## 0. 升级前

- 先用外部 MCP 查当前部署（`kandev_ids.json` 中的三个 v3 workflow）里有没有任务。都没有任务时可以直接替换，不需要迁移进行中的项目。
- 如果升级时已经有项目在 v3 上运行：它们留在改名后的「(旧)」workflow 上跑完。旧 W2 的 prompt 里写的是旧 W3 的 ID，所以旧项目会继续用旧的开发 workflow，互不干扰。
- 已经复制出去的管理目录（各项目的 mgmt_root）不会自动更新。新项目在 `[TASK v1]` 的 `mgmt_template` 指向本仓库的 `mgmt-template/`，就会用上 v3.1 的模板。

## 1. 自检（外部，本机）

```
<python> kandev/check_docs.py
```

要求 6 项全部 OK。

## 2. 替换 workflow（外部 MCP，脚本完成）

```
cd kandev
<python> build_workflows.py apply --workspace <workspace_id> --profiles profiles.local.json --retire-existing
<python> verify_export.py
```

- `--retire-existing` 会把三个 v3 workflow 改名为「… (旧)」，再导入 v3.1，并按 ID 绑定 profile、同步 prompt。`kandev_ids.json` 会被重写。
- 核对 `verify_export.py` 的输出：
  - W3：`0 待开发`（无 prompt、无事件、wip=0）、`1 开发`（start=True，wip=4）、`2 审核` 的 on_turn_complete 是 `move_to_step {'step_position': 4}`、`4 合并` 的 on_pr_merged 是 `move_to_step {'step_position': 5}`。
  - W2「模块规划」的 prompt 中出现新 W3 的「开发」和「待开发」两个步骤 ID（不是占位符）。
- 确认无误后，可以在 Kandev 中删除三个「(旧)」workflow（它们没有任务）。这一步要手动做，脚本不删除任何东西。

## 3. 验证「待开发」依赖的 Kandev 行为（外部 MCP，一次性）

v3.1 的「待开发」依赖下面三点。文档里有描述，但没有实测过。用一个临时任务验证一次，验证完删除：

| # | 操作 | 期望 |
|---|---|---|
| a | 创建临时任务 A：`workflow_id`=新 W3，`workflow_step_id`=「待开发」，`start_agent=false`，prompt="只回复 OK，然后结束本轮，不做任何其他事" | 任务停在「待开发」，没有会话 |
| b | 再建任务 B：同样建到「待开发」，`start_agent=false`，`start_when_unblocked=false`，`blocked_by=[A]`；然后把 A 移到「完成」 | B 仍在「待开发」，没有会话（没有被自动启动） |
| c | 把 B 移到「开发」 | B 启动会话（on_enter auto_start），WIP 计数 +1；它回复 OK 后会因为没有 step_complete 停在「开发」 |
| d | 删除 A、B | — |

- c 会启动一次 developer profile 的会话，消耗很小，但仍是一次真实调用，所以要用户同意后再做。
- 任一项不符合期望：不要开始新项目，回到本仓库调整「待开发」的做法（备选：模块等前置完成后再创建依赖它的任务）。

## 4. 守护 automation（Kandev 内部配置 agent，每个 workspace 一次）

外部 MCP 不能创建 automation。把 [handoff/guard-automation.md](handoff/guard-automation.md) 的交接 prompt 交给 Kandev 内部负责配置的 agent，建一个覆盖整个 workspace 的守护。之后启动新项目不需要任何守护配置：`stage.py` 自己从「多Agent · 项目管理」中找出进行中的项目。

- 守护运行 `kandev/stage.py`，所以 automation 会话要能执行 shell 命令，并能访问 `http://localhost:38429/mcp`。交接 prompt 第 4 步会检查这一点。
- 旧的守护 automation 如果还在：同一个交接 prompt 会更新它（prompt 中有查重步骤），不会留两个。

## 5. 收尾

- `docs/prompts.md` 已按 v3.1 重新生成；如果第 2 步之后又改了 prompt，重新运行 `build_workflows.py dump --out ../docs/prompts.md` 和 `check_docs.py`。
- `verify_export.py` 会刷新 `W1-project.json` / `W2-module.json` / `W3-dev.json` 快照，提交时一并提交。
- 下一次试点建议用 `plan_only: true` 先跑一次规划，检查 charter 的需求覆盖表，再拖到「环境基线」继续。

## 可以由谁来做

| 步骤 | 执行者 | 需要的权限 |
|---|---|---|
| 1、2、5 | 本机 Claude Code（外部 MCP + 脚本） | 用户确认后执行；会改动 Kandev 中的 workflow |
| 3 | 本机 Claude Code（外部 MCP） | 用户确认；会启动一次真实会话 |
| 4 | Kandev 内部配置 agent（交接 prompt） | 用户交给配置 agent；每个 workspace 一次 |
| 删除「(旧)」workflow | 用户（Kandev UI）或经用户确认后用外部 MCP | 删除不可恢复 |
