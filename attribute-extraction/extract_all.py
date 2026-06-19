"""Batch-run attribute extraction over every (article file x attribute) pair.

    export ANTHROPIC_API_KEY=...
    python extract_all.py "../data/data/*.json" all ./out --model claude-opus-4-8

``attributes`` may be the string "all" (every prompt in prompts/) or a
comma-separated list of attribute names. Results are written to
``<output_dir>/<data_basename>/<attribute>.jsonl``.
"""

import os
from glob import glob

import fire

import extract


def _attribute_list(attributes, prompts_dir):
    if attributes == "all":
        return sorted(
            os.path.splitext(os.path.basename(p))[0]
            for p in glob(os.path.join(prompts_dir, "*.txt"))
        )
    if isinstance(attributes, str):
        return [a.strip() for a in attributes.split(",") if a.strip()]
    return list(attributes)


def extract_all(
    data_glob: str,
    attributes: str = "all",
    output_dir: str = "./out",
    model: str = extract.DEFAULT_MODEL,
    dry_run: bool = False,
):
    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    attrs = _attribute_list(attributes, prompts_dir)
    client = extract._client()

    for data_path in glob(data_glob):
        data_name = os.path.splitext(os.path.basename(data_path))[0]
        out_dir = os.path.join(output_dir, data_name)
        os.makedirs(out_dir, exist_ok=True)
        for attribute in attrs:
            save_to = os.path.join(out_dir, f"{attribute}.jsonl")
            print(f"{data_path}  x  {attribute}  ->  {save_to}")
            if dry_run:
                continue
            prompt = extract.load_prompt(attribute, prompts_dir)
            with open(data_path) as f:
                import json

                articles = json.load(f)
            with open(save_to, "w") as out:
                for article in articles:
                    result = extract.extract_examples(client, prompt, article, model=model)
                    out.write(
                        json.dumps(
                            {
                                "source": article.get("url"),
                                "attribute": attribute,
                                "examples": [e.model_dump() for e in result.examples],
                            }
                        )
                        + "\n"
                    )


if __name__ == "__main__":
    fire.Fire(extract_all)
