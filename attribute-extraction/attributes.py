"""The attribute set — one importable source of truth.

Every other module used to work out the attribute set by listing `prompts/*.txt`
and subtracting a denylist of helper prompts. That silently broke whenever a
prompt file was added or renamed, and it could not express the thing v3.0 most
needs to say: **not every attribute is scored the same way.**

    from attributes import ATTRIBUTES, SCORED_IN_WINDOWS, tier_of

**Seven active attributes** as of 2026-08-15, of which **six are PUBLISHED** as
of 2026-09-24. Charisma was RETIRED (r=0.96 with Civility); Strength and
Authenticity are DEFERRED to v4; Divination is WITHHELD — still extracted and
measured, but not shown on a card until the resolver has scored it. See the
note above each tuple for why. All stay defined so older output still reads.

Three tiers, defined in `ATTRIBUTES.md` (which is the contract — if this file
disagrees with it, this file is the bug):

* `text`   — the words are the evidence. The LLM scores them directly.
* `record` — computed against a record we already hold. The LLM extracts a
             position or a commitment; arithmetic assigns the score.
* `search` — resolved against sources found at check time. The LLM extracts a
             claim *and the criterion that would settle it*; the resolver scores
             it afterwards.

Only the `text` tier produces a score at extraction time. The others emit rows
with `score=None`, which is a pending row — never a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Attribute:
    id: str
    name: str
    tier: str                    # text | record | search
    question: str                # the one question the prompt must ask
    definition: str              # card-facing, plain English
    # Where the score comes from when the tier is not `text`.
    evidence: str = ""
    # Extra fields the model must emit for this attribute, beyond the standard
    # {statement, explanation}. Enforced by the extraction schema.
    requires: tuple = field(default_factory=tuple)
    # Can this attribute ever describe SOMEONE ELSE's conduct?
    #
    # For manner-of-speaking attributes the answer is no, and getting this wrong
    # silently deletes data: an MP hurling an insult is being uncivil *himself*,
    # even though the insult is aimed at someone else. The first v3.0 smoke test
    # produced exactly that — a Peters attack filed as subject="other", which
    # the speaker-only aggregation filter would have dropped from his card.
    #
    # Only where a statement can REPORT another person's record does the
    # distinction exist: an opponent's broken promise (Strength), an opponent's
    # hypocrisy (Authenticity), or a claim/forecast the speaker is relaying
    # rather than making (Veracity, Divination).
    subject_can_be_other: bool = False


_DEFINED = (
    Attribute(
        "forthrightness", "Forthrightness", "record",
        "Did the answer address the question that was asked?",
        "How often the politician directly answers the question asked, rather "
        "than dodging or changing the subject.",
        evidence="corpus/oral_questions.jsonl, corpus/written_questions.jsonl",
    ),
    Attribute(
        "strength", "Strength", "record",
        "What did this politician commit to?",
        "The politician's ability to turn stated commitments into law.",
        evidence="corpus/strength_ledger.jsonl",
        requires=("commitment",),
        subject_can_be_other=True,
    ),
    Attribute(
        "veracity", "Veracity", "search",
        "Are the factual premises accurate?",
        "How accurate and non-misleading the politician's factual claims are, "
        "checked against sources.",
        evidence="the resolver",
        requires=("falsification_criterion",),
        subject_can_be_other=True,
    ),
    Attribute(
        "authenticity", "Authenticity", "record",
        "What position did this politician state?",
        "Whether stated positions match how the politician's party actually "
        "voted. Party-level: an MP may personally disagree with a party vote.",
        evidence="corpus/divisions.jsonl, corpus/propositions.jsonl",
        # Both are mandatory: a stance with no proposition cannot be joined to a
        # vote, and a proposition with no stance has nothing to contradict.
        requires=("proposition", "stance"),
        subject_can_be_other=True,
    ),
    Attribute(
        "divination", "Divination", "search",
        "Did the prediction come true?",
        "Whether the politician's predictions actually came true, checked "
        "against what happened.",
        evidence="the resolver",
        requires=("falsification_criterion", "resolve_by"),
        subject_can_be_other=True,
    ),
    Attribute(
        "focus", "Focus", "text",
        "Is this about the policy, or about the other team?",
        "Whether the politician engages the policy question or simply attacks "
        "the other party.",
    ),
    Attribute(
        "civility", "Civility", "text",
        "Is the attack on the argument, or on the person?",
        "Commitment to constructive dialogue over personal attacks. Criticising "
        "a policy hard is civil; turning on the person is not.",
    ),
    Attribute(
        "rigor", "Rigor", "text",
        "Does the conclusion follow from the premises?",
        "Whether conclusions follow logically from their assumptions. Not a "
        "fact-check — the accuracy of the assumptions is Veracity.",
    ),
    Attribute(
        "specificity", "Specificity", "text",
        "Is there checkable content in the statement?",
        "The meaningfulness of the politician's statements (vague platitudes "
        "score low).",
    ),
)

# Deferred to v4 on 2026-08-15. Their definitions stay here so existing output
# still reads and so the work is not lost, but they are out of the active set:
# nothing extracts them, nothing scores them, no card shows them.
#
# **Strength** — the ledger cannot answer the question the attribute asks.
# 53% of scored MPs (64 of 121) have no resolved bill at all, so their score
# came entirely from ballot bills and amendment papers: an activity count, not
# a delivery rate. Among ministers `delivery_rate` took 4 distinct values
# across 29 people. The manifesto and coalition-promise side, which is what
# would make it a real delivery measure, was never built. Publishing it would
# label a rank-within-cohort activity count as "did commitments become law".
#
# **Authenticity** — the unit does not match the card. NZ votes are cast per
# party, and only 88 of 212 propositions carry an individual member record, so
# for most MPs it measures *the party's* consistency with *this member's*
# words while printing on the member's card. Every other attribute measures the
# person. v4 should build it on conscience votes and named dissents, where the
# unit is right.
#
# What survives for v4: `data/strength_score.py`, `data/authenticity_score.py`
# and their 25 tests, `corpus/strength_ledger.jsonl`, the proposition
# vocabulary, and the `positions` extraction path.
DEFERRED = ("strength", "authenticity")

# The active set — what is extracted, scored and evaluated.
ALL = tuple(a for a in _DEFINED if a.id not in DEFERRED)

# Extracted and kept, but NOT PUBLISHED on cards (decided 2026-09-24).
#
# This is a third state, and it is deliberately not DEFERRED or RETIRED.
# RETIRED means cut for redundancy and gone. DEFERRED means out of the active
# set until a v4 rebuild. WITHHELD means the pipeline is right and the data is
# simply not ready to show yet — so extraction MUST continue, or the claims the
# resolver needs would never be collected.
#
# Divination: 1,618 claims but only 113 resolved, so 95% of what a card would
# show is the model's unaided guess — and on 312 resolved claims that guess has
# MAE 0.22 against the evidence and is confidently wrong 6% of the time. It was
# also the weakest column by information content: 29 MPs covered before the
# guesses were allowed in, all sharing one score, because 113 verdicts over 132
# MPs is a median evidence n of 1 and the shrinkage collapsed them.
#
# Bringing it back is ~1.5 nights of resolver time (276 calls at 6.48 claims
# each), not a rebuild. Delete it from this tuple when that has run.
WITHHELD = ("divination",)

# What the cards and the site dataset show. Everything else — the extractor,
# the audits, the eval harness — reads ALL, so a withheld attribute keeps being
# extracted and keeps being measured; it just does not reach a card.
PUBLISHED = tuple(a for a in ALL if a.id not in WITHHELD)

# Every attribute ever defined, keyed by id. Built from _DEFINED, not ALL, so a
# reader handed a v2.0 or early-v3.0 file can still name what it finds instead
# of crashing on it.
BY_ID = {a.id: a for a in _DEFINED}
ATTRIBUTES = tuple(a.id for a in ALL)

# Cut 2026-08-07: Charisma correlated with Civility at r=0.96 — one insult
# counted twice, compounded by the geometric mean. Focus replaced it. Kept here
# so old datasets can be read and reported on without crashing.
RETIRED = ("charisma",)

# What one pass over a speech window produces. The `record`-tier attributes are
# excluded on purpose: Forthrightness needs question/answer pairs (a relation,
# invisible in a lone statement), and Strength/Authenticity are joined to
# records in a separate deterministic step.
SCORED_IN_WINDOWS = tuple(a.id for a in ALL if a.tier == "text")
EXTRACTED_IN_WINDOWS = SCORED_IN_WINDOWS + tuple(
    a.id for a in ALL if a.tier == "search")

# Strength and Authenticity are *extracted* from windows too — a commitment and
# a stated position — but by a separate runner (`extract_positions.py`), not by
# the scoring pass. Keeping them out of EXTRACTED_IN_WINDOWS is deliberate:
# their output feeds a deterministic join rather than the score file, and
# bundling them would put rows with no score into the scores dataset.
#
# Forthrightness is absent because it needs question/answer pairs, which a
# speech window does not contain.
# Empty since 2026-08-15: both record-tier window attributes are DEFERRED. The
# path is kept — `extract_hansard.py --attrs positions` still works — because
# v4 needs exactly this to revive Authenticity from individual votes.
RECORD_IN_WINDOWS = tuple(a for a in ("authenticity", "strength")
                          if a not in DEFERRED)

# Scored over corpus/oral_questions.jsonl instead of over windows.
PAIRWISE = tuple(a.id for a in ALL if a.id == "forthrightness")


def tier_of(attribute: str) -> str:
    a = BY_ID.get(attribute)
    return a.tier if a else "unknown"


def is_scored_at_extraction(attribute: str) -> bool:
    """True when the model assigns the score itself.

    False for the `search` tier — those rows carry a criterion and no score
    until the resolver runs. Treating a pending row as 0.0 would invent a
    failing grade out of an unfinished check.
    """
    return tier_of(attribute) == "text"


def required_fields(attribute: str) -> tuple:
    a = BY_ID.get(attribute)
    return a.requires if a else ()


def normalise_subject(attribute: str, subject: str | None) -> str:
    """Force `speaker` where the attribute cannot describe anyone else.

    Manner-of-speaking attributes measure how the SPEAKER conducted themselves.
    The model reasonably but wrongly reports subject="other" when an insult is
    aimed at someone else — and because aggregation keeps only speaker rows,
    that quietly erases the incivility from the card of the person who committed
    it. See `Attribute.subject_can_be_other`.
    """
    a = BY_ID.get(attribute)
    if a and not a.subject_can_be_other:
        return "speaker"
    return subject if subject in ("speaker", "other", "unclear") else "speaker"
