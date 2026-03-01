## 1. Executive Summary
There are two different projects named “Harbor,” and this is the most important architectural clarification before implementation. `inspect-harbor` is built for the **Laude Institute Harbor eval framework** (`laude-institute/harbor`, `harborframework.com`), not for `av/harbor` (the local LLM service stack). This is explicit in `inspect-harbor`’s package metadata and dependencies (`harbor>=0.1.44`) and in its docs linking Harbor tasks/harness concepts.  
Citations: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor pyproject](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml), [laude Harbor repo](https://github.com/laude-institute/harbor), [av/harbor repo](https://github.com/av/harbor).

For a general-purpose eval runner, the clean pattern is: **Harbor as task/environment/runtime substrate** + **Inspect AI as solver/eval control plane** + **inspect-harbor as adapter layer**. Harbor provides task format, dataset registry, environment orchestration, trial/job lifecycle, verification, and artifact handling; inspect-harbor maps these into Inspect’s Task/Sample/Solver/Scorer abstractions.  
Citations: [Harbor Core Concepts](https://harborframework.com/docs/core-concepts), [Harbor Evals](https://harborframework.com/docs/run-jobs/run-evals), [Harbor Tasks](https://harborframework.com/docs/tasks), [inspect_harbor `_task.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py), [inspect_harbor `_converters.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py), [inspect_harbor `_scorer.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py), [inspect_harbor `_solver.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py).

The main engineering risk is **catalog/version drift** between Harbor’s live registry and inspect-harbor’s generated wrappers. inspect-harbor generates static task functions from Harbor registry snapshots; its registry/task wrappers currently include `spider2-dbt` but do not include `longmemeval` in the generated list I inspected.  
Citations: [inspect_harbor generator script](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py), [inspect_harbor tasks.py](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py), [inspect_harbor REGISTRY.md](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md), [Harbor Registry UI](https://harborframework.com/registry).

## 2. Background & Context
Harbor defines six core runtime concepts: `Task`, `Dataset`, `Agent`, container `Environment`, `Trial`, and `Job`. A task is file-based (`instruction.md`, `task.toml`, `environment/`, `tests/`, optional `solution/`). A job expands into many trials and runs them concurrently.  
Citations: [Core Concepts](https://harborframework.com/docs/core-concepts), [Task Structure](https://harborframework.com/docs/tasks), [Evals](https://harborframework.com/docs/run-jobs/run-evals).

Harbor datasets can be local directories or registry entries pointing to git repos/commits/paths. Registration is git-backed and versioned (`name@version`), with support for custom registries via `--registry-path`/`--registry-url`.  
Citations: [Datasets](https://harborframework.com/docs/datasets), [Registering Datasets](https://harborframework.com/docs/datasets/registering-datasets).

inspect-harbor exposes Harbor datasets as Inspect tasks and provides Harbor-aware scorer/solver components. It also supports a generic `harbor()` entrypoint for loading by dataset name/version, local path, or git task info.  
Citations: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor `_task.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py), [inspect_harbor `_registry.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/_registry.py).

## 3. Key Findings

### Theme A: Harbor orchestration architecture
Harbor’s execution path is operationally clear in source: `harbor run` aliases jobs start; jobs expand into trial configs; orchestrator runs trials concurrently; each trial handles environment startup, agent setup/run, verifier execution, artifact capture, cleanup, and result serialization.  
Citations: [CLI main](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/cli/main.py), [job config](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/job/config.py), [local orchestrator](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/orchestrators/local.py), [trial lifecycle](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py).

The verifier model is deterministic harness-style: copy tests into sandbox, execute test script, read reward from `reward.txt` or `reward.json`. Trial artifacts can be convention-driven (`/logs/artifacts`) or config-driven, with manifest output.  
Citations: [verifier source](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/verifier/verifier.py), [Task Structure](https://harborframework.com/docs/tasks), [Artifact Collection](https://harborframework.com/docs/run-jobs/results-and-artifacts).

### Theme B: inspect-harbor’s bridge role
`inspect_harbor.harbor()` loads Harbor tasks (local path, git task, or registry dataset), converts each to Inspect `Sample`, and returns an Inspect `Task` with default ReAct solver and Harbor scorer. This is the core bridge layer.  
Citations: [inspect_harbor `_task.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py), [inspect-harbor PyPI mapping table](https://pypi.org/project/inspect-harbor/).

Bridge mappings are explicit: Harbor instruction -> `Sample.input`; environment -> `SandboxEnvironmentSpec`; tests -> Harbor scorer; solution script -> Oracle solver.  
Citations: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor `_converters.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py), [inspect_harbor `_scorer.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py), [inspect_harbor `_solver.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py).

### Theme C: defining/registering new agent solvers
In Harbor, new agents are implemented via `BaseAgent` (external) or `BaseInstalledAgent` (installed/headless in-container), then invoked with `--agent-import-path`.  
Citations: [Harbor Agents docs](https://harborframework.com/docs/agents), [BaseAgent](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/base.py), [BaseInstalledAgent](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/installed/base.py).

In inspect-harbor, solver choice is an Inspect concern: you can pass custom solver implementations via `--solver` or Python API. So your “mix-and-match” runner should treat solver as a pluggable Inspect abstraction rather than a Harbor registry object.  
Citations: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [Inspect Solvers](https://inspect.aisi.org.uk/solvers.html).

### Theme D: defining/registering new benchmarks/datasets
Harbor’s adapter workflow is mature and benchmark-centric: create adapter (`harbor adapters init`), produce Harbor task directories, run Oracle parity, run benchmark parity experiments, publish metadata/results, and register dataset in Harbor registry.  
Citations: [Adapters docs](https://harborframework.com/docs/datasets/adapters), [Registering Datasets](https://harborframework.com/docs/datasets/registering-datasets).

inspect-harbor wrappers are generated from Harbor registry (`scripts/generate_tasks.py`). This is convenient but introduces release lag risk; generic `inspect_harbor/harbor` with `dataset_name_version` is the fallback to run datasets not yet wrapped as static functions.  
Citations: [generate_tasks.py](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py), [inspect_harbor `_task.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py), [inspect_harbor tasks.py](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py).

### Theme E: benchmark coverage (Spider2 / LongMemEval) and current state
Current inspect-harbor generated catalogs include `spider2-dbt` task functions (e.g., `spider2_dbt_1_0`, `spider2_dbt`) but no `longmemeval` wrapper in the generated tasks/registry files inspected.  
Citations: [inspect_harbor tasks.py](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py), [inspect_harbor REGISTRY.md](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md).

Harbor’s live registry UI clearly lists `spider2-dbt@1.0`; I did not see `longmemeval` there in the captured listing. So if LongMemEval is required, expect custom registry or adapter work unless you validate a newer private/internal registry entry.  
Citation: [Harbor Registry](https://harborframework.com/registry).

### Theme F: practical architecture for a general-purpose eval runner
Recommended architecture:
- Benchmark adapter plane: Harbor datasets (`dataset@version` or local path).
- Solver plane: Inspect solvers/agents (`--solver`, model, tool policy).
- Execution plane: sandbox provider + concurrency (Docker/Daytona/Modal/E2B).
- Result plane: Harbor/Inspect logs + artifacts + normalized summary table.

Operationally, make every run fully declarative (benchmark ID + solver ID + model + provider + resource overrides + seed/attempts), pin benchmark versions (`@version` and commit IDs), and preserve run manifests/artifacts.

## 4. Analysis
The Harbor + inspect-harbor stack is a good fit for your “general-purpose runner” goal because Harbor already standardizes tasks/verification/environments, while Inspect already standardizes solver experimentation. The bridge code is small and readable, which reduces integration risk.  
Citations: [trial lifecycle](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py), [inspect_harbor `_task.py`](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py).

The most important tradeoff is **velocity vs reproducibility**. Using “latest” dataset aliases and generated wrappers is fast, but can drift. Using pinned versions/commits and explicit custom registries is slower operationally but reproducible. For a benchmarking runner, reproducibility should usually win.

Pragmatic recommendation: build around generic `inspect_harbor/harbor` first (single integration point), then optionally add convenience wrappers. This avoids waiting for wrapper regeneration and works for private/internal datasets.

## 5. Open Questions & Gaps
1. Project-name ambiguity remains a real risk: if your target was truly `av/harbor`, inspect-harbor is not that integration path.  
2. Registry/catalog drift: Harbor registry listings and inspect-harbor generated wrappers can diverge by release timing.  
3. LongMemEval status is unclear from the currently captured public registry/wrapper snapshots; validate against your exact target registry before implementation.  
4. Some behavior differences may matter for strict parity (e.g., inspect-harbor default solver scaffold, resource overrides, timeout handling nuances).  
5. Harbor docs note some tooling still “coming soon” for dataset registration workflows, so part of benchmark onboarding remains manual.  
Citations: [av/harbor](https://github.com/av/harbor), [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor REGISTRY.md](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md), [Harbor Registry](https://harborframework.com/registry), [Registering Datasets](https://harborframework.com/docs/datasets/registering-datasets).

## 6. Sources
- https://github.com/laude-institute/harbor  
- https://pypi.org/project/harbor/  
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/agents  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/run-jobs/results-and-artifacts  
- https://harborframework.com/docs/run-jobs/cloud-sandboxes  
- https://harborframework.com/docs/datasets  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/registry  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/job/config.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/trial/config.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/orchestrators/base.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/orchestrators/local.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/verifier/verifier.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/base.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/installed/base.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/environments/base.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/tasks/client.py  
- https://pypi.org/project/inspect-harbor/  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/_registry.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_sandbox_utils.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py  
- https://inspect.aisi.org.uk/tasks.html  
- https://inspect.aisi.org.uk/solvers.html  
- https://github.com/av/harbor
