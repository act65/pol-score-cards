---
license: cc-by-4.0
language: [en, mi]
task_categories: [text-classification, text-scoring]
pretty_name: NZ Politician Scorecards (Hansard v2)
tags: [politics, new-zealand, accountability, hansard]
---

# NZ Politician Scorecards — Hansard v2

D&D-style **conduct scores** for New Zealand MPs, derived from **Hansard only**
(the 54th Parliament debate record, 2023-12-05 → 2026-05-28). Each MP is scored 0–100
on nine attributes: Forthrightness, Strength, Veracity, Authenticity, Divination, Charisma, Civility, Rigor, Specificity.

- **132 politicians**, **30,585 evidence statements**,
  from **365 scored debate windows**.
- Scores are produced by an LLM (Claude Opus) reading speaker-attributed Hansard
  speech; every score is backed by quoted statements linking to the transcript.

## Files

| file | one row per | key fields |
|---|---|---|
| `politicians.jsonl` | MP | `id, name, party` |
| `attributes.jsonl` | attribute | `id, name, definition` |
| `scores.jsonl` | MP | `<Attribute>` (0–100), plus `<Attribute>_n`, `_conf`, `_ci` |
| `examples.jsonl` | scored statement | `politician_id, attribute, text, score, explanation, source_url` |

## Bias mitigation (read before ranking MPs)

The headline `<Attribute>` value is **not** a raw mean of flagged statements — it
is an **empirical-Bayes shrunk** estimate: thin samples are pulled toward the
per-attribute population mean, so a single statement can't produce a confident
extreme. Each attribute therefore also carries:

- `<Attribute>_n` — number of statements behind it,
- `<Attribute>_conf` — `high` (n≥10) / `medium` (n≥3) / `low`,
- `<Attribute>_ci` — ±95% credible-interval half-width (0–100).

Treat `low`-confidence scores as provisional. empirical-Bayes shrinkage per attribute; n + 95% CI + confidence surfaced.

## Caveats

- **Hansard-only.** Every MP is measured in the *same adversarial arena* (debate),
  which removes the cross-source confound but skews conduct attributes downward vs
  press releases — compare MPs to each other, not to an absolute.
- **LLM-scored**, not human-verified. *Strength*, *Veracity*, and *Divination*
  ideally need external fact/record verification (a later goal); here they are the
  model's best judgement from the text.
- **Selection bias**: scores summarise the statements the model chose to extract.
  The extractor is prompted to sample representatively, but this is not a census of
  everything said. See `manifest.json` for exact counts and file hashes.

## Licence

CC-BY-4.0. Statements remain the property of the Crown / their speakers (Hansard
is Crown copyright, reusable under CC-BY 4.0); scores/explanations are model-generated.
