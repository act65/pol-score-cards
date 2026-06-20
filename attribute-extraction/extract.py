"""Attribute extraction over scraped articles, powered by Claude.

Two entry points, both importable for the eval harness (see ``evaluate.py``):

- ``extract_examples`` — find and score every relevant statement in an article.
  This is the production pipeline: raw article in, list of scored examples out.
- ``score_statement`` — score a single, already-isolated statement. Used by the
  eval harness to measure agreement against the held-out testsets.

Both share the per-attribute prompt files in ``prompts/`` as the definition of
each attribute; only the requested output shape differs.

Usage (CLI, via python-fire):

    export ANTHROPIC_API_KEY=...
    python extract.py extract_file ../data/data/greens_media_releases.json \
        specificity green-specificity.jsonl

Set the model with ``--model`` (default: claude-opus-4-8).
"""

import json
import os
from typing import List, Optional

import anthropic
import fire
from pydantic import BaseModel, Field

import claude_cli

DEFAULT_MODEL = "claude-opus-4-8"
# Backends: "anthropic" (API, uses credits) or "claude_cli" (Claude Code CLI, uses
# the local Claude subscription — no API credits).
DEFAULT_BACKEND = "anthropic"

# All prompts define an attribute on a 0..1 scale where higher is "better"
# (see design-decisions.md). We standardise the output shape here rather than
# duplicating output instructions across every prompt file.
_SCORE_GUIDANCE = (
    "Score each statement from 0.0 (worst / lowest) to 1.0 (best / highest) for "
    "this attribute. Quote the statement verbatim. If the text contains no "
    "statement relevant to this attribute, return an empty list."
)


class Example(BaseModel):
    """One scored statement extracted from a source."""

    politician: str = Field(description="Name of the politician who made the statement.")
    statement: str = Field(description="The statement, quoted verbatim from the source.")
    score: float = Field(description="Attribute score in [0, 1]; higher is better.")
    explanation: str = Field(description="Brief justification for the score.")


class ExtractionResult(BaseModel):
    examples: List[Example]


class StatementScore(BaseModel):
    """Score for a single, pre-isolated statement (used by the eval harness)."""

    score: float = Field(description="Attribute score in [0, 1]; higher is better.")
    explanation: str = Field(description="Brief justification for the score.")


def load_prompt(name: str, prompts_dir: Optional[str] = None) -> str:
    """Load a prompt file by attribute name (without the .txt extension)."""
    if prompts_dir is None:
        prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    with open(os.path.join(prompts_dir, f"{name}.txt"), "r") as f:
        return f.read()


def build_article_text(article: dict) -> str:
    """Render a scraped article dict into the text block sent to the model.

    Tolerant of missing keys — scrapers vary in which metadata they capture.
    """
    parts = []
    for label, key in (
        ("Source", "url"),
        ("Headline", "headline"),
        ("Date", "date"),
        ("Author", "author"),
    ):
        value = article.get(key)
        if value:
            parts.append(f"{label}: {value}")
    content = article.get("content") or article.get("text") or ""
    parts.append(f"Content: {content}")
    return "\n\n".join(parts)


def _client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    # Prefer ANTHROPIC_API_KEY from the environment; only inject a key explicitly
    # when one is passed in.
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _example_from_row(row: dict) -> Optional[Example]:
    """Build an Example from a CLI-parsed dict, tolerantly."""
    try:
        score = float(row.get("score"))
    except (TypeError, ValueError):
        return None
    statement = str(row.get("statement", "")).strip()
    if not statement:
        return None
    return Example(
        politician=str(row.get("politician", "")).strip() or "Unknown",
        statement=statement,
        score=max(0.0, min(1.0, score)),
        explanation=str(row.get("explanation", "")).strip(),
    )


def extract_examples(
    client: Optional[anthropic.Anthropic],
    prompt: str,
    article: dict,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8192,
    backend: str = DEFAULT_BACKEND,
) -> ExtractionResult:
    """Find and score every statement relevant to the attribute in one article."""
    if backend == "claude_cli":
        text = claude_cli.call(f"{prompt}\n\n{_SCORE_GUIDANCE}", build_article_text(article), model=model)
        examples = [e for e in (_example_from_row(r) for r in claude_cli.parse_json_array(text)) if e]
        return ExtractionResult(examples=examples)
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": f"{prompt}\n\n{_SCORE_GUIDANCE}"}],
        messages=[{"role": "user", "content": build_article_text(article)}],
        output_format=ExtractionResult,
    )
    return response.parsed_output


def score_statement(
    client: Optional[anthropic.Anthropic],
    prompt: str,
    statement: str,
    model: str = DEFAULT_MODEL,
    politician: Optional[str] = None,
    backend: str = DEFAULT_BACKEND,
) -> StatementScore:
    """Score a single, already-isolated statement against the attribute."""
    who = f" by {politician}" if politician else ""
    if backend == "claude_cli":
        text = claude_cli.call(
            f"{prompt}\n\n{_SCORE_GUIDANCE}",
            f"Score this single statement{who}:\n{statement}",
            model=model,
        )
        rows = claude_cli.parse_json_array(text)
        ex = _example_from_row(rows[0]) if rows else None
        return StatementScore(score=ex.score if ex else 0.5,
                              explanation=ex.explanation if ex else "")
    user = (
        f"Score the following statement{who} for this attribute.\n\n"
        f"Statement: {statement}"
    )
    response = client.messages.parse(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": f"{prompt}\n\n{_SCORE_GUIDANCE}"}],
        messages=[{"role": "user", "content": user}],
        output_format=StatementScore,
    )
    return response.parsed_output


def extract_file(
    fname: str,
    attribute: str,
    save_to: str,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    prompts_dir: Optional[str] = None,
):
    """Run extraction over a JSON file of articles and write JSONL results.

    fname:     Path to a JSON file containing a list of article dicts.
    attribute: Attribute name; must match a file in the prompts directory.
    save_to:   Path to write JSONL results (one record per article).
    """
    client = _client(api_key)
    prompt = load_prompt(attribute, prompts_dir)

    with open(fname, "r") as f:
        articles = json.load(f)

    bad_responses = []
    with open(save_to, "w") as out:
        for i, article in enumerate(articles):
            headline = article.get("headline", f"article {i}")
            print(f"\rAnalyzing {i + 1}/{len(articles)}: {headline[:60]}...", end=" ", flush=True)
            try:
                result = extract_examples(client, prompt, article, model=model)
            except Exception as e:  # noqa: BLE001 - log and continue the batch
                print(f"\nError on '{headline}': {e}")
                bad_responses.append({"source": article.get("url"), "error": str(e)})
                continue

            record = {
                "source": article.get("url"),
                "attribute": attribute,
                "examples": [e.model_dump() for e in result.examples],
            }
            out.write(json.dumps(record) + "\n")

    print()
    if bad_responses:
        with open("bad_responses.json", "w") as f:
            json.dump(bad_responses, f, indent=4)
        print(f"{len(bad_responses)} articles failed; see bad_responses.json")


if __name__ == "__main__":
    fire.Fire({"extract_file": extract_file})
