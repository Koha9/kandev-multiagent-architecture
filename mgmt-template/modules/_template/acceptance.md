# 验收记录 · <模块>

> 写者：模块验收者（W2「验收调查」，scope mod-audit:<模块>）。只追加，每轮验收一节。不记录原始代码，只记录路径、命令和结论。
> 模块 agent 按本文件的修复项原样建修复子任务；其他模块完成后也读本文件了解本模块交付了什么。

## 第 1 轮 · YYYY-MM-DD HH:MM
- 分支：mod/auth @ <commit>
- 子任务终态：auth-01 merged，auth-02 merged，auth-05 dropped（已被 auth-02 覆盖，理由仍成立）

### 覆盖核对
<!-- 模块契约的每条验收要点、与本模块有关的每条 B-n，是否被 spec 的某条 MA 覆盖。有缺口即为 fail。 -->
| 条目 | 来源 | 覆盖它的 MA | 结论 |
|---|---|---|---|
| 登录、刷新、注销 | 模块契约 · 验收要点 | MA-1, MA-3 | 覆盖 |
| B-1 | charter「模块边界」（本模块是提供方） | MA-4 | 覆盖 |

### 测试
| 命令 | 结果 |
|---|---|
| | |

### 模块验收标准
| 编号 | 结果 | 证据 |
|---|---|---|
| MA-1 | pass / fail / unverified(原因) | |

### 修复项
<!-- 每个 fail 一条；没有写"无"。格式见 roles/module-auditor.md「修复项格式」。 -->
| 编号 | 担当 | 复现步骤 | 期望 | 实际 | 疑似位置 | 对应 |
|---|---|---|---|---|---|---|
| F-1 | auth-02 | `pytest tests/auth/test_login.py -k locked` | 返回 423 | 返回 500 | src/auth/api/login.py | MA-3 |

### 建议
<!-- 子任务 report 中值得做的 suggestions：本模块内 / 涉及其他模块。没有写"无"。 -->
- 无

### 结论
- 通过 → REPORT 消息 id：M-mod-audit.auth-...（有 unverified 时 result=partial，逐条列出）
- 不通过 → 退回「等待开发」：N 条修复项（第 3 轮或涉及其他模块时另发 ESCALATE <id>）
