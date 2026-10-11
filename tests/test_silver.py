"""Tests for src/silver.py. Synthetic participants only, with hand-checked expected numbers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import silver as sv  # noqa: E402

NAN = float("nan")


def make_bronze(rows: list[dict]) -> dict[str, pd.DataFrame]:
    """Build the eight bronze frames from a list of per-participant overrides.

    Defaults describe a valid adult man: no diabetes, HbA1c 5.4, BMI 25, sleep 7, PHQ-9 items
    all 1 (score 9), diet present, and "no" to every activity question (0 active minutes).
    """
    default = {
        "cycle": "2007-2008",
        "RIAGENDR": 1.0,
        "RIDAGEYR": 40.0,
        "RIDEXPRG": NAN,
        "BMXBMI": 25.0,
        "LBXGH": 5.4,
        "DIQ010": 2.0,
        "SLD010H": 7.0,
        "DR1TKCAL": 2000.0,
        "DR1TCARB": 250.0,
        "DR1TTFAT": 70.0,
    }
    default.update({item: 1.0 for item in sv.PHQ9_ITEMS})
    for gate, days, mins, _ in sv.ACTIVITIES:
        default.update({gate: 2.0, days: NAN, mins: NAN})

    full = []
    for i, override in enumerate(rows, start=1):
        row = {**default, "SEQN": float(i), **override}
        full.append(row)
    df = pd.DataFrame(full)
    return {
        topic: df[cols].copy() for topic, cols in sv.REQUIRED_COLUMNS.items()
    }


@pytest.fixture
def cohort():
    """Eleven participants in 2007-2008 and two in 2013-2014, each failing one thing."""
    rows = [
        {},                                                 # 1 valid, label 0
        {"RIAGENDR": 2.0, "RIDAGEYR": 30.0, "RIDEXPRG": 1.0},  # 2 pregnant
        {"RIAGENDR": 2.0, "RIDAGEYR": 25.0, "RIDEXPRG": 3.0},  # 3 cannot ascertain
        {"RIDAGEYR": 17.0},                                 # 4 child
        {"DIQ010": 1.0},                                    # 5 diabetes yes
        {"DIQ010": 3.0},                                    # 6 borderline
        {"DIQ010": 9.0},                                    # 7 don't know
        {"LBXGH": NAN},                                     # 8 no HbA1c
        {"BMXBMI": NAN},                                    # 9 no BMI
        {"SLD010H": 77.0},                                  # 10 sleep refused
        {                                                   # 11 valid, label 1
            "RIAGENDR": 2.0, "RIDAGEYR": 50.0, "LBXGH": 6.0,
            "PAQ650": 1.0, "PAQ655": 3.0, "PAD660": 30.0,   # vigorous recreation 90 min x 2
            "PAQ620": 1.0, "PAQ625": 5.0, "PAD630": 60.0,   # moderate work 300 min
        },
        {"cycle": "2013-2014"},                             # 12 valid
        {"cycle": "2013-2014", "LBXGH": 5.7},               # 13 valid, exactly at cutoff
    ]
    return make_bronze(rows)


# ---------------------------------------------------------------- cleaning helpers


def test_clean_sleep_turns_codes_into_missing_and_keeps_12():
    out = sv.clean_sleep(pd.Series([2.0, 7.0, 12.0, 77.0, 99.0, NAN]))
    assert out.tolist()[:3] == [2.0, 7.0, 12.0]
    assert out.isna().tolist() == [False, False, False, True, True, True]


def test_phq9_sums_valid_items_and_is_missing_if_any_item_is_not_valid():
    items = pd.DataFrame(
        [
            [0, 1, 2, 3, 0, 1, 2, 3, 0],  # 12
            [1, 1, 1, 1, 1, 1, 1, 1, 7],  # refused
            [1, 1, 1, 1, 1, 1, 1, 1, 9],  # don't know
            [1, 1, 1, 1, 1, 1, 1, 1, NAN],  # blank
            [3] * 9,  # 27, the maximum
        ],
        columns=sv.PHQ9_ITEMS,
        dtype=float,
    )
    out = sv.phq9_score(items)
    assert out.iloc[0] == 12
    assert out.iloc[1:4].isna().all()
    assert out.iloc[4] == 27


@pytest.mark.parametrize(
    "gate, days, minutes, expected",
    [
        (2.0, NAN, NAN, 0.0),     # no: zero minutes, not missing
        (1.0, 3.0, 30.0, 180.0),  # 3 x 30 x weight 2
        (1.0, 77.0, 30.0, None),  # days refused
        (1.0, 99.0, 30.0, None),  # days don't know
        (1.0, 3.0, 7777.0, None),  # minutes refused
        (1.0, 3.0, 9999.0, None),  # minutes don't know
        (1.0, 3.0, NAN, None),    # minutes blank (for example removed for 24 hours or more)
        (7.0, NAN, NAN, None),    # gate refused
        (9.0, NAN, NAN, None),    # gate don't know
        (NAN, NAN, NAN, None),    # gate blank
    ],
)
def test_activity_minutes_cases(gate, days, minutes, expected):
    out = sv.activity_minutes(
        pd.Series([gate]), pd.Series([days]), pd.Series([minutes]), weight=2
    )
    if expected is None:
        assert out.isna().all()
    else:
        assert out.iloc[0] == expected


def test_active_minutes_week_adds_the_five_activities_with_weights():
    bronze = make_bronze(
        [
            {
                "PAQ605": 1.0, "PAQ610": 2.0, "PAD615": 30.0,  # vigorous work 60 x 2 = 120
                "PAQ620": 1.0, "PAQ625": 5.0, "PAD630": 60.0,  # moderate work 300
                "PAQ635": 1.0, "PAQ640": 7.0, "PAD645": 10.0,  # transport 70
                "PAQ650": 1.0, "PAQ655": 1.0, "PAD660": 45.0,  # vigorous recreation 45 x 2 = 90
                "PAQ665": 1.0, "PAQ670": 4.0, "PAD675": 15.0,  # moderate recreation 60
            }
        ]
    )
    assert sv.active_minutes_week(bronze["paq"]).iloc[0] == 120 + 300 + 70 + 90 + 60


def test_active_minutes_week_is_missing_if_one_activity_is_missing():
    bronze = make_bronze([{"PAQ650": 1.0, "PAQ655": 77.0, "PAD660": 30.0}])
    assert np.isnan(sv.active_minutes_week(bronze["paq"]).iloc[0])


# ---------------------------------------------------------------- the table


def test_one_row_per_demographics_row(cohort):
    table = sv.build_participants(cohort)
    assert len(table) == 13
    assert table["seqn"].dtype == "int64"


def test_columns_and_values_for_a_valid_participant(cohort):
    row = sv.build_participants(cohort).iloc[0]
    assert row["sex"] == "male" and row["age_years"] == 40
    assert row["bmi"] == 25 and row["hba1c_pct"] == 5.4 and row["elevated_hba1c"] == 0
    assert row["phq9_score"] == 9 and row["sleep_hours"] == 7
    assert row["active_minutes_week"] == 0
    assert row["in_common_sample"]


def test_label_uses_the_cutoff_and_stays_missing_without_hba1c(cohort):
    table = sv.build_participants(cohort).set_index("seqn")
    assert table.loc[11, "elevated_hba1c"] == 1  # 6.0
    assert table.loc[13, "elevated_hba1c"] == 1  # exactly 5.7 counts as elevated
    assert table.loc[1, "elevated_hba1c"] == 0
    assert np.isnan(table.loc[8, "elevated_hba1c"])


def test_activity_formula_on_a_participant(cohort):
    table = sv.build_participants(cohort).set_index("seqn")
    assert table.loc[11, "active_minutes_week"] == 2 * 90 + 300


def test_pregnancy_rule_keeps_blank_and_drops_codes_1_and_3(cohort):
    table = sv.build_participants(cohort).set_index("seqn")
    assert table.loc[1, "not_pregnant"]  # man, blank
    assert not table.loc[2, "not_pregnant"]
    assert not table.loc[3, "not_pregnant"]


def test_only_no_to_the_diabetes_question_is_kept(cohort):
    table = sv.build_participants(cohort).set_index("seqn")
    assert table.loc[1, "no_diabetes_dx"]
    assert not table.loc[5, "no_diabetes_dx"]  # yes
    assert not table.loc[6, "no_diabetes_dx"]  # borderline
    assert not table.loc[7, "no_diabetes_dx"]  # don't know


def test_missing_diabetes_row_is_not_kept(cohort):
    cohort["diq"] = cohort["diq"][cohort["diq"]["SEQN"] != 1.0]
    table = sv.build_participants(cohort).set_index("seqn")
    assert not table.loc[1, "no_diabetes_dx"]


# ---------------------------------------------------------------- summaries


def test_funnel_counts_for_the_first_cycle(cohort):
    f = sv.funnel(sv.build_participants(cohort))
    first = f[f["cycle"] == "2007-2008"].sort_values("step_order")
    assert first["n"].tolist() == [11, 10, 8, 5, 4, 3, 2]
    assert first["n_lost"].tolist()[1:] == [1, 2, 3, 1, 1, 1]


def test_funnel_all_cycles_adds_up(cohort):
    f = sv.funnel(sv.build_participants(cohort))
    total = f[f["cycle"] == "all cycles"].sort_values("step_order")
    assert total["n"].tolist() == [13, 12, 10, 7, 6, 5, 4]


def test_samples_and_summary(cohort):
    table = sv.build_participants(cohort)
    summary = sv.cycle_summary(table)
    common = summary[(summary["sample"] == "common") & (summary["cycle"] == "all cycles")].iloc[0]
    assert common["n"] == 4  # participants 1, 11, 12, 13
    assert common["n_positive"] == 2  # 11 and 13
    assert common["positive_rate"] == 0.5


def test_feature_missingness_counts_who_is_lost_for_model2(cohort):
    miss = sv.feature_missingness(sv.build_participants(cohort))
    first = miss[miss["cycle"] == "2007-2008"].iloc[0]
    assert first["n_model1_sample"] == 3
    assert first["missing_sleep_hours"] == 1
    assert first["n_common_sample"] == 2 and first["n_lost_for_model2"] == 1


# ---------------------------------------------------------------- guards


def test_missing_required_column_gives_a_clear_error(cohort):
    cohort["bmx"] = cohort["bmx"].drop(columns=["BMXBMI"])
    with pytest.raises(ValueError, match="BMXBMI"):
        sv.build_participants(cohort)


def test_duplicate_participants_are_rejected(cohort):
    cohort["ghb"] = pd.concat([cohort["ghb"], cohort["ghb"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicated"):
        sv.build_participants(cohort)