"""Package the v2.0 scorecard dataset and publish it to HuggingFace Datasets.

build_v2_dataset.py writes the four site JSONL files + manifest.json into a bundle
dir. This adds a dataset card (README.md) describing the scores, bias adjustment,
and caveats, then optionally pushes the bundle to a public HF Dataset — the
"bundle into a new dataset we can upload somewhere" step of the v2.0 plan.

    python publish_v2_dataset.py --bundle site_data_full                       # card only
    python publish_v2_dataset.py --bundle site_data_full --repo you/nz-pol-scorecards --push

Pushing needs `pip install huggingface_hub` + auth (HF_TOKEN or `huggingface-cli
login`). Unlike the raw corpus, this is the *scored* dataset (the cards' inputs).
"""

import argparse
import json
import os


ATTR_LINE = ("Forthrightness, Strength, Veracity, Authenticity, Divination, "
             "Charisma, Civility, Rigor, Specificity")


def _load_manifest(bundle):
    path = os.path.join(bundle, "manifest.json")
    if not os.path.exists(path):
        raise SystemExit(f"no manifest.json in {bundle} — run build_v2_dataset.py first")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dataset_card(m):
    dr = m.get("date_range") or ["?", "?"]
    return f"""---
license: cc-by-4.0
language: [en, mi]
task_categories: [text-classification, text-scoring]
pretty_name: NZ Politician Scorecards (Hansard v2)
tags: [politics, new-zealand, accountability, hansard]
---

# NZ Politician Scorecards — Hansard v2

D&D-style **conduct scores** for New Zealand MPs, derived from **Hansard only**
(the 54th Parliament debate record, {dr[0]} → {dr[1]}). Each MP is scored 0–100
on nine attributes: {ATTR_LINE}.

- **{m.get('politicians', '?')} politicians**, **{m.get('examples', '?'):,} evidence statements**,
  from **{m.get('windows_scored', '?')} scored debate windows**.
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

Treat `low`-confidence scores as provisional. {m.get('bias_mitigation', '')}.

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
"""


def push(bundle, repo):
    from huggingface_hub import HfApi
    api = HfApi()
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=bundle, repo_id=repo, repo_type="dataset")
    print(f"pushed {bundle} -> https://huggingface.co/datasets/{repo}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", default="site_data_full")
    ap.add_argument("--repo", help="HuggingFace dataset id, e.g. you/nz-pol-scorecards")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    m = _load_manifest(args.bundle)
    with open(os.path.join(args.bundle, "README.md"), "w", encoding="utf-8") as f:
        f.write(dataset_card(m))
    print(f"wrote {args.bundle}/README.md  "
          f"({m.get('politicians')} MPs, {m.get('examples')} examples, "
          f"{m.get('windows_scored')} windows)")

    if args.push:
        if not args.repo:
            raise SystemExit("--push needs --repo you/dataset-name")
        push(args.bundle, args.repo)
    elif args.repo:
        print(f"(dry run — re-run with --push to upload to {args.repo})")


if __name__ == "__main__":
    main()
