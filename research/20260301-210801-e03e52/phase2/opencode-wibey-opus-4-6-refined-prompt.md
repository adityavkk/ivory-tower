# Cross-Pollination: Produce Your Definitive Report

You previously conducted deep research and produced a report on the topic below.
Other AI agents independently researched the SAME topic. You now have access to
your report and all peer reports.

## Your Task

Produce a **complete, standalone research report** -- your definitive version on this
topic. This is NOT a review or commentary. It is a full rewrite of your report that
incorporates the best of what you and the other agents found.

### Process

1. **Audit your own report** -- identify where you went deep, where you were shallow,
   and where you may have errors or unsupported claims
2. **Read all peer reports with healthy skepticism** -- look for:
   - Ideas, angles, and findings they covered that you missed entirely
   - Areas where they went deeper or found better sources than you
   - Claims that seem plausible but lack strong sourcing -- verify these independently
   - Contradictions between your report and theirs
   - Unique sources or evidence you didn't find
   - Reasoning or conclusions that don't follow from evidence
3. **Conduct NEW web research** to:
   - Verify peer claims before incorporating them -- do not accept anything at face value
   - Resolve contradictions between reports with additional evidence
   - Fill gaps that ALL reports share
   - Explore avenues inspired by peer reports that go beyond what anyone covered
4. **Write your complete, refined report** using the structure below

## Output Structure

Write your report with this structure:

1. **Executive Summary** -- the most important findings in 2-3 paragraphs
2. **Background & Context** -- what the reader needs to know to understand the topic
3. **Key Findings** -- organized by theme, with evidence and source citations for each claim
4. **Analysis** -- your interpretation of the findings: tradeoffs, implications, and
   recommendations where appropriate
5. **Open Questions & Gaps** -- what remains uncertain or under-explored
6. **Sources** -- comprehensive list of all URLs and references cited

## Critical Rules

- The output must be a **complete standalone report**, not a diff, review, or commentary
- Do NOT reference the other agents, the cross-pollination process, or "the peer report"
   in your output -- write as if this is your original work
- Do NOT simply copy content from peer reports -- verify claims independently and rewrite
   in your own analysis
- When peer reports contradict your findings, investigate further and present the
   evidence-backed conclusion (or both sides if genuinely unresolved)
- Incorporate the BEST insights from all sources but maintain your own analytical voice
- Your report should be substantially richer and more accurate than your original --
   if the peer reports didn't add anything, you aren't reading them critically enough

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Your Original Report
This is a deep research task about Harbor and inspect-harbor for building a general-purpose eval runner. Let me plan this out and then conduct thorough research.
Let me start by researching Harbor's GitHub repo, inspect-harbor, and related documentation in parallel.
Good, I have a good overview of Harbor. Now let me dig deeper into the eval-related components. Let me fetch more specific pages in parallel.
Now let me research Inspect AI and the concept of "inspect-harbor", plus the benchmarks Spider2 and LongMemEval.
I now have comprehensive research data from all sources. Let me update the todos and write the report.
Now let me determine the output path and write the comprehensive report.
The research report has been written to `/Users/auk000v/dev/tools/ivory-tower/research/20260301-210801-e03e52/phase1/20260301-210801-e03e52/report.md`.

Here's a summary of the key findings:

**Critical discovery**: The `inspect-harbor` package bridges Inspect AI with the **Harbor Framework** (harborframework.com) -- a completely separate project from `av/harbor` (the LLM stack tool). There is no existing integration between av/harbor and Inspect AI.

**Recommended architecture**: Use **Inspect AI** as the central eval orchestrator (Tasks/Solvers/Scorers/Datasets), **Harbor (av/harbor)** as the infrastructure layer for managing LLM backends, and custom engineering to bridge them. Key custom work needed:
1. An Inspect AI ModelAPI extension for auto-discovering Harbor backends
2. Agentic solvers with tool-use for benchmarks like Spider2
3. Benchmark-specific scorers (CSV matching for Spider2, LLM-as-judge for LongMemEval)
4. Docker network coordination between Harbor's compose stack and Inspect AI's sandboxes

**Easiest starting points**: Spider2-DBT (already in inspect-harbor, 68 local tasks) and LongMemEval-oracle (self-contained JSON, fits in 128K context).

The report covers all 8 requested topics across ~4,500 words with 17 cited sources.


## Peer Reports
### codex-5.3-xhigh

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
