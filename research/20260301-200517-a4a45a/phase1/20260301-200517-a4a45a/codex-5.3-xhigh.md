**Research Report: Building a General-Purpose Eval Runner with Harbor + inspect-harbor**

## 1. Harbor architecture (what is orchestrating what)

There are two closely related but operationally different “Harbor” layers in your source set:

1. `av/harbor` is an infrastructure/tooling project centered on Docker Compose service orchestration, service templates/handles, profiles, and tool wrappers (`harbor`, `harbor bench`, `harbor compose setup`). It gives you runtime service control and repeatable eval command automation. [1][2][3][4][5]  
2. `harbor-python` / Harbor Framework docs describe typed registries and evaluation primitives (benchmarks, solvers, jobs/trials, adapters, evaluator/task runner hooks). This is the model/eval abstraction layer used by `inspect-harbor`. [18][19][20][21][22][23][24][25][26][30]

This split matters: the strongest architecture is to use `av/harbor` for service/runtime management and Harbor Framework + `inspect-harbor` for typed eval execution.

## 2. inspect-harbor’s role as Inspect AI bridge

`inspect-harbor` is an Inspect AI plugin package (latest shown: `0.2.5`, released **January 13, 2026**) that integrates Harbor benchmark/solver concepts into Inspect tasks/solvers/scorers. [6][7]

Bridge responsibilities:

1. `default_harness` manages service lifecycle (local compose or hosted SDK) and then invokes `inspect_ai.eval(...)`. [8]  
2. `HarborServiceManager` handles local Docker-compose-driven service startup/teardown and service URL discovery. [9]  
3. `SDKServiceManager` handles hosted Harbor SDK service loading/unloading. [10]  
4. `harbor_task` / `sample_setup` build Inspect `Task` objects from Harbor benchmark specs and service requirements. [14]  
5. `harbor_solver` maps Inspect solver calls to Harbor solver specifications. [12]  
6. `harbor_scorer` evaluates samples via Harbor benchmark evaluation flow and returns Inspect `Score`/metrics. [13][11]

So `inspect-harbor` is the glue between Inspect AI execution and Harbor service/benchmark/solver semantics.

## 3. How to define/register new agent solvers

You have two extension points:

1. Harbor-native solver registration: define function/class solver and register with Harbor (`@solver` patterns, registry loading, optional CLI/module registration). [22][23]  
2. Agent registration for custom backends: implement `BaseAgent` (`call`, optional async/batch), then register (`@register_agent`) so solvers can reference it. [27][28][29]

In `inspect-harbor`, you then reference the Harbor solver through `harbor_solver(solver=..., prompt=..., agent=..., tool_choice=..., solver_kwargs=...)`. [12]

Practical pattern:
1. Implement/register agent backend in Harbor Framework.
2. Implement/register solver that targets that agent contract.
3. In Inspect eval config, pass the Harbor solver name + kwargs through `harbor_solver(...)`.

## 4. How to define/register new benchmarks/datasets (Spider2, LongMemEval, others)

Harbor Framework benchmark path:

1. Create benchmark class (subclass benchmark base, implement sample evaluation logic). [24]  
2. Register benchmark (`@benchmark`) and optional wrappers for standardized variants. [25]  
3. Use adapters to normalize dataset shape into Harbor data bundle format (`@adapter`, built-in and custom adapter workflows). [26]

`inspect-harbor` task path:

1. Build Inspect task via `harbor_task(...)` and `sample_setup(...)`. [14]  
2. Existing registry tasks show the pattern for Spider2 and LongMemEval, including args like `difficulty`, `benchmark_kwargs`, `sample_kwargs`, `solver`, `service`, `limit`. [15][16][17]

So for a new benchmark suite:
1. Implement Harbor benchmark + adapter.
2. Register benchmark/wrapper in Harbor registry.
3. Add an `inspect-harbor` task factory (or reuse generic `harbor_task`) that maps dataset samples to Inspect states and scorer.

## 5. Eval execution pipeline (solver vs benchmark lifecycle)

End-to-end lifecycle (Inspect-first with `inspect-harbor`):

1. Harness enters context, starts services (local compose or hosted). [8][9][10]  
2. Inspect task starts; solver step resolves Harbor solver spec and executes solver call path. [12][14]  
3. Scorer step creates Harbor benchmark instance/spec and evaluates samples (`evaluate_sample`, polling completion if needed). [13][11]  
4. Metrics/scores are aggregated in Inspect output. [13]  
5. Harness exits and tears down/unloads services. [8][9][10]

Harbor-native runner lifecycle (Framework-first):

1. `harbor run` loads `JobConfig` and `TrialConfig`. [19][20][21]  
2. Evaluator coordinates tasks/trials/batch runs with configurable task runner hooks (`before_task`, `after_task`, custom runner). [30]  
3. Results are persisted/aggregated per run settings. [19][20][21]

`av/harbor` built-in `harbor bench` lifecycle is command-templated orchestration:
1. Setup command once (often `harbor up`).
2. Expand targets matrix and run per-target eval command.
3. Teardown cleanup. [3][4][5]

## 6. Practical architecture for a general-purpose mix-and-match eval runner

Recommended architecture:

1. **Control plane:** one runner service that owns experiment manifests (`solver_id`, `benchmark_id`, `service_stack`, params, seeds, limits).  
2. **Runtime plane:** `av/harbor` profiles + compose for local backends; optional hosted mode via SDK manager. [2][9][10]  
3. **Registry plane:** Harbor registries for solvers/benchmarks/adapters; enforce stable IDs and versioned metadata. [22][23][24][25][26]  
4. **Execution plane:** Inspect AI + `inspect-harbor` harness/task/solver/scorer for standardized logs and scoring. [8][12][13][14]  
5. **Matrix engine:** generate cross-product of solver x benchmark x service profile x difficulty; run in isolated trials using either Inspect loop or Harbor Job/Trial configs. [19][20][21]  
6. **Results plane:** normalize output schema (run_id, solver_id, benchmark_id, dataset_version, service_digest, metrics, artifacts).

Key design choice:
- If you want strongest Inspect observability and custom Python control, make Inspect + `inspect-harbor` the top orchestrator.
- If you want Harbor-native job/trial config governance, make Harbor runner primary and invoke Inspect tasks where needed.
- Avoid dual orchestration for a single run (pick one top-level executor).

## 7. Existing examples/patterns to copy

1. `harbor-bench` Inspect template shows practical environment templating + setup/teardown for `inspect eval`. [4]  
2. `harbor-bench` core execution code shows setup -> target loop -> teardown orchestration pattern. [5]  
3. `inspect-harbor` registry includes ready task suites (including Spider2, LongMemEval) with consistent argument surfaces. [15][16][17]  
4. Harbor adapters docs show reusable ingestion strategy for heterogeneous datasets. [26]

## 8. Gaps, limitations, and custom engineering needed

1. Documentation split: explicit official mapping between `av/harbor` and Harbor Framework internals is not clearly centralized; you will likely define your own integration boundary. [1][2][18]  
2. Overlapping orchestration layers (`harbor bench`, Harbor jobs/trials, Inspect eval) can duplicate responsibilities unless you standardize ownership. [3][19][30]  
3. Benchmark integration still needs task-specific engineering (dataset prep, sample mapping, benchmark kwargs conventions). [16][17][24][26]  
4. Metric harmonization across benchmarks is not automatic; you need a unifying result schema for cross-benchmark comparison. [13][16][17]  
5. Service reproducibility (exact model backend/image/profile/version pinning) must be enforced by your runner metadata; defaults are not enough for strict reproducibility. [2][9][20]

## Sources

[1] https://github.com/av/harbor  
[2] https://github.com/av/harbor/wiki/1.-Harbor-User-Guide  
[3] https://github.com/av/harbor/tree/main/harbor-bench  
[4] https://github.com/av/harbor/blob/main/harbor-bench/templates/inspect-eval-template.yaml  
[5] https://github.com/av/harbor/blob/main/harbor-bench/src/harbor_bench/core.py  
[6] https://pypi.org/project/inspect-harbor/  
[7] https://github.com/meridianlabs-ai/inspect_harbor  
[8] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/default_harness  
[9] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/HarborServiceManager  
[10] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/SDKServiceManager  
[11] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/HarborBenchmark  
[12] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/harbor_solver  
[13] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/harbor_scorer  
[14] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/task  
[15] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/  
[16] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/spider2/  
[17] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/longmemeval/  
[18] https://harborframework.com/docs/core-concepts  
[19] https://harborframework.com/docs/running-jobs  
[20] https://harborframework.com/docs/running-jobs/job-configuration  
[21] https://harborframework.com/docs/running-jobs/trial-configuration  
[22] https://harborframework.com/docs/solvers/custom-solvers  
[23] https://harborframework.com/docs/solvers/registering-solvers  
[24] https://harborframework.com/docs/benchmarks/benchmarking-tasks  
[25] https://harborframework.com/docs/benchmarks/registering-benchmarks  
[26] https://harborframework.com/docs/adapters/  
[27] https://harborframework.com/docs/agents/base-agents  
[28] https://harborframework.com/docs/agents/registering-agents  
[29] https://harborframework.com/docs/agents/custom-agent-example  
[30] https://harborframework.com/reference/core_api/
