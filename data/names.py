"""Politician name normalisation and roster lookup — one implementation.

Every pipeline that touches a person's name needs the same three things, and
each had grown its own copy: strip Hansard's honorifics and titles, fold case
and accents, then look the result up in `mps_roster.json`. Six modules, six
slightly different versions, and the differences were bugs — one stripped
"Rt Hon" only as a single token so "Rt Christopher Luxon" survived, another
missed the "on behalf of" suffix.

    from names import clean, norm, RosterIndex

    roster = RosterIndex()                       # or RosterIndex(path)
    roster.resolve("Hon DAVID SEYMOUR")          # -> "david-seymour"
    roster.resolve("Kapi-Kingi")                 # -> "mariameno-kapa-kingi" (fuzzy)
    clean("WINSTON PETERS on behalf of the PM")  # -> "Winston Peters"

Deterministic: no network, no LLM.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROSTER = os.path.join(HERE, "mps_roster.json")

# Matched word-by-word, so "Rt Hon" must appear as its two separate words.
TITLES = ("Rt", "Hon", "Dr", "Sir", "Dame", "Mr", "Mrs", "Ms", "Rev")
_HONORIFIC = re.compile(r"^(?:%s)\.?\s+" % "|".join(TITLES), re.I)
# "WINSTON PETERS on behalf of the Prime Minister" — the person who actually
# spoke is the one whose conduct we are measuring; drop the delegation.
_ON_BEHALF = re.compile(r"\s+on behalf of\b.*$", re.I)


def norm(s: str) -> str:
    """Casefold, strip accents, collapse whitespace — the lookup key."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).casefold().strip()


def clean(name: str, titlecase: bool = True) -> str:
    """'Rt Hon CHRISTOPHER LUXON (Prime Minister)' -> 'Christopher Luxon'.

    Handles every form the sources use: Hansard's all-caps speaker tags with
    honorifics and portfolios, the questions API's "Surname, Hon Given" order,
    delegation suffixes, and stray unbalanced brackets left by colon-splitting.
    With `titlecase=False` the original casing is preserved."""
    name = re.sub(r"\([^)]*\)", "", name or "")
    name = _ON_BEHALF.sub("", name)
    name = name.replace("(", " ").replace(")", " ")
    name = re.sub(r"\s+", " ", name).strip()
    if "," in name:                        # "Goldsmith, Hon Paul"
        surname, rest = name.split(",", 1)
        name = f"{rest.strip()} {surname.strip()}"
    words = [w for w in name.split() if w.rstrip(".") not in TITLES]
    name = " ".join(words).strip(" .")
    # Hansard caps whoever has the call; title-case it back so the same person
    # matches across their primary question and their supplementaries.
    if titlecase and name and name == name.upper():
        name = name.title()
    return name


class RosterIndex:
    """Lookup from any name form to a politician id.

    Surnames shared by two sitting MPs are dropped rather than guessed — a bare
    surname cannot disambiguate them, and a wrong attribution is worse than
    none."""

    def __init__(self, path: str = DEFAULT_ROSTER, fuzzy_cutoff: float = 0.85):
        self.fuzzy_cutoff = fuzzy_cutoff
        self._index: dict[str, str] = {}
        if not os.path.exists(path):
            return
        with open(path) as f:
            roster = json.load(f)
        buckets: dict[str, set] = {}
        for mp in roster:
            keys = set(mp.get("aliases") or [])
            keys.add(mp["name"])
            keys.add(mp["name"].split()[-1])
            for k in keys:
                buckets.setdefault(norm(k), set()).add(mp["id"])
        self._index = {k: next(iter(v)) for k, v in buckets.items() if len(v) == 1}

    @classmethod
    def from_mapping(cls, mapping: dict, fuzzy_cutoff: float = 0.85) -> "RosterIndex":
        """Build from an explicit {name-or-alias -> id} dict, for tests and for
        callers holding a roster from somewhere other than mps_roster.json."""
        self = cls.__new__(cls)
        self.fuzzy_cutoff = fuzzy_cutoff
        self._index = {norm(k): v for k, v in (mapping or {}).items()}
        return self

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, key: str) -> bool:
        return norm(key) in self._index

    def resolve(self, name: str, fuzzy: bool = True) -> str | None:
        """Politician id for a name, or None.

        Tries the cleaned full name, then the surname, then — with `fuzzy` — a
        close match, because Hansard misspells the occasional name
        ("Kapi-Kingi", "Kapa-Kangi"). A fuzzy match is only accepted when
        exactly one roster name is close enough, so two similar surnames can
        never be conflated."""
        cleaned = clean(name)
        if not cleaned:
            return None
        for key in (norm(cleaned), norm(cleaned.split()[-1])):
            if key in self._index:
                return self._index[key]
        if not fuzzy:
            return None
        key = norm(cleaned)
        close = difflib.get_close_matches(key, self._index.keys(), n=2,
                                          cutoff=self.fuzzy_cutoff)
        if len(close) == 1:
            return self._index[close[0]]
        if len(close) == 2 and self._index[close[0]] == self._index[close[1]]:
            return self._index[close[0]]      # two aliases of one person
        return None

    def as_dict(self) -> dict:
        """The raw {normalised key -> id} mapping, for callers that need it."""
        return dict(self._index)
