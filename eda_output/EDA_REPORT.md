# PMData Exploratory Data Analysis Report

## 1. Executive Summary

This analysis covers **16 participants** across wellness, self-reported exercise (SRPE), injury, nutrition reporting, sleep, and Fitbit intraday sources. The tabular PMSys/Google/Fitbit sources contain a combined total of 6,160 records. No single pre-defined prediction target is provided; readiness is used as the primary outcome for relationship analysis.

At an aggregate level, mean wellness readiness is **4.95**, mean fatigue is **2.71**, and mean sleep score is **76.46**.

## 2. Dataset Overview

| Dataset | Rows | Columns | Main fields |
|---|---:|---:|---|
| wellness | 1,747 | 11 | Timestamp, fatigue, mood, readiness, sleep duration/quality, soreness, stress |
| srpe | 783 | 6 | End time, activity names, perceived exertion, duration |
| injury | 225 | 4 | Timestamp and injury status/body area |
| reporting | 1,569 | 7 | Date, timestamp, meals, weight, fluid, alcohol |
| sleep_score | 1,836 | 11 | Sleep timestamp and sleep score components |

### Participant overview

- Participants: **16**
- Age range: **23.00–60.00 years**
- Gender categories: **{'male': 13, 'female': 3}**
- Person type categories: **{'A': 10, 'B': 6}**
- No pre-defined target variable. `readiness` is used only as an analysis outcome.

### Column interpretation

- **participant_id:** anonymous participant identifier.
- **fatigue/mood/readiness/sleep_quality/soreness/stress:** PMSys daily ordinal wellness measures.
- **sleep_duration_h:** PMSys-reported hours of sleep.
- **perceived_exertion:** self-rated exertion scale for recorded sessions.
- **duration_min:** self-reported exercise duration.
- **overall_score and components:** Fitbit sleep quality measures.
- **steps, calories, distance, activity minutes, heart rate:** participant-level Fitbit-derived measures.

## 3. Data Quality Assessment

- Duplicate wellness rows: **0**
- Duplicate SRPE rows: **0**
- Duplicate sleep rows: **0**
- Mean missingness across sleep-score columns: **0.00%**
- Injury records with a non-empty injury value: **34.22%**
- Fitbit participant-day aggregates: **2,396 rows**
- Numerical columns with at least one IQR-rule outlier: **14**

The percentage missing in each tabular source is saved in `eda_output/missing_values_by_dataset.csv`. Values should be checked against the raw sources before imputation or modeling. IQR outlier counts are saved in `eda_output/outlier_summary.csv`; they are flags for review, not automatic removals.

## 4. Statistical Analysis

### Wellness descriptive statistics

| Metric | Mean | Median | Std. dev. | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| fatigue | 2.71 | 3.00 | 0.68 | 0.00 | 5.00 |
| mood | 3.20 | 3.00 | 0.64 | 0.00 | 5.00 |
| readiness | 4.95 | 5.00 | 1.93 | 0.00 | 10.00 |
| sleep_duration_h | 6.72 | 7.00 | 1.34 | 0.00 | 12.00 |
| sleep_quality | 3.01 | 3.00 | 0.75 | 0.00 | 5.00 |
| soreness | 2.83 | 3.00 | 0.60 | 0.00 | 5.00 |
| stress | 2.91 | 3.00 | 0.72 | 0.00 | 5.00 |

### SRPE descriptive statistics

- Mean duration: **61.23 minutes**
- Median duration: **60.00 minutes**
- Mean perceived exertion: **5.71**
- Median perceived exertion: **6.00**
- Estimated duration × exertion load mean: **352.62**

## 5. Visualizations and interpretations

- `participant_demographics.png`: compares age and demographic groups.
- `wellness_histograms.png`: shows the shape and skew of daily wellness measures.
- `wellness_boxplots.png`: highlights spread and potential outliers.
- `srpe_distributions.png`: shows typical session duration and exertion.
- `activity_categories.png`: identifies repeated activity names.
- `sleep_correlation_heatmap.png`: identifies associations among sleep components.
- `wellness_correlation_heatmap.png`: identifies wellness relationships.
- `readiness_time_series.png`: shows aggregate readiness movement over time.
- `sleep_readiness_scatter.png`: compares matched sleep-score and readiness records.
- `*_frequency.png`: shows categories in reporting and alcohol fields.

## 6. Key Findings

1. The dataset covers 16 participants and includes repeated measures over time.
2. Mean wellness readiness is 4.95; readiness has the strongest absolute relationship with fatigue (correlation 0.44).
3. Mean sleep score is 76.46, while mean resting heart rate is 58.58.
4. Restlessness and overall sleep score correlate at -0.36; lower restlessness tends to accompany better sleep score.
5. Mean SRPE duration is 61.23 minutes and mean perceived exertion is 5.71.
6. Mean estimated training load (duration × perceived exertion) is 352.62.
7. A non-empty injury is recorded in 34.22% of injury records.
8. The daily sleep-score/readiness correlation is 0.03 across matched participant-days.
9. Data completeness varies by source and participant; mean sleep-score missingness is 0.00%.
10. Repeated participant-level measurements mean that pooled row-level correlations may overstate independent evidence.

## 7. Business Insights and Recommendations

- Treat readiness and sleep as monitoring signals rather than isolated diagnosis measures.
- Prioritize missingness reduction for sleep, wellness, and participation reporting.
- Segment exercise load by participant and activity before making training recommendations.
- Investigate high-load/low-readiness periods for potential overload or recovery concerns.
- Use participant-level mixed effects or repeated-measures analysis instead of assuming independence.

## 8. Limitations

- This is observational, repeated-measures data, so associations do not prove causation.
- Time alignment is approximate: timestamps come from several reporting systems.
- Missing records may reflect non-participation or system failures, not true zero values.
- Some fields are ordinal or self-reported and may contain subjective bias.
- Participant count is small and may not generalize to broader populations.
- Fitbit intraday JSON was summarized to participant-day measures; exercise JSON and sleep JSON structures were not all incorporated.

## 9. Recommendations

1. Build a daily participant dashboard covering readiness, sleep, exertion, and injury status.
2. Establish alert rules for sustained readiness decline or unusually high training load.
3. Standardize timestamps and merge records with a validated participant-date key.
4. Audit low-completeness participants and sources before modeling.
5. Use repeated-measures models for prediction; retain participant and date as grouping variables.
6. Validate injury, soreness, and sleep findings with domain experts.

## 10. Conclusion

The PMData collection provides a useful longitudinal view of wellness, sleep, activity, and injury.
The strongest evidence is descriptive and relationship-focused rather than causal. Improved data
completeness, consistent timestamping, and participant-level modeling would make the dataset more
decision-ready for recovery and training monitoring.
