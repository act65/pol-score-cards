# Calibration pilot — 2025-10

**Verdict: all four gates pass. Not yet published.**

Calibration asks one question — *is the speaker as certain as this kind of claim
allows?* — which makes the measurement relative to the **claim**, not to the
confidence. The model assigns an epistemic class *before* it looks at posture,
and available certainty differs by class, so the same flat assertion is 1.0 on
one class and 0.1 on another.

## Reproduce

```bash
cd attribute-extraction
CLAUDE_CLI_USAGE_LOG=$PWD/usage_v3.jsonl CLAUDE_CLI_SYSTEM_FLAG=1 \
CLAUDE_CLI_BUDGET=$PWD/quota_budget.json \
nohup python extract_hansard.py --since 2025-10-01 --until 2025-10 \
  --attrs calibration --window_tokens 3000 --workers 2 --timeout 900 \
  --backend claude_cli --model claude-opus-5 \
  --out pilot_calibration/calibration_pilot.jsonl \
  > pilot_calibration/pilot.log 2>&1 &

python pilot_calibration/analyse.py      # gates + the two failure-mode checks
```

260 windows, 2,517 examples, 99.4% of proposals kept by the quote gate, 2h44m.

## Results

| `claim_class` | n | mean |
|---|---|---|
| `settled_fact` | 620 | 87.8 |
| `value` | 508 | 70.5 |
| `contested_empirical` | 797 | 45.4 |
| `forecast` | 493 | 46.3 |

| gate | pilot | threshold |
|---|---|---|
| Bench coverage | govt 53 / opp 45 | both |
| Spread | 58 pts (30–88) | > 20 |
| Shrink | 0.60 | > 0.5 |
| Max pairwise r | 0.54 (Focus) | < 0.65 |
| Bench gap | −1 | small |

Shrink 0.60 is a small-sample floor: noise 7.5 at 16 examples/MP, projecting to
~0.97 at the full term's ~341/MP. See `ATTRIBUTES.md` for the full decision
including the two failure-mode checks and the `claim_class` enum fix.

## Planning figures — use these, not the pilot's rate guesses

| | measured |
|---|---|
| Density | **9.68 examples/window** (Acuity: 1.75) |
| Cost | **$0.443/call** (Acuity: $0.295) |
| Throughput | **95 windows/h** (Acuity: 195–320) |
| **Full term (5,548 windows)** | **~58 h, ~$2,458** |

Density drives all three: Calibration has no scarce precondition, so nearly
every assertion yields a row, and the output tokens per call are 2–3× Acuity's.

**Run it alone, into its own file**, for the same two reasons as Acuity — resume
reads window ids from `--out`, so pointing it at `hansard_scores_v3.jsonl` finds
every window already done and extracts nothing while reporting success; and
per-attribute yield falls as the system prompt grows, so a bundled run measures a
different instrument from the one this pilot validated.

## Note on the pilot's own data

This pilot predates the `claim_class` / `confidence_markers` split, so its rows
carry `"settled_fact; 'I believe'"` in one field. `analyse.py::_cls` splits on
the semicolon so the pilot stays comparable with later runs.

## Full-term run, paused at 70.4% (12 October 2026)

Paused at the user's request to leave the rest of the week's subscription window
for interactive use. Not a fault: 41.2 h unbroken, 95 calls/h, no subscription
interruption at any point.

| | at the pause |
|---|---|
| Windows | **3,905 / 5,548 (70.4%)** |
| Examples | 30,280 at **7.75/window** |
| Usage | $1,511 list-price at $0.386/call |
| Corpus reached | 2023-12-05 → **2025-08-14** |
| Remaining | 1,643 windows ≈ 17 h, ~$636 |

### Resume

```bash
systemctl --user enable --now nz-scorecards-away
```

Nothing else to set up. Resume is by `window_id` read from
`calibration_scores_v3.jsonl`, verified at the pause — all 3,905 completed
windows are skipped. The unit's deadline was moved to 2026-10-26 when pausing,
because a deadline in the past makes `burst` exit `EX_FAIL` immediately and
`RestartPreventExitStatus=1` then refuses to retry.

### Do not aggregate the partial file

The corpus is processed in **date order**, so the pause leaves everything from
2025-08-14 onward unscored — the last ~15 months of the term. Coverage is
complete for every MP up to that date and absent after it, which is a **period
bias, not a sample**: it would score each MP only on the term's first 20 months
and silently omit the election run-up. This is the same trap `stratify()` was
built to avoid for the veracity resolver, where a fixed-seed shuffle makes every
prefix unbiased. The window extractor has no such shuffle, by design — resume
and audit both want date order — so the rule is simply that the file is not
publishable until it is complete.

### The instrument at 3,905 windows

| gate | pilot (260 w) | 2,610 w | **3,905 w** | threshold |
|---|---|---|---|---|
| MPs (≥20 ex) | 99 @ 16 ex | 124 @ 142 | **128 @ 196** | both benches ✓ |
| Shrink | 0.60 | 0.88 | **0.91** | > 0.5 ✓ |
| Spread | 58 | 34 | **43** | > 20 ✓ |
| Bench gap | −1 | −2.5 | **−3.1** | small ✓ |
| `settled_fact` leakage | n/a | 0 | **0 of 30,280** | 0 |
| Fused class labels | 3.9% | 0 | **0 of 30,280** | 0 |

Shrink rose 0.60 → 0.91 exactly as the small-sample argument predicted (noise
7.5 → 2.2), which is the opposite of Divination, where more data drove shrink
*down* (0.09 → 0.03). Spread fell from the pilot's 58 and is now recovering
(34 → 43) as every MP accumulates enough examples for their mean to settle;
the pilot's extremes were MPs with a dozen rows each.

Both filters added on 2026-10-10 are perfectly compliant at 116× the pilot's
volume: zero `settled_fact` rows and zero fused class labels in 30,280 examples.
