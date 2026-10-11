# Predicting Elevated HbA1c from NHANES Data: An MLOps Pipeline (WIP)

Portfolio project: a reproducible model lifecycle (train, track, register, promote, evaluate on later data) built on public NHANES survey data.
## The research questions:
1. Do sleep, mood, diet and physical activity help to identify elevated HbA1c (5.7% or higher), beyond just using the regularly used age, sex and BMI? In other words, does adding variables like sleep, mood, diet, etc improves diabetes prediction?
2. Can a trained model still be used on a newer NHANES cycle, and what changes when it is retrained? The answer is described per cycle, not judged against a pass/fail line.


NHANES is a one-time snapshot of each participant. The model identifies who has elevated HbA1c at the time of the survey. It does not predict who will develop it later.


## Terms used in this README

| Term | Meaning here |
|---|---|
| Variable | A field as named by NHANES (for example `LBXGH`). |
| Column | The same field once it is stored in a table. |
| Feature | A column used as model input. |
| Label | The 0/1 answer the model tries to identify (HbA1c 5.7% or higher = 1). |
| Cycle | One NHANES data release (for example 2013-2014). |
| Codebook | CDC's documentation page for one data file: question text, allowed codes, counts. |
| Manifest | A CSV listing every downloaded file with its URL, size and SHA-256 fingerprint. |


## Data layers (medallion naming)

Tables are named with the "medallion" convention (bronze, silver, gold), a labelling scheme popularised by Databricks. We use it so that raw, cleaned and summarised data are never mixed.
| Layer | Content in this project |
|---|---|
| Bronze | The downloaded NHANES files loaded into tables with no changes, plus the source cycle and file name. |
| Silver | The cleaned analysis table: one row per participant, one column per variable, non-answer codes turned into missing values, label added. Models train from this layer. |
| Gold | Small summary tables with the outcome metrics per cycle and model.  |


## Data
- Source: CDC / NCHS, NHANES public-use files (.xpt, SAS transport format).
- Cycles in scope: 2007-08, 2009-10, 2011-12, 2013-14, 2015-16, 2017-March 2020 (the combined pre-pandemic files only, P_ prefix), 2021-23.
- Raw files are not committed to this repository. The manifest in `manifest/` records what was downloaded, and `python scripts/download_nhanes.py --verify` checks it.
- Data use: statistical analysis only, no attempt to identify participants, as required by the NCHS Data User Agreement.

## Population and label
- Adults (18 and older).
- Excluded: anyone answering "yes" or "borderline" to the doctor-diagnosed diabetes question (DIQ010), and anyone coded pregnant or "cannot ascertain" for pregnancy. Men and women without a pregnancy code are kept.
- Label: 1 if lab HbA1c (LBXGH) is 5.7% or higher, otherwise 0. This includes prediabetes and undiagnosed diabetes.
- The number of participants left after every filter step is recorded per cycle.

## Variables at a glance

Full definitions, allowed codes and handling rules are in docs/DATA_DICTIONARY.md. Entries marked there as "verified" were checked against the CDC codebook; the rest are still to be verified.
 
| Role | Column | What it is |
|---|---|---|
| Model 1 feature | `RIDAGEYR` | Age in years (80 and older is coded 80). |
| Model 1 feature | `RIAGENDR` | Sex (1 male, 2 female). |
| Model 1 feature | `BMXBMI` | Body mass index. |
| Model 2 feature | sleep hours | Usual hours of sleep on weekdays or workdays. Definition differs before and after 2015-16. |
| Model 2 feature | PHQ-9 score | Sum of nine mood questions, 0 to 27. |
| Model 2 features | diet totals | Selected totals from the day-1 24-hour dietary recall. |
| Model 2 features | physical activity | Minutes of activity and of sitting per day or week. |
| Label source | `LBXGH` | Lab HbA1c, percent. |
| Filter only | `DIQ010`, `RIDEXPRG` | Diabetes diagnosis question, pregnancy status. Never used as features. |
 
Model 1 uses age, sex and BMI. Model 2 uses those plus the Model 2 features. Both are
compared on the same set of participants (those with all Model 2 features present).

# Limitations (so far)
 
- Snapshot design: identifies current status, does not predict the future.
- Many predictors are self-reported and noisy; diet is a single 24-hour recall.
- Pregnancy status is only released by NHANES for women aged 20 to 44, so pregnant
  women outside that range cannot be identified. CDC reports this is under 1% of
  women and girls aged 8 to 19 and 45 to 59.
- HbA1c laboratory methods changed across cycles.
- Sleep and diet definitions differ across cycles, so performance changes may reflect
  data changes and not only drift.
- Analysis is unweighted and the bootstrap ignores the survey's clustered design, so
  results describe NHANES participants, not the US adult population.
- Demo only, not clinical.

## Repository documents
 
- [DECISIONS.md](DECISIONS.md): what was decided, alternatives considered, and why.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md): variable definitions and codes.
