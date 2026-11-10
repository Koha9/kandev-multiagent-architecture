# Kandev: Workflow Model and Multi-Agent Features (state as of 2026-11-08)

Research method: repo metadata via `gh api repos/kdlbs/kandev`; shallow clone of `main` at commit `52309e6` (committed 2026-11-07 22:58 UTC); direct reading of `README.md`, `docs/`, `docs/public/` (the docs-site sources), ADRs in `docs/decisions/`, built-in workflow templates in `apps/backend/config/workflows/`, and Go source under `apps/backend/internal/`. Also checked kandev.ai, open GitHub issues, and release notes. Below, "[doc]" means documented behavior and "[code]" means behavior read from source. Base URL for file links: `https://github.com/kdlbs/kandev/blob/main/`.

---

## Q1. What is Kandev: identity, architecture, agents, executors, license, maturity

### Takeaway
Kandev (repo `kdlbs/kandev`, site https://kandev.ai) is an AGPL-3.0, self-hostable, server-first "AI kanban and development environment". It is a single Go control-plane binary with an embedded Vite/React SPA. Agents run through an `agentctl` runtime on pluggable executors (local, worktree, Docker, Kubernetes, SSH, Sprites). It supports more than 20 agent CLIs, mostly through ACP. It is very active, with near-daily commits and v0.99.1 released 2026-11-06, but it is still pre-1.0 and the multi-agent "Office" layer is experimental.

### Cited Findings
- **Repo identity and stats** (from `gh api`, 2026-11-08): `kdlbs/kandev`; description "AI Kanban & Development Environment. Orchestrate multiple agents, review changes, open PRs. Multi-provider, self-hostable, no telemetry."; homepage `https://kandev.ai`; license AGPL-3.0; primary language Go; 1,086 stars, 181 forks, 296 open issues+PRs; created 2026-01-09; last push 2026-11-08 — [GitHub repo](https://github.com/kdlbs/kandev)
- **Releases:** v0.99.1 (2026-11-06), v0.99.0 (2026-11-05), Plugin SDK 0.1.0 (`pluginsdk/v0.1.0`, 2026-11-05), v0.98.0 (2026-10-23), v0.97.0 (2026-10-04). The CHANGELOG has 120 release headings, from 0.0.1 (2026-02-15) to 0.99.1 (2026-11-06) — [Releases](https://github.com/kdlbs/kandev/releases), [CHANGELOG.md](https://github.com/kdlbs/kandev/blob/main/CHANGELOG.md)
- **Vision:** "Humans stay in control. Define tasks, build agentic workflows with gates, review every change, decide what ships." It also aims for "Remote agents… a single control plane: offload execution to servers, orchestrate from anywhere, including your phone" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- **Architecture [doc]:** the control plane is one Go process. The native `kandev` executable starts a Go launcher, whose internal `__backend` command starts the backend. The backend serves the web app, HTTP API, WebSocket API (`/ws`) and external MCP routes. Persistence is SQLite by default, with PostgreSQL supported. The event bus is in-memory by default, or NATS when configured; the bus has no replay, so consumers recover state from the DB. Task agents run through the selected executor and its `agentctl` runtime, which owns the agent subprocess and adapts its protocol, including ACP — [docs/ARCHITECTURE.md](https://github.com/kdlbs/kandev/blob/main/docs/ARCHITECTURE.md)
- **Project layout:** `apps/backend` (Go orchestrator, lifecycle, agentctl, WS gateway), `apps/web` (Vite/React SPA, Zustand), `apps/cli` (npm shim), `apps/desktop` (Tauri shell), `apps/packages` (shared UI). Distribution is a native Go binary with the frontend embedded; install via Homebrew, Scoop, npm/npx, or the desktop app. Data (worktrees, SQLite) lives in `~/.kandev` by default — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- **Supported agent CLIs (README table):** Claude Code (`@agentclientprotocol/claude-agent-acp`), Codex (`@agentclientprotocol/codex-acp`), Codex app server (`@openai/codex`, experimental feature toggle), GitHub Copilot, Gemini CLI, Amp, Auggie, OpenCode (v2 `@opencode/cli`; v1 `opencode-ai`), Cursor (`cursor-agent`), Devin, Qwen, Factory Droid, iFlow (beta), Kilocode, Pi, Kimi, AWS Kiro, Qoder, Trae, Oh My Pi, Grok, Hermes, Antigravity. "Most structured agent integrations communicate via ACP." Any other CLI can run as a TUI in a PTY via "CLI passthrough" ("Bring your own TUI agents") — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- **Executors:** Local Process, Docker, Kubernetes (Pod per task session; no operator), SSH, and Sprites (sprites.dev cloud). "Git worktree" is also listed as an executor type, and features.md lists "local host processes, git worktrees, Docker containers, remote SSH sessions, or Sprites". Executor profiles hold prepare scripts, env vars, credentials, and settings. Private executor ownership exists for shared instances — [README](https://github.com/kdlbs/kandev/blob/main/README.md), [docs/features.md](https://github.com/kdlbs/kandev/blob/main/docs/features.md)
- **Fallback executor [doc]:** if task-MCP creation has no explicit or inherited executor, Kandev uses the built-in **git-worktree** executor and does not consult the workspace's Default Executor — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- **Website:** kandev.ai presents Kandev as an "open-source workbench for coding agents" that is "Agent neutral" and "Runs on your infrastructure". Docs are at `/docs`, plus `/changelog` and a browser `/demo` — [kandev.ai](https://kandev.ai)
- **Roadmap "Now" list:** stability across agent integrations (stated as the primary focus), mobile UI, plugin system, authentication, i18n, Office mode, remote SSH runtime, GitLab. "Later": Kubernetes operator, analytics. "Done": multi-repo tasks, "Coordinator mode - have an agent coordinate sub-tasks executed by other agents", issue tracker import — [docs/roadmap.md](https://github.com/kdlbs/kandev/blob/main/docs/roadmap.md)
- **Office mode:** an "experimental autonomy layer for persistent agent teams, disabled by default in production" (agent roles and permissions, dashboards, inbox/approvals, routines, delegation, skills, memory, cost tracking, budgets). It is "not yet a stable production contract" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- Third-party summary: a Reddit user reported that Windows support is rougher than macOS/Linux, and another comparison calls Kandev a heavy, IDE-like workspace (secondary sources, aggregated by search) — [web search summary incl. reddit snapshot](https://reddit.sentinel-team.org/posts/1thyq22/snapshots/2026-05-20T00%3A16%3A29.879841Z)

### Inferences
- The version cadence (0.0.1 to 0.99.1 in about 9 months, 120 releases) and the "stability and bug fixes… primary focus" roadmap item point to fast-moving, pre-1.0 software. Workflow and MCP contracts are still changing: export format v1 to v3 and many ADRs dated July to November 2026. Pin a version for any workflow design.
- The repo dogfoods its own agent configs (`.claude/`, `.codex/`, `.cursor/`, `.opencode/`, `.agents/`, `.kandev/` directories are at the root). Kandev is developed with multiple agents.

### Gaps
- No official statement of production readiness or an SLA. Download and install counts were not found.
- I did not verify the Discord or community size.

---

## Q2. Workflow model: definition, step configuration, events/actions, templates, transitions, per-step agents, session continuity

### Takeaway
A **Workspace** holds many **Workflows**. A workflow is an ordered list of **Steps** (the kanban columns), each with a prompt, an optional agent profile, flags, and **event triggers** whose actions are mostly *move* or *start/reset agent*. Tasks move between steps by user drag/MCP move, by user message (`on_turn_start`), by agent turn end or an explicit `step_complete_kandev` signal (`on_turn_complete`), by children completing, or by PR merged/closed. Each step can pin a different agent profile (agent, model, mode). Session continuity is explicit:
- Same effective profile means the same session continues with a new turn.
- A profile change means reuse an existing session for that profile or start a new one (`profile_session_start_policy`), and complete or park the old one (`profile_session_end_policy`).
- `reset_agent_context` forces a fresh ACP session.
- `session_target` can route a step to the task's initial session or an earlier step's session.

### Cited Findings

**Core concepts [doc]**
- The concepts are: Workspace (repos, workflows, tasks, integrations, defaults); Workflow ("An ordered set of steps plus the rules that run when a task or agent turn reaches an event"); Workflow step; Task (title, prompt, workflow position, repo attachments, sessions, one shared plan); Task repository; Session ("One agent conversation attached to a task. Several sessions can share the same task environment."); Plan (single editable Markdown plan with version history). "Moving a task changes its step. It does not prove that an agent ran…" — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- Workflows are configured in **Settings → Workspaces → workspace → Workflows**. Use **Custom** for your own automation and keep a **Review** or **Do nothing** step as a human gate — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)

**Workflow-level fields [code+doc]**
- `Workflow` struct fields: `Name`, `Description`, `Prompt` ("optional workflow-level agent instructions prepended at every step entry before the step prompt"), `AgentProfileID` (workflow default profile), `WorkflowTemplateID`, `Source` (`manual` | `github`) and `SourcePath` (for synced workflows), `Hidden`, and `Style` (`kanban`/`office`/`custom`, a frontend-only hint) — [apps/backend/internal/task/models/models.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/task/models/models.go)

**Step-level fields [code]** (`WorkflowStep` in [apps/backend/internal/workflow/models/models.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/models.go)):
- `Name`, `Position` (0-based order; "next/previous" follow it), `Color` (Tailwind class), `Prompt`, `Events` (StepEvents), `AllowManualMove`, `IsStartStep`, `ShowInCommandPanel`, `AutoArchiveAfterHours`.
- `AgentProfileID` (step override of the workflow default), `ProfileSessionStartPolicy` (`reuse` | `new`), `ProfileSessionEndPolicy` (`complete` | `park`).
- `DisableUnclassifiedFallback`.
- `SessionTarget` (`{kind: initial}` or `{kind: step, step_id}` pointing to an *earlier* step) — [session_target.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/session_target.go)
- `WIPLimit`, `PullFromStepID` (one-hop feeder step).
- `StageType` (`work`/`review`/`approval`/`custom`/`hold`). This is an Office/Phase-2 field; per the code comment, "The execution engine does not branch on it".
- `AutoAdvanceRequiresSignal` (gates `on_turn_complete` on `step_complete_kandev`, ADR 0015), `CancelTriggersTurnComplete`, `CompleteTaskOnEnter`.
- `SelectAutoStartStep`: a task created *with* an agent start lands in the first step (by position) that has `auto_start_agent`, not necessarily the `is_start_step` step — [models.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/models.go)

**Step controls as exposed in the UI editor [doc]**
- Prompt (`{{task_prompt}}` inserts the task description; `@name` references a saved prompt).
- Start step: at most one. If none is set, the first step by position is used. "Creating a task that starts an agent immediately uses the first Auto-start agent step instead."
- Auto-start agent: adds `auto_start_agent` to `on_enter`.
- Plan mode: adds `enable_plan_mode` on entry.
- Reset agent context: disabled when the step changes agent profile.
- Allow manual move: "a product-UI rule, not a security boundary for API clients".
- Show in command panel.
- Auto-archive: hours; the sweep runs every 5 minutes.
- Wait for agent completion signal: waits for `step_complete_kandev`. Default off.
- Run completion actions when a turn is cancelled: default off for custom steps. Built-in Kanban enables it on Backlog and In Progress.
- Complete task on entry: final step only.
- WIP limit: `0` means unlimited, and overflow is visible and queued.
- Pull from: feeder step.
- Source: [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)

**Events (triggers) [code+doc]** — `StepEvents` in [models.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/models.go):
- Kanban-era triggers with typed actions:
  - `on_enter`: `enable_plan_mode`, `auto_start_agent`, `reset_agent_context`, `set_session_mode` (config `mode`, e.g. `acceptEdits`), `clear_decisions`, `queue_run`, `queue_run_for_each_participant`. The code also has `ensure_participant_seat` and `run_code_review`; these two appear only in code constants, not in the import/export doc's action table.
  - `on_turn_start`: `move_to_next`, `move_to_previous`, `move_to_step`.
  - `on_turn_complete`: `move_to_next`, `move_to_previous`, `move_to_step`, `disable_plan_mode`.
  - `on_exit`: `disable_plan_mode`.
- Phase-2/Office triggers with generic actions (`move_to_next`/`move_to_previous`/`move_to_step`/`auto_start_agent`/`queue_run`/`clear_decisions`/`queue_run_for_each_participant`): `on_comment`, `on_blocker_resolved`, `on_children_completed`, `on_approval_resolved`, `on_heartbeat`, `on_budget_alert`, `on_agent_error`.
- PR-poller triggers: `on_pr_merged` (every linked PR merged) and `on_pr_closed` (closed without merge). Both fire without an agent turn — [docs/public/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md), [docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md)
- **Event semantics [doc]:**
  - `on_turn_start` runs when a *user* sends a message, before delivery. "Prompts started automatically when a task enters a step do not run this event."
  - `on_turn_complete` runs when a normal agent turn finishes and its signal requirements are met. "A pending clarification always blocks completion."
  - `on_children_completed` runs when every active direct child is terminal (COMPLETED/FAILED/CANCELLED). Archived and ephemeral children and grandchildren are ignored, and the parent must have an active session in CREATED/STARTING/RUNNING/WAITING_FOR_INPUT. "Terminal child state means work stopped; it does not mean every child succeeded."
  - Guidance: "Keep one transition action per event."
  - Sources: [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md), [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- **`run_code_review` on_enter action [code]:** "starts a native code-review pass over the task's changed files when it enters the step". It takes an optional review `agent_profile` in its config. "A review failure never blocks the transition" — [apps/backend/internal/orchestrator/workflow_callbacks.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/orchestrator/workflow_callbacks.go), [apps/backend/internal/workflow/engine/types.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/engine/types.go)
- `auto_start_agent` compiles with `QueueIfBusy: true`: if the session is busy, the entry prompt is queued instead of dropped [code] — [engine/types.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/engine/types.go)

**Explicit completion signal (`step_complete_kandev`) [code+ADR]**
- ADR 0015 (status "proposed", amended 2026-08-14 and 2026-09-05; the feature is implemented): when enabled, "transitions fire only when the agent calls … `step_complete_kandev`". Bare halts (questions, rate limits, crashes) do not advance. The signal is stored in `TaskSession.Metadata["pending_step_completion_signal"]` with `step_id`, `source` (`agent` | `manual_fallback`), `summary`, `handoff`, `blockers`, and `signaled_at`. It is cleared on transition, on a user message ("re-open semantics"), or on any step change, and it is idempotent (`already_signaled`) — [docs/decisions/0015-explicit-completion-signal-for-auto-advance.md](https://github.com/kdlbs/kandev/blob/main/docs/decisions/0015-explicit-completion-signal-for-auto-advance.md)
- Tool schema [code]: `summary` (required, shown to user); `handoff` ("delivered once in that step's first prompt and not carried beyond it. Up to 8,192 bytes"); `blockers` ("Recorded on this step's transition history, not delivered to the next step's agent"). A stale-turn error occurs if the step changed — [apps/backend/internal/mcp/server/](https://github.com/kdlbs/kandev/tree/main/apps/backend/internal/mcp/server)
- Safety note [doc]: "Requiring `step_complete_kandev` can leave a step waiting indefinitely if the agent cannot call it." — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)

**Template variables [doc]**
- In step prompts, `{{task_prompt}}` is the task description.
- In step and workflow prompts, the single-brace tokens are `{task_id}`, `{task_title}`, and `{step_entry_number}` (how many times the task has entered this step, starting at 1).
- Text arriving via `{{task_prompt}}` is not re-scanned. The workflow-level prompt does not expand `{{task_prompt}}`.
- `@name` saved-prompt references are resolved at run time and attached as hidden context. `{{task_prompt}}` inside a saved prompt is not expanded.
- Source: [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)

**Built-in templates [code+doc]**
- Five user-facing templates ("Kandev currently presents these five Kanban templates"):
  - **Kanban** (`id: simple`): Backlog → In Progress → Review → Done.
  - **Plan & Build** (`id: standard`): Todo → Plan → Implementation → Done.
  - **Architecture**: Ideas → Planning → Review → Approved.
  - **Feature Dev**: Todo → Spec → Work → Review → QA → PR → CI Fixup → Done.
  - **PR Review**: Waiting → Review → Done.
  - Sources: [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md), [apps/backend/config/workflows/](https://github.com/kdlbs/kandev/tree/main/apps/backend/config/workflows)
- There are also four hidden/system templates in the same folder, each with `hidden: true`: `improve-kandev` (Improve → Test → PR), `report-kandev-issue`, `routine` ("System workflow for routine-fired tasks. Single auto-completing step"), and `office-default` (Backlog/Work/Review/Approval/Done with `stage_type` custom/work/review/approval/custom) — [apps/backend/config/workflows/](https://github.com/kdlbs/kandev/tree/main/apps/backend/config/workflows)
- **Kanban template details [code]:**
  - Backlog: `on_turn_start: move_to_next` and `on_turn_complete: move_to_step review`.
  - In Progress: `is_start_step`, `on_enter: auto_start_agent`, `on_turn_complete: move_to_step review`, `cancel_triggers_turn_complete: true`.
  - Review: `on_turn_start: move_to_previous`.
  - Done: `complete_task_on_enter: true` and `on_turn_start: move_to_step in-progress`.
  - Source: [kanban.yml](https://github.com/kdlbs/kandev/blob/main/apps/backend/config/workflows/kanban.yml)
- **Feature Dev details [code+doc]:**
  - Spec: `enable_plan_mode` and `auto_start_agent` on enter, `disable_plan_mode` on exit. The prompt tells the agent to save the plan with `create_task_plan_kandev`.
  - Work, QA, PR, and CI Fixup: `auto_start_agent`.
  - Review: `reset_agent_context` then `auto_start_agent`.
  - Done: `complete_task_on_enter`.
  - "The template does **not** auto-advance between phases."
  - Sources: [feature-dev.yml](https://github.com/kdlbs/kandev/blob/main/apps/backend/config/workflows/feature-dev.yml), [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- **Plan & Build** has "no automatic transitions between these steps". **PR Review**: the Review step "expects a GitHub PR number or URL, an authenticated `gh` CLI… reports **BLOCKER** and **SUGGESTION** findings", and "does not publish review comments by itself" — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
  - This conflicts with the older root doc, which says PR Review findings are "BUG, IMPROVEMENT, NITPICK, PERFORMANCE" and that in Feature Dev "Each phase runs a fresh agent turn" — [docs/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-tips.md). Treat the `docs/public` version and the YAML as current.

**How a task moves [doc]**
- Paths: drag/drop (if `allow_manual_move`), **Move here**, **Move with options** (one-time `reset_context`, extra `instructions`, `skip_step_prompt`), the command palette, MCP `move_task_kandev` (same `entry_options`), and automatic events.
- "A move waits for a running agent to finish" (MCP returns `disposition: "deferred"`), and options persist across WIP queueing and restarts.
- Moves re-check reachability, authorization, WIP, archive, workspace, and active-session rules.
- Agent moves into manual steps (no `auto_start_agent`/`queue_run`/`queue_run_for_each_participant`/`run_code_review`/pull source) with prompt or options are rejected.
- Sources: [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md), [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)
- WIP and queueing: "A manual move into a full target succeeds and queues in that target". Queued tasks do not run destination entry actions until promotion. Pull candidates are ordered by board position, then priority, queue time, creation time, and ID — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- An instance-wide **session limit** (off by default; `KANDEV_MAX_CONCURRENT_SESSIONS`) caps automatic starts and new message turns, separate from per-step WIP — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- **Change workflow:** a task can switch to another workflow and keep its identity, description, repos, and conversations, with per-task profile mapping — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)

**Different agents/models per step [doc]**
- README: "Multi-step pipelines that mix-and-match agents per step - for example, Claude Code Opus to design a plan, GitHub Copilot Sonnet to implement it, and Codex GPT 5.4 to review the changes" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- The portable `agent_profile` is `{agent_name (display name), model, mode}`, plus `config_options` in export v3. It exists at workflow level and step level — [docs/public/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md)
- Per-task overrides: "When a workflow has fixed agent profiles on its steps, expand **Advanced settings** while creating a task to replace one or more of them for that task" — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- Same-session model switching: "When a workflow keeps the same conversation across steps, it can change that session's model and provider options" (rules per agent family: Set/Keep/Restore original). "A fixed agent profile creates a separate session and cannot use these rules." — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)

**Session context between steps [doc+code]**
- "Steps with the same effective profile keep the current session." On a profile change:
  - The destination `profile_session_start_policy` is `reuse` ("continues the newest eligible conversation for that profile, or starts a new session when none is available") or `new` (always fresh).
  - The source `profile_session_end_policy` is `complete` (closes the conversation) or `park` ("stops the agent and keeps the conversation available").
  - Source: [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- **Default conflict:** public workflow-tips says "These settings default to reuse on start and park on end", but the import/export reference says end default is `complete` ([docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md)). Verify in the UI or code before relying on either.
- `reset_agent_context` "Starts the step with fresh conversation context". Kandev restores the model, permission mode, and provider options before the next automatic prompt. If the reset fails, the session waits and the prompt is not sent — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- `session_target` (export v2+): `{kind: initial}` targets the task's launch conversation, and `{kind: step, step_position: N}` targets "an earlier direct-profile step". Later, indirect, and inherited sources are rejected — [docs/public/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md), [docs/public/workflow-sync.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-sync.md)
- Durable cross-step context: the task's single shared **Plan** (agents read it via `get_task_plan_kandev`; human edits are visible to the next agent), the `step_complete_kandev` `handoff` (one hop), the workflow-level prompt, and repository files/commits — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- Parked sessions share the task workspace. "Multiple sessions can write to the same workspace at the same time" — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)

### Inferences
- The workflow engine is a per-task state machine with no parallel branches: a task sits in exactly one step. Steps model sequential *phases*, not parallel lanes. Parallelism has to come from multiple tasks, subtasks, or sessions (see Q3). The open feature request for a "decision step that routes a task into workflow lanes" (#4378) supports this.
- A multi-agent pipeline (planner → implementer → reviewer with different vendors) is native: pin a different `agent_profile` per step, choose `new` vs `reuse`, and pass context through the Plan plus `handoff`. A reviewer that must not be biased by the implementer's conversation should use a different profile with `new`, or use `reset_agent_context`.
- Auto-advance without `auto_advance_requires_signal` treats any halt (including a question) as completion, except that pending clarifications block it. For unattended pipelines, enabling the signal is the documented safe pattern, at the risk of a step waiting forever.

### Gaps
- Full semantics of `queue_run`, `queue_run_for_each_participant`, `ensure_participant_seat`, and `clear_decisions` (Office "participants", quorum) are only partly documented and Office-only. I did not trace them in code.
- I did not confirm whether `on_comment`, `on_heartbeat`, and the other Office triggers are evaluated for regular Kanban workflows or only in Office.
- I did not test conditional branching (for example, move to step X on reviewer FAIL, else Y). No such action exists in the action enums; the only options are move next/previous/specific step, which the agent can approximate via `move_task_kandev`.

---

## Q3. Multi-agent features: subtasks, parallelism, agent-to-agent messaging, MCP tools, worktrees, PRs, GitHub

### Takeaway
Kandev has three coordination boundaries:
1. Extra **named sessions** in one task, sharing the workspace.
2. **Subtasks**: one level deep in regular Kanban, with an inherited or new workspace and their own workflow state.
3. **Multi-repo/multi-branch tasks.**

Agents coordinate through a task-scoped MCP server ("Core" package `kandev`). It covers creating subtasks (optionally autopilot), spawning sessions, messaging other tasks or sessions (queued or interrupt), stopping children, reading conversations, dependency chains (`blocked_by`), plans, `move_task_kandev`, and `step_complete_kandev`. A parent's `on_children_completed` trigger joins fan-out work.

### Cited Findings

**Coordination boundaries [doc]**

| Need | Use | Filesystem | Own workflow state |
|---|---|---|---|
| Another agent on the same files and goal | Additional named session | Shares task env | No |
| Child that sees uncommitted files | Subtask, **Inherit parent workspace** | Shares parent's workspace | Yes |
| Child needing isolation or a different repo | Subtask, **Create new workspace** | Own environment | Yes |
| One deliverable across repos | Multi-repo task | Worktree per attachment | No |

Source: [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)

**Parallel sessions in one task [doc]**
- Open them via "Add panel (+) → New Agent". Context options are Blank, Copy initial prompt, or Summarize session (needs a utility agent). "Two sessions can edit the same files concurrently; assign files or phases explicitly."
- Sessions can be renamed, Set as Primary, or Handoff to another profile (Handoff "creates another session; it does not move the task or transfer its workflow state").
- Source: [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- `spawn_session_kandev(prompt, name?, agent_profile_id?, task_id?)` adds a session to the current task or another same-workspace task, with hidden attribution and reply route. It returns `{task_id, session_id, state, agent_profile_id}` — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md), [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)

**Subtasks [doc]**
- "Regular Kanban allows one subtask level". If a child calls `create_task_kandev` with `parent_id: "self"`, it creates a *sibling* under the common parent (`parent_resolution.reason: "kanban_depth_limit"`). "Arbitrary-depth trees belong to the in-progress Office surface." — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- `create_task_kandev` parameters:
  - `parent_id` and `workspace_mode` (`inherit_parent` | `new_workspace`).
  - `start_agent` (default true; requires a detailed prompt).
  - `autopilot` (default false; immutable; not inherited). An autopilot child gets `ask_parent_question_kandev` instead of `ask_user_question_kandev`, and an autopilot root gets neither.
  - `agent_profile_id`, `workflow_step_id`, `repository_url`/`repository_id`/`local_path`, `base_branch`, `priority` (default `medium`), `blocked_by`, and `external_id` (idempotency).
  - Subtasks inherit the parent's workspace, workflow, profile, executor, repositories, and base branches unless overridden.
  - Source: [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md), [docs/public/automation-and-mcp.md](https://github.com/kdlbs/kandev/blob/main/docs/public/automation-and-mcp.md)
- **Profile precedence on creation:** "the destination step's launch profile first … it overrides an explicit `agent_profile_id`". A fallback preference applies when there is no explicit profile: "Creating session profile" vs "Workspace default profile" (Settings → Preferences → Task Behavior) — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md), [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- README: "Agents can spawn sub-tasks that resume from the parent task's session" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- UI subtask dialog: it proposes `<Parent title> / Subtask N`, has an **Autopilot** switch, and starts the agent immediately. It "does not filter profiles for executor compatibility" — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)

**Dependencies / chains [doc]**
- A task "depends on" others (a peer graph, separate from parent/child), set at creation (`blocked_by`) or via `add_task_dependency_kandev`/`remove_task_dependency_kandev`. Cycles are rejected with the path. "While a task is blocked, no automated path starts it." A create with dependencies plus a start request "records the start as an intent" and launches when every predecessor *succeeds*, which is how A → B → C chains run themselves. Failed or cancelled predecessors keep dependents blocked. Deletion unblocks without starting — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md), [docs/features.md](https://github.com/kdlbs/kandev/blob/main/docs/features.md)
- **Doc conflict:** coordination.md says "Regular Kanban does not currently expose a dependency editor or blocker filter", while tasks-and-workflows.md says dependencies are "declared in the **New Task** dialog under **Depends on**" — [coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md) vs [tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md). The latter looks newer (v0.99 notes include "preserve successful dependencies after archival" #4893).

**Agent-to-agent communication [doc]**
- "Agents running in separate Kandev tasks can talk to each other directly… works across all relationship types… and tasks in entirely different workspaces… The only requirement is that each agent knows the other task's full UUID." — [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)
- `message_task_kandev(task_id, prompt, session_id?, delivery_mode?, reply_to_question_id?)` delivery by target state:
  - Running or starting: `"queued"` (FIFO).
  - Idle, waiting, or completed: `"sent"` (new turn).
  - Created: `"started"`.
  - Failed or cancelled: error.
  - `delivery_mode: "interrupt"` is only for a *direct parent* and cancels the child's turn to deliver now.
  - "There is no persistent channel or shared socket between tasks"; replies are a new `message_task_kandev` back to the sender.
  - Source: [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)
- Queue limits: 10 queued messages per session by default (`KANDEV_QUEUE_MAX_PER_SESSION`). Auto-run is ON by default, running one queued message per turn. Auto-merge folds compatible consecutive messages — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- `stop_task_kandev(child_task_id)`: direct same-workspace child only. It marks live sessions `CANCELLED` and moves the task to `REVIEW`. A cancelled session cannot be messaged, so use `spawn_session_kandev` to resume work — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- `list_related_tasks_kandev` is limited to ancestor/descendant/sibling/blocker in the same workspace. `get_task_conversation_kandev` supports pagination and type filters. `list_task_sessions_kandev` lists sessions — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- Codex app-server subagents are "session-local": Kandev shows them in the session but does not create Kandev tasks for them — [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)
- Documented coordinator-led Kanban pattern:
  1. Inspect workspace, workflows, repos, profiles, and related tasks.
  2. Record one parent plan.
  3. Create sessions for shared-file work and subtasks for independent state.
  4. Use isolated workspaces for concurrent writers.
  5. Send bounded messages.
  6. "Let the direct-child completion event move the parent to Review."
  7. A human merges.
  - Source: [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)

**MCP tool inventory [code]** — every `*_kandev` tool name mapped to its package in [apps/backend/internal/mcp/profile/builtin_catalog.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/mcp/profile/builtin_catalog.go):
- **Core (`kandev`, required on regular tasks):**
  - Discovery: `list_workspaces_kandev`, `list_workflows_kandev`, `list_workflow_steps_kandev`, `list_repositories_kandev`, `list_agents_kandev`, `list_executors_kandev`, `list_executor_profiles_kandev`, `list_tasks_kandev`, `list_related_tasks_kandev`, `list_task_sessions_kandev`, `get_task_conversation_kandev`.
  - Task lifecycle: `create_task_kandev`, `update_task_kandev`, `update_task_state_kandev`, `set_task_title_kandev`, `move_task_kandev`, `archive_task_kandev`, `delete_task_kandev`, `transfer_task_kandev`, `step_complete_kandev`, `stop_task_kandev`.
  - Coordination: `spawn_session_kandev`, `message_task_kandev`, `add_task_dependency_kandev`, `remove_task_dependency_kandev`, `ask_user_question_kandev`, `ask_parent_question_kandev`.
  - Plans and documents: `create_task_plan_kandev`, `get_task_plan_kandev`, `edit_task_plan_kandev`, `update_task_plan_kandev`, `delete_task_plan_kandev`, `list_task_plan_revisions_kandev`, `get_task_plan_revision_kandev`, `restore_task_plan_revision_kandev`, `list_task_documents_kandev`, `get_task_document_kandev`, `write_task_document_kandev`.
  - Repos and branches: `add_branch_to_task_kandev`, `add_workspace_sources_kandev`, `update_repository_base_branch_kandev`.
  - PR/MR: `get_task_change_requests_kandev`, `manage_task_change_request_kandev`, `update_task_change_request_automation_kandev`, `report_change_request_auto_fix_outcome_kandev`, `publish_review_findings_kandev`.
  - Canvases: `list_canvases_kandev`, `create_canvas_kandev`, `get_canvas_kandev`, `get_canvas_state_kandev`, `set_canvas_state_kandev`, `publish_canvas_kandev`, `read_canvas_authoring_skill_kandev`.
- **Configuration (`kandev-configuration`, off by default; needs explicit human selection per task):**
  - Workflows: `create_workflow_kandev`, `update_workflow_kandev`, `delete_workflow_kandev`, `import_workflow_kandev`, `export_workflow_kandev`, `create_workflow_step_kandev`, `update_workflow_step_kandev`, `delete_workflow_step_kandev`, `reorder_workflow_steps_kandev`.
  - Agents and profiles: `update_agent_kandev`, `create_agent_profile_kandev`, `update_agent_profile_kandev`, `delete_agent_profile_kandev`, `list_agent_profiles_kandev`, `create_executor_profile_kandev`, `update_executor_profile_kandev`, `delete_executor_profile_kandev`.
  - MCP config and prompts: `get_mcp_config_kandev`, `update_mcp_config_kandev`, `list_shared_prompts_kandev`, `get_shared_prompt_kandev`, `create_shared_prompt_kandev`, `update_shared_prompt_kandev`.
  - Settings and automations: `search_settings_kandev`, `describe_setting_kandev`, `get_settings_kandev`, `update_settings_kandev`, `list_settings_resources_kandev`, `create_automation_kandev`.
- **Rich Output (`kandev-rich-output`, on by default):** `show_rich_output_kandev`.
- **Walkthroughs (`kandev-walkthroughs`, on):** `show_walkthrough_kandev`, `get_walkthrough_kandev`, `delete_walkthrough_kandev`.
- **Diagnostics (`kandev-diagnostics`, on):** `get_diagnostic_bundle_kandev`.
- Package defaults and the rule that "Agents cannot grant these packages to themselves": [docs/public/builtin-mcp-packages.md](https://github.com/kdlbs/kandev/blob/main/docs/public/builtin-mcp-packages.md)
- Other names found in source outside the regular-task catalog:
  - Coordinator/Office/external surfaces: `propose_task_kandev`, `propose_move_kandev`, `propose_message_kandev`, `propose_resume_kandev`, `propose_improvement_kandev`, `get_coordinator_item_kandev`, `list_coordinator_activity_kandev`, `list_coordinator_turns_kandev`.
  - External MCP: `list_pending_questions_kandev`, `answer_question_kandev`, `list_pending_agent_permissions_kandev`, `resolve_agent_permission_kandev`, `report_pr_auto_fix_outcome_kandev`.
  - Location: [apps/backend/internal/mcp/server/coordinator_tools.go](https://github.com/kdlbs/kandev/tree/main/apps/backend/internal/mcp/server), [docs/public/automation-and-mcp.md](https://github.com/kdlbs/kandev/blob/main/docs/public/automation-and-mcp.md)
- **External MCP:** Kandev exposes streamable HTTP and SSE MCP endpoints for agents outside Kandev, with copyable snippets for Claude Code, Cursor, Codex, Auggie, OpenCode, and Copilot CLI. Agents launched inside Kandev get the task MCP automatically, including passthrough agents — [docs/features.md](https://github.com/kdlbs/kandev/blob/main/docs/features.md)
- `ask_user_question_kandev` supports multi-question bundles, `allow_custom_text`, and returns `selected_option`/`selected_label`/`custom_text`/`attachments`. `ask_parent_question_kandev` is non-blocking and must be answered by the direct parent via `message_task_kandev` with `reply_to_question_id` (idempotent) — [docs/public/agent-communication.md](https://github.com/kdlbs/kandev/blob/main/docs/public/agent-communication.md)

**Worktrees, Copy files, branches [doc]**
- "Workspace isolation - Git worktrees prevent concurrent agents from conflicting" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- **Repository copy files (ADR 0010):** "Repository copy-file settings seed files before a new worktree's setup script runs". Paths and globs are comma-separated, e.g. `.env.local, config/{local,dev}.env`. A `:symlink` suffix shares via a relative link on the host (remote executors copy bytes instead). The first matching pattern wins, and existing destinations are skipped — [docs/public/git-operations.md](https://github.com/kdlbs/kandev/blob/main/docs/public/git-operations.md), [docs/decisions/0010-worktree-copy-files.md](https://github.com/kdlbs/kandev/blob/main/docs/decisions/0010-worktree-copy-files.md)
- Configurable worktree branch names (ADR 0032), named branch policies, and multi-branch tasks (ADR 0013). `add_branch_to_task_kandev` creates a sibling worktree for extra PRs from one task — [docs/decisions/](https://github.com/kdlbs/kandev/tree/main/docs/decisions), [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- Multi-repo tasks give one worktree per repo, per-repo branches and PRs, and per-repo grouping in Changes and Review. They are supported on Worktree, Local Docker, SSH, and Sprites. "Local/Local PC creation remains gated"; "Remote Docker is not implemented" — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- "Separate worktrees isolate file state. They do not by themselves isolate host credentials, ports, background processes" — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)

**PR creation and GitHub integration [doc]**
- PR creation runs `git push --set-upstream origin HEAD`, then `gh pr create` (GitHub, draft by default), `glab mr create` or the REST API (GitLab), or `az repos pr create` (Azure) — [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- The GitHub linked-PR panel shows checks, reviews, comments, conflicts, and merge readiness. You can add PR feedback to agent context, approve, ask an agent to fix conflicts, and merge.
- **Auto-fix CI and address comments** polls about once a minute and stops after 10 repair rounds per PR. **Auto-merge when ready** is the other automation control.
- PR events (review requested, PR merged, PR closed) wake the agent.
- Source: [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- `/github` page: search PRs and issues, saved queries, prompt presets, and launch tasks.
  - **Review Watch** polls a GitHub search (default `type:pr state:open review-requested:@me -is:draft`) and creates tasks in a chosen workflow step, with an optional agent/executor override and a 60–3,600 s interval.
  - **Issue Watch** does the same for issues (default `type:issue state:open`, or label filters).
  - Cleanup policies are Auto, Always delete, or Never.
  - Source: [docs/public/integrations.md](https://github.com/kdlbs/kandev/blob/main/docs/public/integrations.md)
- Review watches respect WIP: overflow is queued or placed in a feeder step. "`agent.boot_ready` only makes the session ready; the first real turn completion performs the configured move once" — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- Other integrations: GitLab (MR panel, review and issue watches), Jira, Linear, Sentry, Azure DevOps, Bitbucket (plugin), and Slack (plugin) — [README](https://github.com/kdlbs/kandev/blob/main/README.md), [docs/public/integrations.md](https://github.com/kdlbs/kandev/blob/main/docs/public/integrations.md)
- **Automations:** schedule (cron + timezone), GitHub PR condition, GitHub PR merged, push/CI checks, authenticated webhook (`POST /api/v1/automations/webhook/<id>` with `X-Webhook-Secret` and `X-Kandev-Delivery-ID`), and manual triggers. Destinations are a hidden automation run, a `normal_task` in a workflow start step, or a plugin-managed conversation. Default max concurrency is 1. A finished run parks in `WAITING_FOR_INPUT` — [docs/public/automation-and-mcp.md](https://github.com/kdlbs/kandev/blob/main/docs/public/automation-and-mcp.md)

**Coordinator (experimental) [doc]**
- A workspace "coordinator" (copilot conversation) can be granted **Autonomy** with a USD/24h cost ceiling. It wakes on events (task needs answer, stalled task) and proposes cards, moves, and messages that need manager approval. "Create a card" can be raised to Automatic only after earned-trust conditions: 30 days of history, at least 20 decided cards, at least 90% approved unedited, and so on, with at most 10 automatic approvals per 24 h.
- Containment is required: an isolated executor (Docker/remote Docker/Sprites/K8s), auth on, no Kandev credential in the env, and no extra MCP servers.
- Source: [docs/public/coordinator.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordinator.md)

### Inferences
- Parallel work within one task (sessions) has **no file locking**. Concurrency safety comes from worktree isolation per task or subtask (`new_workspace`), so a multi-agent design that needs concurrent writers should use isolated subtasks.
- The fan-out/join primitive in regular Kanban is: a parent creates N subtasks (each running its own workflow, possibly with different profiles), then `on_children_completed` on the parent's step moves it to a review or integration step. Because terminal includes FAILED, a human or agent check is still needed at the join.
- Sequential multi-agent handoff can be modelled either *within a task* (step-pinned profiles) or *across tasks* (dependency chains with `blocked_by`). Cross-task chains give each stage its own board card, history, and PR.
- The one-level subtask limit in regular Kanban means hierarchies deeper than coordinator → workers need Office (experimental) or flattening into siblings.

### Gaps
- I did not verify exact input schemas for every MCP tool beyond those documented; `automation-and-mcp.md` (about 120 KB) has more detail than captured here.
- There is no documented broadcast or pub-sub channel between agents. Messaging is point-to-point by UUID only.
- The meaning of "resume from the parent task's session" (README) vs the documented context options for subtasks (Blank / Copy initial prompt / Summarize) is unclear. It may refer to the inherited workspace rather than a forked conversation.

---

## Q4. Human-in-the-loop: review, diff comments, approvals, questions, notifications

### Takeaway
Human gates are expressed as workflow steps with no automatic transition ("Do nothing / wait for user"), plus plan review and editing. An integrated diff Review lets you send line, file, and plan comments back to the agent as a message. Agent questions arrive via `ask_user_question_kandev`. PR panels and notifications (Apprise, webhook, push) complete the loop. Formal approvals and reviewer participants exist only in experimental Office.

### Cited Findings
- **Human gate pattern:** "For a human gate, use **On Turn Complete → Do nothing (wait for user)** … `step_complete_kandev` proves only that the agent emitted the configured completion signal." — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- **Plan review:**
  - Agents write the plan via `create_task_plan_kandev`; plan mode is on in the Plan or Spec steps.
  - Humans edit the plan in the Plan panel (autosaved, with revision history and restore).
  - Selecting plan text adds comments. **Send** includes them in a message, and **Run** sends one comment in plan mode to the primary session.
  - **Implement** or **Implement in fresh agent** starts implementation.
  - Optimistic concurrency: `expected_version`, a truncation guard, and append mode.
  - Source: [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md)
- **Diff review:**
  - Review merges uncommitted, cumulative committed, and linked-PR files.
  - Unified/split diffs, marking files reviewed (stored per session with a diff hash, so files go stale on change), discard or revert hunks.
  - Line and whole-file comments. **Fix comments** sends the accumulated file, line, and comment context to the agent; if the agent is busy, normal queueing applies.
  - Pending comments live in the browser's `sessionStorage` only and are not synced to the backend.
  - Source: [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- **Walkthroughs:** the agent publishes ordered file/line anchors via `show_walkthrough_kandev`, and the human comments per step and **Run**s feedback to the agent — [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- **Clarification questions:** answered from a question panel. If a question becomes inactive, use "Answer as new message". A pending clarification blocks `on_turn_complete` — [docs/public/tasks-and-workflows.md](https://github.com/kdlbs/kandev/blob/main/docs/public/tasks-and-workflows.md), [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- **External answering:** via external MCP `answer_question_kandev` and `resolve_agent_permission_kandev` — [docs/public/automation-and-mcp.md](https://github.com/kdlbs/kandev/blob/main/docs/public/automation-and-mcp.md)
- **Notifications:** providers are Apprise and webhook (POST with a versioned JSON body, events like `session.turn_finished`), configured in Settings → Preferences → Notifications. Mobile push notifications and desktop notifications are also documented — [docs/public/developer-tools.md](https://github.com/kdlbs/kandev/blob/main/docs/public/developer-tools.md), [docs/public/mobile-remote-access.md](https://github.com/kdlbs/kandev/blob/main/docs/public/mobile-remote-access.md)
- **Completion checklist** (doc guidance): "Keep required human approval outside the agent loop." — [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- **Office approvals:** `stage_type: approval`, step participants (reviewers/approvers), and recorded decisions exist but "are **not** exported or imported" and are experimental — [docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md)

### Inferences
- In regular Kanban, "approval" means a human moving the card (or sending a message that triggers `on_turn_start`). There is no first-class approve/reject record or quorum. A redesign that needs auditable approvals should either use Office (unstable) or treat step history (`GET /sessions/:id/workflow/history`, which records signal source, summary, and blockers) as the audit trail.
- Diff comments are not persisted server-side, so they cannot serve as durable inter-agent review artifacts. Use `publish_review_findings_kandev`, task documents, or the plan for durable review output.

### Gaps
- I did not inspect the `publish_review_findings_kandev` schema or how native `run_code_review` results surface in the UI.
- The full notification event list was not enumerated.

---

## Q5. Configuration format, storage, export/import, GitOps sync

### Takeaway
Workflows are authored in the UI and stored in the database (SQLite or Postgres). They can be exported and imported as portable YAML (`type: kandev_workflow`, `version` 1/2/3) through HTTP endpoints, the UI, or Configuration-package MCP tools. They can also be GitOps-synced read-only from a GitHub/GitLab directory (default `.kandev/workflows`). The built-in templates use a different internal YAML schema with string `step_id`s.

### Cited Findings
- **Storage:** the DB is SQLite by default at `<home>/data/kandev.db`, or PostgreSQL. Data lives under `~/.kandev` — [docs/public/configuration.md](https://github.com/kdlbs/kandev/blob/main/docs/public/configuration.md), [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- **Endpoints:**
  - `GET /api/v1/workflows/:id/export`
  - `GET /api/v1/workspaces/:id/workflows/export`
  - `POST /api/v1/workspaces/:id/workflows/import` (YAML body, max 1 MB)
  - Source: [docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md)
- v0.99.0 added "download workflow exports" (#4925) — [v0.99.0 release](https://github.com/kdlbs/kandev/releases/tag/v0.99.0)
- **Envelope:** `version`, `type: kandev_workflow`, `workflows: [...]`.
  - Code constants: `LegacyExportVersion = 1`, `ExportVersion = 2` (adds `session_target` and explicit `complete_task_on_enter`), `ProfileOptionsExportVersion = 3` (adds agent profile `config_options`). The exporter picks the lowest version that fits — [apps/backend/internal/workflow/models/export.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/export.go)
  - The public doc agrees ("Must be `1`, `2`, or `3`") — [docs/public/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md)
  - The older root doc wrongly says the version "Must be exactly `1`" — [docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md)
- **Portable workflow fields:** `name`, `description`, `prompt`, `agent_profile`, `steps`.
- **Portable step fields [code]:** `name`, `position`, `color`, `prompt`, `events`, `is_start_step`, `show_in_command_panel`, `allow_manual_move`, `auto_archive_after_hours`, `agent_profile`, `profile_session_start_policy`, `profile_session_end_policy`, `disable_unclassified_fallback`, `auto_advance_requires_signal`, `cancel_triggers_turn_complete`, `complete_task_on_enter`, `wip_limit`, `pull_from_step_position`, `stage_type`, `session_target` (`{kind, step_position}`) — [export.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/export.go)
- **Import rules:**
  - The whole document is validated first.
  - Dedup is by workflow name: existing names are skipped, and the result is `{created, skipped}`.
  - Fresh step UUIDs are generated, and `move_to_step` uses `step_position`, which is remapped to the new IDs.
  - Agent profiles are matched by exact display name, model, and mode (plus `config_options` in v3). If nothing matches, the profile is silently left empty.
  - Office metadata (participants, decisions) is not portable.
  - Source: [docs/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-import-export.md), [docs/public/workflow-import-export.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-import-export.md)
- **`run_code_review` review agent profile:** stored portably under the action's `config.agent_profile` (`ReviewAgentProfilePortableKey = "agent_profile"`) [code] — [export.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/workflow/models/export.go)
- **Template YAML vs portable YAML:** templates in `apps/backend/config/workflows/*.yml` use `id`/`step_id` references ("Internal workflow TEMPLATE definition — NOT the portable import/export format") — [kanban.yml](https://github.com/kdlbs/kandev/blob/main/apps/backend/config/workflows/kanban.yml)
- **Workflow Sync:**
  - One config per workspace, using GitHub or GitLab. Fields: `branch` (default `main`), `path` (default `.kandev/workflows`), and `interval_seconds` (60 to 2,592,000; default 300).
  - Sync reads immediate `.yml`/`.yaml`/`.json` files.
  - Workflows are keyed by `(source_path, name)` and steps are matched by name, so tasks stay attached.
  - Renaming a step equals delete plus create. If the old step has tasks, the whole workflow update is skipped with a warning.
  - Synced workflows are read-only in the UI.
  - Source: [docs/public/workflow-sync.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-sync.md)
- **MCP config tools:** `create_workflow_kandev`, `update_workflow_step_kandev`, `import_workflow_kandev`, `export_workflow_kandev`, and others are in the Configuration package, which is off by default and needs explicit human selection — [builtin_catalog.go](https://github.com/kdlbs/kandev/blob/main/apps/backend/internal/mcp/profile/builtin_catalog.go), [docs/public/builtin-mcp-packages.md](https://github.com/kdlbs/kandev/blob/main/docs/public/builtin-mcp-packages.md)
- **Duplicate workflow:** copies prompts, transitions, profiles, session policies, WIP, and pull-from. It does not copy tasks or sync ownership — [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)
- **App config:** YAML keys and `KANDEV_*` env vars (e.g. `KANDEV_MAX_CONCURRENT_SESSIONS`, `KANDEV_QUEUE_MAX_PER_SESSION`) — [docs/public/configuration.md](https://github.com/kdlbs/kandev/blob/main/docs/public/configuration.md)

### Inferences
- The most reproducible way to deliver a redesigned multi-agent workflow is a portable YAML file. Use version 2 if you need `session_target`, or version 3 for profile options. Commit it to `.kandev/workflows` in a repo and enable Workflow Sync. Make sure agent profile display names, models, and modes exist identically in the target workspace, because mismatches are silently dropped.

### Gaps
- I did not verify whether the per-step "session option rules" (model overrides within one session) are part of the portable format. The portable struct shown does not include them, and the docs note "Synced workflows show the rules but cannot edit them".

---

## Q6. Known limitations, open issues, roadmap items relevant to multi-agent orchestration

### Takeaway
The main constraints:
- One task occupies one step at a time; there are no branching lanes.
- Regular Kanban allows only one level of subtasks.
- Sessions sharing a workspace have no write isolation.
- Auto-advance on bare turn-end is unreliable unless the explicit signal is enabled.
- Office (deep trees, approvals, persistent agent teams) is experimental.
- Many open bugs concern session lifecycle, step prompt delivery, and coordinator behavior.

### Cited Findings
- One subtask level in regular Kanban; deeper trees are "in-progress Office" — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- "Two sessions can edit the same files concurrently; assign files or phases explicitly." — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- The subtask dialog does not enforce agent/executor credential compatibility, and multi-repo is not available on Local/Local PC or Remote Docker — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- Office is feature-flagged and disabled in production by default. Its "dependency editor, persistent coordinators, deeper task trees, quorum rules, and routines are not stable regular-Kanban features." — [docs/public/coordination.md](https://github.com/kdlbs/kandev/blob/main/docs/public/coordination.md)
- Task IDs act as routing credentials: "A full task UUID is sufficient for cross-workspace messaging, so treat task IDs as sensitive" — [docs/public/sessions-and-review.md](https://github.com/kdlbs/kandev/blob/main/docs/public/sessions-and-review.md)
- Open issues relevant to multi-agent workflows (titles from `gh issue list`, 2026-11-08) — [Issues](https://github.com/kdlbs/kandev/issues):
  - #4378 "A decision step that routes a task into workflow lanes with a decision model"
  - #4566 "Task relationship graph (dependency order, subtasks, parallel steps)"
  - #3340 "Allow executing deterministic shell scripts in workflow step triggers (on_enter, worktree creation)"
  - #4481 "Require current explicit PASS before automatic Review and QA advancement"
  - #3336 "Step prompt is silently ignored on workflow transitions unless on_enter: auto_start_agent is explicitly configured"
  - #5137 "'Start fresh session' after a failed agent startup drops the workflow step prompt"
  - #5173 "Step completion already_signaled can strand latest correction in Build"
  - #5178 "start_created can discard explicit prompt and launch step instructions"
  - #5086 "Message queue Auto-sort-merge for interleaved sub-task messages"
  - #4117 "Queued messages stay bound to a demoted session when the task's primary session changes"
  - #4152 "Simultaneous auto-starts fail ACP init…"
  - #4526 "External MCP: no way to send a follow-up to, or stop, a task an external client started"
  - #4606 "Make omitted workspace_mode resolve the same way on HTTP and MCP subtask creation"
  - #4829 "Let Coordinators maintain in-scope task dependencies"
  - #4330 "Organization-scoped coordinator: one management chat across workspaces"
  - #4654 "Attach a saved layout to a workflow step"
  - #3812 "Sandbox providers for Local/Worktree executors … with per-step/task profile selection"
  - #879 "Declarative config: workflows, prompts, and rules as versioned IaC"
- Recent v0.99.0 changes touching orchestration: "add ACP schema 1.28 session and subagent support" (#4983), "preserve source bindings for spawned sessions" (#5048), "bound message turns by session capacity" (#4998), "decide hold steps by stored nature, not name" (#4938), "add task priority controls to MCP" (#4811), "expose executor discovery to task MCP" (#4708) — [v0.99.0 release](https://github.com/kdlbs/kandev/releases/tag/v0.99.0)
- Docs drift: the root `docs/workflow-tips.md` and `docs/workflow-import-export.md` disagree with `docs/public/*` and the code. Examples are the PR Review finding categories, Feature Dev context resets, export version, and the session end-policy default (see Q2 and Q5) — [docs/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/workflow-tips.md), [docs/public/workflow-tips.md](https://github.com/kdlbs/kandev/blob/main/docs/public/workflow-tips.md)

### Inferences
- A robust multi-agent design on Kandev today should:
  - prefer task or subtask boundaries with isolated worktrees over shared-workspace sessions for concurrent writers;
  - always pair `on_enter: auto_start_agent` with a step prompt (because of #3336);
  - use `auto_advance_requires_signal` together with a human or review gate rather than bare auto-advance;
  - keep critical approvals as manual steps;
  - expect behavior changes between minor versions.

### Gaps
- I did not review closed issues or discussions for resolved multi-agent limitations, or measure how stable these features are in practice.
- No HN thread was found. Reddit coverage is thin and secondary.

---

## Q7. Brief comparison with similar tools (only where it clarifies Kandev's model)

### Takeaway
Kandev's differentiators are server-first deployment, multi-provider agents, and multiple remote executors. Its main conceptual difference from per-task-worktree kanban tools such as Vibe Kanban is the **per-step workflow engine**: event triggers, step-pinned agent profiles, session reuse/park policies, explicit completion signals, and WIP/pull. It also has first-class agent-to-agent MCP messaging, subtasks, and dependencies.

### Cited Findings
- Kandev's self-described differentiators: "Server-first architecture… Remote runtimes… Multi-provider… CLI passthrough and chat… Open source and self-hostable" — [README](https://github.com/kdlbs/kandev/blob/main/README.md)
- Vibe Kanban (BloopAI) also creates a git worktree per task, exposes a local MCP server (`npx vibe-kanban --mcp`) and creates PRs per card. One directory reports that Bloop wound down Vibe Kanban Cloud in April 2026, while the self-hosted OSS continues (third-party sources; not verified against the official repo) — [web search summary](https://github.com/BloopAI/vibe-kanban), [VirtusLab blog](https://virtuslab.com/blog/ai/vibe-kanban/)

### Inferences
- From general knowledge, not verified in this session: Claude Squad (tmux TUI), Conductor (Mac app), and Crystal (desktop app) focus on running several CLI-agent sessions in parallel worktrees without a multi-step workflow engine. Sculptor emphasizes containerized agents, and Terragon is a cloud background-agent service. Kandev's step/event model and MCP coordination layer are what set it apart for designed multi-agent pipelines. Verify before citing.

### Gaps
- I did not fetch primary sources for Conductor, Claude Squad, Crystal, Sculptor, or Terragon in this session, so their late-2026 feature sets and status are unverified.
