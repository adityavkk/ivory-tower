# Cross-Pollination Analysis: Harbor + inspect-harbor Eval Runner

## Refined Report — March 1, 2026

---

## 1. Critical Factual Corrections from Peer Review

### 1.1 The av/harbor vs laude-institute/harbor Confusion

The peer report (codex-5.3) made a fundamental architectural claim: that `av/harbor` serves as the "infrastructure/tooling project centered on Docker Compose service orchestration" that works alongside "Harbor Framework" (laude-institute/harbor) as the "model/eval abstraction layer."

**Verdict: This claim is incorrect, but reveals a genuinely useful insight.**

Independent verification confirms:

- **`av/harbor`** (2.5K stars, 726 commits) is a Docker Compose orchestration tool for local LLM stacks — Ollama, Open WebUI, vLLM, ComfyUI, etc. It has a `harbor bench` feature, but this is an LLM-as-judge benchmarking tool for comparing chat/instruction quality across models and configurations. It is **completely unrelated** to the agent evaluation framework.

- **`laude-institute/harbor`** (816 stars, 551 commits) is the Laude Institute's agent evaluation and RL environment framework. This is what `inspect-harbor` bridges to.

- **`inspect-harbor`** (v0.4.5, Feb 25, 2026, by Meridian Labs / J.J. Allaire) explicitly depends on `harbor >= 0.1.44` (the `laude-institute/harbor` PyPI package) and points to `harborframework.com` as the Harbor documentation source.

The peer report's conflation likely stems from the original prompt referencing `github.com/av/harbor`. The two projects are **completely separate codebases with no shared lineage or interoperability**.

However, the peer report accidentally surfaced something useful: `av/harbor`'s `harbor bench` is a sophisticated LLM-as-judge benchmarking system with variant permutations (temperature, model, API URL cross-products), reproducibility controls (seed pinning), and structured output (HTML reports, CSV, JSON). While unrelated to agent evaluation, its design patterns for parameter sweeps and result aggregation are worth studying for the eval runner's comparison layer.

### 1.2 inspect-harbor Version

The peer report claimed version `0.2.5, released January 13, 2026`. **This is wrong.** PyPI's release history shows:

- v0.1.0: Feb 10, 2026
- v0.2.0: Feb 10, 2026
- v0.3.0: Feb 11, 2026
- v0.4.0 through v0.4.5: Feb 12-25, 2026
- **No version was released in January 2026.**

The correct latest is **v0.4.5 (Feb 25, 2026)**.

### 1.3 Spider2 and LongMemEval in the inspect-harbor Registry

The peer report claimed (sources [15][16][17]) that inspect-harbor's registry already includes Spider2 and LongMemEval tasks. **This is false.**

I verified the complete REGISTRY.md (auto-generated from `laude-institute/harbor`'s `registry.json`). The registry contains **47 datasets**. Neither Spider2 nor LongMemEval appears. The closest match is **`spider2-dbt@1.0`** — a 64-task subset focused specifically on Spider 2.0-DBT (dbt code generation tasks), not the full Spider2 text-to-SQL benchmark.

This is a significant finding that my original report also missed: **Spider2-DBT already has a Harbor adapter.** This means part of the Spider2 ecosystem is already integrated, and the adapter pattern is proven for this benchmark family. However, the core Spider2 text-to-SQL tasks (including the Lite SQLite subset) still need a custom adapter.

### 1.4 Fabricated API Reference URLs

The peer report cited numerous URLs from `meridianlabs-ai.github.io/inspect_harbor/` (sources [8]-[17]). The documentation site at that URL **returns 404**. The inspect-harbor project has no published API reference docs site. Its documentation is entirely in the README and REGISTRY.md on GitHub.

The peer report's descriptions of components like `HarborServiceManager`, `SDKServiceManager`, `default_harness`, and `harbor_solver()` as named API classes **cannot be verified** and appear to be fabricated or hallucinated. The actual inspect-harbor codebase (23.1 KB wheel) is a thin bridge layer with:
- A `harbor()` task function
- A `harbor_scorer` scorer
- An `oracle` solver
- Auto-generated task functions for registry datasets
- Harbor task-to-Inspect sample conversion logic

There is no evidence of `HarborServiceManager`, `SDKServiceManager`, `HarborBenchmark`, or `harbor_solver` as named public API components.

---

## 2. What the Peer Report Got Right (That I Should Emphasize More)

### 2.1 The Overlapping Orchestration Problem

The peer report correctly identified (section 8, point 2) that there are **overlapping orchestration layers**: Harbor's `harbor run` (Job/Trial execution), Inspect AI's `eval()` loop, and potentially a custom eval runner on top. The advice to "pick one top-level executor and avoid dual orchestration for a single run" is sound.

My original report touched on this under "Option C: Hybrid Approach" but the peer report stated it more directly as a design risk. This deserves emphasis: **the most common failure mode for this architecture will be fighting two orchestrators**.

### 2.2 Metric Harmonization as a First-Class Problem

The peer report foregrounded metric harmonization across benchmarks as a key gap. My report mentioned it under "Gap 6: No Unified Leaderboard" but framed it as a dashboard problem. The peer correctly identified it as a **data model problem**: Harbor's `result.json` and Inspect AI's `.eval` log format are structurally different, and cross-benchmark comparison requires a unifying schema.

### 2.3 Reproducibility Requires Explicit Pinning

The peer report noted that "service reproducibility (exact model backend/image/profile/version pinning) must be enforced by your runner metadata; defaults are not enough for strict reproducibility." This is a real gap neither report explored deeply.

---

## 3. New Research Findings (Beyond Either Report)

### 3.1 Spider2-DBT Already Exists — Implications for Full Spider2

The REGISTRY.md reveals `spider2-dbt@1.0` with 64 tasks. This is a Harbor adapter for Spider 2.0-DBT, which evaluates agents on dbt (data build tool) code generation tasks — a subset of the Spider2 ecosystem but not the text-to-SQL core.

**Key implication**: The adapter pattern for Spider2-family tasks is proven. The Spider2-DBT adapter can serve as a template for building a Spider2-Lite (SQLite text-to-SQL) adapter. The adapter likely handles:
- Packaging database schemas and project structures into Docker environments
- Converting task descriptions to `instruction.md` format
- Implementing output comparison in `test.sh`

This reduces the estimated effort for Spider2-Lite from "medium" to "medium-low" — the hardest design decisions have already been made.

### 3.2 The Registry Is Larger and More Diverse Than Originally Reported

My original report stated "45+ datasets totaling ~21,000+ task instances." The actual verified count from REGISTRY.md is **47 datasets** with the following distribution:

| Category | Examples | Task Count |
|----------|----------|------------|
| Software Engineering | SWE-Bench, SWE-Bench Pro, SWE-Lancer, VMAX | ~2,900+ |
| Competitive Programming | code-contests, USACO, LiveCodeBench | ~10,000+ |
| Terminal/Agent Tasks | Terminal-Bench, Terminal-Bench-Pro, TermiGen | ~3,900+ |
| Mathematics | AIME, IneqMath | ~160 |
| Science | GPQA-Diamond, BixBench, CodePDE, ReplicationBench | ~500+ |
| Data Science | DABstep, DS-1000 | ~1,450 |
| Reasoning | ARC-AGI-2, Reasoning Gym (easy+hard) | ~743 |
| Safety | StrongReject | 150 |
| Other | AlgoTune, MMAU, CompileBench, LawBench, etc. | ~1,500+ |

Notable for the eval runner: this breadth means many benchmarks you might want are **already available** with no adapter work needed. The practical "general-purpose eval runner" can start with substantial coverage on day one.

### 3.3 inspect-harbor Supports Non-Docker Sandbox Environments

The PyPI documentation reveals a `sandbox_env_name` parameter that defaults to `"docker"` but can be changed. The example shows `"modal"` as an alternative. This means inspect-harbor may already support running tasks on Modal's cloud infrastructure — which is significant for scale (100+ concurrent trials) and GPU access.

My original report documented this for Harbor native (which supports docker, daytona, modal, e2b, gke) but did not confirm inspect-harbor's sandbox provider support. The `sandbox_env_name` parameter in the task function signature suggests at least partial support.

### 3.4 Resource Override Capability

inspect-harbor v0.4.5 exposes `override_cpus`, `override_memory_mb`, and `override_gpus` parameters on every task function. This is important for the eval runner because:
- Different solvers may need different resource profiles for the same benchmark
- Cost optimization: you can reduce resources for lightweight solvers
- GPU allocation: some benchmarks (ML tasks) need GPUs while most don't

My original report noted the 6 GB minimum memory enforcement but missed these override capabilities.

### 3.5 av/harbor's Bench — Useful Design Patterns Despite Being Unrelated

`av/harbor`'s `harbor bench` (verified via Wiki page 5.1) provides patterns worth borrowing:

1. **Variant permutation engine**: Automatically generates cross-products of model, temperature, API URL, seed, and other parameters. For our eval runner, an analogous system would generate cross-products of solver x benchmark x model x configuration.

2. **LLM-as-judge with configurable judge model**: The bench uses one LLM to test and another as judge, both configurable. Harbor (laude-institute) already supports this via `task.toml[verifier.env]` for LLM judge scoring.

3. **Multi-format results**: HTML reports, CSV for data analysis tools, JSON for programmatic access. Our eval runner should output similarly structured results.

4. **Reproducibility controls**: Explicit temperature=0 + seed pinning guidance. This is a pattern our eval runner should enforce at the configuration level.

### 3.6 LongMemEval: The Context Window Challenge Is Even Harder Than Stated

Neither report fully explored the implications of LongMemEval's context requirements for the Harbor task model. The challenge:

- LongMemEval_M sessions contain ~1.5M tokens of conversation history
- Harbor's `instruction.md` is the sole mechanism for providing context to the agent
- A 1.5M token `instruction.md` is technically valid but practically absurd — it would exhaust most model context windows before the agent even receives the question
- The intended use case for LongMemEval is testing whether agents can **implement their own memory/retrieval systems** over the conversation data

This means a LongMemEval adapter can't simply dump history into `instruction.md`. Instead:
1. The Docker environment should contain the conversation history as files
2. `instruction.md` should contain the question + instructions on where to find the data
3. The agent must independently decide how to process the data (RAG, summarization, etc.)
4. This tests the solver's memory architecture, not just its task execution ability

This reframes LongMemEval as a fundamentally different kind of benchmark — one that tests **solver capabilities** rather than just correctness. The adapter is straightforward; the challenge is building solvers that can handle it.

---

## 4. Revised Architecture Recommendations

### 4.1 Single Orchestrator Rule

Based on cross-pollination insights, the strongest recommendation is:

**Use Inspect AI + inspect-harbor as the sole orchestrator for solver-based evals.** Use Harbor native (`harbor run`) only for testing Harbor-native agents (Claude Code, OpenHands, etc.) that don't fit the Inspect solver model.

Do not try to wrap Harbor native inside Inspect or vice versa for a single eval run. The result formats are different, the concurrency models are different, and debugging dual-orchestrated runs is significantly harder.

### 4.2 Start with What's Already There

The revised priority order for the eval runner:

1. **Immediate (no adapter work)**: Terminal-Bench, SWE-Bench Verified, SWE-Bench Pro, AIME, GPQA-Diamond, ARC-AGI-2, code-contests, DABstep, BixBench, AlgoTune — already in the registry with inspect-harbor task functions.

2. **Low effort (adapter exists, just needs Spider2 family extension)**: Spider2-Lite (SQLite text-to-SQL) — leverage the existing `spider2-dbt` adapter as template.

3. **Medium effort (new adapter, straightforward mapping)**: LongMemEval_oracle — 500 questions with pre-filtered evidence sessions. Adapter creates Docker environments with conversation files; scoring via GPT-4o judge in `test.sh`.

4. **High effort (new adapter + new solver capabilities)**: LongMemEval_M — requires both adapter engineering AND memory-capable solvers that don't exist yet.

### 4.3 Result Normalization Schema

Both reports identified result normalization as a gap. Here's a concrete proposal for a unifying schema:

```json
{
  "run_id": "uuid",
  "timestamp": "ISO-8601",
  "orchestrator": "inspect-harbor | harbor-native",
  "benchmark": {
    "name": "terminal-bench",
    "version": "2.0",
    "subset": null,
    "n_tasks": 89
  },
  "solver": {
    "type": "inspect-solver | harbor-agent",
    "name": "react-default",
    "config": {}
  },
  "model": {
    "provider": "anthropic",
    "name": "claude-sonnet-4-5",
    "config": {"temperature": 0}
  },
  "environment": {
    "runtime": "docker",
    "resources": {"cpus": 4, "memory_mb": 8192, "gpus": 0}
  },
  "results": {
    "accuracy": 0.72,
    "stderr": 0.048,
    "per_task": [
      {"task_id": "task-1", "reward": 1.0, "duration_s": 120},
      {"task_id": "task-2", "reward": 0.0, "duration_s": 300}
    ]
  },
  "cost": {
    "model_tokens_in": 1500000,
    "model_tokens_out": 200000,
    "judge_tokens_in": 50000,
    "judge_tokens_out": 10000,
    "estimated_usd": 12.50
  },
  "reproducibility": {
    "harbor_version": "0.1.45",
    "inspect_harbor_version": "0.4.5",
    "inspect_ai_version": "0.3.180",
    "registry_commit": "abc123",
    "seed": 42
  }
}
```

This schema can be populated from either Inspect AI `.eval` logs or Harbor `result.json` with format-specific adapters.

---

## 5. Contradictions Resolved

| Issue | My Report | Peer Report | Resolution |
|-------|-----------|-------------|------------|
| What is av/harbor? | Unrelated Docker orchestration tool | Infrastructure layer that works with Harbor Framework | **My report was correct.** They are completely separate projects. |
| inspect-harbor version | v0.4.5 (Feb 25, 2026) | v0.2.5 (Jan 13, 2026) | **My report was correct.** v0.4.5 confirmed on PyPI. No January releases exist. |
| Spider2 in registry | Not in registry; needs custom adapter | Already in registry ([16]) | **Partially wrong on both sides.** `spider2-dbt@1.0` (64 tasks) exists — a related but different subset. Full Spider2 text-to-SQL is not in registry. |
| LongMemEval in registry | Not in registry; needs custom adapter | Already in registry ([17]) | **My report was correct.** LongMemEval is not in the registry. |
| inspect-harbor has HarborServiceManager, SDKServiceManager | Not mentioned | Described as core components | **Cannot verify.** The cited API docs site returns 404. The package is 23 KB — unlikely to contain these components. Likely fabricated. |
| harbor-bench in av/harbor | Not discussed | Described as having Inspect integration templates | **Partially correct but misleading.** `harbor bench` exists in av/harbor as an LLM-as-judge tool, but it has no relationship to Inspect AI or Harbor Framework. The "Inspect eval template" the peer references does not exist at the cited path (404). |

---

## 6. Remaining Open Questions

1. **inspect-harbor sandbox provider support**: Does `sandbox_env_name="modal"` actually work? The parameter exists in the API but no documentation confirms Modal support through inspect-harbor (vs. Harbor native).

2. **Harbor adapter contribution process**: How active is the community adapter pipeline? The 47 registry datasets suggest strong core-team output, but community contribution patterns are unclear.

3. **Inspect AI's upcoming features**: Inspect AI is under active development (J.J. Allaire is both an Inspect AI and inspect-harbor maintainer). Future Inspect features could reduce the gap between the two execution modes.

4. **Cost tracking integration**: Neither Harbor nor Inspect AI has built-in cost tracking. LangFuse (supported by av/harbor, potentially integratable with Inspect AI) could serve this role but hasn't been explored in this context.

5. **GPU scheduling for mixed workloads**: When running benchmarks that mix GPU-required tasks (ML training benchmarks) with CPU-only tasks (text-to-SQL, code editing), how does the orchestrator handle heterogeneous resource allocation?

---

## Sources (New or Updated)

| Source | URL | Finding |
|--------|-----|---------|
| inspect-harbor PyPI (verified) | https://pypi.org/project/inspect-harbor/ | v0.4.5, Feb 25, 2026. No January releases. |
| inspect-harbor REGISTRY.md | https://github.com/meridianlabs-ai/inspect_harbor/blob/main/REGISTRY.md | 47 datasets. spider2-dbt present. No Spider2 text-to-SQL or LongMemEval. |
| meridianlabs-ai docs site | https://meridianlabs-ai.github.io/inspect_harbor/ | **404 — does not exist.** |
| av/harbor GitHub | https://github.com/av/harbor | Docker Compose LLM stack orchestrator. No harbor-bench directory in repo tree. |
| av/harbor Wiki - Harbor Bench | https://github.com/av/harbor/wiki/5.1.-Harbor-Bench | LLM-as-judge benchmarking tool. No Inspect AI integration. |
| laude-institute/harbor GitHub | https://github.com/laude-institute/harbor | Agent eval framework, 816 stars, harborframework.com |
| av/harbor harbor-bench directory | https://github.com/av/harbor/tree/main/harbor-bench | **404 — does not exist.** harbor-bench is a built-in CLI command, not a directory. |
