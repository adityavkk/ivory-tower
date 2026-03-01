# Research Synthesis

2 AI agents independently researched a topic, then each produced a refined
report after cross-pollinating findings by skeptically reviewing each other's work. You
have all their refined reports below. Each report is already a comprehensive standalone
document -- your job is to produce the definitive final version.

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Refined Reports
### codex-5.3-xhigh-refined

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


---

### opencode-wibey-opus-4-6-refined

Now let me read my original report and then the peer report in detail. Let me also start planning this task.
Let me now audit both reports and conduct new web research. Let me verify key claims from the peer report and fill gaps.

**My report audit:**
- Strengths: Good coverage of av/harbor architecture, strong on Inspect AI solver patterns, clear architecture diagram, detailed benchmark integration guidance
- Weaknesses: Relied partly on DeepWiki rather than primary sources for Harbor internals; didn't examine Harbor Framework (laude-institute/harbor) source code directly; didn't look at inspect-harbor source code in detail
- The peer report goes much deeper into Harbor Framework internals (job config, orchestrators, trial lifecycle, verifier) and inspect-harbor source code (converters, scorers, solvers, sandbox utils)

**Peer report analysis:**
- Much stronger on Harbor Framework architecture: provides specific source file references (local orchestrator, trial lifecycle, verifier, etc.)
- Identifies the adapter workflow for benchmarks, which I missed
- More concrete on inspect-harbor's bridge mechanics (converters, scorer, solver modules)
- Notes LongMemEval is NOT in the Harbor registry -- important gap I didn't verify
- Recommends building around generic `inspect_harbor/harbor` as single integration point
- Notes registry/version drift as a key risk

Let me now verify critical claims through web research:
Excellent. Now let me fetch more specific sources to verify additional claims and fill remaining gaps.
Now let me fetch a few more sources to round out the research -- checking the Harbor Framework's cloud sandboxes, training workflows, and the Inspect AI agent bridge docs.
Now let me also check the av/harbor GitHub repo for its current state to verify claims about it.
I now have comprehensive information from primary sources. Let me write the definitive report.
Now let me determine the output path and write the report.
The definitive refined report has been written to:

`/Users/auk000v/dev/tools/ivory-tower/research/20260301-210801-e03e52/phase2/opencode-wibey-opus-4-6-refined-out/phase2/report.md`

Key improvements over my original report, informed by the peer report and fresh verification:

1. **Harbor Framework depth**: Substantially expanded coverage of the Harbor Framework (laude-institute/harbor) architecture -- the trial lifecycle, verifier mechanics, job/trial config, cloud sandbox support (Daytona/Modal/E2B), and the Terminus-2 reference agent with its RL support and context summarization system.

2. **Adapter workflow**: Added the complete nine-step adapter development workflow from Harbor Framework docs, which neither my original report nor I had covered at the level of detail warranted. This is critical for onboarding new benchmarks like LongMemEval.

3. **Source code verification**: Read and verified inspect-harbor's actual source code (`_task.py`, `_converters.py`, `_scorer.py`) to confirm bridge mechanics -- including the 6GB minimum memory enforcement, the reward file parsing logic, and the exact conversion pipeline.

4. **Registry verification**: Confirmed the current Harbor registry has 47+ datasets (counted from the live registry page), that spider2-dbt shows 64 tasks (not 68 as sometimes reported), and that LongMemEval is definitively absent.

5. **Corrected the generic entrypoint recommendation**: Following the peer report's insight, emphasized using `harbor()` with `dataset_name_version` as the primary integration point rather than per-dataset wrapper functions, due to registry/catalog drift risk.

6. **Two execution paths analysis**: Added a structured comparison between Harbor Framework's native `harbor run` pipeline and Inspect AI's `inspect eval` pipeline, covering solver ecosystems, sandbox providers, results formats, and RL training support -- helping readers make an informed architectural choice.

7. **31 verified sources** with 26 from direct source code or primary documentation (up from 17 in the original).


## Your Task

Synthesize these reports into a single, comprehensive final report. Since each input
report is already a full research document, focus on:

- **Resolving contradictions** -- where reports disagree, weigh the evidence and reach a
  conclusion (or explain why the question is genuinely unresolved)
- **Combining depth** -- each agent may have gone deepest on different subtopics; merge
  the best analysis from each into a unified treatment
- **Deduplicating without losing nuance** -- remove redundancy but preserve distinct
  analytical perspectives where they add value
- **Identifying what everyone missed** -- gaps that persist across ALL reports are the
  most important open questions

Write the final report with this structure:

1. **Executive Summary** -- the most important findings across all investigations
2. **Background & Context** -- unified context that the reader needs
3. **Key Findings** -- organized by THEME (not by source agent), combining the strongest
   evidence from all reports. Go deep. This is the most important section.
4. **Areas of Consensus** -- where agents independently reached the same conclusions,
   with combined supporting evidence
5. **Areas of Disagreement** -- where agents differed, with analysis of why and which
   view is better supported by evidence
6. **Open Questions** -- what remains uncertain even after multiple independent investigations
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the multi-agent research process (agents used,
   phases, timing)

Be thorough and write in depth. This is the final deliverable -- it should be the
definitive reference document on this topic.