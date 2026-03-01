Here is the comprehensive final synthesis report:

---

# Final Research Synthesis: Building a General-Purpose Eval Runner with Harbor and inspect-harbor

## 1. Executive Summary

The most critical finding across all investigations is that **there are two entirely distinct open-source projects named "Harbor"**, and conflating them will derail any integration effort:

- **`av/harbor`** — A Docker Compose-based CLI for orchestrating local LLM stacks (inference backends, frontends, satellite services). Its eval capability, Harbor Bench, is **model-level only**: prompt → response → LLM judge. It cannot run agent evaluations in sandboxed environments.

- **`laude-institute/harbor`** (Harbor Framework, harborframework.com) — A purpose-built **agent evaluation and RL framework** from the creators of Terminal-Bench. It runs AI agents (Claude Code, OpenHands, Codex CLI, custom agents) in containerized environments with standardized task formats, verifier scripts, and multi-trial statistical evaluation.

**`inspect-harbor`** bridges **Harbor Framework** (not `av/harbor`) to the **Inspect AI** evaluation framework, mapping Harbor tasks to Inspect samples, solvers, and scorers.

**For a general-purpose agent eval runner that mixes and matches solvers against benchmarks like Spider2 and LongMemEval, the recommended stack is: Harbor Framework + inspect-harbor + Inspect AI.** The `av/harbor` project can optionally serve as infrastructure (model serving via LiteLLM) but plays no role in agent evaluation itself.

Spider2 has partial support today via `spider2-dbt@1.0` in the Harbor registry (64 samples from the DBT subset). LongMemEval has no existing Harbor adapter and requires custom engineering. Cross-benchmark result normalization and reproducibility guardrails require additional custom tooling beyond what any of these frameworks provide out of the box.

---

## 2. Key Findings

### Theme A: The Two-Harbor Disambiguation

Both agents independently discovered and flagged the naming collision. This is the single most important finding for anyone starting from the original research question (which referenced `github.com/av/harbor`).

| Dimension | `av/harbor` | `laude-institute/harbor` |
|---|---|---|
| **Purpose** | Local LLM stack orchestration | Agent evaluation & RL |
| **Eval type** | Model-level (LLM judge) | Agent-level (sandboxed environments) |
| **Service model** | Frontends / Backends / Satellites via Docker Compose | Tasks / Datasets / Agents / Trials / Jobs |
| **Scaling** | Single-host Docker Compose | Docker, Daytona, Modal, E2B, GKE |
| **inspect-harbor** | Not connected | Primary integration target |
| **Key tool** | Harbor Bench (YAML tasks + judge) | `harbor run` / `inspect eval` |

### Theme B: Harbor Framework Architecture

Harbor Framework's core abstraction chain is **Job → TrialConfig → Trial**, where:

- **Task** = self-contained eval unit: `instruction.md` (prompt), `task.toml` (metadata/config), `environment/` (Dockerfile), `tests/` (verifier), optional `solution/` (oracle)
- **Dataset** = collection of tasks, registered in a JSON registry with name/version/git refs
- **Agent** = the system under evaluation, either external (`BaseAgent` via bash commands) or installed in-container (`BaseInstalledAgent` in headless mode)
- **Trial** = one execution: environment setup → agent setup/run → verifier → cleanup/artifact collection, with timeout/retry behavior
- **Job** = orchestrator: expands datasets into trial configs, manages concurrency, computes metrics continuously, supports resume semantics

Built-in agents include Terminus-2 (reference), Claude Code, OpenHands, Codex CLI, and MiniSweAgent. Custom agents extend `BaseAgent` from `src/harbor/agents/base.py`.

### Theme C: inspect-harbor as the Inspect AI Bridge

inspect-harbor (`pip install inspect-harbor`) translates between the two frameworks:

| Harbor Concept | Inspect AI Concept |
|---|---|
| Task (`instruction.md`) | `Sample.input` |
| Dataset (tasks collection) | `Task` (Inspect task function) |
| Environment (`Dockerfile`) | `SandboxEnvironmentSpec` |
| Verifier (`tests/test.sh`) | Custom `Scorer` |
| Reference solution (`solve.sh`) | Oracle `Solver` |

**Default agent scaffold**: ReAct agent with `bash(timeout=300)`, `python(timeout=300)`, `update_plan()`, and `CompactionEdit()` for context management.

**Custom solver injection**: via `--solver path/to/file.py@my_solver` CLI flag, or programmatically (e.g., `eval(terminal_bench_sample(), solver=claude_code())`).

**Scoring pipeline**: copies `/tests` into sandbox, runs verifier script, parses `/logs/verifier/reward.txt` then `reward.json`, returns score with metadata.

**Generic loader**: `inspect_harbor/harbor` supports `registry_url`, `registry_path`, and `path` parameters for loading from official, custom, or local sources without modifying the core package.

### Theme D: Solver Registration

Two extension planes exist:

1. **Inspect-side** (preferred for `inspect eval` workflows): implement `@solver` or `@agent` decorated Python functions following Inspect AI conventions. Third-party framework bridges (OpenAI Agents SDK, LangChain, Pydantic AI) are supported via `as_solver()`.

2. **Harbor-native** (for `harbor run` workflows): extend `BaseAgent` or `BaseInstalledAgent` and reference via `--agent-import-path`. Uses Jinja2 templates for agent installation into Docker containers.

For a general-purpose runner centered on Inspect's logging/analysis, Inspect solvers are the primary abstraction.

### Theme E: Benchmark/Dataset Registration

The Harbor adapter workflow is a documented 9-step process: understand original benchmark → write adapter code → generate Harbor task directories → verify oracle solutions → run parity experiments → document → upload to HuggingFace → register in JSON registry → write README.

For inspect-harbor exposure, two paths exist:
1. **Immediate**: use the generic `inspect_harbor/harbor` entrypoint with custom registry/path params
2. **Named functions**: regenerate `tasks.py` from Harbor registry via `scripts/generate_tasks.py`

### Theme F: Spider2 and LongMemEval Integration Status

**Spider2**:
- `spider2-dbt@1.0` is already in the Harbor registry with 64 samples — immediately runnable
- This covers the Spider2-DBT subset (upstream: 68 tasks), **not** the full 632-problem enterprise Spider2 suite
- Full Spider2 tasks requiring live BigQuery/Snowflake access present significant containerization challenges (credentials, network access, cost)

**LongMemEval**:
- Not present in the Harbor registry or inspect-harbor's generated task list
- Requires a custom adapter that packages each question instance with serialized conversation history
- LongMemEval's multi-session stateful evaluation model conflicts with Harbor's per-task, per-container paradigm
- Recommended approach: encode history/session artifacts per task, define task variants by history length (`S`, `M`, oracle-retrieval), map to resource tiers

### Theme G: Practical Architecture for a General-Purpose Eval Runner

The converged architecture across all investigations has 6 layers:

```
┌─────────────────────────────────────────────────────┐
│  1. Control Plane (CLI / Experiment Manifest)        │
│     - benchmark_id, solver_id, model, env_profile    │
│     - Immutable spec with pinned versions/commits    │
├─────────────────────────────────────────────────────┤
│  2. Benchmark Plane                                  │
│     - Harbor registry datasets (official + private)  │
│     - Custom adapters (LongMemEval, etc.)            │
├─────────────────────────────────────────────────────┤
│  3. Solver Plane                                     │
│     - Inspect @solver / @agent decorators            │
│     - Harbor-native BaseAgent (optional)             │
├─────────────────────────────────────────────────────┤
│  4. Execution Plane                                  │
│     - inspect eval inspect_harbor/harbor             │
│     - Sandbox: docker (local), daytona (scale)       │
├─────────────────────────────────────────────────────┤
│  5. Scoring / Normalization Plane                    │
│     - Raw reward JSON + verifier artifacts preserved │
│     - Normalized schema: dataset, task, solver,      │
│       model, reward, timings, exception, artifacts   │
├─────────────────────────────────────────────────────┤
│  6. Reproducibility Guardrails                       │
│     - Fail on implicit dataset versions              │
│     - Record resource overrides (memory floor, etc.) │
└─────────────────────────────────────────────────────┘
```

**Hybrid option**: use `av/harbor` for model serving (LiteLLM proxy, Ollama backends) while running agent evaluation through the Harbor Framework + inspect-harbor stack.

---

## 3. Areas of Consensus

All agents agreed on these points, supported by independent verification:

1. **`inspect-harbor` bridges to `laude-institute/harbor`, not `av/harbor`.** Both agents independently discovered this crucial distinction and made it their primary finding.

2. **Harbor Framework's task format** (`instruction.md` + `task.toml` + `environment/` + `tests/` + optional `solution/`) is the standard contract for benchmark integration. All evidence points to the same directory structure.

3. **Inspect AI solvers are the primary extension point** for a general-purpose eval runner. The `@solver` and `@agent` decorators, combined with `--solver` CLI injection, provide the most flexible mix-and-match capability.

4. **LongMemEval is not in the Harbor registry** and requires custom adapter work. Both agents searched independently and confirmed absence.

5. **Cross-benchmark comparability is non-trivial.** Different benchmarks produce different reward schemas (binary pass/fail vs. multi-metric JSON), requiring custom normalization.

6. **The oracle solver pattern** (running reference solutions to validate tasks) is an essential quality gate before running model evaluations.

7. **Cloud scaling uses Daytona, Modal, or E2B**, but multi-container task support is limited to Daytona + local Docker.

---

## 4. Areas of Disagreement

### Spider2 Registry Availability

- **Claude-opus (phase 1)** stated: "No existing Harbor adapter: Spider2 is not in the Harbor registry as of this research."
- **Codex (phase 1)** stated: "`spider2-dbt@1.0` is already listed in Harbor registry."
- **Resolution**: Codex was correct. The cross-pollination round confirmed that `spider2-dbt@1.0` with 64 samples exists in the Harbor registry and inspect-harbor's generated task list. However, both agents correctly noted this covers only the DBT subset, not the full 632-problem Spider2 enterprise suite. The disagreement was primarily about precision in naming — Spider2-DBT vs. Spider2 writ large.

### Level of Architecture Detail

- **Claude-opus** proposed three distinct architecture options (A: Harbor Framework-centered, B: av/harbor model-level only, C: hybrid) with detailed ASCII diagrams.
- **Codex** converged on a single 6-layer architecture without distinguishing options.
- **Resolution**: Both are valid framings. The 6-layer architecture subsumes Option A from claude-opus. Option B (av/harbor only) is unsuitable for agent eval and was rightly excluded by codex. The hybrid option (C) remains a practical consideration for model serving but not the primary architecture.

### Depth on av/harbor

- **Claude-opus** provided extensive detail on av/harbor's Harbor Bench, Boost, and lm-evaluation-harness integration.
- **Codex** mentioned av/harbor briefly as a disambiguation then focused entirely on Harbor Framework.
- **Resolution**: Claude-opus's coverage is more complete for readers who need to understand why av/harbor is *not* the right tool. For the practical task of building an eval runner, codex's focused approach is more actionable.

---

## 5. Novel Insights

These findings emerged specifically from the cross-pollination refinement round and were not present in either agent's initial report:

1. **Memory floor enforcement**: inspect-harbor's converter enforces a **minimum 6144 MB memory** unless explicitly overridden. This can silently alter benchmark resource conditions compared to original task definitions — a fidelity concern for reproducible evaluation.

2. **Version resolution precedence**: When a dataset version is omitted in inspect-harbor's generic loader, the resolution order is `"head" > highest semver > lexical last`. This is critical for reproducibility — experiments must pin versions explicitly.

3. **Oracle solver side effects**: The oracle solver runs `/solution/solve.sh` and intentionally may leave `/solution` state for scorer-dependent tasks. This means the scoring pipeline is not purely functional — some benchmarks have order-dependent verification.

4. **git sparse-checkout + LFS dependency**: Harbor's task download path uses git sparse-checkout and optionally git-lfs (with a warning if missing). This affects remote task portability and can cause silent failures in environments without git-lfs.

5. **Spider2-DBT parity gap**: The Harbor registry lists 64 samples while Spider2-DBT upstream documents 68 tasks. This 4-task delta (likely an adapter/packaging difference) means claiming "Spider2 evaluation" requires careful scoping documentation.

6. **Hybrid infrastructure insight**: Using `av/harbor` for model serving (LiteLLM proxy) while using Harbor Framework for agent evaluation is architecturally sound — the projects serve complementary roles despite the name collision.

---

## 6. Open Questions

Even after independent investigation and cross-pollination, the following remain uncertain:

1. **Harbor Framework `BaseAgent` API stability**: The internal API (`base.py`) is not fully documented publicly. The `BaseInstalledAgent` Jinja2 template system and `BaseEnvironment` interface contracts are inferred from source reading rather than stable documentation. Breaking changes are possible given the framework's youth (released ~Nov 2025).

2. **inspect-harbor maturity**: At version 0.4.x, breaking changes are likely. The generated task function approach (where `tasks.py` is auto-generated from the registry) creates a coupling between package releases and registry updates.

3. **LongMemEval adapter feasibility at scale**: While encoding conversation histories per-task is theoretically possible, it's unclear whether Harbor's container model can practically handle the 1.5M-token history variants without prohibitive memory/storage overhead or breaking the evaluation semantics.

4. **Full Spider2 enterprise integration**: Tasks requiring live BigQuery/Snowflake connections fundamentally conflict with sandboxed containerized evaluation. The credential management, network access, and cost implications are unresolved. Only the local-DB Spider2-DBT subset is tractable today.

5. **Apple Silicon compatibility**: Harbor's Docker-based approach may have x86/ARM architecture conflicts on Apple M-series chips. The extent of this issue for specific benchmarks is undocumented.

6. **Cross-benchmark comparability methodology**: No standard normalization exists for comparing a binary pass/fail benchmark against one producing multi-metric reward JSON. Whether a meaningful composite score or ranking is achievable across diverse benchmarks remains an open research question.

7. **Registry freshness and cache invalidation**: Harbor's registry is a JSON file with git refs. There is no documented mechanism for subscribing to updates, invalidating cached tasks, or detecting when an adapter's output has drifted from the upstream benchmark's latest version.

8. **HAL Harness as alternative/complement**: The `princeton-pli/hal-harness` framework supports both custom agents and Inspect AI solvers with Azure VM scaling. Whether it's complementary to or competitive with the Harbor + inspect-harbor stack was not deeply explored.

---

## 7. Sources

### Primary Repositories
- https://github.com/av/harbor
- https://github.com/laude-institute/harbor
- https://github.com/meridianlabs-ai/inspect_harbor
- https://github.com/UKGovernmentBEIS/inspect_ai
- https://github.com/UKGovernmentBEIS/inspect_evals

### Harbor Framework Documentation
- https://harborframework.com/docs
- https://harborframework.com/docs/core-concepts
- https://harborframework.com/docs/getting-started
- https://harborframework.com/docs/tasks
- https://harborframework.com/docs/datasets
- https://harborframework.com/docs/datasets/adapters
- https://harborframework.com/docs/datasets/registering-datasets
- https://harborframework.com/docs/datasets/metrics
- https://harborframework.com/docs/agents
- https://harborframework.com/docs/agents/trajectory-format
- https://harborframework.com/docs/run-jobs/run-evals
- https://harborframework.com/docs/run-jobs/cloud-sandboxes
- https://harborframework.com/docs/run-jobs/results-and-artifacts
- https://harborframework.com/registry

### av/harbor Documentation
- https://github.com/av/harbor/wiki/2.-Services
- https://github.com/av/harbor/wiki/5.1.-Harbor-Bench

### inspect-harbor Source & Documentation
- https://pypi.org/project/inspect-harbor/
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/README.md
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/REGISTRY.md
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_task.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_converters.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_solver.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/src/inspect_harbor/harbor/_scorer.py
- https://raw.githubusercontent.com/meridianlabs-ai/inspect_harbor/main/scripts/generate_tasks.py

### Harbor Framework Source
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
- https://pypi.org/project/harbor/

### Inspect AI Documentation
- https://inspect.aisi.org.uk/solvers.html
- https://inspect.aisi.org.uk/agents.html

### Benchmarks
- https://github.com/xlang-ai/Spider2
- https://spider2-sql.github.io/
- https://github.com/xiaowu0162/LongMemEval

### Blog Posts & Articles
- https://quesma.com/blog/compilebench-in-harbor/ (CompileBench → Harbor migration)
- https://tessl.io/blog/how-to-evaluate-ai-agents-an-introduction-to-harbor/
- https://snorkel.ai/blog/terminal-bench-2-0-raising-the-bar-for-ai-agent-evaluation/
- https://mixster.dev/2026/01/15/terminal-bench-docker/ (Terminal-Bench on macOS)
- https://www.comet.com/docs/opik/integrations/harbor (Opik/Harbor integration)
- https://venturebeat.com/ai/terminal-bench-2-0-launches-alongside-harbor-a-new-framework-for-testing

### Related Frameworks
- https://github.com/princeton-pli/hal-harness
- https://github.com/badlogic/pi-terminal-bench

### Research Papers
- Spider 2.0 (ICLR 2025 Oral) — https://openreview.net/forum?id=XmProj9cPs
- LongMemEval (ICLR 2025) — https://arxiv.org/abs/2410.10813

---

## 8. Methodology

### Research Process
This report was produced through a **multi-agent adversarial research process** with three phases:

**Phase 1 — Independent Research** (March 1, 2026)
Two AI agents independently researched the same topic with no access to each other's work:
- **Agent A**: Claude Opus — produced a comprehensive 485-line report with detailed architecture diagrams, code examples, and three architectural options
- **Agent B**: Codex 5.3 (extra-high reasoning) — produced a structured 171-line report organized around the 8 research sub-questions, with direct source citations per claim

**Phase 2 — Cross-Pollination & Skeptical Review** (March 1, 2026)
Each agent received the other's report and was tasked with:
- Identifying what the peer report added to the picture
- Verifying or correcting peer claims through fresh research
- Surfacing new findings neither report covered

Note: The Claude Opus cross-review produced an empty output (likely a session issue). Codex successfully cross-reviewed Claude's report, correcting the Spider2 availability claim and surfacing 5 novel findings about memory floors, version resolution, oracle solver behavior, git-lfs dependencies, and provider constraints.

**Phase 3 — Final Synthesis** (March 1, 2026)
All phase 1 reports, phase 2 refinement reports, and an earlier parallel research run (session `9d5a38`) were synthesized into this final deliverable by Claude Opus, organized thematically rather than by source agent.

### Agents Used
- Claude Opus 4.6 (Anthropic)
- Codex 5.3 extra-high reasoning (OpenAI)

### Key Observation on Process
The cross-pollination round proved its value primarily through the Spider2 correction (one agent's claim that "no adapter exists" was corrected by the other's finding of `spider2-dbt@1.0` in the registry) and through the surfacing of implementation-level details (memory floors, version resolution) that neither agent prioritized in independent research. The adversarial structure successfully prevented a false negative about Spider2 availability from persisting into the final report.
