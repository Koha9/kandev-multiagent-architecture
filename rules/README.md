# 规则槽位

这里是可以定制的规则和参数的出厂版本。部署时它们被内联进步骤 prompt（`kandev/build_workflows.py`），所以改完要重新部署才生效。与角色卡、README 不一致时，agent 以步骤 prompt 为准。

| 文件 | 内容 | 出厂状态 |
|---|---|---|
| `workspace.md` | 时间戳、临时资源的登记和清理 | 有内容 |
| `testing.md` | 消耗额度的操作、测试选择参数 | 有内容 |
| `quality.md` | 主动性与验证的要求 | 有内容 |
| `git.md` | 你的 git 习惯 | 空，不注入 |
| `coding.md` | 对所有项目都适用的编码习惯 | 空，不注入 |
| `params.json` | `dev_wip`（「开发」步骤的并发上限）、`refresh_wakes`（常驻会话被唤醒多少次后刷新）、`guard`（守护阈值，分钟：`T_IDLE`、`T_DECISION`、`T_HOLD`、`T_STALE`、`T_DEDUP`、`T_GATE`（autonomy 2 的立项确认超时，0 关闭）） | 出厂值 |

## 注入到哪些角色

| 槽位 | 角色 |
|---|---|
| `workspace` | 除「接收」外的所有角色 |
| `testing` | 评审、模块管理、模块验收、开发、审核、合并 |
| `quality` | 项目管理、评审、模块管理、模块验收、开发、审核 |
| `git` | 模块管理、开发、审核、合并 |
| `coding` | 开发、审核 |

## 怎么定制

定制写在**安装目录**里（缺省 `~/.kandev-ma/<workspace id 前 8 位>/`；链接模式下是本仓库）。在源仓库里建 `custom/` 对独立安装不起作用。

1. 不改这里的文件。把要改的那一个复制到安装目录的 `custom/rules/`（同名），在副本里改。`params.json` 的副本只写要改的键，值必须是正整数。
2. 角色卡、消息协议、项目模板在 `mgmt-template/`，「接收」步骤的参数缺省值在 `docs/intake.md`：独立安装时直接改安装目录里的文件，升级时你改过的文件会保留，新版写在旁边的 `.new` 文件里。它们对新启动的项目生效，不需要重新部署。
3. 规则槽位和参数要重新部署才生效。让 AI 按 `AGENTS.md`「F. 定制」做，或自己运行：
   ```
   python <安装目录>/kandev/ma.py diff
   python <安装目录>/kandev/ma.py apply --confirmed <diff 打印的值>
   ```

格式：`.md` 槽位第一行 `---` 之前是说明，之后是正文；正文为空表示不注入。