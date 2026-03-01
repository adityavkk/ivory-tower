# Adversarial Strategy -- Known Issues & Fixes

Tracking everything that needs fixing to make the adversarial strategy produce real improvements. Ordered by impact.

---

## 1. ~~Evaluator always returns 0.0~~ FIXED

**Status:** Fixed in `99cfc66`. Scores now extract correctly (6.5 in live tests).

**What was done:**
- Rewrote `_extract_json_from_markdown()` with 5 extraction strategies (raw JSON, json fenced blocks, any fenced block, targeted overall_score regex, fallback)
- Added `_extract_score_from_text()` for prose-only fallback
- Rewrote `parse_judge_output()` to try all `.md` files recursively with multi-strategy extraction

---

## 2. ~~Judge prompt asks for bare JSON but agents add prose~~ FIXED

**Status:** Fixed in `07544f3`. Both agents now produce parseable JSON.

**What was done:**
- Restructured `_JUDGING_TEMPLATE` with two-step approach: evaluate in prose first, then emit JSON on the final line
- Added concrete JSON example for agents to follow
- Removed unrealistic "no markdown fencing" instruction

---

## 3. ~~Feedback passed to proposer is empty when scores are 0.0~~ FIXED

**Status:** Fixed in `99cfc66`.

**What was done:**
- When JSON parsing fails, raw judge prose is stuffed into `asi["critique"]` so the improvement prompt gets natural-language feedback
- `parse_judge_output()` returns combined text as `critique` even on total parse failure

---

## 4. ~~No error logging or observability~~ FIXED

**Status:** Fixed in `99cfc66`.

**What was done:**
- Added `logger = logging.getLogger(__name__)` at module level
- Logging at DEBUG for extraction attempts, INFO for scores and phase transitions, WARNING for parse failures and 0.0 scores, ERROR for optimization exceptions with traceback

---

## 5. ~~`_normalize_counselors_output()` misses agent files~~ FIXED

**Status:** Fixed in `e34fc7f`.

**What was done:**
- Searches ALL slug directories (not just most recent)
- Adds substring filename matching for truncated agent names
- `report.md` fallback works for any number of agents
- `read_counselors_output()` also uses substring matching

---

## 6. ~~Optimized report may be the raw seed~~ FIXED

**Status:** Fixed in `99cfc66`. Warning logged when `seed_score == final_score == 0.0`.

---

## 7. Thread safety of round_counter and seed_result mutations

**Status:** Audited, no issue. Each `optimize_seed()` call has its own closure scope. `manifest.save()` is only called after both threads join.

---

## 8. ~~Synthesis prompt shows `0.0/10` scores~~ FIXED

**Status:** Fixed in `07544f3` + `99cfc66`. Scores of 0.0 are treated as None and omitted from the synthesis prompt header.

---

## 9. Council live tests untested

**Status:** Open. `TestCouncilLiveE2E` exists but has never been run.

**Fix:** Run `uv run pytest -m live -k council -v` and fix whatever breaks.

---

## 10. `litellm` left in venv but not in dependencies

**Status:** Open (cleanup).

**Fix:** Run `uv remove litellm` to clean the venv.

---

## Live test results (post-fix)

Run on 2026-03-01 with `opencode-anthropic-fast` and `opencode-openai-fast`, max_rounds=2:

| Metric | Result |
|--------|--------|
| Tests passed | 18/18 |
| Runtime | 6m 28s |
| Anthropic seed score | 6.5 |
| OpenAI seed score | 6.5 |
| Judge JSON parsed | Yes (both agents) |
| Individual judge scores | OpenAI judging Anthropic: 5.4, Anthropic judging OpenAI: 7.6 |
| Final report | 888 words, on topic |

**Remaining issue:** GEPA rejected all improved candidates because new scores equaled old scores (6.5 == 6.5). The optimizer correctly preserved the seed when no improvement was detected. This is expected behavior but may indicate the evaluator needs finer-grained scoring, or `max_rounds` should be increased to give agents more attempts.

---

## Priority order (updated)

| # | Issue | Status | Impact |
|---|-------|--------|--------|
| 1 | Score parsing | FIXED | Was blocking all optimization |
| 2 | Judge prompt | FIXED | Was causing issue 1 |
| 3 | Empty feedback | FIXED | Was degrading improvement quality |
| 4 | No logging | FIXED | Debugging was blind |
| 5 | File normalization | FIXED | Could crash pipeline |
| 6 | No-improvement warning | FIXED | User-facing quality |
| 7 | Thread safety | Audited, OK | Preventive |
| 8 | 0.0 scores in synthesis | FIXED | Was misleading synthesizer |
| 9 | Council live tests | Open | Unknown breakage |
| 10 | Stale litellm | Open | Cleanup |
