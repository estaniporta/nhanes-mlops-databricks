"""Tests for src/ingest_bronze.py. They use tiny synthetic .xpt files, never real NHANES data."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pyreadstat
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ingest_bronze as ib  # noqa: E402


def write_xpt(path: Path, df: pd.DataFrame) -> Path:
    pyreadstat.write_xport(df, str(path), file_format_version=5, table_name="T")
    return path


@pytest.fixture
def two_cycles(tmp_path):
    older = pd.DataFrame(
        {"SEQN": [1.0, 2.0, 3.0], "SLD010H": [7.0, float("nan"), 12.0], "SLQ999": [1.0, 2.0, 1.0]}
    )
    newer = pd.DataFrame({"SEQN": [10.0, 11.0], "SLD010H": [6.0, 8.0]})
    return (
        write_xpt(tmp_path / "SLQ_E.xpt", older),
        write_xpt(tmp_path / "SLQ_F.xpt", newer),
    )


def test_read_xpt_adds_cycle_and_source_file(two_cycles):
    df = ib.read_xpt(two_cycles[0], "2007-2008")
    assert list(df.columns[:2]) == ["cycle", "source_file"]
    assert set(df["cycle"]) == {"2007-2008"}
    assert set(df["source_file"]) == {"SLQ_E.xpt"}
    assert len(df) == 3


def test_read_xpt_keeps_nhanes_names_and_values(two_cycles):
    df = ib.read_xpt(two_cycles[0], "2007-2008")
    assert {"SEQN", "SLD010H", "SLQ999"} <= set(df.columns)
    assert df["SLD010H"].tolist()[0] == 7.0
    assert df["SLD010H"].isna().tolist() == [False, True, False]


def test_stack_unions_columns_and_leaves_missing_ones_empty(two_cycles):
    frames = [ib.read_xpt(two_cycles[0], "2007-2008"), ib.read_xpt(two_cycles[1], "2009-2010")]
    stacked = ib.stack(frames)
    assert len(stacked) == 5
    assert "SLQ999" in stacked.columns
    older = stacked[stacked["cycle"] == "2007-2008"]
    newer = stacked[stacked["cycle"] == "2009-2010"]
    assert older["SLQ999"].notna().all()
    assert newer["SLQ999"].isna().all()


def test_text_columns_are_decoded_and_blank_becomes_none(tmp_path):
    # The last row has text, so the file does not end in blank padding (see the note in
    # test_row_count_is_what_the_file_holds below).
    df = pd.DataFrame({"SEQN": [1.0, 2.0, 3.0], "NOTE": ["abc  ", "", "zz"]})
    path = write_xpt(tmp_path / "X_E.xpt", df)
    out = ib.read_xpt(path, "2007-2008")
    assert out["NOTE"].tolist() == ["abc", None, "zz"]


def test_row_count_is_what_the_file_holds(two_cycles):
    # pandas works out the number of rows in an XPT file from its size and trailing blanks,
    # because the format stores no row count. In unusual files (a last row that ends in blank
    # text) it can drop a row. That is why the job compares every file with the codebook.
    assert len(ib.read_xpt(two_cycles[0], "2007-2008")) == 3
    assert len(ib.read_xpt(two_cycles[1], "2009-2010")) == 2


def test_check_rows():
    assert ib.check_rows("2007-2008", "DEMO_E.xpt", 10149) == (10149, "ok")
    assert ib.check_rows("2007-2008", "DEMO_E.xpt", 10148) == (10149, "MISMATCH")
    assert ib.check_rows("2007-2008", "SLQ_E.xpt", 123) == (None, "no expectation")


def test_expected_rows_keys_are_real_files():
    real = {
        (cycle, ib.file_name(stem, letter))
        for cycle, letter in ib.CYCLES.items()
        for stem in ib.TOPICS.values()
    }
    assert set(ib.EXPECTED_ROWS) <= real


def test_file_list_matches_the_download_script():
    spec = importlib.util.spec_from_file_location(
        "download_nhanes", ROOT / "scripts" / "download_nhanes.py"
    )
    dl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dl)
    from_script = {(cycle, name) for cycle, name, _ in dl.planned_files()}
    from_loader = {
        (cycle, ib.file_name(stem, letter))
        for cycle, letter in ib.CYCLES.items()
        for stem in ib.TOPICS.values()
    }
    assert from_script == from_loader
