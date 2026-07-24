"""Does the presser extractor need diarization? A/B benchmark.

Press-conference transcripts (corpus/pressers.json) are an undifferentiated wall
of text: the PM speaks, hands to a minister, then journalists ask questions — with
NO speaker labels. The extractor must therefore INFER who said what. This asks:
does adding a speaker-labeling (diarization) step improve attribution, or is the
raw extraction already good enough?

For a few pressers it runs the SAME extractor two ways and dumps both for review:
  RAW       — extract straight from the unlabeled transcript.
  DIARIZED  — first an LLM pass labels every turn (PM / named minister / JOURNALIST),
              then extract from the labeled transcript (labels act like Hansard's
              "Hon NAME:" speaker tags).

    python benchmark_diarization.py --n 2 --chars 26000 --out bench_diar.json

Runs on the claude_cli subscription backend (a handful of calls — keep --n small).
"""

import json
import os
import sys

import fire

import claude_cli
import extract

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "data", "corpus", "pressers.json")

DIARIZE_SYSTEM = (
    "You label speakers in a New Zealand post-Cabinet press-conference transcript. "
    "Speakers are: the Prime Minister (Christopher Luxon), any ministers he introduces "
    "(identify each by name from context), and unnamed JOURNALISTS asking questions. "
    "Rewrite the transcript segmented into speaker turns, prefixing each turn with a "
    "label on its own line in the form 'NAME: ' (use the person's real name for the PM "
    "and ministers, and 'JOURNALIST: ' for any reporter question or interjection). "
    "Keep the words VERBATIM — only insert the labels at turn boundaries; do not "
    "summarise, add, or drop any text. Output only the labelled transcript."
)


def _attrs_system():
    prompts_dir = os.path.join(HERE, "prompts")
    non = {"true", "promises"}
    attrs = sorted(os.path.splitext(f)[0] for f in os.listdir(prompts_dir)
                   if f.endswith(".txt") and os.path.splitext(f)[0] not in non)
    system = extract.build_combined_system(attrs, prompts_dir, examples=True)
    return attrs, set(attrs), system


def _flatten(by_attr):
    """{attr: [Example]} -> [{politician, statement, attrs:[...], scores:{...}}] merged
    by (politician, statement) so each quote is one row listing its scored attributes."""
    rows = {}
    for attr, exs in by_attr.items():
        for e in exs:
            key = (e.politician, e.statement)
            r = rows.setdefault(key, {"politician": e.politician, "statement": e.statement,
                                      "scores": {}})
            r["scores"][attr] = round(e.score, 2)
    return list(rows.values())


def _extract(system, valid_attrs, text, model):
    by_attr = extract.extract_all_attributes(
        None, system, {"content": text}, valid_attrs, model=model, backend="claude_cli")
    return _flatten(by_attr)


def run(n=2, chars=10000, model=extract.DEFAULT_MODEL, out="bench_diar.json", dia_timeout=360):
    pressers = json.load(open(CORPUS))
    # prefer multi-speaker pressers (a minister is introduced) — the hardest case
    pressers.sort(key=lambda p: (0 if "minister" in p["content"][:400].lower() else 1, -len(p["content"])))
    picks = pressers[:n]
    attrs, valid_attrs, system = _attrs_system()
    print(f"attributes: {attrs}\n", flush=True)

    results = []
    for i, p in enumerate(picks, 1):
        chunk = p["content"][:chars]
        print(f"=== [{i}/{n}] {p['date']}  ({len(chunk)} chars) ===", flush=True)

        print("  RAW extract…", flush=True)
        raw = _extract(system, valid_attrs, chunk, model)
        print(f"    -> {len(raw)} statements", flush=True)

        print("  diarize…", flush=True)
        try:
            labelled = claude_cli.call(DIARIZE_SYSTEM, chunk, model=model,
                                       instruction="", timeout=dia_timeout)
            print(f"    -> labelled {len(labelled)} chars", flush=True)
            print("  DIARIZED extract…", flush=True)
            dia = _extract(system, valid_attrs, labelled, model)
            print(f"    -> {len(dia)} statements", flush=True)
        except Exception as e:  # noqa: BLE001 — keep RAW result even if diarize fails
            print(f"    diarize FAILED: {e}", flush=True)
            labelled, dia = "", []

        results.append({"date": p["date"], "url": p["url"], "chunk": chunk,
                        "labelled": labelled, "raw": raw, "diarized": dia})
        json.dump(results, open(os.path.join(HERE, out), "w"), ensure_ascii=False, indent=1)

    # quick tallies: statements per speaker in each condition
    print("\n=== SUMMARY ===", flush=True)
    for r in results:
        rc = {}
        for cond in ("raw", "diarized"):
            from collections import Counter
            rc[cond] = Counter(x["politician"] for x in r[cond])
        print(f"{r['date']}: RAW {len(r['raw'])} stmts {dict(rc['raw'])}", flush=True)
        print(f"{' '*10} DIA {len(r['diarized'])} stmts {dict(rc['diarized'])}", flush=True)
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    fire.Fire(run)
