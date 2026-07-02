# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_full.jsonl`  (since 2026-03-01)

- windows processed: **365**
- scored (attribute, statement) pairs: **30,585**
- distinct statements: **15,026**
- roster MPs with ≥1 score: **132/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 854 | 0.63 | 0 0 10 31 88 105 209 263 140 8 |
| charisma | 2312 | 0.56 | 0 75 178 265 243 303 460 420 348 20 |
| civility | 4673 | 0.51 | 20 213 453 771 933 674 304 297 709 299 |
| divination | 775 | 0.50 | 0 2 7 45 229 323 134 29 5 1 |
| forthrightness | 2696 | 0.46 | 26 293 454 380 307 281 208 306 347 94 |
| rigor | 5154 | 0.53 | 0 87 322 716 753 905 1174 914 281 2 |
| specificity | 7001 | 0.64 | 3 199 276 264 405 840 1343 1608 1657 406 |
| strength | 1282 | 0.54 | 0 6 9 88 245 383 347 162 42 0 |
| veracity | 5838 | 0.65 | 0 7 57 171 429 995 1362 1442 1153 222 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Nicola Willis | National | 1726 | 25,125 | 0.43 | 0.69 |
| Christopher Luxon | National | 1465 | 23,332 | 0.41 | 0.58 |
| Simeon Brown | National | 1065 | 20,144 | 0.41 | 0.63 |
| David Seymour | ACT | 922 | 26,537 | 0.33 | 0.58 |
| Chris Bishop | National | 874 | 24,683 | 0.46 | 0.65 |
| Winston Peters | NZ First | 784 | 14,278 | 0.29 | 0.51 |
| Duncan Webb | Labour | 714 | 23,441 | 0.58 | 0.67 |
| Louise Upston | National | 677 | 16,019 | 0.49 | 0.64 |
| Paul Goldsmith | National | 655 | 8,511 | 0.58 | 0.67 |
| Erica Stanford | National | 508 | 9,848 | 0.55 | 0.66 |
| Ginny Andersen | Labour | 467 | 8,383 | 0.54 | 0.65 |
| Chlöe Swarbrick | Green | 442 | 0 | 0.53 | 0.68 |
| Tama Potaka | National | 434 | 11,118 | 0.47 | 0.66 |
| Deborah Russell | Labour | 434 | 19,221 | 0.66 | 0.70 |
| Simon Watts | National | 411 | 5,115 | 0.50 | 0.67 |
| Chris Hipkins | Labour | 410 | 10,183 | 0.53 | 0.65 |
| Shane Jones | NZ First | 407 | 8,015 | 0.30 | 0.54 |
| Barbara Edmonds | Labour | 398 | 14,898 | 0.58 | 0.64 |
| Andy Foster | NZ First | 397 | 9,667 | 0.64 | 0.68 |
| Julie Anne Genter | Green | 385 | 7,801 | 0.40 | 0.65 |
| Megan Woods | Labour | 381 | 8,072 | 0.57 | 0.65 |
| Willie Jackson | Labour | 353 | 17,855 | 0.39 | 0.57 |
| Lawrence Xu-Nan | Green | 326 | 0 | 0.78 | 0.67 |
| Karen Chhour | ACT | 324 | 2,080 | 0.56 | 0.63 |
| Nicole McKee | ACT | 319 | 1,489 | 0.46 | 0.69 |

## Roster coverage gaps

MPs with NO scores yet (2/134): Barbara Kuriger, Benjamin Doyle
