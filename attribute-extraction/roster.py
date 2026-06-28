"""Map raw speaker names / LLM-returned politician names to canonical MP ids.

Hansard tags ("Rt Hon CHRISTOPHER LUXON", "Hon Dr Megan Woods"), the LLM's
name-only output ("Christopher Luxon"), and curly-apostrophe variants
("Damien O'Connor" vs "O’Connor") all need to resolve to one roster id.

Used by the dataset-stats, bias, and bundling steps so a politician's scores
aren't split across spelling variants. Names that *don't* resolve — and have
non-trivial speech — are surfaced as roster gaps (mid-term replacement MPs the
Wikipedia-built roster missed), not silently dropped.
"""

import json
import os
import re
import unicodedata

_HONORIFIC = re.compile(
    r"^(?:rt\s+hon|hon|right\s+honourable|honourable|dr|sir|dame|mr|mrs|ms|mx)\.?\s+",
    re.I)
_DEFAULT_ROSTER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "data", "mps_roster.json")


def _strip_accents(s: str) -> str:
    # fold accents so "Menéndez" == "Menendez", "Pāora" == "Paora", etc.
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("`", "'")
    s = _strip_accents(s)
    s = s.lower().strip()
    while True:
        n = _HONORIFIC.sub("", s).strip()
        if n == s:
            break
        s = n
    return re.sub(r"\s+", " ", s)


class Roster:
    def __init__(self, path: str = _DEFAULT_ROSTER):
        with open(path, encoding="utf-8") as f:
            self.mps = json.load(f)
        self.by_id = {m["id"]: m for m in self.mps}
        self._exact = {}          # normalised full name / alias -> id
        self._surname = {}        # normalised surname -> set(ids)
        self._firstlast = {}      # "first last" -> set(ids)
        for m in self.mps:
            keys = {_norm(m["name"])} | {_norm(a) for a in m.get("aliases", [])}
            for k in keys:
                if k:
                    self._exact[k] = m["id"]
            toks = _norm(m["name"]).split()
            if toks:
                self._surname.setdefault(toks[-1], set()).add(m["id"])
                if len(toks) >= 2:
                    self._firstlast.setdefault(f"{toks[0]} {toks[-1]}", set()).add(m["id"])

    def match(self, name: str):
        """Return an MP id, or None if the name can't be resolved confidently."""
        n = _norm(name)
        if not n:
            return None
        if n in self._exact:
            return self._exact[n]
        toks = n.split()
        # first + last (handles middle names: "takutai tarsh kemp" -> "takutai kemp")
        if len(toks) >= 2:
            fl = f"{toks[0]} {toks[-1]}"
            ids = self._firstlast.get(fl)
            if ids and len(ids) == 1:
                return next(iter(ids))
        # unique surname
        ids = self._surname.get(toks[-1]) if toks else None
        if ids and len(ids) == 1:
            return next(iter(ids))
        return None

    def name(self, mp_id: str) -> str:
        return self.by_id.get(mp_id, {}).get("name", mp_id)

    def party(self, mp_id: str) -> str:
        return self.by_id.get(mp_id, {}).get("party", "")


# Junk speaker tags that are not individual MPs (the Chair, generic interjectors).
NON_MP = {"hon member", "member", "members", "an hon member", "hon members",
          "the speaker", "speaker", "speaker-elect", "clerk", "deputy speaker",
          "assistant speaker", "temporary speaker", "chairperson", "the chairperson",
          "chief commissioner", "sergeant-at-arms", "unknown"}


def is_probably_mp_name(name: str) -> bool:
    return _norm(name) not in NON_MP and len(_norm(name).split()) >= 1
