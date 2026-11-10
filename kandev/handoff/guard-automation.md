# 交接：配置守护 automation（每个 workspace 一次）

> **给谁**：Kandev 内部负责配置调试的 agent（它有 Core 包里的 `create_automation_kandev`，外部 MCP 没有）。
> **频率**：每个 workspace 只做一次。守护自己发现所有进行中的项目（从「多Agent · 项目管理」的 pm 任务读出 mgmt_root），之后启动新项目不需要任何守护配置。
> **用法**：复制本文件为同目录的 `guard-automation.local.md`（已被 git 忽略），在副本里把所有 `{大写占位}` 替换成本机的值（含义见「本机取值」表），然后把副本的「交接 prompt」整段交给配置 agent。不要把填好的值提交到本文件。
> **检查结果**：外部可以用 `list_settings_resources_kandev`（`resource_type=automation`，`workspace_id=…`）看到它创建的 automation。

## 本机取值（占位）

| 项 | 值 |
|---|---|
| 占位 | 含义 |
|---|---|
| `{WORKSPACE_ID}` | Kandev workspace id |
| `{ARCH_ROOT}` | 本架构仓库在本机的绝对路径（正斜杠） |
| `{ARCH_REPO_ID}` | 本架构仓库在 Kandev 中的仓库 id（没有登记就留空，见第 3 步） |
| `{PYTHON}` | 本机 Python 解释器的绝对路径（只用标准库） |
| `{GUARD_PROFILE_ID}` | 守护用的 agent profile id（profiles.local.json 中的 `mechanical`，便宜模型即可） |
| Kandev 外部 MCP | `http://localhost:38429/mcp`（stage.py 用它只读查询） |

参考配置（已验证可用）：schedule `*/20`、hidden run（`automation_run`）、上面的 profile、并发 1、不挂仓库（`repository_mode=none`）、Local 执行器（不建 worktree）、`reuse_thread`（复用同一个任务）。

## 交接 prompt

```text
请在 Kandev workspace {WORKSPACE_ID} 中配置「多Agent 守护」automation。这是一次性配置，一个 workspace 只要一个守护，它会自己发现所有进行中的多 agent 项目。不要修改任何仓库代码、workflow 或任务。

背景：本 workspace 用三套 workflow（多Agent · 项目管理 / 模块管理 / 开发）运行多 agent 项目。守护每 20 分钟运行一次脚本 {ARCH_ROOT}/kandev/stage.py：脚本只读查询 Kandev，判断每个任务在等谁，输出要发的告警；守护 agent 再用 message_task_kandev 把告警发给对应的上级任务。设计说明见该仓库 mgmt-template/roles/guard.md。

1. 准备
   - kandev 的 MCP 工具可能是延迟加载的：先用工具搜索（查询 "kandev automation"）加载 create_automation_kandev，以及可用的 automation 列表 / 更新 / 运行工具。只有实际调用报错才算不可用；报错时原样回报错误后停止。
   - 读 {ARCH_ROOT}/docs/prompts.md 末尾「守护 automation」一节，取得 prompt 正文。把其中的 <arch_root> 全部替换为 {ARCH_ROOT}，<python> 全部替换为 {PYTHON}。正文里没有其他需要替换的占位。
2. 查重
   - 列出本 workspace 的 automation。已有名称为「多Agent 守护」的 → 更新它，不要新建第二个。名称不同但 prompt 里运行 kandev/stage.py 的旧守护 → 在回报中列出，不要删除，由用户决定。
3. 创建（或更新）
   - 名称：多Agent 守护
   - 描述：多 agent 项目的进度守护，每 20 分钟运行 kandev/stage.py，覆盖本 workspace 所有进行中的项目
   - 触发：schedule，cron */20 * * * *
   - task mode：hidden run
   - agent profile：{GUARD_PROFILE_ID}
   - max concurrent runs：1
   - prompt：第 1 步替换好的正文
   - 仓库与执行器：守护只需要运行一条 Python 命令，不改任何文件。如果必须选仓库，选 {ARCH_ROOT}（仓库 id {ARCH_REPO_ID}）；执行器优先选直接在本地目录运行、不创建 worktree 的那种，避免每 20 分钟产生一个 worktree。
   - 任务复用（continuation policy 等）：选不会每次运行都留下一个新任务的方式（例如复用同一个任务，或不保留运行任务）。
   - 如果工具的参数名或可选值与上面不同，按工具 schema 选最接近的值，并在回报中逐项写明实际使用的值和理由。
4. 验证（只读）
   - 在当前会话运行一次：{PYTHON} {ARCH_ROOT}/kandev/stage.py --json
     期望：退出码 0；没有进行中的项目时标准输出为空（不带 --json 运行会打印「没有进行中的项目。」）。有输出时不要据此发消息或移动任务，这只是连通性检查。
     失败（例如连不上 http://localhost:38429/mcp、找不到 kandev_ids.json）→ 原样回报错误；automation 保留，但说明守护运行时会遇到同样的问题。
   - 如果有"立即运行一次"的工具：运行一次，确认 automation 的会话能执行这条命令、能访问 localhost:38429，并且没有发出任何消息（目前没有进行中的项目）。没有这个工具就跳过，并说明首次定时运行在什么时候。
5. 回报（一条消息，≤15 行）
   - automation id 和名称；新建还是更新；是否发现其他旧守护
   - 实际使用的配置：trigger / cron / task mode / profile / 并发数 / 仓库 / 执行器 / 任务复用方式
   - 第 4 步的结果
   - 做不到的项和原因
```

## 之后

- 守护是否在运行：看 `kandev/guard_state/last_run.json` 的 `at`（每次运行都会更新，正常情况下不超过 20 分钟前）。
- 新项目：照常在「多Agent · 项目管理」新建 pm 任务即可。守护下一次运行时会发现它；pm 初始化管理目录后，守护开始写 `<mgmt_root>/agents/guard/stage.md`。
- 修改守护 prompt（例如 `build_workflows.py` 中的 `GUARD_PROMPT` 变了）：重新生成 `docs/prompts.md`，再把这份交接 prompt 交给配置 agent，它会按第 2 步更新已有的 automation。
- 自动停用：所有项目正常结束后，守护会自己把 automation 设为停用（`stage.py --disable-when-done`，条件见 `mgmt-template/roles/guard.md`「自动停用」），journal 记一行 `guard_disabled`。**启动新项目前**在 Kandev 设置 → Automations 重新启用「多Agent 守护」（或外部 `update_settings_kandev`：target `resource_type=automation`、`resource_id=<id>`、`workspace_id=…`，changes `{"enabled": true}`）。
- 用量上限：任务因到达上限而停下时，守护在重置时间过后向该任务的原会话发 `continue` 恢复，不告警上级（见 guard.md「用量上限」）。
- 修改了守护 prompt 后更新已有 automation：外部 `update_settings_kandev`，changes `{"prompt": "<替换好占位的正文>"}`；不需要重建。

## 为什么不在外部完成

- 外部 MCP（`localhost:38429`）没有创建 automation 的工具，也没有 `message_task_kandev`；已有 automation 可以用 `list_settings_resources_kandev` 查看、用 `get_settings_kandev` / `update_settings_kandev` 读改（守护的自动停用就用它）。
- 守护运行时需要 `message_task_kandev` 发 ALERT，所以守护本身也必须是 Kandev 内部的 automation。
