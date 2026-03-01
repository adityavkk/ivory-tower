# Building a General-Purpose Eval Runner with Harbor, Inspect AI, and inspect-harbor

**Research Report -- March 2026**

---

## 1. Executive Summary

Building a general-purpose eval runner that can mix-and-match different agent solvers against different benchmarks (Spider2, LongMemEval, and others) is achievable using the Harbor Framework and Inspect AI ecosystem, though the critical prerequisite is understanding that two entirely separate projects share the "Harbor" name. The **Harbor Framework** (`laude-institute/harbor`, harborframework.com) is a Python-based evaluation framework for containerized agent tasks -- providing task formats, dataset registries, Docker/cloud sandbox orchestration, trial/job lifecycle management, and verification systems. The separate project **Harbor** (`av/harbor`) is a Bash/Docker Compose CLI for orchestrating local LLM stacks (Ollama, vLLM, llama.cpp, etc.). The `inspect-harbor` package (v0.4.5, Feb 2026) bridges the Harbor Framework -- not av/harbor -- to Inspect AI's Task/Solver/Scorer/Dataset abstractions.

The recommended architecture uses three layers: the **Harbor Framework** as the task/environment/verification substrate (its registry currently hosts 47+ datasets with 60,000+ tasks including spider2-dbt@1.0); **Inspect AI** as the solver/eval control plane (providing the `@solver` abstraction, agent bridge system, and `--solver` runtime swapping); and **inspect-harbor** as the adapter between them. For custom benchmarks not yet in the Harbor registry (such as LongMemEval), the Harbor Framework provides a mature adapter workflow (`harbor adapters init`) with a nine-step process from initial development through oracle verification, parity experiments, and registry publication. Optionally, **av/harbor** can serve as the infrastructure layer for managing local LLM backends, connecting to Inspect AI through OpenAI-compatible API endpoints.

The most important practical insight is that inspect-harbor's generic `harbor()` entrypoint (accepting `dataset_name_version`, local paths, git task references, and custom registries) should be the primary integration point rather than the auto-generated per-dataset wrapper functions, which can lag behind the Harbor registry. For solvers, Inspect AI's pluggable `--solver` flag and `@solver` decorator provide the mix-and-match capability, while Harbor Framework's `BaseAgent`/`BaseInstalledAgent` interfaces and its pre-integrated agents (Terminus-2, Claude Code, Codex CLI, Gemini CLI, OpenHands) provide the agent-side flexibility.

---

## 2. Background & Context

### 2.1 The Two "Harbors" -- A Critical Distinction

The most important architectural clarification is the naming collision between two completely separate projects:

| Project | Repository | Purpose | License |
|---|---|---|---|
| **Harbor Framework** | `laude-institute/harbor` (harborframework.com) | Python framework for building, evaluating, and optimizing agents in containerized environments | -- |
| **Harbor (LLM stack)** | `av/harbor` (github.com/av/harbor) | Bash/Docker Compose CLI for orchestrating local LLM services | Apache-2.0 |

The `inspect-harbor` package (maintained by jjallaire / Meridian Labs) depends on `harbor>=0.1.44` -- the Harbor Framework Python package -- not av/harbor. This is explicitly confirmed in inspect-harbor's `pyproject.toml`, its import statements (`from harbor.dataset.client import DatasetClient`, `from harbor.models.job.config import ...`), and the PyPI package metadata.

**Source**: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor _task.py source](https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_task.py), [laude-institute/harbor](https://github.com/laude-institute/harbor), [av/harbor](https://github.com/av/harbor)

### 2.2 Harbor Framework (laude-institute/harbor)

The Harbor Framework defines six core runtime concepts:

- **Task**: A single instruction + container environment + test script, implemented as a directory of files (`instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/test.sh`, optional `solution/solve.sh`)
- **Dataset**: A collection of tasks, typically corresponding to a benchmark (e.g., Terminal-Bench, SWE-Bench Verified). Datasets can be local directories or registry entries pointing to versioned git repos
- **Agent**: A program that completes tasks, implementing either `BaseAgent` (external, interfacing via `exec`) or `BaseInstalledAgent` (installed directly into the container, headless)
- **Container Environment**: Docker containers (or cloud sandboxes via Daytona, Modal, E2B) defined by Dockerfiles or docker-compose.yaml files
- **Trial**: A single agent attempt at a task -- essentially a rollout producing a reward
- **Job**: A collection of trials across datasets, agents, tasks, and models, run concurrently

Jobs are configured via YAML/JSON config files or CLI flags (`harbor run -d "dataset@version" -a "agent" -m "model"`) and expand into `TrialConfig` objects run in parallel. Harbor's local orchestrator manages the trial lifecycle: environment startup, agent setup/run, verifier execution (copying `tests/` to `/tests/` in the container, running `test.sh`, reading reward from `/logs/verifier/reward.txt` or `reward.json`), artifact capture, and cleanup.

The Harbor Framework comes with pre-integrated agents including **Terminus-2** (Harbor's reference agent using a mono-tool tmux-based design with intelligent context summarization, RL rollout collection, and ATIF trajectory output), **Claude Code**, **Codex CLI**, **Gemini CLI**, **OpenHands**, and **Mini-SWE-Agent**.

**Source**: [Harbor Core Concepts](https://harborframework.com/docs/core-concepts), [Harbor Tasks](https://harborframework.com/docs/tasks), [Harbor Agents](https://harborframework.com/docs/agents), [Harbor Evals](https://harborframework.com/docs/run-jobs/run-evals), [Terminus-2](https://harborframework.com/docs/agents/terminus-2)

### 2.3 Harbor (av/harbor) -- The LLM Stack Tool

av/harbor (Apache-2.0, 2.5k stars, v0.4.1) is a CLI and companion desktop app for orchestrating a local LLM stack via Docker Compose. It manages 50+ services across backends (Ollama, vLLM, llama.cpp, TabbyAPI, Aphrodite, SGLang, KTransformers, mistral.rs), frontends (Open WebUI, ComfyUI, LibreChat), and satellites (SearXNG, Dify, LiteLLM, LangFuse, OpenHands, Aider, AutoGPT, etc.).

Its core is a Bash script (`harbor.sh`) that resolves Docker Compose files, detects hardware (NVIDIA/AMD GPUs), manages configurations via `HARBOR_*` environment variables, and wires services together through "cross-compose" files. All backends expose OpenAI-compatible APIs on a shared Docker network.

av/harbor includes three eval-related services:
- **Harbor Bench**: Deno-based LLM-as-judge benchmarking with YAML tasks and variant permutations
- **Promptfoo**: Prompt testing and red-teaming integration
- **lm-evaluation-harness**: EleutherAI's standard NLP benchmarks against OpenAI-compatible APIs

None of these support agentic evaluation (tool use, sandboxed environments, multi-step agent loops).

**Source**: [av/harbor GitHub](https://github.com/av/harbor), [Harbor Wiki](https://github.com/av/harbor/wiki)

### 2.4 Inspect AI

Inspect AI (MIT, UK AI Safety Institute) provides a structured Python framework for LLM evaluation with four core abstractions: **Task** (bundles Dataset + Solver + Scorer), **Dataset** (collection of `Sample` objects), **Solver** (async function transforming `TaskState`), and **Scorer** (evaluates output against target). It supports Docker/Kubernetes sandboxes, an agent bridge for wrapping third-party agents, MCP tool integration, 100+ pre-built benchmarks via `inspect_evals`, and runtime solver swapping via `--solver`.

**Source**: [Inspect AI Documentation](https://inspect.aisi.org.uk/), [Inspect AI Solvers](https://inspect.aisi.org.uk/solvers.html)

### 2.5 Target Benchmarks

**Spider 2.0** (arXiv:2411.07763, ICLR 2025 Oral) evaluates LLMs on real-world enterprise text-to-SQL workflows. It has 547 tasks across Snowflake/BigQuery/SQLite settings and a 68-task DBT variant using local DuckDB. GPT-4o achieves ~10-13% accuracy.

**LongMemEval** (arXiv:2410.10813, ICLR 2025) benchmarks long-term memory capabilities of chat assistants across 500 questions spanning five abilities. It uses an LLM-as-judge scoring approach. The oracle variant fits in 128K context; the M variant requires ~1.5M tokens.

**Source**: [Spider2 GitHub](https://github.com/xlang-ai/Spider2), [LongMemEval GitHub](https://github.com/xiaowu0162/LongMemEval)

---

## 3. Key Findings

### 3.1 Harbor Framework's Orchestration Architecture

Harbor Framework's execution pipeline operates as follows:

1. **Job creation**: `harbor run -d "dataset@version" -a "agent" -m "model"` creates a `JobConfig`
2. **Trial expansion**: The job config expands into multiple `TrialConfig` objects (crossing datasets x tasks x agents x models)
3. **Concurrent execution**: The local orchestrator runs trials in parallel
4. **Per-trial lifecycle**:
   - Environment startup (Docker container or cloud sandbox via Daytona/Modal/E2B)
   - Agent setup and execution (passing `instruction.md` content to the agent)
   - Verifier execution: copies `tests/` directory to `/tests/` in the container, runs `test.sh`, reads reward from `/logs/verifier/reward.txt` (float) or `/logs/verifier/reward.json` (multi-metric dict)
   - Artifact collection from `/logs/` directory
   - Result serialization (trial `result.json` with rewards, agent trajectories, durations)
   - Cleanup

Results are stored in a structured directory (`jobs/job-name/trial-name/{config.json, result.json, agent/, verifier/}`). Harbor includes a web-based viewer (`harbor view jobs`) for browsing jobs, inspecting trials, viewing agent trajectories, comparing performance across agent/model combinations, and analyzing artifacts.

For horizontal scaling, Harbor supports cloud sandbox providers. Daytona is recommended for its flexibility (including multi-container support via docker-compose.yaml). Up to 100 parallel trials are possible on a MacBook Pro with 14 cores using cloud sandboxes.

**Source**: [Harbor Evals](https://harborframework.com/docs/run-jobs/run-evals), [Harbor Cloud Deployments](https://harborframework.com/docs/run-jobs/cloud-sandboxes), [Harbor Artifact Collection](https://harborframework.com/docs/run-jobs/results-and-artifacts)

### 3.2 inspect-harbor: The Bridge Layer

inspect-harbor provides the critical adapter between Harbor Framework tasks and Inspect AI evaluations. Its architecture is clean and readable:

**Core bridge function** (`_task.py`): The `harbor()` function (decorated with `@task`) accepts multiple loading patterns:
- **Registry dataset**: `dataset_name_version="spider2-dbt@1.0"` (with optional custom `registry_url` or `registry_path`)
- **Git task**: `path` + `task_git_url` + optional `task_git_commit_id`
- **Local path**: `path="/path/to/task_or_dataset"`
- **Local dataset**: `path` to a directory of tasks

It loads Harbor `Task` objects via `load_harbor_tasks()`, converts each to an Inspect `Sample` via `harbor_task_to_sample()`, and returns an Inspect `Task` with a default ReAct solver and harbor scorer.

**Converter** (`_converters.py`): `harbor_task_to_sample()` maps:
- `harbor_task.instruction` → `Sample.input`
- Harbor environment (Dockerfile or docker-compose.yaml) → `SandboxEnvironmentSpec` via `ComposeConfig` with resource limits (CPUs, memory with 6GB minimum enforcement, GPUs)
- Task metadata (tests_dir, test_path, verifier config, solution config) → `Sample.metadata`

**Scorer** (`_scorer.py`): `harbor_scorer()` copies test files to `/tests/` in the sandbox at scoring time, runs `test.sh`, reads the reward file (`reward.txt` or `reward.json`), and returns an Inspect `Score`. It handles cleanup of scoring files between epochs.

**Default solver**: ReAct agent with `bash(timeout=300)`, `python(timeout=300)`, `update_plan()`, and `CompactionEdit()` for context window management.

**Source**: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [inspect_harbor _task.py](https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_task.py), [inspect_harbor _converters.py](https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_converters.py), [inspect_harbor _scorer.py](https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_scorer.py)

### 3.3 Defining and Registering New Agent Solvers

There are two parallel paths for integrating custom agents, depending on which layer you target:

#### Via Harbor Framework (for use with `harbor run`)

Implement either:

1. **External Agent** (`BaseAgent`): Interfaces with the environment through `BaseEnvironment.exec()`. Requires implementing `name()`, `version()`, `setup()`, and `run()` methods. Run with `--agent-import-path path.to.agent:MyAgent`.

2. **Installed Agent** (`BaseInstalledAgent`): Installed directly into the container, executing in headless mode. Brings custom tools. Requires implementing `_install_agent_template_path`, `create_run_agent_commands()`, and `populate_context_post_run()`.

#### Via Inspect AI (for use with `inspect eval`)

1. **Native Inspect Solver**: `@solver`-decorated function implementing `async def solve(state: TaskState, generate: Generate) -> TaskState`. Compose with `chain()`, equip with tools (`bash()`, `python()`, `text_editor()`, MCP tools, custom `@tool` functions).

2. **Agent Bridge** (Python agents): `agent_bridge(agent_fn, model="inspect")` routes API calls through Inspect's model provider.

3. **Sandbox Agent Bridge** (CLI agents): `sandbox_agent_bridge(command="my-agent --api-url http://localhost:13131")` wraps container-based CLI agents via a proxy server.

Registration is via setuptools entry points:
```toml
[project.entry-points.inspect_ai]
my_solvers = "my_package._registry"
```

Runtime swapping: `inspect eval --solver path/to/agent.py@custom_agent` or `inspect eval --solver inspect_swe/claude_code`.

The key architectural insight for a "mix-and-match" runner is that **solver choice is an Inspect AI concern** -- you pass different solvers to the same task via `--solver` without needing to modify the Harbor registry or task definitions.

**Source**: [Harbor Agents](https://harborframework.com/docs/agents), [Inspect AI Solvers](https://inspect.aisi.org.uk/solvers.html), [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/)

### 3.4 Defining and Registering New Benchmarks/Datasets

Harbor Framework provides a mature, nine-step adapter workflow for onboarding new benchmarks:

1. **Understand the original benchmark**: Identify task instructions, environments, tests, solutions
2. **Fork Harbor and develop adapter code**: Create `adapters/{adapter-name}/` with `adapter.py`, `run_adapter.py`, templates, and metadata. The adapter generates Harbor task directories (`instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh`)
3. **Verify oracle solutions**: Run `harbor run -p datasets/<adapter-name>` and confirm 100% oracle pass rate
4. **Discuss parity plans**: Coordinate with the Harbor team on agent/model choices for parity experiments
5. **Run parity experiments**: Compare adapter results against original benchmark baselines
6. **Record parity results**: Formal `parity_experiment.json` with metrics, trial scores, and statistical comparisons
7. **Upload to HuggingFace**: Store parity data in the Harbor Parity Experiments dataset
8. **Register the dataset**: Add entries to `registry.json` in the Harbor repository (task-level entries with git URLs and commit IDs for pinning)
9. **Document and submit**: Comprehensive README following the Harbor adapter template

For quick bootstrapping: `harbor adapters init my-adapter --name "My Benchmark"` creates starter code and template files.

The adapter workflow ensures **parity** between the original benchmark and the Harbor adaptation, which is critical for credibility. The team provides API cost support for parity experiments.

**Source**: [Harbor Adapters](https://harborframework.com/docs/datasets/adapters), [Harbor Registering Datasets](https://harborframework.com/docs/datasets/registering-datasets)

### 3.5 Current Registry Coverage and Benchmark Status

The Harbor Framework registry (as of March 2026) hosts **47+ datasets** totaling **60,000+ tasks**. Key entries include:

| Dataset | Version | Tasks | Notes |
|---|---|---|---|
| terminal-bench | 2.0 | 89 | Terminal agent evaluation |
| swebench-verified | 1.0 | 500 | Human-validated SWE-bench subset |
| swebenchpro | 1.0 | 731 | Multi-language (Python/JS/TS/Go) |
| spider2-dbt | 1.0 | 64 | Local DuckDB, no cloud credentials |
| code-contests | 1.0 | 44,220 | DeepMind competitive programming |
| swe-lancer-diamond | all | 463 | OpenAI's SWE-Lancer |
| terminal-bench-pro | 1.0 | 200 | Extended terminal benchmark |
| algotune | 1.0 | 154 | Algorithm optimization |
| arc_agi_2 | 1.0 | 167 | Abstract reasoning |
| dabstep | 1.0 | 450 | Data agent benchmark |

**Spider2-DBT is in the registry** (`spider2-dbt@1.0`, 64 tasks). Note: the registry shows 64 tasks, not 68 as sometimes reported.

**LongMemEval is NOT in the registry**. There is no `longmemeval` entry in the Harbor registry or in inspect-harbor's generated task functions. Integrating LongMemEval would require creating a Harbor adapter or wrapping it directly as an Inspect AI task.

**Source**: [Harbor Registry](https://harborframework.com/registry), [inspect-harbor REGISTRY.md](https://github.com/meridianlabs-ai/inspect_harbor/blob/main/REGISTRY.md)

### 3.6 The Eval Execution Pipeline

#### Path A: Harbor Framework Native Pipeline

```
harbor run -d "spider2-dbt@1.0" -a terminus-2 -m "openai/gpt-5"
```

1. Registry resolution → download and cache tasks from git
2. Job creation → trial config expansion
3. Parallel trial execution → Docker/cloud sandbox lifecycle
4. Verifier → read reward.txt/reward.json
5. Results → `jobs/` directory with viewer support

#### Path B: Inspect AI via inspect-harbor

```
inspect eval inspect_harbor/spider2_dbt --model openai/gpt-5 --solver path/to/agent.py@my_solver
```

1. `harbor()` task function loads Harbor tasks from registry
2. Convert each to `Sample` with `SandboxEnvironmentSpec`
3. Inspect AI creates Docker sandboxes per sample
4. Solver chain executes (calling `generate()` to hit LLM API, processing tool calls)
5. `harbor_scorer()` copies tests into sandbox, runs `test.sh`, reads reward
6. Results → Inspect AI `EvalLog` (JSON with `EvalSpec`, `EvalPlan`, `EvalSample`, `EvalResults`)
7. Sandbox cleanup

#### Path C: Hybrid (av/harbor + Inspect AI)

```bash
# Start LLM backends via av/harbor
harbor up vllm litellm
# Run eval via Inspect AI, pointing at Harbor-managed endpoints
inspect eval inspect_harbor/spider2_dbt \
  --model openai/meta-llama/Meta-Llama-3-8B-Instruct \
  -M base_url=$(harbor url litellm)/v1
```

This uses av/harbor purely as infrastructure (model serving, API routing via LiteLLM) and Inspect AI + inspect-harbor for the eval execution.

### 3.7 Existing Examples and Patterns

**Pattern 1: inspect-harbor quick start**
```bash
pip install inspect-harbor
inspect eval inspect_harbor/terminal_bench_sample --model openai/gpt-5-mini
```
Downloads from Harbor registry, runs default ReAct agent, Docker sandboxes, results in `./logs`.

**Pattern 2: Custom solver with inspect-harbor**
```bash
inspect eval inspect_harbor/terminal_bench --solver inspect_swe/claude_code --model anthropic/claude-sonnet-4-5
```
Swaps the default ReAct agent for Claude Code solver.

**Pattern 3: Harbor Framework native run**
```bash
harbor run -d terminal-bench@2.0 --agent terminus-2 --model openai/gpt-5 -e daytona -n 50
```
Runs Terminus-2 agent on Terminal-Bench with 50 parallel trials via Daytona cloud sandboxes.

**Pattern 4: Generic harbor() with custom registry**
```bash
inspect eval inspect_harbor/harbor \
  -T dataset_name_version="my-benchmark@1.0" \
  -T registry_url="https://github.com/myorg/registry.json" \
  --model openai/gpt-5
```
Uses the generic entrypoint for datasets not yet wrapped as static functions.

**Pattern 5: Local task development**
```bash
inspect eval inspect_harbor/harbor \
  -T path="/path/to/local_dataset" \
  --model openai/gpt-5
```

**Source**: [inspect-harbor PyPI](https://pypi.org/project/inspect-harbor/), [Harbor Evals](https://harborframework.com/docs/run-jobs/run-evals)

---

## 4. Analysis

### 4.1 Recommended Architecture for a General-Purpose Eval Runner

The optimal architecture has four planes:

```
┌──────────────────────────────────────────────────────────────────┐
│                   Eval Runner CLI / Config                        │
│  Declarative: benchmark_id + solver_id + model + provider +      │
│  resource_overrides + seed/attempts                              │
├──────────────────────────────────────────────────────────────────┤
│               Benchmark / Task Plane                              │
│  Harbor Framework datasets (registry or local)                   │
│  Custom adapters for benchmarks not in registry                  │
│  Loaded via inspect-harbor's generic harbor() entrypoint         │
├──────────────────────────────────────────────────────────────────┤
│                  Solver / Agent Plane                              │
│  Inspect AI solvers: ReAct, CoT, custom @solver, agent_bridge   │
│  Runtime-swappable via --solver flag                             │
│  Harbor agents: Terminus-2, Claude Code, OpenHands               │
├──────────────────────────────────────────────────────────────────┤
│                Execution / Sandbox Plane                           │
│  Docker (local) | Daytona | Modal | E2B                          │
│  Concurrency: --max-samples (Inspect) or -n (Harbor)            │
├──────────────────────────────────────────────────────────────────┤
│               Infrastructure Plane (Optional)                     │
│  av/harbor: Ollama, vLLM, LiteLLM (API routing), LangFuse       │
│  Cloud APIs: OpenAI, Anthropic, Google                           │
├──────────────────────────────────────────────────────────────────┤
│                  Results / Analysis Plane                          │
│  Inspect AI logs (JSON) | Harbor jobs/ (JSON + viewer)           │
│  Normalized summary tables | Artifact collection                 │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Two Execution Paths: Harbor Native vs. Inspect AI

A key design decision is whether to use Harbor Framework's native `harbor run` pipeline or Inspect AI via inspect-harbor:

| Dimension | Harbor Native (`harbor run`) | Inspect AI (`inspect eval`) |
|---|---|---|
| **Solver ecosystem** | Harbor agents (Terminus-2, Claude Code, etc.) | Inspect solvers + agent bridge + any Python agent |
| **Solver swapping** | `--agent` flag, `--agent-import-path` | `--solver` flag, entry points |
| **Sandbox providers** | Docker, Daytona, Modal, E2B | Docker, Kubernetes |
| **Horizontal scaling** | `-n` parallel trials, cloud sandboxes | `--max-samples`, `--max-tasks` |
| **Results format** | jobs/ directory with web viewer | EvalLog JSON with Inspect viewer |
| **RL/Training support** | Terminus-2 rollout collection, ATIF trajectories | Not native |
| **Registry integration** | Direct (`-d dataset@version`) | Via inspect-harbor |

For a **general-purpose eval runner focused on benchmarking**, the Inspect AI path offers broader solver flexibility (wrapping arbitrary Python agents, runtime swapping, chain composition). For **RL training data generation and trajectory collection**, the Harbor Framework native path with Terminus-2 is superior.

The pragmatic recommendation is to **build around Inspect AI + inspect-harbor as the primary path**, using the generic `harbor()` entrypoint as the single integration point for all Harbor-registered benchmarks. This avoids coupling to specific wrapper functions and works for both registry and custom/local datasets.

### 4.3 Integrating Spider2

**Spider2-DBT** (`spider2-dbt@1.0`): Already in the Harbor registry with 64 tasks. Immediately runnable:
```bash
inspect eval inspect_harbor/spider2_dbt --model openai/gpt-5 --solver my_sql_agent
```
No cloud credentials needed -- uses local DuckDB.

**Spider2-Snow/Lite** (547 tasks): NOT in the Harbor registry. Integration options:
1. **Harbor adapter path**: Create a Harbor adapter following the nine-step workflow, submit to the registry
2. **Direct Inspect AI task**: Load from `spider2-snow.jsonl`, create an agentic solver with database execution tools, build a CSV comparison scorer porting Spider2's `compare_pandas_table`
3. **Credential management**: Snowflake/BigQuery credentials need secure injection into Docker sandboxes via environment variables in `task.toml` or Inspect's sandbox configuration

### 4.4 Integrating LongMemEval

LongMemEval is **not in the Harbor registry** and has no existing adapter. Two integration approaches:

**Option A: Harbor adapter** -- Create task directories with `instruction.md` containing the chat history + question, `environment/Dockerfile` with a minimal Python container, `tests/test.sh` running an LLM-as-judge scorer, `solution/solve.sh` providing the ground truth. Register in the Harbor registry. This enables use via both `harbor run` and `inspect eval`.

**Option B: Direct Inspect AI task** -- Load from `longmemeval_oracle.json` on HuggingFace, map to `Sample` objects, implement a custom scorer replicating LongMemEval's per-type-specific LLM-as-judge prompts (off-by-one tolerance for temporal, latest-answer for knowledge-update, abstention detection).

The oracle variant (~128K tokens per instance) is the practical starting point. The M variant (~1.5M tokens) exceeds most model context windows, requiring RAG-based solvers.

### 4.5 Key Tradeoffs

**Velocity vs. Reproducibility**: Using "latest" dataset aliases and unversioned wrappers (e.g., `terminal_bench()`) is fast but can drift. Using pinned versions (`terminal_bench_2_0()`, `dataset_name_version="terminal-bench@2.0"`) and explicit git commit IDs is slower but reproducible. For a benchmarking runner, **reproducibility should always win** -- pin `@version` and `git_commit_id`.

**Registry/catalog drift**: The Harbor Framework registry and inspect-harbor's auto-generated wrapper functions can diverge by release timing. The generate script (`scripts/generate_tasks.py`) produces static task functions from registry snapshots, so newly added datasets may not have wrappers yet. The generic `harbor()` entrypoint with `dataset_name_version` is the resilient fallback.

**Harbor Native vs. Inspect AI**: Harbor's native pipeline excels at RL data collection (Terminus-2's rollout details, ATIF trajectories) and has broader cloud sandbox support (Daytona with multi-container, Modal, E2B). Inspect AI excels at solver flexibility, the agent bridge system, and integration with 100+ existing eval benchmarks.

### 4.6 Recommendations

1. **Start with spider2-dbt@1.0 via inspect-harbor** as a proof-of-concept -- 64 tasks, zero credential setup, immediate solver experimentation with `--solver`
2. **Use the generic `harbor()` entrypoint** as your primary integration point, not the per-dataset wrapper functions
3. **Build a LongMemEval adapter** using Harbor's `harbor adapters init` workflow for long-term community value, or wrap directly as an Inspect AI task for faster iteration
4. **For solver development**, write Inspect AI `@solver` functions with appropriate tool sets (bash/python for terminal tasks, SQL execution tools for Spider2, RAG pipeline for LongMemEval-M)
5. **For infrastructure**, use av/harbor + LiteLLM as the model serving layer, connecting to Inspect AI via `--model openai/model-name -M base_url=$(harbor url litellm)/v1`
6. **Pin all benchmark versions** (`@version` + git commit IDs) and preserve run manifests for reproducibility
7. **Invest in a thin orchestration wrapper** that coordinates av/harbor backend startup, Inspect AI eval execution, and results normalization into a single declarative config

---

## 5. Open Questions & Gaps

### 5.1 No Native av/harbor + Inspect AI Integration

There is no bridge between av/harbor (the LLM stack tool) and Inspect AI. While Inspect AI can point at any OpenAI-compatible endpoint, there is no automated discovery of Harbor's running services, no lifecycle coordination (ensuring backends are running before eval starts), and no shared configuration. A custom Inspect AI `ModelAPI` provider that queries Harbor's service registry could address this but would need to be built.

### 5.2 Docker Networking Between av/harbor and Inspect AI Sandboxes

av/harbor manages its own Docker network (`harbor-network`). Inspect AI's Docker sandboxes create separate containers per evaluation sample. Whether an Inspect AI sandbox container can reach Harbor's inference backends on `harbor-network` depends on Docker network configuration that would need custom engineering (attaching Inspect sandbox containers to Harbor's network or using host networking).

### 5.3 LongMemEval Registry Absence

LongMemEval is not in the Harbor Framework registry and has no existing adapter. Building one is feasible but requires non-trivial work on the LLM-as-judge scorer (five different evaluation patterns for five memory abilities) and the Oracle solution (which may not exist in a form easily converted to `solve.sh`). The Harbor team's Discord `#adapters-announcements` channel and their [Adapter List spreadsheet](https://docs.google.com/spreadsheets/d/1mJbiASPm32DDNzEnV6eDGwpEf3FlMUe5dhkZmFjjSoo/) should be checked for whether LongMemEval is planned.

### 5.4 Spider2-Snow/Lite Credential Management

Spider2's Snowflake and BigQuery settings require cloud credentials. How to securely inject these into evaluation sandboxes (via `task.toml` environment variables, Inspect's sandbox env, or Docker secrets) while maintaining reproducibility across different environments is unresolved.

### 5.5 Results Normalization Across Execution Paths

If you use Harbor Framework's native pipeline for some benchmarks and Inspect AI for others, results end up in two different formats (Harbor's `jobs/` directory with `result.json` vs. Inspect AI's `EvalLog` JSON). A unified results format or dashboard would need custom engineering. Harbor's web viewer and Inspect's log viewer serve different needs.

### 5.6 Cost Tracking

Neither Harbor Framework nor Inspect AI provides built-in cost tracking across a full eval suite, though Terminus-2 supports `model_info` with input/output cost per token for LiteLLM cost tracking. Budget management, cost-per-benchmark estimation, and automatic stopping when budgets are exceeded would need to be built.

### 5.7 Training Workflow Integration

Harbor Framework supports RL training workflows (Terminus-2's `collect_rollout_details` for token IDs and logprobs, ATIF trajectory format for SFT data) that Inspect AI does not natively provide. If the eval runner needs to double as a training data pipeline, the Harbor native path may be preferable for those benchmarks, creating a split architecture.

---

## 6. Sources

### Primary Repositories
1. **Harbor Framework**: https://github.com/laude-institute/harbor -- Containerized agent evaluation framework
2. **av/harbor**: https://github.com/av/harbor -- LLM stack orchestration tool (Apache-2.0, v0.4.1)
3. **inspect-harbor**: https://github.com/meridianlabs-ai/inspect_harbor -- Inspect AI bridge to Harbor Framework (MIT, v0.4.5, Feb 2026)
4. **Inspect AI**: https://github.com/UKGovernmentBEIS/inspect_ai -- Eval framework by UK AISI (MIT)
5. **Spider2**: https://github.com/xlang-ai/Spider2 -- Enterprise text-to-SQL benchmark (MIT)
6. **LongMemEval**: https://github.com/xiaowu0162/LongMemEval -- Long-term memory benchmark (MIT)

### Documentation
7. **Harbor Framework Docs**: https://harborframework.com/docs/core-concepts
8. **Harbor Framework Registry**: https://harborframework.com/registry
9. **Harbor Framework Tasks**: https://harborframework.com/docs/tasks
10. **Harbor Framework Agents**: https://harborframework.com/docs/agents
11. **Harbor Framework Terminus-2**: https://harborframework.com/docs/agents/terminus-2
12. **Harbor Framework Evals**: https://harborframework.com/docs/run-jobs/run-evals
13. **Harbor Framework Adapters**: https://harborframework.com/docs/datasets/adapters
14. **Harbor Framework Cloud Deployments**: https://harborframework.com/docs/run-jobs/cloud-sandboxes
15. **Harbor Framework Artifact Collection**: https://harborframework.com/docs/run-jobs/results-and-artifacts
16. **Harbor Framework Datasets**: https://harborframework.com/docs/datasets
17. **Harbor Framework Registering Datasets**: https://harborframework.com/docs/datasets/registering-datasets
18. **av/harbor Wiki**: https://github.com/av/harbor/wiki
19. **Inspect AI Documentation**: https://inspect.aisi.org.uk/
20. **Inspect AI Solvers**: https://inspect.aisi.org.uk/solvers.html
21. **inspect-harbor PyPI**: https://pypi.org/project/inspect-harbor/
22. **inspect-harbor Documentation**: https://meridianlabs-ai.github.io/inspect_harbor/

### Source Code (Verified)
23. **inspect_harbor _task.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_task.py
24. **inspect_harbor _converters.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_converters.py
25. **inspect_harbor _scorer.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_scorer.py
26. **inspect_harbor pyproject.toml**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/pyproject.toml

### Papers
27. **Spider 2.0**: arXiv:2411.07763 (ICLR 2025 Oral)
28. **LongMemEval**: arXiv:2410.10813 (ICLR 2025)

### Datasets
29. **LongMemEval Dataset**: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
30. **Spider2 Leaderboard**: https://spider2-sql.github.io/
31. **Harbor Parity Experiments**: https://huggingface.co/datasets/harborframework/parity-experiments
