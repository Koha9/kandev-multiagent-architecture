# Development project conventions

[中文](project-conventions.md) | **English**

> This file covers conventions on **the side of the project being developed**: what the multi-agent architecture requires every project to have and to follow.
> The pm writes these into `project/conventions.md` during Project planning (立项规划), and the baseline module puts them into effect in the repository and writes `project/environment.md` (both are **the project's own** management files; templates in [../mgmt-template/project/](../mgmt-template/project/conventions.md) (Chinese)), and each project fills them in for its own tech stack.
> The architecture doc [workflow.md](workflow.en.md) only specifies which step and which role put these conventions into effect, and how to escalate when blocked; it does not prescribe their content.

## 1. Quota and external side effects

- Real AI calls, paid APIs, deployments, pushing to remotes and changing remote settings: must be turned on by an explicit switch (e.g. the environment variable `<PROJECT>_REAL_AI=1`), off by default.
- Tests that need real calls are tagged with a marker, and the switch is checked again at the test-framework level (conftest or equivalent); when it is off they are always skipped. Relying only on test config defaults (e.g. addopts in pytest.ini) is not enough, since a single command-line argument can override them.
- The call limit for each kind of real call is written into conventions and enforced by the quota ledger (see section 2).
- Acceptance items that need real calls as proof reuse results already obtained in module acceptance instead of calling again.

## 2. Constraint list and enforcement

The conventions "Constraint list (约束清单)" marks how each constraint is enforced: `enforced in code` / `check script` / `prompt only`. The baseline module turns everything that can be enforced into code, and writes the commands into environment.md "Constraint enforcement (约束落实)".

| Constraint | Mechanism | Tool |
|---|---|---|
| No pushing to remotes (unless conventions explicitly allow it) | set the push URL of every remote to `DISABLED` | git |
| Developers only change files within owns | an out-of-scope check runs once before the developer reports and once during review | [`tools/check_owns.py`](../mgmt-template/tools/check_owns.py) |
| Limit on real calls | quota ledger: conftest consumes before every real call and fails once over the limit | [`tools/quota.py`](../mgmt-template/tools/quota.py) |
| Single writer for the management directory (when under git) | pre-commit hook checks paths against `MGMT_SCOPE` | [`tools/mgmt_precommit.py`](../mgmt-template/tools/mgmt_precommit.py) |
| Review does not change test selection arguments | written in the reviewer role card | prompt only |

The scripts under `tools/` use only the Python standard library and are copied with mgmt-template into each project's management directory. `python` in commands is written as the absolute interpreter path from environment.md.

## 3. Tests and reruns

- Each development task's contract states a directly runnable test command; new features must come with tests, and existing tests must not be deleted or weakened to make them pass.
- When review, module acceptance and project acceptance rerun tests, they run them exactly as written in environment.md, without changing test selection arguments (`-o addopts`, `-m`, `-k`, etc.) and without turning on quota-consuming switches.
- environment.md states the smoke test (one command, expected output, duration). Every development session runs it once at the start; on failure it reports instead of developing on a broken baseline (tasks of the baseline module skip it until the smoke test exists).
- environment.md "合并门禁" (Merge gate) states the full local check to run before merging (lint + full tests + build, and whether the integration-test suite is included). The W3 Merge (「合并」) step runs it exactly as written, together with the owns check, before merging into the module branch.
- Integration tests (when the project has an integration-test module): environment.md "结合测试" (Integration tests) states the automation tool, how to start the really assembled application, one run command and the test directory; the baseline module adds one minimal passing case to the skeleton.
  - Tests run against the really assembled application and assert user-visible results and data state; only quota-consuming external calls may be mocked.
  - Automation tools come first. Operating the product manually is a fallback, used only for scenarios the tool cannot cover (still with tool support where possible), with the reason and evidence written in the report.
  - When a product defect is found, the failing case is kept and the defect reported (naming the owning module and the suspected location); assertions are not changed, no mocks are added, nothing is skipped; the pm hands the fix to the owning module.
  - The suite stays in the repository, and Project acceptance, Final merge and later fix rounds all re-run it.

## 4. UI evidence

- Projects with a UI state the tool, command and viewports in the "Screenshots (截图)" section of environment.md.
- Tasks with `ui: true` attach screenshots in the report: when changing an existing UI, both before and after, saved to `<mgmt_root>/evidence/<task id>/`. Review checks the screenshots against the AC.
- Project acceptance collects screenshots of the key pages at each viewport in final-report "How to run for final review (终审运行方式)", reducing the cost of the user starting the service themselves to look during the final review.

## 5. Merging and pushing

- The merge method is written into environment.md "Merge method (合并方式)": development branches always fast-forward into `mod/<module>` locally (the Merge step does it after the merge gate; `mod/*` exists only locally, so no PRs); Final merge (「收尾合并」) may merge locally or via PR (restore the push URL first for a PR).
- Module branches are cut from `mod/baseline` and the integration branch from the baseline branch; the user's baseline branch is not touched before Final merge (「收尾合并」).
- By default merges are local only, with no push to remotes. To push or open PRs, this must be explicitly agreed in conventions and environment.md, and the push ban in section 2 adjusted accordingly.
- When pushing is disabled, the baseline module first records each remote's original push URL in environment.md "约束落实" (constraint enforcement); Final merge (「收尾合并」) restores them from that record (the repository goes back to the user when the project ends).
- environment.md "共享文件" (Shared files) lists files that several modules and tasks append entries to (dependency manifests, route registration, the app shell, etc.) says where each module appends, and marks generated files with their regeneration command; merge conflicts touching only these files are resolved in place. A task's `shared` in tasks.json lists the shared files it touches: several tasks may change them, but each only appends its own entries; the owns check accepts owns + shared.

## 6. Environment

- environment.md states the OS / shell, language and version, interpreter or environment, install commands from zero to runnable, and common commands.
- Files that need Kandev's repository Copy files setting go into "Copy files": the baseline module escalates to the pm, who asks the user to configure it when attended; when unattended, choose an approach that does not depend on Copy files, and the pm writes an ADR.

## 7. Corresponding templates

| Convention | File in the project | Writer |
|---|---|---|
| Sections 1–3, 5 | `project/conventions.md` ("消耗额度与外部副作用" (quota and external side effects), "约束清单" (constraint list), "测试" (tests)) | pm |
| Commands for sections 2–6 | `project/environment.md` ("约束落实" (constraint enforcement), "截图" (screenshots), "合并方式" (merge method), "合并门禁" (merge gate), "Copy files") | baseline module agent |
| Quota ledger | `quota/ledger.json` | written only by `tools/quota.py` |
| Screenshots | `evidence/<task id>/` | that task's developer |
