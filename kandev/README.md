# Kandev 部署

把 [多 Agent 开发 Workflow](../docs/workflow.md) 部署到任意 Kandev workspace。想让 agent 代为部署和验收，见 [../AGENTS.md](../AGENTS.md)。

## 文件

| 文件 | 用途 |
|---|---|
| `ma.py` | 入口：部署前的提问清单、安装到独立目录、查看 prompt 差异、部署、检查（doctor）、升级 |
| `deploy_questions.json` | 部署、定制、升级前必须向用户确认的事项（`ma.py questions` 查看） |
| `prompts.py` | 唯一的配置来源：三套 workflow 的结构和 prompt（规则槽位取自 `../rules/`） |
| `build_workflows.py` | 部署逻辑：导入、就地更新、绑定 profile，以及 `dump`（生成 prompts.md）、`stats`（每个步骤的字符数和携带的共享块）命令 |
| `manifest.py`、`slots.py`、`kandev_client.py` | 安装清单与答案校验、规则槽位的读取、Kandev MCP 客户端 |
| `check_docs.py` | 自检：prompts.md 是否最新、链接、步骤名、模板路径、版本号、stage 回归测试。改完 workflow、部署前运行 |
| `stage.py` | 守护用的阶段分类：从 Kandev 状态判断每个任务"在等谁"，生成 `agents/guard/stage.md` 和告警 |
| `tests/` | 离线测试：`stage.py` 的回归测试、`ma.py` 的安装 / 定制 / 部署门禁 / 升级测试（用内存里的 Kandev 替身）、管理目录工具的测试 |
| `verify_export.py` | 导出已部署的 workflow，打印每个步骤的配置用来核对，并把去掉本机 ID 的副本写到 `export/` |
| `export/` | 示例 workflow：从实际部署导出的三套 workflow，见 [export/README.md](export/README.md) |
| `handoff/` | 外部 MCP 做不了、要交给 Kandev 内部 agent 执行的工作的交接 prompt |
| `profiles.example.json` | 角色 → agent profile ID 的格式示例 |
| `profiles.local.json` | 本机实际使用的 profile ID（`ma.py apply` 按清单里的答案写出，不提交、不手改） |
| `kandev_ids.json` | `apply` 生成：各 workflow 和步骤的 ID（不提交；链接模式的第二个 workspace 起文件名带前 8 位 id） |

## 前提

- Kandev 正在运行，外部 MCP 端点可用（默认 `http://localhost:38429/mcp`；不同时在答案里写 `kandev_url`）。
- Python 3.9+。脚本只用标准库，不需要安装依赖。
- 已在 Kandev 里为各角色准备好 agent profile，选法和约束见 [docs/workflow.md](../docs/workflow.md)「角色与 profile」；`ma.py install` 会校验。

## 部署

`python` 换成本机的 Python 解释器。

```
python kandev/ma.py questions --stage install          # 部署前要确认的事项
python kandev/ma.py install --answers answers.json     # 记录答案；独立安装时复制到安装目录 <home>
python <home>/kandev/ma.py diff                        # workspace 里的现状，和将要改变的内容
python <home>/kandev/ma.py apply                       # 自检 → 导入 / 就地更新 → 守护交接文件 → 导出
python <home>/kandev/ma.py doctor                      # 检查安装目录、已部署的 workflow、守护
```

答案文件是一个 JSON 对象，键见 `ma.py questions`。最少：

```json
{
  "setup_style": "quick",
  "workspace_id": "<workspace id>",
  "profiles": {"pm": "<profile id>", "auditor": "…", "developer": "…", "reviewer": "…", "mechanical": "…"},
  "guard_automation": "yes"
}
```

`setup_style` 为 `custom` 时还要写 `install_mode`、`home`（链接模式不用）、`python`、`kandev_url`。缺必问项、有不认识的键、profile 违反约束、路径含空格时，`install` 逐条列出并拒绝执行。

- **两种安装方式**（`install_mode`）：`standalone`（缺省）把运行所需的文件复制到安装目录 `<home>`（缺省 `~/.kandev-ma/<workspace id 前 8 位>/`），写进 Kandev 的路径都指向它，之后删除本仓库不影响运行；`link` 不复制，`<home>` 就是本仓库，适合要改 workflow 本身的人。链接模式下一个仓库可以部署到多个 workspace，后面的 workspace 用带前 8 位 id 的 ids 文件和心跳文件。
- **`apply` 遇到已有的同名 workflow**：
  - 同一系列（major.minor 相同，例如 v3.3 和 v3.3.4）：就地更新 prompt、profile、description 和步骤结构，步骤 ID 和任务不变。必须带 `--confirmed <ma.py diff 打印的值>`；有进行中的项目时还要 `--with-running`。
  - 其他系列：必须带 `--retire`。旧版改名为"<名称> (<旧版本号>)"，任务都保留，再导入新版；旧版上进行中的项目在旧 workflow 上跑完，但守护不再巡检它们。
- **定制**：规则槽位见 [../rules/README.md](../rules/README.md)，覆盖文件放在 `<home>/custom/rules/`，改完重新 `diff` + `apply`。
- **升级**：在新版仓库中运行 `python kandev/ma.py upgrade --home <home>`（先 `--dry-run` 看会改什么），再在 `<home>` 中 `diff` + `apply`。各版本要注意的事（包括守护 prompt 有没有变、要不要重新交接）见 [../CHANGELOG.md](../CHANGELOG.md)。
- **改答案**：`ma.py answer --set key=value`（可改 profiles、guard_automation、python、kandev_url、setup_style；workspace 和安装方式要改就重新安装）。
- 部署后按 [AGENTS.md](../AGENTS.md)「B. 验收部署」核对。

内部实现：`ma.py apply` 调用 `build_workflows.py apply`，它按 W3 → W2 → W1 的顺序导入（后者的 prompt 里要写入前者的步骤 ID），先不带 profile 导入，再按 ID 逐步绑定 profile，最后写出 ids 文件。

## 守护 automation

外部 MCP 不能创建 automation，所以守护（每个 workspace 一个，覆盖所有项目）要由 Kandev 内部的 agent 创建：

1. `ma.py apply`（或 `ma.py guard`）在 `handoff/` 下生成 `guard-handoff.<workspace 前 8 位>.local.md`（[handoff/guard-automation.md](handoff/guard-automation.md) 填好本机取值的副本）和 `guard-prompt.<workspace 前 8 位>.local.md`（守护 prompt 全文）。
2. 在任一 Kandev 任务里，把交接文件中「交接 prompt」整段交给 agent 执行。

也可以在 Kandev 设置 → Automations 里手动建：schedule `*/20 * * * *`、hidden run、便宜模型的 profile、并发 1，prompt 用 `guard-prompt.<workspace 前 8 位>.local.md` 代码块里的全文。

人工查看守护会看到什么：`python <home>/kandev/stage.py --ids <ids 文件> --dry-run`。不带 `--dry-run` 的运行会把这次的告警记成已发。

## 其他手动部分

- **仓库设置**：Copy files、worktree 分支模板等，按项目由 baseline 模块确定（需要用户配置时经 pm 提出）后再配置。
