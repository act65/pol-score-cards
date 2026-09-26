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
    "ricardo menéndez march": ("ricardo-menendez-march", "Green"),
    "julie anne genter": ("julie-anne-genter", "Green"),
    "lan pham": ("lan-pham", "Green"),
    # 54th Parliament MPs surfaced by Hansard (parties via Wikipedia/Parliament).
    "andy foster": ("andy-foster", "NZ First"),
    "arena williams": ("arena-williams", "Labour"),
    "cameron brewer": ("cameron-brewer", "National"),
    "cameron luxton": ("cameron-luxton", "ACT"),
    "camilla belich": ("camilla-belich", "Labour"),
    "carl bates": ("carl-bates", "National"),
    "catherine wedd": ("catherine-wedd", "National"),
    "cushla tangaere-manuel": ("cushla-tangaere-manuel", "Labour"),
    "dan bidois": ("dan-bidois", "National"),
    "dana kirkpatrick": ("dana-kirkpatrick", "National"),
    "deborah russell": ("deborah-russell", "Labour"),
    "duncan webb": ("duncan-webb", "Labour"),
    "francisco hernandez": ("francisco-hernandez", "Green"),
    "georgie dansey": ("georgie-dansey", "Labour"),
    "ginny andersen": ("ginny-andersen", "Labour"),
    "hana-rawhiti maipi-clarke": ("hana-rawhiti-maipi-clarke", "Te Pāti Māori"),
    "helen white": ("helen-white", "Labour"),
    "huhana lyndon": ("huhana-lyndon", "Green"),
    "hūhana lyndon": ("huhana-lyndon", "Green"),
    "jamie arbuckle": ("jamie-arbuckle", "NZ First"),
    "jenny marcroft": ("jenny-marcroft", "NZ First"),
    "jenny salesa": ("jenny-salesa", "Labour"),
    "joseph mooney": ("joseph-mooney", "National"),
    "kahurangi carter": ("kahurangi-carter", "Green"),
    "lawrence xu-nan": ("lawrence-xu-nan", "Green"),
    "mariameno kapa-kingi": ("mariameno-kapa-kingi", "Te Pāti Māori"),
    "nancy lu": ("nancy-lu", "National"),
    "nicola grigg": ("nicola-grigg", "National"),
    "oriini kaipara": ("oriini-kaipara", "Te Pāti Māori"),
    "rachel boyack": ("rachel-boyack", "Labour"),
    "reuben davidson": ("reuben-davidson", "Labour"),
    "rima nakhle": ("rima-nakhle", "National"),
    "ryan hamilton": ("ryan-hamilton", "National"),
    "scott simpson": ("scott-simpson", "National"),
    "shanan halbert": ("shanan-halbert", "Labour"),
    "simon court": ("simon-court", "ACT"),
    "steve abel": ("steve-abel", "Green"),
    "stuart smith": ("stuart-smith", "National"),
    "tangi utikere": ("tangi-utikere", "Labour"),
    "todd stephenson": ("todd-stephenson", "ACT"),
    "tom rutherford": ("tom-rutherford", "National"),
    "vanushi walters": ("vanushi-walters", "Labour"),
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
    """Infer a party from a party-site filename, as a fallback when a statement's
    speaker isn't in the known-politician table. Multi-party sources (RNZ,
    Hansard, Beehive) return None so the party comes from speaker resolution."""
    p = os.path.basename(path).lower()
    for key, party in (
        ("green", "Green"), ("national", "National"), ("act", "ACT"),
        ("top", "Opportunity"), ("opportunity", "Opportunity"),
        ("labour", "Labour"), ("nzfirst", "NZ First"), ("nz_first", "NZ First"),
    ):
        if key in p:
            return party
    return None


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
          backend="claude_cli", max_workers=None, max_n=None, min_chars=500,
          merge=False):
    """Run the pipeline. backend: 'claude_cli' (uses the Claude subscription, no
    API credits — default) or 'anthropic' (uses API credits).

    max_n     — cap the number of articles processed (controls quota spend).
    min_chars — skip articles whose content is shorter than this (drops junk/
                placeholder records so we don't waste extraction calls on them).
    merge     — fold this run into the EXISTING site data instead of overwriting
                it: existing politicians are kept, the ones found in this run are
                added/replaced. Use it to grow the site one source file at a time."""
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

    # ONE call per article scores all 9 attributes at once (the article text is
    # the bulk of the tokens, so sending it once instead of 9× is the big saving).
    tasks = [(path, _src_party(path), art) for path, art in arts]
    print(f"Backend: {backend}; articles: {len(files)} file(s), {len(arts)} records "
          f"({skipped} skipped < {min_chars} chars); attributes: "
          f"{len(PROMPT_TO_SITE_ATTR)}; {len(tasks)} calls — one per article "
          f"(concurrency {max_workers})")
    if dry_run:
        for f in files:
            print("  -", f)
        return

    client = None if backend == "claude_cli" else extract._client()
    valid_attrs = set(PROMPT_TO_SITE_ATTR)
    combined_system = extract.build_combined_system(list(PROMPT_TO_SITE_ATTR))

    def run(task):
        path, src_party, art = task
        try:
            return task, extract.extract_all_attributes(
                client, combined_system, art, valid_attrs, model=model, backend=backend)
        except Exception as e:  # noqa: BLE001
            print(f"\n  ! failed on {art.get('url')}: {e}")
            return task, None

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for task, res in pool.map(run, tasks):
            done += 1
            if done % 5 == 0 or done == len(tasks):
                print(f"\r  {done}/{len(tasks)} calls done", end="", flush=True)
            results.append((task, res))
    print()

    # aggregate
    scores_acc = defaultdict(list)        # (pid, site_attr) -> [0..1 scores]
    examples_acc = defaultdict(list)      # (pid, site_attr) -> [{text, source_url, explanation}]
    politicians = {}                      # pid -> {id, name, party}
    for (path, src_party, art), res in results:
        if res is None:
            continue
        # res: {prompt_attr: [Example, ...]} -> flatten to (site_attr, Example)
        for prompt_attr, examples in res.items():
            site_attr = PROMPT_TO_SITE_ATTR.get(prompt_attr)
            if not site_attr:
                continue
            for ex in examples:
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

    _write(out_dir, politicians, scores_acc, examples_acc, min_examples, merge=merge)


def _read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _write(out_dir, politicians, scores_acc, examples_acc, min_examples, merge=False):
    os.makedirs(out_dir, exist_ok=True)
    pol_path = os.path.join(out_dir, "politicians.jsonl")
    scores_path = os.path.join(out_dir, "scores.jsonl")
    ex_path = os.path.join(out_dir, "examples.jsonl")

    # preserve existing portraits (match by id) and back up the sample data once
    existing_pols = {d["id"]: d for d in _read_jsonl(pol_path)}
    existing_img = {pid: d["image"] for pid, d in existing_pols.items() if d.get("image")}
    for fn in ("politicians.jsonl", "scores.jsonl", "examples.jsonl"):
        p = os.path.join(out_dir, fn)
        bak = os.path.join(out_dir, fn.replace(".jsonl", ".sample.jsonl"))
        if os.path.exists(p) and not os.path.exists(bak):
            shutil.copyfile(p, bak)
            print(f"backed up {fn} -> {os.path.basename(bak)}")

    # which politicians cleared the evidence threshold THIS run
    keep = {pid for (pid, _), exs in examples_acc.items() if len(exs) >= min_examples}

    # this run's rows, keyed by politician id
    new_pols = {}
    for pid in keep:
        rec = dict(politicians[pid])
        if pid in existing_img:
            rec["image"] = existing_img[pid]
        new_pols[pid] = rec
    new_scores = {}
    for pid in keep:
        row = {"politician_id": pid}
        for (p2, attr), vals in scores_acc.items():
            if p2 == pid and vals:
                row[attr] = round(100 * sum(vals) / len(vals))
        new_scores[pid] = row
    new_examples = {}
    for (pid, attr), exs in examples_acc.items():
        if pid not in keep:
            continue
        for ex in exs:
            new_examples.setdefault(pid, []).append({
                "politician_id": pid, "attribute": attr,
                "text": ex["text"],
                "score": ex.get("score"),               # this statement's 0-100 value
                "explanation": ex.get("explanation"),     # the analysis
                "context": ex.get("context"),             # where/when it was said
                "source_url": ex["source_url"],
            })

    if merge:
        # Per-politician merge: existing politicians are preserved as-is; the
        # politicians this run covers (new, or re-extracted) replace their old
        # entries wholesale. Lets you grow the site one source file at a time
        # without re-paying to extract the whole corpus.
        final_pols = dict(existing_pols)
        final_scores = {r["politician_id"]: r for r in _read_jsonl(scores_path)}
        final_examples = {}
        for r in _read_jsonl(ex_path):
            final_examples.setdefault(r["politician_id"], []).append(r)
        final_pols.update(new_pols)
        final_scores.update(new_scores)
        for pid in keep:
            final_examples[pid] = new_examples.get(pid, [])
        added = sorted(p for p in keep if p not in existing_pols)
        print(f"merge: {len(existing_pols)} existing + {len(keep)} from this run "
              f"({len(added)} new: {', '.join(added) or 'none'}) -> {len(final_pols)} total")
    else:
        final_pols, final_scores, final_examples = new_pols, new_scores, new_examples

    out_ids = sorted(final_pols)
    with open(pol_path, "w", encoding="utf-8") as f:
        for pid in out_ids:
            f.write(json.dumps(final_pols[pid], ensure_ascii=False) + "\n")
    with open(scores_path, "w", encoding="utf-8") as f:
        for pid in out_ids:
            if pid in final_scores:
                f.write(json.dumps(final_scores[pid], ensure_ascii=False) + "\n")
    with open(ex_path, "w", encoding="utf-8") as f:
        for pid in out_ids:
            for ex in final_examples.get(pid, []):
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(out_ids)} politicians with real scores + evidence to {out_dir}")
    print("Politicians:", ", ".join(out_ids))


if __name__ == "__main__":
    fire.Fire({"build": build})
