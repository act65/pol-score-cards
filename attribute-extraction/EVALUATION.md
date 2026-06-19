# Attribute Extraction — Evaluation

How we measure whether the LLM scoring is any good, and where the numbers come from.

## What is evaluated

The testsets in `testsets/` split into two tasks:

| Testset | Task | Gold field | Wired into `evaluate.py`? |
|---|---|---|---|
| `civility_testset.jsonl` | score a statement 0..1 | `civility_score` | ✅ |
| `veracity_testset.jsonl` | score a statement 0..1 | `veracity_score` | ✅ |
| `evasion.jsonl` | detect evasion (binary) | `contains_evasion` | ⬜ detection — not yet wired |
| `integrity.jsonl` | detect a factual claim (binary) | `contains_claim` | ⬜ detection — not yet wired |

`evaluate.py` currently covers the **scoring** testsets. Each row is a single,
pre-isolated statement with a human-assigned gold score; the harness calls
`extract.score_statement` with the matching prompt and compares.

## Metrics

For each attribute, over its testset (`n` rows):

- **MAE** — mean absolute error on the 0..1 scale. Interpretable directly: 0.10
  means predictions are off by 0.1 on average.
- **RMSE** — penalises large misses more than MAE.
- **Pearson r** — linear agreement between predicted and gold scores. This is
  the headline number: it tells you whether the model *ranks* statements the way
  the rubric does, even if it's systematically high or low.
- **Binary accuracy** — agreement after thresholding both at 0.5 ("acceptable"
  vs "not"). A coarse but intuitive pass/fail view.

The metric functions are pure Python and unit-tested offline in
`test_evaluate.py` (`pytest test_evaluate.py`) — no API key needed to trust the
arithmetic.

## Running it

```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python evaluate.py run all            # writes eval_report.json
python evaluate.py run civility       # single attribute
python evaluate.py run veracity --model claude-haiku-4-5   # cheaper model
```

`eval_report.json` contains per-attribute metrics plus per-statement
predicted/gold/error/explanation so you can eyeball the worst misses.

## Results

Live run, `claude-opus-4-8`, 2025-06-19 (`python evaluate.py run all`):

```
  civility       n=14  MAE=0.129  RMSE=0.175  r=0.882  binacc=0.857
  veracity       n=14  MAE=0.139  RMSE=0.199  r=0.734  binacc=0.786
```

**Reading it:** On these (small) held-out sets, the model ranks statements much
the way the human rubric does — civility correlation 0.88 is strong, veracity
0.73 is good. Average error is ~0.13 on the 0–1 scale, and binary "acceptable vs
not" agreement is 0.86 / 0.79.

**The instructive miss confirms the trust caveat.** The single largest veracity
error (0.5) was the claim *"My opponent voted against clean water initiatives 17
times"*: gold = 0.0 (false), model = 0.5. The model correctly reasoned it
*couldn't verify the voting record* and hedged to the middle — exactly the
behaviour the README's trust table predicts for veracity (LLM identifies the
claim; a fact-checking step must score it). Civility/specificity, which are
judgeable from the text alone, score higher and more reliably. Full
per-statement predictions and explanations are in `eval_report.json`.

### Methodology caveats (important for interpreting results)

- **Tiny testsets (n≈14).** These numbers are directional, not statistically
  robust. Treat a high `r` as "promising", not "validated". Grow the testsets
  before drawing strong conclusions.
- **Trust varies by attribute.** Per `README.md`, civility/specificity/
  forthrightness are plausibly LLM-scorable end-to-end; veracity/strength/
  divination need external verification, so a good `r` on the veracity testset
  reflects the model judging *plausibility*, not ground-truth fact-checking.
- **Prompt/testset leakage.** Several prompts embed few-shot examples. Keep
  those examples disjoint from the testsets, or the scores are inflated. This is
  tracked as a known cleanup task (see the prompt-improvement work).
