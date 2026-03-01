# Adversarial Strategy -- Known Issues & Fixes

Tracking everything that needs fixing to make the adversarial strategy produce real improvements. Ordered by impact.

---

## 1. Evaluator always returns 0.0 (critical)

**Symptom:** GEPA logs show `New subsample score 0.0 is not better than old score 0.0, skipping` on every round. No improvement is ever accepted.

**Root cause:** `parse_judge_output()` fails to extract the JSON from the judge agent's response. The agents wrap their output in markdown prose, extra commentary, or non-standard fencing that the current regex in `_extract_json_from_markdown()` doesn't match. When parsing fails, the function returns `0.0` as the default score.

**Fix:**
- Make `_extract_json_from_markdown()` more resilient: try `json.loads()` on the raw text first, handle fenced blocks with extra whitespace, handle the case where the agent writes a preamble before the JSON.
- Add a fallback regex that extracts `"overall_score": <number>` directly from the text even when the full JSON doesn't parse.
- Log a warning when JSON parsing fails so the issue is visible during runs.
- Add live-agent test cases that capture real judge output formats and verify parsing.

**File:** `src/ivory_tower/strategies/adversarial.py` -- `parse_judge_output()`, `_extract_json_from_markdown()`

---

## 2. Judge prompt asks for bare JSON but agents add prose

**Symptom:** The judging prompt says "Respond with ONLY a JSON object (no markdown fencing, no extra text)" but agents (especially OpenCode-wrapped ones) ignore this and write explanatory text around the JSON.

**Fix:**
- Restructure the judging prompt to use a tool-call / structured-output framing that agents are more likely to respect.
- Alternatively, accept that agents will add prose and make the parser robust enough to handle it (see fix 1).
- Consider a two-pass approach: ask the agent to judge in natural language first, then ask it to emit the structured JSON separately.

**File:** `src/ivory_tower/prompts.py` -- `_JUDGING_TEMPLATE`

---

## 3. Feedback passed to proposer is empty when scores are 0.0

**Symptom:** `extract_feedback_from_reflective_dataset()` returns defaults because GEPA's reflective dataset contains `0.0` scores and empty feedback dicts. The improvement prompt then shows `0/10` for every dimension with `(none provided)` for strengths/weaknesses/suggestions.

**Root cause:** Circular dependency with issue 1 -- when the evaluator returns `(0.0, {"error": "Failed to parse..."})`, the ASI dict has no `dimensions`, `strengths`, etc. This gets stored in the reflective dataset and the proposer receives garbage feedback.

**Fix:**
- Even when JSON parsing fails, extract whatever text the judge wrote and pass it as a `critique` string so the improving agent at least has the natural-language feedback.
- In `evaluator()`, when `parse_judge_output()` returns an error ASI, read the raw judge markdown and stuff it into `asi["critique"]`.

**File:** `src/ivory_tower/strategies/adversarial.py` -- `evaluator()` closure, `extract_feedback_from_reflective_dataset()`

---

## 4. No error logging or observability during optimization

**Symptom:** When things go wrong (JSON parse failure, counselors error, file not found), the errors are silently swallowed. The only signal is `0.0` scores in the optimization log.

**Fix:**
- Add a proper `logging.getLogger(__name__)` logger.
- Log at WARNING level when judge output fails to parse.
- Log at INFO level each round's score and whether the candidate was accepted.
- Log at ERROR level when counselors subprocess fails.
- Write a `phase2/{agent}-debug.log` with the raw judge outputs for post-mortem analysis.

**File:** `src/ivory_tower/strategies/adversarial.py` -- throughout

---

## 5. `_normalize_counselors_output()` misses agent files

**Symptom:** After `run_counselors()`, the expected file (`{agent}-seed.md` or `{agent}.md`) sometimes doesn't exist because the counselors CLI writes to a slug-based subdirectory with a different naming convention (e.g., `report.md` or a session-id-based name).

**Root cause:** The normalization function only checks the most recently modified slug directory and only falls back to `report.md` when there's exactly 1 agent. Multi-agent runs or agents with non-standard output names are missed.

**Fix:**
- Walk all `.md` files in the slug directory and match by content heuristic (e.g., which agent session produced it) when filename matching fails.
- Add a more aggressive fallback: if only one `.md` file exists in the slug dir and one expected output is missing, use it regardless of name.
- Consider standardizing the counselors `--tools` naming so output filenames are predictable.

**File:** `src/ivory_tower/strategies/adversarial.py` -- `_normalize_counselors_output()`, `read_counselors_output()`

---

## 6. Optimized report may be the raw seed (no actual improvement)

**Symptom:** Because GEPA sees `0.0 is not better than 0.0` on every round, the `best_candidate` is always the seed. The "optimized" report is identical to the seed.

**Root cause:** Direct consequence of issue 1. Even if the proposer successfully produces an improved report, GEPA rejects it because both old and new scores are 0.0.

**Fix:**
- Fix issue 1 (score parsing).
- Additionally, consider setting GEPA's `raise_on_exception=True` during development so silent failures surface immediately.
- Add a post-optimization assertion or warning: if `final_score == seed_score == 0.0`, log that optimization likely failed.

**File:** `src/ivory_tower/strategies/adversarial.py` -- `optimize_seed()`

---

## 7. Thread safety of round_counter and seed_result mutations

**Symptom:** No observed bug yet, but `optimize_seed()` captures `seed_result` (a mutable manifest object) and `round_counter` (a list used as mutable int) in closures that run inside GEPA's optimization loop while two such loops run concurrently in a ThreadPoolExecutor.

**Fix:**
- Each `optimize_seed()` call has its own closure scope so there's no cross-thread sharing of `round_counter` or `seed_result`. But confirm that `manifest.save()` isn't called concurrently from inside the closures (it isn't -- only after `optimize_seed` returns). Low priority, just worth auditing.

---

## 8. Synthesis prompt shows `0.0/10` scores

**Symptom:** The adversarial synthesis prompt includes `scored 0.0/10 by agent_b` which misleads the synthesizer into thinking the reports are terrible.

**Root cause:** Consequence of issue 1 cascading into `_run_synthesis()`.

**Fix:**
- When scores are 0.0 (likely indicating parse failure), omit the score from the synthesis prompt or add a note that scoring was unavailable.
- Better: fix issue 1 so real scores flow through.

**File:** `src/ivory_tower/strategies/adversarial.py` -- `_run_synthesis()`, `src/ivory_tower/prompts.py` -- `_ADVERSARIAL_SYNTHESIS_TEMPLATE`

---

## 9. Council live tests untested

**Symptom:** `TestCouncilLiveE2E` exists but has never been run. Unknown if council strategy works end-to-end with live agents.

**Fix:**
- Run `uv run pytest -m live -k council -v` and fix whatever breaks.

**File:** `tests/test_live_e2e.py`

---

## 10. `litellm` left in venv but not in dependencies

**Symptom:** `litellm` was installed during development (`uv add litellm`) but later made unnecessary by the `_unused_lm` callable workaround. It's still in the venv.

**Fix:**
- Run `uv remove litellm` to clean the venv.
- Verify GEPA still works without it (it should -- the no-op callable bypasses the code path that imports litellm).

---

## Priority order

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 1 | Score parsing returns 0.0 | Blocks all optimization | Medium |
| 2 | Judge prompt ignored by agents | Causes issue 1 | Low |
| 3 | Empty feedback to proposer | Degrades improvement quality | Low (fixed by 1) |
| 4 | No logging | Debugging is blind | Low |
| 5 | File normalization misses agents | Can crash pipeline | Medium |
| 6 | Optimized == seed | User-facing quality | Fixed by 1 |
| 7 | Thread safety audit | Preventive | Low |
| 8 | Synthesis shows 0.0 scores | Misleads synthesizer | Low (fixed by 1) |
| 9 | Council live tests unrun | Unknown breakage | Low |
| 10 | Stale litellm in venv | Cleanup | Trivial |

Fixing issues 1-4 would make the adversarial strategy functional. Issues 5-10 are polish.
