# Token Efficiency, Context Engineering, and Reliability in Multi-Agent LLM Coding Systems

Research date: 2026-11-08. Publication dates are given in brackets. Unless a line says otherwise, every figure below comes from the linked primary source. Lines marked "(derived)" are my own arithmetic.

## Q1. Measured token costs of multi-agent vs single agent, and when parallelism is worth it

### Takeaway
Multi-agent setups multiply token spend. Anthropic measured about 4x chat tokens for a single agent and about 15x for multi-agent. Google/MIT-style controlled studies measured 1.6x to 6.2x the tokens of a single agent at matched performance. Multi-agent pays off only on tasks that split into breadth-first, independent parts, such as research or decomposable analysis. On sequential or tightly coupled work, which covers most coding, it is neutral or harmful. On SWE-bench Verified, every multi-agent variant scored slightly below a single agent.

### Cited Findings
**Anthropic, multi-agent research system [2025-06-13]**
- Agents use about 4x more tokens than chat. Multi-agent systems use about 15x more tokens than chat. — [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- On BrowseComp, token usage alone explained 80% of performance variance. Number of tool calls and model choice explained most of the rest, for 95% in total. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Moving to a better model (Sonnet 4) gave a bigger gain than doubling the token budget on Sonnet 3.7. Model quality acts as a multiplier on token efficiency. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- An Opus 4 lead with Sonnet 4 subagents beat single-agent Opus 4 by 90.2% on Anthropic's internal research eval. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Parallelism (3-5 subagents, each running 3+ tools in parallel) cut research time by up to 90% on complex queries. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- When multi-agent fits: high-value tasks with heavy parallelization, information that exceeds a single context window, and many complex tools. When it does not fit: "most coding tasks", which have fewer truly parallelizable parts, and tasks needing shared context or many dependencies between agents. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Effort-scaling rules written into the prompt:
  - Simple fact-finding: 1 agent, 3-10 tool calls.
  - Comparisons: 2-4 subagents, 10-15 calls each.
  - Complex research: more than 10 subagents.
  - An early failure mode was "spawning 50 subagents for simple queries". — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)

**Kim et al., "Towards a Science of Scaling Agent Systems" [arXiv 2512.08296; v1 2025-12-09, v3 2026-04-08]**
- Setup: 260 configurations, 5 architectures (single-agent, plus Independent, Centralized, Decentralized, and Hybrid multi-agent), 3 LLM families, 6 benchmarks (BrowseComp-Plus, Finance-Agent, PlanCraft, WorkBench, SWE-bench Verified, Terminal-Bench). — [arXiv abs](https://arxiv.org/abs/2512.08296); [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- Token overhead vs single agent: Independent +58%, Decentralized +263%, Centralized +285%, Hybrid +515%. — [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- Success per 1K tokens: single agent 67.7, Independent 42.4, Decentralized 23.9, Centralized 21.5, Hybrid 13.6. Efficiency scores were 0.466 for single agent vs 0.074-0.234 for multi-agent, a 2-6x efficiency penalty. — [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- Performance change vs single agent:
  - Finance-Agent (decomposable): Centralized +80.8%.
  - PlanCraft (sequential): -39% to -70%.
  - SWE-bench Verified: Hybrid -2.1%, Centralized -3.1%, Decentralized -5.4%, Independent -14.9%.
  - Terminal-Bench: Centralized -19.2%, Independent +1.7%.
  - Mean multi-agent effect across all benchmarks: about -0.3%, with high variance. — [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- Capability saturation: once the single-agent baseline exceeds about 45%, adding agents gives diminishing or negative returns (β = -0.236, p = 0.004). — [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- Error amplification at trace level vs single agent: Independent 17.2x, Decentralized 7.8x, Hybrid 5.1x, Centralized 4.4x. A central orchestrator contains errors best. — [arXiv HTML v3](https://arxiv.org/html/2512.08296v3)
- A predictive model picks the best architecture for 87% of held-out configurations (cross-validated R² = 0.373-0.413). — [arXiv abs](https://arxiv.org/abs/2512.08296)
- The tool-coordination trade-off (tool-heavy tasks hurt more by multi-agent overhead) holds in direction but is not statistically significant in the six-benchmark model (p = 0.211). — [arXiv PDF](https://arxiv.org/pdf/2512.08296)

**Claude Code official cost guidance [costs page, current as of 2026-11]**
- Agent teams use about 7x more tokens than standard sessions when teammates run in plan mode, because each teammate keeps its own context window. Token usage is "roughly proportional to team size." — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Cognition (Devin), "Don't Build Multi-Agents" [2025-06-12, Walden Yan]**
- Principle 1: share context, meaning full agent traces, not just messages. Principle 2: actions carry implicit decisions, and conflicting decisions produce bad results. — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)
- Flappy Bird example: two parallel subagents built a mismatched Mario-style background and a mismatched bird, leaving the final agent to reconcile them. — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)
- Recommends a single-threaded linear agent by default. For very long tasks it recommends a dedicated context-compression model; Cognition fine-tuned smaller models for this. — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)
- Notes that Claude Code subagents (as of June 2025) answer well-defined questions rather than write code, and never run in parallel with the main agent. Their benefit is keeping investigation out of the main history. — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)

### Inferences
- The two sources agree. Anthropic's 15x and Kim et al.'s 1.6-6.2x both mean multi-agent only pays when the task's value is high and its parts are independent, since cost scales close to linearly with agent count.
- For coding agents, the SWE-bench and Terminal-Bench numbers point to a default of one strong agent that owns all code edits. Use subagents as read-only explorers, researchers, or verifiers that return summaries. Parallelize code writing only across truly independent units (separate worktrees or modules), with a centralized orchestrator that verifies.
- The 45% saturation finding suggests skipping multi-agent orchestration when a single strong model already solves the task class reasonably well. The extra tokens buy little there.

### Gaps
- No primary source found for per-task token counts of named coding frameworks (ChatDev, MetaGPT) in 2024-2026. Older ChatDev-era cost claims (e.g., "under $1 per app") were not verified here.
- The Anthropic 4x/15x figures come from research tasks, not coding. I found no equivalent Anthropic-published multiplier for coding sessions beyond the agent-teams ~7x figure.

## Q2. Context engineering techniques that cut tokens while keeping quality

### Takeaway
Effective techniques are mostly about what enters the context:
- subagents as context firewalls returning 1-2K-token summaries
- compaction and tool-result clearing
- notes and progress files on disk
- just-in-time retrieval by file path, grep, or glob
- stable, append-only prefixes for KV-cache hits
- keeping always-loaded files small, with detailed workflows moved to on-demand skills

Evidence from ICLR 2026 shows that bloated or LLM-generated AGENTS.md files raise cost by more than 20% without raising success.

### Cited Findings
**Context rot and attention budget**
- Anthropic [2025-09-29] defines context rot: as the context grows, recall accuracy falls across all models. It frames context as a finite "attention budget" (n² pairwise token relationships). — [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Chroma tested 18 LLMs, including GPT-4.1, Claude 4, Gemini 2.5, and Qwen3 [2025-07-14, Hong, Troynikov, Huber]:
  - Performance becomes less reliable as input length grows, and models do not use their context uniformly.
  - Low needle-question similarity degrades faster.
  - Even one distractor hurts, and four compound the drop.
  - Surprisingly, shuffled haystacks beat logically coherent ones. — [Chroma: Context Rot](https://www.trychroma.com/research/context-rot)
- Chroma LongMemEval: focused prompts (~300 tokens) scored significantly higher than full prompts (~113K tokens) for all models. Claude showed the biggest gap, mostly from abstaining. GPT models hallucinated most when distractors were present. — [Chroma: Context Rot](https://www.trychroma.com/research/context-rot)

**Subagents as context firewalls**
- Subagents explore with tens of thousands of tokens but return condensed summaries of about 1,000-2,000 tokens. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Claude Code docs: delegate verbose operations (running tests, fetching docs, processing logs) to subagents so only a summary returns. Subagent requests still cost tokens, so give them a smaller model (`model: haiku`). — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Subagents can write outputs to external storage or the filesystem and return lightweight references. This cuts information loss and the token cost of passing outputs through the lead agent (the "telephone game"). — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)

**Compaction and tool-result clearing**
- Compaction: summarize near the context limit, first maximizing recall, then trimming for precision. Tool-result clearing is the lightest-touch form. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- After compaction, Claude Code continues with the summary plus the five most recently accessed files. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- In Claude Code, `/compact` is itself a large request because it reads the whole conversation. `/clear` costs nothing, so clear between unrelated tasks. Custom compaction instructions (e.g., "focus on test output and code changes") can go in CLAUDE.md. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Compaction alone was not enough for multi-context-window app building. Anthropic added external progress artifacts. — [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

**Structured notes and file-based handoffs**
- Use a NOTES.md or to-do file as persistent memory outside the context window. In Claude Plays Pokémon, notes let the agent resume across context resets over thousands of steps. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Long-running harness [2025-11-26]:
  - An initializer agent writes `init.sh`, `claude-progress.txt`, a JSON feature list (200+ features, all initially failing), and an initial git commit.
  - Each later session reads git log and progress files and picks one feature.
  - JSON was chosen because the model is less likely to overwrite it inappropriately than Markdown. — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Manus [2025-07-18]: treat the file system as unlimited external memory. Compression should be restorable, so keep a URL or path and drop the content. "Recitation" means keeping and constantly updating `todo.md` so goals stay in recent attention. — [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- The lead agent saves its plan to memory because context beyond 200K tokens gets truncated. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Counterpoint: Cognition argues for sharing full traces rather than summaries when agents must make consistent decisions. — [Cognition blog](https://cognition.com/blog/dont-build-multi-agents)

**Just-in-time retrieval vs preloading**
- Just-in-time: keep lightweight identifiers (paths, queries, links) and load at runtime through tools. It is slower but more autonomous.
- Hybrid: Claude Code preloads CLAUDE.md and uses glob/grep just in time. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Code-intelligence (LSP) plugins replace grep plus multiple file reads with a single go-to-definition call, reducing unnecessary reads. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Tool-output trimming and tool design**
- Hooks can preprocess output, e.g., grep a 10,000-line log for ERROR, "reducing context from tens of thousands of tokens to hundreds". The docs include a PreToolUse hook that filters test output down to failures. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Tools should return token-efficient information with minimal functional overlap: "If a human engineer can't definitively say which tool should be used ... an AI agent can't be expected to do better." — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- MCP tool definitions are deferred by default (only names enter context). CLI tools (`gh`, `aws`) are more context-efficient than MCP servers. Disable unused servers. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- A tool-testing agent rewrote flawed MCP tool descriptions and cut later agents' task completion time by 40%. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- For SWE-bench, Anthropic "spent more time optimizing our tools than the overall prompt". Requiring absolute file paths eliminated a class of errors. — [Anthropic: Building effective agents (2024-12-19)](https://www.anthropic.com/engineering/building-effective-agents)

**Prompt caching and stable prefixes**
- Manus calls KV-cache hit rate "the single most important metric for a production-stage AI agent". Its input:output ratio is about 100:1, with about 50 tool calls per task on average. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- Manus cache practices:
  - No timestamps at the start of the prompt, since one token change invalidates everything after it.
  - Keep the context append-only.
  - Use deterministic JSON serialization.
  - Mask tools with logits instead of adding or removing tool definitions mid-task. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- Claude API cache mechanics:
  - Prefix order is tools → system → messages. A change at one level invalidates that level and all later ones.
  - Changing tool definitions invalidates everything.
  - Changing thinking or effort parameters invalidates the message blocks.
  - Up to 4 breakpoints per request.
  - Default TTL is 5 minutes, refreshed on each hit. A 1-hour TTL is optional. — [Claude prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Claude Code's `/usage` shows a "Prompt cache (main)" line with the share of input from cache. The docs example shows "91% of input tokens from cache". It also reports misses and their likely cause (e.g., "tool definitions changed"), plus expected rebuilds after compaction or tool-result clearing. The first message after a break longer than the TTL misses and reprocesses the full context. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Model tiering**
- Use Sonnet for most coding and reserve Opus for complex architecture or multi-step reasoning. Use `model: haiku` for simple subagents and Sonnet for agent-team teammates. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Anthropic's research system used an Opus lead with Sonnet subagents. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Lower `/effort` or thinking budgets for simple tasks. Thinking tokens bill as output, and the default budget can be tens of thousands of tokens per request. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Skills, progressive disclosure, and CLAUDE.md/AGENTS.md sizing**
- Move workflow-specific instructions from CLAUDE.md into skills, which load on demand. "Aim to keep CLAUDE.md under 200 lines". `/usage` recommendations flag oversized files (example: "Trim ~/code/api/CLAUDE.md · 49k tokens per request"). — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Spawned teammates automatically load CLAUDE.md, MCP servers, and skills. Every token in the spawn prompt adds to each teammate's starting context. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Gloaguen, Mündler, Müller, Raychev, Vechev (ETH/LogicStar), "Evaluating AGENTS.md" [arXiv 2602.11988, 2026-02-12; ICLR 2026]:
  - LLM-generated context files reduced success by about 0.5% on SWE-bench Lite and about 2% on AgentBench.
  - Developer-written files gave only about 4% improvement.
  - Both types raised inference cost by more than 20%.
  - Agents follow the files' instructions, which broadens exploration (more tests, more traversal) without more resolved tasks.
  - Agents tested: Claude Code/Sonnet-4.5, Codex/GPT-5.2 and GPT-5.1 Mini, Qwen Code. — [arXiv 2602.11988](https://arxiv.org/abs/2602.11988)
  - A secondary write-up reports +3.92 steps and +23% cost per task. This is unverified against the paper. — [arxiviq summary](https://arxiviq.substack.com/p/evaluating-agentsmd-are-repository)
- System prompts should sit at the "right altitude": start minimal and add instructions only for observed failure modes. — [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

**Prompting efficiency**
- Specific prompts avoid broad scanning. Plan mode prevents expensive rework. Course-correct early with Esc or `/rewind`. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Each delegated subagent needs an objective, an output format, tool and source guidance, and task boundaries. Vague delegation caused duplicated work and gaps. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)

### Inferences
- For a Kandev-style orchestrator, the cheapest high-impact levers are likely these:
  - Keep a stable, byte-identical system/tool prefix shared across tasks, with no timestamps or reordered tool lists, so caching works.
  - Hand off between agents through files (spec, progress JSON, summary), not full transcripts.
  - Cap subagent return size at about 1-2K tokens.
  - Keep AGENTS.md/CLAUDE.md small and repo-specific, and move workflow detail into skills.
- Changing models or tool sets between steps of one agent session invalidates the cache. Model tiering is cheapest at agent boundaries (separate subagents), not mid-conversation.
- Chroma's distractor results suggest that trimming tool output, such as passing only test failures, improves accuracy as well as cost.

### Gaps
- LangChain/LangGraph context-engineering posts (write/select/compress/isolate framing) were not fetched. That framing is not verified here.
- OpenAI caching economics (automatic caching discount levels and thresholds) were not fetched. Check the current OpenAI docs before citing them.
- No controlled study found on file-based handoffs vs full-transcript handoffs for coding agents. The evidence is practitioner reports from Anthropic, Manus, and Cognition, and they partly disagree.

## Q3. Academic findings on why multi-agent systems fail, plus related evidence (debate, voting, agent PRs, long context)

### Takeaway
Most multi-agent failures come from system design and specification, inter-agent misalignment, and weak verification, not from model capability alone. MAST found 41-86.7% failure rates across 7 open-source frameworks. Multi-agent debate rarely beats cheap self-consistency or majority voting at equal compute. In the wild, agent-authored GitHub PRs are merged less often than human PRs, except for documentation.

### Cited Findings
**MAST: Cemri, Pan, Yang, ... Zaharia, Gonzalez, Stoica (UC Berkeley), "Why Do Multi-Agent LLM Systems Fail?" [arXiv 2503.13657; v1 2025-03-17, v3 2025-10-26]**
- Built from 150 traces and validated on 1,600+ annotated traces (MAST-Data, 1,642 traces) across 7 frameworks: ChatDev, MetaGPT, HyperAgent, AppWorld, AG2, Magentic-One, OpenManus. Human inter-annotator κ = 0.88. — [arXiv abs](https://arxiv.org/abs/2503.13657)
- Failure rates across the 7 open-source frameworks ranged from 41% to 86.7%. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- 14 failure modes in 3 categories, with share of failures:
  - **FC1 System design / specification**: disobey task spec 11.8%, disobey role spec 1.5%, step repetition 15.7%, loss of conversation history 2.8%, unaware of termination conditions 12.4%.
  - **FC2 Inter-agent misalignment**: conversation reset 2.2%, fail to ask for clarification 6.8%, task derailment 7.4%, information withholding 0.85%, ignored other agent's input 1.9%, reasoning-action mismatch 13.2%.
  - **FC3 Task verification**: premature termination 6.2%, no or incomplete verification 8.2%, incorrect verification 9.1%. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
  - Category totals (derived from the mode shares): FC1 ≈ 44%, FC2 ≈ 32%, FC3 ≈ 24%.
- An LLM-as-judge annotator (o1, few-shot) reached accuracy 0.94 and κ = 0.77. On unseen systems and benchmarks it reached κ = 0.79. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- Interventions on ChatDev with the same GPT-4o model:
  - Better role specs plus giving the CEO the final say: +9.4% task success.
  - Adding a high-level task-objective verification step: +15.6% on ProgramDev. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- MetaGPT vs ChatDev: MetaGPT had 60-68% fewer FC1/FC2 failures but 1.56x more FC3 (verification) failures. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- Framework-specific patterns:
  - HyperAgent: mostly step repetition and incorrect verification.
  - OpenManus: step repetition.
  - AppWorld: premature termination, possibly due to its star topology. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- Conclusions:
  - Verifiers help, but many perform only superficial checks, so multi-level verification is needed.
  - Better base models alone are conjectured to be insufficient.
  - The same model performs differently under different system designs. — [arXiv HTML v3](https://arxiv.org/html/2503.13657v3)

**Debate, voting, and "more agents"**
- Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet" (2023; ICLR 2024), GSM8K:
  - At 3 responses, debate scored 83.2% vs self-consistency 82.5%.
  - At 9 responses, debate scored 83.0% vs self-consistency 88.2%.
  - The gains were attributed to self-consistency, not to correction. — [arXiv 2310.01798](https://arxiv.org/pdf/2310.01798)
- "Stop Overvaluing Multi-Agent Debate" (originally titled "If Multi-Agent Debate is the Answer, What is the Question?") [arXiv 2502.08788, 2025]: MAD methods fail to reliably beat CoT and self-consistency even with more inference compute. — [arXiv 2502.08788](https://arxiv.org/abs/2502.08788v3)
- "Talk Isn't Always Cheap" [arXiv 2509.05396, 2025]: debate can degrade performance relative to majority voting, especially with heterogeneous agents. — [arXiv 2509.05396](https://arxiv.org/html/2509.05396v2)
- Smit et al., "Should we be going MAD?" (ICML 2024): debate does not reliably outperform self-consistency. — [arXiv 2311.17371](https://arxiv.org/html/2311.17371v3)
- Li et al., "More Agents Is All You Need" [arXiv 2402.05120, Feb 2024; TMLR]: plain sampling-and-voting ("Agent Forest") makes performance scale with the number of agents, and gains grow with task difficulty. The method is orthogonal to other enhancements. — [arXiv 2402.05120](https://arxiv.org/abs/2402.05120)

**Agent-authored PRs on GitHub: AIDev dataset [Li, Zhang, Hassan; arXiv 2507.15003, 2025-07-20; data cutoff 2025-06-22]**
- Scale: 456,535 agent PRs, 61,453 repos, 47,303 developers. Agents: OpenAI Codex, Devin, GitHub Copilot, Cursor, Claude Code. — [arXiv 2507.15003](https://arxiv.org/html/2507.15003v1)
- Merge rates in AIDev-pop (repos with >500 stars): humans 76.8%, Codex 65.3%, Claude Code 52.5%, Cursor 51.4%, Devin 48.9%, Copilot 38.2%. The paper's text gives slightly different values (64%, 49%, 35%) from its table. — [arXiv 2507.15003](https://arxiv.org/html/2507.15003v1)
- Documentation PRs are the exception: Codex 88.6% and Claude Code 85.7% vs humans 76.5%. Feature, fix, and performance PRs lag humans by 15-40 percentage points. — [arXiv 2507.15003](https://arxiv.org/html/2507.15003v1)
- Agent PRs are structurally simpler: only 9.1% change cyclomatic complexity vs 23.3% of human PRs. One developer opened 164 Codex PRs in about 4 days, against 176 human PRs over 3.5 years. — [arXiv 2507.15003](https://arxiv.org/html/2507.15003v1)
- 58.2% of agent PRs had no explicit review (vs 75.3% for humans). Bot reviewers appeared on 20.1% of agent PRs. — [arXiv 2507.15003](https://arxiv.org/html/2507.15003v1)
- Later studies using different subsets and closed-PR denominators [2026-02] report higher rates: Codex 77.9%, Cursor 74.5%, Claude Code 71.9%, Copilot 68.0%, Devin 61.6%, overall 69.3%. — [arXiv 2602.08915](https://arxiv.org/html/2602.08915v1). A task-level study ranks Codex highest (0.83) and Copilot lowest (0.45). — [arXiv 2602.02345](https://arxiv.org/html/2602.02345v1). Numbers are not comparable across papers because subsets and denominators differ.

**Long-context degradation**
- See Chroma Context Rot (18 models) under Q2. Performance falls with input length even on simple tasks, and distractors compound the drop. — [Chroma](https://www.trychroma.com/research/context-rot)

### Inferences
- About 44% of MAST failures come from specification and system design, and about 24% from verification. For a coding orchestrator, the cheapest fixes are likely explicit role and task specs, explicit termination conditions, and an objective-level verifier, as in ChatDev's +15.6%. Adding more agents is not one of them.
- If you need redundancy for correctness, sampling-and-voting or best-of-N with a deterministic test oracle is better supported than multi-agent debate.
- AIDev merge-rate gaps support the case for human or deterministic gates before merge. Agents do best on narrow, well-scoped tasks such as documentation.

### Gaps
- The specific Llama2-13B ensemble vs Llama2-70B claim from "More Agents" was not verified on the page I fetched.
- MAST's per-framework failure-rate figure was not in the extracted text. Only the 41-86.7% range is confirmed.
- I found no 2025-2026 study measuring cost (tokens or $) per merged agent PR.

## Q4. Reliability practices: verification loops, gates, checkpoints, budgets, stopping conditions, and avoiding reviewer-coder loops

### Takeaway
Reliable agent loops rest on four things:
- ground truth from the environment (tests, execution, browser E2E) rather than LLM opinion
- explicit, immutable acceptance criteria (a JSON feature list where only a `passes` field can change, and tests that may not be edited)
- incremental work with git checkpoints and progress files
- hard stopping conditions (iteration caps, spend caps)

MAST shows step repetition (15.7%) and unawareness of termination conditions (12.4%) are the two most common single failure modes, so loop limits are not optional.

### Cited Findings
- Agents should get "ground truth" from the environment at each step (tool results, code execution). "it's also common to include stopping conditions (such as a maximum number of iterations) to maintain control." Run extensive testing in sandboxes with guardrails, because errors compound. — [Anthropic: Building effective agents (2024-12-19)](https://www.anthropic.com/engineering/building-effective-agents)
- Evaluator-optimizer (generator plus critic loop) fits when evaluation criteria are clear and iteration measurably helps. — [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- Long-running coding harness [2025-11-26]:
  - Observed failure modes: one-shotting too much and running out of context mid-feature; prematurely declaring the project done; marking features complete without end-to-end tests.
  - Fixes: one feature per session; descriptive git commits so bad changes can be reverted; a progress file; the rule that editing or removing tests is unacceptable; a startup routine (pwd, read git log and progress, pick the top unfinished feature, run `init.sh` plus a basic E2E test before new work).
  - Claude verified end-to-end only when explicitly told to use browser automation (Puppeteer MCP). — [Anthropic harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- Production multi-agent reliability:
  - Resume from checkpoints after errors instead of restarting, combined with retry logic.
  - Use rainbow deployments so running long agents are not broken by updates.
  - Monitor decision patterns and interaction structure.
  - Subagents run synchronously, which creates bottlenecks. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Evaluation practice:
  - Start with about 20 real queries, since early effect sizes are large.
  - Use a single LLM-judge call with a rubric (factual accuracy, citation accuracy, completeness, source quality, tool efficiency) scoring 0.0-1.0 plus pass/fail.
  - Human testing still catches edge cases. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- MAST shows that verifiers often do only superficial checks (incorrect verification 9.1%, no or incomplete verification 8.2%) and recommends multi-level verification. — [MAST arXiv HTML v3](https://arxiv.org/html/2503.13657v3)
- Manus keeps failed actions and stack traces in context so the model updates its beliefs and avoids repeating mistakes. It adds structured variation to avoid few-shot "ruts", where the model copies repetitive patterns. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- Claude Code budget and stop controls:
  - `--max-budget-usd` CLI flag.
  - Workspace and org spend limits.
  - Per-user TPM/RPM recommendations (e.g., 200-300K TPM per user for 1-5 users).
  - At most three idle goal check-ins per goal, earlier uncapped.
  - Shut down teammates when done, since active teammates keep consuming tokens. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- Self-correction without external feedback does not reliably improve reasoning. Gains attributed to debate come from aggregation. — [Huang et al., arXiv 2310.01798](https://arxiv.org/pdf/2310.01798)
- Errors amplify 17.2x in independent multi-agent setups vs 4.4x with a centralized orchestrator that validates outputs. — [Kim et al., arXiv 2512.08296v3](https://arxiv.org/html/2512.08296v3)

### Inferences
- Avoid infinite reviewer-coder ping-pong with all of the following:
  - a hard iteration cap (e.g., N review rounds) plus a budget cap
  - a deterministic pass condition (tests, lint, typecheck green) that ends the loop regardless of reviewer opinion
  - reviewer findings limited to concrete, verifiable items
  - escalation to a human after the cap, not another round

  This is consistent with MAST's FM-1.3 and FM-1.5 and the evidence that LLM self-correction without external signals is weak.
- Make tasks idempotent and resumable: one task, one branch or worktree, one commit per verified unit, plus a machine-readable status file. A retry then restarts from the last checkpoint, not from scratch, matching Anthropic's checkpoint/resume practice.
- Put verification at the objective level (does the deliverable meet the original spec?) and not only at the unit level. MAST's ChatDev intervention (+15.6%) and Anthropic's E2E finding both point the same way.

### Gaps
- No peer-reviewed study found that quantifies optimal reviewer-coder iteration caps for coding agents.
- No quantitative data found on retry and checkpoint success rates in production coding-agent systems.

## Q5. Concrete numbers: cost per task and developer, cache hit rates, model-routing savings

### Takeaway
Claude Code usage averages about $13 per developer per active day ($150-250/month, under $30/day for 90% of users), up from a published $6/day before April 2026. Agent-style workloads are dominated by input tokens (~100:1 input:output at Manus), so cache reads at 0.1x the base input price, and lower on the newest Claude models, are the largest single cost lever. Learned routers report 35-85% savings at 95% of strong-model quality, depending on benchmark.

### Cited Findings
**Cost per developer**
- Claude Code: about $13 per developer per active day and $150-250 per developer per month, with 90% of users under $30 per active day (enterprise deployments). — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- The earlier published figure was $6 per day (90% under $12). Reporting says the page was updated around 2026-04-16. — [Shopifreaks report](https://www.shopifreaks.com/anthropic-more-than-doubles-its-public-estimate-of-average-daily-claude-code-spending-from-6-to-13-per-developer/) (secondary)
- The Claude Code docs example of `/usage` shows a session with 1.2K input, 5.3K output, 940K cache read, and 50K cache write tokens costing $0.55. Cache reads dominate token volume. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Cache economics**
- Cache write costs 1.25x base input (5-minute TTL) or 2x (1-hour TTL). Cache read costs 0.1x for most models, 0.05x for Opus 5.5 and Sonnet 5.5, and 0.025x for Fable/Mythos 5.1. — [Claude prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Selected prices, $ per million tokens:
  - Opus 5.5: input 4, 5-minute write 5, cache read 0.20, output 20.
  - Sonnet 5.5: input 2, cache read 0.10, output 10.
  - Sonnet 4.6: input 3, cache read 0.30, output 15.
  - Haiku 4.5: input 1, cache read 0.10, output 5. — [Claude prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Minimum cacheable prefix: 512 tokens on the newest models, 1,024-4,096 on older ones. Shorter prompts silently skip caching. — [Claude prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- Manus: cached $0.30/MTok vs uncached $3/MTok on Claude Sonnet (10x). Input:output ratio is about 100:1, with about 50 tool calls per task. — [Manus blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- Example cache hit rate shown in Claude Code docs: "91% of input tokens from cache" over 14 requests. This is an illustrative example, not a measured fleet average. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)

**Model routing**
- RouteLLM (LMSYS, 2024-07-01):
  - The matrix-factorization router reaches 95% of GPT-4 quality on MMLU with about 26% of calls going to GPT-4, about 48% cheaper than a random baseline.
  - With augmented data it uses about 14% GPT-4 calls, about 75% cheaper than random.
  - The README claims up to 85% cost reduction at 95% GPT-4 performance on MT-Bench. — [LMSYS RouteLLM blog](https://lmsys.org/blog/2024-07-01-routellm/); [RouteLLM GitHub](https://github.com/lm-sys/RouteLLM)
  - Secondary summaries cite about 45% savings on MMLU and 35% on GSM8K at 95% quality. — [smol.ai news](https://news.smol.ai/tags/llm-routing) (secondary)

**Token multipliers (recap)**
- Agents about 4x and multi-agent about 15x chat tokens. — [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system)
- Multi-agent overhead of 58-515% vs a single agent. — [arXiv 2512.08296v3](https://arxiv.org/html/2512.08296v3)
- Claude Code agent teams about 7x in plan mode. — [Claude Code: Manage costs](https://code.claude.com/docs/en/costs)
- AGENTS.md files add more than 20% cost. — [arXiv 2602.11988](https://arxiv.org/abs/2602.11988)

### Inferences (derived)
- With about 100:1 input:output and cache reads at 0.1x, a session at a 90% cache hit rate pays roughly 0.1 + 0.9 × 0.1 = 0.19x of uncached input cost on the input side (ignoring write premiums). That is about a 5x saving. A broken prefix (timestamp, reordered tools, model or effort switch) wipes it out.
- With Sonnet 5.5 input at $2 vs Opus 5.5 at $4 per MTok, and Haiku 4.5 at $1, tiering subagents by role (Haiku or Sonnet for exploration and log digestion, the strongest model for planning and final integration) roughly halves to quarters per-token cost on delegated work. Quality impact must be measured per task class.
- Routing savings from RouteLLM come from chat benchmarks, not agentic coding. Treat them as an upper-bound indication, not a coding-agent result.

### Gaps
- No published fleet-wide cache-hit-rate statistics for Claude Code or Codex were found.
- No primary source found for per-task (per-issue) dollar cost of coding agents on SWE-bench-style tasks in 2025-2026.
- OpenAI caching discounts and Codex pricing were not verified in this pass.
- The "$47,000 over 3 days from 23 unattended subagents" anecdote appeared only on a vendor blog and could not be verified, so it is excluded from the findings.
