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
| `stage.py` | 守护用的阶段分类：从 Kandev 状态判断每个任务"在等谁"，生成 `agents/guard/stage.md`，并输出守护要原样执行的动作（`action`：工具和完整参数） |
| `tests/` | 离线测试：`stage.py` 的回归测试、`ma.py` 的安装 / 定制 / 部署门禁 / 升级测试（用内存里的 Kandev 替身）、管理目录工具的测试 |
| `verify_export.py` | 导出已部署的 workflow，打印每个步骤的配置用来核对，并把去掉本机 ID 的副本写到 `export/` |
| `export/` | 示例 workflow：从实际部署导出的三套 workflow，见 [export/README.md](export/README.md) |
| `handoff/` | 外部 MCP 做不了、要交给 Kandev 内部 agent 执行的工作的交接 prompt |
| `profiles.example.json` | 角色 → agent profile ID 的格式示例 |
| `profiles.local.json` | 本机实际使用的 profile ID（`ma.py apply` 按清单里的答案写出，不提交、不手改） |
| `kandev_ids.json` | `apply` 生成：各 workflow 和步骤的 ID（不提交；链接模式的第二个 workspace 起文件名带前 8 位 id） |

## 前提

- Kandev 正在运行，外部 MCP 端点可用（默认 `http://localhost:38429/mcp`；不同时在答案里写 `kandev_url`）。本仓库和安装目录要在运行 Kandev 的那台机器上：`kandev_url` 不是本机地址（localhost / 127.0.0.1 / ::1）时 `install` 会停下，确认这台就是 Kandev 主机后加 `--remote-kandev`。
- Python 3.9+。脚本只用标准库，不需要安装依赖。
- 已在 Kandev 里为各角色准备好 agent profile，选法和约束见 [docs/workflow.md](../docs/workflow.md)「角色与 profile」；`ma.py install` 会校验。

## 部署

`python` 换成本机的 Python 解释器。

```
python kandev/ma.py questions --stage install                        # 部署前要确认的事项（整棵提问树）
python kandev/ma.py questions --stage install --answers answers.json # 只列出这一批该问、还没回答的项
python kandev/ma.py install --answers answers.json     # 记录答案；独立安装时复制到安装目录 <home>
python <home>/kandev/ma.py diff                        # workspace 里的现状，和将要改变的内容
python <home>/kandev/ma.py apply                       # 自检 → 导入 / 就地更新 → 建任务参数文件 → 守护交接文件 → 导出
python <home>/kandev/ma.py doctor                      # 检查安装目录、已部署的 workflow、守护
```

### 提问树

install 阶段的提问是一棵树（`deploy_questions.json`），按 `group` 分批，一批最多 4 题：

```
批          提问                                                                 什么时候问
basics      setup_style  quick | guided | custom                                 必须问
            workspace_id、guard_automation  yes | skip                           必须问
            kandev_url                                                           不问，agent 检测后填
models      review_access  ask | local | remote_only                             guided 起
            model_strategy  auto | scoped | per_role                             guided 起
profiles    profiles（最后一张表给用户确认；可选角色含 guard）                   必须问
delivery    project_defaults.remote  auto | none | push | pr                     guided 起
              （review_access=remote_only 时推荐 pr，不能是 none）
            project_defaults.ci  auto | none | local | remote                    guided 起
              （remote 需要 remote 不是 none；local 不需要推送）
            project_defaults.autonomy  ask | 1 | 2 | 3 | 4                       guided 起
policy      project_defaults.plan_only  ask | true | false                       guided 起，仅 autonomy 为 ask / 3 / 4
            project_defaults.run_policy  ask | active | conservative             guided 起
            project_defaults.integration_test  auto | off                        guided 起
            project_defaults.paid_calls  ask | deny | allow                      guided 起
install     install_mode  standalone | link；standalone 时 home；python          custom
```

- `ask=always` 的项每种方式都问；`guided` 的项选了 guided 或 custom 才问；`custom` 的项只有选了 custom 才问；`detect` 的项（`kandev_url`）从不问，agent 确认连通时用的地址不是默认值就写进答案。没问到的项用推荐值（quick 下 agent 按推荐值或检测结果决定）。`when` 不匹配的项不适用，答案里写了也忽略。
- 逐批问：把已有答案写进答案文件，运行 `ma.py questions --stage install --answers <文件>`。它只列出这一批（一个 group）要问的项，推荐值按已有答案算；回答后写回文件再运行，直到打印「没有待问的问题，可以运行 install」和一张全部取值的总表。总表每项标来源：用户 / agent 检测 / 推荐值，`home`、`python` 显示解析后的实际路径，后面列出需要用户留意的组合（例如 autonomy=4 且 remote=push）。把这张总表给用户确认（quick 安装时必须做）。
- agent 没问用户、按检测结果自己填的键列进答案文件的 `_agent`（例如 `"_agent": ["kandev_url"]`），总表标成「agent 检测」；必须问的项不能列进去。
- 模型选法（`model_strategy`）只记录 agent 是怎么选 profile 的，部署只用 `profiles`。scoped 的范围（哪些厂商 / CLI）在对话里说，不记录。
- 答案之间的约束：`ci=remote` 或 `review_access=remote_only` 时 `remote` 不能是 `none`，否则 `install` 和 `answer` 拒绝。

### 答案文件

一个 JSON 对象，键见 `ma.py questions`。`project_defaults.*` 可以写成嵌套对象，也可以写成带点的键。quick 最少：

```json
{
  "setup_style": "quick",
  "workspace_id": "<workspace id>",
  "profiles": {"pm": "<profile id>", "auditor": "…", "developer": "…", "reviewer": "…", "mechanical": "…"},
  "guard_automation": "yes"
}
```

guided 再加：

```json
{
  "review_access": "remote_only",
  "model_strategy": "auto",
  "project_defaults": {"remote": "pr", "ci": "auto", "autonomy": "ask", "plan_only": "ask", "run_policy": "ask",
                       "integration_test": "auto", "paid_calls": "ask"},
  "kandev_url": "http://localhost:38430/mcp",
  "_agent": ["kandev_url"]
}
```

`setup_style` 为 `custom` 时还要写 `install_mode`、`home`（链接模式不用）、`python`。缺必问项、有不认识的键、取值不在选项里、profile 违反约束、答案之间冲突、路径含空格时，`install` 逐条列出并拒绝执行。有选项的项可以写 JSON 的数字和布尔值（`"autonomy": 3`），记成字符串。以 `_` 开头的顶层键不是答案（`_agent` 之外的被忽略）。

清单记录补全后的答案，另外记下哪些键是答案文件里写明的（`explicit`）：没写明的项是推荐值，之后用 `answer` 改了它依赖的项时会跟着重新取值（例如把 `review_access` 改成 `remote_only`，没回答过的 `remote` 变成 `pr`）；写明过的不跟着变。

旧版记录的答案照样有效：`apply`、`doctor`、`answer` 对已记录的答案只要求必问项，缺的按推荐值处理；已删除的 `vendors`、`reviewer_cross_vendor` 被忽略，`model_strategy: vendor` 读成 `scoped`，`integration_test: ask` 读成 `auto`。

### 项目缺省值

`install` 把 `review_access` 和 `project_defaults.*` 写成 `<home>/custom/project-defaults.json`，W1「接收」把它当作每个新项目的缺省值（`ask` 表示每个项目再问）。这个文件的键和取值是与「接收」的约定（[docs/intake.md](../docs/intake.md)「部署缺省值」），`_schema` 是约定的版本：

```json
{
  "_schema": "2",
  "_source": "ma.py install 根据部署提问的答案生成；改用 ma.py answer --set …",
  "review_access": "ask|local|remote_only",
  "remote": "auto|none|push|pr",
  "ci": "auto|none|local|remote",
  "autonomy": "ask|1|2|3|4",
  "plan_only": "ask|true|false",
  "run_policy": "ask|active|conservative",
  "integration_test": "auto|off",
  "paid_calls": "ask|deny|allow"
}
```

- 值都是字符串。`plan_only` 在 `autonomy` 固定为 1 或 2 时不适用，写 `ask`。`ci` 不随 `remote` 改写（`ci=local` 不需要推送）。
- 不手改：用 `ma.py answer --set project_defaults.remote=pr`（`review_access` 用 `--set review_access=remote_only`）改，它会重写这个文件（旧内容另存 `.bak`），之后启动的项目生效，不需要重新部署。
- `custom/` 属于用户，不随安装复制，升级不动。链接模式下多个 workspace 共用这一个文件，内容是最后一次 `install` / `answer` 写入的那个 workspace 的缺省值（`doctor` 会提示）。
- `doctor` 打印当前取值；没有这个文件或是旧格式（没有 `_schema`）时只给 WARN，「接收」把缺的键按 `ask`（`remote`、`ci`、`integration_test` 按 `auto`）处理。缺省就要推送时（`remote` 是 push / pr，或 `review_access=remote_only`）`doctor` 还预检本机的 git、gh 和 gh 的登录状态（`--offline` 时不查登录），有问题给 WARN；它查的是运行 `doctor` 的机器和用户，仓库级的推送权限要到项目启动时才知道。

### 安装方式与维护

- **两种安装方式**（`install_mode`）：`standalone`（缺省）把运行所需的文件复制到安装目录 `<home>`（缺省 `~/.kandev-ma/<workspace id 前 8 位>/`），写进 Kandev 的路径都指向它，之后删除本仓库不影响运行；`link` 不复制，`<home>` 就是本仓库，适合要改 workflow 本身的人。链接模式下一个仓库可以部署到多个 workspace，后面的 workspace 用带前 8 位 id 的 ids 文件和心跳文件。
- **`apply` 遇到已有的同名 workflow**：
  - 同一系列（major.minor 相同，例如 v3.3 和 v3.3.4）：就地更新 prompt、profile、description 和步骤结构，步骤 ID 和任务不变。必须带 `--confirmed <ma.py diff 打印的值>`；有进行中的项目时还要 `--with-running`。
  - 其他系列：必须带 `--retire`。旧版改名为"<名称> (<旧版本号>)"，任务都保留，再导入新版；旧版上进行中的项目在旧 workflow 上跑完，但守护不再巡检它们。
- **定制**：规则槽位见 [../rules/README.md](../rules/README.md)，覆盖文件放在 `<home>/custom/rules/`，改完重新 `diff` + `apply`。
- **升级**：在新版仓库中运行 `python kandev/ma.py upgrade --home <home>`（先 `--dry-run` 看会改什么），再在 `<home>` 中 `diff` + `apply`。各版本要注意的事（包括守护 prompt 有没有变、要不要重新交接）见 [../CHANGELOG.md](../CHANGELOG.md)。
- **改答案**：`ma.py answer --set key=value`（可改 profiles、guard_automation、python、kandev_url、setup_style、model_strategy、review_access 和 `project_defaults.*`；workspace 和安装方式要改就重新安装）。改了 profiles（含 `guard`）或 python 后重新 `ma.py guard`，按新的交接文件更新守护 automation。
- 部署后按 [AGENTS.md](../AGENTS.md)「B. 验收部署」核对。
- **`doctor`** 不带 `--offline` 时连 Kandev 核对：已部署的 workflow 与本目录一致、守护 automation 和心跳；三套 workflow 里还有标题以 `【部署验收临时】`（`ma.py` 的 `ACCEPT_TMP_PREFIX`）开头的任务时给 WARN，列出标题、id 和所在步骤：这是验收 B3 建的临时任务没删，请用户删除（脚本不删）。

内部实现：`ma.py apply` 调用 `build_workflows.py apply`，它按 W3 → W2 → W1 的顺序导入（后者的 prompt 里要写入前者的步骤 ID），先不带 profile 导入，再按 ID 逐步绑定 profile，最后写出 ids 文件。

## 守护 automation

外部 MCP 不能创建 automation，所以守护（每个 workspace 一个，覆盖所有项目）要由 Kandev 内部的 agent 创建：

1. `ma.py apply`（或 `ma.py guard`）在 `handoff/` 下生成 `guard-handoff.<workspace 前 8 位>.local.md`（[handoff/guard-automation.md](handoff/guard-automation.md) 填好本机取值的副本）和 `guard-prompt.<workspace 前 8 位>.local.md`（守护 prompt 全文）。
2. 在任一 Kandev 任务里，把交接文件中「交接 prompt」整段交给 agent 执行。

也可以在 Kandev 设置 → Automations 里手动建：schedule `*/20 * * * *`、hidden run、便宜模型的 profile、并发 1，prompt 用 `guard-prompt.<workspace 前 8 位>.local.md` 代码块里的全文。

人工查看守护会看到什么：`python <home>/kandev/stage.py --ids <ids 文件> --dry-run`。不带 `--dry-run` 的运行会把这次的告警记成已发。

## 其他手动部分

- **仓库设置**：Copy files、worktree 分支模板等，按项目由 baseline 模块确定（需要用户配置时经 pm 提出）后再配置。
