# Guess vs search

Does searching for evidence beat the model's unaided guess? The guess (`prior_score`) was written at extraction time, before any lookup, and was withheld from the resolver — so these are independent.

389 verdicts; 312 have both a guess and a resolved score.

## Verdicts

| verdict | n | share |
|---|---:|---:|
| true | 170 | 44% |
| partly_true | 82 | 21% |
| not_yet_due | 68 | 17% |
| correct | 24 | 6% |
| false | 16 | 4% |
| wrong | 12 | 3% |
| uncheckable | 9 | 2% |
| partly_correct | 8 | 2% |

**20% returned no score** (`uncheckable` / `not_yet_due`). That is a real answer, not a failure — but it is also the share of claims where searching bought nothing.

## Agreement

| metric | value |
|---|---:|
| Pearson r (guess vs searched) | 0.64 |
| mean absolute gap | 0.220 |
| median absolute gap | 0.200 |
| agree within 0.25 | 69% |
| disagree by >= 0.5 | 19 of 312 |

**How to read this.** A high `r` with a small gap means the guess already tracks the evidence, and the search is an expensive way to confirm what the model knew. A low `r`, or a handful of large flips, means the guess is confidently wrong somewhere — which is exactly the failure mode the site cannot afford, and justifies the cost.

### Where the guess was confidently wrong

- **divination** / Nicola Willis — guessed 0.60, resolved 0.00 (`wrong`)
  > Now, there are clear indications that the economy has turned upwards, but even so, I would expect the unemployment rate to rise a bit further before beginning to fall.
  source: https://www.stats.govt.nz/news/unemployment-rate-at-5-3-percent-in-the-september-2025-quarter/
- **divination** / Rachel Boyack — guessed 0.50, resolved 0.00 (`wrong`)
  > The Animal Law Association, who won a court case, and given that the Minister’s allowing this to run till February—we’ve got between December and February for another court case.
  source: https://www.rnz.co.nz/news/political/581566/government-s-pig-farming-law-changes-passed-through-parliament-under-urgency
- **divination** / Francisco Hernandez — guessed 0.50, resolved 1.00 (`correct`)
  > I’m not able to discuss it because it’s still in the middle of a media pitch, but when it does come out, it will reveal that, actually, this thing is not that financially viable.
  source: https://www.treasury.govt.nz/sites/default/files/2025-10/oia-20250592.pdf
- **divination** / Paul Goldsmith — guessed 0.50, resolved 1.00 (`correct`)
  > There are several cases that have been heard that will have to be re-heard in light of this legislation if it passes.
  source: https://www.teaonews.co.nz/2026/03/04/high-court-reaffirms-customary-marine-title-for-ruapuke-island-under-tougher-law/
- **divination** / Deborah Russell — guessed 0.70, resolved 0.00 (`wrong`)
  > There is better legislation coming. The Minister of Commerce and Consumer Affairs has assured me that he’s working on his Companies Amendment Bill and that he anticipates having it
  source: https://disclosure.legislation.govt.nz/bill/government
- **divination** / Louise Upston — guessed 0.50, resolved 1.00 (`correct`)
  > The industry has earned $513 million in 2024 and is projected to surpass $750 million this year.
  source: https://www.nzgda.com/blog/new-zealand-game-development-industry-breaks-records
- **divination** / Willow-Jean Prime — guessed 0.70, resolved 0.00 (`wrong`)
  > This sits alongside the Government’s pilot boot camp legislation, to put these into law—no doubt soon—to be again considered in this House.
  source: https://www.wheretheystand.nz/bills/1072
- **divination** / Simeon Brown — guessed 0.80, resolved 0.00 (`false`)
  > Those wait-lists are only going to increase with tomorrow's strikes.
  source: https://www.rnz.co.nz/news/national/575181/new-zealand-s-nurses-teachers-and-others-set-for-mega-strike-what-you-need-to-know
- **divination** / Celia Wade-Brown — guessed 0.85, resolved 0.00 (`wrong`)
  > I just want to note that this bill’s probably unanimous passing should be a more frequent occurrence in this House.
  source: https://www.scoop.co.nz/stories/PA2601/S00023/auckland-council-auckland-future-fund-bill-second-reading-8-oct-2025.htm
- **divination** / Matt Doocey — guessed 0.25, resolved 1.00 (`correct`)
  > Let’s be very clear, because what we are going to hear from Opposition parties is the challenging of the Government’s position in this space.
  source: https://www.scoop.co.nz/stories/PA2512/S00207/offshore-renewable-energy-bill-second-reading.htm

## Sourcing

389/389 verdicts cite at least one URL (100%). A resolved score with no source cannot be audited by a reader and should not be published.

