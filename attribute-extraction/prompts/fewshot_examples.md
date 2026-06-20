# Few-shot example blocks (extracted from prompts/*.txt)

These are the per-attribute few-shot `Examples` blocks. They remain inline in
each `prompts/<attr>.txt`, but the combined extractor (`extract._condense_prompt`)
strips them at runtime to save tokens. Preserved here for the future ablation
study (does few-shot improve accuracy? see TODOs).

## authenticity

```
Examples (statement → score, reasoning):
- "We will always stand up for renters" — said by an MP whose party just voted down renter protections → 0.15 (words contradict the vote).
- "I campaigned on cutting this tax, and today I delivered exactly that." → 0.9 (action matches the prior commitment).
- "I've consistently supported public transport investment" — where the record is mixed/unclear → 0.5 (plausible but unverified from the text).
```

## charisma

```
Examples (statement → score, reasoning):
- "I know members opposite care about housing too — let's take the parts of both plans that work and build something that lasts." → 0.9 (inclusive, consensus-seeking).
- "We will fight them every step of the way and never give an inch." → 0.3 (rallying, but purely combative).
- "Anyone who disagrees with us simply doesn't care about this country." → 0.1 (alienating, shuts down dialogue).
```

## civility

```
Examples (statement → score, reasoning):
- "If the Honourable Member spent less time cosying up to developers and more time listening to renters, we might solve this." → 0.35 (accusatory, implies the member is corrupt and uncaring).
- "I disagree with the Minister's housing plan: the modelling assumes demand the regions don't have, and I'll explain why." → 0.9 (pointed but engages the substance, no personal attack).
- "The Prime Minister is clearly out of her depth and has no idea what she's doing." → 0.2 (personal attack on competence).
```

## divination

```
Examples (statement → score, reasoning):
- "Inflation will peak in the first quarter of next year." → 0.6 (plausible, consistent with current forecasts, but uncertain).
- "Our policies will lead to unemployment below 4% by year end." → 0.4 (optimistic vs current trend).
- "If nothing changes, poverty will rise significantly within two years." → 0.55 (directionally supported, magnitude uncertain).
```

## forthrightness

```
Examples (response → score, reasoning):
- Q: "Will the budget be balanced next year?" A: "We're committed to fiscal responsibility and reducing debt." → 0.15 (pivots to talking points; never says yes or no).
- Q: "Will you raise the fuel tax?" A: "Yes — by 12 cents a litre from July, and here's why." → 0.95 (direct, complete).
- Q: "What measures would cut emissions 50% by 2030?" A: "We have a comprehensive plan: renewables, public transport, sustainable agriculture." → 0.4 (themes, not the specific measures asked for).
```

## promises

```
Examples (statement → score, reasoning):
- "We will build 10,000 state houses by the end of 2027." → 0.95 (amount + deadline).
- "We will invest more in regional rail." → 0.45 (real pledge, no amount or date).
- "We believe every New Zealander deserves a warm, dry home." → 0.05 (value statement, no committed action).
```

## rigor

```
Examples (statement → score, reasoning):
- "Crime is up 4% per the latest stats, and the three policies the report links to the rise are all ones this government cut." → 0.85 (evidence-based, conclusion follows).
- "If we let them ban this, soon they'll ban everything." → 0.1 (slippery slope, no evidence).
- "Everyone I talk to agrees with me, so the policy must be right." → 0.2 (appeal to popularity / anecdote).
```

## specificity

```
Examples (statement → score, reasoning):
- "We will lift the minimum wage to $25/hour by April 2026." → 0.95 (figure + date).
- "We're committed to supporting hard-working families." → 0.1 (slogan, no mechanism or measure).
- "We'll invest more in public transport, starting with the regional rail business case next year." → 0.6 (named action + rough timing, but no amounts).
```

## true

```
Examples (statement → score, reasoning):
- "New Zealand's population passed 5 million in 2020." → 0.95 (matches official statistics).
- "Crime has doubled in the last year." → 0.2 (police data shows a far smaller change).
- "This tax cut will pay for itself." → 0.3 (contested; most analyses find it does not fully offset).
```

## veracity

```
Examples (statement → score, reasoning):
- "Unemployment has fallen to 3.2%." → 0.95 if official statistics confirm it; lower if the real figure differs.
- "This bill will create 10 million jobs in its first year." → 0.3 (unsubstantiated; models predict far fewer).
- "Our state cut unemployment 15% since I took office." → 0.8 (official data shows ~12% — directionally true, slightly overstated).
```
