# Example workflows (Kandev export)

[中文](README.md) | **English**

These three files were exported with `export_workflow_kandev` from a real deployed Kandev workspace, and their content is identical to what `build_workflows.py` generates. Machine-specific IDs have been replaced with placeholders.

| File | Workflow | Steps |
|---|---|---|
| [W1-project.json](W1-project.json) | 多Agent · 项目管理 (W1 Project management) | Not started (待立项) → Project planning (立项规划) → Plan review (立项评审) → Plan approval (立项确认) → Environment baseline (环境基线) → Module dispatch (模块下发) → Coordination (调度) → Project acceptance (项目验收) → Final human review (人工终审) → Final merge (收尾合并) → Done (完成) (+ Refresh (刷新)) |
| [W2-module.json](W2-module.json) | 多Agent · 模块管理 (W2 Module management) | Module planning (模块规划) → Waiting on development (等待开发) → Acceptance check (验收调查) → Done (完成) (+ Refresh (刷新)) |
| [W3-dev.json](W3-dev.json) | 多Agent · 开发 (W3 Development) | Queued (待开发) → Develop (开发) → Review (审核) → Awaiting decision (等待决策) → Merge (合并) → Done (完成) |

## Uses

- **Inspecting the configuration**: each step's prompt, events (on_enter / on_turn_complete, etc.), WIP, session policy, and the profile's model and mode can all be looked up directly here. For a readable version of the prompts, see [docs/prompts.md](../../docs/prompts.md) (Chinese).
- **Manual import** (not recommended): Kandev's workflow import feature can import these files directly, but note two things:
  1. On import, profiles are matched by model / mode. When the same model has several profiles, the match may be wrong, so check every step after importing.
  2. The W1 and W2 prompts reference the IDs of the next-level workflow, which must be replaced by hand after importing:
     - W2 Module planning (模块规划) prompt: `<W3_ID>`, `<W3_DEV_STEP_ID>`, `<W3_HOLD_STEP_ID>`
     - W1 Module dispatch (模块下发) prompt: `<W2_ID>`, `<W2_PLAN_STEP_ID>`

Deploying with `python kandev/build_workflows.py apply` is recommended; it handles both points above automatically, see [kandev/README.en.md](../README.en.md).

## Re-exporting

After deploying, run `python verify_export.py` in `kandev/`. It overwrites the three files here and automatically replaces the IDs from `kandev_ids.json` with placeholders.
