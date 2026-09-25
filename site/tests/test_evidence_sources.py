"""A checked score has to show what it was checked against.

Veracity and Divination are settled by search (`resolve.py`), and every verdict
carries the source URLs it was decided on. Those URLs were collected, stored and
published in examples.jsonl for weeks without any template rendering them: the
one artifact that lets a reader disagree with us, invisible. These tests are
about that not happening again silently.
"""

import collections
import re

import app
import data_access_jsonl


def _pairs_with_sources():
    """[(politician_id, attribute)] where at least one quote was checked."""
    out = []
    for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items():
        if any(e.get("evidence_urls") for e in exs):
            out.append((pid, attr))
    return out


def test_the_dataset_still_carries_searched_sources():
    """If this fails the builder stopped joining resolver output at all, and
    every test below would pass trivially against a page with nothing to show."""
    assert _pairs_with_sources(), "no published example carries evidence_urls"


def test_a_checked_quote_renders_its_verdict_and_every_source():
    c = app.app.test_client()
    pid, attr = sorted(_pairs_with_sources())[0]
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    checked = [e for e in data_access_jsonl.get_examples(pid, attr)
               if e.get("evidence_urls")]
    # One verdict block per checked quote, and every URL present as a link.
    assert html.count('class="ev-verdict') == len(checked)
    for e in checked:
        assert app._verdict_label(e["verdict"]) in html
        for u in e["evidence_urls"]:
            assert f'href="{u}"' in html, f"{u} not linked on {pid}/{attr}"


def test_an_unsettled_verdict_is_shown_as_open_not_as_checked():
    """`uncheckable` and `not_yet_due` carry real sources and no answer.

    They must render distinctly, because the score beside them is still the
    model's guess. Showing them the same way as a settled verdict would dress a
    guess in someone else's evidence.
    """
    c = app.app.test_client()
    for pid, attr in sorted(_pairs_with_sources()):
        exs = data_access_jsonl.get_examples(pid, attr)
        open_ones = [e for e in exs
                     if e.get("evidence_urls") and not e.get("resolved")]
        if not open_ones:
            continue
        html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
        assert html.count("ev-verdict-open") == len(open_ones)
        return
    raise AssertionError("no unsettled verdict in the dataset to check")


def test_no_unresolved_example_is_presented_as_resolved():
    """`resolved`, not the presence of a verdict, decides whether a score is
    checked. A row can carry sources and still be a guess."""
    for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items():
        for e in exs:
            if e.get("verdict") in ("uncheckable", "not_yet_due"):
                assert not e.get("resolved"), (pid, attr, e["verdict"])


def test_the_unverified_banner_counts_how_far_checking_has_got():
    """The banner used to say the verdict "is not yet in" on pages that by now
    show dozens of settled ones."""
    c = app.app.test_client()
    pid, attr = max(_pairs_with_sources(),
                    key=lambda k: sum(1 for e in data_access_jsonl.get_examples(*k)
                                      if e.get("resolved") and e.get("evidence_urls")))
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    n = sum(1 for e in data_access_jsonl.get_examples(pid, attr)
            if e.get("resolved") and e.get("evidence_urls"))
    assert "now been checked against sources" in html
    assert f"{n:,}" in html
    assert "verdict</em> on each claim is not yet in" not in html


def test_a_repeated_host_is_numbered():
    """Five RNZ articles must not read as one host rendered five times."""
    c = app.app.test_client()
    for pid, attr in sorted(_pairs_with_sources()):
        for e in data_access_jsonl.get_examples(pid, attr):
            urls = e.get("evidence_urls") or []
            hosts = [app._hostname(u) for u in urls]
            dupe = next((h for h in hosts if hosts.count(h) > 1), None)
            if not dupe:
                continue
            html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
            assert '<span class="ev-sn">' in html
            return
    raise AssertionError("no repeated host in the dataset to check")


def test_the_mp_page_marks_a_checked_quote_without_the_links():
    """The MP page shows a few quotes per attribute; the verdict belongs there,
    the URL list does not — six attributes of stacked links would bury it."""
    c = app.app.test_client()
    pid = next(p for p, _a in sorted(_pairs_with_sources()))
    html = c.get(f"/politician/{pid}").get_data(as_text=True)
    # Whether this MP's sampled quotes happen to include a checked one varies
    # with the seeded shuffle, so assert the weaker, stable property: if the
    # marker is there it carries no source list.
    if "mp-q-verdict" in html:
        assert 'class="ev-sources"' not in html


def test_verdict_labels_distinguish_a_statement_from_a_prediction():
    """Veracity asks "was this true", Divination "did it come true". The same
    phrase for both would misdescribe one of them."""
    assert app._verdict_label("false") != app._verdict_label("wrong")
    assert "true" in app._verdict_label("true")
    assert "came true" in app._verdict_label("correct")
    # Every verdict resolve.py can emit has a phrase, or the page prints a
    # bare enum at a reader.
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(app.__file__)),
                                    "..", "attribute-extraction"))
    import resolve
    for v in resolve.SCORED_VERDICTS | resolve.UNSCORED_VERDICTS:
        assert v in app._VERDICT_LABEL, f"{v} has no reader-facing phrase"


def test_hostname_shortens_without_losing_the_link():
    assert app._hostname("https://www.stats.govt.nz/a/b?c=1") == "stats.govt.nz"
    assert app._hostname("https://en.wikipedia.org/wiki/X") == "en.wikipedia.org"
    # Never empty: an unparseable source still has to render as something.
    assert app._hostname("nonsense") == "nonsense"
