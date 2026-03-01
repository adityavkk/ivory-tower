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
