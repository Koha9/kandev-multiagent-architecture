# 示例 workflow（Kandev 导出）

**中文** | [English](README.en.md)

这三个文件是从一个实际部署的 Kandev workspace 用 `export_workflow_kandev` 导出的，内容与 `build_workflows.py` 生成的完全一致。本机相关的 ID 已经换成占位符。

| 文件 | workflow | 步骤 |
|---|---|---|
| [W1-project.json](W1-project.json) | 多Agent · 项目管理 | 接收 → 立项规划 → 立项评审 → 立项确认 → 模块下发 → 调度 → 项目验收 → 人工终审 → 收尾合并 → 完成（+ 刷新） |
| [W2-module.json](W2-module.json) | 多Agent · 模块管理 | 模块规划 → 等待开发 → 验收调查 → 完成（+ 刷新） |
| [W3-dev.json](W3-dev.json) | 多Agent · 开发 | 待开发 → 开发 → 审核 → 等待决策 → 合并 → 完成 |

## 用途

- **看配置**：每个步骤的 prompt、事件（on_enter / on_turn_complete 等）、WIP、会话策略、profile 的模型和模式，都可以直接在这里查。prompt 的可读版本见 [docs/prompts.md](../../docs/prompts.md)。
- **手动导入**（不推荐）：Kandev 的 workflow 导入功能可以直接导入这些文件，但要注意两点：
  1. 导入时 profile 按 model / mode 匹配。同一个模型有多个 profile 时可能匹配错，导入后要逐个步骤检查。
  2. W1、W2 的 prompt 里引用了下一层 workflow 的 ID，需要导入后手动替换：
     - W2「模块规划」prompt：`<W3_ID>`、`<W3_DEV_STEP_ID>`、`<W3_HOLD_STEP_ID>`
     - W1「接收」prompt：`<ARCH_ROOT>`（本仓库在运行 Kandev 的机器上的绝对路径，用正斜杠）
     - W1「模块下发」prompt：`<W2_ID>`、`<W2_PLAN_STEP_ID>`

推荐用 `python kandev/build_workflows.py apply` 部署，它会自动处理上面两点，见 [kandev/README.md](../README.md)。

## 重新导出

部署后在 `kandev/` 下运行 `python verify_export.py`，会覆盖这里的三个文件，并用 `kandev_ids.json` 里的 ID 自动替换成占位符。
