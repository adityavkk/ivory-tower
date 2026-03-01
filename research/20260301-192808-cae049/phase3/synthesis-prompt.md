# Research Synthesis

2 AI agents independently researched a topic, then cross-pollinated
findings by skeptically reviewing each other's work. You have all their refinement
reports below.

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Refinement Reports
### claude-opus-cross-codex-5.3-xhigh



---

### codex-5.3-xhigh-cross-claude-opus

Read and executed the instructions from [prompt.md](/Users/auk000v/dev/tools/ivory-tower/research/20260301-192808-cae049/phase2/codex-5.3-xhigh-cross-claude-opus-out/phase2/prompt.md).  
The `## Peer Report (claude-opus)` section in that file is empty, so I used the available Claude report from the prior run at [claude-opus-report.md](/Users/auk000v/dev/tools/ivory-tower/research/20260301-191720-9d5a38/phase1/claude-opus-report.md) as the “other report,” then re-verified key claims with fresh web research.

## Refined Analysis (Cross-Pollinated + Newly Verified)

As of **March 1, 2026**, the core conclusion still stands: for a general-purpose **agent** eval runner, you should center on **laude-institute/harbor + inspect-harbor + Inspect AI**, not `av/harbor` (which is valuable infrastructure but a different eval paradigm).

### 1) What the peer report added that improved the picture
- It went deeper on `av/harbor` service taxonomy (frontends/backends/satellites) and explicitly treated Harbor Bench as model-level LLM judging rather than environment-grounded agent eval.
- It highlighted benchmark-specific operational constraints (Spider2 cloud DB credentials, LongMemEval long-history/statefulness).
- It introduced hybrid architecture thinking: use `av/harbor` for model serving/proxy while using Harbor Framework for agent benchmarking.

### 2) Peer claims that required correction or nuance after verification
- **Outdated/incorrect now**: “No existing Harbor adapter for Spider2.”  
  Verified current state: Harbor registry exposure in inspect-harbor includes `spider2-dbt@1.0` (`spider2_dbt_1_0`) with 64 samples.
- **Nuance needed**: Spider2 scope mismatch.  
  Spider2 upstream now emphasizes `Spider2-DBT` (68 tasks) while Harbor listing exposes 64 samples; this is likely an adapter/subset/packaging delta, not full parity with original 632-problem framing.
- **Still true**: LongMemEval is not present in inspect-harbor’s generated registry table (no match), so LongMemEval remains custom adapter work.

### 3) New findings neither report covered well
- **inspect-harbor fidelity caveat**: converter enforces a **minimum 6144 MB memory** unless explicitly overridden.  
  This can silently alter benchmark resource conditions vs original task definitions.
- **Version resolution behavior** in inspect-harbor generic loader: when dataset version omitted, precedence is documented as `"head" > highest semver > lexical last` (important for reproducibility).
- **Execution contract details**:
  - `inspect-harbor` scorer copies `/tests`, runs verifier, and parses `/logs/verifier/reward.txt` then `reward.json`.
  - Oracle solver runs `/solution/solve.sh` and intentionally may leave `/solution` state for scorer-dependent tasks.
- **Harbor lifecycle internals** (more concrete than prior summaries):
  - `Job` expands dataset/task configs into trial configs, supports resume semantics, computes metrics continuously.
  - `Trial` performs environment setup → agent setup/run → verifier → cleanup/artifact handling with timeout/retry behavior.
  - Task download path uses git sparse-checkout and optionally git-lfs (with warning if missing), which affects remote task portability.
- **Provider capability constraint** confirmed in docs: multi-container task support is currently Daytona + local Docker; not Modal/E2B.

### 4) Refined architecture for a mix-and-match eval runner

1. **Control Plane (your runner CLI/manifest)**
- Inputs: `benchmark_id`, `solver_id`, `model`, `env_profile`, `budget`, `seed`, `registry`.
- Materialize immutable experiment spec with pinned commits/versions.

2. **Benchmark Plane**
- Preferred path: Harbor registry datasets (official or private).
- For unsupported suites (LongMemEval): adapter generator emits Harbor task dirs + registry entry + parity metadata.

3. **Solver Plane**
- Default: Inspect solver APIs (`@solver`, agents via `as_solver()`).
- Optional Harbor-native agents for direct `harbor run` workflows.

4. **Execution Plane**
- Driver: `inspect eval inspect_harbor/harbor` for cross-solver flexibility.
- Sandbox profile chosen per benchmark (`docker` local, `daytona` for scale/multi-container).

5. **Scoring/Normalization Plane**
- Preserve raw reward JSON and verifier artifacts.
- Normalize into shared schema (`dataset`, `task`, `solver`, `model`, `reward`, `timings`, `exception_type`, `artifact_uri`).

6. **Reproducibility Guardrails**
- Fail run if dataset version is implicit and not resolved to a recorded concrete value.
- Record effective resource overrides (especially memory floor effects).

### 5) Spider2 + LongMemEval integration plan (practical)

- **Spider2**
  - Treat `spider2-dbt` as immediately runnable Harbor-compatible path.
  - Do not claim equivalence to full Spider2 enterprise setting without parity documentation.
  - Explicitly declare whether evaluation is on DBT subset (and task count used).

- **LongMemEval**
  - Adapter should package each question instance with serialized history and deterministic verifier path.
  - For very long histories, define task variants (`S`, `M`, oracle-retrieval) and resource tiers.
  - Inference: you can map “stateful memory” to Harbor by encoding history/session artifacts per task, but you must preserve evaluation semantics carefully.

### 6) Remaining engineering gaps
- LongMemEval adapter + parity experiments are still required.
- Cross-benchmark comparability is non-trivial (binary pass vs multi-metric reward JSON).
- External credentialed benchmarks (e.g., Snowflake-backed settings) need secure secret plumbing and cost controls.
- Registry/task freshness can drift; pinning and cache invalidation policy must be explicit.

## Sources
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/datasets  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://harborframework.com/docs/agents  
- https://harborframework.com/docs/agents/trajectory-format  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/run-jobs/cloud-sandboxes  
- https://harborframework.com/docs/run-jobs/results-and-artifacts  
- https://pypi.org/project/harbor/  
- https://pypi.org/project/inspect-harbor/  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/README.md  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
- https://github.com/av/harbor/wiki/2.-Services  
- https://github.com/av/harbor/wiki/5.1.-Harbor-Bench  
- https://github.com/xlang-ai/Spider2  
- https://spider2-sql.github.io/  
- https://github.com/xiaowu0162/LongMemEval  
- https://github.com/UKGovernmentBEIS/inspect_evals  
- https://inspect.aisi.org.uk/solvers.html  
- https://inspect.aisi.org.uk/agents.html


## Your Task

Synthesize everything into a comprehensive final report with this structure:

1. **Executive Summary** -- the most important findings across all investigations
2. **Key Findings** -- organized by THEME (not by source agent), combining the strongest evidence
3. **Areas of Consensus** -- where agents agree, with combined supporting evidence
4. **Areas of Disagreement** -- where agents differed, with analysis of why and which view is better supported
5. **Novel Insights** -- unique findings that emerged from the cross-pollination refinement round
6. **Open Questions** -- what remains uncertain even after independent investigations
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the multi-agent research process (agents used, phases, timing)

Be thorough. This is the final deliverable.