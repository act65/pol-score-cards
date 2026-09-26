"""A checked score has to show what it was checked against.

Veracity and Divination are settled by search (`resolve.py`), and every verdict
carries the source URLs it was decided on. Those URLs were collected, stored and
published in examples.jsonl for weeks without any template rendering them: the
one artifact that lets a reader disagree with us, invisible. These tests are
about that not happening again silently.
"""

import collections
import re
from html import unescape

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


# --- Whose analysis is on the page ------------------------------------------
# Three different texts have been labelled "Analysis" here and only one of them
# ever was. A checked claim has the resolver's finding, from having actually
# looked; an unchecked search-tier claim has only the extractor's description of
# what is being asserted; a text-tier attribute has the extractor's reading of
# the statement, which needs no source and IS the analysis.

def _pairs_with_findings():
    return [(pid, attr)
            for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items()
            if any(e.get("verdict_reasoning") for e in exs)]


def test_the_dataset_carries_the_resolvers_own_reasoning():
    assert _pairs_with_findings(), "no published example carries verdict_reasoning"


def test_a_checked_quote_shows_the_finding_not_the_guess():
    """The resolver's reasoning replaces the extractor's, and the extractor's
    description must not also be printed beside it."""
    c = app.app.test_client()
    pid, attr = sorted(_pairs_with_findings())[0]
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    # Resolver reasoning is full of apostrophes and quotation marks, which the
    # template escapes; compare prose against the unescaped page.
    text = unescape(html)
    checked = [e for e in data_access_jsonl.get_examples(pid, attr)
               if e.get("verdict_reasoning")]
    assert html.count('class="ev-analysis ev-finding"') == len(checked)
    for e in checked:
        lead, _rest = app._split_finding(e["verdict_reasoning"])
        assert lead[:80] in text, "the finding's opening is not on the page"
        # The guessed description of the same quote must be gone.
        if e.get("explanation"):
            assert e["explanation"] not in text


def test_an_unchecked_search_claim_is_not_labelled_analysis():
    """It is a description of what was asserted, not a verdict on it. Calling it
    "Analysis" is what made a guess read like a check."""
    c = app.app.test_client()
    pid, attr = sorted(_pairs_with_findings())[0]
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    # "The claim:" is for a row the resolver has NOT reached. A pending row is
    # also resolved=False, but the resolver did reach it and its reasoning
    # explains why the claim cannot be settled yet — so that renders as
    # "Finding:", next to the amber "searched — too early to tell" chip.
    untouched = [e for e in data_access_jsonl.get_examples(pid, attr)
                 if not e.get("resolved") and e.get("explanation")
                 and not e.get("verdict_reasoning")]
    assert untouched, "no unresolved search-tier quote on this page to check"
    assert html.count("The claim:") == len(untouched)
    assert "Analysis:" not in html


def test_a_pending_row_shows_the_resolvers_reasoning_not_the_guess():
    """It has no score, but the resolver still explained why. That is worth more
    than the extractor's description of the claim."""
    for (pid, attr), exs in data_access_jsonl._EXAMPLES_BY_PAIR.items():
        pend = [e for e in exs if e.get("pending") and e.get("verdict_reasoning")]
        if not pend:
            continue
        html = app.app.test_client().get(
            f"/attribute/{pid}/{attr}").get_data(as_text=True)
        assert "ev-verdict-open" in html      # amber: searched, unsettled
        assert "ev-finding" in html          # and its reasoning is shown
        return
    raise AssertionError("no pending row carries resolver reasoning")


def test_a_text_tier_attribute_still_says_analysis():
    """Civility/Rigor/Specificity/Focus need no source: the statement is the
    evidence. Relabelling those would be a regression, not a fix."""
    c = app.app.test_client()
    pid, attr = next(((p, a) for (p, a), exs
                      in data_access_jsonl._EXAMPLES_BY_PAIR.items()
                      if a == "Civility" and len(exs) > 5), (None, None))
    assert pid, "no Civility page with evidence"
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    assert "Analysis:" in html
    assert "The claim:" not in html
    assert "ev-finding" not in html


def test_the_long_working_is_behind_a_disclosure_not_dumped_inline():
    """Median finding is ~1,000 characters and a page can hold sixteen."""
    c = app.app.test_client()
    pid, attr = max(_pairs_with_findings(),
                    key=lambda k: sum(1 for e in data_access_jsonl.get_examples(*k)
                                      if e.get("verdict_reasoning")))
    html = c.get(f"/attribute/{pid}/{attr}").get_data(as_text=True)
    long_ones = [e for e in data_access_jsonl.get_examples(pid, attr)
                 if e.get("verdict_reasoning")
                 and app._split_finding(e["verdict_reasoning"])[1]]
    assert html.count('class="ev-more"') == len(long_ones)


def test_splitting_a_finding_never_loses_or_duplicates_a_word():
    """lead + " " + rest must reconstruct the original exactly, for every
    finding in the dataset — a split that drops a clause would quietly change
    what we are claiming a source says."""
    seen = 0
    for exs in data_access_jsonl._EXAMPLES_BY_PAIR.values():
        for e in exs:
            r = e.get("verdict_reasoning")
            if not r:
                continue
            seen += 1
            lead, rest = app._split_finding(r)
            assert (lead if not rest else f"{lead} {rest}") == r.strip()
    assert seen, "no findings to check"


def test_splitting_never_breaks_a_word_in_half():
    """No space inside the limit used to cut mid-word, rendering the word with a
    space through the middle across the two elements."""
    lead, rest = app._split_finding("x" * 300)
    assert rest == "" and lead == "x" * 300
    lead, rest = app._split_finding("word word word " + "y" * 400)
    assert lead == "word word word" and rest == "y" * 400
    assert app._split_finding("") == ("", "")
