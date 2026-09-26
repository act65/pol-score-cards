# Hansard attribute extraction — efficiency plan (v2.0)

v2.0 scores **all current MPs** from **Hansard only**. This is the plan for
running the nine-attribute extraction over the 54th-term Hansard corpus
efficiently and *correctly* (right speaker → right score), and what it will cost.

## The input

`data/corpus/hansard.json` — 54th Parliament (since 2023-10-14):

| | |
|---|---|
| sitting days | 190 (2023-12-05 → 2026-05-28) |
| parts (≈5k-word chunks) | 1,435 |
| raw content tokens (est) | ~10.5M |

(`data/hansard_coverage.py` for the coverage report; `hansard_prep.py measure`
for the token breakdown.)

## Two problems the raw corpus has

1. **Attribution.** Parts are arbitrary character-chunks, so a chunk often opens
   mid-speech with the `Hon NAME:` tag stranded in the previous chunk. If the LLM
   guesses the speaker, scores land on the wrong MP — unacceptable for a public
   scorecard. (~8% of content is such orphaned openers.)
2. **Token waste.** ~13% of the transcript is procedural (the Speaker, the Clerk,
   division bells, "the question is that…") with no scoreable MP conduct.

## The pipeline (`hansard_prep.py` → `extract_hansard.py`)

```
corpus/hansard.json
  → group by sitting day
  → prep_day(): re-segment into speaker turns (NZ Hansard tag formats),
                drop procedural/Chair turns, carry the speaker across part
                boundaries to rescue orphaned openers, merge consecutive
                same-speaker turns  → attributed member-speech blocks
  → re-batch blocks into ~6k-token windows, each block prefixed "SPEAKER: …"
  → extract_all_attributes(): ONE cached call per window scores all 9 attributes
  → append to JSONL, resumable (skips windows already written)
```

After prep: **8.6M tokens kept as 22k attributed blocks across ~190 speakers**
(82% of raw; 18% procedural/chrome dropped). Every block carries a known speaker,
so the model *scores* rather than *guesses who spoke*.

## Token-reduction levers (measured, not assumed)

| Lever | Effect | Status |
|---|---|---|
| **Combined call** (all 9 attrs, text sent once not 9×) | ~9× fewer input tokens | already in `extract_all_attributes` |
| **Speaker-prep** (drop procedural, fix attribution) | −18% content, correct attribution | `hansard_prep.py` (new) |
| **Prompt caching** on the shared 9-rubric system prompt | system prompt ~free after call 1 (~$72 of $210 input on the full Opus run) | enabled in `extract.py` (new) |
| **Condensed prompts** (strip few-shot blocks) | smaller system prompt | already in `_condense_prompt` |
| **Model tier** (Opus → Sonnet → Haiku) | the biggest $ dial (~5–20×) | **needs an accuracy/cost bake-off first** |
| **Shorter explanations** (output tokens) | output is ~⅓ of the Opus cost | tunable via prompt |

## Full-run cost estimate (`extract_hansard.py --dry_run`)

190 days → **1,707 windows (API calls)**, **8.7M content input tokens**,
~1.5M output tokens (est. ~900/window).

At *placeholder* Opus list rates (in $15 / out $75 / cache-read $1.5 per Mtok):

| | $ |
|---|---|
| input (caching ON) | ~139 |
| input (no caching) | ~210 (caching saves ~$72) |
| output | ~115 |
| **total (Opus)** | **~254** |

⚠️ Rates are placeholders — set `--in_rate/--out_rate` to current pricing.
Sonnet/Haiku would be materially cheaper (the model dial dwarfs everything else).

## Two ways to pay

- **`--backend claude_cli`** — runs on the local Claude subscription, **no API
  credits** (respects the quota constraint). Cost is quota/wall-clock, not $.
- **`--backend anthropic`** — API credits, with caching as above.

## Recommended gate before the full run (task 1c)

1. **Model bake-off**: score the existing `civility`/`veracity` testsets with
   Opus vs Sonnet vs Haiku (`evaluate.py`), pick the cheapest model that holds
   accuracy. (Track B already wants this.)
2. **Pilot one sitting day** (~8–12 windows) end-to-end: verify attribution maps
   to the roster, sanity-check scores, measure *real* output token size (the
   ~900/window assumption).
3. Then run the full 190 days (resumable) on the chosen model/backend.
