# Adversarial Strategy -- Known Issues & Fixes

## Previously fixed (issues 1-8)

Issues 1-6 and 8 were fixed in earlier commits on this branch. Score parsing now works (6.5 instead of 0.0), judge prompt restructured, logging added, file normalization improved, 0.0 scores omitted from synthesis.

---

## Remaining issues (ordered by impact)

### 11. Seed capture reads conversational output, not the actual report (CRITICAL)

**Status:** Open.

**Symptom:** Phase 1 seed files contain agent meta-commentary ("I'll create a comprehensive report...") or planning notes ("## Goal -- produce a report..."), NOT the actual research report. The Anthropic agent writes its real 20K report to `research_report.md` inside the counselors slug directory, but the orchestrator copies `{agent}.md` (3K conversational summary) as the seed.

**Root cause:** Counselors writes per-agent output to `<slug>/<agent>.md` -- this is the agent's conversational/session output (what it "said"), not necessarily the artifact it produced. Some agents (OpenCode-based) use file-write tools to create separate report files during execution. The `_normalize_counselors_output()` function copies `{agent}.md` as the seed, ignoring these extra files.

**Evidence from live run `20260301-220933-5611e3`:**
```
phase1/<slug>/opencode-anthropic-fast.md      3,047 bytes  ← conversational summary (copied as seed)
phase1/<slug>/research_report.md             20,633 bytes  ← ACTUAL report (ignored!)
phase1/<slug>/opencode-openai-fast.md        12,595 bytes  ← planning notes (copied as seed)
```

The `run.json` from counselors tracks `outputFile` pointing to `{agent}.md` only. It does not track extra files written by agents.

**Fix:** After `run_counselors()` completes for phase 1, pick the **largest** `.md` file in the slug directory (excluding `prompt.md`, `summary.md`) as the seed, not necessarily `{agent}.md`. Heuristic:
1. Check if a file other than `{agent}.md`, `prompt.md`, `summary.md` exists in the slug dir and is substantially larger (>2x) than `{agent}.md`
2. If yes, use that file as the seed (it's the actual report)
3. If no, use `{agent}.md` as before

This heuristic should be in `_normalize_counselors_output()` or a new helper. Apply the same logic in `read_counselors_output()` for improvement rounds.

**Files to edit:**
- `src/ivory_tower/strategies/adversarial.py` -- `_normalize_counselors_output()`, `read_counselors_output()`

**How to verify:** After fixing, run `uv run pytest tests/ -x -v` (all 194 mocked tests should pass). Then check that the fix would pick `research_report.md` (20K) over `opencode-anthropic-fast.md` (3K) by examining the logic.

---

### 12. Feedback passthrough from GEPA reflective_dataset is broken (CRITICAL)

**Status:** Open.

**Symptom:** The improvement prompt (phase 2, proposer round) shows **example/template feedback** instead of actual judge feedback. From the live run:

```
## Judge's Feedback
### Overall Score: 0.0/10
### Strengths
- Comprehensive coverage of major subtopics          ← THIS IS THE EXAMPLE FROM THE PROMPT TEMPLATE
- Good use of recent primary sources in Section 3    ← NOT REAL JUDGE FEEDBACK
### Weaknesses
- Section 2 lacks citations for key claims
- No discussion of counterarguments to the main thesis
```

Meanwhile, the actual judge gave scores like 5.4/10 and 7.6/10 with detailed, specific feedback. That feedback never reached the improving agent.

**Root cause:** `extract_feedback_from_reflective_dataset()` at `adversarial.py:293` iterates GEPA's `reflective_dataset` (a `Mapping[str, Sequence[Mapping[str, Any]]]`), takes the last entry from the first key, and looks for `score`, `overall_score`, `dimensions`, `strengths`, `weaknesses`, `suggestions`, `critique`. 

The problem is that GEPA's reflective_dataset structure doesn't match what we expect. The evaluator returns `(score, asi_dict)` where `asi_dict` has keys `dimensions`, `strengths`, `weaknesses`, `suggestions`, `critique` -- but NOT `score` or `overall_score`. The score is tracked separately by GEPA in its own data structures. So `extract_feedback_from_reflective_dataset` finds the ASI dict but `last_entry.get("score")` returns None, and `last_entry.get("overall_score")` also returns None, giving `score: 0.0`.

The dimension values (7, 6, 5, 7, 6) and strings ("Comprehensive coverage...") in the improvement prompt match the **example JSON in `_JUDGING_TEMPLATE`** exactly. This means either (a) GEPA's reflective_dataset was empty so defaults were used, or (b) the reflective_dataset contained the example values because an earlier parsing step extracted the example JSON from the prompt instead of the actual judge output.

**Fix:**
1. Add debug logging to dump the raw `reflective_dataset` structure the proposer receives: `logger.debug("[%s] reflective_dataset keys=%s, structure=%s", agent, list(reflective_dataset.keys()), {k: len(v) for k, v in reflective_dataset.items()})`
2. Also log the first entry: `logger.debug("[%s] reflective_dataset first entry sample: %s", agent, str(dict(list(reflective_dataset.items())[0][1][-1]))[:500] if reflective_dataset else "empty")`
3. Fix `extract_feedback_from_reflective_dataset` to handle GEPA's actual format. The function may need to look for nested structures or different key names.
4. As a fallback: if the reflective_dataset doesn't contain usable feedback, the proposer should read the most recent judge output file directly from disk (the `judging/round-NN-*.md` file) and parse it with `parse_judge_output()` instead of relying on GEPA's reflective_dataset.

**Files to edit:**
- `src/ivory_tower/strategies/adversarial.py` -- `extract_feedback_from_reflective_dataset()`, the `proposer()` closure inside `optimize_seed()`

**How to verify:** Run `uv run pytest tests/ -x -v` (mocked tests pass). Then run live: `uv run pytest tests/test_live_e2e.py -m live -k adversarial -v -s` and check the improvement prompt files in `phase2/{agent}-improve-round-*/improve-prompt.md` -- they should contain real judge scores and feedback, not the example template values.

---

### 13. `max_rounds` maps 1:1 to `max_metric_calls` but seed eval consumes a call

**Status:** Open.

**Symptom:** `--max-rounds 2` sets `max_metric_calls=2` in GEPA config. But GEPA uses one metric call to evaluate the seed, leaving only 1 call for evaluating an improved candidate. The user expects 2 *improvement* rounds, not 1 seed eval + 1 improvement eval.

**Evidence:** Optimization log shows `rounds: 3` evaluator calls but `score_history` has only 1 entry (the seed). GEPA's stopper fired after 2 metric calls.

**Fix:** In `_run_adversarial_optimization()`, set `max_metric_calls = max_rounds + 1` (or `max_rounds * 2 + 1` if GEPA does subsample evals) so the user gets the number of improvement rounds they asked for.

**File to edit:**
- `src/ivory_tower/strategies/adversarial.py` -- the `GEPAConfig` construction around line 775

**How to verify:** `uv run pytest tests/ -x -v` then live test -- optimization log should show `score_history` with entries for each round.

---

### 14. Improvement prompt sends conversational output as "Your Current Report"

**Status:** Open. Direct consequence of issue 11.

**Symptom:** The improvement prompt's "## Your Current Report" section contains the 3K conversational meta-commentary, not the 20K actual report. The improving agent is told to improve a summary it didn't write, not the real report.

**Evidence from `phase2/opencode-anthropic-fast-improve-round-03/improve-prompt.md`:**
```
## Your Current Report
I'll read the file and follow the instructions.
I'll create a comprehensive research report comparing WebSocket vs SSE...
Now let me gather more information about scalability...
```

This is the agent's conversational output, not a research report.

**Root cause:** The `proposer()` closure passes `candidate.get("report", "")` as the current report. The `candidate` dict comes from GEPA, which stores whatever was in the seed candidate -- and the seed was set from `seed_file.read_text()` which reads the normalized seed file (the conversational output, per issue 11).

**Fix:** Fixing issue 11 (seed capture) automatically fixes this. Once the seed contains the real report, GEPA's candidate will contain the real report, and the improvement prompt will show the real report.

---

### 15. Proposer reads conversational output from improvement rounds too

**Status:** Open. Same pattern as issue 11/14 but for improvement rounds.

**Symptom:** After `run_counselors()` in the proposer, `read_counselors_output()` returns `{agent}.md` from the slug dir. If the agent wrote its improved report to a separate file (e.g., `improved_research_report.md`), that file is ignored. The proposer returns the conversational output to GEPA as the "improved" candidate.

**Evidence:** `phase2/opencode-anthropic-fast-improve-round-03/`:
```
opencode-anthropic-fast-improve-round-03/<slug>/opencode-anthropic-fast.md   3,366 bytes  ← returned by read_counselors_output
improved_research_report.md                                                  25,486 bytes  ← ignored!
```

**Fix:** Apply the same "pick the largest substantive .md file" heuristic from issue 11 to `read_counselors_output()`. When there are extra `.md` files in the output directory (outside the slug dir or inside it) that are substantially larger than `{agent}.md`, prefer those.

**Files to edit:**
- `src/ivory_tower/strategies/adversarial.py` -- `read_counselors_output()`

---

### 16. Log the exact input to each GEPA improvement round

**Status:** Open.

**Symptom:** It's impossible to debug the optimization loop without seeing what GEPA passed to the proposer and evaluator at each round.

**Fix:** Add detailed round-by-round logging:
1. In `evaluator()`: log the length of `candidate["report"]` and the first 200 chars
2. In `proposer()`: log the `reflective_dataset` structure (keys + entry count per key), the extracted feedback dict (score, dimension scores), and the length of `candidate["report"]`
3. Write a `phase2/{agent}-round-{N}-debug.json` with the full feedback dict passed to `build_improvement_prompt`

**File to edit:**
- `src/ivory_tower/strategies/adversarial.py` -- `evaluator()` and `proposer()` closures

---

## Fix dependency tree

```
Issue 11 (seed capture)
  └── Issue 14 (improvement prompt has wrong report) -- fixed by 11
  └── Issue 15 (proposer returns wrong improved text) -- same heuristic as 11

Issue 12 (feedback passthrough)
  └── Add logging to diagnose reflective_dataset structure
  └── Fix extract_feedback_from_reflective_dataset or bypass it

Issue 13 (max_rounds off by one)
  └── Simple: max_metric_calls = max_rounds + 1

Issue 16 (debug logging)
  └── Independent, do alongside other fixes
```

**Recommended execution order:**
1. Fix 11 + 15 together (seed capture + read_counselors_output best-file heuristic)
2. Fix 12 (feedback passthrough -- add logging first, then fix based on what you see)
3. Fix 13 (max_rounds mapping)
4. Fix 16 (debug logging for GEPA rounds)
5. Run live tests to verify end-to-end improvement

---

## Context for subagent

**IMPORTANT: ALL work MUST happen in the git worktree at `/Users/auk000v/dev/tools/ivory-tower-fixes`.** Do NOT read, write, or run commands in `/Users/auk000v/dev/tools/ivory-tower` (that is the main worktree on `main` branch). Every file path, every `uv run pytest`, every `git commit`, every `git push` must use `/Users/auk000v/dev/tools/ivory-tower-fixes` as the working directory. This worktree is on branch `fix/adversarial-strategy`.

**Key files (all paths relative to `/Users/auk000v/dev/tools/ivory-tower-fixes`):**
- `src/ivory_tower/strategies/adversarial.py` -- all fix targets
- `src/ivory_tower/prompts.py` -- prompt templates (no changes needed for these fixes)
- `src/ivory_tower/counselors.py` -- counselors CLI wrapper (read-only reference)
- `tests/test_adversarial_strategy.py` -- 45 mocked tests
- `tests/test_adversarial_helpers.py` -- helper unit tests
- `tests/test_integration.py` -- 21 integration tests
- `tests/test_live_e2e.py` -- 18 live adversarial + 4 council tests

**Counselors output structure:**
```
<output_dir>/
  <slug>/                          ← counselors creates this
    prompt.md                      ← copy of input prompt
    run.json                       ← metadata (timestamp, tools, duration, wordCount, outputFile)
    summary.md                     ← human-readable summary
    <agent>.md                     ← agent's conversational/session output
    <agent>.stderr                 ← agent's stderr
    [extra files]                  ← agents may write additional files via file-write tools
```

The `{agent}.md` is the agent's conversational output. The REAL report may be in a separate file like `research_report.md` or `improved_research_report.md`. The heuristic to find the real report: pick the largest `.md` file excluding `prompt.md`, `summary.md`, and `run.json`.

**Test commands (run from `/Users/auk000v/dev/tools/ivory-tower-fixes`):**
- Mocked: `uv run pytest tests/ -x -v` (should see 194 passed)
- Live adversarial: `uv run pytest tests/test_live_e2e.py -m live -k adversarial -v -s` (5-10 min)

**After each fix:** commit with a descriptive message and `git push`. All git commands must run in `/Users/auk000v/dev/tools/ivory-tower-fixes`.
