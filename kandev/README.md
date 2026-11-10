# Kandev 部署

把 [多 Agent 开发 Workflow v3.1](../docs/workflow.md) 部署到任意 Kandev workspace。从 v3 升级见 [UPGRADE-v3.1.md](UPGRADE-v3.1.md)。

## 文件

| 文件 | 用途 |
|---|---|
| `build_workflows.py` | 唯一的配置来源：三套 workflow 的结构、prompt，以及 `apply` / `dump` 命令 |
| `check_docs.py` | 自检：prompts.md 是否最新、链接、步骤名、模板路径、版本号、stage 回归测试。改完 workflow、部署前运行 |
| `stage.py` | 守护用的阶段分类：从 Kandev 状态判断每个任务"在等谁"，生成 `agents/guard/stage.md` 和告警 |
| `tests/` | `stage.py` 的离线回归测试（`python kandev/tests/test_stage.py`） |
| `handoff/` | 外部 MCP 做不了、要交给 Kandev 内部 agent 执行的工作的交接 prompt |
| `profiles.example.json` | 角色 → agent profile ID 的格式示例 |
| `profiles.local.json` | 本机实际使用的 profile ID（每台机器各自维护，不提交） |
| `kandev_ids.json` | `apply` 生成：各 workflow 和步骤的 ID（每台机器各自不同，不提交） |
| `verify_export.py` | 导出已部署的 workflow，打印每个步骤的配置，用来核对 |
| `W1-project.json` / `W2-module.json` / `W3-dev.json` | 最近一次的导出快照（只供参考，不要直接导入，原因见下） |

## 前提

- Kandev 外部 MCP 端点可用（默认 `http://localhost:38429/mcp`，可用 `--url` 改）。
- 已为 5 个角色各准备一个 agent profile（见 `profiles.example.json`）：
  - auditor 必须与 pm 不同，reviewer 必须与 developer 不同。
  - mode 建议设为能无人值守执行的权限模式。

## 部署

```
python check_docs.py
python build_workflows.py apply --workspace <workspace_id> --profiles profiles.local.json
python verify_export.py
```

- **已有旧版同名 workflow**：加 `--retire-existing`，旧版会被改名为"<名称> (旧)"，任务都保留，然后导入新版。
- **已经是同一版本**：再次运行 `apply` 只同步 prompt 和 profile，不改结构。要改结构，就先删除或改名旧 workflow，再导入。
- **为什么不直接导入导出的 JSON**：导出文件只按 model / mode 记录 profile。同一个模型如果有多个 profile，导入时可能匹配错。脚本先不带 profile 导入，再按 ID 逐步绑定。
- **改 prompt 之后**：`python build_workflows.py dump --out ../docs/prompts.md`，再跑一次 `check_docs.py`。

## 外部 MCP 做不了的部分

外部 MCP 没有 `message_task_kandev`，也不能创建 automation。这些工作写成交接 prompt，交给 Kandev 内部的 agent（在任一 Kandev 任务里粘贴给它）执行：

| 工作 | 交接 prompt |
|---|---|
| 创建 / 更新守护 automation（每个 workspace 一次，覆盖所有项目） | [handoff/guard-automation.md](handoff/guard-automation.md) |

也可以在 Kandev 设置 → Automations 里手动建，配置和 prompt 见 `docs/prompts.md` 的「守护 automation」一节。

## 其他手动部分

- **仓库设置**：Copy files、worktree 分支模板等，按项目在「环境基线」步骤确定后再配置。
