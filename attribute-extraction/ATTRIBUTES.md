
## Decision 2026-10-02 — Veracity's queue is not full of junk, so narrowing the prompt is the wrong tool

The goal was to tighten Veracity so the resolver faces a manageable number of
claims: 25,747 extracted, 25,486 unresolved, which at the measured 58
verdicts/h is **444 hours**. The intended mechanism was a prompt gate on
structural anchors (a figure, a date, a named source, a comparison) — the
rewrite of the uncredited abstain rule recorded on 2026-09-27.

**Measured first, on the 276 veracity claims already resolved. The premise is
false: 97% of them came back usable** — 170 `true`, 82 `partly_true`, 15
`false`, and only **9 `uncheckable`**. There is no unresolvable chaff to filter
out, so there is nothing for a checkability gate to catch.

No structural gate beats that base rate:

| gate | claims kept | usable verdict | vs 97% base |
|---|---:|---:|---:|
| figure | 164 | 96% | −1.0 |
| source | 18 | 100% | +3.3 |
| compare | 54 | 94% | −2.3 |
| figure AND compare | 30 | 93% | −3.4 |
| figure AND (year OR source) | 36 | 100% | +3.3 |

The two gates that reach 100% do so on n=18 and n=36, for +3.3 points over a
97% base. Meanwhile the tight gate would discard **239 of 276 (87%)** claims
that *did* resolve usefully.

So a prompt gate cuts volume without improving verifiability. It is a sampling
decision wearing a quality filter's clothes — and an expensive one: it needs a
fresh 5,548-window extraction (~$1,640, 18–28 h) and yields a subset whose
composition nobody chose.

**Resolved instead by sampling what is already on disk.** `resolve.stratify()`
caps claims per politician and draws them at an even stride through the term.
The median MP has 160 veracity claims and 113 of 138 have at least 56, so:

| cap per MP | claims | resolver hours |
|---:|---:|---:|
| 10 | 1,349 | 23 |
| 20 | 2,658 | 46 |
| 30 | 3,924 | 68 |
| 56 | 6,992 | 121 |

against 444 h unstratified. The even stride matters as much as the cap: taking
each MP's *first* n claims would rebuild the time bias inside every MP, which
is the bias that got `resolve_veracity` pulled on 2026-09-08 (371 of 389
resolved claims from one month out of seven).

**What this does NOT settle.** The abstain rule now in `prompts/veracity.txt`
is untested against real output — the 25,747 claims on disk were all extracted
before it landed, so it affects only future extraction (the June-to-election
Hansard, once scraped). Narrowing Veracity may still be worth doing there on a
different argument: at 4.6 claims/window it consumes 31% of the whole
extraction's output budget. That is a cost-of-extraction case, not a
quality-of-claims case, and it should be argued on its own evidence.
