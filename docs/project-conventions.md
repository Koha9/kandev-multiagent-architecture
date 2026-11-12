# 开发项目约定

**中文** | [English](project-conventions.en.md)

> 本文件写的是**被开发项目一侧**的约定：多 agent 架构要求每个项目具备什么、遵守什么。
> 这些内容由 pm 在「立项规划」「环境基线」写进**项目自己的**管理文件（`project/conventions.md`、`project/environment.md`，模板在 [../mgmt-template/project/](../mgmt-template/project/conventions.md)），每个项目按自己的技术栈填写。
> 架构文档 [workflow.md](workflow.md) 只规定由哪个步骤、哪个角色落实这些约定，以及被拦下时怎么升级，不规定具体内容。

## 1. 额度与外部副作用

- 真实 AI 调用、付费 API、部署、推送远端、改远端设置：必须由显式开关打开（例如环境变量 `<PROJECT>_REAL_AI=1`），默认关闭。
- 需要真实调用的测试用 marker 标记，并在测试框架层面（conftest 或同等位置）再检查一次开关，未打开时一律 skip。只靠测试配置的默认值（例如 pytest.ini 的 addopts）不够，一个命令行参数就能覆盖。
- 每种真实调用的次数上限写进 conventions，并由额度账本强制（见第 2 节）。
- 需要真实调用来证明的验收项，复用模块验收中已有的结果，不重复调用。

## 2. 约束清单与执行方式

conventions「约束清单」为每条约束标明执行方式：`代码强制` / `检查脚本` / `仅 prompt`。环境基线把能强制的都落实为代码，命令写进 environment.md「约束落实」。

| 约束 | 机制 | 工具 |
|---|---|---|
| 不推送远端（conventions 没有明确允许时） | 对每个 remote 设置 push 地址为 `DISABLED` | git |
| 开发只改 owns 内的文件 | 开发上报前、审核时各跑一次越界检查 | [`tools/check_owns.py`](../mgmt-template/tools/check_owns.py) |
| 真实调用次数上限 | 额度账本：conftest 在每次真实调用前 consume，超限即失败 | [`tools/quota.py`](../mgmt-template/tools/quota.py) |
| 管理目录单写者（用 git 管理时） | pre-commit 钩子按 `MGMT_SCOPE` 检查路径 | [`tools/mgmt_precommit.py`](../mgmt-template/tools/mgmt_precommit.py) |
| 审核不改测试选择参数 | 写在审核角色卡中 | 仅 prompt |

`tools/` 下的脚本只用 Python 标准库，随 mgmt-template 复制到每个项目的管理目录。命令中的 `python` 写成 environment.md 里的解释器绝对路径。

## 3. 测试与复跑

- 每个开发任务的契约写明可直接执行的测试命令；新功能必须带测试，不能为了通过而删除或弱化已有测试。
- 审核、模块验收、项目验收复跑测试时，按 environment.md 原样执行，不得修改测试选择参数（`-o addopts`、`-m`、`-k` 等），不得打开消耗额度的开关。
- environment.md 写明冒烟测试（一条命令、期望输出、耗时）。所有开发会话开始时先跑一次，失败就上报，不在坏的基线上开发。
- 结合测试（项目有 integration-test 模块时）：environment.md「结合测试」写明自动化工具、如何启动真实组装的应用、一条运行命令和测试目录；环境基线在骨架中放一个能跑通的最小用例。
  - 测试对真实组装的应用运行，断言用户可见的结果和数据状态，只 mock 消耗额度的外部调用。
  - 优先用自动化工具。手动操作产品只作回退：工具做不到的场景才用，同样优先借助工具，并在 report 写明原因和证据。
  - 测出产品缺陷时保留失败的用例并上报，不改断言、不加 mock、不跳过。
  - 这套测试留在仓库里，项目验收、收尾合并和之后的修复轮次都会重跑。

## 4. 界面证据

- 有界面的项目在 environment.md「截图」一节写明工具、命令和视口。
- `ui: true` 的任务在 report 中附截图：改的是已有界面时要有改动前和改动后，存到 `<mgmt_root>/evidence/<任务id>/`。审核核对截图与 AC 一致。
- 项目验收在 final-report「终审运行方式」中汇总关键页面在各视口的截图，减少用户在终审时自己启动服务查看的成本。

## 5. 合并与推送

- 合并方式写进 environment.md「合并方式」：本地由模块 agent 合并（默认），或 PR（base=`mod/<模块>`）+ 必需检查。
- 默认只在本地合并，不推送远端。要推送或开 PR，必须在 conventions 和 environment.md 中明确约定，并相应调整第 2 节的禁止推送。

## 6. 环境

- environment.md 写明 OS / Shell、语言与版本、解释器或环境、从零到可运行的安装命令、常用命令。
- 需要 Kandev 仓库设置 Copy files 的文件写进「Copy files」：attended 时请用户配置；unattended 时选不依赖 Copy files 的方案并写 ADR。

## 7. 对应的模板

| 约定 | 项目中的文件 | 写者 |
|---|---|---|
| 第 1–3、5 节 | `project/conventions.md`（「消耗额度与外部副作用」「约束清单」「测试」） | pm |
| 第 2–6 节的命令 | `project/environment.md`（「约束落实」「截图」「合并方式」「Copy files」） | pm |
| 额度账本 | `quota/ledger.json` | 只由 `tools/quota.py` 写 |
| 截图 | `evidence/<任务id>/` | 该任务的开发 |
