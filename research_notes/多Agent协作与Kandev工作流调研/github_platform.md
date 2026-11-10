# GitHub as a Management & Communication Platform for Multiple AI Coding Agents (vs. Alternatives)

Research date: 2026-11-08. Sources are mostly primary (docs.github.com, github.blog changelog, official repos). Where only secondary/practitioner sources exist, that is flagged. Note: several docs pages (e.g. Copilot coding agent "about" page) have been rewritten in 2026 and no longer describe older flows verbatim; the changelog entries are the authoritative dated record.

## Q1. GitHub's own agent features (state as of late 2026)

### Takeaway
GitHub has turned Issues/PRs into a multi-vendor agent dispatch surface: you can assign an issue (or open PR) to Copilot, Claude, Codex, or several at once from the Assignees dropdown, iterate via `@claude`/`@codex`/`@copilot` PR comments, and govern it from "Agent HQ / mission control". Event-driven automation is covered by GitHub Agentic Workflows (gh-aw: Markdown -> Actions with read-only agents and "safe-outputs" for writes) and by vendor Actions such as `anthropics/claude-code-action` v1.

### Cited Findings
**Agent HQ / mission control**
- Agent HQ announced at GitHub Universe on 2025-10-28: "mission control", a single command center to assign, steer and track multiple agents across GitHub, VS Code, mobile and CLI; agents from Anthropic, OpenAI, Google, Cognition and xAI promised "over the coming months" within paid Copilot; includes branch controls for CI on agent-created code, identity controls for agents, one-click merge conflict resolution, Slack and Linear integrations — [GitHub Blog: Introducing Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/)
- Same announcement: enterprise "agent governance layer"/control plane (security policies, audit logging, which agents are allowed, model access) in public preview; custom agents with own system prompt/tools; AGENTS.md as source-controlled rules; GitHub MCP Registry in VS Code; Copilot coding agent gains a first-pass code-review step; Copilot metrics dashboard/API public preview — [GitHub Blog](https://github.blog/news-insights/company-news/welcome-home-agents/)
- 2026-02-04: Claude and Codex available as coding agents on GitHub (public preview, Copilot Pro+ and Enterprise); "Assign an issue to Claude, Codex, Copilot, or all three using the Assignees dropdown"; can also assign an open PR; each session consumes one premium request during preview — [GitHub Changelog 2026-02-04](https://github.blog/changelog/2026-02-04-claude-and-codex-are-now-available-in-public-preview-on-github/)
- 2026-02-26: extended to Copilot Business and Pro, no extra subscription; one issue can be assigned to multiple agents to compare approaches; mention `@claude` or `@codex` in PR comments to request changes — [GitHub Changelog 2026-02-26](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/)
- 2026-03-19: Copilot coding agent starts work ~50% faster (Copilot only) — [GitHub Changelog 2026-03-19](https://github.blog/changelog/2026-03-19-copilot-coding-agent-now-starts-work-50-faster/)
- 2026-07-07: Codex as agent provider in JetBrains (public preview); Claude sessions gain permission modes and debug logs — [GitHub Changelog 2026-07-07](https://github.blog/changelog/2026-07-07-codex-as-agent-provider-and-agentic-enhancements-in-jetbrains-ides/)
- 2026-10-01 (VS Code September releases): agent sessions for Copilot, Claude and Codex can open PR forms directly from the Agents window — [GitHub Changelog 2026-10-01](https://github.blog/changelog/2026-10-01-github-copilot-in-vs-code-september-2026-releases/)

**Copilot coding agent (current docs)**
- Works in a cloud dev environment; "can only work on one branch at a time and can open one pull request per task"; Actions-based sessions max 59 minutes and limited to the repo specified, while newer "cloud sandbox" sessions "can work across multiple repositories"; rulesets/branch protection can block it from creating/updating PRs; Cloud and Actions compute draw on the same monthly allowance "separate from AI credits"; "Agent Merge: Copilot watches a pull request and works on the blockers you select"; without write access the session is read-only — [GitHub Docs: About Copilot coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- Built-in protections: only users with write access can trigger it, comments from others are not passed to it; pushes only to one branch (existing PR branch or new `copilot/` branch); cannot run `git push` directly; cannot mark PR ready, approve or merge; Actions workflows on its PRs don't run until a write-access user clicks "Approve and run workflows"; requester cannot approve the PR; agent-identity PRs need an extra approval; firewall-restricted internet; hidden characters / HTML comments stripped before input reaches the agent; commits authored by Copilot, co-authored by requester, signed; session logs + audit log; for automations, events from non-write users ignored by default — [GitHub Docs: Risks and mitigations](https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations)
- Same page lists acknowledged risks: prompt injection via hidden instructions in issues/comments, data exposure, reduced admin visibility, unattended automations — [GitHub Docs: Risks and mitigations](https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations)

**GitHub Agentic Workflows (gh-aw)**
- `gh aw` CLI extension: Markdown + YAML frontmatter compiled (`gh aw compile`) to standard Actions workflows; engines: Copilot, Claude Code, OpenAI Codex, plus Gemini and Pi; "complements existing CI/CD; it does not replace it"; agent jobs default to read-only GitHub access, sandboxed; "Safe outputs buffer configured writes, validate them, and apply them in separate jobs"; README warns it requires "careful human supervision" and "Use it with caution, and at your own risk"; security advisory GHSA-8h78-hpm7-29gg retired versions >=0.83.3,<0.85.4; ~5.6k stars at time of fetch — [github/gh-aw](https://github.com/github/gh-aw)
- Earlier package listing called it a "research demonstrator", early development; listed sandboxing, input sanitization, network isolation, SHA-pinned deps, tool allowlisting, compile-time validation — [pkg.go.dev githubnext/gh-aw](https://pkg.go.dev/github.com/githubnext/gh-aw)
- Safe-output types relevant to multi-agent coordination (with default max per run): `create-issue`(1), `update-issue`(1), `link-sub-issue`(1), `add-comment`(1), `add-labels`(5), `remove-labels`(3), `assign-to-agent`(1), `assign-to-user`(1), `set-issue-type`(5), `create-pull-request`(1), `push-to-pull-request-branch`(1), `create-pull-request-review-comment`(10), `reply-to-pull-request-review-comment`(10), `resolve-pull-request-review-thread`(10), `add-reviewer`(3), `merge-pull-request`(1, experimental), `update-project`(10), `create-project-status-update`, `dispatch-workflow`(3), `call-workflow`(1), `dispatch-repository`, `create-check-run`(1), `create-agent-session`(1), `create-discussion`, plus Jira/Linear/Azure DevOps outputs and `noop`/`report-missing-tool` — [gh-aw Safe Outputs reference](https://github.github.com/gh-aw/reference/safe-outputs/)
- Design: agent emits structured output; separate jobs with their own scoped permissions (e.g. `issues: write`) perform writes, enabling validation, auditability and per-operation limits — [gh-aw Safe Outputs reference](https://github.github.com/gh-aw/reference/safe-outputs/)

**Claude Code GitHub Action**
- `anthropics/claude-code-action` v1.0: activates on `@claude` mentions, issue assignments, or automation with explicit `prompt`; "Intelligent Mode Detection"; unified `prompt` and `claude_args`; Structured Outputs become Action outputs; progress tracking comment with checkboxes; runs on your own runner; auth via Anthropic API (key or workload identity federation), Bedrock, Vertex, Microsoft Foundry; installed via `/install-github-app` (repo admin required) — [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action)
- By default it only runs when a user with write permission triggers it, but that can be disabled by configuration (risk vector) — [Aikido: PromptPwnd](https://aikido.dev/blog/promptpwnd-github-actions-ai-agents)

**Issue hierarchy / dependency primitives**
- Sub-issues: up to 100 sub-issues per parent, up to 8 nesting levels; CLI: `gh issue edit PARENT --add-sub-issue N[,M]`; REST `/repos/{owner}/{repo}/issues/{n}/sub_issues` — [GitHub Docs: Adding sub-issues](https://docs.github.com/en/enterprise-cloud@latest/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
- Issue dependencies (blocked by / blocking) GA 2025-08-21; up to 50 issues per relationship type; supported in API and webhooks — [GitHub Changelog 2025-08-21](https://github.blog/changelog/2025-08-21-dependencies-on-issues/)
- REST endpoints for listing/adding/removing `blocked_by` dependencies — [GitHub Docs: Issue dependencies REST](https://docs.github.com/en/enterprise-server@3.22/rest/issues/issue-dependencies); community skill notes paths `GET/POST /repos/{o}/{r}/issues/{n}/dependencies/blocked_by` and that removal uses numeric issue ID, and claims no MCP tool for dependencies (unverified against current MCP server) — [Smithery skill](https://smithery.ai/skills/takemo101/github-issue-dependency)

**GitHub MCP server**
- Toolsets: `context`, `actions`, `code_quality`, `code_security`, `copilot`, `copilot_issue_intents`, `dependabot`, `discussions`, `gists`, `git`, `governance`, `issues`, `labels`, `notifications`, `orgs`, `projects`, `pull_requests`, `repos`, `secret_protection`, `security_advisories`, `stargazers`, `users`; remote-only `copilot_spaces`, `github_support_docs_search`; defaults `context, repos, issues, pull_requests, users`; `--read-only` overrides `--tools`; remote URL `https://api.githubcopilot.com/mcp/` — [github/github-mcp-server](https://github.com/github/github-mcp-server)
- Relevant tools: `issue_read` (`get_sub_issues`, `get_parent`), `sub_issue_write` (`add`/`remove`/`reprioritize`, `replace_parent`), `projects_list/get/write`, `list_issue_types` + `type` param on `issue_write`, `assign_copilot_to_issue`, `assign_copilot_to_issue_with_intent`, `request_copilot_review` — [github/github-mcp-server](https://github.com/github/github-mcp-server)

### Inferences
- GitHub now natively provides the "assign issue -> agent -> draft PR -> review comment loop" for three vendors, so a local orchestrator does not need to reimplement cloud-agent dispatch; it can treat "assign to @copilot/@claude/@codex" as one more worker backend.
- gh-aw's safe-outputs set (labels, sub-issue link, assign-to-agent, dispatch-workflow, project update, review-comment reply) is effectively a whitelisted vocabulary for GitHub-native agent state machines; it is the most mature pattern for "agent writes to GitHub safely".
- Every GitHub-hosted agent path is gated by write-access triggers and human-approved workflow runs / merges — good for safety, but adds human-in-the-loop latency to any fully autonomous chain.

### Gaps
- No official, dated GitHub doc found describing Agent HQ GA status (still "public preview" per Feb 2026 changelogs); third-party guides describe settings like "Agent Governance" menu but are unverified ([i-programmer](https://www.i-programmer.info/news/105-artificial-intelligence/18651-github-adds-claude-and-codex-to-agent-hq.html)).
- Did not verify current Projects v2 GraphQL specifics (field updates via `updateProjectV2ItemFieldValue`) or issue-type REST endpoints in this pass.
- Did not fetch OpenAI's own Codex GitHub integration docs (Codex cloud `@codex` review) separately from GitHub's Agent HQ integration.
- gh-aw threat-detection job details and current version number not captured (Releases page empty at fetch time).

## Q2. Documented real-world multi-agent coordination patterns on GitHub, and lessons

### Takeaway
Practitioners converge on: labels as a linear state machine (one owner per stage), issues as task specs, PRs as handoff artifacts, CI/deterministic checks as gates, a non-coding orchestrator, worktrees for parallelism, and humans keeping the merge. Evidence is anecdotal (blog posts), not measured studies.

### Cited Findings
- Six specialized agents coordinated through GitHub: each pipeline stage is a GitHub label owned by one agent; handoff = label change, no direct agent messaging; humans approve merges; specialized narrow-context agents beat one generalist — [Operum blog](https://www.operum.ai/blog/building-ai-agent-orchestrator); [DEV Community (same author)](https://dev.to/alprimak/building-an-ai-agent-orchestrator-how-6-specialized-agents-coordinate-through-github-55gk)
- "371 git worktrees" report: system stabilized after enforcing that the orchestrator only delegates and never writes code; sub-agent failures stopped cascading; orchestrator is a single point of failure; team cut agents from seven to five — [LevelUp/gitconnected](https://levelup.gitconnected.com/what-371-git-worktrees-taught-me-about-multi-agent-ai-36d4d61acfb5?gi=85d4d05bd94c)
- Common failure: multiple agents opening overlapping/conflicting PRs; recommended routing work to avoid shared code and returning results only after deterministic checks pass — [DEV Community: 7 orchestration lessons](https://dev.to/jenueldev/your-ai-agents-are-not-a-team-yet-7-orchestration-lessons-from-multi-agent-failures-2lf3)
- GitHub doesn't natively implement agent-to-agent coordination; teams build chaining from issues, labels and Actions — [Medium: When Two Agents Work the Same PR](https://nivedv.medium.com/when-two-agents-work-the-same-pr-multi-agent-orchestration-in-github-fb77f38b3d95)
- Rules/templates for a solo dev orchestrating many parallel agents with worktrees — [OskarGroth/orchestrating-agents](https://github.com/OskarGroth/orchestrating-agents)
- Human review before merge still required by current tools — [Addy Osmani: conductors to orchestrators](https://addyosmani.com/blog/future-agentic-coding/)
- GitHub's own "comparison" pattern: assign same issue to Copilot, Claude, Codex and compare PRs — [GitHub Changelog 2026-02-26](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/)

### Inferences
- Pattern mapping: issue body = task spec; sub-issues = orchestrator decomposition; `blocked_by` = DAG; assignee/label = claim + state; PR = handoff artifact; PR review + review comments = agent-to-agent feedback; required checks/rulesets = gate; Projects v2 = board view for humans.
- Label state machines work because labels are cheap, visible, webhook-emitting and idempotent; but claims via label/assignee are not atomic (see Q3).

### Gaps
- No quantitative studies found (throughput, merge rate, cost per merged PR) of GitHub-issue-coordinated multi-agent systems.
- No primary source found documenting a large OSS project running orchestrator-files-sub-issues + worker-claims-by-label at scale.

## Q3. Limitations: rate limits, latency, cost, context bloat, concurrency, security, noise

### Takeaway
Hard limits are generous for a single local orchestrator (5,000 REST req/h, 5,000 GraphQL points/h per user) but tight inside Actions (`GITHUB_TOKEN` 1,000 req/h per repo) and on writes (80 content-creating req/min, 500/h). The dominant risk is security: issue/PR/comment text is untrusted input, and multiple published attacks (Invariant's GitHub MCP "toxic agent flow", Aikido's PromptPwnd, April 2026 "Comment and Control") exfiltrated private data or secrets via agents reading GitHub content.

### Cited Findings
**Rate limits**
- REST primary: unauthenticated 60/h; authenticated user 5,000/h (15,000/h for GHEC-owned apps); GitHub App installation min 5,000/h, scaling +50 per repo/user beyond 20 up to 12,500/h (15,000/h on GHEC); `GITHUB_TOKEN` in Actions 1,000/h per repo (15,000/h for GHEC) — [GitHub Docs: REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- Secondary: max 100 concurrent requests (REST+GraphQL shared); 900 points/min REST, 2,000 points/min GraphQL; 90 s CPU per 60 s (<=60 s GraphQL); content creation generally 80 req/min and 500 req/h; GET = 1 point, POST/PATCH/PUT/DELETE = 5 points, GraphQL mutation = 5 points — [GitHub Docs: REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- GraphQL primary: 5,000 points/h per user (10,000 for GHEC-owned apps on behalf of user); `GITHUB_TOKEN` 1,000 points/h per repo; every connection needs `first`/`last`; max 500,000 nodes per call — [GitHub Docs: GraphQL rate limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)

**Actions / token behavior affecting agent chaining**
- Events created with `GITHUB_TOKEN` generally do not trigger new workflow runs (anti-recursion), except `workflow_dispatch` and `repository_dispatch`; PRs created/updated by the token are an exception but their runs require approval; token limited to the workflow's repo; expires at job end, max 6 h on hosted runners (24 h refresh limit on self-hosted) — [GitHub Docs: GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token)
- Copilot coding agent Actions sessions capped at 59 minutes; compute draws on the account's monthly allowance — [GitHub Docs: About coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- Claude/Codex sessions on GitHub cost one premium request each (preview) — [GitHub Changelog 2026-02-04](https://github.blog/changelog/2026-02-04-claude-and-codex-are-now-available-in-public-preview-on-github/)

**Prompt injection / security incidents**
- Invariant Labs: attacker files a malicious issue on a public repo; victim's agent (Claude Desktop + GitHub MCP with a PAT covering public+private repos) reads issues, then pulls private repo data and opens a public PR leaking it; affects any agent using GitHub MCP regardless of model; Invariant calls it an architectural, agent-system-level issue, not a server code bug; mitigations: least-privilege (one repo per session), MCP-scan / toxic flow analysis — [Invariant Labs: GitHub MCP vulnerability](https://invariantlabs.ai/blog/mcp-github-vulnerability); [Invariant: Toxic Flow Analysis](https://invariantlabs.ai/blog/toxic-flow-analysis); walkthrough in [Security Boulevard/Wallarm 2026-04](https://lab.wallarm.com/attacking-the-mcp-trust-boundary)
- Aikido "PromptPwnd" (Dec 2025): workflows interpolated untrusted issue titles/bodies into agent prompts; hidden instructions made agents run privileged tools and post secrets back to the issue; affected Claude Code Actions and others when configured to let non-write users trigger; recommends restricting tools, avoiding agent write tools on issues/PRs, validating untrusted input — [Aikido: PromptPwnd](https://aikido.dev/blog/promptpwnd-github-actions-ai-agents)
- "Comment and Control" (April 2026): PoC PR comments with hidden instructions caused Anthropic's Claude Code Security Review Action, Google's Gemini CLI Action and GitHub Copilot Agent to post `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GEMINI_API_KEY` into public PR comments or Actions logs, with zero maintainer interaction beyond the automated trigger; Google patched in 4 days; no Anthropic/GitHub response reported in the note; root cause = any agent with bash + secrets + untrusted NL input — [CSA Research Note 2026-05-03](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/)
- CSA recommendations: treat PR titles/comments/issue bodies as untrusted; minimize tools (review agent need not push); separate agents from credentials; short-lived scoped keys; explicit minimal `permissions`; remove `pull_request_target` workflows that check out fork code; red-team before deploy — [CSA Research Note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/)
- GitHub's mitigations for its own agent: write-access-only triggers, hidden-char/HTML-comment stripping, firewall, no self-merge — [GitHub Docs: Risks and mitigations](https://docs.github.com/en/copilot/concepts/agents/coding-agent/risks-and-mitigations)
- gh-aw itself had a security advisory (GHSA-8h78-hpm7-29gg) forcing retirement of versions 0.83.3–0.85.4 — [github/gh-aw](https://github.com/github/gh-aw)

### Inferences
- Rate-limit budgeting: a local orchestrator polling N issues every minute via REST burns ~60N req/h; at 5,000/h that caps polling at ~80 issues/min. Prefer webhooks or GraphQL batching, ETag conditional requests, and keep writes under 80/min (content creation limit is the realistic ceiling for chatty agents posting comments).
- Inside Actions, `GITHUB_TOKEN`'s 1,000/h per repo and the "no workflow triggered by GITHUB_TOKEN events" rule mean agent-to-agent chaining via labels/comments silently breaks unless you use a GitHub App token, PAT, or `workflow_dispatch`/`repository_dispatch` (gh-aw's `dispatch-workflow` safe-output exists for this reason).
- Claiming races: assignee/label changes are not compare-and-swap; two workers can both add `claimed` label. Mitigations: single orchestrator assigns (workers never self-claim), or claim then re-read and back off if another assignee present; or keep claims in a local DB/lease system (beads, Agent Mail reservations).
- Context cost: long issue/PR threads (bot progress comments, CI summaries, multiple review rounds) are re-read on every agent turn; summarizing into the issue body or a single "status" comment and reading only the latest N comments reduces tokens. (No measured token figure found.)
- Noise: GitHub notifications fire for every agent comment/label; human maintainers get flooded unless agents batch updates (e.g. edit one tracking comment, as claude-code-action does with its checkbox progress comment).

### Gaps
- No primary measurement found for webhook delivery latency or Actions queue-to-start latency for agent workflows (only Copilot's "50% faster start", no absolute number).
- No measured data on token cost of reading GitHub threads for agents.
- Could not confirm whether GitHub MCP server's "lockdown mode"/content sanitization for public repos is documented (page truncated before that section).

## Q4. Alternatives: beads, MCP Agent Mail, Linear, markdown task files (and Kandev board)

### Takeaway
Local-first tools trade GitHub's durability/visibility for low latency, no rate limits, atomic claims and less injection surface: beads (git/Dolt-backed dependency-graph issue tracker with `bd ready`) handles task state; MCP Agent Mail handles agent-to-agent messaging and advisory file leases; Linear offers a hosted "delegate to agent" model with agent sessions. They compose with GitHub rather than replace PRs/CI.

### Cited Findings
- beads (`bd`): "distributed, git-backed graph issue tracker for AI agents"; hash-based IDs (e.g. `bd-a1b2`) to avoid merge collisions across agents/branches; JSON output, dependency tracking, auto-ready detection (`bd ready`); "memory decay" summarizes old closed tasks to save context; agents onboarded via a line in AGENTS.md; Claude Code MCP plugin — [steveyegge/beads](https://github.com/steveyegge/beads)
- beads storage changed: older docs say JSONL in `.beads/` + SQLite cache + background sync daemon; current README highlights a version-controlled SQL DB (Dolt) with cell-level merge, branching, sync via Dolt remotes; check version — [steveyegge/beads](https://github.com/steveyegge/beads); [skills.cat beads](https://skills.cat/skills/itechmeat/llm-code/beads)
- MCP Agent Mail: "gmail for your coding agents"; agent identities (adjective+noun), inbox/outbox, threads, acks, importance; advisory time-limited file reservations on paths/globs with optional pre-commit guard; Markdown messages in a per-project Git repo + SQLite FTS5; web UI at `/mail` with Human Overseer messages; cross-project contact requires approval; ~2.2k stars; Python version now deprecated/maintenance, "superseded by mcp_agent_mail_rust" — [Dicklesworthstone/mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)
- Agent Mail + beads convention: beads = task status/dependencies, Agent Mail = conversation/audit; use beads ID (`bd-123`) as mail thread ID and reservation reason; Beads Viewer (`bv`) for graph analysis (PageRank, critical path); README claims 1 agent-hour ≈ 10–20 human hours (author's claim, unmeasured) — [Dicklesworthstone/mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)
- Linear Agents API (Developer Preview): assigning an issue to an agent makes it the *delegate*, human keeps assignee ownership; sessions start on mention/delegation; agents emit "Agent Activities" that render progress; `promptContext` packages issue + comments — [Linear Developers: Agents](https://linear.app/developers/agents)
- Linear Codex agent (2025-12-04): delegate issue to Codex, it picks repo and starts work; requires ChatGPT paid plan + connected GitHub — [Linear changelog via mirror](https://hn.jakechampion.name/reader/https://linear.app/changelog/2025-12-04-openai-codex-agent)
- No official Linear-built Claude agent found; community bridges (Linear <-> Anthropic Managed Agents sessions; Claude Code in Sprite sandbox) — [NorthIsUp/claude-linear-agent](https://github.com/NorthIsUp/claude-linear-agent); [DEV: sandboxed Linear agent](https://dev.to/marvinjude/building-a-sandboxed-linear-agent-powered-by-claude-code-and-sprite-24db)
- Agent HQ mission control integrates with Linear and Slack — [GitHub Blog: Agent HQ](https://github.blog/news-insights/company-news/welcome-home-agents/)
- gh-aw can write to Linear/Jira/Azure DevOps via safe-outputs (`linear-create-issue`, `jira-create-issue`, ...) — [gh-aw Safe Outputs](https://github.github.com/gh-aw/reference/safe-outputs/)

### Inferences
- Comparison matrix (synthesized):
  - GitHub Issues/PRs: + durable, human-visible, webhooks, native agent assignment, CI/rulesets as gates, audit; − rate limits, latency (minutes for Actions-based agents), non-atomic claims, notification noise, untrusted-content injection surface, thread bloat in context.
  - beads: + local, instant, offline, dependency DAG + `bd ready`, atomic-ish via DB, context-saving compaction, versioned with repo; − not visible to non-repo stakeholders, no CI/review integration, storage backend churn.
  - MCP Agent Mail: + real-time-ish messaging, file leases (solves the worktree-overlap problem), audit in git; − another server to run, advisory (not enforced) locks unless pre-commit guard installed, Python version deprecated.
  - Linear: + polished human board, first-class agent delegate/session model; − SaaS, Developer Preview API, still needs GitHub for code/PR.
  - Plain markdown task files (TODO.md/PLAN.md in repo): + zero infra, diffable, cheap context; − no claims/locks, merge conflicts with parallel agents (exactly what beads' hash IDs address).
- Kandev's own board (local orchestrator DB) occupies the same niche as beads + Agent Mail: fast, local, authoritative for run-time state.

### Gaps
- Kandev board capabilities not researched here (outside GitHub scope; likely covered by another researcher).
- No benchmark comparing GitHub-coordinated vs local-tracker-coordinated agent teams.
- Rust Agent Mail feature parity not checked.

## Q5. Combining a local orchestrator (Kandev + worktrees) with GitHub as durable record; useful gh CLI capabilities

### Takeaway
Use GitHub for durable, human-facing, reviewable artifacts (issue specs, PRs, reviews, checks, merges) and keep high-frequency coordination (claims, leases, heartbeats, agent chatter, scratch plans) local in the orchestrator DB / beads / Agent Mail, syncing summaries outward at state transitions. The `gh` CLI already covers most needs natively (`gh issue edit --add-sub-issue`, `gh pr review`, `gh pr checks`, `gh api graphql`).

### Cited Findings
- `gh issue edit PARENT --add-sub-issue N` (comma-separated list) is native in gh CLI per GitHub docs (no extension needed) — [GitHub Docs: Adding sub-issues](https://docs.github.com/en/enterprise-cloud@latest/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
- Dependencies settable via REST `blocked_by` endpoints (usable through `gh api`) — [GitHub Docs: Issue dependencies REST](https://docs.github.com/en/enterprise-server@3.22/rest/issues/issue-dependencies)
- GraphQL connections require `first`/`last`; points budget 5,000/h — design `gh api graphql` queries to batch issue+labels+latest comments per call — [GitHub Docs: GraphQL limits](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
- GitHub MCP server alternative for agents that prefer MCP: `issue_read`/`sub_issue_write`/`projects_write`/`assign_copilot_to_issue`; `--read-only` mode for reader agents — [github/github-mcp-server](https://github.com/github/github-mcp-server)
- Offloading a task to a cloud agent from a local orchestrator = assign issue to Copilot/Claude/Codex or `@claude`/`@codex` in a PR comment — [GitHub Changelog 2026-02-26](https://github.blog/changelog/2026-02-26-claude-and-codex-now-available-for-copilot-business-pro-users/)
- beads explicitly designed to live in the repo alongside code with multi-branch-safe IDs; Agent Mail stores messages in git for audit — [steveyegge/beads](https://github.com/steveyegge/beads); [mcp_agent_mail](https://github.com/Dicklesworthstone/mcp_agent_mail)
- Least privilege recommended: one repo per agent session, scoped short-lived tokens — [Invariant Labs](https://invariantlabs.ai/blog/mcp-github-vulnerability); [CSA note](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-github-actions-security-20260503-csa-st/)

### Inferences
Proposed split (synthesis, not sourced as a single recommendation):
- **GitHub (durable, shared, human-reviewed):** epic/issue specs + acceptance criteria; sub-issue tree and `blocked_by` edges for the human-visible plan; one label per coarse state (`agent:queued/in-progress/needs-review/blocked`); PRs (one per task/worktree branch) as the handoff; PR reviews/inline comments for reviewer-agent feedback that humans must also see; required checks + rulesets as the merge gate; final merge by human; Projects v2 only as a human board (agents update via batched GraphQL/gh-aw `update-project`).
- **Local orchestrator DB (Kandev):** authoritative run-time state — which agent/worktree holds which task (atomic claims), heartbeats, retries, token/cost accounting, session transcripts, mapping task<->issue#<->PR#<->branch<->worktree, cached GitHub state (ETags) to avoid polling.
- **Repo files (AGENTS.md, task markdown / beads `.beads/`):** agent instructions, per-task working notes and plans that should version with the code; beads if you want a dependency DAG/`ready` queue local to the repo.
- **Agent-to-agent chatter / file leases:** local (Agent Mail-style or orchestrator messaging), with only a summary posted to the GitHub issue/PR at state transitions to limit noise, rate-limit use and context bloat.
- Security posture: treat all GitHub text as untrusted data; reader agents use read-only tokens/`--read-only` MCP; writers act through a narrow allowlist (gh-aw safe-outputs pattern or orchestrator-mediated writes); never give an agent both secrets+bash and untrusted issue/PR text without isolation; ignore comments from non-write users.
- Useful gh commands for agents: `gh issue list/view --json` (structured, cheap), `gh issue edit --add-label/--remove-label/--add-assignee/--add-sub-issue`, `gh issue develop` (branch from issue), `gh pr create --draft`, `gh pr review --approve/--request-changes/--comment -b`, `gh pr checks --watch`, `gh pr view --json reviews,comments,statusCheckRollup`, `gh run watch/view --log-failed`, `gh api graphql` for batched reads and Projects v2 mutations, `gh api` for dependencies/sub-issues REST. (Flags listed from general gh CLI knowledge; only `--add-sub-issue` was verified in this pass.)

### Gaps
- Did not verify current `gh` CLI release notes for any new 2026 agent-related subcommands (e.g. `gh agent-task`), nor third-party `gh sub-issue` extensions' status (native flag appears to supersede them).
- No source found that prescribes a GitHub-vs-local split for a local worktree orchestrator; the split above is inference.
