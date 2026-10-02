# Acuity pilot — 2025-10

260 windows, 9 sitting days, `claude-opus-5` via `claude_cli`, 3.3 h at 2 workers.

    python extract_hansard.py --since 2025-10-01 --until 2025-10 \
        --attrs acuity --window_tokens 3000 --workers 2 \
        --backend claude_cli --out pilot_acuity/acuity_pilot.jsonl
    python pilot_acuity/analyse.py

The `.jsonl` is gitignored — it is an experiment's raw output, regenerable, and
not the published instrument. This file is the record.

## Gates (ATTRIBUTES.md)

| gate | result | |
|---|---|---|
| covered on both benches | 46 government / 44 opposition, 90 MPs | **PASS** |
| max pairwise \|r\| < 0.65 | 0.51 (statement level), 0.48 (MP level) | **PASS** |
| spread > 20 pts | 60 pts | **PASS** |
| shrink > 0.5 | 0.67, at a median of 4 examples per MP | **PASS** |

## Does it measure anything?

454 examples over 186 windows. Mean 56, median 60, and the distribution is
spread rather than bimodal or degenerate:

    0.0:5  0.1:41  0.2:67  0.3:16  0.4:37  0.5:38
    0.6:52 0.7:21  0.8:90  0.9:73  1.0:14

**Signal exceeds noise, which is the thing Divination could not do:**

| | true between-MP sd | sampling noise |
|---|---:|---:|
| Acuity (pilot) | **18.1** | 12.6 |
| Divination (full term) | 5.5–6.2 | 12.8–14.0 |

2.4 examples per window extrapolates to ~13,500 examples over the full term,
about **103 per MP** — comparable to Specificity (108) and eleven times
Divination's nine.

## Did it escape Forthrightness?

Yes, and this was the risk worth checking: if Acuity mostly re-scored ministers'
answers in question time it would have inherited the executive-only coverage it
exists to avoid.

**0 of 454 examples match a Forthrightness answer.** Not a join artifact — there
are 422 Forthrightness rows dated 2025-10 and none matches even on a 60-character
prefix. The 46/44 bench split says the same thing.

## Independence

Statement-level `r` on co-scored statements, and MP-level `r` on per-MP means
(the fallback, because Acuity selects different statements and the co-scored
counts sit near the n>=30 floor):

| vs | statement-level | MP-level |
|---|---:|---:|
| Focus | 0.35 | 0.14 |
| Civility | — (19 co-scored) | −0.02 |
| Rigor | 0.43 | 0.37 |
| Specificity | **0.51** | 0.48 |

Specificity is the closest to the line and the one to watch on a full run.

## Bench × role — a finding, not a bias

The raw government/opposition gap is −11. It decomposes:

| | n | mean |
|---|---:|---:|
| government, role-holder | 13 | 59 |
| **government, backbench** | **27** | **37** |
| opposition, role-holder | 3 | 43 |
| opposition, backbench | 33 | 57 |

Ministers (59) and opposition backbenchers (57) are indistinguishable. The gap is
government backbenchers, who follow a minister with prepared praise that engages
nothing — exactly the case the prompt names as low-scoring.

The opposition role-holder cell is n=3 and means nothing. All of these are at a
median of 4 examples per MP; this table needs the full term before it goes
anywhere public.

## Quality gates in the extractor

459 proposed, 454 kept (99%). Quote fidelity rejected 5 (4 mid-sentence,
1 missing). 129 proposals for attributes that were not requested were dropped by
`--attrs acuity` — the model volunteers other attributes even when only one
rubric is in the system prompt.

## Known defects

1. ~~**Prompt compliance.**~~ FIXED 2026-09-26, in the prompt rather than the
   model. 101 rows carry `responding_to: "nothing: ..."` and averaged 15 against
   a prompt that said 0.0 by definition — but every one of the 101 fell between
   0.0 and 0.3, with none above. The model had been applying a consistent BAND
   all along and the prompt described it as a point, so the prompt was the thing
   that was wrong. It now defines 0.0-0.3 for "engages no part of the argument
   but is at least on the subject", reserves 0.0 for a speech that could have
   been delivered in a different debate on a different day, and states that an
   unpointable statement is never a 0.5 — a glance that engages nothing is not a
   partial engagement, it is prepared material that happens to be on topic.

   The pilot data therefore remains valid: the change codifies the behaviour
   that produced it rather than altering it. `analyse.py` now checks the band
   and reports PASS/FAIL.
2. **The standard overlap audit under-reports.** Acuity selects statements the
   other four mostly do not, so co-scored counts sit at 19–36 and
   `attribute_overlap.py` will print blanks. MP-level correlation has to stand in.
3. **A one-month pilot cannot settle signal-to-noise per MP.** Median n is 4.
   The decomposition above is suggestive, not decisive — which is precisely the
   mistake that made Divination look acceptable at first.

## Status

`WITHHELD` in the registry. It reaches a card only after a full-term run
reproduces these numbers at ~103 examples per MP.

## Full-term run, started 2026-10-02 (unattended)

The pilot's four gates passed, so acuity is being extracted over the whole
54th term: 5,548 windows, ~70 h at the 79 windows/h this pilot measured.
`overnight_run.py --stage acuity` reproduces the command above with
`--since 2023-10-06`, writing to `acuity_scores_v3.jsonl`.

**The 260 pilot windows are NOT reused, and the file is not seeded with them.**
The prompt changed after the pilot: the pilot run had no band for unpointable
speeches, which is what made 101 rows look like prompt non-compliance when they
were in fact the model placing them correctly (commit 6531ead, "The model was
right about acuity's low band; the prompt was not"). Those rows were produced by
a different instrument from the one now in `prompts/acuity.txt`, so 2025-10 is
re-extracted rather than carried over. The cost is 3.3 h of the 70.

**Still withheld.** `attributes.WITHHELD` keeps acuity off the cards. Extraction
is not publication: the open question this run exists to answer is whether the
pilot's numbers hold at full coverage — in particular the ~32 examples/MP figure
(the README's earlier "103 per MP" extrapolated 2.4 examples/window across all
133 MPs without accounting for how unevenly speaking time is distributed), and
whether the −11 government/opposition bench gap still decomposes to government
backbenchers at 37 against ministers 59 and opposition backbenchers 57.

**Marginal cost is not zero.** Acuity is extracted ALONE, not bundled into a
re-run of the other six. Per-attribute yield falls 26–58% as the system prompt
grows, because the example budget per window is fixed and divided between
attributes — measured on the 7-attribute control in `pilot_abstain/README.md`,
where unchanged prompts moved 26–58%. Bundling would have produced a different
instrument for every attribute at once.
