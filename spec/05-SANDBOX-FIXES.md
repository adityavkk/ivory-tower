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

Both strategies call `run_counselors()` directly with filesystem paths and
never reference `config.sandbox_backend`. Passing `--sandbox local` (or any
backend) is silently ignored. The CLI validates the backend but the strategies
don't use it.

The sandbox spec (03-SANDBOX-SPEC.md) calls for these strategies to be
refactored to use the sandbox system, but this work was never done.

**Fix options**:
a. Refactor council/adversarial to use `GenericTemplateExecutor` (large change, may break GEPA integration for adversarial)
b. Wire sandbox providers directly into the strategy code without the template executor
c. Document as unsupported and warn at CLI level when `--sandbox` is used with council/adversarial

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
