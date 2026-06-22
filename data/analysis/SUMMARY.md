# Corpus analysis

**4,199 articles** across **5** sources; roster of **123** politicians, **121** mentioned at least once.

Charts: `articles_per_source.png`, `timeline.png`, `top_politicians.png`, `politicians_per_source.png`.

## Articles per source

| Source | Articles | Politicians |
|---|--:|--:|
| newsroom | 2,356 | 117 |
| rnz | 982 | 114 |
| national | 838 | 61 |
| spinoff | 17 | 32 |
| act | 6 | 6 |

## Most-covered politicians

| Politician | Articles | Sources |
|---|--:|--:|
| Christopher Luxon | 906 | 4 |
| Nicola Willis | 624 | 4 |
| Winston Peters | 559 | 4 |
| David Seymour | 503 | 5 |
| Chris Bishop | 485 | 4 |
| Chris Hipkins | 410 | 5 |
| Simeon Brown | 406 | 4 |
| Shane Jones | 385 | 4 |
| Erica Stanford | 276 | 4 |
| Paul Goldsmith | 255 | 4 |
| Simon Watts | 219 | 4 |
| Judith Collins | 208 | 4 |
| Todd McClay | 159 | 4 |
| Louise Upston | 158 | 4 |
| Tama Potaka | 151 | 4 |
| Chlöe Swarbrick | 130 | 4 |
| Shane Reti | 124 | 3 |
| Mark Mitchell | 121 | 3 |
| Brooke van Velden | 110 | 4 |
| Chris Penk | 107 | 3 |

## Source breadth per politician
(how many distinct sources mention each — single-source MPs are the fragile ones)

- mentioned in **1** source(s): 7 politicians
- mentioned in **2** source(s): 47 politicians
- mentioned in **3** source(s): 41 politicians
- mentioned in **4** source(s): 24 politicians
- mentioned in **5** source(s): 2 politicians

## Source-mix for the most-covered MPs
(share of each MP's articles from their own party's press releases vs independent news/Hansard — a high party-release share flatters them)

| Politician | Articles | % party | % news | % Hansard |
|---|--:|--:|--:|--:|
| Christopher Luxon | 906 | 6% | 93% | 0% |
| Nicola Willis | 624 | 19% | 80% | 0% |
| Winston Peters | 559 | 1% | 98% | 0% |
| David Seymour | 503 | 5% | 94% | 0% |
| Chris Bishop | 485 | 28% | 71% | 0% |
| Chris Hipkins | 410 | 3% | 96% | 0% |
| Simeon Brown | 406 | 30% | 69% | 0% |
| Shane Jones | 385 | 5% | 94% | 0% |
| Erica Stanford | 276 | 33% | 66% | 0% |
| Paul Goldsmith | 255 | 20% | 79% | 0% |
| Simon Watts | 219 | 21% | 78% | 0% |
| Judith Collins | 208 | 13% | 86% | 0% |
| Todd McClay | 159 | 45% | 54% | 0% |
| Louise Upston | 158 | 48% | 51% | 0% |
| Tama Potaka | 151 | 27% | 72% | 0% |

## Relevance (articles mentioning no tracked MP)
**785 of 4,199** (19%) mention none of the 123 MPs — drop these before extraction (`filter_corpus.py`).

| Source | Articles | No-MP | ~Tokens |
|---|--:|--:|--:|
| newsroom | 2,356 | 530 | 6,340,383 |
| rnz | 982 | 237 | 1,207,879 |
| national | 838 | 15 | 577,046 |
| spinoff | 17 | 2 | 33,331 |
| act | 6 | 1 | 3,474 |
| **total** | **4,199** | **785** | **8,162,113** |

## Articles per party

| Party | Articles |
|---|--:|
| National | 2,922 |
| NZ First | 925 |
| Labour | 821 |
| ACT | 733 |
| Green | 340 |
| Te Pāti Māori | 133 |

## Coverage gaps — 2 of 123 MPs with zero articles

Jo Luxton, Mike Davidson (politician)
