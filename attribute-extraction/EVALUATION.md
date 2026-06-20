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

### Model comparison — can a cheaper model do the scoring?

We score on a Claude Pro subscription via the `claude -p` CLI backend (no API
credits), so it's worth knowing whether a cheaper/faster model is good enough.
`evaluate.py compare` runs the testsets across several models:

```
python evaluate.py compare        # opus-4-8 vs sonnet-4-6 vs haiku-4-5 (~28 calls/model)
```

Prelim run, CLI backend, 2026-06-20 (best `r` first):

| Attribute | Model | n | MAE ↓ | RMSE ↓ | Pearson r ↑ | Binary acc ↑ |
|---|---|---:|---:|---:|---:|---:|
| **civility** | claude-opus-4-8   | 14 | **0.196** | **0.259** | **0.627** | **0.714** |
|              | claude-haiku-4-5  | 14 | 0.250 | 0.286 | 0.433 | 0.571 |
|              | claude-sonnet-4-6 | 14 | 0.275 | 0.315 | 0.186 | 0.643 |
| **veracity** | claude-opus-4-8   | 14 | **0.204** | **0.254** | **0.489** | **0.714** |
|              | claude-sonnet-4-6 | 14 | 0.250 | 0.296 | 0.191 | 0.357 |
|              | claude-haiku-4-5  | 14 | 0.289 | 0.316 | -0.033 | 0.429 |

**Conclusion: keep Opus for scoring — the cheaper models don't hold up.**
`claude-opus-4-8` is best on every metric for both attributes. Dropping to
Sonnet or Haiku roughly halves (or worse) the rank correlation — Sonnet's
civility `r` falls 0.63 → 0.19, and Haiku's veracity `r` collapses to ≈0 (no
better than random ranking). MAE also worsens by 5–9 points on the 0–1 scale.
On a tiny set these are directional, but the gap is large and consistent enough
that downgrading the scorer isn't worth the quality loss.

> **Backend caveat.** This comparison ran through the **CLI** backend (loose
> "return a JSON array" prompting), whereas the headline run above used the
> **Anthropic API** with structured outputs (`messages.parse`). That's why
> Opus's absolute numbers here (civility `r`=0.63) are lower than the API run
> (`r`=0.88): the structured-output harness is stronger. The cross-model
> *ranking* is what's robust — all three models ran through the identical CLI
> harness, so the comparison is apples-to-apples even if the absolute scores
> are pessimistic. For the best absolute quality, score with the API backend.

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
