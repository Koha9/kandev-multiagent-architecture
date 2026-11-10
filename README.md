# Kandev 多 Agent 开发架构

在 Kandev 上用多个编码 agent 无人值守或半值守地完成中到大型软件项目的 workflow 设计、模板和部署脚本。架构与具体项目无关。当前版本 v3.1。

本仓库分四部分，彼此分开：

## 1. 多 Agent 架构（本仓库的目标）

| 想做什么 | 看哪里 |
|---|---|
| 了解整体设计 | [docs/workflow.md](docs/workflow.md) |
| 看流程图 | [workflow-diagrams.md](workflow-diagrams.md)（浏览器打开 `workflow-diagrams.html` 也可以） |
| 查看或修改各步骤的 prompt | [docs/prompts.md](docs/prompts.md)，由脚本生成；源头是 `kandev/build_workflows.py` |
| 管理目录怎么组织、文档格式 | [docs/mgmt-workspace.md](docs/mgmt-workspace.md) |
| agent 之间怎么通信 | [mgmt-template/protocol/message.md](mgmt-template/protocol/message.md) |
| 部署到 Kandev | [kandev/README.md](kandev/README.md)；从 v3 升级见 [kandev/UPGRADE-v3.1.md](kandev/UPGRADE-v3.1.md) |
| 外部 MCP 做不了、要交给 Kandev 内部 agent 的工作 | [kandev/handoff/](kandev/handoff/guard-automation.md) |
| 改完 workflow 后自检 | `python kandev/check_docs.py` |

## 2. 开发项目约定（架构带入每个被开发项目）

| 内容 | 看哪里 |
|---|---|
| 每个项目要遵守的约定：额度与副作用、约束清单、测试、截图、合并与推送 | [docs/project-conventions.md](docs/project-conventions.md) |
| 复制到每个项目管理目录的模板、角色卡和检查脚本 | [mgmt-template/](mgmt-template/README.md) |

## 3. 评估（用具体开发项目检验架构）

[evaluation/](evaluation/README.md)：基准项目、指标采集脚本。试点记录涉及具体项目，只保存在本机，不在公开仓库中。

## 4. 调研与设计演进

- `reports/`、`research_notes/`：多 agent 开发的调研（成功案例、省 token、Kandev 机制、GitHub 作为协作平台）、与 dsh-superagent 的对比（v3.1 的依据）、平台选型
- `workflow-draft-v1.md` → `workflow-design-v2.md` → `docs/workflow.md`：设计的演进
