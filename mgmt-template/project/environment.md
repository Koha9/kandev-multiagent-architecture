# 环境基线 · <project>

> 写者：baseline 模块 agent（mod:baseline），命令和结果取自它的开发子任务的 report。所有开发会话开始时都要按「冒烟测试」一节执行一遍；合并步骤按「合并门禁」执行。

## 运行环境
- OS / Shell：
- 语言与版本：
- 解释器或环境：<例如 conda 环境名，写在仓库根目录的 .conda-env>

## 安装
```
<从零到可运行的命令，按顺序>
```

## 常用命令
| 用途 | 命令 | 期望 |
|---|---|---|
| 构建 | | |
| 单元测试 | | 全部通过 |
| lint / 类型检查 | | 无错误 |

## 冒烟测试
- 命令：`<一条命令>`
- 期望输出：<关键一行>
- 耗时：<约 N 秒>

## 结合测试
<!-- charter 中有 integration-test 模块时填写，否则写"不适用"。测的是真实组装的应用，不是 mock。 -->
- 工具：<按技术栈选，例如 Web 界面用 Playwright>
- 启动应用：`<命令>`（独立端口 <端口>，临时数据 <位置>，不影响开发数据）
- 运行命令：`<一条命令>`，期望：全部通过
- 测试目录：`<例如 tests/e2e/>`
- 允许 mock 的外部调用：<只限消耗额度的，例如真实 AI>
- 手动操作产品只作回退：自动化工具做不到的场景才用，并在 report 写明原因和证据

## Copy files（Kandev 仓库设置）
- `<.conda-env>`
- `<.env.local>`

## 合并方式
- 开发分支合入模块分支：<本地（合并步骤通过门禁后自己快进合入 mod/<模块>） | PR（base=mod/<模块>）+ 必需检查>
- 集成分支：`integration`（从基线分支切出）

## 合并门禁
<!-- W3「合并」步骤在合入模块分支前原样运行；失败退回「开发」。 -->
| 检查 | 命令 | 期望 |
|---|---|---|
| 完整本地检查（lint + 全量测试 + 构建） | `<一条命令，例如 scripts/check.ps1>` | 退出码 0 |
| 结合测试套件 | `<命令>` 或"不包括"（说明原因，例如耗时） | 全部通过 |
| owns 检查 | 见「约束落实」 | OK |

## 约束落实
<!-- 对应 conventions「约束清单」，写出可直接执行的命令。 -->
| 约束 | 命令或机制 | 已验证 |
|---|---|---|
| 禁止推送 | `git -C <repo> remote set-url --push origin DISABLED` | <日期> |
| owns 检查 | `python <mgmt_root>/tools/check_owns.py --tasks <mgmt_root>/modules/<模块>/tasks.json --task <任务id> --base mod/<模块>` | |
| 额度账本 | 账本 `<mgmt_root>/quota/ledger.json`；打开真实调用时同时设置 `MA_QUOTA_LEDGER=<账本>`、`MA_QUOTA_TOOL=<mgmt_root>/tools/quota.py`；查看用量 `python <mgmt_root>/tools/quota.py --ledger <账本> show` | |
| 真实调用开关 | `<PROJECT>_REAL_AI=1`（conftest 检查，未设置一律 skip） | |

## 截图
<!-- 有界面的项目填写；ui: true 的任务按这里截图 -->
- 工具与命令：<例如 Playwright 脚本 `scripts/shot.ps1 <url> <out>`>
- 视口：<例如 390×844、700×1000、1440×900>
- 存放：`<mgmt_root>/evidence/<任务id>/`，文件名 `<页面>-<视口>-before|after.png`

## 已知问题
- 无
