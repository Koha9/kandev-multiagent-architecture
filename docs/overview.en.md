# Multi-agent development workflow: overview

[中文（完整版）](workflow.md) | **English overview**

This page is an English summary of [workflow.md](workflow.md) sections 1–6: the principles, the overall structure, roles, run modes and the three step tables. Everything else (context and recovery, concurrency, branches, platform limits, rejected designs, prompts, templates) is maintained in Chinese only; the list at the end says where. The Kandev workflows and steps have Chinese names, so each step is given with its Chinese name.

## Principles

1. **Single writer.** One agent writes a given file at a time. Parallelism only happens between independent tasks, each in its own worktree.
2. **Tests are the judge.** Every task has a machine-checkable done condition (tests, lint, build). An agent's opinion of its own work does not count.
3. **Verifiers start clean.** Review, plan review, module acceptance and project acceptance each use a different profile and a fresh session, and look only at the deliverable and the criteria. Verifiers do not set the criteria; they apply the ones written by the level above and write each failure as a fix item that can be dispatched as is.
4. **State lives in files; sessions are disposable.** Any session can be reset at any time and resumes from the management directory and the task documents.
5. **Managers do not write code.** Project and module management plan, delegate and record. Even the environment and the skeleton are built by development tasks, in the baseline module.
6. **Every loop has a cap.** Send-backs, review rounds and message rounds have hard limits; beyond them the matter goes one level up or to a person.
7. **Gates are inside the workflow.** In unattended runs an independent review step replaces the human gate; nothing waits for an external poller.
8. **Side effects are off by default.** Anything that spends quota or touches the outside world needs an explicit switch.
9. **Verbatim requirements all the way through.** Each requirement is copied as R-n and never reworded; every acceptance criterion says which R it covers. How to implement is left to the level below.
10. **Constraints that code can enforce are not left to prompts alone.** When code blocks an agent, it stops and reports instead of working around it.
11. **Honest conclusions.** Acceptance results are only pass, fail or unverified (with a reason). Everything the user has to handle is collected in one place, each item with a recommended answer.
12. **Hard boundaries, loose methods.** Boundaries say what may be changed, not how. Prompts state boundaries, deliverables and done conditions; planning and design are left to the agent.
13. **Split along knowledge boundaries.** Each layer holds only its own knowledge. Long-running sessions only route; investigation, acceptance and coding happen in one-off sessions that write their results to files.

## Overall structure

```
Project management task (W1, the root task, 1)
 ├─ creates → module management tasks (W2, separate tasks; baseline first, the others blocked_by baseline, in parallel)
 │             └─ subtasks → development tasks (W3, own worktree, base_branch = mod/<module>)
 └─ Guard (a Kandev automation; read-only patrol every 20 minutes, alerts the manager concerned)
```

| Layer | Knows | Does not touch |
|---|---|---|
| Project (pm) | Verbatim requirements, product intent, module list, module boundaries (B-n), project acceptance criteria, decisions | Module internals, task details, code |
| Module (module agent) | Its own spec, interfaces, tasks and code | Other modules' internals (public interfaces only) |
| Task (developer) | One self-contained contract and its own `owns` paths | Other tasks |

- **Baseline module.** The first module is always `baseline`. It goes through the normal W2 + W3 and delivers the environment, smoke test, check scripts, shared skeleton and explicit switches, so these are reviewed and accepted like any other code. Every other module depends on it and branches from `mod/baseline` (or from the module it depends on).
- **Integration-test module** (unless `integration_test: off`). The last module, `integration-test`, depends on all the others. When they finish it merges every module branch into the integration branch and writes and runs automated tests against the assembled product. Defects go through the pm to a fix task owned by the responsible module.
- **Fixes.** Verifiers grade what they find: only blocking problems are a fail and produce a fix module; minor ones are recorded as known issues, and flaky tests as test defects, both left for the user at final review. Fix rounds are counted per project and capped at 2. Merge conflicts outside the declared shared files are also fix items, not resolved on the spot.
- **Size tiers.** The plan picks a size (small, medium, large), which caps the number of feature modules (2 for small, 5 for medium).
- **What the user watches.** `project/attention.md` (decisions needed, each with a recommended answer) and `agents/guard/stage.md` (who the system is waiting on).

### Roles and profiles

Each role is bound to a Kandev agent profile. Five are required; the rest fall back to the default shown. Pairs that must differ: pm ≠ auditor, pm ≠ plan_auditor, module ≠ module_auditor, developer ≠ reviewer.

| Role | Used in | Model advice | Session |
|---|---|---|---|
| `intake` (optional, = mechanical) | W1 Intake | A light model is enough | New each time |
| `pm` | W1 planning, dispatch, scheduling, refresh | Strong model | Long-lived; context reset on entering scheduling |
| `plan_auditor` (optional, = auditor) | W1 plan review | Small context, largest impact: the strongest model | New each time |
| `auditor` | W1 project acceptance | Strong model | New each time |
| `module` (optional, = pm) | W2 planning, waiting, refresh | Strong model | One per module; context reset on entering waiting |
| `module_auditor` (optional, = auditor) | W2 acceptance | Strong model | New each time |
| `developer` | W3 development | Main coding model | One per task, reused when sent back |
| `reviewer` | W3 review | Ideally another vendor | New each time |
| `mechanical` | W3 merge gate, W1 final merge | Coding model | New each time |
| Guard | Kandev automation; decisions are made by `kandev/stage.py` | Cheap model | New each run |

## Run modes

The `[TASK v1]` header of the pm task sets `mode: attended | unattended`; module and development tasks inherit it.

| | attended (default) | unattended |
|---|---|---|
| Plan approval | Waits for the user after plan review passes | Goes straight on to module dispatch |
| Questions to the user | Allowed, batched, each with a recommended answer | None. The agent decides, writes an ADR and lists it in `project/attention.md` |
| Environment needs user setup | The baseline module escalates to the pm, who asks the user | Choose an approach that needs no user setup; the pm writes an ADR |
| Final human review | The user | The user (when they come back) |

`plan_only: true` always stops at plan approval, whatever the mode, so the user can read the plan before spending development quota. `integration_test: auto | off` (default auto) controls whether the integration-test module is added.

## W1 Project management

| # | Step | Role | What happens | Next |
|---|---|---|---|---|
| 0 | Intake（接收） | intake | Entry. A complete `[TASK v1]` header passes unchanged; otherwise derive what can be derived, ask the user for the rest and rewrite the task description | Completion signal → 1 |
| 1 | Planning（立项规划） | pm | Initialize the management directory; write the charter (requirements R-n, module list, module boundaries B-n, project acceptance criteria), conventions, ADRs. No code | Completion signal → 2 |
| 2 | Plan review（立项评审） | plan_auditor | Independent review of the charter with a requirement coverage table | Send back to 1 (at most twice); pass → 3 when attended or plan_only, → 4 when unattended |
| 3 | Plan approval（立项确认） | pm + human | Gate: the pm asks the user to approve or send back | Approve → 4; send back → 1; decide later → stays (dragging to 4 also approves) |
| 4 | Module dispatch（模块下发） | pm | Create the modules not yet created (baseline first, integration-test last), then dispatch pending fix items and final-review notes as fix modules | Completion signal → 5 |
| 5 | Scheduling（调度） | pm | Long-running, routing only: reports, escalations, questions, alerts | When all modules are done the agent moves itself to 6 |
| 6 | Project acceptance（项目验收） | auditor | Merge all module branches into the integration branch, run all tests, check every acceptance criterion and every R, write the final report | No fail (or still failing the third time) → 7; fail → 4 |
| 7 | Final human review（人工终审） | pm + human | Gate: the pm asks the user to approve or send back, plus the open items from the final report | Approve → 8; send back → 4; decide later → stays (dragging to 8 also approves) |
| 8 | Final merge（收尾合并） | mechanical | Merge the integration branch into the base branch, run the smoke test, clean up | Completion signal → 10 |
| 9 | Refresh（刷新） | pm | Reset the context, then move back to the step it came from | The agent moves itself |
| 10 | Done（完成） | — | Task completed. Must be the last step | — |

## W2 Module management

| # | Step | Role | What happens | Next |
|---|---|---|---|---|
| 0 | Module planning（模块规划） | module | Write spec, interfaces and tasks.json; create development subtasks with self-contained contracts | Completion signal → 1 |
| 1 | Waiting for development（等待开发） | module | Long-running, routing only: answer subtask questions, handle tasks waiting for a decision, release held tasks whose prerequisites are merged, create fix subtasks | All subtasks finished → 2 |
| 2 | Acceptance（验收调查） | module_auditor | Independent module verifier: coverage check, run the module tests, judge each module acceptance criterion, write fix items | Pass → report to the pm, 4; fail → 1 |
| 3 | Refresh（刷新） | module | Reset the context, then move back | The agent moves itself |
| 4 | Done（完成） | — | Module completed; modules that depend on it start. Must be the last step | — |

## W3 Development

| # | Step | Role | What happens | Next |
|---|---|---|---|---|
| 0 | Held（待开发） | — | Parks subtasks that have prerequisites; no session, not counted in WIP | The module agent moves it to 1 once the prerequisites are merged |
| 1 | Development（开发） | developer | Smoke test → implement the contract → tests and `owns` check → report → commit | Completion signal → 2; blocked or dropped → escalate and move to 3 |
| 2 | Review（审核） | reviewer | Rerun the tests as-is; write personally checked evidence for each acceptance criterion; spot-check an edge case | Pass → 4; minor → 1 (at most 3 rounds); wrong direction → 3 |
| 3 | Waiting for a decision（等待决策） | — | Not counted in WIP; waits for the module agent | Back to 1 with instructions, or to 5 |
| 4 | Merge（合并） | mechanical | Merge gate: rebase onto the module branch, run the gate commands, fast-forward into the module branch, report to the module agent | Merged → 5; gate failure → 1 |
| 5 | Done（完成） | — | | |

The development step has a global WIP limit shared by all modules (4 as shipped).

## Install, customize, upgrade

`kandev/ma.py install` records four answers (quick or custom setup, workspace, a profile for each role, whether to create the guard) and, by default, copies everything needed at run time into an install directory (`~/.kandev-ma/<first 8 characters of the workspace id>/`), so a deployment keeps working after the source repository is moved or deleted. `ma.py apply` deploys the three workflows and `ma.py doctor` checks the result. Rules (workspace, testing, quality, git, coding) and numeric parameters (development WIP, refresh threshold, guard thresholds) are customized by placing overrides in `custom/rules/` inside the install directory and deploying again. `ma.py upgrade` updates an install directory from a newer source repository and keeps the files you changed. The easiest route is to hand the prompts in [README.en.md](../README.en.md) to an agent.

## Where the rest is (Chinese)

| Topic | File |
|---|---|
| Full design, including context and recovery, concurrency, branches, platform limits, rejected designs | [workflow.md](workflow.md) |
| Diagrams | [workflow-diagrams.md](workflow-diagrams.md) |
| Launch parameters (`[TASK v1]` header) | [intake.md](intake.md) |
| Deployment commands | [../kandev/README.md](../kandev/README.md) |
| Rule slots and parameters | [../rules/README.md](../rules/README.md) |
| Management directory | [mgmt-workspace.md](mgmt-workspace.md), [../mgmt-template/README.md](../mgmt-template/README.md) |
| Conventions for the project being built | [project-conventions.md](project-conventions.md) |
| Version history | [../CHANGELOG.md](../CHANGELOG.md) |
| Agent entry point | [../AGENTS.md](../AGENTS.md) |
