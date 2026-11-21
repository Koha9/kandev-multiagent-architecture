# Kandev 部署

**中文** | [English](README.en.md)

把 [多 Agent 开发 Workflow](../docs/workflow.md) 部署到任意 Kandev workspace。想让 agent 代为部署和验收，见 [../AGENTS.md](../AGENTS.md)。

## 文件

| 文件 | 用途 |
|---|---|
| `ma.py` | 入口：部署前的提问清单、安装到独立目录、查看 prompt 差异、部署、检查（doctor）、升级 |
| `deploy_questions.json` | 部署、定制、升级前必须向用户确认的事项（`ma.py questions` 查看） |
| `build_workflows.py` | 唯一的配置来源：三套 workflow 的结构、prompt（规则槽位取自 `../rules/`），以及 `apply` / `dump` 命令 |
| `manifest.py`、`slots.py`、`kandev_client.py` | 安装清单与答案校验、规则槽位的读取、Kandev MCP 客户端 |
| `check_docs.py` | 自检：prompts.md 是否最新、链接、步骤名、模板路径、版本号、stage 回归测试。改完 workflow、部署前运行 |
| `stage.py` | 守护用的阶段分类：从 Kandev 状态判断每个任务"在等谁"，生成 `agents/guard/stage.md` 和告警 |
| `tests/` | 离线测试：`stage.py` 的回归测试、`ma.py` 的安装 / 定制 / 升级测试、管理目录工具的测试 |
| `verify_export.py` | 导出已部署的 workflow，打印每个步骤的配置用来核对，并把去掉本机 ID 的副本写到 `export/` |
| `export/` | 示例 workflow：从实际部署导出的三套 workflow，见 [export/README.md](export/README.md) |
| `handoff/` | 外部 MCP 做不了、要交给 Kandev 内部 agent 执行的工作的交接 prompt |
| `profiles.example.json` | 角色 → agent profile ID 的格式示例 |
| `profiles.local.json` | 本机实际使用的 profile ID（`ma.py install` 按用户确认的答案写出，不提交） |
| `kandev_ids.json` | `apply` 生成：各 workflow 和步骤的 ID（每台机器各自不同，不提交） |

## 前提

- Kandev 正在运行，外部 MCP 端点可用（默认 `http://localhost:38429/mcp`，可用 `--url` 改）。
- Python 3。脚本只用标准库，不需要安装依赖。
- 已为 5 个必填角色（pm、auditor、developer、reviewer、mechanical）各准备一个 agent profile；可选角色 module、module_auditor、plan_auditor、intake 不填时分别等于 pm、auditor、auditor、mechanical（见 `profiles.example.json` 和 [docs/workflow.md](../docs/workflow.md)「角色与 profile」）：
  - auditor、plan_auditor 必须与 pm 不同，module_auditor 必须与 module 不同，reviewer 必须与 developer 不同。
  - 立项评审（plan_auditor）上下文小、影响最大，适合最强模型；mechanical 负责合并门禁，用编码模型；intake 只整理启动参数（W1「接收」），轻量模型即可。
  - mode 建议设为能无人值守执行的权限模式。

## 部署

`python` 换成本机的 Python 解释器。

```
python kandev/ma.py questions --stage install          # 部署前要确认的事项
python kandev/ma.py install --answers answers.json     # 记录答案；独立安装时复制到安装目录 <home>
python <home>/kandev/ma.py diff                        # 已部署的 prompt 与将要部署的差异
python <home>/kandev/ma.py apply                       # 自检 → 导入 / 就地更新 → 守护交接文件 → 导出
python <home>/kandev/ma.py doctor                      # 检查安装目录、已部署的 workflow、守护
```

- **答案文件**：JSON，键见 `ma.py questions`。最少要有 `setup_style`（quick / custom）、`workspace_id`、`profiles`（角色 → profile ID，格式同 `profiles.example.json`）、`existing_workflows`（none / update / retire）、`guard_automation`（create / manual / skip）、`acceptance_run`（yes / no）。缺必问项时 `install` 和 `apply` 都拒绝执行。
- **两种安装方式**（`install_mode`）：`standalone`（缺省）把运行所需的文件复制到安装目录 `<home>`（缺省 `~/.kandev-ma/<workspace id 前 8 位>/`），写进 Kandev 的路径都指向它，之后删除本仓库不影响运行；`link` 不复制，`<home>` 就是本仓库，适合要改 workflow 本身的人。
- **就地更新**已部署的 workflow 时，`apply` 要求带上 `--confirmed <ma.py diff 打印的值>`；有进行中的项目时还要 `--with-running`。
- **定制**：规则槽位见 [../rules/README.md](../rules/README.md)，覆盖文件放在 `<home>/custom/rules/`，改完重新 `diff` + `apply`。
- **升级**：在新版仓库中运行 `python kandev/ma.py upgrade --home <home>`（`--dry-run` 先看会改什么），再在 `<home>` 中 `diff` + `apply`。
- `ma.py apply` 内部调用 `build_workflows.py apply`：按 W3 → W2 → W1 的顺序导入（后者的 prompt 里要写入前者的步骤 ID），先不带 profile 导入，再按 ID 逐步绑定 profile，最后写出 `kandev_ids.json`。
- **已有同名 workflow**：
  - 同一系列（major.minor 相同，例如 v3.3 和 v3.3.1）：再次运行 `apply` 就地更新 prompt、profile、description 和步骤结构（顺序、事件、开关）。步骤 ID 和步骤里的任务不变，进行中的项目继续在这套 workflow 上跑。
  - 其他系列：加 `--retire-existing`，旧版会被改名为"<名称> (<旧版本号>)"（例如"(v3.1)"），任务都保留，然后导入新版。旧版上进行中的项目会在旧 workflow 上跑完。
- **改 prompt 之后**：`python build_workflows.py dump --out ../docs/prompts.md`，再跑一次 `check_docs.py`。
- 部署后按 [AGENTS.md](../AGENTS.md)「验收部署」核对。

## 守护 automation

外部 MCP 不能创建 automation，所以守护（每个 workspace 一个，覆盖所有项目）要由 Kandev 内部的 agent 创建：

1. `ma.py apply`（或 `ma.py guard`）在 `handoff/` 下生成 `guard-handoff.<workspace 前 8 位>.local.md`：[handoff/guard-automation.md](handoff/guard-automation.md) 填好本机取值的副本（已被 git 忽略）。
2. 在任一 Kandev 任务里，把副本中「交接 prompt」整段交给 agent 执行。

也可以在 Kandev 设置 → Automations 里手动建：schedule `*/20 * * * *`、hidden run、便宜模型的 profile、并发 1，prompt 见 [docs/prompts.md](../docs/prompts.md) 末尾「守护 automation」一节（替换其中的 `<arch_root>` 和 `<python>`）。

## 其他手动部分

- **仓库设置**：Copy files、worktree 分支模板等，按项目由 baseline 模块确定（需要用户配置时经 pm 提出）后再配置。
