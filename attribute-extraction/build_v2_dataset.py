"""Bundle the extracted Hansard scores into the site's dataset format (task 2c).

Reads extract_hansard.py output, resolves speakers to the roster, applies the
empirical-Bayes bias adjustment (bias_adjust.py), and writes the four JSONL files
the Flask site consumes — into a fresh output dir (default site_data_v2/) so the
live site/static is untouched until you approve a swap. Also writes a versioned
manifest (counts, date range, sha256) for publishing to HuggingFace.

    python build_v2_dataset.py --scores hansard_scores_3mo.jsonl --out site_data_v2
"""

import collections
import datetime
import hashlib
import json
import os

import fire

import bias_adjust
from roster import Roster, is_probably_mp_name

# Canonical attribute id -> (display name, definition). Definitions from README.
ATTRIBUTES = [
    ("forthrightness", "Forthrightness", "How often the politician directly answers the question asked, rather than dodging or changing the subject."),
    ("strength", "Strength", "The politician's ability to translate public rhetoric and promises into concrete policies and see them through to implementation."),
    ("veracity", "Veracity", "How accurate and non-misleading the politician's factual claims are."),
    ("authenticity", "Authenticity", "Consistency between the politician's public statements and their actions, votes, and speeches."),
    ("divination", "Divination", "How often the politician's predictions about future events have proven accurate."),
    ("charisma", "Charisma", "The politician's ability to persuade colleagues, build consensus, and work across party lines."),
    ("civility", "Civility", "Commitment to constructive dialogue over personal attacks, insults, or unproductive rhetoric."),
    ("rigor", "Rigor", "How rigorously the politician avoids logical fallacies and relies on evidence-based reasoning."),
    ("specificity", "Specificity", "The meaningfulness of the politician's statements (vague platitudes score low)."),
]
ID2NAME = {a: n for a, n, _ in ATTRIBUTES}


def _read(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _pick_examples(exs, cap=0):
    """Examples per (MP, attribute), ordered highest-score first. With cap<=0 (the
    default) ALL extracted statements are kept — the score already uses them all,
    so this just controls how much evidence the card displays. With cap>0, keep a
    score-diverse spread (highest, lowest, middle) so the range is still visible."""
    s = sorted(exs, key=lambda e: e.get("score", 0.5), reverse=True)
    if cap <= 0 or len(s) <= cap:
        return s
    spread = sorted(s, key=lambda e: e.get("score", 0.5))
    idx = sorted(set(round(i * (len(spread) - 1) / (cap - 1)) for i in range(cap)))
    return [spread[i] for i in idx]


def _ingest(rows, label, source, url_fn, R, per_pair, examples, unresolved, dates, src_counts):
    """Fold one score source into the shared pools. Scores are BLENDED into the
    same (mid, attr) pool as every other source — a politician gets one combined
    score per attribute. Each example is tagged with its `source` so the stats
    (and evidence pages) can still break coverage down by source."""
    for rec in rows:
        date = rec.get("date", "")
        dates.add(date)
        url = url_fn(rec, date)
        for attr, exs in rec.get("examples_by_attribute", {}).items():
            if attr not in ID2NAME:
                continue
            for e in exs:
                sc = e.get("score")
                if not isinstance(sc, (int, float)):
                    continue
                mid = R.match(e.get("politician", ""))
                if not mid:
                    if is_probably_mp_name(e.get("politician", "")):
                        unresolved[e.get("politician", "")] += 1
                    continue
                per_pair[(mid, attr)].append(sc)
                src_counts[source] += 1
                examples[(mid, attr)].append({
                    "politician_id": mid, "attribute": ID2NAME[attr],
                    "text": e.get("statement", ""),
                    "score": round(sc * 100),
                    "explanation": e.get("explanation", ""),
                    "context": f"{label} — {date}",
                    "source_url": url,
                    "source": source,
                })


def run(scores="hansard_scores_full.jsonl", out="site_data_v2",
        corpus_label="Hansard 54th Parliament", min_n=1, max_examples=0,
        presser_scores="", presser_label="Post-Cabinet press conference"):
    R = Roster()
    os.makedirs(out, exist_ok=True)

    per_pair = collections.defaultdict(list)        # (mid, attr) -> [score]  (all sources pooled)
    examples = collections.defaultdict(list)        # (mid, attr) -> [example dict]
    unresolved = collections.Counter()
    dates = set()
    src_counts = collections.Counter()              # source -> #examples

    # Hansard: URL built from the sitting date. Pressers: each record carries its
    # own YouTube URL. Both blend into the same per-(mp, attribute) score pool.
    hansard_rows = _read(scores)
    presser_rows = _read(presser_scores) if presser_scores else []
    _ingest(hansard_rows, corpus_label, "Hansard",
            lambda rec, date: f"https://hansard.parliament.nz/hansard-transcript/{date}",
            R, per_pair, examples, unresolved, dates, src_counts)
    _ingest(presser_rows, presser_label, "Pressers",
            lambda rec, date: rec.get("url", ""),
            R, per_pair, examples, unresolved, dates, src_counts)

    adjusted = bias_adjust.adjust_scores(per_pair)
    mp_ids = sorted({mid for (mid, _a) in per_pair})

    # politicians.jsonl
    with open(os.path.join(out, "politicians.jsonl"), "w", encoding="utf-8") as f:
        for mid in mp_ids:
            f.write(json.dumps({"id": mid, "name": R.name(mid),
                                "party": R.party(mid)}) + "\n")

    # attributes.jsonl
    with open(os.path.join(out, "attributes.jsonl"), "w", encoding="utf-8") as f:
        for aid, name, defn in ATTRIBUTES:
            f.write(json.dumps({"id": name, "name": name, "definition": defn}) + "\n")

    # scores.jsonl — adjusted (shrunk) score + n/confidence/CI per attribute, so
    # the site can show the bias-aware value AND flag thin evidence.
    n_scores = 0
    with open(os.path.join(out, "scores.jsonl"), "w", encoding="utf-8") as f:
        for mid in mp_ids:
            row = {"politician_id": mid}
            for aid, name, _d in ATTRIBUTES:
                a = adjusted.get((mid, aid))
                if not a or a.n < min_n:
                    continue
                row[name] = bias_adjust.display_score(a)
                row[f"{name}_n"] = a.n
                row[f"{name}_conf"] = a.confidence
                row[f"{name}_ci"] = round(a.ci95 * 100)
            f.write(json.dumps(row) + "\n")
            n_scores += 1

    # examples.jsonl
    n_ex = 0
    with open(os.path.join(out, "examples.jsonl"), "w", encoding="utf-8") as f:
        for key, exs in examples.items():
            for e in _pick_examples(exs, cap=max_examples):
                f.write(json.dumps(e) + "\n")
                n_ex += 1

    # manifest
    def _sha(name):
        h = hashlib.sha256()
        with open(os.path.join(out, name), "rb") as fh:
            h.update(fh.read())
        return h.hexdigest()[:16]

    files = ["politicians.jsonl", "attributes.jsonl", "scores.jsonl", "examples.jsonl"]
    sources = [corpus_label] + ([presser_label] if presser_scores else [])
    manifest = {
        "dataset": "nz-pol-scorecards-v2",
        "source": " + ".join(sources),
        "windows_scored": len(hansard_rows) + len(presser_rows),
        "examples_by_source": dict(src_counts),
        "date_range": [min(dates), max(dates)] if dates else None,
        "politicians": len(mp_ids),
        "attributes": [n for _a, n, _d in ATTRIBUTES],
        "examples": n_ex,
        "scoring": "all sources blended into one score per (politician, attribute); "
                   "each quote tagged with its source",
        "bias_mitigation": "empirical-Bayes shrinkage per attribute; n + 95% CI + confidence surfaced",
        "unresolved_speakers": len(unresolved),
        "files": {name: {"sha256_16": _sha(name)} for name in files},
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"bundled -> {out}/")
    print(f"  politicians: {len(mp_ids)}   scores rows: {n_scores}   examples: {n_ex}")
    print(f"  by source: {dict(src_counts)}")
    print(f"  date range: {manifest['date_range']}")
    if unresolved:
        print(f"  ⚠ {len(unresolved)} unresolved speakers (roster gaps), top: "
              + ", ".join(f'{n}({c})' for n, c in unresolved.most_common(6)))


if __name__ == "__main__":
    fire.Fire(run)
