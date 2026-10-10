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
