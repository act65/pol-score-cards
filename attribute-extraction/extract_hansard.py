"""Run the combined window extraction over the Hansard corpus.

Pipeline per sitting day:
  corpus/hansard_v2.json  --group by day-->  parts
     --hansard_prep.prep_day-->  attributed member-speech blocks (procedural dropped)
     --re-batch to ~window_tokens-->  windows (each block prefixed "SPEAKER: …")
     --extract.extract_all_attributes (ONE cached call)-->  examples
     --quote gate + required-field checks-->  kept examples
     --append--> <out> JSONL  (resumable: skips windows already written)

**This covers six of the nine attributes.** The four text-only ones (civility,
rigor, specificity, focus) are scored here; veracity and divination are
extracted here as resolver candidates, with a falsification criterion and no
score. Forthrightness needs question/answer PAIRS — see `extract_questions.py`.
Strength and Authenticity are joined to records deterministically. The split is
declared in `attributes.py`; see `ATTRIBUTES.md` for why.

Why this shape:
  * one combined call sends the window text once, not once per attribute;
  * speaker-prep drops ~18% procedural/chrome AND gives every block a known
    speaker, so scores are attributed rather than guessed;
  * prompt caching makes the shared rubric block ~free after the first call;
  * re-batching keeps calls (and their fixed overhead) low.

    # estimate the run WITHOUT spending anything:
    python extract_hansard.py --dry_run                                # full term
    python extract_hansard.py --dry_run --since 2025-10-01 --until 2025-10
    # real run (subscription backend, no API credits):
    python extract_hansard.py --backend claude_cli --out hansard_scores_v3.jsonl
    # real run (API, with caching):
    export ANTHROPIC_API_KEY=...; python extract_hansard.py --out hansard_scores_v3.jsonl

Prefer `overnight_run.py`, which stages the pilot before the full term, is
time-bounded, and runs the instrument audits at the end.
"""

import collections
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import fire

import attributes
import claude_cli
import extract
import hansard_prep


def _windows(blocks, window_tokens):
    """Pack attributed blocks into ~window_tokens text windows, each block
    rendered as 'SPEAKER: text' so the model never has to guess the speaker."""
    win, cur, cur_tok = [], [], 0
    for b in blocks:
        piece = f"{b['speaker']}: {b['text']}"
        ptok = len(piece) // 4
        if cur and cur_tok + ptok > window_tokens:
            win.append("\n\n".join(cur))
            cur, cur_tok = [], 0
        cur.append(piece)
        cur_tok += ptok
    if cur:
        win.append("\n\n".join(cur))
    return win


def _saved_ids(path):
    ids = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(json.loads(line)["window_id"])
                except Exception:
                    pass
    return ids


def _load_by_day(corpus, since, until=""):
    """Days in [since, until]. `until` is inclusive and may be a month prefix
    ('2025-10'), which is what makes a single-month pilot expressible — using
    --limit_days for that silently spilled into the following months."""
    by_day = collections.defaultdict(list)
    with open(corpus, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            date = r.get("date", "")
            if date >= since and (not until or date[:len(until)] <= until):
                by_day[date].append(r)
    return dict(sorted(by_day.items()))


# Which attributes one pass extracts. Two named sets, because they produce two
# different datasets and must not be mixed:
#
#   scores    — the four text attributes (scored) plus veracity/divination
#               (criterion, no score). Goes to the scores file.
#   positions — authenticity and strength, which emit a stated position and a
#               commitment with no score at all. These feed the deterministic
#               joins in data/authenticity_score.py and data/strength_score.py.
#
# Appending positions to the scores file would put permanently score-less rows
# into the dataset the site aggregates, so they are run separately and land in
# their own file.
def _resolve_attrs(spec: str) -> list:
    """Named set ('scores', 'positions') or an explicit comma-separated list."""
    named = {"scores": attributes.EXTRACTED_IN_WINDOWS,
             "positions": attributes.RECORD_IN_WINDOWS}
    if spec in named:
        return sorted(named[spec])
    chosen = [a.strip() for a in spec.split(",") if a.strip()]
    unknown = [a for a in chosen if a not in attributes.BY_ID]
    if unknown:
        raise SystemExit(f"unknown attribute(s): {', '.join(unknown)}. "
                         f"Use a name from attributes.py, or one of "
                         f"{sorted(named)}.")
    return sorted(chosen)


def run(out="hansard_scores.jsonl",
        corpus="../data/corpus/hansard_v2.json",
        since="2023-10-06",
        until="",
        attrs="scores",
        window_tokens=14000,
        workers=4,
        model=extract.DEFAULT_MODEL,
        backend=extract.DEFAULT_BACKEND,
        dry_run=False,
        limit_days=0,
        # Must scale with window_tokens. A 3k-token window returns in ~150s; a
        # 14k one does not fit in claude_cli's 300s default, and every call
        # then times out silently. See extract.extract_all_attributes.
        timeout=900,
        # rough public list rates ($/Mtok) for the estimate only — verify current.
        in_rate=15.0, out_rate=75.0, cache_read_rate=1.5):
    prompts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    # The attribute set comes from the registry, not from listing prompts/ — a
    # denylist over filenames silently broke whenever a prompt was added.
    # Windows produce the four text-only attributes (scored) plus veracity and
    # divination (extracted with a falsification criterion, scored later by the
    # resolver). Forthrightness needs question/answer PAIRS and is run over
    # corpus/oral_questions.jsonl by extract_questions.py; Strength and
    # Authenticity are joined to records deterministically.
    attrs = _resolve_attrs(attrs)
    valid = set(attrs)
    system = extract.build_combined_system(attrs, prompts_dir)
    sys_tok = len(system) // 4

    by_day = _load_by_day(corpus, since, until)
    days = list(by_day)
    if limit_days:
        days = days[:limit_days]

    # Build all windows first (cheap) so we can report/resume.
    plan = []  # (window_id, date, text, in_tok)
    for date in days:
        blocks = hansard_prep.prep_day(by_day[date])
        for i, text in enumerate(_windows(blocks, window_tokens)):
            wid = f"{date}#{i}"
            plan.append((wid, date, text, len(text) // 4))

    n_win = len(plan)
    content_tok = sum(p[3] for p in plan)

    if dry_run:
        # caching: system prompt billed full once, then cache-read; assume cache
        # stays warm across the back-to-back batch (TTL ~5 min).
        sys_full = sys_tok
        sys_cached = sys_tok * (n_win - 1) if n_win else 0
        # output: assume ~900 output tokens/window (statements+scores+explanations)
        out_tok = n_win * 900
        in_cost = (content_tok + sys_full) / 1e6 * in_rate \
            + sys_cached / 1e6 * cache_read_rate
        in_cost_nocache = (content_tok + sys_tok * n_win) / 1e6 * in_rate
        out_cost = out_tok / 1e6 * out_rate
        print(f"=== Hansard extraction DRY RUN ({model}) ===")
        print(f"days: {len(days)}   windows (=API calls): {n_win}   "
              f"window_tokens≈{window_tokens}")
        print(f"system prompt: {sys_tok:,} tok ({len(attrs)} attrs, cached)")
        print(f"content input: {content_tok:,} tok")
        print(f"est output:    {out_tok:,} tok (~900/window)")
        print(f"--- $ estimate at in={in_rate}/out={out_rate}/cache={cache_read_rate} per Mtok ---")
        print(f"input  $ (caching ON):  {in_cost:8.2f}")
        print(f"input  $ (no caching):  {in_cost_nocache:8.2f}   "
              f"(caching saves ${in_cost_nocache - in_cost:,.2f})")
        print(f"output $:               {out_cost:8.2f}")
        print(f"TOTAL  $ (caching ON):  {in_cost + out_cost:8.2f}")
        print("NB rates are placeholders — set --in_rate/--out_rate to current "
              "pricing, or use --backend claude_cli (subscription, no API $).")
        return

    client = extract._client() if backend == "anthropic" else None
    done = _saved_ids(out)
    if done:
        print(f"resuming: {len(done)} windows already in {out}")
    todo = [p for p in plan if p[0] not in done]
    print(f"{len(todo)} windows to do (of {n_win}) with {workers} worker(s)")

    # Gate statistics across the whole run. The quote-reject rate and the
    # per-attribute firing rate are both targets in ATTRIBUTES.md, so they are
    # collected live rather than reconstructed from the output afterwards.
    gate = collections.Counter()
    gate_lock = threading.Lock()

    def work(item):
        wid, date, text, _tok = item
        local = collections.Counter()
        by_attr = extract.extract_all_attributes(
            client, system, {"date": date, "content": text}, valid,
            model=model, backend=backend, stats=local, timeout=timeout)
        with gate_lock:
            gate.update(local)
        return wid, date, by_attr

    # Each claude_cli call is an independent subprocess, so threads parallelise
    # well (they block on the subprocess, releasing the GIL). Results are written
    # from the main thread as they complete, so the JSONL append stays single-
    # threaded and safe; the run remains resumable (window_id dedupe on restart).
    written = 0
    with open(out, "a", encoding="utf-8") as fh, \
            ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, item): item[0] for item in todo}
        quota_spent = False
        for fut in as_completed(futures):
            wid = futures[fut]
            try:
                wid, date, by_attr = fut.result()
            except claude_cli.QuotaExhausted as e:
                # Every remaining call would fail the same way, so stop now.
                # Grinding on wasted 2.8h and 780 calls on 2026-08-13 while
                # reporting "no progress" as if it were a transient stall.
                print(f"\nSUBSCRIPTION QUOTA EXHAUSTED at {wid}: {e}", flush=True)
                print("stopping this pass — the run is resumable, so restart "
                      "it after the usage window resets.", flush=True)
                quota_spent = True
                for pending in futures:
                    pending.cancel()
                break
            except Exception as e:  # noqa: BLE001
                print(f"\nerror on {wid}: {e}", flush=True)
                continue
            rec = {"window_id": wid, "date": date,
                   "examples_by_attribute":
                       {a: [e.model_dump() for e in exs] for a, exs in by_attr.items()}}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            written += 1
            n = sum(len(v) for v in by_attr.values())
            print(f"[{written}/{len(todo)}] {wid}: {n} scored examples", flush=True)
    if quota_spent:
        print(f"\nSTOPPED EARLY on quota: {written} of {len(todo)} windows "
              f"done this pass.", flush=True)
    print(f"done: wrote {written} windows -> {out}")
    _report_gate(gate, attrs)
    if quota_spent:
        # EX_TEMPFAIL: blocked, not broken. overnight_run.py stops the stage on
        # this rather than re-entering a pass that cannot make progress.
        raise SystemExit(75)


def _report_gate(gate, attrs):
    """Show what the quality gates rejected, and why.

    A silent gate is indistinguishable from no gate. If the quote-reject rate is
    high the prompt is not being followed; if an attribute keeps almost nothing
    its eligibility rule is too tight.
    """
    considered = gate.get("considered", 0)
    if not considered:
        return
    kept = sum(v for k, v in gate.items() if k.startswith("kept:"))
    print(f"\n=== quality gates ===\n{considered:,} statement-attribute pairs "
          f"proposed, {kept:,} kept ({100 * kept / considered:.0f}%)")

    quote = {k: v for k, v in gate.items() if k.startswith("quote:")}
    if quote:
        total = sum(quote.values())
        print(f"\nrejected on quote fidelity: {total:,} "
              f"({100 * total / considered:.1f}%)")
        for k, v in sorted(quote.items(), key=lambda kv: -kv[1]):
            print(f"  {k.split(':', 1)[1]:14} {v:6,}")

    other = {k: v for k, v in gate.items()
             if not k.startswith(("quote:", "kept:")) and k != "considered"}
    if other:
        print("\nrejected on required fields / scores:")
        for k, v in sorted(other.items(), key=lambda kv: -kv[1]):
            print(f"  {k:34} {v:6,}")

    print("\nkept per attribute:")
    for a in attrs:
        n = gate.get(f"kept:{a}", 0)
        print(f"  {a:16} {n:6,}  ({100 * n / considered:4.1f}% of proposals)")


if __name__ == "__main__":
    fire.Fire(run)
