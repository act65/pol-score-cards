"""Tests for the labelling round-trip.

    cd attribute-extraction && python -m pytest tests/test_labelling.py

Hand labels are the most expensive thing in the project and the hardest to
redo, so the failure modes worth guarding are the silent ones: a rubric that
does not match the columns being asked for, and an import that quietly drops
work.
"""

import json

import pytest

import label_testset as lt


def test_every_requested_column_has_a_rubric():
    """A column with no rubric is a column labelled from memory — which is how
    the re-anchored civility scale would get encoded wrong."""
    for name in ["subject"] + lt.ATTRIBUTES:
        assert name in lt.RUBRICS, f"no rubric for {name}"
        assert lt.RUBRICS[name].strip()


def test_no_rubric_for_a_column_we_do_not_ask_for():
    for name in lt.LEGACY_ATTRIBUTES:
        assert name not in lt.RUBRICS


def test_charisma_is_gone_from_the_requested_columns():
    """Cut on 2026-08-07 at r=0.96 with civility; Focus replaced it."""
    assert "charisma" not in lt.ATTRIBUTES
    assert "focus" in lt.ATTRIBUTES


def test_civility_rubric_states_the_new_anchor():
    """The re-anchoring is the one change that silently invalidates labels made
    from the old scale, so the guide has to say so out loud."""
    rubric = lt.RUBRICS["civility"].lower()
    assert "re-anchored" in rubric
    assert "standard, not an achievement" in rubric


def test_guide_covers_every_column_and_explains_the_omissions():
    text = lt._guide_text()
    for name in ["subject"] + lt.ATTRIBUTES:
        assert f"## {name}" in text
    for name in ["forthrightness", "strength", "veracity"]:
        assert name in text, "the guide must say why this is not labelled"


# --- round-trip -------------------------------------------------------------

def _pool(tmp_path, rows):
    p = tmp_path / "pool.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return str(p)


ROW = {"statement_id": "abc123", "split": "dev", "politician": "A Person",
       "party": "Labour", "side": "opposition", "date": "2025-10-01",
       "statement": "A statement.", "gold": {}, "labelled_by": None}


def test_export_then_import_preserves_labels(tmp_path):
    pool = _pool(tmp_path, [dict(ROW)])
    csv_path = str(tmp_path / "pool.csv")
    lt.export(pool=pool, out=csv_path)

    text = (tmp_path / "pool.csv").read_text().splitlines()
    header, row = text[0].split(","), text[1].split(",")
    row[header.index("subject")] = "speaker"
    row[header.index("civility")] = "0.8"
    (tmp_path / "pool.csv").write_text(text[0] + "\n" + ",".join(row) + "\n")

    lt.import_csv(path=csv_path, pool=pool, by="tester")
    out = json.loads(open(pool).read().strip())
    assert out["gold"] == {"subject": "speaker", "civility": 0.8}
    assert out["labelled_by"] == "tester"


def test_import_requires_an_annotator_name(tmp_path):
    """Inter-annotator agreement is impossible to reconstruct after the fact."""
    pool = _pool(tmp_path, [dict(ROW)])
    csv_path = str(tmp_path / "pool.csv")
    lt.export(pool=pool, out=csv_path)
    with pytest.raises(SystemExit):
        lt.import_csv(path=csv_path, pool=pool, by=None)


@pytest.mark.parametrize("column,bad", [
    ("civility", "1.5"),          # outside 0..1
    ("civility", "high"),         # not a number
    ("subject", "themself"),      # not in the enum
])
def test_a_bad_cell_writes_nothing_at_all(tmp_path, column, bad):
    """Partial writes are worse than a failed import — you cannot tell which
    rows made it in without re-reading everything."""
    pool = _pool(tmp_path, [dict(ROW)])
    csv_path = str(tmp_path / "pool.csv")
    lt.export(pool=pool, out=csv_path)

    lines = (tmp_path / "pool.csv").read_text().splitlines()
    header, row = lines[0].split(","), lines[1].split(",")
    row[header.index(column)] = bad
    (tmp_path / "pool.csv").write_text(lines[0] + "\n" + ",".join(row) + "\n")

    with pytest.raises(SystemExit):
        lt.import_csv(path=csv_path, pool=pool, by="tester")
    assert json.loads(open(pool).read().strip())["gold"] == {}


def test_labels_on_retired_attributes_survive_a_reimport(tmp_path):
    """Someone may have labelled charisma before it was cut. The importer no
    longer asks for it, but it must not silently delete the work."""
    row = dict(ROW, gold={"charisma": 0.4})
    pool = _pool(tmp_path, [row])
    csv_path = str(tmp_path / "pool.csv")
    lt.export(pool=pool, out=csv_path)          # exports without a charisma column
    lt.import_csv(path=csv_path, pool=pool, by="tester")
    assert json.loads(open(pool).read().strip())["gold"]["charisma"] == 0.4


def test_a_blank_cell_clears_rather_than_scoring_zero(tmp_path):
    """Blank means 'not judged'. Reading it as 0.0 would invent a gold label at
    the bottom of the scale."""
    row = dict(ROW, gold={"civility": 0.9})
    pool = _pool(tmp_path, [row])
    csv_path = str(tmp_path / "pool.csv")
    lt.export(pool=pool, out=csv_path)

    lines = (tmp_path / "pool.csv").read_text().splitlines()
    header, cells = lines[0].split(","), lines[1].split(",")
    cells[header.index("civility")] = ""
    (tmp_path / "pool.csv").write_text(lines[0] + "\n" + ",".join(cells) + "\n")

    lt.import_csv(path=csv_path, pool=pool, by="tester")
    assert "civility" not in json.loads(open(pool).read().strip())["gold"]
