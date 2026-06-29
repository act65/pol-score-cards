# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_3mo.jsonl`  (since 2026-03-01)

- windows processed: **75**
- scored (attribute, statement) pairs: **7,133**
- distinct statements: **3,358**
- roster MPs with ≥1 score: **119/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 165 | 0.64 | 0 0 1 6 18 15 42 56 25 2 |
| charisma | 495 | 0.52 | 0 17 40 68 74 70 101 79 45 1 |
| civility | 1095 | 0.50 | 8 51 96 198 216 154 77 80 161 54 |
| divination | 157 | 0.50 | 0 0 4 11 48 58 23 11 1 1 |
| forthrightness | 803 | 0.48 | 6 72 128 113 108 77 55 92 124 28 |
| rigor | 1153 | 0.54 | 0 15 50 154 181 199 292 209 53 0 |
| specificity | 1673 | 0.64 | 1 37 63 62 113 237 313 370 386 91 |
| strength | 329 | 0.56 | 0 1 3 10 45 110 109 41 10 0 |
| veracity | 1263 | 0.62 | 0 0 13 44 111 270 345 269 192 19 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Nicola Willis | National | 494 | 25,125 | 0.50 | 0.67 |
| Christopher Luxon | National | 412 | 23,332 | 0.43 | 0.54 |
| David Seymour | ACT | 375 | 26,537 | 0.32 | 0.56 |
| Chris Bishop | National | 287 | 24,683 | 0.40 | 0.63 |
| Simeon Brown | National | 225 | 20,144 | 0.47 | 0.61 |
| Louise Upston | National | 220 | 16,019 | 0.52 | 0.63 |
| Tama Potaka | National | 186 | 11,118 | 0.46 | 0.64 |
| Duncan Webb | Labour | 147 | 23,441 | 0.59 | 0.61 |
| Erica Stanford | National | 145 | 9,848 | 0.51 | 0.62 |
| Paul Goldsmith | National | 140 | 8,511 | 0.49 | 0.65 |
| Shane Jones | NZ First | 137 | 8,015 | 0.31 | 0.50 |
| Simon Watts | National | 132 | 5,115 | 0.40 | 0.60 |
| Winston Peters | NZ First | 127 | 14,278 | 0.32 | 0.54 |
| James Meager | National | 119 | 14,876 | 0.78 | 0.78 |
| Deborah Russell | Labour | 113 | 19,221 | 0.63 | 0.70 |
| Chris Hipkins | Labour | 112 | 10,183 | 0.54 | 0.59 |
| Barbara Edmonds | Labour | 103 | 14,898 | 0.49 | 0.60 |
| Lawrence Xu-Nan | Green | 98 | 0 | 0.86 | 0.65 |
| Chlöe Swarbrick | Green | 95 | 0 | 0.51 | 0.61 |
| Megan Woods | Labour | 94 | 8,072 | 0.62 | 0.65 |
| Andy Foster | NZ First | 92 | 9,667 | 0.60 | 0.76 |
| Dan Bidois | National | 87 | 5,418 | 0.49 | 0.59 |
| Julie Anne Genter | Green | 85 | 7,801 | 0.34 | 0.63 |
| Casey Costello | NZ First | 78 | 7,800 | 0.61 | 0.61 |
| Cushla Tangaere-Manuel | Labour | 76 | 7,048 | 0.63 | 0.66 |

## Roster coverage gaps

MPs with NO scores yet (15/134): Adrian Rurawhe, Barbara Kuriger, Benjamin Doyle, Darleen Tana, David Parker, Gerry Brownlee, Golriz Ghahraman, Grant Robertson, Greg O'Connor, James Shaw, Kelvin Davis, Mark Cameron, Peeni Henare, Takutai Kemp, Tanya Unkovich
