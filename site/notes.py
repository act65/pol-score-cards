"""The development notes: markdown files in `notes/`, rendered as site pages.

Why files rather than a database: the site is built to static HTML and served
from a CDN (see freeze.py), so there is nothing at runtime to write to. A post is
a file in the repo, reviewed in a diff like the code it describes.

Front matter is a `key: value` block between `---` fences. Deliberately not YAML:
the fields are four strings, and a parser I can read in ten lines cannot fail in
a way I have to debug at build time.

    ---
    title: Why Forthrightness isn't on the card
    date: 2026-09-26
    summary: One sentence for the index and the link preview.
    tags: attributes, coverage
    draft: true          # optional; omitted from the index and from the build
    ---

The body is trusted markdown — our own files, in our own repo — so the rendered
HTML is passed through unescaped. Anything that ever accepts a post from
elsewhere has to sanitise instead.
"""

import datetime
import functools
import os
import re

import markdown

NOTES_DIR = os.environ.get("SCORECARD_NOTES") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "notes")

_FENCE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)

# `tables` because these posts are mostly tables of numbers; `footnotes` and
# `attr_list` so a caveat can sit at the bottom rather than in a parenthesis;
# `toc` to give every heading an id worth linking to.
_EXTENSIONS = ("tables", "fenced_code", "footnotes", "attr_list", "toc", "sane_lists")


def _slug(filename):
    return os.path.splitext(os.path.basename(filename))[0]


def _parse(text, slug):
    m = _FENCE.match(text)
    if not m:
        raise ValueError(f"note {slug!r} has no front matter")
    meta, body = {}, m.group(2)
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()
    missing = {"title", "date", "summary"} - meta.keys()
    if missing:
        raise ValueError(f"note {slug!r} is missing {', '.join(sorted(missing))}")
    try:
        date = datetime.date.fromisoformat(meta["date"])
    except ValueError as e:
        raise ValueError(f"note {slug!r} has a bad date: {e}") from e
    return {
        "slug": slug,
        "title": meta["title"],
        "date": date,
        "date_display": date.strftime("%-d %B %Y"),
        "summary": meta["summary"],
        "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
        "draft": meta.get("draft", "").lower() in ("1", "true", "yes"),
        "html": markdown.markdown(body, extensions=list(_EXTENSIONS)),
    }


@functools.lru_cache(maxsize=1)
def _load():
    """Every note, newest first. Cached: a note is a file that only changes
    between deploys, and the static build renders each page once anyway."""
    notes = []
    if not os.path.isdir(NOTES_DIR):
        return tuple()
    for name in sorted(os.listdir(NOTES_DIR)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(NOTES_DIR, name)
        with open(path, encoding="utf-8") as f:
            notes.append(_parse(f.read(), _slug(name)))
    notes.sort(key=lambda n: (n["date"], n["slug"]), reverse=True)
    return tuple(notes)


def all_notes(include_drafts=False):
    return [n for n in _load() if include_drafts or not n["draft"]]


def get_note(slug):
    return next((n for n in all_notes() if n["slug"] == slug), None)
