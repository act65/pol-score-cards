# Guess vs search

Does searching for evidence beat the model's unaided guess? The guess (`prior_score`) was written at extraction time, before any lookup, and was withheld from the resolver — so these are independent.

18 verdicts; 17 have both a guess and a resolved score.

## Verdicts

| verdict | n | share |
|---|---:|---:|
| true | 11 | 61% |
| partly_true | 3 | 17% |
| wrong | 2 | 11% |
| uncheckable | 1 | 6% |
| partly_correct | 1 | 6% |

**6% returned no score** (`uncheckable` / `not_yet_due`). That is a real answer, not a failure — but it is also the share of claims where searching bought nothing.

## Agreement

| metric | value |
|---|---:|
| Pearson r (guess vs searched) | 0.78 |
| mean absolute gap | 0.182 |
| median absolute gap | 0.150 |
| agree within 0.25 | 82% |
| disagree by >= 0.5 | 1 of 17 |

**How to read this.** A high `r` with a small gap means the guess already tracks the evidence, and the search is an expensive way to confirm what the model knew. A low `r`, or a handful of large flips, means the guess is confidently wrong somewhere — which is exactly the failure mode the site cannot afford, and justifies the cost.

### Where the guess was confidently wrong

- **divination** / Nicola Willis — guessed 0.60, resolved 0.00 (`wrong`)
  > Now, there are clear indications that the economy has turned upwards, but even so, I would expect the unemployment rate to rise a bit further before beginning to fall.
  source: https://www.stats.govt.nz/news/unemployment-rate-at-5-3-percent-in-the-september-2025-quarter/

## Sourcing

18/18 verdicts cite at least one URL (100%). A resolved score with no source cannot be audited by a reader and should not be published.

