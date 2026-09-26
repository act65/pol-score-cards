"""Clean up politician IDs in the generated site data (no LLM calls).

The claude_cli backend sometimes returns annotated names ("Chris Hipkins
(Labour)", "Christopher Luxon (Prime Minister)", "NZ Government") which slug into
messy/duplicate ids. This re-resolves every politician through the (now hardened)
resolve_politician, merges duplicates, drops organisations/non-NZ figures, and
recomputes each attribute score as the mean of its (displayed) example scores —
so the site's "average across the statements below" is exactly true.

    python clean_site_ids.py          # cleans ../site/static in place
"""

import json
import os
from collections import defaultdict

import build_site_data as B

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "static")
MIN_EXAMPLES = 2


def _load(name):
    with open(os.path.join(STATIC, name)) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    pols = _load("politicians.jsonl")
    examples = _load("examples.jsonl")

    # old id -> (new id, display, party) via the hardened resolver on the display name
    remap, info, image = {}, {}, {}
    for p in pols:
        resolved = B.resolve_politician(p.get("name", p["id"]))
        if resolved is None:
            continue
        nid, disp, party = resolved
        remap[p["id"]] = nid
        # prefer a KNOWN party; keep the first clean display we see
        info.setdefault(nid, {"id": nid, "name": disp, "party": party or p.get("party", "")})
        if party:
            info[nid]["party"] = party
        if p.get("image"):
            image[nid] = p["image"]

    # regroup examples by (new id, attribute)
    grouped = defaultdict(list)
    for e in examples:
        nid = remap.get(e["politician_id"])
        if not nid:
            continue
        grouped[(nid, e["attribute"])].append(e)

    kept = {nid for (nid, _), exs in grouped.items() if len(exs) >= MIN_EXAMPLES}

    # write politicians
    with open(os.path.join(STATIC, "politicians.jsonl"), "w", encoding="utf-8") as f:
        for nid in sorted(kept):
            rec = dict(info[nid])
            if nid in image:
                rec["image"] = image[nid]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # scores: mean of the displayed example scores per attribute
    with open(os.path.join(STATIC, "scores.jsonl"), "w", encoding="utf-8") as f:
        for nid in sorted(kept):
            row = {"politician_id": nid}
            for (p2, attr), exs in grouped.items():
                if p2 == nid:
                    vals = [e["score"] for e in exs if e.get("score") is not None]
                    if vals:
                        row[attr] = round(sum(vals) / len(vals))
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # examples: capped, only for kept politicians
    with open(os.path.join(STATIC, "examples.jsonl"), "w", encoding="utf-8") as f:
        for (nid, attr), exs in sorted(grouped.items()):
            if nid not in kept:
                continue
            for e in exs[:B.MAX_EXAMPLES]:
                f.write(json.dumps({"politician_id": nid, "attribute": attr,
                                    "text": e["text"], "score": e.get("score"),
                                    "explanation": e.get("explanation"),
                                    "context": e.get("context"),
                                    "source_url": e.get("source_url")},
                                   ensure_ascii=False) + "\n")

    print(f"cleaned -> {len(kept)} politicians")
    print(", ".join(sorted(kept)))


if __name__ == "__main__":
    main()
