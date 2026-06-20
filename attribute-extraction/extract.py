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
import re
from collections import defaultdict
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


_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"[ \t]+")
# Boilerplate lines that carry no scoreable content — drop them to save tokens.
_BOILER_RE = re.compile(
    r"^\s*(?:©|(?:copyright|authorised by|all rights reserved|share (?:this|on)|"
    r"follow us|subscribe|sign up|read more|related (?:stories|articles)|"
    r"advertisement|cookie|privacy policy|terms of use)\b)",
    re.I,
)


def trim_text(text: str) -> str:
    """Strip tokens that cost money but carry no signal: URLs, boilerplate/footer
    lines, and redundant whitespace. Conservative — keeps all substantive prose."""
    if not text:
        return ""
    out = []
    for line in text.splitlines():
        line = _URL_RE.sub("", line)          # URLs are unscoreable noise
        line = _WS_RE.sub(" ", line).strip()
        if not line or _BOILER_RE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def build_article_text(article: dict, trim: bool = True) -> str:
    """Render a scraped article dict into the text block sent to the model.

    Tolerant of missing keys — scrapers vary in which metadata they capture.
    With `trim`, URLs/boilerplate/whitespace are stripped to cut input tokens.
    """
    parts = []
    for label, key in (
        ("Headline", "headline"),
        ("Date", "date"),
        ("Author", "author"),
    ):
        value = article.get(key)
        if value:
            parts.append(f"{label}: {value}")
    content = article.get("content") or article.get("text") or ""
    if trim:
        content = trim_text(content)
    parts.append(f"Content: {content}")
    return "\n\n".join(parts)


# --- Combined extraction: score ALL attributes in ONE call per article ---------
# Sending the article once (instead of once per attribute) is the single biggest
# token saving — the article text dominates input, and it was being resent 9×.

class _AttrScore(BaseModel):
    attribute: str = Field(description="Attribute id this score is for.")
    score: float = Field(description="Attribute score in [0, 1]; higher is better.")
    explanation: str = Field(description="Brief justification.")


class _MultiExample(BaseModel):
    politician: str = Field(description="Name of the politician (name only).")
    statement: str = Field(description="The statement, quoted verbatim.")
    scores: List[_AttrScore] = Field(description="One entry per attribute that applies.")


class MultiResult(BaseModel):
    examples: List[_MultiExample]


def _condense_prompt(text: str) -> str:
    """Strip the few-shot 'Examples' block (token-heavy, and a testset-leakage
    risk) and collapse blank lines, keeping the definition + scoring anchors."""
    for marker in ("\nExamples (", "\nExamples:", "\nExample ("):
        i = text.find(marker)
        if i != -1:
            text = text[:i]
    return "\n".join(l.rstrip() for l in text.strip().splitlines() if l.strip())


def build_combined_system(attrs: List[str], prompts_dir: Optional[str] = None) -> str:
    """One system prompt covering every attribute's (condensed) rubric."""
    blocks = []
    for name in attrs:
        blocks.append(f"### Attribute: {name}\n{_condense_prompt(load_prompt(name, prompts_dir))}")
    preamble = (
        "You are an expert analyst of New Zealand politics. From the text, find each "
        "notable statement made by an individual NZ politician. For EACH statement, "
        "score it on every attribute below that clearly applies (omit attributes that "
        "don't apply to that statement). Each attribute is scored 0.0 (worst) to 1.0 "
        "(best), higher = better. Quote statements verbatim. Skip organisations, "
        "governments, and non-NZ figures.\n\nThe attributes and their rubrics:\n"
    )
    return preamble + "\n\n".join(blocks)


_COMBINED_INSTRUCTION = (
    "\n\nReturn ONLY a JSON array (no prose, no markdown fences). Each element is one "
    'statement: {"politician": "<person\'s name ONLY — no party/title/honorific>", '
    '"statement": "<verbatim quote>", "scores": [{"attribute": "<one of the attribute '
    'ids above>", "score": <0.0-1.0>, "explanation": "<brief>"}]}. In "scores" include '
    "ONLY the attributes that clearly apply to that statement; omit the rest. Only "
    "include statements by an individual New Zealand politician. If nothing relevant "
    "is present, return []."
)


def extract_all_attributes(
    client: Optional[anthropic.Anthropic],
    system: str,
    article: dict,
    valid_attrs: set,
    model: str = DEFAULT_MODEL,
    backend: str = DEFAULT_BACKEND,
    max_tokens: int = 8192,
) -> dict:
    """Score every attribute for one article in a single call.

    Returns {attribute_id: [Example, ...]} so callers can route each attribute's
    examples exactly as the per-attribute path did.
    """
    out = defaultdict(list)
    article_text = build_article_text(article)
    if backend == "claude_cli":
        text = claude_cli.call(system, article_text, model=model,
                               instruction=_COMBINED_INSTRUCTION)
        rows = claude_cli.parse_json_array(text)
        for row in rows:
            statement = str(row.get("statement", "")).strip()
            politician = str(row.get("politician", "")).strip() or "Unknown"
            for sc in row.get("scores", []) or []:
                attr = str(sc.get("attribute", "")).strip().lower()
                if attr not in valid_attrs:
                    continue
                ex = _example_from_row({"politician": politician, "statement": statement,
                                        "score": sc.get("score"), "explanation": sc.get("explanation")})
                if ex:
                    out[attr].append(ex)
        return out
    response = client.messages.parse(
        model=model, max_tokens=max_tokens,
        system=[{"type": "text", "text": system + _COMBINED_INSTRUCTION}],
        messages=[{"role": "user", "content": article_text}],
        output_format=MultiResult,
    )
    for me in response.parsed_output.examples:
        for sc in me.scores:
            attr = sc.attribute.strip().lower()
            if attr not in valid_attrs:
                continue
            out[attr].append(Example(
                politician=me.politician.strip() or "Unknown",
                statement=me.statement.strip(),
                score=max(0.0, min(1.0, sc.score)),
                explanation=sc.explanation.strip(),
            ))
    return out


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
