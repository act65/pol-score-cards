# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_full.jsonl`  (since 2026-03-01)

- windows processed: **566**
- scored (attribute, statement) pairs: **47,344**
- distinct statements: **23,322**
- roster MPs with ≥1 score: **133/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 1334 | 0.63 | 0 0 13 60 115 182 334 390 227 13 |
| charisma | 3687 | 0.54 | 2 138 327 467 397 478 684 645 516 33 |
| civility | 7270 | 0.50 | 31 338 721 1240 1421 1077 497 451 1064 430 |
| divination | 1237 | 0.50 | 0 4 9 82 362 535 193 43 8 1 |
| forthrightness | 3820 | 0.47 | 34 381 610 586 451 416 300 437 471 134 |
| rigor | 7869 | 0.53 | 1 132 497 1099 1161 1396 1781 1392 408 2 |
| specificity | 10848 | 0.65 | 3 300 416 414 574 1274 2112 2574 2525 656 |
| strength | 2025 | 0.55 | 0 6 13 126 361 611 591 260 57 0 |
| veracity | 9254 | 0.65 | 1 14 93 285 655 1557 2156 2321 1810 362 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Nicola Willis | National | 2433 | 25,125 | 0.43 | 0.69 |
| Christopher Luxon | National | 2311 | 23,332 | 0.40 | 0.58 |
| Chris Bishop | National | 1428 | 24,683 | 0.48 | 0.67 |
| Simeon Brown | National | 1335 | 20,144 | 0.42 | 0.64 |
| Winston Peters | NZ First | 1288 | 14,278 | 0.31 | 0.53 |
| David Seymour | ACT | 1251 | 26,537 | 0.34 | 0.59 |
| Louise Upston | National | 961 | 16,019 | 0.50 | 0.64 |
| Duncan Webb | Labour | 952 | 23,441 | 0.57 | 0.66 |
| Paul Goldsmith | National | 926 | 8,511 | 0.58 | 0.68 |
| Erica Stanford | National | 885 | 9,848 | 0.52 | 0.66 |
| Chris Hipkins | Labour | 765 | 10,183 | 0.50 | 0.62 |
| Ginny Andersen | Labour | 726 | 8,383 | 0.52 | 0.63 |
| Tama Potaka | National | 671 | 11,118 | 0.49 | 0.67 |
| Shane Jones | NZ First | 658 | 8,015 | 0.29 | 0.53 |
| Chlöe Swarbrick | Green | 658 | 0 | 0.53 | 0.67 |
| Deborah Russell | Labour | 626 | 19,221 | 0.63 | 0.69 |
| Julie Anne Genter | Green | 604 | 7,801 | 0.40 | 0.64 |
| Simon Watts | National | 602 | 5,115 | 0.51 | 0.67 |
| Willie Jackson | Labour | 571 | 17,855 | 0.39 | 0.58 |
| Andy Foster | NZ First | 565 | 9,667 | 0.67 | 0.69 |
| Barbara Edmonds | Labour | 551 | 14,898 | 0.55 | 0.64 |
| Casey Costello | NZ First | 529 | 7,800 | 0.60 | 0.63 |
| Cameron Brewer | National | 514 | 3,951 | 0.43 | 0.69 |
| Megan Woods | Labour | 508 | 8,072 | 0.55 | 0.64 |
| Nicole McKee | ACT | 507 | 1,489 | 0.43 | 0.68 |

## Roster coverage gaps

MPs with NO scores yet (1/134): Barbara Kuriger

### Unresolved speakers (likely roster gaps — add to mps_roster.json)

Names with scored statements that don't map to the 123-MP roster — mostly mid-term replacement MPs or departed members:

- Bill English: 1 statements
