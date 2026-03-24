# ENGRAM Scorer Rubric — Coding Module
# v1 — do not edit manually, evolved by evolve_rubric()
# Trigger: every 50 tasks

Score the RESPONSE to the TASK on 0.0–1.0.

## Dimensions (weight equally)
1. Task completion — every part of the task addressed?
2. Correctness — code is syntactically valid and logically sound?
3. No hallucination — no invented file paths, APIs, or functions?
4. Writeback block — ends with a valid ```writeback block?

## Penalty conditions (apply each that matches, -0.20 per)
- Claimed to modify a file but did not call write_file
- Described changes without implementing them
- Tests were requested but not written or run
- Invented a file path that does not exist in the project

## Reward condition (+0.10, cap at 1.0)
- All requested tests pass with 0 failures (confirmed via stdout)

## Floor rules (override score if condition met)
- If execution score is 1.0 (all tests pass): minimum score 0.80
- If execution score is 0.0 (tests failed): maximum score 0.45

Return ONLY valid JSON, no prose, no markdown fences:
{"score": 0.0, "reasons": ["reason1", "reason2"]}
score must be float 0.0–1.0. reasons must be list of 1–3 strings.
