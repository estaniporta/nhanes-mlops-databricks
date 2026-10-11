"""Load the raw NHANES .xpt files from a Unity Catalog Volume into bronze Delta tables.

One table per topic, with all four Part 1 cycles stacked (decision D04):

    bronze_demo, bronze_bmx, bronze_ghb, bronze_diq,
    bronze_slq, bronze_dpq, bronze_paq, bronze_dr1tot

Every table has two extra columns, `cycle` and `source_file`. NHANES column names and values
are left exactly as they are. Missing values become NULL (not NaN), and so do blank text
values. Nothing else is changed:
numbers stay as the doubles NHANES stores, and cleaning belongs to silver.

A table `bronze_load_log` records the row count of every file next to the row count the
CDC codebook states, where I have one. The job fails at the end if any count differs.

Run as a Databricks job (see databricks.yml) or locally with a Spark session:
    python src/ingest_bronze.py --catalog workspace --schema nhanes_demo --volume raw
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CYCLES = {"2007-2008": "E", "2009-2010": "F", "2011-2012": "G", "2013-2014": "H"}

# table suffix -> NHANES file stem
TOPICS = {
    "demo": "DEMO",
    "bmx": "BMX",
    "ghb": "GHB",
    "diq": "DIQ",
    "slq": "SLQ",
    "dpq": "DPQ",
    "paq": "PAQ",
    "dr1tot": "DR1TOT",
}

# Row counts stated in the CDC codebooks ("cumulative" count at the end of a table).
# Only counts I read myself are listed; a missing key means "no expectation".
EXPECTED_ROWS = {
    ("2007-2008", "DEMO_E.xpt"): 10149,
    ("2009-2010", "DEMO_F.xpt"): 10537,
    ("2011-2012", "DEMO_G.xpt"): 9756,
    ("2013-2014", "DEMO_H.xpt"): 10175,
    ("2007-2008", "BMX_E.xpt"): 9762,
    ("2009-2010", "BMX_F.xpt"): 10253,
    ("2013-2014", "BMX_H.xpt"): 9813,
    ("2007-2008", "GHB_E.xpt"): 6917,
    ("2009-2010", "GHB_F.xpt"): 7369,
    ("2011-2012", "GHB_G.xpt"): 6549,
    ("2013-2014", "GHB_H.xpt"): 6979,
    ("2007-2008", "DIQ_E.xpt"): 9666,
    ("2009-2010", "DIQ_F.xpt"): 10109,
    ("2011-2012", "DIQ_G.xpt"): 9364,
    ("2013-2014", "DIQ_H.xpt"): 9770,
    ("2007-2008", "DPQ_E.xpt"): 5995,
    ("2009-2010", "DPQ_F.xpt"): 6360,
    ("2011-2012", "DPQ_G.xpt"): 5615,
    ("2013-2014", "DPQ_H.xpt"): 5924,
    ("2009-2010", "SLQ_F.xpt"): 6889,
    ("2011-2012", "SLQ_G.xpt"): 6175,
    ("2013-2014", "SLQ_H.xpt"): 6464,
    ("2011-2012", "PAQ_G.xpt"): 9107,
    ("2013-2014", "PAQ_H.xpt"): 9484,
    ("2009-2010", "DR1TOT_F.xpt"): 10253,
    ("2011-2012", "DR1TOT_G.xpt"): 9338,
    ("2013-2014", "DR1TOT_H.xpt"): 9813,
}


def file_name(stem: str, letter: str) -> str:
    return f"{stem}_{letter}.xpt"


def read_xpt(path: str | Path, cycle: str) -> pd.DataFrame:
    """Read one SAS transport file and add the `cycle` and `source_file` columns.

    Text columns are decoded as latin-1 (never fails), stripped of trailing blanks, and a
    blank text value becomes None (NULL), the same as a missing number.
    """
    path = Path(path)
    df = pd.read_sas(path, format="xport", encoding="latin-1")
    # Every column that is not a number is text. (pandas 2 stores it as "object", pandas 3 as
    # "str", which turns None back into NaN, so build an explicit object column.)
    for col in df.select_dtypes(exclude="number").columns:
        values = [None if v is None or v != v else (str(v).strip() or None) for v in df[col]]
        df[col] = pd.Series(values, index=df.index, dtype=object)
    df.insert(0, "cycle", cycle)
    df.insert(1, "source_file", path.name)
    return df


def stack(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Stack frames by column name. A column missing from a cycle is empty for that cycle."""
    return pd.concat(frames, ignore_index=True, sort=False)


def check_rows(cycle: str, name: str, actual: int) -> tuple[int | None, str]:
    expected = EXPECTED_ROWS.get((cycle, name))
    if expected is None:
        return None, "no expectation"
    return expected, "ok" if expected == actual else "MISMATCH"


def nan_to_null(sdf):
    """pandas stores missing numbers as NaN. In Spark NaN is a number, not NULL, so convert."""
    from pyspark.sql import functions as F
    from pyspark.sql.types import DoubleType, FloatType

    cols = []
    for field in sdf.schema.fields:
        c = F.col(f"`{field.name}`")
        if isinstance(field.dataType, (DoubleType, FloatType)):
            c = F.when(F.isnan(c), F.lit(None)).otherwise(c)
        cols.append(c.alias(field.name))
    return sdf.select(*cols)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="nhanes_demo")
    parser.add_argument("--volume", default="raw")
    args = parser.parse_args()

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    print(f"pandas {pd.__version__}")
    root = Path(f"/Volumes/{args.catalog}/{args.schema}/{args.volume}")
    loaded_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log: list[dict] = []

    for topic, stem in TOPICS.items():
        frames = []
        table = f"{args.catalog}.{args.schema}.bronze_{topic}"
        for cycle, letter in CYCLES.items():
            name = file_name(stem, letter)
            df = read_xpt(root / cycle / name, cycle)
            expected, status = check_rows(cycle, name, len(df))
            log.append(
                {
                    "table_name": f"bronze_{topic}",
                    "cycle": cycle,
                    "source_file": name,
                    "rows": len(df),
                    "columns": df.shape[1] - 2,
                    "expected_rows": expected,
                    "check": status,
                    "loaded_utc": loaded_utc,
                }
            )
            print(f"{cycle}/{name}: {len(df):,} rows, {df.shape[1] - 2} columns, {status}")
            frames.append(df)
        stacked = stack(frames)
        sdf = nan_to_null(spark.createDataFrame(stacked))
        (
            sdf.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(table)
        )
        print(f"wrote {table}: {len(stacked):,} rows, {stacked.shape[1]} columns\n")

    from pyspark.sql.types import LongType, StringType, StructField, StructType

    log_schema = StructType(
        [
            StructField("table_name", StringType()),
            StructField("cycle", StringType()),
            StructField("source_file", StringType()),
            StructField("rows", LongType()),
            StructField("columns", LongType()),
            StructField("expected_rows", LongType()),
            StructField("check", StringType()),
            StructField("loaded_utc", StringType()),
        ]
    )
    log_sdf = spark.createDataFrame([tuple(r.values()) for r in log], schema=log_schema)
    (
        log_sdf.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{args.catalog}.{args.schema}.bronze_load_log")
    )

    bad = [r for r in log if r["check"] == "MISMATCH"]
    if bad:
        lines = "\n".join(
            f"  {r['cycle']}/{r['source_file']}: got {r['rows']}, codebook says {r['expected_rows']}"
            for r in bad
        )
        raise SystemExit(f"Row count differs from the codebook for {len(bad)} file(s):\n{lines}")
    print("All row counts that have a codebook value match.")


if __name__ == "__main__":
    main()