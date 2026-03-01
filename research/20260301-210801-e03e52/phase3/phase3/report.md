# Building a General-Purpose Eval Runner with Harbor, Inspect AI, and inspect-harbor

**Final Synthesis Report -- March 1, 2026**

---

## 1. Executive Summary

This report synthesizes independent research by two AI agents into a definitive guide for building a general-purpose eval runner that can mix-and-match different agent solvers against different benchmarks (Spider2, LongMemEval, and others) using the Harbor and Inspect AI ecosystems.

**The single most important finding** is that there are two entirely separate projects named "Harbor," and confusing them derails the entire architecture:

- **Harbor Framework** (`laude-institute/harbor`, harborframework.com) -- A Python evaluation framework for containerized agent tasks, providing task formats, dataset registries, Docker/cloud sandbox orchestration, trial/job lifecycle management, and verification systems.
- **Harbor (LLM stack)** (`av/harbor`, github.com/av/harbor) -- A Bash/Docker Compose CLI for orchestrating local LLM services (Ollama, vLLM, llama.cpp, LiteLLM, etc.).

The `inspect-harbor` package (v0.4.5, Feb 2026, maintained by jjallaire / Meridian Labs) bridges the **Harbor Framework** -- not av/harbor -- to Inspect AI's Task/Solver/Scorer/Dataset abstractions. This is confirmed by its Python dependency (`harbor>=0.1.44`), its import statements (`from harbor.dataset.client import DatasetClient`), and the PyPI package metadata.

**The recommended architecture** uses three layers:

1. **Harbor Framework** as the task/environment/verification substrate -- its registry hosts 47+ datasets with 60,000+ tasks, including `spider2-dbt@1.0` (64 tasks, immediately runnable).
2. **Inspect AI** as the solver/eval control plane -- providing the `@solver` abstraction, agent bridge system, runtime solver swapping via `--solver`, and 100+ existing benchmarks.
3. **inspect-harbor** as the adapter between them, with the generic `harbor()` entrypoint as the primary integration point.
4. **Optionally, av/harbor** as infrastructure for managing local LLM backends, connecting via OpenAI-compatible endpoints.

**Spider2-DBT** is immediately available through the Harbor registry and inspect-harbor wrappers. **LongMemEval is absent** from the Harbor registry and requires custom adapter work or direct Inspect AI task creation. Both agents independently verified this status.

The most practical starting point is running `spider2-dbt@1.0` through inspect-harbor, then building a solver plug-in registry in Inspect AI for matrix sweeps over solver x model combinations, then integrating additional benchmarks like LongMemEval via Harbor's adapter workflow.

---

## 2. Background & Context

### 2.1 The Two "Harbors" -- A Critical Distinction

| Attribute | Harbor Framework | Harbor (LLM Stack) |
|---|---|---|
| **Repository** | `laude-institute/harbor` | `av/harbor` |
| **Website** | harborframework.com | github.com/av/harbor |
| **License** | -- | Apache-2.0 |
| **Language** | Python | Bash |
| **Stars** | -- | ~2,500 |
| **Purpose** | Agent evaluation framework with containerized environments, dataset registry, trial lifecycle | LLM service orchestration (50+ services), Docker Compose management |
| **Core abstraction** | Task, Dataset, Agent, Trial, Job | Service, Backend, Satellite, Frontend |
| **Eval capabilities** | Full: task format, adapters, registry, parallel trials, verifier, artifact collection, RL training | Limited: Harbor Bench (LLM-as-judge), Promptfoo, lm-eval-harness (none support agentic evaluation) |

Both agents independently confirmed this distinction through primary source verification. The `inspect-harbor` package depends exclusively on the Harbor Framework Python package.

### 2.2 Harbor Framework Architecture

The Harbor Framework defines six core runtime concepts:

- **Task**: A directory containing `instruction.md` (what the agent must do), `task.toml` (metadata and resource requirements), `environment/` (Dockerfile or docker-compose.yaml), `tests/` (test.sh verification script), and optionally `solution/` (oracle solve.sh).
- **Dataset**: A collection of tasks corresponding to a benchmark (e.g., SWE-Bench Verified, Terminal-Bench). Datasets can be local directories or registry entries backed by versioned git repos with commit pinning (`dataset@version`).
- **Agent**: A program that completes tasks. Two interfaces: `BaseAgent` (external, interfacing via `exec`) and `BaseInstalledAgent` (installed directly into the container, headless execution). Pre-integrated agents include Terminus-2, Claude Code, Codex CLI, Gemini CLI, OpenHands, and Mini-SWE-Agent.
- **Container Environment**: Docker containers or cloud sandboxes (Daytona, Modal, E2B). Daytona supports multi-container environments via docker-compose.yaml. Up to 100 parallel trials on a single MacBook Pro using cloud sandboxes.
- **Trial**: A single agent attempt at a single task -- one rollout producing a reward.
- **Job**: A collection of trials crossing datasets x tasks x agents x models, run concurrently via the local orchestrator.

Jobs are configured via YAML/JSON or CLI: `harbor run -d "dataset@version" -a "agent" -m "model"`. The orchestrator manages the full trial lifecycle: environment startup, agent setup/run, verifier execution (copies `tests/` to `/tests/` in the container, runs `test.sh`, reads reward from `/logs/verifier/reward.txt` or `reward.json`), artifact capture from `/logs/`, result serialization, and cleanup.

Results are stored in a structured directory (`jobs/job-name/trial-name/{config.json, result.json, agent/, verifier/}`). Harbor includes a web-based viewer (`harbor view jobs`) for browsing jobs, inspecting trials, comparing agent/model performance, and analyzing artifacts.

**Terminus-2**, Harbor's reference agent, uses a mono-tool tmux-based design with intelligent context summarization, RL rollout collection (token IDs and logprobs), and ATIF trajectory output for SFT data generation.

### 2.3 av/harbor (The LLM Stack Tool)

av/harbor (v0.4.1) manages 50+ services across backends (Ollama, vLLM, llama.cpp, TabbyAPI, Aphrodite, SGLang, KTransformers, mistral.rs), frontends (Open WebUI, ComfyUI, LibreChat), and satellites (SearXNG, Dify, LiteLLM, LangFuse, OpenHands, Aider, AutoGPT, etc.).

Its core is `harbor.sh` -- a Bash script that resolves Docker Compose files, detects hardware (NVIDIA/AMD GPUs), manages configurations via `HARBOR_*` environment variables, and wires services together through "cross-compose" files. All backends expose OpenAI-compatible APIs on a shared Docker network.

Its eval-related services (Harbor Bench, Promptfoo, lm-evaluation-harness) are oriented toward OpenAI-compatible API benchmarking, not agentic evaluation with tool use, sandboxed environments, or multi-step agent loops.

### 2.4 Inspect AI

Inspect AI (MIT, UK AI Safety Institute) provides a structured Python evaluation framework with four core abstractions:

- **Task**: Bundles Dataset + Solver + Scorer
- **Dataset**: Collection of `Sample` objects (input, target, metadata, sandbox config)
- **Solver**: Async function transforming `TaskState` -- composable via `chain()`, equipped with tools
- **Scorer**: Evaluates output against target

Key features: Docker/Kubernetes sandboxes, agent bridge for wrapping third-party agents, MCP tool integration, 100+ pre-built benchmarks via `inspect_evals`, runtime solver swapping via `--solver`, and structured `EvalLog` output.

### 2.5 Target Benchmarks

**Spider 2.0** (arXiv:2411.07763, ICLR 2025 Oral): Enterprise text-to-SQL benchmark with 547 tasks across Snowflake/BigQuery/SQLite. The **DBT variant** (68 tasks originally, 64 in Harbor registry -- see Section 5 for discussion) uses local DuckDB with no cloud credentials required. GPT-4o achieves ~10-13% accuracy.

**LongMemEval** (arXiv:2410.10813, ICLR 2025): Benchmarks long-term memory capabilities of chat assistants across 500 questions spanning five memory abilities. Uses LLM-as-judge scoring with per-type-specific evaluation prompts (off-by-one tolerance for temporal questions, latest-answer for knowledge-update, abstention detection). The oracle variant fits in 128K context; the M variant requires ~1.5M tokens.

---

## 3. Key Findings

### 3.1 inspect-harbor: The Critical Bridge Layer

inspect-harbor provides the adapter between Harbor Framework tasks and Inspect AI evaluations. Both agents analyzed its source code and converged on the same architecture:

**Core bridge function** (`_task.py`): The `harbor()` function (decorated with `@task`) accepts four loading patterns:

1. **Registry dataset**: `dataset_name_version="spider2-dbt@1.0"` (with optional custom `registry_url` or `registry_path`)
2. **Git task**: `path` + `task_git_url` + optional `task_git_commit_id` for commit pinning
3. **Local path**: `path="/path/to/task_or_dataset"` for development
4. **Custom registry**: `registry_url` or `registry_path` for private/organizational registries

The function loads Harbor `Task` objects via `load_harbor_tasks()`, converts each to an Inspect `Sample` via `harbor_task_to_sample()`, and returns an Inspect `Task` with a default ReAct solver and harbor scorer.

**Converter** (`_converters.py`): `harbor_task_to_sample()` maps:
- `harbor_task.instruction` → `Sample.input`
- Harbor environment (Dockerfile or docker-compose.yaml) → `SandboxEnvironmentSpec` via `ComposeConfig` with resource limits (CPUs, memory with **6GB minimum enforcement**, GPUs)
- Task metadata (tests_dir, test_path, verifier config, solution config) → `Sample.metadata`

**Scorer** (`_scorer.py`): `harbor_scorer()` copies test files to `/tests/` in the sandbox at scoring time, runs `test.sh`, reads the reward file (`reward.txt` for a float or `reward.json` for a multi-metric dict), and returns an Inspect `Score`. It handles cleanup of scoring files between epochs.

**Default solver**: ReAct agent with `bash(timeout=300)`, `python(timeout=300)`, `update_plan()`, and `CompactionEdit()` for context window management.

The critical practical recommendation -- independently made by both agents -- is to **use the generic `harbor()` entrypoint** with `dataset_name_version` rather than the auto-generated per-dataset wrapper functions (e.g., `spider2_dbt_1_0()`). The wrappers are generated snapshots from `scripts/generate_tasks.py` and can lag behind the Harbor registry. The generic entrypoint always resolves against the live registry.

### 3.2 Defining and Registering New Agent Solvers

There are two parallel paths for integrating custom agents, depending on which execution layer is targeted:

#### Via Inspect AI (recommended for mix-and-match benchmarking)

1. **Native Inspect Solver**: `@solver`-decorated function implementing `async def solve(state: TaskState, generate: Generate) -> TaskState`. Compose with `chain()`, equip with tools (`bash()`, `python()`, `text_editor()`, MCP tools, custom `@tool` functions).

2. **Agent Bridge** (for existing Python agents): `agent_bridge(agent_fn, model="inspect")` routes API calls through Inspect's model provider, allowing existing Python agent codebases to be used as Inspect solvers without major refactoring.

3. **Sandbox Agent Bridge** (for CLI-based agents): `sandbox_agent_bridge(command="my-agent --api-url http://localhost:13131")` wraps container-based CLI agents via a proxy server.

4. **Registration**: Via setuptools entry points in `pyproject.toml`:
   ```toml
   [project.entry-points.inspect_ai]
   my_solvers = "my_package._registry"
   ```

5. **Runtime swapping**: `inspect eval --solver path/to/agent.py@custom_agent` or `inspect eval --solver inspect_swe/claude_code` -- the key enabler for mix-and-match evaluation without modifying task definitions.

#### Via Harbor Framework (for RL training data or native Harbor runs)

1. **External Agent** (`BaseAgent`): Interfaces with the environment through `BaseEnvironment.exec()`. Requires implementing `name()`, `version()`, `setup()`, and `run()` methods. Run with `--agent-import-path path.to.agent:MyAgent`.

2. **Installed Agent** (`BaseInstalledAgent`): Installed directly into the container, executing in headless mode. Requires implementing `_install_agent_template_path`, `create_run_agent_commands()`, and `populate_context_post_run()`.

The key architectural insight is that **solver choice is an Inspect AI concern** -- you pass different solvers to the same task via `--solver` without needing to modify the Harbor registry, task definitions, or adapt. For RL training data collection, Harbor Framework agents (especially Terminus-2) have native support that Inspect AI lacks.

### 3.3 Defining and Registering New Benchmarks/Datasets

Harbor Framework provides a mature nine-step adapter workflow for onboarding new benchmarks:

1. **Understand the original benchmark**: Identify task instructions, environments, tests, solutions
2. **Fork Harbor and develop adapter code**: Create `adapters/{adapter-name}/` with `adapter.py`, `run_adapter.py`, templates, and metadata. The adapter generates Harbor task directories (the standard `instruction.md`, `task.toml`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh` structure)
3. **Verify oracle solutions**: Run `harbor run -p datasets/<adapter-name>` and confirm 100% oracle pass rate
4. **Discuss parity plans**: Coordinate with the Harbor team on agent/model choices for parity experiments
5. **Run parity experiments**: Compare adapter results against original benchmark baselines
6. **Record parity results**: Formal `parity_experiment.json` with metrics, trial scores, and statistical comparisons
7. **Upload to HuggingFace**: Store parity data in the Harbor Parity Experiments dataset
8. **Register the dataset**: Add entries to `registry.json` in the Harbor repository (task-level entries with git URLs and commit IDs for pinning)
9. **Document and submit**: Comprehensive README following the Harbor adapter template

Quick bootstrapping: `harbor adapters init my-adapter --name "My Benchmark"` creates starter code and template files.

The adapter workflow is specifically designed to ensure **parity** between the original benchmark and the Harbor adaptation -- critical for credibility and for trusting that eval results on the Harbor version are comparable to published baselines. The Harbor team provides API cost support for parity experiments.

For benchmarks that do not need the full Harbor registry workflow (e.g., quick prototyping), an alternative is to create tasks directly as Inspect AI `Task` objects, loading data from JSON/JSONL/HuggingFace datasets and implementing custom scorers. This bypasses Harbor entirely but loses the registry, versioning, and parity infrastructure.

### 3.4 Current Registry Coverage and Benchmark Availability

The Harbor Framework registry (as of March 2026) hosts **47+ datasets** totaling **60,000+ tasks**. Notable entries:

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

**Spider2-DBT** (`spider2-dbt@1.0`): Present in the Harbor registry with 64 tasks. Both agents independently confirmed this, with inspect-harbor exposing wrapper functions `spider2_dbt_1_0` and `spider2_dbt`. Immediately runnable with no cloud credentials.

**LongMemEval**: **Not present** in the Harbor registry. Both agents independently verified this -- it does not appear in inspect-harbor's generated task functions (`tasks.py`) or its `REGISTRY.md`. Public Harbor registry URLs for LongMemEval (e.g., `harborframework.com/registry/longmemeval/1.0`) did not resolve. Integration requires custom adapter work.

### 3.5 The Eval Execution Pipeline -- Two Paths Compared

A key design decision is whether to use Harbor Framework's native `harbor run` pipeline or Inspect AI via inspect-harbor. Both agents analyzed this trade-off:

#### Path A: Harbor Framework Native Pipeline

```bash
harbor run -d "spider2-dbt@1.0" -a terminus-2 -m "openai/gpt-5"
```

1. Registry resolution → download and cache tasks from git
2. Job creation → trial config expansion (datasets x tasks x agents x models)
3. Parallel trial execution → Docker/cloud sandbox lifecycle (up to 100 parallel via Daytona)
4. Verifier → copies tests, runs test.sh, reads reward.txt/reward.json
5. Results → `jobs/` directory with web viewer (`harbor view jobs`)

#### Path B: Inspect AI via inspect-harbor

```bash
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

Uses av/harbor purely as infrastructure (model serving, API routing via LiteLLM) and Inspect AI + inspect-harbor for eval execution.

#### Comparison

| Dimension | Harbor Native (`harbor run`) | Inspect AI (`inspect eval`) |
|---|---|---|
| **Solver ecosystem** | Harbor agents (Terminus-2, Claude Code, etc.) | Inspect solvers + agent bridge + any Python agent |
| **Solver swapping** | `--agent` flag, `--agent-import-path` | `--solver` flag, entry points |
| **Sandbox providers** | Docker, Daytona, Modal, E2B | Docker, Kubernetes |
| **Horizontal scaling** | `-n` parallel trials, cloud sandboxes (up to 100) | `--max-samples`, `--max-tasks` |
| **Results format** | jobs/ directory with web viewer | EvalLog JSON with Inspect viewer |
| **RL/Training support** | Terminus-2 rollout collection, ATIF trajectories | Not native |
| **Benchmark ecosystem** | 47+ datasets via registry | 100+ via inspect_evals + Harbor registry via inspect-harbor |
| **Registry integration** | Direct (`-d dataset@version`) | Via inspect-harbor's `harbor()` |

**Recommendation**: Build around **Inspect AI + inspect-harbor** as the primary execution path for benchmarking, because it offers broader solver flexibility (wrapping arbitrary Python agents, runtime swapping, chain composition) and access to both the Inspect and Harbor benchmark ecosystems. Use Harbor Framework's native pipeline when **RL training data generation** (Terminus-2 rollout collection, ATIF trajectories) is the goal.

### 3.6 Integrating Spider2

**Spider2-DBT** (`spider2-dbt@1.0`): Immediately available. Zero setup required:
```bash
inspect eval inspect_harbor/spider2_dbt --model openai/gpt-5 --solver my_sql_agent
```
No cloud credentials needed -- uses local DuckDB.

**Spider2-Snow/Lite** (547 tasks across Snowflake/BigQuery/SQLite): NOT in the Harbor registry. Integration options:

1. **Harbor adapter path**: Create a Harbor adapter following the nine-step workflow, submit to the registry. This is the preferred long-term approach for community value and parity verification.
2. **Direct Inspect AI task**: Load from `spider2-snow.jsonl`, create an agentic solver with database execution tools, build a CSV comparison scorer porting Spider2's `compare_pandas_table`.
3. **Credential management**: Snowflake/BigQuery credentials need secure injection into Docker sandboxes via environment variables in `task.toml` or Inspect's sandbox configuration. This is non-trivial and unresolved in the existing tooling.

### 3.7 Integrating LongMemEval

LongMemEval is absent from the Harbor registry and has no existing adapter. Two approaches:

**Option A: Harbor adapter** (recommended for long-term value):
- Create task directories with `instruction.md` containing the chat history + question
- `environment/Dockerfile` with a minimal Python container
- `tests/test.sh` running an LLM-as-judge scorer implementing LongMemEval's five per-type evaluation patterns (off-by-one tolerance for temporal, latest-answer for knowledge-update, abstention detection)
- `solution/solve.sh` providing the ground truth
- Register in the Harbor registry via the full adapter workflow

**Option B: Direct Inspect AI task** (faster iteration):
- Load from `longmemeval_oracle.json` on HuggingFace (`xiaowu0162/longmemeval-cleaned`)
- Map to `Sample` objects with chat history as input and expected answer as target
- Implement a custom scorer replicating LongMemEval's LLM-as-judge prompts
- This bypasses Harbor entirely but loses the registry and parity infrastructure

The **oracle variant** (~128K tokens per instance) is the practical starting point -- it fits in large context windows. The **M variant** (~1.5M tokens per instance) exceeds most model context windows, requiring RAG-based solvers, which adds significant solver complexity.

### 3.8 Existing Examples and Patterns

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

### 3.9 Recommended Architecture for a General-Purpose Eval Runner

The recommended architecture has five planes:

```
┌──────────────────────────────────────────────────────────────────┐
│                   Eval Runner CLI / Config                        │
│  Declarative: benchmark_id + solver_id + model + provider +      │
│  resource_overrides + seed/attempts + version pins               │
├──────────────────────────────────────────────────────────────────┤
│               Benchmark / Task Plane                              │
│  Harbor Framework datasets (registry or local or custom)         │
│  Custom adapters for benchmarks not in registry                  │
│  Loaded via inspect-harbor's generic harbor() entrypoint         │
├──────────────────────────────────────────────────────────────────┤
│                  Solver / Agent Plane                              │
│  Inspect AI solvers: ReAct, CoT, custom @solver, agent_bridge   │
│  Runtime-swappable via --solver flag                             │
│  Harbor agents: Terminus-2, Claude Code, OpenHands (via bridge)  │
├──────────────────────────────────────────────────────────────────┤
│                Execution / Sandbox Plane                           │
│  Docker (local) | Daytona | Modal | E2B | Kubernetes             │
│  Concurrency: --max-samples (Inspect) or -n (Harbor)            │
├──────────────────────────────────────────────────────────────────┤
│               Infrastructure Plane (Optional)                     │
│  av/harbor: Ollama, vLLM, LiteLLM (API routing), LangFuse       │
│  Cloud APIs: OpenAI, Anthropic, Google                           │
├──────────────────────────────────────────────────────────────────┤
│                  Results / Analysis Plane                          │
│  Inspect AI logs (JSON) | Harbor jobs/ (JSON + viewer)           │
│  Normalized summary tables | Artifact collection                 │
│  Reproducibility metadata (dataset version, git commit, solver   │
│  version, model ID, seed/config)                                 │
└──────────────────────────────────────────────────────────────────┘
```

**Implementation roadmap** (both agents converged on this ordering):

1. Stand up the runner for `spider2-dbt@1.0` through inspect-harbor -- proof of concept, zero credentials, 64 tasks.
2. Build a solver plug-in registry in Inspect AI (`solver_id -> callable`) and run matrix sweeps over solver x model combinations.
3. Integrate LongMemEval -- either via Harbor adapter (preferred for community value and parity) or direct Inspect AI task (faster iteration).
4. Add reproducibility guardrails: pin dataset version + registry commit, store run manifests, enforce immutable run configs.
5. Build a thin orchestration wrapper that coordinates av/harbor backend startup, Inspect AI eval execution, and results normalization into a single declarative config.

---

## 4. Areas of Consensus

Both agents independently reached the same conclusions on the following points, providing high confidence:

### 4.1 The Two Harbors Are Completely Separate

Both agents verified through primary sources (PyPI metadata, import statements, repository inspection) that `inspect-harbor` bridges the Harbor Framework (`laude-institute/harbor`), not `av/harbor`. This is the foundational architectural fact.

### 4.2 Inspect AI Should Own Solver Logic

Both agents concluded that solver experimentation belongs in Inspect AI (via `@solver`, `agent_bridge`, `sandbox_agent_bridge`, `--solver` flag), while Harbor Framework should own task/environment/verification semantics. This separation keeps each tool in its area of strength.

### 4.3 The Generic `harbor()` Entrypoint Is Preferred

Both agents independently recommended using `harbor()` with `dataset_name_version` over per-dataset wrapper functions, citing the risk of registry/catalog drift where generated wrappers lag behind the live Harbor registry.

### 4.4 Spider2-DBT Is Ready; LongMemEval Requires Custom Work

Both agents verified: `spider2-dbt@1.0` is in the Harbor registry (64 tasks, local DuckDB, no credentials). LongMemEval is absent from the registry, inspect-harbor's task functions, and REGISTRY.md. Custom adapter or direct Inspect AI integration is required.

### 4.5 Start with spider2-dbt@1.0 as Proof of Concept

Both agents recommended the same implementation starting point: spider2-dbt via inspect-harbor as the lowest-friction entry, enabling immediate solver experimentation before tackling harder integrations.

### 4.6 Pin Everything for Reproducibility

Both agents emphasized the importance of pinning dataset versions (`@version`), git commit IDs, solver versions, model IDs, and seeds/configs to enable reproducible evaluation runs.

---

## 5. Areas of Disagreement

### 5.1 Spider2-DBT Task Count: 64 vs. 68

**Agent 1** flagged a metadata inconsistency: the Spider2-DBT registry page text says "68 examples" while the registry itself shows 64 tasks, and inspect-harbor's REGISTRY.md shows sample count 64. They suggest dataset filtering or stale metadata as the explanation.

**Agent 2** simply states the count is 64 tasks without noting the discrepancy.

**Resolution**: The Harbor registry and inspect-harbor both use 64 tasks. The Spider2 paper describes 68 DBT tasks, but filtering (e.g., removing tasks with environment issues or ambiguous specifications) during the Harbor adapter process likely reduced the count to 64. Both agents agree the runnable set is 64; the discrepancy is a metadata/documentation issue, not a functional one. Users should validate the exact task count in their run manifest.

### 5.2 Depth of Coverage

The two agents diverged significantly in what they covered most deeply:

- **Agent 1** was more concise and focused: stronger on identifying the adapter workflow as the critical integration path, flagging registry/version drift as a concrete risk, and providing a tighter set of actionable recommendations.
- **Agent 2** was substantially more detailed: deeper coverage of Harbor Framework internals (trial lifecycle, verifier mechanics, cloud sandbox options, Terminus-2's RL capabilities), inspect-harbor source code (6GB memory minimum, reward file parsing), Docker networking concerns, cost tracking gaps, training workflow integration, and concrete code examples.

Neither approach was wrong -- they represent different depth/breadth trade-offs. This synthesis combines both.

### 5.3 Role of av/harbor

Both agents agreed av/harbor is not the eval orchestrator, but differed slightly in emphasis:

- **Agent 1** describes av/harbor as "optional infrastructure" and cautions that bridging Inspect task semantics to av/harbor's service-only tooling requires custom engineering.
- **Agent 2** provides a concrete hybrid pattern (Path C) showing exactly how to use av/harbor as a model-serving backend with Inspect AI, and identifies specific Docker networking challenges.

**Resolution**: av/harbor is best understood as a convenience layer for model serving, not an eval component. The hybrid pattern works but requires attention to Docker network configuration.

---

## 6. Open Questions

These persist across both independent investigations and represent genuinely unresolved areas:

### 6.1 LongMemEval's Status in the Harbor Ecosystem

Neither agent found LongMemEval in the Harbor registry, and public URLs did not resolve. It is unclear whether:
- LongMemEval is in development as a Harbor adapter (check the Harbor team's Discord `#adapters-announcements` channel and [Adapter List spreadsheet](https://docs.google.com/spreadsheets/d/1mJbiASPm32DDNzEnV6eDGwpEf3FlMUe5dhkZmFjjSoo/))
- It exists in a private/internal registry
- No one has started the adapter work

This is the most impactful open question for the stated goal.

### 6.2 Docker Networking Between av/harbor and Inspect AI Sandboxes

av/harbor manages its own Docker network (`harbor-network`). Inspect AI creates separate Docker containers per evaluation sample. Whether Inspect AI sandbox containers can reach Harbor's inference backends on `harbor-network` depends on Docker network configuration that would need custom engineering (attaching Inspect sandbox containers to Harbor's network or using host networking). Neither agent tested this.

### 6.3 Spider2-Snow/Lite Credential Management

The full Spider2 benchmark (547 tasks) requires Snowflake and BigQuery credentials. How to securely inject these into evaluation sandboxes while maintaining reproducibility across different environments is unresolved. `task.toml` environment variables, Inspect's sandbox env, and Docker secrets are all possible approaches, but none has been validated.

### 6.4 Results Normalization Across Execution Paths

If some benchmarks run via Harbor Framework's native pipeline and others via Inspect AI, results end up in two incompatible formats (Harbor's `jobs/` directory with `result.json` vs. Inspect AI's `EvalLog` JSON). A unified results format, dashboard, or normalization layer would need custom engineering. Neither Harbor's web viewer nor Inspect's log viewer covers the other's format.

### 6.5 Cost Tracking and Budget Management

Neither Harbor Framework nor Inspect AI provides built-in cost tracking across a full eval suite. Terminus-2 supports `model_info` with input/output cost per token for LiteLLM cost tracking, but there is no cross-benchmark budget management, cost-per-benchmark estimation, or automatic stopping when budgets are exceeded. For large-scale eval sweeps, this is a significant operational gap.

### 6.6 Training Workflow Integration

Harbor Framework supports RL training workflows (Terminus-2's `collect_rollout_details` for token IDs and logprobs, ATIF trajectory format for SFT data) that Inspect AI does not natively provide. If the eval runner needs to double as a training data pipeline, some benchmarks may need the Harbor native path, creating a split architecture with two execution paths and two results formats. The engineering cost of this split is unquantified.

### 6.7 Concurrency and Resource Scaling

For large-scale evaluation (e.g., sweeping 5 solvers x 3 models x multiple benchmarks), the interaction between Inspect AI's concurrency controls (`--max-samples`, `--max-tasks`) and the resource demands of Docker sandboxes (especially with the 6GB memory minimum enforced by inspect-harbor) needs empirical validation. Cloud sandbox providers (Daytona, Modal) may alleviate local resource constraints, but their integration with Inspect AI's Docker sandbox model is untested.

### 6.8 Gaps Both Agents Missed

Neither agent investigated:
- **Inspect AI's native Docker sandbox networking** -- how sandbox containers connect to external services (model APIs, databases) in practice
- **Error recovery and retry semantics** -- how failed trials/samples are handled in both pipelines, and whether partial results are preserved
- **Multi-tenant / CI/CD integration** -- running the eval runner in automated pipelines, including secrets management, ephemeral infrastructure, and scheduled sweeps
- **inspect-harbor version compatibility** -- how tightly coupled inspect-harbor's version is to specific Harbor Framework and Inspect AI versions, and what the upgrade path looks like

---

## 7. Sources

### Primary Repositories
1. **Harbor Framework**: https://github.com/laude-institute/harbor
2. **av/harbor**: https://github.com/av/harbor (Apache-2.0, v0.4.1)
3. **inspect-harbor**: https://github.com/meridianlabs-ai/inspect_harbor (MIT, v0.4.5, Feb 2026)
4. **Inspect AI**: https://github.com/UKGovernmentBEIS/inspect_ai (MIT)
5. **Spider2**: https://github.com/xlang-ai/Spider2 (MIT)
6. **LongMemEval**: https://github.com/xiaowu0162/LongMemEval (MIT)

### Documentation
7. **Harbor Framework Core Concepts**: https://harborframework.com/docs/core-concepts
8. **Harbor Framework Getting Started**: https://harborframework.com/docs/getting-started
9. **Harbor Framework Registry**: https://harborframework.com/registry
10. **Harbor Framework Tasks**: https://harborframework.com/docs/tasks
11. **Harbor Framework Agents**: https://harborframework.com/docs/agents
12. **Harbor Framework Terminus-2**: https://harborframework.com/docs/agents/terminus-2
13. **Harbor Framework Evals**: https://harborframework.com/docs/run-jobs/run-evals
14. **Harbor Framework Adapters**: https://harborframework.com/docs/datasets/adapters
15. **Harbor Framework Registering Datasets**: https://harborframework.com/docs/datasets/registering-datasets
16. **Harbor Framework Datasets**: https://harborframework.com/docs/datasets
17. **Harbor Framework Cloud Sandboxes**: https://harborframework.com/docs/run-jobs/cloud-sandboxes
18. **Harbor Framework Results/Artifacts**: https://harborframework.com/docs/run-jobs/results-and-artifacts
19. **av/harbor Wiki - User Guide**: https://github.com/av/harbor/wiki/1.-Harbor-User-Guide
20. **av/harbor Wiki - Services**: https://github.com/av/harbor/wiki/2.-Services
21. **av/harbor Wiki - CLI Reference**: https://github.com/av/harbor/wiki/3.-Harbor-CLI-Reference
22. **av/harbor Wiki - Harbor Bench**: https://github.com/av/harbor/wiki/5.1.-Harbor-Bench
23. **av/harbor Wiki - lm-evaluation-harness**: https://github.com/av/harbor/wiki/2.3.17-Satellite%3A-lm-evaluation-harness
24. **av/harbor Wiki - LiteLLM**: https://github.com/av/harbor/wiki/2.3.5-Satellite%3A-LiteLLM
25. **Inspect AI Documentation**: https://inspect.aisi.org.uk/
26. **Inspect AI Solvers**: https://inspect.aisi.org.uk/solvers.html
27. **inspect-harbor PyPI**: https://pypi.org/project/inspect-harbor/
28. **inspect-harbor Documentation**: https://meridianlabs-ai.github.io/inspect_harbor/
29. **Harbor PyPI (Framework)**: https://pypi.org/project/harbor/

### Source Code (Verified by Agents)
30. **inspect_harbor _task.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_task.py
31. **inspect_harbor _converters.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_converters.py
32. **inspect_harbor _scorer.py**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/harbor/_scorer.py
33. **inspect_harbor pyproject.toml**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/pyproject.toml
34. **inspect_harbor tasks.py (generated wrappers)**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/src/inspect_harbor/tasks.py
35. **inspect_harbor REGISTRY.md**: https://github.com/meridianlabs-ai/inspect_harbor/blob/main/REGISTRY.md

### Registry Entries
36. **Spider2-DBT Registry**: https://harborframework.com/registry/spider2-dbt/1.0
37. **LongMemEval Registry (not found)**: https://harborframework.com/registry/longmemeval/1.0

### Papers
38. **Spider 2.0**: arXiv:2411.07763 (ICLR 2025 Oral)
39. **LongMemEval**: arXiv:2410.10813 (ICLR 2025)

### Datasets
40. **LongMemEval HuggingFace**: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
41. **Spider2 Leaderboard**: https://spider2-sql.github.io/
42. **Harbor Parity Experiments**: https://huggingface.co/datasets/harborframework/parity-experiments

---

## 8. Methodology

### Research Process

This report was produced through a three-phase multi-agent research process:

**Phase 1 -- Independent Research**: Two AI agents independently researched the topic. Each conducted web research, read primary documentation, examined source code, and produced comprehensive standalone reports.

- **Agent 1** (`codex-5.3-xhigh`): Focused on primary source verification -- PyPI metadata, raw source code from GitHub, Harbor Framework documentation, and registry pages. Produced a concise, high-confidence report with 20+ verified sources.
- **Agent 2** (`opencode-wibey-opus-4-6`): Conducted broader research including DeepWiki summaries, Harbor Framework documentation, av/harbor wiki, inspect-harbor source code, and academic papers. Produced a detailed report covering more ground but with some reliance on secondary sources.

**Phase 2 -- Cross-Pollination**: Each agent reviewed the other's Phase 1 report, identifying strengths, weaknesses, and gaps. Each then produced a refined report incorporating insights from the peer review while independently verifying new claims through additional research.

- Agent 1's refinement focused on sharpening the Harbor Framework vs. av/harbor distinction, verifying registry status, and tightening the architectural recommendation.
- Agent 2's refinement substantially expanded Harbor Framework coverage (trial lifecycle, cloud sandboxes, Terminus-2, adapter workflow), verified inspect-harbor source code directly, and added execution path comparison.

**Phase 3 -- Synthesis** (this report): A third agent synthesized both refined reports into a definitive final document, resolving contradictions, combining the deepest analysis from each, deduplicating without losing nuance, and identifying gaps that persisted across both investigations.

**Timing**: Full research cycle completed on March 1, 2026.

### Confidence Assessment

- **High confidence**: Two Harbors distinction, Spider2-DBT availability, LongMemEval absence, solver extensibility via Inspect AI, adapter workflow for new benchmarks, generic `harbor()` entrypoint recommendation.
- **Medium confidence**: Specific inspect-harbor internals (6GB memory minimum, reward file parsing) -- verified by one agent reading source code, consistent with the other agent's findings but not independently re-verified.
- **Lower confidence**: Docker networking between av/harbor and Inspect AI sandboxes (identified as a gap but not tested), concurrency scaling characteristics (not empirically validated), training workflow integration trade-offs (described architecturally but not implemented).
