"""End-to-end: scraped articles -> extracted attributes -> the site's data.

This is the MVP backbone. For each article file it runs the attribute extractors,
aggregates per-politician scores (mean of example scores, on 0-100) and collects
the statements behind each score, then writes the three files the site reads:

    site/static/politicians.jsonl   {id, name, party, image?}
    site/static/scores.jsonl        {politician_id, <Attribute>: 0-100, ...}
    site/static/examples.jsonl      {politician_id, attribute, text, source_url}

so the site shows real data and each card stat links to the real evidence.

    export ANTHROPIC_API_KEY=...
    python build_site_data.py                 # over ../data/data/live_*.json
    python build_site_data.py --articles "../data/data/live_greens_2026-06.json"
    python build_site_data.py --dry_run        # show plan, no API calls
"""

import glob
import json
import os
import shutil
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import fire

import extract

# prompt file -> site attribute id (attributes.jsonl). All 9 attributes covered.
PROMPT_TO_SITE_ATTR = {
    "civility": "Civility",
    "veracity": "Veracity",
    "specificity": "Specificity",
    "forthrightness": "Precision",
    "rigor": "Rigor",
    "charisma": "Charisma",
    "divination": "Divination",
    "promises": "Strength",
    "authenticity": "Authenticity",
}

# Known NZ politicians -> (canonical id, party). Lets us reuse existing card
# portraits (matched by id) and label parties the LLM can't infer from a quote.
KNOWN = {
    "jacinda ardern": ("ardern", "Labour"),
    "christopher luxon": ("luxon", "National"),
    "david seymour": ("seymour", "ACT"),
    "winston peters": ("peters", "NZ First"),
    "chloe swarbrick": ("swarbrick", "Green"),
    "chlöe swarbrick": ("swarbrick", "Green"),
    "judith collins": ("collins", "National"),
    "marama davidson": ("davidson", "Green"),
    "tamatha paul": ("tamatha-paul", "Green"),
    "nicola willis": ("nicola-willis", "National"),
    "simeon brown": ("simeon-brown", "National"),
    "matt doocey": ("matt-doocey", "National"),
    "todd mcclay": ("todd-mcclay", "National"),
    "tama potaka": ("tama-potaka", "National"),
    "grant mccallum": ("grant-mccallum", "National"),
    "priyanca radhakrishnan": ("priyanca-radhakrishnan", "Labour"),
    "chris hipkins": ("chris-hipkins", "Labour"),
    "shane jones": ("shane-jones", "NZ First"),
    "rachel brooking": ("rachel-brooking", "Labour"),
    # Current cabinet ministers (appear in Beehive releases).
    "chris bishop": ("chris-bishop", "National"),
    "erica stanford": ("erica-stanford", "National"),
    "chris penk": ("chris-penk", "National"),
    "mark mitchell": ("mark-mitchell", "National"),
    "paul goldsmith": ("paul-goldsmith", "National"),
    "andrew bayly": ("andrew-bayly", "National"),
    "casey costello": ("casey-costello", "NZ First"),
    "louise upston": ("louise-upston", "National"),
    "shane reti": ("shane-reti", "National"),
    "brooke van velden": ("brooke-van-velden", "ACT"),
    "karen chhour": ("karen-chhour", "ACT"),
    "nicole mckee": ("nicole-mckee", "ACT"),
    "andrew hoggard": ("andrew-hoggard", "ACT"),
    "simon watts": ("simon-watts", "National"),
    "penny simmonds": ("penny-simmonds", "National"),
    "melissa lee": ("melissa-lee", "National"),
    "tama potaka": ("tama-potaka", "National"),
    "gerry brownlee": ("gerry-brownlee", "National"),
    "barbara edmonds": ("barbara-edmonds", "Labour"),
    "carmel sepuloni": ("carmel-sepuloni", "Labour"),
    "kieran mcanulty": ("kieran-mcanulty", "Labour"),
    "willie jackson": ("willie-jackson", "Labour"),
    "megan woods": ("megan-woods", "Labour"),
    "rawiri waititi": ("rawiri-waititi", "Te Pāti Māori"),
    "debbie ngarewa-packer": ("debbie-ngarewa-packer", "Te Pāti Māori"),
    "ricardo menendez march": ("ricardo-menendez-march", "Green"),
    "julie anne genter": ("julie-anne-genter", "Green"),
    "lan pham": ("lan-pham", "Green"),
}

# Leading honorifics to strip from extracted/byline names before matching.
_HONORIFICS = ("rt hon", "hon", "dr", "sir", "dame", "mp")

MAX_EXAMPLES = 5  # per (politician, attribute) on the evidence page


def _slug(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return "-".join(n.split())


def _strip_honorifics(name):
    """Drop leading honorifics like 'Hon', 'Rt Hon', 'Dr' (Beehive bylines use them)."""
    words = name.strip().split()
    changed = True
    while changed and words:
        changed = False
        for h in _HONORIFICS:
            hw = h.split()
            if [w.lower().strip(".") for w in words[: len(hw)]] == hw:
                words = words[len(hw):]
                changed = True
                break
    return " ".join(words)


# Drop extracted "politicians" that are actually organisations / non-NZ figures.
_DENY_KEYWORDS = ("government", "coalition", "council", "ministry", "department",
                  "opposition", "cabinet", "parliament", "party", "nations",
                  "commission", "the crown", "treasury", "reserve bank")
_DENY_NAMES = {"antonio guterres", "piyush goyal", "donald trump", "joe biden",
               "vladimir putin", "benjamin netanyahu"}


def _clean_name(name):
    """Strip title/party annotations and honorifics: 'Rt Hon Christopher Luxon
    (Prime Minister)' / 'Chloe Swarbrick / Green Party' -> 'Christopher Luxon' /
    'Chloe Swarbrick'."""
    n = name.split("(")[0].split("/")[0].split(",")[0]
    n = _strip_honorifics(n)
    return " ".join(n.split())


def resolve_politician(name):
    """-> (id, display_name, party) or None to skip (org / non-NZ / empty)."""
    display = _clean_name(name) or name.strip()
    key = display.lower()
    if not key or len(key) < 3:
        return None
    if key in _DENY_NAMES or any(kw in key for kw in _DENY_KEYWORDS):
        return None
    if key in KNOWN:
        pid, party = KNOWN[key]
        return pid, display, party
    return _slug(display), display, None


def _load_articles(path):
    """Load articles from either a JSON array (sources.py output) or JSONL
    (hansard.py appends one record per line)."""
    with open(path) as f:
        text = f.read().strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def _src_party(path):
    p = path.lower()
    return "Green" if "green" in p else ("National" if "national" in p else None)


def _context(art):
    """Human-readable context for an example: where/when it was said."""
    bits = []
    if art.get("headline"):
        bits.append(f"“{art['headline']}”")
    if art.get("author"):
        bits.append(art["author"])
    if art.get("date"):
        bits.append(str(art["date"])[:10])
    src = art.get("source") or (art.get("url", "").split("/")[2] if art.get("url", "").startswith("http") else "")
    if src:
        bits.append(src)
    return " — ".join(bits)


def build(articles=None, out_dir=None, model=None, dry_run=False, min_examples=1,
          backend="claude_cli", max_workers=None, max_n=None, min_chars=500):
    """Run the pipeline. backend: 'claude_cli' (uses the Claude subscription, no
    API credits — default) or 'anthropic' (uses API credits).

    max_n     — cap the number of articles processed (controls quota spend).
    min_chars — skip articles whose content is shorter than this (drops junk/
                placeholder records so we don't waste extraction calls on them)."""
    articles_glob = articles or os.path.join("..", "data", "data", "live_*.json")
    out_dir = out_dir or os.path.join("..", "site", "static")
    model = model or extract.DEFAULT_MODEL
    if max_workers is None:
        max_workers = 3 if backend == "claude_cli" else 6  # CLI calls are heavier
    files = sorted(glob.glob(articles_glob)) if isinstance(articles_glob, str) else list(articles_glob)

    # collect articles, dropping junk/placeholder records and capping at max_n
    arts = []
    skipped = 0
    for path in files:
        for art in _load_articles(path):
            if len(art.get("content", "")) < min_chars:
                skipped += 1
                continue
            arts.append((path, art))
    if max_n:
        arts = arts[:int(max_n)]

    # one extraction task per (article, attribute)
    tasks = []
    for path, art in arts:
        for prompt_name, site_attr in PROMPT_TO_SITE_ATTR.items():
            tasks.append((path, _src_party(path), art, prompt_name, site_attr))
    print(f"Backend: {backend}; articles: {len(files)} file(s), {len(arts)} records "
          f"({skipped} skipped < {min_chars} chars); attributes: "
          f"{len(PROMPT_TO_SITE_ATTR)}; {len(tasks)} calls (concurrency {max_workers})")
    if dry_run:
        for f in files:
            print("  -", f)
        return

    client = None if backend == "claude_cli" else extract._client()
    prompts = {p: extract.load_prompt(p) for p in PROMPT_TO_SITE_ATTR}

    def run(task):
        path, src_party, art, prompt_name, site_attr = task
        try:
            return task, extract.extract_examples(client, prompts[prompt_name], art,
                                                  model=model, backend=backend)
        except Exception as e:  # noqa: BLE001
            print(f"\n  ! {prompt_name} failed on {art.get('url')}: {e}")
            return task, None

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for task, res in pool.map(run, tasks):
            done += 1
            if done % 10 == 0 or done == len(tasks):
                print(f"\r  {done}/{len(tasks)} calls done", end="", flush=True)
            results.append((task, res))
    print()

    # aggregate
    scores_acc = defaultdict(list)        # (pid, site_attr) -> [0..1 scores]
    examples_acc = defaultdict(list)      # (pid, site_attr) -> [{text, source_url, explanation}]
    politicians = {}                      # pid -> {id, name, party}
    for (path, src_party, art, prompt_name, site_attr), res in results:
        if res is None:
            continue
        for ex in res.examples:
            resolved = resolve_politician(ex.politician)
            if resolved is None:
                continue
            pid, disp, party = resolved
            if party is None:
                party = src_party or ""
            politicians.setdefault(pid, {"id": pid, "name": disp, "party": party})
            if party and not politicians[pid]["party"]:
                politicians[pid]["party"] = party
            scores_acc[(pid, site_attr)].append(ex.score)
            if len(examples_acc[(pid, site_attr)]) < MAX_EXAMPLES:
                examples_acc[(pid, site_attr)].append({
                    "text": ex.statement,
                    "score": round(ex.score * 100),      # 0-100, matches the card
                    "explanation": ex.explanation,        # the analysis
                    "context": _context(art),             # where/when it was said
                    "source_url": art.get("url"),
                })

    _write(out_dir, politicians, scores_acc, examples_acc, min_examples)


def _write(out_dir, politicians, scores_acc, examples_acc, min_examples):
    # preserve existing portraits (match by id) and back up the sample data once
    existing_img = {}
    pol_path = os.path.join(out_dir, "politicians.jsonl")
    if os.path.exists(pol_path):
        for line in open(pol_path):
            if line.strip():
                d = json.loads(line)
                if d.get("image"):
                    existing_img[d["id"]] = d["image"]
    for fn in ("politicians.jsonl", "scores.jsonl", "examples.jsonl"):
        p = os.path.join(out_dir, fn)
        bak = os.path.join(out_dir, fn.replace(".jsonl", ".sample.jsonl"))
        if os.path.exists(p) and not os.path.exists(bak):
            shutil.copyfile(p, bak)
            print(f"backed up {fn} -> {os.path.basename(bak)}")

    # which politicians cleared the evidence threshold
    keep = {pid for (pid, _), exs in examples_acc.items() if len(exs) >= min_examples}

    with open(pol_path, "w", encoding="utf-8") as f:
        for pid in sorted(keep):
            rec = dict(politicians[pid])
            if pid in existing_img:
                rec["image"] = existing_img[pid]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(os.path.join(out_dir, "scores.jsonl"), "w", encoding="utf-8") as f:
        for pid in sorted(keep):
            row = {"politician_id": pid}
            for (p2, attr), vals in scores_acc.items():
                if p2 == pid and vals:
                    row[attr] = round(100 * sum(vals) / len(vals))
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(os.path.join(out_dir, "examples.jsonl"), "w", encoding="utf-8") as f:
        for (pid, attr), exs in sorted(examples_acc.items()):
            if pid not in keep:
                continue
            for ex in exs:
                f.write(json.dumps({
                    "politician_id": pid, "attribute": attr,
                    "text": ex["text"],
                    "score": ex.get("score"),            # this statement's 0-100 value
                    "explanation": ex.get("explanation"),  # the analysis
                    "context": ex.get("context"),         # where/when it was said
                    "source_url": ex["source_url"],
                }, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(keep)} politicians with real scores + evidence to {out_dir}")
    print("Politicians:", ", ".join(sorted(keep)))


if __name__ == "__main__":
    fire.Fire({"build": build})
