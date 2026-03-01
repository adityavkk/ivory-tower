## Research Report: Harbor + inspect-harbor for a General-Purpose Eval Runner (as of March 1, 2026)

### Executive Summary
There are two different “Harbor” projects in play, and this is the main architectural decision point:

1. `av/harbor` is a Docker-based local LLM service orchestrator (backends/frontends/satellites, profiles, tunnels, etc.).
2. `laude-institute/harbor` (Harbor Framework) is an eval/task framework (tasks/datasets/agents/trials/jobs).

`inspect-harbor` (PyPI `inspect-harbor`, repo `meridianlabs-ai/inspect_harbor`) integrates with the **Harbor Framework task model**, not `av/harbor` service orchestration.  
So for a mix-and-match solver/benchmark runner in Inspect AI, the clean path is: **Inspect AI + inspect-harbor + Harbor Framework registry/adapters**.

---

### 1. Harbor Architecture

### `av/harbor` (the repo you linked)
`av/harbor` is centered on service orchestration via CLI + Docker Compose:
- `harbor up/down/restart`, defaults, profiles, capabilities detection, per-service config/env.
- Organizes services into UIs/backends/satellites.
- Includes `Harbor Bench` as a built-in benchmark service (LLM-as-judge, configurable task YAML, reports/CSV/JSON output).

This architecture is ideal for standing up model infra and tool services quickly, but it is not the same object model as Inspect/Harbor Framework eval tasks.

### Harbor Framework (`laude-institute/harbor`)
Core concepts are explicit and eval-native:
- `Task` = instruction + container env + verifier.
- `Dataset` = collection of tasks.
- `Agent` runs tasks in environment.
- `Trial` = one rollout attempt.
- `Job` = many trials; internally expanded and run in parallel.

This is the Harbor model that `inspect-harbor` consumes.

---

### 2. inspect-harbor as the Inspect↔Harbor Bridge
From `inspect_harbor` source and README:

- It exposes Inspect tasks like `inspect_harbor/terminal_bench`, `inspect_harbor/hello_world`, etc.
- Generic entrypoint `harbor(...)` supports loading tasks from:
  - Harbor registry (`dataset_name_version`)
  - Local path
  - Git URL + commit
  - Custom registry URL/path
- It maps Harbor task artifacts into Inspect objects:
  - Harbor task → Inspect `Sample`
  - Harbor environment → Inspect `SandboxEnvironmentSpec`
  - Harbor verifier (`tests/test.sh`) → Inspect scorer (`harbor_scorer`)
  - Harbor solution script → Inspect solver (`oracle`)
- Default solver if none provided: Inspect ReAct scaffold with `bash`, `python`, `update_plan`, and `CompactionEdit`.
- Scoring contract: expects verifier output under `/logs/verifier/reward.txt` or `/logs/verifier/reward.json`.

Inference: this is a task/harness bridge, not a Harbor-service lifecycle manager.

---

### 3. Defining and Registering New Solvers
For Inspect AI, use normal solver registration:
- Define a `@solver` function returning async solve logic (`TaskState`, `Generate`).
- Pass with CLI `--solver path/to/file.py@solver_name`.

With Harbor tasks this works unchanged:
- `inspect eval inspect_harbor/<dataset> --solver your_solver.py@solver --model ...`
- Or use built-in `inspect_harbor/oracle` for dataset sanity checks.

---

### 4. Defining and Registering New Benchmarks/Datasets

### In Harbor Framework
- Create/adapter tasks into Harbor task format (`instruction.md`, `task.toml`, `environment/`, `tests/`, optional `solution/`).
- Register dataset in registry.
- Harbor adapter docs define parity workflow (oracle pass, parity runs, registration).

### In inspect-harbor
- Immediate use: call generic `inspect_harbor/harbor` with custom `registry_url`, `registry_path`, local `path`, or git source.
- Convenience exposure: regenerate static task wrappers via `scripts/generate_tasks.py` (auto-generates `tasks.py` + `REGISTRY.md` from Harbor registry).

---

### 5. Eval Execution Pipeline (actual bridge flow)
1. `inspect eval inspect_harbor/<task-or-dataset> ...`
2. `load_harbor_tasks(...)` resolves source (registry/local/git).
3. Each Harbor task is converted to Inspect `Sample` with sandbox config and metadata.
4. Solver runs in sandbox (default ReAct/custom/oracle).
5. `harbor_scorer` copies tests, executes verifier script in sandbox.
6. Scorer parses reward files and returns score + metadata.
7. Inspect logs written to `./logs`.

---

### 6. Practical Architecture for a General-Purpose Runner

Recommended design:
- Config-driven matrix over:
  - benchmark descriptor (Inspect task path + `-T` args)
  - solver descriptor (`file.py@solver` or packaged solver)
  - model(s)
  - execution controls (`max_tasks`, retries, fail-on-error)
- Use `eval_set()` for combinatorics and reproducibility.
- Keep benchmark integration and solver integration decoupled.

Minimal architecture components:
- Benchmark registry adapter layer (Harbor registry + custom/local)
- Solver registry layer (Inspect solver specs)
- Run planner (matrix expansion)
- Execution engine (Inspect `eval`/`eval_set`)
- Results sink (Inspect logs + post-processing)

If you must also use `av/harbor`, treat it as infra bootstrap:
- Start model/tool services with `av/harbor`
- Point Inspect/solvers at those endpoints
- Keep eval lifecycle in Inspect + inspect-harbor

---

### 7. Existing Patterns You Can Reuse
- `inspect_harbor` already includes many benchmark wrappers (auto-generated from Harbor registry).
- Built-in Oracle solver pattern for verifier sanity.
- Generic Harbor loader pattern for private/local datasets without waiting for wrapper generation.
- Harbor Framework adapter workflow for onboarding external benchmarks.

---

### 8. Spider2 + LongMemEval Status and Engineering Gaps

As of March 1, 2026:
- Harbor registry in `inspect_harbor` includes `spider2-dbt@1.0` (64 tasks).
- I did not find `LongMemEval` in the generated inspect-harbor registry table.

What this implies:
- Spider2: you can run the available Harbor adapter variant now (`spider2-dbt`), but it is not identical to the full Spider 2.0 paper scope (632 workflow problems).
- LongMemEval: likely requires a new Harbor adapter (conversation-history packaging + verifier/scoring mapping) before it becomes first-class in `inspect_harbor`.

Custom engineering likely needed:
- LongMemEval adapter + Harbor taskification pipeline.
- Possibly custom scorer logic if category-wise memory metrics are needed beyond scalar reward.
- Careful design for multi-session memory replay in sandbox context.

---

### Key Gaps / Uncertainties in Research
- Some Harbor docs/search indexing is noisy due multiple “Harbor” products.
- Could not verify a separate “inspect-harbor transport/decorator API” in current `meridianlabs-ai/inspect_harbor` source; current public code centers on Harbor task loading + scorer/solver bridge.
- Spider2 public ecosystem has multiple variants/subsets (site/leaderboard vs adapters), so adapter scope must be pinned explicitly by dataset/version.

---

## Sources
- https://github.com/av/harbor  
- https://github.com/av/harbor/wiki/1.-Harbor-User-Guide  
- https://github.com/av/harbor/wiki/3.-Harbor-CLI-Reference  
- https://github.com/av/harbor/wiki/5.1.-Harbor-Bench  
- https://github.com/laude-institute/harbor  
- https://harborframework.com/docs/core-concepts  
- https://harborframework.com/docs/agents  
- https://harborframework.com/docs/tasks  
- https://harborframework.com/docs/evals  
- https://harborframework.com/docs/datasets/adapters  
- https://harborframework.com/docs/datasets/registering-datasets  
- https://pypi.org/project/inspect-harbor/  
- https://github.com/meridianlabs-ai/inspect_harbor  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/README.md  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/__init__.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_sandbox_utils.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py  
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md  
- https://inspect.aisi.org.uk/reference/inspect_ai.solver.html  
- https://inspect.aisi.org.uk/solvers.html  
- https://inspect.aisi.org.uk/tasks.html  
- https://arxiv.org/abs/2411.07763  
- https://spider2-sql.github.io/  
- https://github.com/xiaowu0162/LongMemEval
