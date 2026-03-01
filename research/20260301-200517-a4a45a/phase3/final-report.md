# Building a General-Purpose Eval Runner with Harbor and inspect-harbor

## Final Synthesis Report — March 1, 2026

---

## 1. Executive Summary

This report synthesizes findings from two independent AI research agents investigating how to build a general-purpose eval runner using Harbor and inspect-harbor — one that can mix and match different agent solvers against different benchmarks (Spider2, LongMemEval, and others).

**The most important findings:**

1. **There are two unrelated projects called "Harbor."** The original research prompt referenced `av/harbor`, which is a Docker Compose orchestration tool for local LLM stacks. The project relevant to building an eval runner is **`laude-institute/harbor`** (the Laude Institute's agent evaluation framework, documented at harborframework.com). `inspect-harbor` bridges exclusively to the latter. This disambiguation is the single most critical insight — building on the wrong "Harbor" would waste all engineering effort.

2. **The foundation already exists and is substantial.** Harbor (v0.1.45) + inspect-harbor (v0.4.5) provide a working eval pipeline with 47 curated benchmark datasets (~21,000+ tasks), containerized sandbox environments, standardized task format, scoring infrastructure, and the ability to plug in any Inspect AI solver. A general-purpose eval runner can start with significant coverage on day one.

3. **Spider2 is partially integrated; LongMemEval is not.** The Harbor registry includes `spider2-dbt@1.0` (64 tasks for dbt code generation), proving the adapter pattern for the Spider2 family. Full Spider2 text-to-SQL and LongMemEval both require custom adapter engineering — with LongMemEval posing fundamentally harder design challenges around ultra-long context management.

4. **The primary architecture risk is dual orchestration.** Harbor native (`harbor run`) and Inspect AI (`inspect eval` via inspect-harbor) are two different execution modes with different concurrency models, result formats, and debugging workflows. Pick one top-level executor per eval run; do not try to nest them.

5. **Custom engineering is concentrated in three areas:** (a) benchmark adapters for non-integrated datasets, (b) memory-capable solvers for long-context benchmarks, and (c) result normalization across execution modes.

---

## 2. Key Findings

### 2.1 Harbor Architecture (laude-institute/harbor)

Harbor (v0.1.45, Apache-2.0, 816 GitHub stars) is an open-source framework for evaluating AI agents in sandboxed container environments. It was created by the Laude Institute (the team behind Terminal-Bench).

**Core Abstractions:**

| Concept | Description |
|---------|-------------|
| **Task** | A single evaluation unit: `instruction.md`, environment definition, test scripts, optional solution |
| **Dataset** | A collection of tasks, local or from the curated registry |
| **Agent** | A program that attempts tasks (Claude Code, OpenHands, Codex, custom, etc.) |
| **Environment** | A sandboxed container runtime (Docker, Daytona, Modal, E2B, GKE) |
| **Trial** | One agent attempt at one task, producing a trajectory and reward |
| **Job** | A collection of trials (Cartesian product of tasks × agents × attempts) |

**Task Directory Format:**

```
my_task/
├── instruction.md          # Natural language instructions for the agent
├── task.toml               # Configuration: timeouts, resources, metadata, env vars
├── environment/            # Dockerfile or docker-compose.yaml
├── tests/                  # Verification (test.sh → reward.txt or reward.json)
└── solution/               # Optional reference solution (solve.sh)
```

**Execution Lifecycle:** `harbor run -d "dataset@version" -a agent-name -m provider/model` triggers: job initialization → task download (git sparse checkout + LFS) → environment provisioning → agent setup + execution (with timeout) → verification (test.sh) → artifact collection (ATIF v1.4 trajectories) → cleanup. Concurrency is managed via `asyncio.Semaphore`.

**Environment Runtimes:**

| Environment | Type | GPU | Multi-Container | Notes |
|-------------|------|-----|-----------------|-------|
| Docker | Local | No | Yes (compose) | Default; mounted filesystem |
| Daytona | Cloud | No | Yes (compose) | I/O-bounded, enables 100+ concurrent trials |
| Modal | Cloud | Yes | No | GPU access for ML workloads |
| E2B | Cloud | No | No | Lightweight cloud sandboxes |
| GKE | Cloud (K8s) | Yes | No | Kubernetes-based scaling |

**Registry:** 47 curated datasets totaling ~21,000+ task instances, spanning software engineering (SWE-Bench, SWE-Bench Pro), competitive programming (code-contests with 44K+ tasks), terminal/agent tasks (Terminal-Bench), mathematics (AIME), science (GPQA-Diamond, BixBench), data science (DABstep, DS-1000), reasoning (ARC-AGI-2), safety (StrongReject), and more. Custom registries are supported via `--registry-path` or `--registry-url`.

**Built-in Agents:** claude-code, codex, openhands, gemini-cli, aider, goose, mini-swe-agent, qwen-coder, cursor-cli, cline-cli, opencode, terminus-2, oracle, nop. Custom agents can be loaded at runtime via `--agent-import-path module:Class`.

### 2.2 inspect-harbor: The Inspect AI Bridge

inspect-harbor (v0.4.5, Feb 25, 2026, by Meridian Labs / J.J. Allaire) bridges Harbor's task/scoring infrastructure with Inspect AI's solver/evaluation ecosystem. It depends on `harbor >= 0.1.44` and `inspect-ai >= 0.3.176`.

**What it does:**

- Converts Harbor Tasks to Inspect AI Samples (`harbor_task_to_sample()`)
- Maps `instruction.md` → `Sample.input`, `environment/` → `SandboxEnvironmentSpec`, `tests/test.sh` → `harbor_scorer`
- Provides a core `harbor()` task function with four loading patterns: registry dataset, git task, local task, local dataset
- Auto-generates `@task` functions for all 47+ registry datasets (e.g., `from inspect_harbor import terminal_bench, swebench_verified`)
- Bundles an `oracle` solver (runs `solution/solve.sh` for task validation)
- Provides a default ReAct solver: `react(tools=[bash(timeout=300), python(timeout=300), update_plan()], compaction=CompactionEdit())`
- Supports resource overrides (`override_cpus`, `override_memory_mb`, `override_gpus`) and alternative sandbox environments (`sandbox_env_name`)

**Key constraint:** The `harbor_scorer` is always used regardless of solver choice — it is baked into the task definition. This ensures consistent verification across all solvers.

**Important note on documentation:** inspect-harbor has no published API reference docs site. The only documentation is the README and REGISTRY.md on GitHub. Multiple URLs cited in earlier research phases pointing to `meridianlabs-ai.github.io/inspect_harbor/reference/` return 404 and the API classes described at those URLs (e.g., `HarborServiceManager`, `SDKServiceManager`, `HarborBenchmark`) could not be verified.

### 2.3 Defining and Registering New Agent Solvers

**Harbor Native Agents:** Implement `BaseAgent` (external agents that communicate via `exec()` commands) or `BaseInstalledAgent` (agents installed into the container). Registration requires adding to the `AgentName` enum and providing installation templates. Runtime loading via `--agent-import-path module:Class` avoids source modifications.

**Inspect AI Solvers (via inspect-harbor):** Any Inspect AI solver works with Harbor tasks. The solver is swapped freely while `harbor_scorer` handles verification consistently:

```python
@solver
def my_agent():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Custom agent logic
        ...
    return solve

eval(terminal_bench(), solver=my_agent(), model="anthropic/claude-sonnet-4-5")
```

CLI override: `inspect eval inspect_harbor/terminal_bench --solver path/to/agent.py@my_agent`

### 2.4 Defining and Registering New Benchmarks

**Harbor's Adapter System:** `harbor adapters init` launches an interactive wizard for converting third-party benchmarks to Harbor's task format. The adapter reads original benchmark data and generates task directories. The workflow: generate tasks → validate with Oracle solver (expect 100% pass rate) → run parity experiments vs. original harness → upload to HuggingFace → register in `registry.json` → submit PR.

**Via inspect-harbor:** Once in Harbor format, tasks are immediately usable: `harbor(path="/path/to/my-benchmark/")` or `harbor(dataset_name_version="my-benchmark@1.0", registry_path="./my-registry.json")`.

### 2.5 Spider2 Integration Status

**What exists:** `spider2-dbt@1.0` in the Harbor registry — 64 tasks for Spider 2.0-DBT (dbt code generation), a subset introduced May 22, 2025 when the original Spider2 setting was removed for that workflow. Spider2-DBT has 68 examples total; the Harbor adapter exposes 64 runnable tasks.

**What doesn't exist:** The full Spider2 text-to-SQL benchmark (including Spider 2.0-Lite with 135 SQLite-based tasks) is not in the registry.

**Integration path:** The existing `spider2-dbt` adapter serves as a template for building a Spider2-Lite adapter. Spider2-Lite (SQLite subset) is the most feasible target: self-contained databases can be baked into Docker images, tasks map naturally to `instruction.md` + schema context, and evaluation is CSV output comparison wrappable as `test.sh`. Cloud-database variants (BigQuery, Snowflake) require `allow_internet=true` and credential injection and represent significantly higher effort.

### 2.6 LongMemEval Integration Status

**Not in the registry.** LongMemEval (Wu et al., 2024, ICLR 2025) benchmarks long-term memory capabilities across 500 questions with conversation histories ranging from ~115K tokens (oracle subset) to ~1.5M tokens (M subset, ~500 sessions).

**Critical design insight from cross-pollination:** A naive adapter that dumps conversation history into `instruction.md` would be impractical — 1.5M tokens would exhaust model context windows before the question is even posed. Instead:

1. The Docker environment should contain conversation history as files in the filesystem
2. `instruction.md` should contain the question + instructions on where to find the data
3. The agent must independently decide how to process the data (RAG, summarization, indexing, etc.)
4. This makes LongMemEval a benchmark that tests **solver memory architecture**, not just task correctness

The LongMemEval_oracle subset (500 questions with only evidence sessions) is the practical starting point. GPT-4o-based automated QA scoring can be implemented in `test.sh` (requiring API key injection via `task.toml[verifier].env`).

---

## 3. Areas of Consensus

Both research agents agreed on the following points, supported by independent verification:

### 3.1 inspect-harbor bridges to laude-institute/harbor, not av/harbor

Both agents ultimately concluded that `inspect-harbor`'s `harbor >= 0.1.44` dependency refers to the PyPI package published by the Laude Institute, not the `av/harbor` Docker orchestration tool. This was confirmed via `pyproject.toml` dependency inspection, PyPI package descriptions, and documentation cross-referencing. (One agent identified this immediately; the other corrected course during cross-pollination.)

### 3.2 Harbor + inspect-harbor is the right foundation

Both agents agreed the recommended approach is to use Harbor as the task/benchmark/environment layer and inspect-harbor + Inspect AI as the solver/evaluation layer. This provides:
- Standardized task format with consistent scoring (`tests/test.sh` → rewards)
- Solver flexibility via Inspect AI's `@solver` abstraction
- Container-based isolation with multiple runtime options
- A large existing benchmark library (47 datasets, 21K+ tasks)

### 3.3 LongMemEval requires custom engineering; it's not in the registry

Both agents confirmed LongMemEval is absent from the registry and requires a custom adapter. Both identified the context window challenge as the core difficulty.

### 3.4 Result normalization is a first-class problem

Both agents identified that Harbor native (`result.json`) and Inspect AI (`.eval` logs) produce structurally different output formats. Cross-benchmark and cross-execution-mode comparison requires a custom normalization layer.

### 3.5 The eval runner should avoid dual orchestration

Both agents warned against nesting Harbor's job/trial orchestration inside Inspect AI's eval loop or vice versa. The recommended pattern: use Inspect AI + inspect-harbor as the sole orchestrator for solver-based evals; use Harbor native only for Harbor-native agents (Claude Code, OpenHands, etc.).

---

## 4. Areas of Disagreement

### 4.1 The identity and role of av/harbor

| | Agent 1 (opencode-opus) | Agent 2 (codex-5.3-xhigh) | Resolution |
|---|---|---|---|
| **Claim** | av/harbor is a completely separate, unrelated Docker orchestration tool for LLM stacks | av/harbor is the "infrastructure/tooling layer" that works alongside Harbor Framework as the "eval abstraction layer" | **Agent 1 was correct.** They are completely separate codebases with no shared lineage or interoperability. Agent 2 corrected this during cross-pollination. |

### 4.2 inspect-harbor version

| | Agent 1 | Agent 2 | Resolution |
|---|---|---|---|
| **Claim** | v0.4.5, Feb 25, 2026 | v0.2.5, Jan 13, 2026 | **Agent 1 was correct.** PyPI release history shows v0.1.0 was released Feb 10, 2026 — no releases existed in January 2026. Agent 2 acknowledged the error in cross-pollination. |

### 4.3 Spider2 and LongMemEval in the registry

| | Agent 1 | Agent 2 | Resolution |
|---|---|---|---|
| **Claim** | Not in registry; need custom adapters | Already in inspect-harbor's registry | **Both partially wrong.** `spider2-dbt@1.0` (64 tasks) exists — a related subset of the Spider2 ecosystem. Full Spider2 text-to-SQL and LongMemEval are not in the registry. Agent 2's cited URLs for Spider2/LongMemEval registry pages returned 404. |

### 4.4 inspect-harbor API surface

| | Agent 1 | Agent 2 | Resolution |
|---|---|---|---|
| **Claim** | Thin bridge: `harbor()` task, `harbor_scorer`, `oracle` solver, auto-generated task functions | Rich API: `HarborServiceManager`, `SDKServiceManager`, `default_harness`, `harbor_solver()`, `HarborBenchmark` | **Agent 1's characterization is better supported.** The 23 KB wheel size and verified codebase structure are consistent with a thin bridge. Agent 2's cited API reference URLs return 404 and the described classes could not be verified. |

### 4.5 Architectural emphasis

| | Agent 1 | Agent 2 | Resolution |
|---|---|---|---|
| **Emphasis** | Detailed task format, adapter workflow, specific gap analysis | Control-plane / registry-plane / execution-plane architecture with abstract roles | **Both useful.** Agent 1 provided more grounded, verifiable technical detail. Agent 2 provided better high-level architectural framing. The synthesis benefits from combining both perspectives. |

---

## 5. Novel Insights

These findings emerged specifically from the cross-pollination refinement round, where each agent reviewed the other's work and conducted additional verification:

### 5.1 Registry Drift Between Harbor and inspect-harbor

inspect-harbor ships an auto-generated registry map, but current task counts differ from the live Harbor registry for multiple datasets (e.g., `code-contests`, `seta-env`, `termigen-environments`). This means inspect-harbor task metadata can lag Harbor registry evolution. **Practical implication:** Treat dataset availability and task counts as runtime-validated, not assumed. Add pre-run registry consistency checks to the eval runner.

### 5.2 LongMemEval Requires a Fundamentally Different Adapter Design

Standard Harbor adapters put task content in `instruction.md`. For LongMemEval, conversation histories (up to ~1.5M tokens) should be placed as files in the Docker environment's filesystem, with `instruction.md` containing only the question and pointers to the data files. This reframes LongMemEval as a benchmark that tests **solver memory architecture** rather than just correctness — the solver must implement its own RAG, indexing, or retrieval strategy.

### 5.3 Spider2-DBT Proves the Adapter Pattern for Spider2 Family

The existence of `spider2-dbt@1.0` in the registry (64 tasks) reduces uncertainty around Spider2 integration. The hardest design decisions (schema packaging, environment structure, evaluation approach) have been made. Building a Spider2-Lite (SQLite) adapter can follow the same pattern.

### 5.4 av/harbor's harbor bench Has Useful Design Patterns

Despite being an unrelated project, `av/harbor`'s `harbor bench` LLM-as-judge system offers patterns worth borrowing for the eval runner:
- **Variant permutation engine:** Automatic cross-products of model × temperature × API URL × seed
- **LLM-as-judge with configurable judge model:** Separate test model from evaluation model
- **Multi-format output:** HTML, CSV, JSON results for different consumption patterns
- **Reproducibility controls:** Explicit temperature=0 + seed pinning

### 5.5 Resource Override Capabilities in inspect-harbor

inspect-harbor v0.4.5 exposes `override_cpus`, `override_memory_mb`, and `override_gpus` parameters on every task function, plus a `sandbox_env_name` parameter (defaulting to `"docker"`, with `"modal"` as an alternative). This enables per-run resource tuning — important for cost optimization and GPU scheduling in mixed workloads.

### 5.6 inspect-flow for Experiment Matrix Orchestration

The codex agent surfaced `inspect-flow` (by Meridian Labs, same team as inspect-harbor) as a tool for declarative task × model sweeps. This could serve as the matrix orchestration layer instead of building a custom one.

---

## 6. Open Questions

1. **Does `sandbox_env_name="modal"` actually work through inspect-harbor?** The parameter exists in the API but no documentation confirms Modal support through inspect-harbor specifically (vs. Harbor native). Needs empirical testing.

2. **How active is the community adapter pipeline?** The 47 registry datasets suggest strong core-team output, but it's unclear how many are community-contributed vs. Laude Institute internal. This affects the sustainability of the adapter ecosystem.

3. **What is the inspect-harbor API stability contract?** The package went from v0.1.0 to v0.4.5 in ~2 weeks (Feb 10-25, 2026) with 12 releases. The API may still be unstable. With only 3 GitHub stars, community adoption is minimal, increasing breakage risk.

4. **Can inspect-flow handle the solver × benchmark × model matrix at scale?** It was identified during research but not deeply evaluated for fitness as the matrix orchestration layer.

5. **How does GPU scheduling work for mixed workloads?** When running benchmarks that mix GPU-required tasks (ML training, CodePDE) with CPU-only tasks (text-to-SQL, code editing), how do Harbor's cloud environments handle heterogeneous resource allocation?

6. **What are the actual costs of running full benchmark suites at scale?** No public data exists on typical costs using Harbor's cloud environments (Modal, Daytona). The eval runner needs cost tracking, but neither Harbor nor Inspect AI provides built-in cost accounting. LangFuse integration is a potential solution but unexplored.

7. **How does Harbor handle multi-container task limitations in cloud environments?** Docker supports multi-container tasks (via compose), but Modal, E2B, and GKE do not. Benchmarks requiring multiple services (e.g., application + database) may be limited to Docker/Daytona environments.

8. **What is the programmatic API stability for Harbor?** Harbor exports Python classes for programmatic use, but documentation on API stability guarantees is sparse at v0.1.x.

---

## 7. Sources

All URLs were cited across at least one research phase and verified where possible. URLs marked with "(404)" returned not-found during verification.

### Primary Projects

| Source | URL |
|--------|-----|
| Harbor (Laude Institute) GitHub | https://github.com/laude-institute/harbor |
| Harbor Framework Website/Docs | https://harborframework.com/ |
| Harbor Registry | https://harborframework.com/registry |
| Harbor Core Concepts | https://harborframework.com/docs/core-concepts |
| Harbor Task Format | https://harborframework.com/docs/tasks |
| Harbor Running Jobs / Evals | https://harborframework.com/docs/run-jobs/run-evals |
| Harbor Cloud Sandboxes | https://harborframework.com/docs/run-jobs/cloud-sandboxes |
| Harbor Adapters | https://harborframework.com/docs/datasets/adapters |
| inspect-harbor PyPI | https://pypi.org/project/inspect-harbor/ |
| inspect-harbor GitHub | https://github.com/meridianlabs-ai/inspect_harbor |
| inspect-harbor REGISTRY.md | https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md |
| inspect-harbor pyproject.toml | https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml |
| harbor PyPI (laude-institute) | https://pypi.org/project/harbor/ |
| Inspect AI Documentation | https://inspect.ai-safety-institute.org.uk/ |
| inspect-flow (Meridian Labs) | https://meridianlabs-ai.github.io/inspect_flow/ |

### av/harbor (Separate Project)

| Source | URL |
|--------|-----|
| av/harbor GitHub | https://github.com/av/harbor |
| av/harbor Harbor Bench Wiki | https://github.com/av/harbor/wiki/5.1.-Harbor-Bench |
| av/harbor lm-eval-harness satellite | https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness |
| av/harbor Promptfoo satellite | https://github.com/av/harbor/wiki/2.3.28-Satellite%3A-Promptfoo |

### Benchmarks

| Source | URL |
|--------|-----|
| Spider2 Project | https://spider2-sql.github.io/ |
| Spider2 GitHub | https://github.com/xlang-ai/Spider2 |
| Spider2 Paper | arXiv:2411.07763 (Lei et al., 2024) |
| LongMemEval GitHub | https://github.com/xiaowu0162/LongMemEval |
| LongMemEval HuggingFace | https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned |
| LongMemEval Paper | arXiv:2410.10813 (Wu et al., 2024) |

### URLs Cited but Not Verified (404 or Unconfirmed)

| Source | URL | Status |
|--------|-----|--------|
| inspect-harbor API docs | https://meridianlabs-ai.github.io/inspect_harbor/ | 404 |
| inspect-harbor reference pages ([8]-[17] in codex report) | https://meridianlabs-ai.github.io/inspect_harbor/reference/... | 404 |
| inspect-harbor registry task pages | https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/spider2/ | 404 |
| av/harbor harbor-bench directory | https://github.com/av/harbor/tree/main/harbor-bench | 404 |

---

## 8. Methodology

### Research Process

This report was produced through a structured multi-agent research process with three phases:

**Phase 1 — Independent Research** (Duration: ~590 seconds / ~10 minutes)
Two AI agents independently researched the same topic:
- **Agent A:** `opencode-wibey-opus-4-6` (OpenCode powered by Claude Opus 4)
- **Agent B:** `codex-5.3-xhigh` (Codex 5.3 at extra-high reasoning effort)

Each agent had access to web fetching, GitHub repository analysis (DeepWiki), and code exploration tools. They produced independent research reports without seeing each other's work.

**Phase 2 — Cross-Pollination** (Duration: ~227 seconds / ~4 minutes)
Each agent received both reports and was tasked with skeptically reviewing the other's findings:
- Agent A reviewed Agent B's report and conducted verification research
- Agent B reviewed Agent A's report and conducted verification research

This phase uncovered significant factual errors (fabricated URLs, wrong version numbers, incorrect project identity claims) and produced new insights that neither agent found independently (registry drift, LongMemEval adapter design, resource override capabilities).

**Phase 3 — Synthesis** (This report)
A single agent (opencode-wibey-opus-4-6) synthesized all findings from both phases into this final report, organized by theme rather than by source agent.

### Research Run

- **Run ID:** `20260301-200517-a4a45a`
- **Date:** March 1, 2026
- **Total research duration:** ~817 seconds (~13.6 minutes) for phases 1-2
- **Synthesizer:** opencode-wibey-opus-4-6

### Limitations of This Research

1. **Source code access was limited.** Neither agent could fully read inspect-harbor's Python source files from GitHub. Understanding is based on package metadata, README content, REGISTRY.md, and structural analysis (wheel size, dependency tree).

2. **Some Harbor Framework doc URLs were not independently verified.** URLs under `harborframework.com/docs/` were cited by both agents but content verification was limited to what could be fetched via web tools.

3. **No hands-on testing.** Neither agent installed or ran Harbor, inspect-harbor, or Inspect AI. All findings are based on documentation, source code analysis, and package metadata review.

4. **One agent produced multiple fabricated or hallucinated references** (API doc URLs, version numbers, registry contents). These were caught during cross-pollination, but the possibility of subtler errors surviving the process cannot be excluded.

5. **inspect-harbor is very new** (first release Feb 10, 2026 — only 19 days before this research). The package may have changed significantly between research and publication.

---

## Appendix: Recommended Build Plan

Based on the combined findings, here is a pragmatic sequence for building the eval runner:

### Phase A: Foundation (No Custom Adapters)

1. Install Harbor (v0.1.45+) and inspect-harbor (v0.4.5+) with Inspect AI
2. Validate the pipeline end-to-end with a built-in benchmark (e.g., `terminal_bench_sample`)
3. Run existing registry benchmarks with the default ReAct solver and at least one custom solver
4. Establish the result normalization schema and build initial adapters for Inspect `.eval` logs

### Phase B: Spider2 Integration

5. Evaluate the existing `spider2-dbt@1.0` tasks to understand the adapter pattern
6. Build Spider2-Lite (SQLite) adapter using `spider2-dbt` as a template: `harbor adapters init`
7. Validate with Oracle solver, run parity experiments against Spider2's evaluation suite

### Phase C: LongMemEval Integration

8. Build LongMemEval_oracle adapter with conversation data as Docker filesystem files
9. Implement GPT-4o QA scoring in `test.sh` with API key injection
10. Test with default ReAct solver (expected: poor performance on harder subsets)
11. Build memory-capable solver prototypes (RAG, indexing strategies) for LongMemEval_M

### Phase D: Hardening

12. Add pre-run registry consistency checks (inspect-harbor registry vs. Harbor registry drift)
13. Implement capability metadata per solver (max_context, tool needs, internet, container mode) with incompatible pairing rejection
14. Add cost tracking (token counting, compute time, estimated USD)
15. Build cross-benchmark comparison dashboard
16. Implement version pinning and reproducibility controls (Harbor version, registry commit, model config, seed)
