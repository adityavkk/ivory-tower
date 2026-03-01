# Research Synthesis

2 AI agents independently researched a topic, then cross-pollinated
findings by skeptically reviewing each other's work. You have all their refinement
reports below.

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Refinement Reports
### codex-5.3-xhigh-cross-opencode-wibey-opus-4-6

**Refined Cross-Pollination Analysis**

### 1) Resolved contradiction: which “Harbor” does `inspect-harbor` actually bridge?
`inspect-harbor` is aligned with **Harbor Framework** (`laude-institute/harbor`), not `av/harbor`.

Evidence:
- `inspect_harbor` dependency is `harbor>=0.1.44` in its `pyproject.toml` ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml)).
- Harbor PyPI package describes itself as Terminal-Bench harness and eval framework ([source](https://pypi.org/project/harbor/)).
- `av/harbor` is a local LLM stack + service orchestration toolkit (`harbor up`, satellites like Promptfoo/lm-eval) ([source](https://github.com/av/harbor), [source](https://github.com/av/harbor/wiki/5.1.-Harbor-Bench)).

So the peer report’s disambiguation was correct; my original report mixed layers too aggressively.

### 2) Verified updates since the earlier reports
- `inspect-harbor` latest is **0.4.5** (released **February 25, 2026**) ([source](https://pypi.org/project/inspect-harbor/)).
- `harbor` latest is **0.1.45** (released **February 27, 2026**) ([source](https://pypi.org/project/harbor/)).
- Harbor registry currently includes **`spider2-dbt@1.0`** ([source](https://harborframework.com/registry)).
- `inspect_harbor` registry table includes `spider2_dbt_1_0`, but **does not list LongMemEval** ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md)).

### 3) New findings neither report covered well

#### A. Registry drift risk between Harbor and inspect-harbor
`inspect_harbor` ships an auto-generated registry map, but current counts differ from live Harbor registry for multiple datasets (e.g., `code-contests`, `seta-env`, `termigen-environments`) ([inspect_harbor REGISTRY](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md), [Harbor registry](https://harborframework.com/registry)).

Inference: inspect-harbor task metadata can lag Harbor registry evolution; treat dataset availability/count as runtime-validated, not assumed.

#### B. Spider2 status changed materially
Spider2 site notes:
- **May 22, 2025**: Spider2-DBT introduced, original Spider2 setting removed for that workflow.
- Spider2-DBT has 68 examples; Harbor adapter exposes 64 runnable tasks currently in registry.
([source](https://spider2-sql.github.io/), [source](https://harborframework.com/registry))

Inference: “Spider2 integration” should target `spider2-dbt` first, not legacy assumptions.

#### C. LongMemEval integration is still custom-work territory
LongMemEval official repo confirms 500-question sets and very long histories (`S` ~115k tokens; `M` ~500 sessions; oracle subset provided) ([source](https://github.com/xiaowu0162/LongMemEval)).
It is not currently listed in inspect-harbor registry tasks ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md)).

### 4) Refined architecture for a general-purpose solver×benchmark runner

#### Recommended control-plane stack
- **Benchmark/task harness**: Harbor Framework (`harbor run`, tasks/jobs/trials) ([core concepts](https://harborframework.com/docs/core-concepts), [evals](https://harborframework.com/docs/run-jobs/run-evals)).
- **Inspect integration**: `inspect-harbor` for Inspect solvers against Harbor tasks ([source](https://pypi.org/project/inspect-harbor/)).
- **Experiment matrix orchestration**: `inspect-flow` for declarative task×model sweeps ([source](https://meridianlabs-ai.github.io/inspect_flow/)).
- **Optional service runtime**: `av/harbor` only as infra provider for local model APIs/tools, not as eval harness bridge ([source](https://github.com/av/harbor), [Promptfoo satellite](https://github.com/av/harbor/wiki/2.3.28-Satellite%3A-Promptfoo), [lm-eval satellite](https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness)).

#### Why this is stronger
- Single scoring ground truth (`tests/test.sh` -> reward files) from Harbor task format ([source](https://harborframework.com/docs/tasks)).
- Solver flexibility from Inspect (`--solver ...`) without rewriting benchmark harnesses ([source](https://pypi.org/project/inspect-harbor/)).
- Better scale path via Harbor cloud sandboxes (Daytona/Modal/E2B; multi-container caveat) ([source](https://harborframework.com/docs/run-jobs/cloud-sandboxes)).

### 5) Concrete build plan (pragmatic sequence)

1. Standardize on **Harbor task format** as canonical benchmark representation.
2. Use `inspect-harbor` only for datasets verified in current registry map; add a pre-run registry check.
3. Start with built-in `spider2_dbt_1_0`; treat LongMemEval as a new Harbor adapter project.
4. Build LongMemEval adapter via `harbor adapters init`, include parity/oracle workflow from adapter docs ([source](https://harborframework.com/docs/datasets/adapters)).
5. Add capability metadata per solver (`max_context`, tool needs, internet need, container mode) and benchmark requirements; reject incompatible pairings early.
6. Use one output schema across runs (job/trial IDs, dataset version, solver ID, model, artifacts path, score fields) and normalize both Harbor-native and Inspect logs.

### 6) What custom engineering is definitely required
- LongMemEval adapter + judge/test harness integration.
- Solver memory strategy for ultra-long contexts (plain ReAct defaults are insufficient for hardest LongMemEval settings).
- Registry/version pinning and drift guards.
- Cross-run result normalizer (Harbor job outputs vs Inspect logs).
- Credential and internet-policy handling for benchmarks with external systems.

---

### Sources
- https://github.com/av/harbor  
- https://github.com/av/harbor/wiki/5.1.-Harbor-Bench  
- https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness  
- https://github.com/av/harbor/wiki/2.3.28-Satellite%3A-Promptfoo  
- https://github.com/laude-institute/harbor  
- https://pypi.org/project/harbor/  
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/run-jobs/cloud-sandboxes  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/registry  
- https://pypi.org/project/inspect-harbor/  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
- https://meridianlabs-ai.github.io/inspect_flow/  
- https://spider2-sql.github.io/  
- https://github.com/xiaowu0162/LongMemEval


---

### opencode-wibey-opus-4-6-cross-codex-5.3-xhigh

Now I have both reports. Let me analyze them carefully, then conduct new research to produce a refined analysis. Let me start by understanding what each report covered and where they diverge.
Let me now analyze the key differences and then verify critical claims from both reports in parallel.

**Key observations from initial analysis:**

1. **Major contradiction on project identity**: My report explicitly disambiguates `av/harbor` (Docker orchestration for LLM stacks) from `laude-institute/harbor` (eval framework), concluding inspect-harbor bridges to the latter. The peer report treats `av/harbor` as the infrastructure/runtime layer and "Harbor Framework" as a separate abstraction layer, claiming they work together.

2. **Version discrepancy**: My report says inspect-harbor v0.4.5 (Feb 25, 2026). Peer says v0.2.5 (Jan 13, 2026). Need to verify.

3. **Peer claims Spider2 and LongMemEval are already in inspect-harbor's registry** ([15][16][17]) — my report says they'd need custom adapters. This is a critical factual disagreement.

4. **Peer introduces concepts not in my report**: `HarborServiceManager`, `SDKServiceManager`, `default_harness`, `harbor_solver()`, `HarborBenchmark` — with specific API reference URLs from meridianlabs-ai docs.

5. **Peer introduces `harbor-bench`** as a separate component within `av/harbor` with Inspect integration templates.

Let me verify these claims now:
Now let me verify the peer report's specific claims about inspect-harbor API docs and the registry containing Spider2/LongMemEval:
Key finding: there is no `harbor-bench` directory in `av/harbor` (404). Let me check what the REGISTRY.md actually contains and verify the peer report's API doc URLs:
Excellent. Now I have very clear verification results. Let me update my findings and write the refined analysis.
Now let me find the output file path and write the refined analysis:
The output directory only has the prompt. I need to write the refined analysis as a file in this directory. Let me write it now:
The refined cross-pollination analysis has been written to `/Users/auk000v/dev/tools/ivory-tower/research/20260301-200517-a4a45a/phase2/opencode-wibey-opus-4-6-cross-codex-5.3-xhigh-out/phase2/output.md`.

Here's a summary of what the peer review uncovered:

**Major corrections to the peer report:**
- The peer report's central architectural claim (av/harbor as infrastructure layer + Harbor Framework as eval layer working together) is **wrong** — they are completely unrelated projects
- The peer's version claim (v0.2.5, Jan 2026) is **wrong** — actual latest is v0.4.5 (Feb 25, 2026)
- The peer's claim that Spider2 and LongMemEval are already in inspect-harbor's registry is **wrong** — only `spider2-dbt@1.0` (a related but different subset) exists
- Multiple API reference URLs cited by the peer return 404 and the described API classes appear fabricated

**New discoveries from cross-pollination:**
- **Spider2-DBT adapter exists** (64 tasks) — proves the adapter pattern for Spider2-family benchmarks, reducing effort for a full Spider2-Lite adapter
- The verified registry contains **47 datasets** — more than originally counted, with very broad coverage
- inspect-harbor supports **resource overrides** (`override_cpus/memory_mb/gpus`) and potentially non-Docker sandboxes (`sandbox_env_name`)
- av/harbor's `harbor bench` (though unrelated) has useful design patterns for **variant permutation engines** and **reproducibility controls**
- LongMemEval needs a fundamentally different adapter approach: conversation data should go in the Docker environment as files, not crammed into `instruction.md`
- Proposed a **concrete result normalization schema** and a **revised priority order** for benchmark integration


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