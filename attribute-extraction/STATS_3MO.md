# Extracted Hansard dataset — statistics

Source scores: `hansard_scores_3mo.jsonl`  (since 2026-03-01)

- windows processed: **27**
- scored (attribute, statement) pairs: **2,448**
- distinct statements: **1,133**
- roster MPs with ≥1 score: **89/134**

## Per attribute

| attribute | n | mean | histogram 0.0→1.0 |
|---|---:|---:|---|
| authenticity | 63 | 0.64 | 0 0 0 4 5 5 20 17 11 1 |
| charisma | 175 | 0.52 | 0 9 19 17 26 22 29 34 19 0 |
| civility | 360 | 0.51 | 7 20 42 56 54 48 27 18 67 21 |
| divination | 52 | 0.51 | 0 0 2 0 17 17 10 5 0 1 |
| forthrightness | 249 | 0.48 | 1 31 29 38 29 24 22 30 41 4 |
| rigor | 393 | 0.56 | 0 7 21 35 51 70 98 80 31 0 |
| specificity | 574 | 0.64 | 0 23 11 19 40 68 117 143 130 23 |
| strength | 105 | 0.55 | 0 0 3 3 15 44 30 6 4 0 |
| veracity | 477 | 0.64 | 0 0 8 19 34 85 118 116 86 11 |

## Top politicians by statements scored

| MP | party | statements | words spoken | mean civility | mean veracity |
|---|---|---:|---:|---:|---:|
| Nicola Willis | National | 190 | 25,125 | 0.54 | 0.69 |
| Christopher Luxon | National | 158 | 23,332 | 0.50 | 0.57 |
| David Seymour | ACT | 114 | 26,537 | 0.31 | 0.60 |
| Louise Upston | National | 78 | 16,019 | 0.57 | 0.63 |
| Duncan Webb | Labour | 69 | 23,441 | 0.57 | 0.53 |
| James Meager | National | 67 | 14,876 | 0.86 | 0.79 |
| Megan Woods | Labour | 66 | 8,072 | 0.59 | 0.66 |
| Tama Potaka | National | 63 | 11,118 | 0.53 | 0.64 |
| Simon Watts | National | 57 | 5,115 | 0.37 | 0.54 |
| Francisco Hernandez | Green | 53 | 3,195 | 0.41 | 0.63 |
| Chris Bishop | National | 52 | 24,683 | 0.44 | 0.68 |
| Shane Jones | NZ First | 52 | 8,015 | 0.28 | 0.47 |
| Simeon Brown | National | 50 | 20,144 | 0.68 | 0.70 |
| Cushla Tangaere-Manuel | Labour | 49 | 7,048 | 0.62 | 0.65 |
| Deborah Russell | Labour | 49 | 19,221 | 0.57 | 0.73 |
| Cameron Brewer | National | 47 | 3,951 | 0.41 | 0.62 |
| Chris Hipkins | Labour | 46 | 10,183 | 0.74 | 0.70 |
| Andy Foster | NZ First | 43 | 9,667 | 0.45 | 0.75 |
| Tamatha Paul | Green | 40 | 4,291 | 0.29 | 0.56 |
| Ricardo Menéndez March | Green | 38 | 0 | 0.38 | 0.71 |
| Winston Peters | NZ First | 37 | 14,278 | 0.29 | 0.53 |
| Judith Collins | National | 36 | 2,640 | 0.42 | 0.57 |
| Dan Bidois | National | 35 | 5,418 | 0.45 | 0.62 |
| Julie Anne Genter | Green | 35 | 7,801 | 0.22 | 0.68 |
| Barbara Edmonds | Labour | 33 | 14,898 | 0.58 | 0.69 |

## Roster coverage gaps

MPs with NO scores yet (45/134): Adrian Rurawhe, Andrew Bayly, Andrew Hoggard, Arena Williams, Ayesha Verrall, Barbara Kuriger, Benjamin Doyle, Catherine Wedd, Damien O'Connor, Dana Kirkpatrick, Darleen Tana, David Parker, Debbie Ngarewa-Packer, Georgie Dansey, Gerry Brownlee, Glen Bennett, Golriz Ghahraman, Grant McCallum, Grant Robertson, Greg Fleming, Greg O'Connor, Hana-Rawhiti Maipi-Clarke, Hūhana Lyndon, James Shaw, Jenny Marcroft, Joseph Mooney, Kelvin Davis, Lan Pham, Lemauga Lydia Sosene, Mariameno Kapa-Kingi, Mark Cameron, Mark Patterson, Maureen Pugh, Melissa Lee, Miles Anderson, Paulo Garcia, Peeni Henare, Priyanca Radhakrishnan, Rachel Boyack, Sam Uffindell …
