# Real-world cases of multi-agent LLM coding systems on medium-to-large software projects (2025-2026)

Research date: 2026-11-08. Every claim has a date and a source URL. Primary sources were fetched directly unless marked "secondary". The OpenAI harness-engineering page returned HTTP 403 to the fetcher, and so did Steve Yegge's Medium post. Facts for those two cases come from search excerpts, localized OpenAI pages and secondary summaries, and are flagged as such.

---

## Q1. Which documented cases exist, and how big were they (who, what, scale, architecture, cost)?

### Takeaway
The best-documented cases are four write-ups: Anthropic's C compiler (16 peer agents, about 100K LOC, about $20K, 2 weeks), Cursor's planner/worker experiments (hundreds of agents, 1M+ LOC browser in about a week), OpenAI's Codex "harness engineering" product (about 1M LOC in 5 months, 3 to 7 engineers, zero hand-written code), and Anthropic's long-running harness posts (initializer/coding agent, then planner/generator/evaluator). Cognition, Claude Code agent teams and Gas Town supply design doctrine and tooling, with less hard project data.

### Cited Findings

**Case A: Anthropic, "Building a C compiler with a team of parallel Claudes" (Nicholas Carlini, Safeguards team, 2026-02-05)**
- What was built: a clean-room Rust C compiler, written from scratch with no internet access and only the Rust std library as a dependency. It builds Linux 6.9 on x86, ARM and RISC-V. It also compiles QEMU, FFmpeg, SQLite, Postgres and Redis, passes about 99% of most compiler test suites including the GCC torture tests, and runs Doom — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Scale: 16 parallel agents (Opus 4.6), close to 2,000 Claude Code sessions over two weeks, about 2B input tokens and 140M output tokens, cost just under $20,000, about 100,000 LOC — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Harness: a bash `while true` loop restarts Claude Code with `--dangerously-skip-permissions` and a prompt file, and logs to `agent_logs/`. Each agent runs in its own Docker container. A bare git repo is mounted at `/upstream`, cloned to `/workspace` and pushed back — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Coordination: there is no orchestrator, no inter-agent messaging and no high-level goal management. An agent claims a task by writing a lock file in `current_tasks/`. Git sync forces a collision loser to pick a different task. When done, the agent pulls, merges, pushes and deletes its lock. Merge conflicts were frequent, and Claude resolved them — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Specialized roles in the peer pool: one agent deduplicated code, one worked on compiler performance, one on generated-code efficiency, one critiqued the design as a Rust expert and refactored, and one wrote documentation — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Model dependence: Opus 4 could barely produce a working compiler. Opus 4.5 was the first to pass large test suites, but it could not compile large real projects — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- Limitations: there is no 16-bit x86 real-mode codegen, so it calls GCC for that phase, and its 16-bit output is over 60KB against Linux's 32KB limit. It has no own assembler or linker. With all optimizations on, its output is less efficient than GCC with optimizations off. Rust quality is "reasonable", below expert level. The author said the experiment left him "feeling uneasy" about mistaking passing tests for done — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)

**Case B: Cursor, "Scaling long-running autonomous coding" (Wilson Lin, 2026-01-14)**
- Web browser from scratch ("FastRender", Rust): agents ran close to a week and wrote over 1M LOC across about 1,000 files. Hundreds of workers pushed to the same branch with minimal conflicts — [Cursor](https://cursor.com/blog/scaling-agents)
- Solid to React migration in Cursor's own codebase: over 3 weeks, +266K/-193K edits. It passes CI but "still needed careful review" — [Cursor](https://cursor.com/blog/scaling-agents)
- Video rendering rewritten in Rust ran 25x faster, was merged and is slated for production — [Cursor](https://cursor.com/blog/scaling-agents)
- Ongoing projects: Java LSP (7.4K commits, 550K LOC), Windows 7 emulator (14.6K commits, 1.2M LOC), Excel clone (12K commits, 1.6M LOC). The post reports "trillions of tokens" and hundreds of concurrent agents per project — [Cursor](https://cursor.com/blog/scaling-agents)
- Final architecture: Planners → Workers → Judge (details in Q2). Model mix: GPT-5.2 did best on long autonomous work and was a better planner than GPT-5.1-Codex. Opus 4.5 "tended to stop early and take shortcuts" — [Cursor](https://cursor.com/blog/scaling-agents)
- Critique (secondary, 2026-01-22 to 01-26): reports say `cargo build` on the repo failed with "34 previous errors" and that GitHub Actions on main were failing. The repo issue tracking this was #98. Critics disputed the "from scratch" claim because of reliance on existing crates and Servo components, which Lin denied. They also noted the post gave no reproducible build or known-good commit. CEO Michael Truell is quoted saying "It *kind of* works". Some developers later got it compiling after fixes — [The Register](https://www.theregister.com/2026/01/22/cursor_ai_wrote_a_browser/); [The Register opinion](https://theregister.com/2026/01/26/cursor_opinion/); [ITHome](https://www.ithome.com/0/914/094.htm); [letsdatascience](https://letsdatascience.com/news/cursor-misrepresents-ai-built-web-browser-project-f61f9408)

**Case C: OpenAI, "Harness engineering: leveraging Codex in an agent-first world" (Ryan Lopopolo, 2026-02-11)**
- Five-month experiment that built and shipped an internal beta product with "0 lines of manually-written code". The repo reached "on the order of a million lines of code", covering app logic, infra, tooling, docs and internal dev utilities — [OpenAI (search excerpt)](https://openai.com/index/harness-engineering/)
- About 1,500 PRs opened and merged, about 3.5 PRs per engineer per day. The team grew from 3 engineers to 7. These figures are secondary and unverified against the English original — [zby summary](https://zby.github.io/commonplace/sources/harness-engineering-leveraging-codex-agent-first-world); [Orbital Witness, 2026-07-22](https://tech.orbitalwitness.com/posts/2026-07-22-grading-ourselves-against-the-harness-engineering-playbook/)
- Codex CLI with GPT-5 generated the initial scaffold: repo structure, CI config, formatting rules and package manager. Codex also wrote the first AGENTS.md — [second-brain summary](https://second-brain-nuxt.vercel.app/harness-engineering-leveraging-codex-in-an-agent-first-world); [OpenAI (search excerpt)](https://openai.com/index/harness-engineering/)
- AGENTS.md is a short map of roughly 100 lines that points to a structured `docs/` directory, the system of record. One big AGENTS.md "failed in predictable ways" because it was hard to verify and could not be checked mechanically, so "drift is inevitable" — [OpenAI (search excerpt)](https://openai.com/index/harness-engineering/)
- Review: nearly all review effort moved to agent-to-agent review. Humans may review PRs but are not required to — [OpenAI it-IT](https://openai.com/it-IT/index/harness-engineering/); [OpenAI da-DK](https://openai.com/da-DK/index/harness-engineering/)

**Case D: Anthropic, "Effective harnesses for long-running agents" (Justin Young, 2025-11-26)**
- Problem: Opus 4.5 in an Agent SDK loop with compaction alone could not build a production-quality web app from a high-level prompt. It tried to one-shot the app, ran out of context mid-feature, and declared done prematurely — [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Two "agents": an initializer and a coding agent. They share a system prompt, tools and harness and differ only in the initial user prompt. For a claude.ai clone, the initializer produced a feature list of 200+ features, all initially `passes: false` — [Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

**Case E: Anthropic, "Harness design for long-running application development" (Prithvi Rajasekaran, Labs, 2026-03-24)**
- Three agents: planner, generator and evaluator. The planner turns a 1 to 4 sentence prompt into a full product spec. The generator builds, originally in sprints. The evaluator drives the running app with Playwright and fails any sprint that misses a hard threshold — [Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- Cost and quality comparison on a retro game maker ("RetroForge"): a solo Opus 4.5 run took 20 min and $9 and the core feature did not work. The full harness took 6 hr and $200, more than 20x the cost, and was much more functional — [Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- A browser DAW with the simplified Opus 4.6 harness took about 3 hr 50 min and cost $124.70. It had a working arrangement view, mixer and transport, but was "far from professional quality". Frontend runs took 5 to 15 iterations and up to about 4 hours — [Anthropic](https://www.anthropic.com/engineering/harness-design-long-running-apps)

**Case F: Anthropic, "How we built our multi-agent research system" (2025-06-13)**. This is a research product, not coding, but it is the reference orchestrator-worker design.
- Lead agent (Opus 4) plus parallel subagents (Sonnet 4) plus a CitationAgent. It beat single-agent Opus 4 by 90.2% on an internal research eval. Token usage explained about 80% of variance on BrowseComp. Multi-agent runs use about 15x the tokens of chat, and single agents about 4x — [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- The post states most coding tasks are a poor fit: they need shared context and have many inter-agent dependencies, so they parallelize less well than research — [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)

**Case G: Cognition / Devin**
- "Don't Build Multi-Agents" (Walden Yan, 2025-06-12) argues for a single-threaded linear agent, plus a context-compression model for long tasks. It calls 2025 multi-agent systems "fragile systems" — [Cognition](https://cognition.com/blog/dont-build-multi-agents)
- "Multi-Agents: What's Actually Working" (Walden Yan, 2026-04-22) reports patterns that do work: single writer with many contributors, a clean-context reviewer loop, "Smart Friend" model escalation, and "Managed Devins" (map-reduce-and-manage via internal MCP). Stats: Devin Review catches about 2 bugs per PR on average, about 58% of them severe. Usage in the largest enterprise segment grew about 8x over 6 months — [Cognition](https://cognition.com/blog/multi-agents-working)
- An X post on 2026-04-20 announced that Devin can manage a team of Devins. Each managed session has its own VM, terminal, browser and test infrastructure — secondary: [chatgate.ai](https://chatgate.ai/post/devin-desktop); [techedt](https://www.techedt.com/cognition-launches-devin-desktop-for-managing-ai-coding-agents-across-engineering-workflows)

**Case H: Claude Code agent teams (product feature, experimental; docs fetched 2026-11)**
- Components are a team lead, teammates (each a full Claude Code instance), a shared task list with pending, in-progress and completed states plus dependencies, and a mailbox at `~/.claude/teams/{team}/inboxes/{agent}.json`. Task claiming uses file locking. Enabling it requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — [Claude Code docs](https://code.claude.com/docs/en/agent-teams)

**Case I: Steve Yegge's Gas Town plus Beads (open-sourced 2026-01-01)**
- Yegge built Gas Town in Go with AI agents over about 17 days, drawing on more than a year of prior experiments. It coordinates 10+ coding agents, and other reports say 20 to 30. It is "still in alpha stage". Heavy use may need 2 to 3 Claude Max subscriptions ($100 to $200/month each) — [heise, 2026-02-21](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html); [search summaries](https://cloudnativenow.com/features/gas-town-what-kubernetes-for-ai-coding-agents-actually-looks-like/)
- Maggie Appleton characterized it as speculative design fiction rather than a production tool — secondary mention via [search summaries](https://second-brain-nuxt.vercel.app/gas-towns-agent-patterns)

### Inferences
- The two largest-LOC claims (Cursor's 1M+ browser and OpenAI's ~1M product) differ in verifiability. The OpenAI product was internally used and shipped. The Cursor browser drew public build-failure critiques. The C compiler is the most rigorously validated case, because it compiled Linux, the test suites were external and the limitations were disclosed.
- Cost per success varies a lot. The compiler cost about $20K for about 100K LOC. Anthropic's app harness costs $125 to $200 per app versus $9 for a failed solo run. Multi-agent pays when an oracle exists and the task exceeds what a single agent can reliably do.

### Gaps
- Factory droids, Google Jules, the GitHub Copilot coding agent at scale, and Amp/Sourcegraph were not researched within the tool budget. I found no fetched primary data on them, so I report none.
- I could not fetch OpenAI's English original or Yegge's Medium post (403). Details such as the docs/ layout, custom linters with remediation messages, layered architecture, "golden principles", the doc-gardening agent, the Chrome DevTools integration, and Gas Town's GUPP, molecules and hooks are known only from my memory or secondary sources. I have left them out of the cited facts.
- Cursor published no exact agent counts per run, no total dollar cost, and no quality metrics such as test pass rate for the browser.

---

## Q2. Which coordination topologies were used, and what was learned about flat peers versus hierarchy?

### Takeaway
Flat peers can work when an external oracle partitions the work, as with the C compiler's lock files plus tests. At hundreds of agents, flat self-coordination failed through lock contention or risk aversion, and a planner → worker → judge hierarchy with independent workers succeeded. Every source converges on "single writer per unit of work", fresh-context reviewers or evaluators, and minimal middle-management layers.

### Cited Findings
- **Flat peers with lock files (Anthropic compiler):** agents claim tasks via files in `current_tasks/` and coordinate only through git. There is no orchestrator, and agents choose "the next most obvious" problem. This worked while the failing tests were many and independent — [Anthropic, 2026-02-05](https://www.anthropic.com/engineering/building-c-compiler)
- **Flat peers broke down on a monolithic task:** compiling the kernel was one big task. All 16 agents hit the same bug, fixed it and overwrote each other's changes. The fix was oracle-based partitioning (Q5), not a manager agent — [Anthropic](https://www.anthropic.com/engineering/building-c-compiler)
- **Cursor attempt 1, flat with a shared lock file:** locks were held too long or never released, and "20 agents performed like 2 or 3". The system was brittle when an agent died holding a lock — [Cursor, 2026-01-14](https://cursor.com/blog/scaling-agents)
- **Cursor attempt 2, optimistic concurrency control:** writes failed if state had changed. This was more robust, but agents became risk-averse, avoided hard tasks, made small safe changes and churned — [Cursor](https://cursor.com/blog/scaling-agents)
- **Cursor final design, hierarchy:** Planners continuously explore and create tasks and can spawn sub-planners per area. Workers take a task, finish it without coordinating with other workers, and push. A Judge decides at the end of each cycle whether to continue, and the next iteration starts fresh — [Cursor](https://cursor.com/blog/scaling-agents)
- **Cursor, less is more:** an "integrator" role for quality control and conflict resolution became a bottleneck, and workers handled conflicts fine on their own. Too little structure gives conflicts, duplication and drift. Too much gives fragility. "The prompts matter more" than the harness and models — [Cursor](https://cursor.com/blog/scaling-agents)
- **Cognition, 2025:** use a single-threaded linear agent. The Flappy Bird example shows two subagents producing inconsistent pieces (a Mario-style background and a mismatched bird), because "actions carry implicit decisions" — [Cognition, 2025-06-12](https://cognition.com/blog/dont-build-multi-agents)
- **Cognition, 2026:** "single writer, multiple contributors" is the common thread of what works. Parallel-writer swarms: "most of the sexy ideas in that space still don't see meaningful adoption". Unstructured negotiating swarms are "mostly a distraction". Managed Devins work as map-reduce-and-manage, but managers are "overly prescriptive", children wrongly assume shared state, and cross-agent communication doesn't happen by default — [Cognition, 2026-04-22](https://cognition.com/blog/multi-agents-working)
- **Anthropic research system, orchestrator-worker:** a lead plans and spawns parallel subagents with their own contexts. Subagents write outputs to the filesystem and pass references back. Synchronous subagent execution is a bottleneck, and async adds coordination and state-consistency complexity — [Anthropic, 2025-06-13](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Anthropic app harness, pipeline:** Planner → Generator ⇄ Evaluator. They communicate through files and negotiate "sprint contracts" before each sprint — [Anthropic, 2026-03-24](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **Claude Code agent teams, lead plus peer teammates:** a shared task list (lead-assigned or self-claimed, file-locked) plus direct messaging. There are no nested teams, and only the lead manages the team. The docs recommend 3 to 5 teammates and 5 to 6 tasks per teammate, and say "Three focused teammates often outperform five scattered ones". They warn the lead sometimes implements tasks itself instead of waiting — [Claude Code docs](https://code.claude.com/docs/en/agent-teams)
- **Gas Town, Kubernetes-like control plane and data plane:** the Mayor decomposes work into Beads and bundles it into Convoys. The Deacon patrols the system and restarts stuck sessions. The Witness monitors agents in a single Rig and replaces stalled ones. Polecats are disposable workers, each in its own git worktree. The Refinery reviews output and handles merges. Long-lived agents use Erlang-style mailboxes. Agents are treated as "cattle" not "pets" — [heise, 2026-02-21](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)

### Inferences
- The scale threshold: at about 16 agents with a strong oracle, flat peers plus git plus lock files sufficed. At about 20 or more agents without an oracle-driven task supply, Cursor found flat coordination collapsed and needed planners to generate tasks.
- The main job of a hierarchy is task generation and decomposition (planners), not supervising writes. Workers should stay independent, and merge conflict resolution can be left to workers (Cursor, Anthropic).
- Across all sources, one agent should write to one unit of work at a time. Parallel writers on shared files or a shared task fail (kernel bug, Flappy Bird, Claude Code docs on same-file overwrites).

### Gaps
- No source gives a controlled A/B comparison of flat versus hierarchical topologies at the same scale and task. The Cursor evidence is qualitative.

---

## Q3. How did they keep quality high (tests as oracle, CI gates, reviewer and judge agents, linters, human checkpoints)?

### Takeaway
The decisive quality lever is an external, near-perfect oracle: test suites, a reference implementation such as GCC, or browser-driven end-to-end checks. The next levers are CI gates that forbid regressions, then separate fresh-context reviewer or evaluator agents tuned to be skeptical, and mechanical architectural enforcement instead of prose rules.

### Cited Findings
- Tests had to be "near-perfect", because otherwise Claude solves the wrong problem. Carlini sourced compiler test suites and wrote verifiers and build scripts for open-source packages — [Anthropic compiler, 2026-02-05](https://www.anthropic.com/engineering/building-c-compiler)
- New features kept breaking existing ones late in the project. The fix was a CI pipeline and stricter enforcement so commits could not break existing code — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- GCC served as a known-good oracle for differential testing (Q5) — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- Claude marked features complete after unit tests or `curl` checks without end-to-end verification. Prompting it to test as a human user with Puppeteer MCP greatly improved results. Limits remain: the model's vision is limited, and Puppeteer cannot see browser-native alert modals — [Anthropic harnesses, 2025-11-26](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- The feature list is JSON, not Markdown, because models are less likely to improperly edit JSON. Coding agents may only flip the `passes` field — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Separate evaluator: "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work". Out of the box, Claude was a poor QA agent. It found real issues, talked itself into approving them, and tested superficially. The team tuned the evaluator prompt over several rounds against human judgments. The evaluator uses hard thresholds per criterion, and failing any one fails the sprint — [Anthropic harness design, 2026-03-24](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- The evaluator is worth its cost only when the task sits beyond what the current model reliably does alone. With Opus 4.6 it moved to a single pass at the end — [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- Cursor uses a Judge agent at the end of each cycle to decide whether to continue. The Solo to React migration passed CI but "still needed careful review" — [Cursor, 2026-01-14](https://cursor.com/blog/scaling-agents)
- Clean-context reviewer: the review agent sees only the diff and none of the coder's context. Coder and reviewer iterate until most bugs are fixed, before a human opens the PR. "Clean context leads to a notable improvement in capabilities". Devin Review averages about 2 bugs per PR, about 58% severe — [Cognition, 2026-04-22](https://cognition.com/blog/multi-agents-working)
- At OpenAI, review moved almost entirely to agent-to-agent, and human review is optional — [OpenAI it-IT](https://openai.com/it-IT/index/harness-engineering/). Architectural rules are mechanically enforced through CI and linters rather than review. Without mechanical enforcement, agents drifted into inconsistent patterns. The review bottleneck shifts from "is the code correct" to "does it match intent" — secondary: [second-brain summary](https://second-brain-nuxt.vercel.app/harness-engineering-leveraging-codex-in-an-agent-first-world)
- A single large AGENTS.md cannot be checked mechanically, so the docs are kept as a structured, verifiable system of record — [OpenAI (search excerpt)](https://openai.com/index/harness-engineering/)
- Claude Code agent teams expose quality-gate hooks. `TeammateIdle`, `TaskCreated` and `TaskCompleted` hooks can block with exit code 2 and send feedback, for example to refuse task completion until tests pass — [Claude Code docs](https://code.claude.com/docs/en/agent-teams)
- Gas Town's Refinery checks output with review presets and the project CLAUDE.md. "Sweeps", sampled review waves such as a 60-minute review sweep, correct architectural drift by filing new Beads. heise recommends static quality gates such as fitness functions and static analysis — [heise, 2026-02-21](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)
- For the research system, an LLM judge with a single rubric prompt (0.0 to 1.0 plus pass/fail) matched human judgment best. Humans still caught issues automation missed. For stateful workflows, evaluate the end state, not the path — [Anthropic research, 2025-06-13](https://www.anthropic.com/engineering/multi-agent-research-system)
- Counter-evidence: the Cursor browser reportedly failed to compile on main, with CI red. Throughput without a hard green-CI gate on the main branch produced unverifiable output — [The Register, 2026-01-22](https://www.theregister.com/2026/01/22/cursor_ai_wrote_a_browser/)

### Inferences
- Quality enforcement in successful cases is layered: (1) an oracle or test suite, (2) a CI no-regression gate on the shared branch, (3) a separate skeptical reviewer with fresh context and hard thresholds, (4) mechanical architecture and lint rules, (5) humans on intent rather than line-by-line correctness.
- Self-evaluation is consistently unreliable (Anthropic, Cognition). Reviewer independence (separate agent, clean context, ideally a different prompt or model) matters more than reviewer count.

### Gaps
- OpenAI's specific linters, layer rules and doc-gardening agents are unverified (403).
- There are no quantitative defect-rate comparisons with versus without reviewer agents, beyond Cognition's bugs-per-PR figure.

---

## Q4. How did they keep continuity across context windows and sessions?

### Takeaway
The cases keep continuity outside the model, in the repo itself: git history with descriptive commits, a progress log, a structured JSON feature or task list, an `init.sh` or run script, and short map-style docs. Fresh context resets with structured handoff beat in-place compaction for older models. Stronger models (Opus 4.5 and later) reduced the need for resets, and periodic fresh starts still counter drift.

### Cited Findings
- The initializer creates `init.sh`, `claude-progress.txt` and the first git commit, then expands the prompt into a JSON feature list with 200+ entries. Each entry has a category, description, test steps and `passes: false` — [Anthropic harnesses, 2025-11-26](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Each coding-agent session does the same start-up: run `pwd`, read the git log and progress file, read the feature list and pick the highest-priority unfinished feature, then start the app via `init.sh` and run a basic end-to-end smoke test before new work, to catch broken states. It works on one feature per session, commits with descriptive messages, updates progress, and leaves a clean state "appropriate for merging to a main branch" — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Compaction alone was insufficient — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Context resets (a fresh agent with a structured handoff) versus compaction (in-place summary): Sonnet 4.5 showed "context anxiety", so resets were essential. Opus 4.5 "largely removed" it, so resets were dropped — [Anthropic harness design, 2026-03-24](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- The compiler loop restarts a fresh Claude Code session per task. Close to 2,000 sessions ran in 2 weeks, and state lives in git plus lock files plus logs. It keeps output short to avoid context pollution: a few printed lines, details in log files, errors tagged `ERROR` for grep, and precomputed summary stats — [Anthropic compiler, 2026-02-05](https://www.anthropic.com/engineering/building-c-compiler)
- Cursor workers start each iteration fresh after the Judge. "Periodic fresh starts are still needed to counter drift and tunnel vision" — [Cursor, 2026-01-14](https://cursor.com/blog/scaling-agents)
- At OpenAI, an AGENTS.md of about 100 lines serves as a map, and the `docs/` directory is the system of record. Secondary sources stress keeping all knowledge in the repository. Without repo-local context, agent assumptions compounded into architectural problems — [OpenAI (search excerpt)](https://openai.com/index/harness-engineering/); [second-brain summary](https://second-brain-nuxt.vercel.app/harness-engineering-leveraging-codex-in-an-agent-first-world)
- The research system's lead saves its plan to memory before the 200K-token truncation point. Agents summarize completed phases into external memory and spawn fresh subagents when context runs low. It resumes from checkpoints rather than restarting, and uses "rainbow deployments" so updates don't kill running agents — [Anthropic research, 2025-06-13](https://www.anthropic.com/engineering/multi-agent-research-system)
- Cognition 2025 recommends a dedicated model to compress history into key details, events and decisions, which is "hard to get right". Cognition fine-tuned smaller models for it — [Cognition, 2025-06-12](https://cognition.com/blog/dont-build-multi-agents)
- Gas Town: Beads, a git-backed issue tracker with hash IDs, holds all tasks. A "handoff" synchronously transfers work state to a new instance when context reaches a critical fill level. Stuck Polecats are replaced "without losing the context from the last session". heise reports quality drops noticeably at about 60% context fill on a 200K window — [heise, 2026-02-21](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html); Beads described in [search summaries](https://ascii.co.uk/news/article/news-20260125-f25263de/steve-yegges-gas-town-reveals-agent-orchestration-design-pat)
- Claude Code agent teams persist the task list at `~/.claude/tasks/{team}/` after the session ends. In-process teammates are not restored by `/resume` or `/rewind`, and task status can lag, blocking dependents — [Claude Code docs](https://code.claude.com/docs/en/agent-teams)

### Inferences
- A practical continuity kit: a machine-checkable task list whose status agents can change but not rewrite, an append-only progress log, git as the authoritative history, a one-command environment boot, a mandatory start-of-session smoke test, and a short map document linking to deeper docs.
- Treat agent sessions as disposable and keep durable state in files or git. Every system that survived restarts (compiler loop, Gas Town, Cursor iterations) depends on this.

### Gaps
- No source quantifies how much continuity artifacts improve outcomes (for example, completion rate with versus without progress files).

---

## Q5. Which failure modes were reported, and how were they fixed?

### Takeaway
The recurring failures are: duplicate work and agents overwriting each other on a shared monolithic task, regressions from parallel changes, lock contention and risk aversion under flat coordination, premature "done" and stubbed features, lenient self-review, context pollution and time blindness, drift and tunnel vision on long runs, and cross-agent assumption mismatch. Each has a documented engineering fix.

### Cited Findings
- **All agents fixing the same bug and overwriting each other (kernel build).** Fix: use GCC as an oracle. Compile a random subset of kernel files with GCC and the rest with the agent compiler, so different agents hit different bugs. Use delta debugging to find file pairs that fail together but pass apart — [Anthropic compiler, 2026-02-05](https://www.anthropic.com/engineering/building-c-compiler)
- **New features breaking existing functionality.** Fix: a CI pipeline with stricter enforcement so commits cannot break existing code — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- **Context pollution.** Fix: print minimal output, log details to files, add grep-able `ERROR` tags and precomputed summaries — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- **Time blindness (an agent running full slow suites).** Fix: a `--fast` flag that runs a deterministic 1% or 10% random sample per agent, varied across VMs so all files get covered collectively — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- **Frequent merge conflicts.** They were tolerated, and agents resolved them on pull and merge — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler). At Cursor, hundreds of workers pushed to one branch "with minimal conflicts" once a hierarchy existed — [Cursor, 2026-01-14](https://cursor.com/blog/scaling-agents)
- **Lock contention ("20 agents performed like 2 or 3") and locks orphaned by crashed agents.** Fix: abandon shared-lock self-coordination — [Cursor](https://cursor.com/blog/scaling-agents)
- **Risk aversion and churn under optimistic concurrency.** Fix: planners own task creation, and workers own complete tasks without coordinating — [Cursor](https://cursor.com/blog/scaling-agents)
- **Integrator bottleneck.** Fix: remove the role and let workers resolve their own conflicts — [Cursor](https://cursor.com/blog/scaling-agents)
- **Drift, tunnel vision, and agents running far too long.** Fix: a judge per cycle plus fresh starts. The issue is still open — [Cursor](https://cursor.com/blog/scaling-agents)
- **Model-specific early stopping and shortcuts.** Opus 4.5 "tended to stop early and take shortcuts" in Cursor's harness. Fix: pick the model per role (GPT-5.2 for planning and long runs) — [Cursor](https://cursor.com/blog/scaling-agents)
- **One-shotting, running out of context mid-feature, premature "done", and undocumented broken state.** Fix: an initializer-built JSON feature list, one feature per session, a commit and progress note at each session end, and a smoke test at each session start — [Anthropic harnesses, 2025-11-26](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Marking done after only unit tests or curl.** Fix: browser-automation end-to-end checks — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Lenient self-evaluation, stubbed features and superficial QA.** For example, DAW audio recording was stub-only. Fix: a separate skeptical evaluator with hard thresholds, calibrated against human judgment, plus negotiated sprint contracts on what "done" means — [Anthropic harness design, 2026-03-24](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **Planner over-specification cascading errors.** Fix: the planner states deliverables, the what and why, not granular how. Without a planner, the generator under-scoped — [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps). The granular-detail cascade appears only in a secondary write-up — [understandingdata](https://understandingdata.com/posts/generator-evaluator-harness-design/)
- **Over-simplifying the harness.** A radical simplification failed to match the original. Fix: remove components one at a time to find which are load-bearing — [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **Subagents misreading tasks and inconsistent implicit decisions (Flappy Bird).** Fix: share full traces, or use a single writer — [Cognition, 2025-06-12](https://cognition.com/blog/dont-build-multi-agents); [Cognition, 2026-04-22](https://cognition.com/blog/multi-agents-working)
- **Over-prescriptive managers, children assuming shared state, and no cross-agent communication by default** — [Cognition, 2026-04-22](https://cognition.com/blog/multi-agents-working)
- **Over-spawning: 50 subagents for simple queries, and duplicated work from vague briefs.** Fix: detailed briefs covering objective, output format, tools and boundaries, plus effort-scaling rules (1 agent for simple, 2 to 4 for comparisons, 10+ for complex). A tool-testing agent rewrote bad tool descriptions and cut completion time by 40% — [Anthropic research, 2025-06-13](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Same-file overwrites, task status lag, and a lead declaring done early or doing the work itself.** Fix: file ownership per teammate, manual nudges, and "Wait for your teammates" prompts — [Claude Code docs](https://code.claude.com/docs/en/agent-teams)
- **Duplicate work, merge conflicts, forgotten design decisions (such as "three or four logging libraries" in one codebase) and accumulating misconceptions ("Heresies").** Fix: Beads as a single task source, Refinery review, drift-correcting sweeps, rule files and static gates — [heise, 2026-02-21](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)
- **Unverifiable output at scale: the browser fails to compile and main CI is red** — [The Register, 2026-01-22](https://www.theregister.com/2026/01/22/cursor_ai_wrote_a_browser/)
- **Human cost.** heise notes that many developers report less job satisfaction because they mostly review AI code — [heise](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)

### Inferences
- Most fixes do not change the agents themselves. They change the environment: oracles, partitioning, CI gates, task-list schema, log hygiene and fresh contexts. This matches OpenAI's framing of the work as "harness engineering".

### Gaps
- Cursor gave no failure statistics, such as the share of worker tasks reverted or the rate of judge rejections.

---

## Q6. Which cross-case practices emerge for quality, throughput, stability and long-running continuity?

### Takeaway
Across cases: run many disposable single-writer workers on independently verifiable tasks, fed by a planner or oracle. Gate the shared branch with CI and a fresh-context skeptical reviewer or evaluator. Keep all durable state (tasks, progress, decisions, docs) in the repo in machine-checkable form. Restart contexts often. Add structure only where it is load-bearing, and remove it as models improve.

### Cited Findings (supporting evidence for each practice)
- **Oracle first:** near-perfect tests or a reference implementation are prerequisites for autonomous parallelism — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- **Partition work so agents hit different failures,** using random oracle subsets and delta debugging — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler)
- **Hierarchy for task generation, independence for execution:** planners and sub-planners, workers that don't coordinate, a judge per cycle, no integrator — [Cursor](https://cursor.com/blog/scaling-agents)
- **Single writer per unit,** with any number of read-only contributors and reviewers — [Cognition 2026](https://cognition.com/blog/multi-agents-working); file ownership per teammate in [Claude Code docs](https://code.claude.com/docs/en/agent-teams)
- **Clean-context reviewer or evaluator, tuned skeptical, with hard thresholds** — [Cognition 2026](https://cognition.com/blog/multi-agents-working); [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **CI no-regression gate on the shared branch** — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler); the counter-example is [The Register on Cursor](https://www.theregister.com/2026/01/22/cursor_ai_wrote_a_browser/)
- **Mechanical enforcement over prose:** a short AGENTS.md map plus a docs/ system of record, with rules in linters and CI — [OpenAI (excerpt)](https://openai.com/index/harness-engineering/); [second-brain summary](https://second-brain-nuxt.vercel.app/harness-engineering-leveraging-codex-in-an-agent-first-world)
- **Structured, schema-locked task state:** a JSON feature list where agents may only flip `passes`. Claude Code's file-locked task list with dependencies. Beads as a git-backed tracker — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents); [Claude Code docs](https://code.claude.com/docs/en/agent-teams); [heise](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)
- **A session protocol** (orient → read log and tasks → boot → smoke test → one task → commit → update progress) — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Context hygiene:** terse tool output, logs to files, sampled fast tests, and handoff at about 60% fill — [Anthropic compiler](https://www.anthropic.com/engineering/building-c-compiler); [heise](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html)
- **Supervision and self-healing:** a Deacon or Witness that restarts stuck or zombie agents. Checkpoint and resume rather than restart — [heise](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html); [Anthropic research](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Right-size the team:** start with 3 to 5 teammates and 5 to 6 tasks each. Effort-scaling rules in the lead prompt — [Claude Code docs](https://code.claude.com/docs/en/agent-teams); [Anthropic research](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Model per role:** use the best long-horizon model for planners and long runs, and a strong primary when escalating to a "smart friend" — [Cursor](https://cursor.com/blog/scaling-agents); [Cognition 2026](https://cognition.com/blog/multi-agents-working)
- **Prompts as the main lever:** "the prompts matter more" — [Cursor](https://cursor.com/blog/scaling-agents)
- **Budget for 15x to 20x+ token cost,** and use multi-agent only when task value justifies it — [Anthropic research](https://www.anthropic.com/engineering/multi-agent-research-system); [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- **Re-evaluate the harness on each model release.** Stripping sprints and resets worked with Opus 4.5 and 4.6, and components should be removed one at a time — [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps)

### Inferences
- For a Kandev-style workflow (task board plus per-task agent sessions plus worktrees), the evidence suggests:
  - Planner or decomposer tasks that create independent child tasks with explicit acceptance tests.
  - One worktree and one writer per task.
  - A required CI-green merge gate.
  - A separate reviewer session started with only the diff and the acceptance criteria.
  - A per-repo progress log, task JSON and AGENTS.md map that each new session reads first.
  - A watchdog for stuck sessions.
  - Periodic "sweep" or cleanup tasks for drift.
- These are inferences from the cited cases. No source evaluated Kandev itself.

### Gaps
- There is no rigorous published benchmark comparing these practices head-to-head. Most evidence is single-organization experience reports, often by vendors with commercial interest (Cursor, Cognition, Anthropic, OpenAI).
