# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_full.jsonl`  (since 2026-03-01)

- windows processed: **89**
- scored (attribute, statement) pairs: **8,043**
- distinct statements: **3,826**
- roster MPs with ≥1 score: **123/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 195 | 0.63 | 0 0 1 6 22 22 51 63 28 2 |
| charisma | 603 | 0.53 | 0 21 50 76 81 86 128 101 59 1 |
| civility | 1270 | 0.49 | 9 70 119 237 252 170 88 86 182 57 |
| divination | 188 | 0.49 | 0 1 5 14 61 68 25 12 1 1 |
| forthrightness | 833 | 0.48 | 6 79 134 118 111 78 56 95 126 30 |
| rigor | 1291 | 0.52 | 0 19 73 191 214 216 310 215 53 0 |
| specificity | 1842 | 0.63 | 1 46 76 73 132 259 346 398 418 93 |
| strength | 385 | 0.55 | 0 1 4 17 66 118 119 47 13 0 |
| veracity | 1436 | 0.62 | 0 2 18 55 136 304 378 290 223 30 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Nicola Willis | National | 554 | 25,125 | 0.48 | 0.67 |
| Christopher Luxon | National | 466 | 23,332 | 0.42 | 0.55 |
| David Seymour | ACT | 426 | 26,537 | 0.32 | 0.55 |
| Chris Bishop | National | 305 | 24,683 | 0.42 | 0.63 |
| Simeon Brown | National | 236 | 20,144 | 0.45 | 0.60 |
| Louise Upston | National | 220 | 16,019 | 0.52 | 0.63 |
| Tama Potaka | National | 191 | 11,118 | 0.46 | 0.64 |
| Winston Peters | NZ First | 183 | 14,278 | 0.31 | 0.51 |
| Duncan Webb | Labour | 178 | 23,441 | 0.55 | 0.60 |
| Chris Hipkins | Labour | 168 | 10,183 | 0.52 | 0.62 |
| Erica Stanford | National | 168 | 9,848 | 0.47 | 0.62 |
| Paul Goldsmith | National | 154 | 8,511 | 0.54 | 0.66 |
| Shane Jones | NZ First | 150 | 8,015 | 0.31 | 0.49 |
| James Meager | National | 135 | 14,876 | 0.78 | 0.78 |
| Simon Watts | National | 132 | 5,115 | 0.40 | 0.60 |
| Deborah Russell | Labour | 113 | 19,221 | 0.63 | 0.70 |
| Julie Anne Genter | Green | 110 | 7,801 | 0.32 | 0.62 |
| Megan Woods | Labour | 107 | 8,072 | 0.62 | 0.66 |
| Marama Davidson | Green | 106 | 2,833 | 0.47 | 0.66 |
| Barbara Edmonds | Labour | 103 | 14,898 | 0.49 | 0.60 |
| Rawiri Waititi | Te Pāti Māori | 99 | 3,850 | 0.48 | 0.55 |
| Lawrence Xu-Nan | Green | 98 | 0 | 0.86 | 0.65 |
| Chlöe Swarbrick | Green | 96 | 0 | 0.50 | 0.61 |
| Andy Foster | NZ First | 92 | 9,667 | 0.60 | 0.76 |
| Dan Bidois | National | 87 | 5,418 | 0.49 | 0.59 |

## Roster coverage gaps

MPs with NO scores yet (11/134): Adrian Rurawhe, Barbara Kuriger, Benjamin Doyle, Darleen Tana, David Parker, Greg O'Connor, James Shaw, Kelvin Davis, Peeni Henare, Takutai Kemp, Tanya Unkovich
