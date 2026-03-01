# Cross-Pollination Review

You previously conducted deep research and produced a report. Another AI agent
independently researched the SAME topic. You now have access to both reports.

## Your Task

1. **Read YOUR report** carefully -- understand what you covered well and where you went shallow
2. **Read the OTHER report with healthy skepticism** -- look for:
   - Ideas and angles they explored that you completely missed
   - Areas where they went deeper than you did
   - Claims that seem plausible but lack strong sourcing -- verify these independently
   - Contradictions or disagreements between the reports
   - Unique sources or evidence you didn't find
   - Reasoning or conclusions that don't follow from the evidence
3. **Conduct NEW research** (web searches) on:
   - Avenues inspired by the other report that go BEYOND what either covered
   - Contradictions that need resolution through additional evidence
   - Gaps that both reports share
4. **Write a REFINED analysis** that captures what this peer review uncovered

## Critical Rules

- Do NOT simply copy content from the other report into yours
- Do NOT accept claims from the other report at face value -- verify key facts independently via web search
- Use the other report as a SPRINGBOARD for NEW investigation
- The goal is to explore territory that NEITHER report adequately covered
- Your refined analysis should contain substantial NEW content, not just reorganized old content
- If the other report makes a strong claim your research contradicts, investigate further and present evidence for both sides
- Maintain your unique perspective -- don't homogenize with the other report

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Your Original Report


## Peer Report (codex-5.3-xhigh)
**Research Report: Building a General-Purpose Eval Runner with Harbor + inspect-harbor**

**Important Clarification**
There are two different “Harbor” projects in play:

1. `av/harbor` is a local LLM stack/orchestration project (services like Open WebUI, Ollama, etc.) ([source](https://github.com/av/harbor)).
2. `laude-institute/harbor` / `harborframework.com` is the eval framework used by `inspect-harbor` ([sources](https://github.com/laude-institute/harbor), [https://harborframework.com/docs](https://harborframework.com/docs), [https://pypi.org/project/inspect-harbor/](https://pypi.org/project/inspect-harbor/)).

`inspect-harbor` integrates with Harbor Framework (`laude-institute/harbor`), not with `av/harbor`.

## 1) Harbor architecture (how it orchestrates agents, services, eval tasks)

Harbor Framework is organized around these primitives:

1. `Task`: instruction + container environment + verifier test script (`instruction.md`, `task.toml`, `environment/`, `tests/`, optional `solution/`) ([source](https://harborframework.com/docs/tasks)).
2. `Dataset`: collection of tasks (local dir or registry-backed) ([source](https://harborframework.com/docs/datasets)).
3. `Agent`: either external (`BaseAgent`) or installed-in-container (`BaseInstalledAgent`) ([sources](https://harborframework.com/docs/agents), [base agent code](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/base.py), [installed agent code](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/installed/base.py)).
4. `Environment`: unified container abstraction (`BaseEnvironment`) with start/stop/upload/download/exec across Docker/Daytona/Modal/E2B adapters ([sources](https://harborframework.com/docs/core-concepts), [cloud docs](https://harborframework.com/docs/run-jobs/cloud-sandboxes), [base env code](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/environments/base.py)).
5. `Trial`: one agent attempt on one task; handles environment lifecycle, agent run, verification, artifacts, retries/timeouts ([source](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py)).
6. `Job`: collection of trials across datasets/tasks/agents/models; orchestrates concurrency + metrics + resume behavior ([source](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py)).

Inference from sources: Harbor’s core orchestration boundary is `Job -> many TrialConfig -> per-trial environment/agent/verifier`.

## 2) inspect-harbor’s role as bridge to Inspect AI

`inspect-harbor` is a compatibility layer that maps Harbor tasks/datasets into Inspect tasks/samples/solvers/scorers.

1. Loader entrypoint: `inspect_harbor.harbor()` (`@task`) supports local path, git task, registry dataset, and filtering knobs (`dataset_task_names`, `n_tasks`, etc.) ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_task.py)).
2. Conversion: Harbor task -> Inspect `Sample` with `SandboxEnvironmentSpec` and metadata for tests/solution/verifier env/resource config ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_converters.py)).
3. Default solver: Inspect ReAct scaffold with `bash`, `python`, `update_plan`, plus `CompactionEdit` ([sources](https://pypi.org/project/inspect-harbor/), [README raw](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/README.md)).
4. Harbor scorer: copies `/tests`, runs verifier script, parses `/logs/verifier/reward.txt` or `reward.json`, returns score/metadata ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_scorer.py)).
5. Oracle solver: runs Harbor `solution/solve.sh` in sandbox for sanity checks ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_solver.py)).

## 3) Defining/registering new agent solvers

There are two extension planes:

1. Inspect-side solver extension (best for `inspect eval` workflows):
- Implement custom Inspect `@solver` (TaskState + generate pattern) ([source](https://inspect.aisi.org.uk/solvers.html)).
- Invoke via `--solver path/to/file.py@my_solver` or package entrypoint ([source](https://pypi.org/project/inspect-harbor/)).

2. Harbor-native agent extension (best for `harbor run` workflows):
- Implement `BaseAgent` (external) or `BaseInstalledAgent` (in-container/headless) and run via `--agent-import-path` ([sources](https://harborframework.com/docs/agents), [base code](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/base.py), [installed base](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/installed/base.py)).

Inference: for a “general-purpose runner” centered on Inspect logs/analysis, custom Inspect solvers are the primary abstraction; Harbor-native agents are still useful if you also run Harbor jobs directly.

## 4) Defining/registering new benchmarks/datasets (Spider2, LongMemEval)

Dataset onboarding path in Harbor:

1. Convert source benchmark into Harbor task directories (adapter pattern) ([source](https://harborframework.com/docs/datasets/adapters)).
2. Ensure task format compliance (`instruction.md`, `task.toml`, `environment`, `tests`, optional `solution`) ([source](https://harborframework.com/docs/tasks)).
3. Add dataset entry in `registry.json` with name/version/task git refs ([sources](https://harborframework.com/docs/datasets/registering-datasets), [registry docs](https://harborframework.com/docs/datasets)).
4. Optional dataset metrics in registry (`mean`, `sum`, `min`, `max`, or local uv-script custom metric) ([source](https://harborframework.com/docs/datasets/metrics)).

Current status:
1. `spider2-dbt@1.0` is already listed in Harbor registry ([source](https://harborframework.com/registry)).
2. `LongMemEval` was not found in current Harbor registry listing ([source](https://harborframework.com/registry)).

For inspect-harbor exposure:
1. Immediate: use generic `inspect_harbor/harbor` with custom registry/path/git params ([source](https://pypi.org/project/inspect-harbor/)).
2. Named task functions: regenerate `tasks.py` from Harbor registry (`scripts/generate_tasks.py`) and release package ([sources](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/scripts/generate_tasks.py), [tasks.py](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/tasks.py)).

## 5) Eval execution pipeline (lifecycle)

Bridge pipeline (`inspect eval inspect_harbor/...`) is:

1. Resolve dataset/task source (registry/git/local) -> download/cache tasks.
2. Parse Harbor task config + files.
3. Convert each Harbor task to Inspect `Sample` with sandbox spec/metadata.
4. Run solver (default ReAct or custom).
5. Run Harbor scorer: upload tests, execute verifier script.
6. Parse reward file, compute metrics, store logs.

Native Harbor pipeline (`harbor run`) is:

1. Build `JobConfig`, expand datasets -> task configs -> trial configs.
2. Orchestrator runs trials concurrently.
3. Each trial starts environment, sets up/runs agent, runs verifier, collects artifacts, writes result.
4. Job aggregates metrics and per-agent/dataset stats ([sources](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py), [trial](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py), [verifier](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/verifier/verifier.py), [run docs](https://harborframework.com/docs/run-jobs/run-evals), [artifacts](https://harborframework.com/docs/run-jobs/results-and-artifacts)).

## 6) Practical architecture for a mix-and-match general-purpose eval runner

Recommended architecture:

1. `Benchmark Registry Layer`
- Source A: Harbor official registry datasets.
- Source B: private registry + local datasets.
- Source C: adapter-generated datasets (for missing suites like LongMemEval).

2. `Solver Registry Layer`
- Inspect solvers (default ReAct + custom solvers + oracle + third-party solver packages).
- Metadata per solver: required tools, expected model families, timeout profiles.

3. `Execution Layer`
- Driver: Inspect (`inspect eval`) with `inspect_harbor/harbor` generic entrypoint.
- Backend env profiles: docker/daytona/modal/e2b.
- Concurrency policy by benchmark cost profile.

4. `Result Normalization Layer`
- Normalize per-trial outputs to common schema (`task_id`, `dataset`, `solver`, `model`, `reward`, timing, exception class, artifacts pointers).
- Preserve raw verifier JSON for benchmark-specific metrics.

5. `Experiment Control Layer`
- YAML/JSON experiment manifests for reproducibility.
- Explicit pinning: dataset version + git commit + solver version + model revision + env profile.

Inference: this gives you one runner that can evaluate Harbor-native benchmark adapters while still using Inspect’s solver ecosystem and logging.

## 7) Existing examples/patterns worth reusing

1. Registry-driven benchmark execution (`harbor run -d ...`) ([source](https://harborframework.com/docs/run-jobs/run-evals)).
2. Cloud horizontal scaling (`--env daytona`, high `-n`) ([source](https://harborframework.com/docs/run-jobs/cloud-sandboxes)).
3. Artifact convention (`/logs/artifacts`) + manifest-based collection ([source](https://harborframework.com/docs/run-jobs/results-and-artifacts)).
4. Oracle sanity pass before model evals ([source](https://pypi.org/project/inspect-harbor/)).
5. Adapter workflow + parity experiments for benchmark fidelity ([source](https://harborframework.com/docs/datasets/adapters)).
6. Auto-generated inspect-harbor task wrappers from Harbor registry ([source](https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/scripts/generate_tasks.py)).

## 8) Gaps, limitations, and custom engineering needed

1. Naming ambiguity (`av/harbor` vs Harbor Framework) can derail integration planning; choose one architecture explicitly.
2. LongMemEval is not currently listed in Harbor registry, so you likely need a new adapter + registration workflow.
3. inspect-harbor’s named dataset functions are generated snapshots; registry additions may require package regeneration/release for first-class function names.
4. Cross-benchmark metric comparability is not automatic; benchmark-specific reward schemas require custom normalization.
5. Multi-container support differs by sandbox provider (Daytona supports; others may not), which affects benchmark portability.
6. Verification can involve LLM judges (cost + key management + reproducibility concerns) ([source](https://pypi.org/project/inspect-harbor/)).
7. Remote task download depends on git/sparse checkout and potentially git-lfs behavior in Harbor task client ([source](https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/tasks/client.py)).

**Gaps in my research**
1. I could not fully inspect every Harbor internal module due source retrieval limits in this session, so some orchestration internals are inferred from exposed interfaces and docs.
2. I did not find authoritative Harbor-registry support for LongMemEval as of March 1, 2026; if it exists privately, it would require your private registry source to verify.

## Sources
- https://github.com/av/harbor
- https://github.com/laude-institute/harbor
- https://harborframework.com/docs
- https://harborframework.com/docs/getting-started
- https://harborframework.com/docs/core-concepts
- https://harborframework.com/docs/tasks
- https://harborframework.com/docs/datasets
- https://harborframework.com/docs/datasets/registering-datasets
- https://harborframework.com/docs/datasets/adapters
- https://harborframework.com/docs/datasets/metrics
- https://harborframework.com/docs/agents
- https://harborframework.com/docs/run-jobs/run-evals
- https://harborframework.com/docs/run-jobs/results-and-artifacts
- https://harborframework.com/docs/run-jobs/cloud-sandboxes
- https://harborframework.com/registry
- https://pypi.org/project/harbor/
- https://pypi.org/project/inspect-harbor/
- https://github.com/meridianlabs-ai/inspect_harbor/tree/f2cc9c540b22fefd180e35a951fd52a552bec70d
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/README.md
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_task.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_converters.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_solver.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/harbor/_scorer.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/src/inspect_harbor/tasks.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/f2cc9c540b22fefd180e35a951fd52a552bec70d/scripts/generate_tasks.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/__init__.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/base.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/agents/installed/base.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/environments/base.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/job.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/trial/trial.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/verifier/verifier.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/tasks/client.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/dataset/client.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/job/config.py
- https://raw.githubusercontent.com/laude-institute/harbor/main/src/harbor/models/trial/config.py
- https://inspect.aisi.org.uk/solvers.html
