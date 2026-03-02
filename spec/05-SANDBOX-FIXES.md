---
title: "ivory-tower: sandbox live testing results + open issues"
author: "automated live testing"
version: 1
created: 2026-03-01
base_sha: 7328df9
branch: test/sandbox-live
branch_head: 373d99f
depends_on: "03-SANDBOX-SPEC.md v1"
---

# Sandbox Live Testing -- Results and Open Issues

Live testing of the sandbox system and template-based strategies against real
agents and real filesystem operations. Branch `test/sandbox-live` (6 commits,
`373d99f`). Base: main at `7328df9`.

## Test matrix

| Component | Result | Notes |
|-----------|--------|-------|
| NullSandboxProvider | pass | Full lifecycle with real I/O |
| LocalSandboxProvider | pass | Isolation, copy_in/out, shared volume, append |
| FileBlackboard (transcript) | pass | Multi-agent, multi-round, access control |
| FileBlackboard (directory) | pass | Per-file writes, sorted concatenation |
| AgentFSSandboxProvider | skipped | `agentfs` CLI not installed |
| DaytonaSandboxProvider | skipped | `daytona` SDK not installed |
| Debate template (live) | pass | 4 phases, blackboard transcript populated |
| Map-reduce template (live) | partial | Runs but fan-out is broken (see issue 1) |
| Red-blue template (live) | pass | 4 phases, correct team assignments |

## Fixes applied on branch (3)

### Fix A: `_find_report()` picks wrong file

**File**: `src/ivory_tower/executor/counselors_exec.py:60`
**Commit**: `4e56d6f`

The report finder was returning counselors meta-files (`summary.md`,
`prompt.md`) instead of the agent's actual output. Counselors writes several
files per slug directory:

```
<slug>/prompt.md       # input prompt copy
<slug>/summary.md      # counselors-generated summary
<slug>/run.json        # metadata
<slug>/<agent>.md      # actual agent output
```

The old code picked the first `.md` file alphabetically. Fixed to:
1. Prefer exact `{agent_name}.md` match
2. Filter out known meta-files (`prompt.md`, `summary.md`, `run.json`)
3. If multiple candidates remain, pick the largest
4. Fall back to any `.md` as last resort

### Fix B: `rounds_override` applied to non-iterative phases

**File**: `src/ivory_tower/templates/executor.py:217`
**Commit**: `fbf485b`

When `rounds_override=1` was passed (e.g. to limit debate rounds), ALL phases
were treated as iterative -- including opening statements, closing statements,
and verdict. This produced wrong output keys like `agent-round-1` instead of
`agent.md`.

Fixed: only phases that explicitly declare a `rounds` field in their template
config are treated as iterative. `rounds_override` can override the count but
won't make a non-iterative phase iterative.

### Fix C: `{subtopic}` KeyError in output filename template

**File**: `src/ivory_tower/templates/executor.py:312`
**Commit**: `0dd39ff`

The map-reduce template uses `{subtopic}-research.md` as its output filename
pattern. When the dynamic fan-out system doesn't resolve subtopics (see issue
1 below), `str.format()` raises `KeyError`. Added `_safe_format()` helper
that substitutes `'unknown'` for missing template variables with a warning.

---

## Open issues

### Issue 1: Dynamic fan-out not implemented

**Priority**: high
**Affects**: map-reduce strategy
**File**: `src/ivory_tower/templates/executor.py`, `_resolve_phase_agents()`

The map-reduce template declares `agents: dynamic` on its map phase, expecting
the decompose phase to produce subtopics that are then assigned to individual
agents. Currently `_resolve_phase_agents()` returns all agents for `dynamic`
phases instead of creating subtopic-specific assignments. The `{subtopic}`
output template variable is never populated.

**Result**: Both agents write to `unknown-research.md`, second overwrites
first. Map-reduce produces output but loses half the research.

**Fix**: Implement subtopic extraction from the decompose phase output.
Parse the planner's response for subtopics (numbered list, headings, or JSON),
assign one agent per subtopic, and populate the `{subtopic}` variable in the
output template. This is the core feature that makes map-reduce useful.

### Issue 2: Debate prompts don't include blackboard context

**Priority**: medium
**Affects**: debate strategy
**File**: `src/ivory_tower/templates/executor.py`, `_run_iterative_phase()`

During the debate rounds phase, the prompt sent to agents is just the raw
`topic` string. The blackboard transcript is written to a file in the agent's
sandbox, but nothing in the prompt tells the agent to read it or references
its content.

Agents with file-read tools can discover the transcript, but agents without
tool access will debate blind -- each round is effectively independent.

**Fix**: Inject the current blackboard transcript into the prompt before each
round. The `build_prompt` step should read the blackboard content and append
it as context (e.g. "Previous discussion:\n{transcript}\n\nYour turn:").

### Issue 3: `LocalSandbox.snapshot()` returns None

**Priority**: low
**Affects**: local sandbox backend
**File**: `src/ivory_tower/sandbox/local.py`

The local sandbox provider's `snapshot()` method is a no-op that returns
`None`. This means post-phase snapshots configured in templates
(`snapshot_after_phase: true`) silently do nothing with the local backend.

**Fix**: Implement snapshot as a directory copy or tarball. Alternatively,
document this as a known limitation and recommend `agentfs` for snapshot
support.

### Issue 4: Council and adversarial ignore `--sandbox`

**Priority**: medium
**Affects**: council, adversarial strategies
**File**: `src/ivory_tower/strategies/council.py`, `src/ivory_tower/strategies/adversarial.py`
**Status**: Resolved (ACP integration).

Both strategies now use `AgentExecutor.run()` via `_get_executor()` /
`_create_sandbox()` / `_run_agent()` helpers. Sandboxes are created per-agent
using `config.sandbox_backend` and passed to executors. The `run_counselors()`
calls no longer exist in strategies. Option (b) was implemented.

### Issue 5: `resume_pipeline()` doesn't preserve `sandbox_backend`

**Priority**: low
**Affects**: template-based strategies with sandbox
**File**: `src/ivory_tower/engine.py`, `resume_pipeline()`

When resuming a run, `resume_pipeline()` reconstructs a `RunConfig` from the
manifest but does not set `sandbox_backend`. This means resumed runs default
to `sandbox_backend="none"` even if the original run used a different backend.

**Fix**: Persist `sandbox_backend` in the manifest (it may already be in
`sandbox_config`) and restore it in `resume_pipeline()`.

### Issue 6: AgentFS and Daytona backends untested live

**Priority**: medium
**Affects**: agentfs, daytona sandbox backends

Neither backend was available during testing. All existing tests are fully
mocked. The agentfs backend shells out to the `agentfs` CLI and the daytona
backend uses the daytona Python SDK -- both need their respective tools
installed for live testing.

**Fix**: Install agentfs and daytona in a CI environment and add live tests.
The test structure is already in place (`@pytest.mark.skipif` guards).

### Issue 7: `opencode-openai-fast` produces empty output in sandboxed context

**Priority**: low
**Affects**: any strategy using codex-spark agents with sandbox
**Observed in**: debate live test

The codex-spark agent auto-rejects file read permissions for workspace paths,
producing 0-word output in some debate rounds. This is a counselors/agent
configuration issue, not an ivory-tower bug, but it affects reliability.

**Workaround**: Use agents that don't require permission prompts for file
access (e.g. claude-based agents) when running sandboxed strategies.

---

## TDD plan

Each issue lists RED tests (write first, must fail) then GREEN implementation.
Tests target existing files where possible -- no new test files unless needed.

### Issue 1: Dynamic fan-out

RED tests go in `tests/test_template_executor.py`:

```python
class TestResolvePhaseAgents:
    """Unit tests for _resolve_phase_agents()."""

    def test_dynamic_with_fan_out_parses_subtopics_from_numbered_list(self):
        """Planner output with '1. Topic A\n2. Topic B' produces 2 agent
        assignments, one per subtopic."""

    def test_dynamic_with_fan_out_parses_subtopics_from_headings(self):
        """Planner output with '## Topic A\n## Topic B' produces 2 assignments."""

    def test_dynamic_with_fan_out_assigns_agents_round_robin(self):
        """3 subtopics + 2 agents -> agents assigned round-robin."""

    def test_dynamic_with_fan_out_populates_subtopic_variable(self):
        """Output filename '{subtopic}-research.md' resolves to actual subtopic
        names, not 'unknown'."""

    def test_dynamic_without_fan_out_falls_back_to_all_agents(self):
        """agents='dynamic' with no fan_out or missing prior phase returns all."""

class TestMapReduceEndToEnd:
    def test_map_reduce_subtopics_produce_separate_files(self):
        """Full map-reduce run: decompose produces 3 subtopics, map phase
        creates 3 distinct output files (not 'unknown-research.md')."""
```

GREEN: Implement subtopic parsing in `_resolve_phase_agents()`. Read the
fan-out phase's output files, extract subtopics (numbered list, markdown
headings, or JSON array), return `(agent, subtopic)` pairs assigned
round-robin. Pass `subtopic` into `_safe_format()` for output filenames.

### Issue 2: Blackboard context in prompts

RED tests go in `tests/test_template_executor.py`:

```python
class TestIterativePhaseBlackboardPrompt:
    def test_prompt_includes_blackboard_transcript(self):
        """In round 2, the prompt passed to the executor includes the
        blackboard transcript from round 1, not just the raw topic."""

    def test_prompt_in_round_1_has_empty_transcript(self):
        """In round 1 (empty blackboard), prompt still includes the
        blackboard section header but no prior content."""

    def test_prompt_without_blackboard_is_just_topic(self):
        """Phases with no blackboard config pass topic as-is."""
```

GREEN: In `_run_iterative_phase()`, before each agent call, read
`blackboard.get_content()` and build a composite prompt:
`f"{topic}\n\n## Previous discussion\n\n{transcript}"` when transcript
is non-empty, else just `topic`. No changes to `_run_single_phase()`.

### Issue 3: `LocalSandbox.snapshot()`

No new tests needed. `test_sandbox_local.py::TestLocalSandboxSnapshotDiffDestroy::test_snapshot_returns_none`
already asserts `snapshot()` returns `None`. Flip this test:

```python
# Change existing test from:
def test_snapshot_returns_none(self):
    assert sandbox.snapshot("snap1") is None

# To:
def test_snapshot_returns_path(self):
    sandbox.write_file("doc.md", "content")
    snap = sandbox.snapshot("snap1")
    assert snap is not None
    assert Path(snap).exists()
    # Verify snapshot is independent -- delete original, snapshot persists
    os.remove(sandbox._resolve("doc.md"))
    assert Path(snap).exists()
```

GREEN: Implement `snapshot()` in `LocalSandbox` as a `shutil.copytree()`
of the workspace to `snapshots/{label}/`. Return the snapshot path.

### Issue 4: Council/adversarial ignore `--sandbox`

RED tests go in `tests/test_engine.py`:

```python
class TestSandboxWarning:
    def test_council_with_sandbox_warns(self):
        """Running council with --sandbox local emits a warning that
        sandbox is not supported for this strategy."""

    def test_adversarial_with_sandbox_warns(self):
        """Running adversarial with --sandbox local emits a warning."""

    def test_debate_with_sandbox_no_warning(self):
        """Template-based strategies with --sandbox produce no warning."""
```

GREEN: In `engine.py::run_pipeline()`, after resolving the strategy, check
if the strategy class has a `supports_sandbox` attribute (default `False`
on council/adversarial, `True` on template-based strategies). If
`config.sandbox_backend != "none"` and the strategy doesn't support it,
emit `logger.warning()`. This is fix option (c) -- cheapest, safest.

### Issue 5: Resume preserves `sandbox_backend`

RED test goes in `tests/test_engine.py` (extend existing `TestResumePipeline`):

```python
def test_resume_reconstructs_sandbox_backend(self):
    """resume_pipeline() restores sandbox_backend from manifest.sandbox_config."""
```

Also in `tests/test_sandbox_integration.py` (extend `TestManifestBackwardCompatibility`):

```python
def test_v3_manifest_sandbox_config_survives_resume(self):
    """Manifest with sandbox_config={'backend': 'local'} is restored
    into RunConfig.sandbox_backend='local' during resume."""
```

GREEN: In `engine.py::resume_pipeline()`, read
`manifest.sandbox_config.get("backend", "none")` and set it on the
reconstructed `RunConfig`.

### Issue 6: AgentFS and Daytona live tests

RED tests go in `tests/test_sandbox_live.py` (already created on the branch):

```python
@pytest.mark.live
@pytest.mark.skipif(not shutil.which("agentfs"), reason="agentfs not installed")
class TestAgentFSLive:
    def test_create_sandbox_write_read_destroy(self): ...
    def test_shared_volume_lifecycle(self): ...
    def test_snapshot_produces_db_copy(self): ...
    def test_diff_after_write(self): ...

@pytest.mark.live
@pytest.mark.skipif(not _daytona_available(), reason="daytona not installed")
class TestDaytonaLive:
    def test_create_sandbox_write_read_destroy(self): ...
    def test_execute_command_in_container(self): ...
    def test_resource_limits_applied(self): ...
```

GREEN: Install `agentfs` and `daytona` in a CI environment, run the tests.
No source changes expected -- the providers are already implemented. If
tests fail, fix the providers.

### Issue 7: Empty agent output

No code fix needed (external agent behavior). No new tests -- the existing
live test `test_sandbox_live.py` already handles this with resilience
checks (`373d99f`). Document the workaround in the README sandbox section.

---

## Commit plan

| # | Branch work | Commit message |
|---|-------------|----------------|
| 1 | RED: fan-out tests | `test: add failing tests for dynamic fan-out subtopic resolution` |
| 2 | GREEN: implement fan-out | `feat: implement dynamic fan-out with subtopic parsing in template executor` |
| 3 | RED: blackboard prompt tests | `test: add failing tests for blackboard transcript in iterative prompts` |
| 4 | GREEN: inject transcript | `feat: inject blackboard transcript into iterative phase prompts` |
| 5 | RED+GREEN: local snapshot | `feat: implement LocalSandbox.snapshot() as directory copy` |
| 6 | RED+GREEN: sandbox warning | `fix: warn when --sandbox used with council/adversarial` |
| 7 | RED+GREEN: resume sandbox | `fix: restore sandbox_backend from manifest on resume` |
| 8 | RED: agentfs/daytona live | `test: add live test skeletons for agentfs and daytona backends` |
| 9 | Regression run | `chore: verify full test suite passes` |
