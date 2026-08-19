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
from collections import Counter, defaultdict
from typing import List, Literal, Optional

import anthropic
import fire
from pydantic import BaseModel, Field

import attributes
import check_quotes
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
    """One extracted statement, scored or awaiting resolution."""

    politician: str = Field(description="Name of the politician who made the statement.")
    statement: str = Field(description="The statement, quoted verbatim from the source.")
    score: Optional[float] = Field(
        default=None, description="Attribute score in [0, 1]; None until resolved.")
    # The model's unaided guess for search-tier attributes. Kept in a separate
    # field from `score` on purpose: it lets us measure whether searching beats
    # guessing, while making it structurally impossible for a guess to be
    # published as a resolved score.
    prior_score: Optional[float] = Field(default=None)
    explanation: str = Field(description="Brief justification for the score.")
    subject: str = Field(default="speaker", description="speaker | other | unclear.")
    subject_name: Optional[str] = Field(default=None)
    falsification_criterion: Optional[str] = Field(default=None)
    resolve_by: Optional[str] = Field(default=None)
    # `record`-tier fields. Authenticity extracts a stance on a named bill or
    # motion; the vote record decides whether it was kept. The bill is named in
    # words rather than picked from an ID list — `authenticity_score.py` matches
    # it to the proposition vocabulary, and refuses ambiguous matches.
    proposition: Optional[str] = Field(default=None)
    stance: Optional[str] = Field(default=None)
    # Strength extracts a commitment so it can be joined to the legislative
    # record. The ledger, not the model, decides whether it was delivered.
    commitment: Optional[str] = Field(default=None)
    # Set by the quote gate: verbatim | spliced | missing. Rows that fail the
    # gate are dropped, so anything written out is `verbatim` — the field is
    # kept so the audit can be re-run on the output without the corpus.
    quote_check: Optional[str] = Field(default=None)


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
    # Optional because the `search`-tier attributes (veracity, divination) are
    # no longer scored at extraction time — they emit a claim plus the criterion
    # that would settle it, and the resolver assigns the score later. A missing
    # score is a PENDING row, never a zero.
    score: Optional[float] = Field(
        default=None,
        description=("Attribute score in [0, 1]; higher is better. Leave empty "
                     "for veracity and divination — the resolver decides."))
    prior_score: Optional[float] = Field(
        default=None,
        description=("veracity/divination ONLY: your best guess from knowledge "
                     "alone, before any search. Recorded to measure whether "
                     "searching beats guessing — never published as the score."))
    explanation: str = Field(description="Brief justification.")
    falsification_criterion: Optional[str] = Field(
        default=None,
        description=("REQUIRED for veracity and divination. What evidence would "
                     "show this true, and what would show it false. Stated "
                     "before any checking happens."))
    resolve_by: Optional[str] = Field(
        default=None,
        description=("REQUIRED for divination. ISO date (YYYY-MM-DD) by which "
                     "the outcome should be observable."))
    # `record`-tier fields. These live here, on the schema the MODEL sees,
    # because a field the gate requires but the schema never offers is a field
    # the model cannot supply: the first positions run proposed 138 examples
    # and every one was dropped for `missing_proposition` / `missing_commitment`.
    proposition: Optional[str] = Field(
        default=None,
        description=("REQUIRED for authenticity. The bill, motion or policy the "
                     "speaker took a position ON, named as they named it (e.g. "
                     "'Fast-track Approvals Bill'). Do NOT invent an id — the "
                     "join matches this text to the vote record, and refuses "
                     "ambiguous matches. If no identifiable measure is named, "
                     "emit nothing for authenticity."))
    stance: Optional[str] = Field(
        default=None,
        description=("REQUIRED for authenticity. Exactly 'support' or 'oppose' "
                     "— the direction the speaker took on that proposition. "
                     "If the position has no clear direction, emit nothing for "
                     "authenticity rather than guessing."))
    commitment: Optional[str] = Field(
        default=None,
        description=("REQUIRED for strength. The specific thing the speaker "
                     "committed THEMSELVES or their government to doing, in "
                     "one clause. Not a prediction about the world (that is "
                     "divination) and not an opinion. If no commitment is "
                     "made, emit nothing for strength."))


class _MultiExample(BaseModel):
    politician: str = Field(description="Name of the politician (name only).")
    statement: str = Field(description="The statement, quoted verbatim.")
    # Who the judgement is ABOUT, which is not always who said it. An MP
    # describing an opponent's broken promise is making a low-delivery claim
    # about that opponent; filing it under the speaker penalises them for doing
    # scrutiny. See attribute-extraction/EVALUATION.md "subject attribution".
    subject: Literal["speaker", "other", "unclear"] = Field(
        default="speaker",
        description=(
            "Whose conduct the judgement is about. 'speaker' = the person who "
            "said it, their own party, or their own government. 'other' = the "
            "statement judges someone else (an opponent, a previous "
            "government). 'unclear' if it cannot be determined."))
    subject_name: Optional[str] = Field(
        default=None,
        description="When subject is 'other', who the judgement is about, if named.")
    scores: List[_AttrScore] = Field(description="One entry per attribute that applies.")


class MultiResult(BaseModel):
    examples: List[_MultiExample]


def build_combined_system(attrs: List[str], prompts_dir: Optional[str] = None) -> str:
    """One system prompt covering every attribute's rubric.

    Each attribute's prompt is included in full, worked examples and all. There
    used to be an ``examples=False`` mode that stripped the few-shot blocks to
    save tokens; it is gone, because in v3.0 those examples ARE the instruction.
    The boundary cases carry the whole point — "valid inference from a false
    premise scores HIGH on rigor", "scrutiny of a named policy failure scores
    HIGH on focus" — so dropping them would remove precisely what stops the
    attributes collapsing back into one another.

    The prompt is identical across every call, so with caching it is billed once
    and then read at the ~10% cache rate: length costs almost nothing per call.
    """
    blocks = [f"### Attribute: {name}\n{load_prompt(name, prompts_dir)}"
              for name in attrs]
    return _PREAMBLE + "\n\n".join(blocks)


# The cross-cutting rules. Each attribute's own prompt states what IT measures;
# this states the things that go wrong across all of them. Every clause here is
# a defect that was measured in the v2.0 output, not a precaution.
_PREAMBLE = """You are an expert analyst of New Zealand politics. From the text, find each
statement made by an individual NZ politician that bears on any attribute below,
and record it. Skip organisations, governments, and non-NZ figures. When the
source identifies the speaker (a Hansard "Hon NAME:" tag), attribute the
statement to that exact person.

Five rules govern every attribute. They matter more than any individual rubric.

=== 1. THE ATTRIBUTES ARE NOT NINE VIEWS OF "IS THIS GOOD" ===

Each attribute asks ONE question and must ignore the others. In the previous
version they collapsed into a single "was this a good statement" judgement:
Civility and Charisma correlated at 0.96, Civility and Rigor at 0.85, Veracity
and Rigor at 0.83. A card is meant to be several independent readings; instead
one bad remark moved a third of it.

So: score each attribute ONLY on its own question. A statement can — and often
should — score high on one and low on another:

  * valid reasoning from FALSE premises  -> HIGH rigor, LOW veracity
  * a precise, checkable, FALSE claim    -> HIGH specificity, LOW veracity
  * a blunt "no" that answers squarely   -> HIGH forthrightness, LOW specificity
  * fierce criticism of a POLICY         -> HIGH civility (it attacks no one)
  * "Labour are hopeless"                -> HIGH civility, ZERO focus
  * an insult beside a sound argument    -> LOW civility, HIGH rigor
  * on-policy but badly reasoned         -> HIGH focus, LOW rigor

If you find yourself giving one statement the same score on several attributes,
stop and check whether you are answering each question separately or just
rating the statement overall.

**FOCUS vs RIGOR — the pair most often confused.** The first v3.0 pilot had
them correlating at 0.87, because a content-free jibe at the other party got
scored twice: once by Focus (rightly) and once by Rigor, which reached for a
fallacy label to describe what was really just abuse. The division:

  * The statement engages a policy and the INFERENCE is weak -> score RIGOR.
    Focus stays HIGH; arguing badly about a real policy is still on-policy.
  * The statement is about the other party and there is no argument once you
    remove that -> score FOCUS only. Emit NOTHING for Rigor. A jibe is not an
    argument, and dressing it in a fallacy name does not make it one.

=== 2. SCORE ONLY WHERE THERE WAS A REAL OPPORTUNITY TO SCORE 0-100 ===

Only include a statement under an attribute if the speaker could genuinely have
scored anywhere from the bottom to the top of that scale. If a statement could
not have been much better or much worse on an attribute, scoring it adds noise.

RETURNING NOTHING IS A CORRECT AND EXPECTED OUTCOME. Most statements bear on one
or two attributes, not many. In the previous version 84% of statements were
scored on two or more attributes and Specificity fired on over half the corpus,
which is what an over-eager extractor looks like. Omit far more than you include.

Never eligible, for any attribute: procedural speech ("I move that the question
be now put", "Point of order"), the Speaker's rulings, the Clerk's readings,
interjections too short to carry a claim, and documents read into the record.
Each attribute's own prompt adds its own exclusions — apply them.

=== 3. QUOTE VERBATIM. THIS IS A HARD REQUIREMENT ===

Every score on the public site links back to its quote, so the quote must be
real. An audit of the previous run found 6% of statements did not appear in the
transcript at all, 9% were ellipsis-joined fragments, and 25% were cut
mid-sentence.

  * Copy the text EXACTLY as it appears. No paraphrase, no tidying, no fixing
    grammar, no resolving pronouns, no correcting a mis-speak.
  * NEVER join non-contiguous text with "..." or an ellipsis. If two separate
    passages matter, emit two separate statements.
  * Begin and end on a SENTENCE BOUNDARY. A fragment lifted from mid-sentence
    can mean something the speaker never said — a word-order slip in live speech
    reads as a false claim once the surrounding sentences are gone.

Statements that fail these checks are discarded automatically, so a
carefully-reasoned score on a mangled quote is wasted work.

=== 4. WHO THE JUDGEMENT IS ABOUT ===

`politician` is who SAID it. `subject` is whose conduct it lets you judge, and
they are frequently different people.

  * subject="speaker" — the statement reveals something about the speaker, their
    own party, or their own government.
  * subject="other" — it judges someone else: an opponent's broken promise, a
    previous government's failure, another party's hypocrisy. Name them in
    `subject_name`.
  * subject="unclear" — only when you genuinely cannot tell.

Pointing out someone else's failure is SCRUTINY. It is the job of an opposition
MP and must never be recorded as the speaker's own failing. Getting this wrong
was the worst bug in the previous version: it hit opposition MPs 4.1 times as
often as government ones on Authenticity and 7.8 times as often on Strength.

BUT — and this is the opposite error — the distinction only exists where a
statement REPORTS someone else's record. It does not apply to how the speaker
is behaving right now:

  * CIVILITY, RIGOR, SPECIFICITY and FOCUS are always about the SPEAKER. An MP
    hurling an insult is being uncivil HIMSELF, even though the insult is aimed
    at someone else. A muddled argument is HIS muddle. Always subject="speaker".
  * STRENGTH and AUTHENTICITY are where subject="other" genuinely belongs — an
    opponent's broken promise, another party's flip-flop.
  * VERACITY and DIVINATION take subject="other" only when the speaker is
    RELAYING a claim or forecast someone else made, rather than asserting it.

Marking an insult as subject="other" removes it from the record of the person
who said it. That is data loss, not fairness.

=== 5. SAMPLE REPRESENTATIVELY ===

Extract EVERY statement that qualifies under rules 1 and 2 — including ordinary,
mild and routine ones, not only the striking or quotable. These scores average
into a portrait of a politician's conduct over time, so a calm, on-topic answer
matters as much as a memorable attack. Do not skip a statement because it is
unremarkable, and do not go hunting for the worst thing in the window.

Note the tension with rule 2 and hold both: be strict about which ATTRIBUTES
apply to a statement, and unbiased about which STATEMENTS you look at.

=== SCORING AND THE TWO ATTRIBUTES YOU DO NOT SCORE ===

Scores run 0.0 (worst) to 1.0 (best) — higher is always better.

VERACITY and DIVINATION are different. For those two:

  * LEAVE `score` EMPTY. A separate resolver searches for evidence afterwards
    and assigns the real score.
  * State `falsification_criterion` — what evidence would show the claim true
    and what would show it false — plus `resolve_by` for divination.
  * THEN give `prior_score`: your best guess from your own knowledge, before any
    searching. This is recorded to measure whether searching actually beats
    guessing. It is never published as the score, so guess honestly rather than
    defensively — a confident 0.05 or 0.95 is more useful than a hedged 0.5, and
    if you truly do not know, 0.5 is the right answer.

Write the criterion BEFORE forming any view of the answer, and in that order:
fixing what counts as proof before looking is the whole defence against
confirmation bias. If you cannot state a real criterion, omit the claim entirely
— an unverifiable claim is not a veracity item however confidently you could
guess at it.

The attributes and their rubrics:
"""


_COMBINED_INSTRUCTION = (
    "\n\nReturn ONLY a JSON array (no prose, no markdown fences). Each element is one "
    'statement: {"politician": "<person\'s name ONLY — no party/title/honorific>", '
    '"statement": "<VERBATIM quote, whole sentences, no ellipsis>", '
    '"subject": "speaker"|"other"|"unclear", '
    '"subject_name": "<who it is about, when subject is other>", '
    '"scores": [{"attribute": "<one of the attribute ids above>", '
    '"score": <0.0-1.0, OMIT for veracity and divination>, '
    '"explanation": "<brief>", '
    '"falsification_criterion": "<REQUIRED for veracity and divination>", '
    '"resolve_by": "<YYYY-MM-DD, REQUIRED for divination>", '
    '"prior_score": <0.0-1.0, veracity/divination ONLY: your unaided guess>}]}. '
    'In "scores" include ONLY the attributes that clearly apply to that statement; '
    "omit the rest, and omit far more than you include. Only include statements by an "
    "individual New Zealand politician. If nothing relevant is present, return []."
)

# Semantic guidance only (no format spec) — the --json-schema flag enforces the
# shape on the CLI structured-output path, so we don't redescribe the JSON here.
_COMBINED_STRUCT_INSTRUCTION = (
    "\n\nFor each statement by an individual NZ politician, populate `scores` with "
    "ONLY the attributes that clearly apply — omit the rest, and omit far more than "
    "you include. Use the person's name only (no party, title, or honorific). Quote "
    "the statement VERBATIM in whole sentences; never join fragments with an "
    "ellipsis, as such rows are discarded automatically. Always set `subject` — "
    "'speaker' when the statement reveals something about the speaker's own conduct, "
    "'other' (with `subject_name`) when it judges an opponent or a previous "
    "government. For veracity and divination leave `score` empty and supply "
    "`falsification_criterion` (plus `resolve_by` for divination) and then "
    "`prior_score`, your unaided guess, which is recorded but never published. "
    "Skip "
    "organisations, governments, and non-NZ figures. If nothing relevant is present, "
    "return an empty examples list."
)


def _accept(attr: str, politician: str, statement: str, sc, source_norm: str,
            rejects: Counter) -> Optional[Example]:
    """Validate one (statement, attribute) pair and build its Example, or None.

    Three gates, in order of how badly each corrupts the dataset:

    1. **Quote fidelity.** The statement must appear verbatim in the source.
       A paraphrase or an ellipsis-splice cannot be audited by a reader who
       clicks through, which is the site's entire promise.
    2. **Required fields.** `search`-tier attributes without a falsification
       criterion are unresolvable, so they are dead weight — and a criterion
       invented after the fact is exactly the confirmation bias we are guarding
       against.
    3. **Score presence.** `text`-tier attributes need a score; `search`-tier
       ones must NOT have one, because a model-guessed score would quietly
       become the answer the resolver was supposed to find.
    """
    get = (lambda k: getattr(sc, k, None)) if not isinstance(sc, dict) else sc.get
    if not statement:
        rejects["empty"] += 1
        return None

    verdict = check_quotes.classify(statement, source_norm)
    if verdict != "verbatim":
        rejects[f"quote:{verdict}"] += 1
        return None
    if not (check_quotes._sentence_starts(statement)
            and check_quotes._sentence_ends(statement)):
        rejects["quote:mid_sentence"] += 1
        return None

    # Every field the registry declares mandatory for this attribute must be
    # present. Read generically from the registry rather than by name, so
    # declaring a new `requires` entry in attributes.py is enough to enforce it.
    for required in attributes.required_fields(attr):
        if not get(required):
            rejects[f"{attr}:missing_{required}"] += 1
            return None
    criterion = get("falsification_criterion")
    resolve_by = get("resolve_by")

    raw = get("score")
    prior = None
    if attributes.is_scored_at_extraction(attr):
        try:
            score = max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            rejects[f"{attr}:no_score"] += 1
            return None
    else:
        # Pending until the resolver runs. The model's unaided guess is kept as
        # `prior_score` so we can measure whether searching beats guessing — but
        # `score` stays None, so a guess can never be published as a resolved
        # answer no matter what the model returned.
        score = None
        # A `prior_score` is the model's unaided guess at an answer the RESOLVER
        # will later establish, so it only means anything for the search tier.
        # Record-tier attributes are never guessed — arithmetic over the
        # legislative record decides them — so a missing prior there is correct,
        # not a defect, and counting it as one filled the gate report with
        # `no_prior` noise on rows that were kept anyway.
        if attributes.tier_of(attr) != "search":
            prior = None
        else:
            try:
                prior = max(0.0, min(1.0, float(
                    get("prior_score") if get("prior_score") is not None else raw)))
            except (TypeError, ValueError):
                prior = None
                rejects[f"{attr}:no_prior"] += 1

    return Example(
        politician=politician or "Unknown",
        statement=statement,
        score=score,
        prior_score=prior,
        explanation=str(get("explanation") or "").strip(),
        subject=str(get("subject") or "speaker"),
        subject_name=get("subject_name"),
        falsification_criterion=criterion,
        resolve_by=resolve_by,
        proposition=get("proposition"),
        stance=(str(get("stance")).lower().strip()
                if get("stance") is not None else None),
        commitment=get("commitment"),
        quote_check=verdict,
    )


def extract_all_attributes(
    client: Optional[anthropic.Anthropic],
    system: str,
    article: dict,
    valid_attrs: set,
    model: str = DEFAULT_MODEL,
    backend: str = DEFAULT_BACKEND,
    max_tokens: int = 8192,
    stats: Optional[Counter] = None,
    timeout: int = 900,
) -> dict:
    """Score every attribute for one article in a single call.

    Returns {attribute_id: [Example, ...]}. Pass `stats` to collect rejection
    counts across a run — the firing rate and the quote-gate reject rate are
    both metrics we hold prompt changes to, so they need to be observable
    during the run, not reconstructed afterwards.

    `timeout` applies to the claude_cli backend and MUST scale with the window
    size. It defaulted to 300s inside `claude_cli`, which is fine for a
    3k-token window (~150s) and silently fatal for a 14k-token one: every call
    timed out, retried twice, and the run produced nothing at all while looking
    healthy. Window size and timeout are coupled, so they are set together in
    the runner rather than left to a default here.
    """
    out = defaultdict(list)
    article_text = build_article_text(article)
    source_norm = check_quotes.norm(article_text)
    rejects = stats if stats is not None else Counter()

    if backend == "claude_cli":
        # Schema-enforced structured output via `claude -p --json-schema` — the
        # subscription-path equivalent of the API's messages.parse.
        result = claude_cli.call_structured(
            system, article_text, MultiResult.model_json_schema(),
            model=model, instruction=_COMBINED_STRUCT_INSTRUCTION,
            timeout=timeout, label="windows")
        rows = (result or {}).get("examples", []) or []
        pairs = [(str(r.get("politician", "")).strip(),
                  str(r.get("statement", "")).strip(),
                  r.get("subject") or "speaker", r.get("subject_name"), sc)
                 for r in rows for sc in (r.get("scores") or [])]
    else:
        response = client.messages.parse(
            model=model, max_tokens=max_tokens,
            # The combined system prompt is identical across every article, so
            # cache it: after the first call the prefix is billed at the ~10%
            # cache-read rate. Over a thousand-window run that is a large, free
            # saving (TTL ~5 min, kept warm by back-to-back calls).
            system=[{"type": "text", "text": system + _COMBINED_INSTRUCTION,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": article_text}],
            output_format=MultiResult,
        )
        pairs = [(me.politician.strip(), me.statement.strip(),
                  me.subject, me.subject_name, sc)
                 for me in response.parsed_output.examples for sc in me.scores]

    for politician, statement, subject, subject_name, sc in pairs:
        get = sc.get if isinstance(sc, dict) else (lambda k: getattr(sc, k, None))
        attr = str(get("attribute") or "").strip().lower()
        if attr not in valid_attrs:
            rejects[f"unknown_attribute:{attr}"] += 1
            continue
        rejects["considered"] += 1
        ex = _accept(attr, politician, statement, sc, source_norm, rejects)
        if ex:
            # Subject is reported per STATEMENT but only means anything for some
            # attributes. An insult is the speaker's own incivility however it
            # is aimed, so forcing `speaker` here stops the aggregation filter
            # deleting it from the card of whoever said it.
            ex.subject = attributes.normalise_subject(attr, subject)
            ex.subject_name = subject_name if ex.subject == "other" else None
            if ex.subject != "speaker":
                rejects[f"subject_other:{attr}"] += 1
            rejects[f"kept:{attr}"] += 1
            out[attr].append(ex)
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
