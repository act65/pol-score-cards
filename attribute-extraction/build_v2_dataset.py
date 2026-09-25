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
import sys

import fire

import bias_adjust
# Name resolution comes from data/names.py, the single implementation (see
# CLAUDE.md). `roster.py` used to live here and was the seventh near-copy; it
# lacked the "Surname, Given" ordering, the "on behalf of" delegation strip and
# the fuzzy match for Hansard's misspellings, so scores could split across
# spelling variants of one MP. Verified identical on the v3.0 corpus before
# removal: 111 distinct speaker names, 3,703 rows, zero divergence.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "data"))
from names import RosterIndex, clean, is_probably_mp_name  # noqa: E402


class Roster:
    """Thin adapter keeping the old call sites working over names.RosterIndex."""

    def __init__(self, path: str = None):
        self._idx = RosterIndex(path) if path else RosterIndex()

    def match(self, name):
        return self._idx.resolve(clean(name))

    def name(self, mp_id):
        return self._idx.name_of(mp_id)

    def party(self, mp_id):
        return self._idx.party_of(mp_id)

import attributes as attribute_registry

# The attribute set and its card-facing definitions come from the registry
# (attributes.py), which is the single source of truth shared with the
# extractor. They used to be duplicated here, which is how the site kept
# describing Charisma after it was cut.
# PUBLISHED, not ALL: a WITHHELD attribute (Forthrightness since 2026-09-25) is
# still extracted, audited and evaluated, but must not reach a card.
ATTRIBUTES = [(a.id, a.name, a.definition) for a in attribute_registry.PUBLISHED]
PUBLISHED_IDS = {a for a, _n, _d in ATTRIBUTES}
# Names for every ACTIVE attribute, not just the published ones: the ingest
# meets whatever is in the score files and must be able to name it. Filtering
# happens on PUBLISHED_IDS, at the point of ingest, so a withheld attribute
# reaches neither scores.jsonl nor examples.jsonl. (Keying this off ATTRIBUTES
# made withholding a record-tier attribute a KeyError rather than an omission.)
ID2NAME = {a.id: a.name for a in attribute_registry.ALL}

# These scorecards cover the 54th Parliament. The oral-questions corpus starts
# earlier (2023-07), so 19% of the Q/A pairs are from the 53rd — a different
# Parliament, with different portfolios and, for some MPs, a different side of
# the House. Letting those through would put pre-election behaviour on a card
# whose every other attribute is term-only.
TERM_START = "2023-10-06"


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


def _sort_key(e):
    """Score for ordering, with the scoreless sorted last rather than crashing.

    A PENDING row (a prediction whose resolve-by date has not passed, or a claim
    no source settles) carries score=None on purpose. `sorted` on a mixed
    None/int key raises, and it raised here — the build died halfway and left a
    truncated examples.jsonl, which is a worse failure than a bad order because
    it looks like a finished file.
    """
    sc = e.get("score")
    return sc if isinstance(sc, (int, float)) else -1


def _pick_examples(exs, cap=0):
    """Examples per (MP, attribute), ordered highest-score first. With cap<=0 (the
    default) ALL extracted statements are kept — the score already uses them all,
    so this just controls how much evidence the card displays. With cap>0, keep a
    score-diverse spread (highest, lowest, middle) so the range is still visible."""
    s = sorted(exs, key=_sort_key, reverse=True)
    if cap <= 0 or len(s) <= cap:
        return s
    spread = sorted(s, key=_sort_key)
    idx = sorted(set(round(i * (len(spread) - 1) / (cap - 1)) for i in range(cap)))
    return [spread[i] for i in idx]


def _ingest(rows, label, source, url_fn, R, per_pair, examples, unresolved, dates,
            src_counts, use_prior=False, resolved=None, stale=None):
    """Fold one score source into the shared pools. Scores are BLENDED into the
    same (mid, attr) pool as every other source — a politician gets one combined
    score per attribute. Each example is tagged with its `source` so the stats
    (and evidence pages) can still break coverage down by source."""
    for rec in rows:
        date = rec.get("date", "")
        dates.add(date)
        url = url_fn(rec, date)
        for attr, exs in rec.get("examples_by_attribute", {}).items():
            if attr not in PUBLISHED_IDS:
                continue
            for i, e in enumerate(exs):
                sc = e.get("score")
                is_resolved = True
                pending = False
                verdict = sources = None
                if sc is None and resolved:
                    # A searched verdict beats the guess, and beats it silently
                    # -- same field, but now with sources behind it.
                    hit = resolved.get((rec.get("window_id", ""), attr, str(i)))
                    # The resolver's item_id embeds the example's POSITION in the
                    # window, which is only stable while the window is never
                    # re-extracted. Re-score a window and index 2 can be a
                    # different statement, so the key alone would attach a
                    # searched verdict to a quote it was never about -- the worst
                    # available failure, because the reader gets sources that
                    # look authoritative and are about something else.
                    #
                    # So confirm the statement text agrees before trusting the
                    # join. It found one stale row on 2026-09-25 (window
                    # 2024-11-06#1 veracity|4, a fifth example that no longer
                    # exists) and that one dropped harmlessly -- but the same
                    # staleness shifts indices as easily as it removes them, and
                    # the June-to-election re-scrape will re-extract windows.
                    if hit and (hit.get("statement", "").strip()
                                != e.get("statement", "").strip()):
                        if stale is not None:
                            stale[attr] += 1
                        hit = None
                    if hit:
                        # Keep the verdict and its sources WHATEVER it was.
                        # `uncheckable` and `not_yet_due` yield no score (see
                        # _resolved_index) but the search still happened, and
                        # every one of those rows carries source URLs. "Here is
                        # where we looked and why it could not be settled" is
                        # worth more to a reader than silence, and it is the
                        # honest reason the number beside it is still a guess.
                        #
                        # The row stays resolved=False in that case, because
                        # `resolved` is what the site reads to decide whether a
                        # score is checked. A verdict on the row must never be
                        # what makes a guess look verified.
                        verdict, sources = hit.get("verdict"), hit.get("sources")
                        if hit.get("resolved_score") is not None:
                            sc = hit["resolved_score"]
                        else:
                            # Searched, and the answer is that there is no
                            # answer yet: `not_yet_due` (the resolve-by date has
                            # not passed) or `uncheckable` (no source settles
                            # it). This row is PENDING and carries no score.
                            #
                            # It must not fall through to `prior_score`. The
                            # divination prompt tells the model to write 0.5
                            # when the date has not passed, and 42 of the first
                            # 68 not_yet_due items are exactly 0.5 -- so the
                            # "score" was a placeholder the prompt asked for,
                            # published as though it were a finding. The other
                            # 26 are the model forming a view it was explicitly
                            # told not to form.
                            #
                            # Nor 0.5 by our own hand, which is the same number
                            # dressed as a decision, and which would punish long
                            # horizons: "this policy will fail by 2030" would be
                            # dragged to the middle while a prediction about
                            # next week scores 100. That inverts the attribute.
                            #
                            # Scoring plausibility-when-made instead is the dead
                            # end the prompt records: it correlated 0.72 with
                            # Rigor and put every MP in the House between 43 and
                            # 54, an eleven-point spread, which measured nothing.
                            pending = True
                if pending:
                    # Shown as evidence, with its verdict and the sources it was
                    # searched against, and counted in nothing.
                    is_resolved = False
                    sc = None
                elif not isinstance(sc, (int, float)):
                    # v3.0: search-tier rows (veracity, divination) carry no
                    # score until the resolver runs, only the model's unaided
                    # `prior_score`. With --use_prior we display that guess so
                    # the card is not blank — but it is tagged `resolved:false`
                    # all the way to the site, because a guess presented as a
                    # checked fact is the exact failure v3.0 exists to end.
                    if not use_prior:
                        continue
                    sc = e.get("prior_score")
                    is_resolved = False
                    if not isinstance(sc, (int, float)):
                        continue
                mid = R.match(e.get("politician", ""))
                if not mid:
                    if is_probably_mp_name(e.get("politician", "")):
                        unresolved[e.get("politician", "")] += 1
                    continue
                # A pending row contributes no score, so it changes neither
                # the headline number nor `n`. It is still an example.
                if sc is not None:
                    per_pair[(mid, attr)].append(sc)
                src_counts[source] += 1
                ex_row = {
                    "resolved": is_resolved,
                    "pending": pending,
                    "politician_id": mid, "attribute": ID2NAME[attr],
                    "text": e.get("statement", ""),
                    "score": None if sc is None else round(sc * 100),
                    "explanation": e.get("explanation", ""),
                    "context": f"{label} — {date}",
                    "source_url": url,
                    "source": source,
                }
                if verdict:
                    ex_row["verdict"] = verdict
                    ex_row["evidence_urls"] = sources or []
                    # The resolver's OWN analysis, which is a different thing
                    # from the extractor's `explanation` above and strictly
                    # better where it exists. The extractor never checked
                    # anything: for a search-tier claim its explanation restates
                    # what is being asserted and what would settle it (median
                    # 167 chars). The resolver went and looked, and its reasoning
                    # carries figures, dates, named sources and the
                    # disconfirming cases it ruled out (median 1,027). Showing
                    # the first where the second exists was labelling a
                    # description of the claim as "Analysis".
                    #
                    # Kept in its own field rather than overwriting
                    # `explanation`: they answer different questions, and the
                    # extractor's is still what the text-tier attributes show.
                    if hit.get("reasoning"):
                        ex_row["verdict_reasoning"] = hit["reasoning"]
                examples[(mid, attr)].append(ex_row)


def _ingest_qa(rows, R, per_pair, examples, unresolved, dates, src_counts,
               since=TERM_START):
    """Fold Forthrightness question/answer pairs into the scored pools.

    Unlike Strength and Authenticity, Forthrightness is **not** exempt from
    shrinkage. Their denominators are complete — every bill an MP held, every
    position they stated — so there is nothing to shrink toward. An MP's
    answered questions are a *sample* of how they answer, and a minister who
    fielded three questions should not sit above one who fielded ninety on the
    strength of three. So these go through the same empirical-Bayes path as the
    text attributes.

    Each pair also becomes an example, so the card can show the question next to
    the answer. A Forthrightness score without the question it dodged is not
    auditable, which is the whole promise of the site.
    """
    skipped_pre_term = 0
    for rec in rows:
        score = rec.get("score")
        if not isinstance(score, (int, float)):
            continue
        if since and (rec.get("date") or "") < since:
            skipped_pre_term += 1
            continue
        # The Q/A extractor leaves politician_id null; resolve it here through
        # the one name implementation rather than trusting the raw string.
        mid = rec.get("politician_id") or R.match(rec.get("politician", ""))
        if not mid:
            if is_probably_mp_name(rec.get("politician", "")):
                unresolved[rec.get("politician", "")] += 1
            continue
        date = rec.get("date", "")
        dates.add(date)
        per_pair[(mid, "forthrightness")].append(score)
        src_counts["Oral questions"] += 1
        question = (rec.get("question") or "").strip()
        examples[(mid, "forthrightness")].append({
            "resolved": True,
            "politician_id": mid, "attribute": ID2NAME["forthrightness"],
            "text": rec.get("statement", ""),
            "score": round(score * 100),
            "explanation": rec.get("explanation", ""),
            "question": question,
            "asked_by": rec.get("asker"),
            "context": f"Oral question — {date}"
                       + (f" — asked by {rec['asker']}" if rec.get("asker") else ""),
            "source_url": f"https://hansard.parliament.nz/hansard-transcript/{date}",
            "source": "Oral questions",
        })
    if skipped_pre_term:
        print(f"  Q/A: skipped {skipped_pre_term:,} pairs before {since} "
              f"(53rd Parliament)")


def _resolved_index(path):
    """{(window_id, attribute, index) -> resolved row} from the resolver output.

    Search-tier attributes are extracted with `score=None` and a `prior_score`
    that is only the model's unaided guess. Once `resolve.py` has searched for
    evidence, THAT is the answer and the guess must be replaced — a resolved
    score carries source URLs a reader can click, which is the whole difference
    between the two.

    `uncheckable` and `not_yet_due` return no score. They stay unresolved rather
    than falling back to the guess: a prediction whose horizon has not passed
    has no answer yet, and inventing one from a hunch is exactly the failure the
    resolver exists to remove.
    """
    index = {}
    if not path or not os.path.exists(path):
        return index
    for row in _read(path):
        item = row.get("item_id") or ""
        # "<window_id>|<attribute>|<i>", where window_id may carry a @model tag.
        parts = item.split("|")
        if len(parts) != 3:
            continue
        window, attr, i = parts[0].split("@")[0], parts[1], parts[2]
        index[(window, attr, i)] = row
    return index


def _record_scores(paths):
    """Read the record-tier score files: {(politician_id, attribute) -> row}.

    Strength, Authenticity and Forthrightness are not scored from text — they
    come from `data/strength_score.py`, `data/authenticity_score.py` and the
    Q/A pass, each already one row per politician with its own denominator.

    They are deliberately NOT put through `bias_adjust`. Shrinkage exists to
    stop a politician with three sampled statements looking extreme; these
    scores are rates over a known, complete denominator (every bill they held,
    every position they stated), so there is nothing to shrink toward and doing
    so would pull a genuine 12-for-12 record toward the mean of a different
    quantity.
    """
    out = {}
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        for row in _read(path):
            attr = row.get("attribute")
            pid = row.get("politician_id")
            # `insufficient_evidence` rows carry score None on purpose: no
            # bills to pass, no positions stated. Absent, never zero.
            if not attr or not pid or row.get("score") is None:
                continue
            out[(pid, attr)] = row
    return out


# --- Leadership -------------------------------------------------------------
# data/leadership.json is a hand-written, sourced snapshot of who held a senior
# role (see its own _note for the as-at date and what that excludes). It is a
# display facet only: no score depends on it, and an MP missing from it is a
# backbencher, not an error. Joined in here rather than read by the site so the
# published dataset carries its own answer to "who is a minister?".
_LEADERSHIP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "leadership.json")


def _leadership(path: str = _LEADERSHIP) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("roles", {})


def run(scores="hansard_scores_full.jsonl", out="site_data_v2",
        corpus_label="Hansard 54th Parliament", min_n=1, max_examples=0,
        presser_scores="", presser_label="Post-Cabinet press conference",
        release_scores="", release_label="Party press release",
        use_prior=False, record_scores="", qa_scores="",
        qa_since=TERM_START, resolved=""):
    R = Roster()
    os.makedirs(out, exist_ok=True)

    per_pair = collections.defaultdict(list)        # (mid, attr) -> [score]  (all sources pooled)
    examples = collections.defaultdict(list)        # (mid, attr) -> [example dict]
    unresolved = collections.Counter()
    dates = set()
    src_counts = collections.Counter()              # source -> #examples

    # Hansard: URL from the sitting date. Pressers/releases: each record carries its
    # own URL. All three blend into the same per-(mp, attribute) score pool.
    hansard_rows = _read(scores)
    presser_rows = _read(presser_scores) if presser_scores else []
    release_rows = _read(release_scores) if release_scores else []

    # Parties delete/restructure their sites, so some release URLs now 404. The
    # liveness map (data/corpus/release_url_status.json, from check_release_urls.py)
    # marks those; we point their evidence links at the Wayback snapshot instead,
    # dated to the release, so a dead live URL still resolves.
    _here = os.path.dirname(os.path.abspath(__file__))
    _status_path = os.path.join(_here, "..", "data", "corpus", "release_url_status.json")
    url_status = json.load(open(_status_path)) if os.path.exists(_status_path) else {}

    def release_url(rec, date):
        u = rec.get("url", "")
        s = url_status.get(u)
        if s and not s.get("live", True):
            ts = (date.replace("-", "") + "120000") if date else ""
            return f"https://web.archive.org/web/{ts}/{u}" if ts else f"https://web.archive.org/web/{u}"
        return u

    resolved_index = _resolved_index(resolved)
    if resolved_index:
        print(f"  resolver: {len(resolved_index):,} searched verdicts available")

    stale = collections.Counter()
    _ingest(hansard_rows, corpus_label, "Hansard",
            lambda rec, date: f"https://hansard.parliament.nz/hansard-transcript/{date}",
            R, per_pair, examples, unresolved, dates, src_counts, use_prior,
            resolved_index, stale)
    if stale:
        print(f"  resolver: {sum(stale.values())} verdict(s) DROPPED as stale — "
              f"the window was re-extracted and the statement no longer matches "
              f"({dict(stale)}). Re-run resolve.py to settle them again.")
    _ingest(presser_rows, presser_label, "Pressers",
            lambda rec, date: rec.get("url", ""),
            R, per_pair, examples, unresolved, dates, src_counts, use_prior)
    _ingest(release_rows, release_label, "Party releases", release_url,
            R, per_pair, examples, unresolved, dates, src_counts, use_prior)

    # Skipped entirely when Forthrightness is withheld — there is no point
    # resolving 11k Q/A pairs into a pool nothing will read.
    if qa_scores and os.path.exists(qa_scores) and "forthrightness" in PUBLISHED_IDS:
        _ingest_qa(_read(qa_scores), R, per_pair, examples, unresolved,
                   dates, src_counts, since=qa_since)
    elif qa_scores:
        print("  Q/A: skipped — forthrightness is withheld (attributes.WITHHELD)")

    adjusted = bias_adjust.adjust_scores(per_pair)
    record = _record_scores(
        [p.strip() for p in record_scores.split(",")] if record_scores else [])
    # A politician can have a record-tier score without ever being quoted, so
    # the card list is the union of both, not just whoever was extracted.
    mp_ids = sorted({mid for (mid, _a) in per_pair}
                    | {pid for (pid, _a) in record})

    # politicians.jsonl
    leaders = _leadership()
    with open(os.path.join(out, "politicians.jsonl"), "w", encoding="utf-8") as f:
        for mid in mp_ids:
            row = {"id": mid, "name": R.name(mid), "party": R.party(mid)}
            role = leaders.get(mid)
            if role:
                row["leadership"] = role["tier"]          # "leader" | "minister"
                row["role"] = role["role"]
                if role.get("portfolio"):
                    row["portfolio"] = role["portfolio"]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_roles = sum(1 for mid in mp_ids if mid in leaders)
    print(f"  leadership: {n_roles} of {len(mp_ids)} MPs carry a role "
          f"({len(leaders) - n_roles} in the list are unscored, e.g. the Speaker)")

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
                rec = record.get((mid, aid))
                if rec is not None:
                    # Computed from the record, not sampled from speech: no
                    # shrinkage, and the denominator travels with the score so
                    # the card can show what it is a rate *of*.
                    row[name] = round(float(rec["score"]) * 100)
                    row[f"{name}_n"] = (rec.get("positions_scored")
                                        or rec.get("evidence_n") or 0)
                    row[f"{name}_tier"] = "record"
                    for extra in ("cohort", "cohort_n", "basis",
                                  "positions_stated", "contradictions"):
                        if rec.get(extra) is not None:
                            row[f"{name}_{extra}"] = rec[extra]
                    continue
                a = adjusted.get((mid, aid))
                if not a or a.n < min_n:
                    continue
                row[name] = bias_adjust.display_score(a)
                row[f"{name}_n"] = a.n
                row[f"{name}_conf"] = a.confidence
                row[f"{name}_ci"] = round(a.ci95 * 100)
                # Search-tier attributes shown from `prior_score` are the
                # model's unaided guess. Flagged so the card can mark them
                # unverified rather than presenting a guess as a check.
                row[f"{name}_tier"] = (
                    "unresolved"
                    if attribute_registry.tier_of(aid) == "search"
                    else "text")
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
    sources = ([corpus_label] + ([presser_label] if presser_scores else [])
               + ([release_label] if release_scores else []))
    manifest = {
        "dataset": "nz-pol-scorecards-v2",
        "source": " + ".join(sources),
        "windows_scored": len(hansard_rows) + len(presser_rows) + len(release_rows),
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
