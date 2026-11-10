# Benchmark project: run once after every workflow change

[中文](README.md) | **English**

> Purpose: compare different workflow versions on a fixed small project, without having to do a full pilot run on a real project every time. Results are comparable only if the requirements, environment and profiles stay the same.
> Size: 2 modules, 2 tasks per module (1 of which has a prerequisite task), expected to take 30–45 minutes. Incurs real agent session costs.

## Task description (use verbatim, replacing only the angle brackets)

The translation below is for reading only. Run the benchmark with the Chinese task description in [README.md](README.md) so that results stay comparable across runs.

```
[TASK v1]
project: bench-todo
mode: unattended
plan_only: false
mgmt_root: <working directory>/bench/todo-mgmt-<version>-<date>
mgmt_template: <absolute path of this repo>/mgmt-template
repo: <working directory>/bench/todo
role: pm
scope: pm
parent: user
pm: self
branch: <auto> base main
---
# Goal
A locally run to-do list web app, for benchmarking only, not public-facing.

# Requirements (most important first)
1. The backend (either the Python standard library or FastAPI) provides HTTP endpoints to create, delete, update and query to-dos, with data stored in SQLite.
2. A single-page frontend: list to-dos, add, check off as done, delete; data persists after a page refresh.
3. To-dos can have a due date; overdue to-dos are shown in red in the list.
4. At phone width (390px) the layout does not scroll horizontally.

# Run conditions
- Do not call ask_user_question_kandev; write an ADR for anything the user needs to decide and register it in attention.md.
- Merge locally, do not push to a remote. Do not use Docker.
- Make no real AI or paid API calls (all quota limits are 0).
```

Before running, create the repository `<repo>` with `git init` as an empty repository containing only a README (main branch).

## Metrics collected

When the run ends (on reaching Final human review (人工终审)):

```
python evaluation/metrics.py > evaluation/bench/results/<version>-<date>.jsonl
```

Append a row to `evaluation/bench/results.md`:

| Version | Date | Total time | Total queue time | Review send-backs | Guard alerts | Human interventions | Requirement coverage (R met / total) | Notes |
|---|---|---|---|---|---|---|---|---|

- Total time: from creation of the pm task to entering Final human review.
- Total queue time: the sum of `wait_min` over the development tasks (output of metrics.py).
- Guard alerts: the number of ALERT lines in `agents/guard/journal.md`.
- Requirement coverage: the number of items marked "met" (满足) in the "Requirement coverage" (需求覆盖) section of final-report / 4.
