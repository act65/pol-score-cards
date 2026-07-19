# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_full.jsonl`  (since 2026-03-01)

- windows processed: **744**
- scored (attribute, statement) pairs: **65,079**
- distinct statements: **31,322**
- roster MPs with ≥1 score: **134/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 1817 | 0.64 | 0 0 13 82 155 226 440 525 346 30 |
| charisma | 5045 | 0.54 | 5 214 479 639 509 630 902 915 710 42 |
| civility | 10061 | 0.51 | 52 480 974 1651 1890 1458 668 625 1499 764 |
| divination | 1637 | 0.50 | 0 5 10 104 481 706 254 57 17 3 |
| forthrightness | 5198 | 0.48 | 41 487 808 785 599 582 417 618 668 193 |
| rigor | 10778 | 0.53 | 3 215 690 1511 1557 1855 2367 1967 611 2 |
| specificity | 14833 | 0.65 | 9 410 545 576 770 1656 2754 3560 3594 959 |
| strength | 2772 | 0.55 | 0 7 17 171 445 862 831 356 83 0 |
| veracity | 12938 | 0.65 | 1 26 128 401 900 2114 2907 3213 2640 608 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Christopher Luxon | National | 3217 | 23,332 | 0.39 | 0.58 |
| Nicola Willis | National | 3143 | 25,125 | 0.42 | 0.69 |
| Chris Bishop | National | 2357 | 24,683 | 0.51 | 0.68 |
| David Seymour | ACT | 1871 | 26,537 | 0.36 | 0.60 |
| Simeon Brown | National | 1697 | 20,144 | 0.43 | 0.63 |
| Winston Peters | NZ First | 1653 | 14,278 | 0.30 | 0.55 |
| Erica Stanford | National | 1338 | 9,848 | 0.52 | 0.67 |
| Duncan Webb | Labour | 1333 | 23,441 | 0.59 | 0.69 |
| Louise Upston | National | 1304 | 16,019 | 0.51 | 0.64 |
| Paul Goldsmith | National | 1185 | 8,511 | 0.58 | 0.69 |
| Ginny Andersen | Labour | 1000 | 8,383 | 0.52 | 0.64 |
| Chris Hipkins | Labour | 999 | 10,183 | 0.50 | 0.62 |
| Andy Foster | NZ First | 915 | 9,667 | 0.67 | 0.70 |
| Julie Anne Genter | Green | 911 | 7,801 | 0.41 | 0.64 |
| Shane Jones | NZ First | 909 | 8,015 | 0.29 | 0.51 |
| Simon Watts | National | 854 | 5,115 | 0.51 | 0.66 |
| Deborah Russell | Labour | 845 | 19,221 | 0.64 | 0.69 |
| Tama Potaka | National | 814 | 11,118 | 0.51 | 0.66 |
| Chlöe Swarbrick | Green | 804 | 0 | 0.52 | 0.66 |
| Lawrence Xu-Nan | Green | 720 | 0 | 0.73 | 0.68 |
| Kieran McAnulty | Labour | 712 | 4,536 | 0.50 | 0.63 |
| Barbara Edmonds | Labour | 700 | 14,898 | 0.55 | 0.64 |
| Megan Woods | Labour | 693 | 8,072 | 0.54 | 0.66 |
| Willie Jackson | Labour | 692 | 17,855 | 0.41 | 0.59 |
| Arena Williams | Labour | 680 | 4,043 | 0.64 | 0.65 |

## Roster coverage gaps

MPs with NO scores yet (0/134): 

### Unresolved speakers (likely roster gaps — add to mps_roster.json)

Names with scored statements that don't map to the 123-MP roster — mostly mid-term replacement MPs or departed members:

- Jim Bolger: 3 statements
- Bill English: 1 statements
