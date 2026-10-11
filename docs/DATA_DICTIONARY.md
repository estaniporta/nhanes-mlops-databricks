# Data dictionary

What each variable is supposed to mean, according to CDC's codebooks. This file describes
the documentation. What we actually observe in the data (missing counts, ranges, positive
rate per cycle) goes into the cycle profile table, not here.

Status values:
- verified: checked against the codebook named in "Source".
- to verify: carried over from our design notes, not yet checked.

Non-answer codes: NHANES stores "refused" and "don't know" as numbers (typically 7 and 9,
or 77 and 99, or 777 and 999, depending on the question). They are not real answers. In the
silver table they become missing values. The exact codes are listed per variable.

Cycle coverage of the verified entries so far: 2017-March 2020 only (`P_` files).
Earlier cycles still need to be compared.

## Participant and demographics (file DEMO, `P_DEMO` for 2017-March 2020)

Source: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_DEMO.htm

| Variable | Meaning | Values | Our handling | Status |
|---|---|---|---|---|
| SEQN | Participant ID, the join key across files | Integer | Key. Must be unique within a cycle. | verified |
| RIDSTATR | Interview and examination status | 1 interviewed only, 2 interviewed and examined | Not a feature. People with only 1 have no lab values, so they drop out at the HbA1c step. | verified |
| RIAGENDR | Sex | 1 male, 2 female | Model 1 feature | verified |
| RIDAGEYR | Age in years at screening | 0 to 79, and 80 means 80 or older (top-coded) | Model 1 feature. Filter: 18 or older. | verified |
| RIDEXPRG | Pregnancy status at exam | 1 pregnant (positive test or self-report), 2 not pregnant, 3 cannot ascertain, blank not released or not applicable | Filter only. Exclude 1 and 3. Keep 2 and blank. | verified |
| SDMVSTRA, SDMVPSU | Masked variance stratum and pseudo-PSU (survey design) | Stratum 149 to 172, PSU 1 to 3 in this file | Not features. Possible group key for grouped cross-validation (open item). | verified |

Notes on RIDEXPRG (from the codebook):
- It is only released for females aged 20 to 44. Everyone else is blank, including all men.
  That is why the filter excludes codes 1 and 3 instead of requiring code 2.
- Code 3 also covers people who were interviewed but not examined. Those people have no
  HbA1c and would be removed later anyway.
- CDC states that fewer than 1% of women and girls aged 8 to 19 or 45 to 59 are pregnant.
  They cannot be identified here and remain in the data. This is listed as a limitation.

## Sleep (file SLQ, `P_SLQ` for 2017-March 2020)

Source: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/P_SLQ.htm

| Variable | Meaning | Values | Our handling | Status |
|---|---|---|---|---|
| SLD012 | Usual hours of sleep on weekdays or workdays | 3 to 13.5 in half-hour steps, 2 means less than 3 hours, 14 means 14 hours or more, blank missing | Model 2 feature, with definition tag "derived from times". Codes 2 and 14 are kept as they are. | verified (2017-March 2020) |
| SLD013 | Same, for weekends or non-workdays | Same as SLD012 | Not used for now. | verified (2017-March 2020) |
| SLD010H | Hours of sleep, asked directly (2007-2014) | Whole hours, top code 12 or more | Same column as SLD012, with definition tag "asked directly". | to verify |

What the sleep number means (from the codebook):
- It is a usual night on weekdays or workdays, not last night and not a 7-day average.
- In 2015 and later it is derived from the usual bed time and wake time that the person
  reports, and rounded to the nearest half hour. It covers the main sleep period only, so
  it may miss naps or broken sleep.
- The sleep questions were asked of participants aged 16 and older.
- Before 2015-16 the number came from a direct question. This definition break is kept as
  it is and recorded in the definition tag column.

## Still to document

Each of these must be checked in the codebook for every cycle before we rely on it.

| Variable | Role | To check |
|---|---|---|
| LBXGH (file GHB) | Label source: HbA1c, percent | Units, missing codes, instrument changes by cycle |
| BMXBMI (file BMX) | Model 1 feature | Units, who was measured, missing codes |
| DIQ010 (file DIQ) | Filter: doctor-told diabetes | Codes for yes, no, borderline, refused, don't know. Wording per cycle |
| DPQ010 to DPQ090 (file DPQ) | PHQ-9 items, summed to the score | Valid codes 0 to 3, codes for refused and don't know |
| Diet totals (file DR1TOT) | Model 2 features | Which totals we use, the reliable-recall status variable, mode of administration by cycle |
| Activity items (file PAQ) | Model 2 features | Item names, units, how we turn them into minutes, absent in 2021-23 |
