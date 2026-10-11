"""Build the silver tables from the bronze Delta tables.

Reads the eight bronze tables (only the columns we need), builds the analysis table with
src/silver.py and writes four Delta tables:

    silver_participants          one row per participant, columns, label and funnel flags
    silver_funnel                participants left after each filter step, per cycle
    silver_feature_missingness   who is lost to each Model 2 feature, per cycle
    silver_cycle_summary         size and positive rate per cycle

Run as a Databricks job (see databricks.yml) or locally with a Spark session:
    python src/build_silver.py --catalog workspace --schema nhanes_demo
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _add_src_to_path() -> None:
    """Make the sibling modules (silver.py, ingest_bronze.py) importable.

    Databricks runs a job file through exec(), so `__file__` does not exist there. The job
    passes the folder explicitly with --src (see databricks.yml). Locally, `__file__` works.
    """
    src = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--src=")), None)
    if src is None:
        try:
            src = str(Path(__file__).resolve().parent)
        except NameError:
            src = str(Path.cwd() / "src")
    sys.path.insert(0, src)


_add_src_to_path()

import pandas as pd  # noqa: E402

import silver as sv  # noqa: E402
from ingest_bronze import nan_to_null  # noqa: E402

TABLE_FORMAT = "delta"  # a local test can switch this to "parquet"


def read_bronze(spark, catalog: str, schema: str) -> dict[str, pd.DataFrame]:
    """Read the needed columns of each bronze table into pandas."""
    out = {}
    for topic, cols in sv.REQUIRED_COLUMNS.items():
        table = f"{catalog}.{schema}.bronze_{topic}"
        sdf = spark.table(table)
        missing = [c for c in cols if c not in sdf.columns]
        if missing:
            raise ValueError(f"{table} is missing columns: {missing}")
        out[topic] = sdf.select(*[f"`{c}`" for c in cols]).toPandas()
        print(f"read {table}: {len(out[topic]):,} rows")
    return out


def to_spark(spark, pdf: pd.DataFrame, int_columns: tuple[str, ...] = ()):
    """pandas to Spark with NaN as NULL. Columns in int_columns become whole numbers."""
    from pyspark.sql import functions as F

    pdf = pdf.copy()
    for col in pdf.columns:
        if str(pdf[col].dtype).startswith("Int"):  # pandas nullable integers
            pdf[col] = pdf[col].astype("float64")
    sdf = nan_to_null(spark.createDataFrame(pdf))
    for col in int_columns:
        sdf = sdf.withColumn(col, F.col(col).cast("long"))
    return sdf


def write_table(sdf, name: str) -> None:
    (
        sdf.write.format(TABLE_FORMAT)
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(name)
    )
    print(f"wrote {name}: {sdf.count():,} rows")


def run(spark, catalog: str, schema: str) -> dict[str, pd.DataFrame]:
    bronze = read_bronze(spark, catalog, schema)
    participants = sv.build_participants(bronze)
    funnel = sv.funnel(participants)
    missingness = sv.feature_missingness(participants)
    summary = sv.cycle_summary(participants)

    prefix = f"{catalog}.{schema}"
    write_table(to_spark(spark, participants, ("elevated_hba1c",)), f"{prefix}.silver_participants")
    write_table(to_spark(spark, funnel, ("n_lost",)), f"{prefix}.silver_funnel")
    write_table(to_spark(spark, missingness), f"{prefix}.silver_feature_missingness")
    write_table(to_spark(spark, summary), f"{prefix}.silver_cycle_summary")

    pd.set_option("display.width", 200, "display.max_columns", 50)
    print("\nFunnel, all cycles:")
    print(funnel[funnel["cycle"] == "all cycles"][["step_order", "step", "n", "n_lost"]].to_string(index=False))
    print("\nFunnel, by cycle (n):")
    print(funnel[funnel["cycle"] != "all cycles"].pivot(index=["step_order", "step"], columns="cycle", values="n").to_string())
    print("\nSample sizes and positive rate:")
    print(summary.to_string(index=False))
    return {"participants": participants, "funnel": funnel, "missingness": missingness, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default="workspace")
    parser.add_argument("--schema", default="nhanes_demo")
    parser.add_argument("--src", default=None, help="folder holding silver.py (set by the job)")
    args = parser.parse_args()

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    print(f"pandas {pd.__version__}")
    run(spark, args.catalog, args.schema)


if __name__ == "__main__":
    main()