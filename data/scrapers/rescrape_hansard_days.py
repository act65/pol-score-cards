"""Re-fetch the Hansard sitting days we already have, with the fixed day parser.

Why this exists (TODO 1b, see data/VOTES.md): the original scrape dropped every
paragraph under 40 characters as page chrome. Hansard prints a division result
as a run of *short* paragraphs, so that filter silently deleted the "Ayes 83" /
"Noes 34" labels, the verdict line, and any tally line for a small party — a
34-strong Noes ended up recorded as an unopposed vote. `parse_hansard_day` now
keeps short paragraphs that carry Hansard's transcript markup, but the fix only
reaches the data on a re-fetch.

This re-renders exactly the day URLs already present in the existing corpus
(rather than re-enumerating the whole term) and writes to a **separate** file, so
the corpus behind the current scored examples is left untouched:

    cd data/scrapers
    python rescrape_hansard_days.py run --out ../corpus/hansard_v2.json

Resumable: re-running skips URLs already written, so an interrupted run just
continues. Progress goes to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import time

import fire

from hansard import _Session, parse_hansard_day

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.join(HERE, "..", "corpus", "hansard.json")
DEFAULT_OUT = os.path.join(HERE, "..", "corpus", "hansard_v2.json")


def _urls_in(path: str) -> list[str]:
    """Distinct day URLs in a JSONL corpus, oldest first."""
    seen = {}
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            url = rec.get("url")
            if url:
                seen.setdefault(url, rec.get("date") or "")
    return [u for u, _ in sorted(seen.items(), key=lambda kv: kv[1])]


def _done(path: str) -> set:
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path) as f:
        for line in f:
            if line.strip():
                out.add(json.loads(line).get("url"))
    return out


def _render_day(sess, url: str, settle: int, max_sections: int, attempts: int):
    """Render one day, retrying on an empty parse.

    An empty result is usually transient — the SPA had not finished rendering, or
    the anti-bot challenge had not cleared, within the settle window. Retrying the
    same URL with a longer settle and a fresh browser recovers most of them; the
    same day that "fails" here parses fine on a second pass."""
    for attempt in range(1, attempts + 1):
        try:
            html = sess.render(url, wait_for=None, settle_s=settle * attempt)
            records = parse_hansard_day(html, url, max_sections=max_sections) if html else []
        except Exception as exc:                     # noqa: BLE001 — keep going
            records, err = [], exc
        else:
            err = None
        if records:
            return records, attempt, None
        if attempt < attempts:
            sess._recycle()                          # stale browser is a common cause
    return [], attempts, err


def run(out: str = DEFAULT_OUT, source: str = DEFAULT_SOURCE, settle: int = 45,
        headless: bool = True, limit: int | None = None,
        max_sections: int = 99, attempts: int = 3, recycle_every: int = 20) -> None:
    """Re-render every day URL in `source` and write parsed records to `out`."""
    urls = _urls_in(source)
    done = _done(out)
    todo = [u for u in urls if u not in done]
    if limit:
        todo = todo[:limit]
    print(f"[rescrape] {len(urls)} day URLs in {os.path.basename(source)}; "
          f"{len(done)} already done; fetching {len(todo)}", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    written = failed = retried = 0
    stubborn = []
    started = time.time()
    with _Session(headless=headless, recycle_every=recycle_every) as sess, open(out, "a") as sink:
        for i, url in enumerate(todo, 1):
            records, used, err = _render_day(sess, url, settle, max_sections, attempts)
            if not records:
                why = f"FAILED: {err}" if err else "no records"
                print(f"  [{i}/{len(todo)}] {url} {why} (after {used} attempts)",
                      file=sys.stderr)
                failed += 1
                stubborn.append(url)
                continue
            if used > 1:
                retried += 1
            for rec in records:
                sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
            sink.flush()
            written += len(records)
            if i % 10 == 0 or i == len(todo):
                rate = (time.time() - started) / i
                left = rate * (len(todo) - i) / 60
                print(f"  [{i}/{len(todo)}] {written} records, {failed} failed, "
                      f"{retried} needed a retry, ~{left:.0f} min left", file=sys.stderr)
    print(f"[rescrape] wrote {written} records "
          f"({failed} days failed, {retried} recovered on retry) -> {out}")
    if stubborn:
        print("[rescrape] days still missing (re-run to retry them):", file=sys.stderr)
        for u in stubborn:
            print(f"  {u}", file=sys.stderr)


if __name__ == "__main__":
    fire.Fire({"run": run, "urls": lambda source=DEFAULT_SOURCE: len(_urls_in(source))})
