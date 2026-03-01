## 1. Executive Summary

A critical architectural fact is that there are two different “Harbor” projects in play. `inspect-harbor` is built for the **Harbor Framework** from `laude-institute/harbor` (`harborframework.com`), not for `av/harbor` (the local multi-service LLM stack). This is explicit in the package dependency (`harbor>=0.1.44`) and docs that map Harbor task concepts into Inspect AI abstractions.  
Sources: https://pypi.org/project/inspect-harbor/ , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml , https://github.com/laude-institute/harbor , https://github.com/av/harbor

For a general-purpose eval runner that mixes solvers and benchmarks (Spider2, LongMemEval, others), the most reliable path is:
- Inspect AI as the solver/eval control plane.
- Harbor Framework datasets/tasks as the benchmark/environment substrate.
- `inspect-harbor` as the adapter from Harbor tasks to Inspect Task/Sample/Scorer.
- Optional: `av/harbor` as model/backend infrastructure (Ollama, llama.cpp, vLLM, LiteLLM), not as the benchmark harness itself.  
Sources: https://harborframework.com/docs/core-concepts , https://harborframework.com/docs/run-jobs/run-evals , https://pypi.org/project/inspect-harbor/ , https://github.com/av/harbor/wiki/2.-Services

As of March 1, 2026, Spider2-DBT is present in Harbor registry and inspect-harbor wrappers, while LongMemEval is not visible in inspect-harbor’s generated registry list and did not resolve at public Harbor registry URLs tested. That implies custom adapter/registration work is likely required for LongMemEval.  
Sources: https://harborframework.com/registry/spider2-dbt/1.0 , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md , https://harborframework.com/registry/longmemeval/1.0

---

## 2. Background & Context

Harbor Framework (Laude) is an eval/training framework centered on `Task`, `Dataset`, `Agent`, `Container environment`, `Trial`, and `Job`. `harbor run` expands work into trials and executes them in parallel, producing per-job and per-trial outputs.  
Sources: https://harborframework.com/docs/core-concepts , https://harborframework.com/docs/run-jobs/run-evals

Harbor tasks are directory-based (`instruction.md`, `task.toml`, `environment/`, `tests/`, optional `solution/`). Datasets can be local directories or registry entries backed by Git URLs/commits/paths (`dataset@version`).  
Sources: https://harborframework.com/docs/tasks , https://harborframework.com/docs/datasets

`inspect-harbor` exposes Harbor datasets to Inspect AI and supports loading from registry, local path, and git task sources. It also documents Harbor-to-Inspect mapping and Oracle-solver parity checks.  
Sources: https://pypi.org/project/inspect-harbor/

`av/harbor` is a separate project focused on orchestrating local AI services/backends/satellites (Ollama, vLLM, LiteLLM, lm-eval-harness, Harbor Bench, etc.), with commands like `harbor up`, `harbor defaults`, and service-level `harbor run <service> <command>`.  
Sources: https://github.com/av/harbor , https://github.com/av/harbor/wiki/1.-Harbor-User-Guide , https://github.com/av/harbor/wiki/3.-Harbor-CLI-Reference

---

## 3. Key Findings

### A) Harbor Framework architecture for eval orchestration
Harbor Framework defines the right primitives for agent benchmark execution: task format + dataset registry + trial/job parallelization + artifact/result outputs.  
Sources: https://harborframework.com/docs/core-concepts , https://harborframework.com/docs/run-jobs/run-evals , https://harborframework.com/docs/tasks

Datasets are git-backed and versioned; registration is explicit and reproducibility-friendly via commit pinning and `dataset@version`.  
Sources: https://harborframework.com/docs/datasets , https://harborframework.com/docs/datasets/registering-datasets

### B) inspect-harbor is the Inspect bridge for Harbor Framework
`inspect-harbor` is explicitly “Inspect AI interface to Harbor tasks,” with dependency on Harbor Framework package versions and explicit Harbor↔Inspect concept mappings.  
Sources: https://pypi.org/project/inspect-harbor/ , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml

It supports loading patterns needed for a general runner:
- Registry dataset via `dataset_name_version`.
- Custom registry (`registry_url` / `registry_path`).
- Local task/dataset path.
- Git task path + commit pinning.
Sources: https://pypi.org/project/inspect-harbor/

### C) Solver extensibility should be owned by Inspect
Inspect solvers are first-class composable/custom functions over `TaskState`; this is the natural place to define pluggable “agent solvers” for mix-and-match evaluation.  
Sources: https://inspect.aisi.org.uk/solvers.html

Harbor Framework agents can also be custom (`BaseAgent`/`BaseInstalledAgent`), but in an Inspect-centric runner, solver logic should primarily live in Inspect while Harbor provides task/environment semantics.  
Sources: https://harborframework.com/docs/core-concepts , https://inspect.aisi.org.uk/solvers.html

### D) Benchmark onboarding is adapter-centric
Harbor adapters are the intended path for integrating external benchmarks. Workflow emphasizes understanding benchmark instructions/environments/tests/solutions, then adapting to Harbor task format and validating parity.  
Sources: https://harborframework.com/docs/datasets/adapters

This is the right mechanism for integrating non-native suites (including LongMemEval if absent from public registry).  
Sources: https://harborframework.com/docs/datasets/adapters , https://harborframework.com/docs/datasets/registering-datasets

### E) Current benchmark availability signals
Spider2-DBT is publicly present in Harbor registry and in inspect-harbor wrappers (`spider2_dbt_1_0`, `spider2_dbt`).  
Sources: https://harborframework.com/registry/spider2-dbt/1.0 , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md

There is a metadata inconsistency: Spider2-DBT page text says “68 examples,” while the registry page also shows `Tasks (64)`, and inspect-harbor REGISTRY table line indicates sample count `64`.  
Sources: https://harborframework.com/registry/spider2-dbt/1.0 , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
Inference: dataset/task filtering or stale metadata likely explains the mismatch; validate exact task count in your run manifest.

LongMemEval is not present in inspect-harbor generated registry/task wrappers inspected, and public Harbor registry LongMemEval URLs did not resolve successfully in this check.  
Sources: https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md , https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py , https://harborframework.com/registry/longmemeval/1.0  
Inference: LongMemEval likely requires custom adapter + registry entry (or exists only in private/internal registry).

### F) What av/harbor does (and does not) provide for this goal
`av/harbor` is strong for backend/service orchestration and exposes many backends/satellites, including eval-related satellites (`lm-evaluation-harness`, `Harbor Bench`).  
Sources: https://github.com/av/harbor/wiki/2.-Services , https://github.com/av/harbor/wiki/1.-Harbor-User-Guide

Its built-in eval tools are oriented to OpenAI-compatible API benchmarking and lm-eval workflows, not Harbor task-format multi-trial agent eval orchestration.  
Sources: https://github.com/av/harbor/wiki/5.1.-Harbor-Bench , https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness , https://github.com/av/harbor/wiki/3.-Harbor-CLI-Reference

---

## 4. Analysis

The cleanest general-purpose architecture is:

1. **Eval control plane:** Inspect AI tasks + custom solver registry (per-agent solver IDs).  
2. **Benchmark plane:** Harbor Framework datasets via `inspect_harbor/harbor` (`dataset_name_version`, `path`, custom registries).  
3. **Model/backend plane:** Either direct providers or `av/harbor` endpoints (Ollama/vLLM/llama.cpp/LiteLLM).  
4. **Execution plane:** Inspect sandbox + Harbor task environments; concurrency managed by Inspect run config and Harbor dataset/task slicing.  
5. **Results plane:** Inspect logs plus Harbor-style task artifacts and reproducibility metadata (dataset version, git commit, solver version, model ID, seed/config).

Why this works:
- It keeps solver experimentation where Inspect is strongest (custom chains/agents, flexible scoring).
- It keeps benchmark/environment semantics where Harbor Framework is strongest (task format, adapters, registry).
- It allows `av/harbor` to remain infrastructure-only, avoiding semantic mismatch.

Recommended implementation order:
1. Stand up runner for `spider2-dbt@1.0` through `inspect_harbor/harbor`.
2. Add solver plug-in registry in Inspect (`solver_id -> callable`) and run matrix sweeps over solver × model.
3. Integrate LongMemEval by creating Harbor adapter + registry entry, then load through same runner path.
4. Add reproducibility guardrails: pin dataset version and registry commit, store run manifests, and enforce immutable run configs.

---

## 5. Open Questions & Gaps

1. LongMemEval public availability in Harbor registry remains unclear; check your target registry (public vs private) explicitly.  
2. Spider2-DBT sample/task count discrepancy (`68` vs `64`) should be validated against real downloaded task set in your run.  
3. inspect-harbor wrappers are generated snapshots; confirm wrapper freshness or use generic `inspect_harbor/harbor` path to avoid wrapper lag.  
4. If strict use of `av/harbor` is required for everything, custom engineering is needed to bridge Inspect task semantics to service-only eval tooling.  
5. For large-scale runs, concurrency/network/topology between Inspect sandboxes and `av/harbor` services must be validated in your deployment environment.

---

## 6. Sources

- https://github.com/av/harbor  
- https://github.com/av/harbor/wiki/1.-Harbor-User-Guide  
- https://github.com/av/harbor/wiki/2.-Services  
- https://github.com/av/harbor/wiki/3.-Harbor-CLI-Reference  
- https://github.com/av/harbor/wiki/5.1.-Harbor-Bench  
- https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness  
- https://github.com/av/harbor/wiki/2.3.5-Satellite%3A-LiteLLM  
- https://github.com/laude-institute/harbor  
- https://pypi.org/project/harbor/  
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/getting-started  
- https://harborframework.com/docs/run-jobs/run-evals  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/datasets  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/registry  
- https://harborframework.com/registry/spider2-dbt/1.0  
- https://harborframework.com/registry/longmemeval  
- https://harborframework.com/registry/longmemeval/1.0  
- https://pypi.org/project/inspect-harbor/  
- https://github.com/meridianlabs-ai/inspect_harbor  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/pyproject.toml  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
- https://inspect.aisi.org.uk/solvers.html
