# Checks

SQL queries that show whether each step worked, with the result to expect.
Run them in the Databricks SQL editor. Catalog `workspace`, schema `nhanes_demo`.

Status: done (with date), pending (job not run yet) or optional.

## Bronze

| # | What it checks | Expected | Status |
|---|---|---|---|
| B1 | Row count of every file matches the CDC codebook | 32 rows, no `MISMATCH`. 27 `ok` and 5 `no expectation` (BMX_G, DR1TOT_E, PAQ_E, PAQ_F, SLQ_E) | done 2026-10-11 |
| B2 | Missing numbers became NULL, not NaN | 0 in every cycle | done 2026-10-11 |
| B3 | The 15 activity columns we use have values in every cycle | every count above 0 | done 2026-10-11 |
| B4 | Rows per cycle in the demographics table | 10149, 10537, 9756, 10175 | pending |
| B5 | Which columns `bronze_paq` holds (why `PAQ_H` has 96) | list only, nothing to match | optional |

```sql
-- B1
SELECT * FROM workspace.nhanes_demo.bronze_load_log ORDER BY table_name, cycle;

-- B2
SELECT cycle, SUM(CASE WHEN isnan(SLD010H) THEN 1 ELSE 0 END) AS nan_count
FROM workspace.nhanes_demo.bronze_slq GROUP BY cycle;

-- B3
SELECT cycle,
  COUNT(PAQ605) AS paq605, COUNT(PAQ610) AS paq610, COUNT(PAD615) AS pad615,
  COUNT(PAQ620) AS paq620, COUNT(PAQ625) AS paq625, COUNT(PAD630) AS pad630,
  COUNT(PAQ635) AS paq635, COUNT(PAQ640) AS paq640, COUNT(PAD645) AS pad645,
  COUNT(PAQ650) AS paq650, COUNT(PAQ655) AS paq655, COUNT(PAD660) AS pad660,
  COUNT(PAQ665) AS paq665, COUNT(PAQ670) AS paq670, COUNT(PAD675) AS pad675
FROM workspace.nhanes_demo.bronze_paq GROUP BY cycle ORDER BY cycle;

-- B4
SELECT cycle, COUNT(*) AS n FROM workspace.nhanes_demo.bronze_demo GROUP BY cycle ORDER BY cycle;

-- B5
SELECT column_name FROM workspace.information_schema.columns
WHERE table_name = 'bronze_paq' ORDER BY ordinal_position;
```

## Silver (after `build_silver` has run)

| # | What it checks | Expected | Status |
|---|---|---|---|
| S1 | Funnel: participants left after each step | Read it. Step 0 equals B4. Look for a sudden drop, especially at step 3 (diabetes question) | pending |
| S2 | One row per participant, and as many rows as the demographics table | `n` and `n_distinct` both 40617 | pending |
| S3 | No NaN left in the float columns | 0 | pending |
| S4 | HbA1c values per cycle equal the codebook rows minus blanks | 6427, 6930, 6145, 6643 | pending |
| S5 | Sleep values per cycle equal the codebook valid answers (2009-10 to 2013-14) | 6874, 6158, 6454 for F, G, H. 2007-08: not read | pending |
| S6 | The flags agree with each other | both counts 0 | pending |
| S7 | Positive rate per cycle (shows the lab changes) | Read it. No fixed value | pending |
| S8 | Who is lost to each Model 2 feature | Read it. Shows what the complete-case rule (D01) costs | pending |

```sql
-- S1
SELECT step_order, step, cycle, n, n_lost
FROM workspace.nhanes_demo.silver_funnel ORDER BY cycle, step_order;

-- S2
SELECT COUNT(*) AS n, COUNT(DISTINCT concat(cycle, '-', seqn)) AS n_distinct
FROM workspace.nhanes_demo.silver_participants;

-- S3
SELECT COUNT(*) AS nan_rows
FROM workspace.nhanes_demo.silver_participants
WHERE isnan(bmi) OR isnan(hba1c_pct) OR isnan(sleep_hours) OR isnan(phq9_score)
   OR isnan(energy_kcal) OR isnan(carbohydrate_g) OR isnan(total_fat_g)
   OR isnan(active_minutes_week) OR isnan(age_years);

-- S4
SELECT cycle, SUM(CASE WHEN has_hba1c THEN 1 ELSE 0 END) AS n_hba1c
FROM workspace.nhanes_demo.silver_participants GROUP BY cycle ORDER BY cycle;

-- S5
SELECT cycle, COUNT(sleep_hours) AS n_sleep
FROM workspace.nhanes_demo.silver_participants GROUP BY cycle ORDER BY cycle;

-- S6
SELECT
  SUM(CASE WHEN in_common_sample AND NOT in_model1_sample THEN 1 ELSE 0 END) AS common_not_in_model1,
  SUM(CASE WHEN (elevated_hba1c IS NULL) <> (NOT has_hba1c) THEN 1 ELSE 0 END) AS label_vs_hba1c
FROM workspace.nhanes_demo.silver_participants;

-- S7
SELECT * FROM workspace.nhanes_demo.silver_cycle_summary ORDER BY sample, cycle;

-- S8
SELECT * FROM workspace.nhanes_demo.silver_feature_missingness ORDER BY cycle;
```

## Where the expected numbers come from

- B1, B4: row totals printed at the end of each codebook table.
- S4: HbA1c rows minus blank rows in the GHB codebooks (6917 - 490, 7369 - 439,
  6549 - 404, 6979 - 336).
- S5: sleep answers 2 to 11 plus "12 or more" in the SLQ codebooks (6835 + 39,
  6123 + 35, 6408 + 46).

New checks are added here whenever a step is added to the pipeline.