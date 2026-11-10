# Workflow v3.1 Diagrams

[中文](workflow-diagrams.md) | **English**

> Companion to [workflow.en.md](workflow.en.md). The diagrams are written in Mermaid and render directly in VS Code (Markdown Preview Mermaid extension), GitHub and Typora; you can also open `workflow-diagrams.html` in a browser.

---

## Diagram 1: Overall view (entries / loops / exits)

```mermaid
flowchart TD
  START(["Entry: the user creates a pm task<br/>[TASK v1]: mode = attended / unattended, plan_only"])

  subgraph W1["W1 Project management (1 task)"]
    P1["Project planning (立项规划)<br/>charter: verbatim requirements R-n + modules + PA + ADR"]
    PR["Plan review (立项评审, independent session)<br/>requirement coverage table → charter-review"]
    PRC{"Review verdict"}
    P2{"Plan approval (立项确认)<br/>(attended or plan_only)"}
    P3["Environment baseline (环境基线)<br/>skeleton / smoke / check scripts / quota switches<br/>constraint list: no push / owns check / quota ledger"]
    P3C{"Smoke tests pass?"}
    P4["Module dispatch (模块下发)<br/>create_task × N"]
    P5["Coordination (调度, long-running)<br/>each report = one turn"]
    P5C{"All modules done?"}
    P6["Project acceptance (项目验收, independent session)<br/>integration + full verification + check each R"]
    P6C{"Any fail?"}
    P7{"Final human review (人工终审)"}
    PF["Final merge (收尾合并, mechanical)<br/>integration → baseline / smoke / cleanup"]
    PFC{"Merge + smoke pass?"}
    REF1["Refresh (刷新, relay)<br/>reset context, then move back"]
  end

  subgraph W2["W2 Module management (1 per module, can run in parallel)"]
    M1["Module planning (模块规划)<br/>spec / interfaces / tasks.json<br/>create_task development subtasks"]
    M2["Waiting on development (等待开发, long-running)<br/>answer questions / handle escalations / local merge<br/>release Queued / confirm dropped"]
    M3["Acceptance check (验收调查, reset context)<br/>check FAILED subtasks first"]
    M3C{"Module acceptance passes?"}
    REF2["Refresh (刷新, relay)"]
  end

  subgraph W3["W3 Development (own worktree per subtask, Develop WIP 4)"]
    D0["Queued (待开发, no WIP)<br/>tasks with prerequisites wait here"]
    D1["Develop (开发)<br/>smoke → implement → tests + owns check → report"]
    R1["Review (审核, new session, different profile)<br/>re-run as-is + evidence per AC + edge spot-check"]
    R1C{"Review verdict"}
    D3["Awaiting decision (等待决策)"]
    D4["Merge (合并) into module branch"]
  end

  FIN(["Normal exit: integration branch merged into baseline, project done"])
  ESC(["Exception exit: stop and hand to a human<br/>cap exceeded / no decision possible / final merge failed"])
  GUARD["Guard (Kandev automation)<br/>runs stage.py every 20 minutes<br/>→ stage.md + ALERT"]

  START --> P1 --> PR --> PRC
  PRC -->|"blocking issues (send back ≤2 times)"| P1
  PRC -->|"pass · unattended"| P3
  PRC -->|"pass · attended / plan_only"| P2
  P2 -->|"send message: with comments"| P1
  P2 -->|"drag to Environment baseline = approve"| P3
  P3 --> P3C
  P3C -->|"no (≤3 times)"| P3
  P3C -->|"yes"| P4
  P4 -->|"each module"| M1
  P4 --> P5

  M1 -->|"subtasks without prerequisites"| D1
  M1 -->|"subtasks with prerequisites"| D0
  M1 --> M2
  M2 -.->|"prerequisites merged: release"| D0
  D0 --> D1
  D1 -.->|"dropped / blocked: ESCALATE"| M2
  D1 -->|"step_complete + handoff"| R1 --> R1C
  R1C -->|"minor (≤3 rounds)"| D1
  R1C -->|"direction / round 3"| D3
  R1C -->|"pass"| D4
  D3 -.->|"ESCALATE"| M2
  M2 -.->|"send back after contract change / split"| D1
  D4 -->|"on_children_completed"| M3
  M3 --> M3C
  M3C -->|"no: fix subtasks"| M2
  M3C -.->|"yes: REPORT"| P5

  P5 --> P5C
  P5C -->|"no: keep waiting"| P5
  P5C -->|"yes"| P6 --> P6C
  P6C -->|"yes: to fix"| P4
  P6C -->|"no (unverified listed under needs user action)"| P7
  P7 -->|"send message: with comments"| P4
  P7 -->|"drag to Final merge = approve"| PF --> PFC
  PFC -->|"yes"| FIN
  PFC -->|"no: stop and explain"| ESC

  P5 -.->|"session too long"| REF1 -.->|"move back"| P5
  M2 -.->|"session too long"| REF2 -.->|"move back / all subtasks terminal → acceptance"| M2
  M2 -.->|"cross-module / cap exceeded"| P5
  P5 -.->|"no decision possible"| ESC
  GUARD -.->|"ALERT"| M2
  GUARD -.->|"ALERT"| P5

  classDef entry fill:#d1fae5,stroke:#059669,stroke-width:2px,color:#064e3b
  classDef exit fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a
  classDef exc fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d
  classDef loop fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f
  classDef gate fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#4c1d95
  classDef aux fill:#f3f4f6,stroke:#6b7280,stroke-dasharray:4 3,color:#111827
  class START entry
  class FIN exit
  class ESC exc
  class PRC,P3C,R1C,M3C,P5C,P6C,PFC loop
  class P2,P7 gate
  class GUARD,REF1,REF2,D0 aux
```

Legend: 🟩 entry　🟦 normal exit　🟥 exception exit　🟨 loop decision point　🟪 human gate　⬜ auxiliary (guard / refresh)　dashed line = message, notification or relay

### Entries

| Entry | Trigger | Where it lands |
|---|---|---|
| Project entry | The user creates a pm task (Start task; or leave it in Not started (「待立项」) and start it later by sending a message) | W1 Project planning (立项规划) |
| Module entry | The pm calls `create_task_kandev`; with dependencies, `blocked_by` unblocks it automatically once the prerequisite module is done | W2 Module planning (模块规划) |
| Subtask entry | The module agent calls `create_task_kandev` (autopilot, `base_branch=mod/<module>`); tasks with prerequisites are created in Queued (「待开发」) with `start_agent=false` | W3 Develop (开发) / Queued (待开发) |
| (Optional) external entry | GitHub Issue Watch imports issues as tasks | W1 or W2 |

### Loops

| # | Loop | Returns to | Ends when | Cap, and where it goes beyond the cap |
|---|---|---|---|---|
| L1 | Project planning ↔ Plan review | Project planning | Review passes | After 2 send-backs, the 3rd time only records non-blocking issues and passes |
| L2 | Plan approval (attended) | Project planning | The user approves | Up to the user |
| L3 | Environment baseline self-fix | Environment baseline | Smoke tests pass | 3 times → attended: hand to the user; unattended: write an ADR and stop |
| L4 | Develop ↔ Review | Develop (same session) | pass | Round 3 → Awaiting decision |
| L5 | Handling direction issues | Develop (contract changed) or a new subtask | The module agent decides | Cross-module → pm |
| L6 | Module acceptance ↔ fix subtasks | Waiting on development | Module acceptance passes | 3rd time → escalate to pm |
| L7 | Coordination wait | Coordination (one turn per report) | All modules done | Session too long → Refresh |
| L8 | Project acceptance / final-review comments ↔ fixes | Module dispatch | The user approves | Up to the user |
| L9 | Session refresh | Refresh step → original step | State written to NOW | Still too long after refresh → split the task or module |

### Exits

| Exit | Condition | Result |
|---|---|---|
| Normal exit | In Final human review the user drags the task to Final merge (「收尾合并」), and both the merge and the smoke tests pass | Integration branch merged into baseline, temporary resources cleaned up, task done |
| Subtask exit | Review passes and it is merged into the module branch | Subtask ends; when all have ended, `on_children_completed` fires |
| Module exit | Module acceptance passes and has been reported | Module task ends; modules depending on it are unblocked |
| Exception exit | Loop cap exceeded, management cannot decide, conflict or smoke failure during Final merge | Stops at the current step with an explanation, waiting for a human |
| Abandoned exit | Task too large or in the wrong direction, stopped with `stop_task_kandev` | Marked `failed` in `tasks.json`, replaced by new subtasks split from it |

---

## Diagram 2: Agent view (lifecycle + allowed interactions)

Shown as a sequence diagram: each column is an agent. **Vertical activation bar = the lifetime of that agent's session (lifecycle)**; arrows = **allowed** interactions (labeled with the tool used). Any interaction not drawn in the diagram is not allowed.
`loop` means a loop, `alt` a branch, `opt` an optional part; the gray block is what the guard may trigger at any time.

```mermaid
sequenceDiagram
  actor U as 👤 User
  participant PM as Project manager agent

  U->>+PM: Create pm task (mode = attended / unattended) [entry]
  Note over PM: Project planning (立项规划)
  create participant AU as Independent auditor agent (new session each time)
  PM->>AU: step_complete → Plan review (立项评审)
  activate AU
  alt Blocking issues (send back ≤2 times)
    AU-->>PM: move_task back to Project planning (with issue list)
  else Pass · unattended
    AU-->>PM: move_task → Environment baseline (in place of human approval)
  else Pass · attended
    AU->>U: step_complete → Plan approval (立项确认, human gate)
    U-->>PM: Drag to Environment baseline = approve, send message = back to Project planning with comments
  end
  deactivate AU
  Note over PM: Environment baseline → Module dispatch

  create participant MM as Module manager / acceptance agent
  PM->>MM: create_task (starts automatically once prerequisite modules are done)
  activate MM
  Note over MM: Module planning: write spec / interfaces / tasks.json

  create participant D as Developer agent
  MM->>D: create_task (autopilot, base_branch=mod/module)
  activate D
  Note over MM: Waiting on development (long-running)

  opt Developer has a question
    D->>MM: ask_parent_question
    MM-->>D: message reply (reply_to_question_id)
  end

  loop Develop ↔ Review, at most 3 rounds
    create participant R as Reviewer agent (new session each time)
    D->>R: step_complete + handoff (report)
    activate R
    Note over R: Re-run tests as-is, evidence per AC, edge spot-check
    alt minor
      R-->>D: move_task back (with notes), developer keeps the same session
    else direction / round 3
      R->>MM: KMSG ESCALATE
      Note over D: Awaiting decision
      MM-->>D: move_task back after changing the contract, or stop_task and split
    else pass
      R-->>D: step_complete → merge into module branch
    end
    deactivate R
  end
  deactivate D
  Note over D: Subtask ended (can still be woken by a question)
  D-->>MM: All subtasks ended → on_children_completed

  rect rgb(243, 244, 246)
    participant G as Guard (Kandev automation)
    G->>MM: KMSG ALERT (read-only patrol: session too long / stuck)
    MM-->>D: INSTRUCT write a checkpoint then reopen with reset_context, or split
    G->>PM: KMSG ALERT (Coordination session too long)
    PM->>PM: Write 「刷新返回」 → move to Refresh → reset, then move back to Coordination
  end

  Note over MM: Acceptance check (reset context): check FAILED subtasks first
  opt Deliverable (report / review) unclear: ask its owner
    MM->>D: KMSG QUESTION (at most 2 rounds, no digging through conversations or code)
    D-->>MM: KMSG ANSWER (answer only, no changes)
  end
  alt Module acceptance fails (before the 3rd entry)
    MM->>MM: Create fix subtasks, back to Waiting on development
  else Cross-module issue / cap exceeded
    MM->>PM: KMSG ESCALATE
    PM-->>MM: KMSG DECISION (ADR)
  end
  MM->>PM: KMSG REPORT (module report)
  deactivate MM

  Note over PM: Coordination: all modules done
  PM->>AU: move_task → Project acceptance (new session)
  activate AU
  alt All PAs pass
    AU->>U: step_complete → Final human review (final-report states how to run it)
  else Any fail
    AU-->>PM: move_task back to Module dispatch (create fix tasks)
  end
  deactivate AU
  alt User approves
    U->>PM: Drag to Final merge (收尾合并)
    Note over PM: Final merge (mechanical): integration → baseline, smoke, cleanup [normal exit]
  else User has comments
    U->>PM: Send message → back to Module dispatch with comments
  end
  deactivate PM
```

### Agent lifecycles at a glance

| Agent | Created by | Session lifetime | When the session is reopened | When it ends |
|---|---|---|---|---|
| Project manager | The user | Long-lived (whole project) | Reset via the Refresh (「刷新」) step | Final merge completes |
| Independent auditor | The workflow (Plan review / Project acceptance) | One review | A new session every time | Gives a verdict |
| Module manager / acceptance | Project manager | For the life of the module | Reset via the Refresh step; reset on entering Acceptance check | Module report completed |
| Developer | Module manager | One subtask | Reopened after writing a checkpoint when alerted | Merged into the module branch, or stopped and split |
| Reviewer | The workflow (Review step) | One review | A new session every time | Gives a verdict |
| Guard | Kandev automation (cron) | One patrol | A new session every time | Sends alerts, or ends with nothing to do |

### Interaction permission matrix

Rows = initiator, columns = receiver. ✅ allowed　⚠️ allowed with conditions　❌ forbidden

| Initiator ↓ / Receiver → | User | Project manager | Module manager | Developer | Reviewer |
|---|---|---|---|---|---|
| **Project manager** | ⚠️ attended only: questions, gates | — | ✅ create tasks, decisions | ❌ | ❌ |
| **Independent auditor** | ✅ via gate steps | ✅ only through `move_task` (with comments) and task docs | ❌ | ❌ | ❌ |
| **Module manager** | ❌ via the project manager | ✅ reports, escalations | ⚠️ other modules: factual questions only | ✅ create tasks, reply, send back, stop, ask | ⚠️ read the review deliverable; if unclear, ask that review session |
| **Developer** | ❌ (under autopilot can only ask the upstream manager) | ❌ | ✅ `ask_parent_question` | ❌ no direct communication between developers | ✅ only through `step_complete` + handoff |
| **Reviewer** | ❌ | ❌ | ✅ ESCALATE | ✅ only by sending back via `move_task` (with notes) | — |
| **Guard** | ❌ | ✅ ALERT; move to Refresh when the pm is stuck and unresponsive | ✅ ALERT | ❌ relayed via the module manager | ❌ |

### Explicitly forbidden interactions (and why)

- **Developer ↔ developer**: parallel writers coordinate privately, resulting in duplicated work or overwriting each other. When coordination is needed, it goes through the module manager.
- **Reviewer / independent auditor ↔ conversation with the reviewee**: it would break the reviewer's clean context. Reviews express opinions only through structured verdicts and send-back notes.
- **Developer / reviewer → project manager**: skipping a level bloats the project manager's context. Everything is aggregated through the module manager.
- **Modules agreeing on interfaces privately**: cross-module decisions must be written as ADRs and decided by the project manager.
- **The guard fixing things directly**: the guard only detects and alerts; fixes are carried out by the task's upstream manager. The only exception is moving a stuck pm to Refresh.
- **Looking things up on someone else's behalf**: for information you don't own, ask the owner directly instead of digging through conversation history or reading code to guess. When asked about something you don't own, refer the asker to the owner.
- **Chatting in GitHub comments**: GitHub only records summaries of state changes; communication between agents stays inside Kandev.
