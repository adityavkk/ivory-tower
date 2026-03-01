## Harbor + inspect-harbor Research Report (as of March 1, 2026)

### 1) Harbor architecture: how it orchestrates backends, services, and eval tasks
Harbor’s core model is `Task -> Dataset -> Trial -> Job`. A task is `instruction.md + environment + tests/test.sh (+ optional solution)`, datasets are task collections, a trial is one attempt, and a job is a parallelized collection of trials.  
Source: https://harborframework.com/docs/core-concepts , https://harborframework.com/docs/tasks

In execution terms, Harbor’s `Job` class is the main entrypoint: it expands job config into many `TrialConfig`s (agents x tasks x attempts), creates an orchestrator via `OrchestratorFactory`, runs trials concurrently, and aggregates metrics/results to `result.json`.  
Source: https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py

Harbor environment backends are container-first (local Docker and cloud sandboxes like Daytona, Modal, E2B). Multi-container support is explicitly called out for Daytona.  
Source: https://harborframework.com/docs/run-jobs/cloud-sandboxes

### 2) inspect-harbor’s role as the Inspect AI <-> Harbor bridge
`inspect-harbor` (PyPI `inspect-harbor`, latest shown as `0.4.5`, released February 25, 2026) exposes Harbor datasets/tasks as Inspect tasks.  
Source: https://pypi.org/project/inspect-harbor/

Bridge mechanics in code:
1. `harbor()` loads Harbor tasks from local path, git, or Harbor registry (using Harbor clients/config models).
2. Converts Harbor task objects into Inspect `Sample`s with sandbox specs.
3. Uses a scorer that runs Harbor verifier scripts (`tests/test.sh`) and reads `reward.txt`/`reward.json`.
4. Includes an Oracle solver that runs `solution/solve.sh`.
Sources:  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py

### 3) Defining/registering new agent solvers
Harbor-native path:
1. Implement `BaseAgent` (external) or `BaseInstalledAgent` (installed/headless in-container).
2. Run with `--agent-import-path path.to.agent:Class`.
Source: https://harborframework.com/docs/agents

Inspect-harbor path:
1. Use any Inspect solver via `--solver ...`.
2. Default is a ReAct scaffold with `bash/python/update_plan` tools.
Source: https://pypi.org/project/inspect-harbor/ and https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/README.md

Inference: for a general runner, support both solver types behind one adapter interface (`HarborAgentAdapter`, `InspectSolverAdapter`) so solver onboarding is framework-agnostic.

### 4) Defining/registering new benchmarks/datasets (Spider2 + LongMemEval)
Harbor dataset integration model:
1. Convert benchmark tasks into Harbor task directories.
2. Run locally, verify Oracle passes.
3. Register in registry JSON (`name`, `version`, task git pointers) or use local/custom registry.
Sources:  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/datasets  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://harborframework.com/docs/datasets/adapters

Spider2 status:
- Harbor registry includes `spider2-dbt@1.0`, runnable directly.
- Inspect-harbor auto-generates `spider2_dbt` task functions from Harbor registry.
Sources:  
- https://harborframework.com/registry/spider2-dbt/1.0  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py

LongMemEval status:
- I did not find LongMemEval in Harbor registry/inspect-harbor generated tasks.
- Official LongMemEval benchmark has 500 instances and structured long-session history fields.
Sources:  
- https://harborframework.com/registry  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://github.com/xiaowu0162/LongMemEval

Inference: LongMemEval requires custom Harbor adapter work (task conversion + verifier metric logic), not just “plug and run”.

### 5) Eval execution pipeline in practice
Harbor pipeline:
1. Resolve tasks from local path or registry.
2. Materialize trial matrix (`task x agent x attempt`).
3. Orchestrator runs environments/agents/verifiers with concurrency and hooks.
4. Collect rewards/metrics, write job/trial artifacts, optional artifact collection from sandbox paths.
Sources:  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/run-jobs/results-and-artifacts

Inspect-harbor pipeline:
1. `inspect eval inspect_harbor/<dataset>`
2. Bridge loads Harbor tasks and maps to Inspect samples/sandbox.
3. Solver executes; Harbor scorer runs benchmark verifier script for grading.
Sources: same inspect-harbor files above + https://pypi.org/project/inspect-harbor/

### 6) Practical architecture for a general-purpose mix-and-match eval runner
Recommended architecture:
1. `RunnerConfig` (dataset, solver, model, env, concurrency, retries, artifact paths).
2. `DatasetResolver` supporting Harbor registry/custom registry/local paths.
3. `SolverRegistry` supporting Harbor agent plugins and Inspect solvers.
4. `ExecutionBackend` switch:
   - Harbor backend (`harbor run`) when using Harbor-native agents.
   - Inspect backend (`inspect eval inspect_harbor/...`) when using Inspect solvers.
5. `ResultNormalizer` mapping Harbor and Inspect outputs into one schema for dashboards/leaderboards.

Inference: this avoids forcing all solvers into one framework while reusing Harbor’s task format/registry as the shared benchmark substrate.

### 7) Existing examples/patterns worth copying
1. Harbor built-in benchmark flow (`harbor run -d ... -a ... -m ...`) and cloud scale patterns.  
2. Harbor adapter workflow for converting external benchmarks to Harbor tasks.  
3. inspect-harbor auto-generated task wrappers from Harbor registry (gives immediate Inspect compatibility for registered datasets).  
4. Oracle-first validation pattern (run reference solution before model eval).
Sources:  
- https://harborframework.com/docs/getting-started  
- https://harborframework.com/docs/datasets/adapters  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py  
- https://pypi.org/project/inspect-harbor/

### 8) Gaps, limitations, and custom engineering needed
1. LongMemEval is not presently listed in Harbor registry/inspect-harbor generated tasks, so custom adapter engineering is required.  
2. Harbor docs show custom metrics are local-script based today; hosted custom metric workflows are limited.  
3. Cloud backend capabilities differ (not all support multi-container tasks).  
4. inspect-harbor currently requires Python >=3.12, while LongMemEval docs use Python 3.9 tooling; environment harmonization is needed.  
5. Contradiction noted for Spider2-DBT: page text says “68 examples” but Harbor registry page shows “Tasks (64)”. This should be clarified before benchmarking comparisons.
Sources:  
- https://harborframework.com/registry  
- https://harborframework.com/docs/datasets/metrics  
- https://harborframework.com/docs/run-jobs/cloud-sandboxes  
- https://pypi.org/project/inspect-harbor/  
- https://github.com/xiaowu0162/LongMemEval  
- https://harborframework.com/registry/spider2-dbt/1.0

## Research gaps
1. I did not find an official Harbor-native LongMemEval adapter/repo path in the current Harbor registry artifacts reviewed.  
2. Public docs are strong on task/job usage but thinner on some internal orchestration class contracts beyond source snippets.  
3. I did not find a canonical “Harbor + Inspect hybrid architecture” reference; recommendations above are synthesis/inference from docs and code.

## Sources
- https://harborframework.com/docs  
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/getting-started  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/datasets  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/docs/datasets/metrics  
- https://harborframework.com/docs/run-jobs  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/run-jobs/results-and-artifacts  
- https://harborframework.com/docs/run-jobs/cloud-sandboxes  
- https://harborframework.com/docs/agents  
- https://harborframework.com/registry  
- https://harborframework.com/registry/spider2-dbt/1.0  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py  
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/job/config.py  
- https://pypi.org/project/inspect-harbor/  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/README.md  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py  
- https://github.com/xiaowu0162/LongMemEval  
- https://arxiv.org/abs/2407.10956
