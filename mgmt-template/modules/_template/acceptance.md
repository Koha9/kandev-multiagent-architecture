# 验收记录 · <模块>

> 写者：该模块 agent。只追加，每轮验收一节。不记录原始代码，只记录路径、命令和结论。

## 第 1 轮 · YYYY-MM-DD HH:MM
- 分支：mod/auth @ <commit>
- 子任务终态：auth-01 merged，auth-02 merged，auth-03 FAILED → 已补建 auth-04，auth-05 dropped（已被 auth-02 覆盖）

### 测试
| 命令 | 结果 |
|---|---|
| | |

### 模块验收标准
| 编号 | 结果 | 证据 |
|---|---|---|
| MA-1 | pass / fail / unverified(原因) | |

### 问答
| 消息 id | 对象 | 问题 | 结论 |
|---|---|---|---|
| M-mod.auth-... | dev:auth-02 | 令牌刷新是否幂等 | 是，见 report |

### 结论
- 通过 → REPORT 消息 id：M-mod.auth-...（有 unverified 时 result=partial，逐条列出）
- 不通过 → 修复任务：auth-05（原因：...）
