# ENGRAM Scorer Rubric — Marketing Module
# v1 — do not edit manually, evolved by evolve_rubric()
# Trigger: every 50 tasks

Score the RESPONSE to the TASK on 0.0–1.0.

## Dimensions (weight equally)
1. Specificity — concrete outcomes, numbers, named results present?
2. Audience clarity — reader can self-select in or out within first sentence?
3. Format adherence — matches the requested structure exactly?
4. Persuasion logic — follows problem → solution → proof → CTA arc?

## Penalty conditions (apply each that matches, -0.20 per)
- Contains generic filler phrases: "world-class", "cutting-edge",
  "innovative solution", "take it to the next level", "synergy",
  "game-changing", "revolutionary", "best-in-class"
- No specific outcome or proof point anywhere in response
- Requested format not delivered (asked for bullets, got paragraph)
- No call-to-action when task context implies one is needed

## Reward condition (+0.10, cap at 1.0)
- Contains a specific verifiable claim with a number and a timeframe
  (e.g. "reduced churn by 23% in 90 days")

## Proxy signal rules (override score if condition met)
- If specificity_signals == 0: maximum score 0.55
- If generic_phrase_count >= 3: maximum score 0.50
- If audience_named == False and task requests copy: maximum score 0.65

Return ONLY valid JSON, no prose, no markdown fences:
{"score": 0.0, "reasons": ["reason1", "reason2"]}
score must be float 0.0–1.0. reasons must be list of 1–3 strings.
