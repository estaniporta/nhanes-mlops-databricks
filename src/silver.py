"""Build the silver analysis table from the bronze tables (pure pandas, no Spark).

Input: one pandas DataFrame per bronze topic (see REQUIRED_COLUMNS).
Output: `build_participants` returns one row per participant (cycle + SEQN) with readable
column names, non-answer codes turned into missing values, the label, and one True/False flag
per filter step. The funnel and the summaries are computed from those flags, so every
number can be traced back to rows.

Decisions this code implements (see DECISIONS.md): D01 complete cases, D02 pregnancy filter,
D03 diabetes question, D08 prediabetes question left alone, D09 and D11 Model 2 columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

KEY = ["cycle", "SEQN"]

PHQ9_ITEMS = [f"DPQ0{i}0" for i in range(1, 10)]  # DPQ010 ... DPQ090

# (yes/no question, days per week, minutes per day, weight). Weight 2 for vigorous activity,
# 1 for moderate activity and for walking or cycling to get around (D11).
ACTIVITIES = [
    ("PAQ605", "PAQ610", "PAD615", 2),  # vigorous work
    ("PAQ620", "PAQ625", "PAD630", 1),  # moderate work
    ("PAQ635", "PAQ640", "PAD645", 1),  # walking or cycling to get around
    ("PAQ650", "PAQ655", "PAD660", 2),  # vigorous recreation
    ("PAQ665", "PAQ670", "PAD675", 1),  # moderate recreation
]
ACTIVITY_COLUMNS = [c for a in ACTIVITIES for c in a[:3]]

REQUIRED_COLUMNS = {
    "demo": KEY + ["RIAGENDR", "RIDAGEYR", "RIDEXPRG"],
    "bmx": KEY + ["BMXBMI"],
    "ghb": KEY + ["LBXGH"],
    "diq": KEY + ["DIQ010"],
    "slq": KEY + ["SLD010H"],
    "dpq": KEY + PHQ9_ITEMS,
    "paq": KEY + ACTIVITY_COLUMNS,
    "dr1tot": KEY + ["DR1TKCAL", "DR1TCARB", "DR1TTFAT"],
}

MODEL2_FEATURES = [
    "sleep_hours",
    "phq9_score",
    "energy_kcal",
    "carbohydrate_g",
    "total_fat_g",
    "active_minutes_week",
]

HBA1C_CUTOFF = 5.7

# (flag column, description). The funnel applies them one after the other.
FUNNEL_STEPS = [
    (None, "all participants in the demographics file"),
    ("is_adult", "age 18 or older"),
    ("not_pregnant", "not pregnant (codes 1 and 3 excluded, blank kept)"),
    ("no_diabetes_dx", "answered no to the diabetes question"),
    ("has_hba1c", "has an HbA1c value"),
    ("has_bmi", "has a BMI value (Model 1 sample)"),
    ("has_model2_features", "has all Model 2 features (common sample)"),
]


# ---------------------------------------------------------------- cleaning helpers


def clean_sleep(hours: pd.Series) -> pd.Series:
    """Refused (77) and don't know (99) become missing. 12 means 12 or more and stays 12."""
    return hours.where(~hours.isin([77, 99]))


def phq9_score(items: pd.DataFrame) -> pd.Series:
    """Sum of the nine PHQ-9 items, 0 to 27. Missing unless all nine answers are 0 to 3."""
    valid = items.isin([0, 1, 2, 3])
    return items.where(valid).sum(axis=1, skipna=False)


def activity_minutes(gate: pd.Series, days: pd.Series, minutes: pd.Series, weight: int) -> pd.Series:
    """Weighted minutes per week for one activity.

    A "no" answer (2) means 0 minutes. A "yes" (1) needs valid days (1 to 7) and valid
    minutes (not refused 7777, not don't know 9999, more than 0), otherwise missing.
    Refused, don't know and blank answers to the yes or no question are missing.
    """
    valid_days = days.where(days.between(1, 7))
    valid_minutes = minutes.where(~minutes.isin([7777, 9999]) & (minutes > 0))
    out = pd.Series(np.nan, index=gate.index, dtype="float64")
    yes = gate == 1
    out.loc[gate == 2] = 0.0
    out.loc[yes] = (valid_days * valid_minutes * weight).loc[yes]
    return out


def active_minutes_week(paq: pd.DataFrame) -> pd.Series:
    """Moderate-equivalent minutes per week (D11). Missing if any activity is missing."""
    parts = [
        activity_minutes(paq[gate], paq[days], paq[mins], weight)
        for gate, days, mins, weight in ACTIVITIES
    ]
    return pd.concat(parts, axis=1).sum(axis=1, skipna=False)


# ---------------------------------------------------------------- building the table


def _check_input(bronze: dict[str, pd.DataFrame]) -> None:
    for topic, cols in REQUIRED_COLUMNS.items():
        if topic not in bronze:
            raise ValueError(f"bronze table for topic '{topic}' is missing")
        missing = [c for c in cols if c not in bronze[topic].columns]
        if missing:
            raise ValueError(f"bronze_{topic} is missing columns: {missing}")
        dupes = bronze[topic].duplicated(subset=KEY).sum()
        if dupes:
            raise ValueError(f"bronze_{topic} has {dupes} duplicated (cycle, SEQN) rows")


def _with_int_key(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["SEQN"] = out["SEQN"].astype("int64")
    return out


def build_participants(bronze: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per participant in the demographics file, with columns, label and flags."""
    _check_input(bronze)
    b = {topic: _with_int_key(df[REQUIRED_COLUMNS[topic]]) for topic, df in bronze.items()}

    df = b["demo"]
    for topic in ["bmx", "ghb", "diq", "slq", "dpq", "paq", "dr1tot"]:
        df = df.merge(b[topic], on=KEY, how="left", validate="one_to_one")

    out = pd.DataFrame(
        {
            "cycle": df["cycle"],
            "seqn": df["SEQN"],
            "age_years": df["RIDAGEYR"],
            "sex": df["RIAGENDR"].map({1.0: "male", 2.0: "female"}),
            "bmi": df["BMXBMI"],
            "hba1c_pct": df["LBXGH"],
            "sleep_hours": clean_sleep(df["SLD010H"]),
            "phq9_score": phq9_score(df[PHQ9_ITEMS]),
            "energy_kcal": df["DR1TKCAL"],
            "carbohydrate_g": df["DR1TCARB"],
            "total_fat_g": df["DR1TTFAT"],
            "active_minutes_week": active_minutes_week(df[ACTIVITY_COLUMNS]),
        }
    )
    out["elevated_hba1c"] = (out["hba1c_pct"] >= HBA1C_CUTOFF).astype("float64").where(
        out["hba1c_pct"].notna()
    )

    # one True/False flag per funnel step
    out["is_adult"] = out["age_years"] >= 18
    out["not_pregnant"] = ~df["RIDEXPRG"].isin([1, 3])
    out["no_diabetes_dx"] = df["DIQ010"] == 2
    out["has_hba1c"] = out["hba1c_pct"].notna()
    out["has_bmi"] = out["bmi"].notna()
    out["has_model2_features"] = out[MODEL2_FEATURES].notna().all(axis=1)

    base = out["is_adult"] & out["not_pregnant"] & out["no_diabetes_dx"]
    out["in_model1_sample"] = base & out["has_hba1c"] & out["has_bmi"]
    out["in_common_sample"] = out["in_model1_sample"] & out["has_model2_features"]

    m1 = out[out["in_model1_sample"]]
    if m1[["age_years", "sex"]].isna().any().any():
        raise ValueError("age or sex is missing inside the Model 1 sample")
    return out


# ---------------------------------------------------------------- summaries


def funnel(participants: pd.DataFrame) -> pd.DataFrame:
    """Participants left after each filter step, per cycle and in total."""
    rows = []
    groups = [("all cycles", participants)] + [
        (cycle, g) for cycle, g in participants.groupby("cycle", sort=True)
    ]
    for cycle, g in groups:
        keep = pd.Series(True, index=g.index)
        previous = None
        for order, (flag, description) in enumerate(FUNNEL_STEPS):
            if flag is not None:
                keep = keep & g[flag]
            n = int(keep.sum())
            rows.append(
                {
                    "step_order": order,
                    "step": description,
                    "cycle": cycle,
                    "n": n,
                    "n_lost": None if previous is None else previous - n,
                }
            )
            previous = n
    return pd.DataFrame(rows).astype({"n_lost": "Int64"})


def feature_missingness(participants: pd.DataFrame) -> pd.DataFrame:
    """Inside the Model 1 sample: how many people lack each Model 2 feature, per cycle."""
    rows = []
    m1 = participants[participants["in_model1_sample"]]
    groups = [("all cycles", m1)] + [(c, g) for c, g in m1.groupby("cycle", sort=True)]
    for cycle, g in groups:
        row = {"cycle": cycle, "n_model1_sample": len(g)}
        for feature in MODEL2_FEATURES:
            row[f"missing_{feature}"] = int(g[feature].isna().sum())
        row["n_common_sample"] = int(g["has_model2_features"].sum())
        row["n_lost_for_model2"] = len(g) - row["n_common_sample"]
        rows.append(row)
    return pd.DataFrame(rows)


def cycle_summary(participants: pd.DataFrame) -> pd.DataFrame:
    """Size and positive rate per cycle, for the Model 1 sample and the common sample."""
    rows = []
    for sample, flag in [("model1", "in_model1_sample"), ("common", "in_common_sample")]:
        sub = participants[participants[flag]]
        groups = [("all cycles", sub)] + [(c, g) for c, g in sub.groupby("cycle", sort=True)]
        for cycle, g in groups:
            n_pos = int(g["elevated_hba1c"].sum())
            rows.append(
                {
                    "sample": sample,
                    "cycle": cycle,
                    "n": len(g),
                    "n_positive": n_pos,
                    "positive_rate": n_pos / len(g) if len(g) else None,
                }
            )
    return pd.DataFrame(rows)