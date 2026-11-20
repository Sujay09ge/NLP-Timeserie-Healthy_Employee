"""
Reproducible exploratory data analysis for the PMData collection.

Run:
    python eda_pmdata.py
"""

from pathlib import Path
import ast
import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


warnings.filterwarnings("ignore")
BASE = Path(__file__).resolve().parent
OUT = BASE / "eda_output"
OUT.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 150})


def load_overview():
    """Clean the two-row participant overview header."""
    raw = pd.read_excel(BASE / "participant-overview.xlsx", sheet_name=0, header=None)
    rows = raw.iloc[2:].copy()
    columns = [
        "participant_id", "age", "height_cm", "gender", "person_type",
        "max_heart_rate", "five_km_date", "five_km_minutes",
        "five_km_seconds", "fitbit_stride_walk_cm", "fitbit_stride_run_cm",
    ]
    rows.columns = columns
    rows["participant_id"] = rows["participant_id"].astype(str).str.strip()
    numeric = [
        "age", "height_cm", "max_heart_rate", "five_km_minutes",
        "five_km_seconds", "fitbit_stride_walk_cm", "fitbit_stride_run_cm",
    ]
    for col in numeric:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    rows["five_km_date"] = pd.to_datetime(rows["five_km_date"], errors="coerce")
    rows["gender"] = (
        rows["gender"]
        .astype("string")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.lower()
    )
    rows = rows.dropna(subset=["participant_id"])
    return rows


def load_csv_sources():
    """Combine each PMSys/Google/Fitbit CSV across participants."""
    combined = {}
    frame_specs = {
        "wellness": ("pmsys", "wellness.csv", "effective_time_frame"),
        "srpe": ("pmsys", "srpe.csv", "end_date_time"),
        "injury": ("pmsys", "injury.csv", "effective_time_frame"),
        "reporting": ("googledocs", "reporting.csv", "date"),
        "sleep_score": ("fitbit", "sleep_score.csv", "timestamp"),
    }
    for name, (subdir, filename, date_col) in frame_specs.items():
        frames = []
        for participant_dir in sorted(BASE.glob("p*")):
            path = participant_dir / subdir / filename
            if not path.exists():
                continue
            df = pd.read_csv(path)
            df["participant_id"] = participant_dir.name
            if name == "reporting":
                df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce")
                df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
            else:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
            frames.append(df)
        combined[name] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    combined["wellness"]["date"] = combined["wellness"]["effective_time_frame"].dt.floor("D")
    combined["srpe"]["date"] = combined["srpe"]["end_date_time"].dt.floor("D")
    combined["injury"]["date"] = combined["injury"]["effective_time_frame"].dt.floor("D")
    combined["sleep_score"]["date"] = combined["sleep_score"]["timestamp"].dt.floor("D")
    return combined


def json_daily_metrics():
    """
    Convert intraday Fitbit JSON files into one participant-day summary.
    Values are summed for activity/volume measures and averaged for rate measures.
    """
    sum_fields = {
        "steps", "calories", "distance", "sedentary_minutes",
        "lightly_active_minutes", "moderately_active_minutes",
        "very_active_minutes",
    }
    mean_fields = {"heart_rate", "resting_heart_rate"}
    rows = []

    for participant_dir in sorted(BASE.glob("p*")):
        fitbit_dir = participant_dir / "fitbit"
        if not fitbit_dir.exists():
            continue
        for path in fitbit_dir.glob("*.json"):
            metric = path.stem
            if metric not in sum_fields | mean_fields:
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, list):
                continue

            tmp = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                dt = item.get("dateTime")
                value = item.get("value")
                if dt is None or value is None:
                    continue
                try:
                    timestamp = pd.Timestamp(dt)
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    continue
                tmp.append({"date": timestamp.normalize(), "value": numeric_value})
            if not tmp:
                continue
            metric_df = pd.DataFrame(tmp)
            grouped = (
                metric_df.groupby("date", as_index=False)["value"].sum()
                if metric in sum_fields
                else metric_df.groupby("date", as_index=False)["value"].mean()
            )
            grouped = grouped.rename(columns={"value": metric})
            grouped["participant_id"] = participant_dir.name
            rows.append(grouped)

    if not rows:
        return pd.DataFrame()
    result = None
    for frame in rows:
        if result is None:
            result = frame
            continue
        overlap = [
            col for col in frame.columns
            if col not in {"participant_id", "date"} and col in result.columns
        ]
        if overlap:
            merged = result.merge(frame, on=["participant_id", "date"], how="outer", suffixes=("_old", "_new"))
            for col in overlap:
                old_col = f"{col}_old"
                new_col = f"{col}_new"
                if old_col in merged.columns and new_col in merged.columns:
                    merged[col] = merged[old_col].combine_first(merged[new_col])
                    merged = merged.drop(columns=[old_col, new_col])
            result = merged
        else:
            result = result.merge(
                frame, on=["participant_id", "date"], how="outer"
            )
    return result


def missing_report(frames):
    parts = []
    for name, df in frames.items():
        if df.empty:
            continue
        q = df.isna().mean().mul(100).round(2).rename("missing_percent")
        q = q.to_frame()
        q["dataset"] = name
        q["column"] = q.index
        q["missing_rows"] = df.isna().sum().values
        parts.append(q.reset_index(drop=True))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def save_descriptive_tables(frames):
    for name, df in frames.items():
        numeric = df.select_dtypes(include=[np.number])
        if not numeric.empty:
            desc = numeric.describe().T
            desc["median"] = numeric.median()
            desc["mode"] = numeric.mode().iloc[0] if not numeric.mode().empty else np.nan
            desc.to_csv(OUT / f"{name}_numeric_statistics.csv")


def outlier_report(frames):
    """Summarize IQR-rule outliers for numerical columns in each tabular source."""
    rows = []
    for dataset_name, df in frames.items():
        for col in df.select_dtypes(include=[np.number]).columns:
            values = df[col].dropna()
            if values.empty:
                continue
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            count = int(((values < lower) | (values > upper)).sum())
            if count:
                rows.append({
                    "dataset": dataset_name,
                    "column": col,
                    "outlier_count": count,
                    "outlier_percent": round(count / len(values) * 100, 2),
                    "lower_bound": round(lower, 4),
                    "upper_bound": round(upper, 4),
                })
    return pd.DataFrame(rows)


def safe_filename(value):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


def make_visualizations(frames, overview, daily_fitbit):
    wellness = frames["wellness"]
    srpe = frames["srpe"]
    reporting = frames["reporting"]
    sleep = frames["sleep_score"]
    injury = frames["injury"]

    # Participant demographics
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.histplot(overview["age"].dropna(), bins=10, kde=True, ax=axes[0])
    axes[0].set_title("Participant age distribution")
    sns.countplot(data=overview, x="gender", hue="person_type", ax=axes[1])
    axes[1].set_title("Gender and A/B person type")
    fig.tight_layout()
    fig.savefig(OUT / "participant_demographics.png", bbox_inches="tight")
    plt.close(fig)

    # Wellness distributions
    wellness_cols = ["fatigue", "mood", "readiness", "sleep_duration_h",
                     "sleep_quality", "soreness", "stress"]
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes = axes.ravel()
    for i, col in enumerate(wellness_cols):
        sns.histplot(wellness[col].dropna(), bins=12, kde=True, ax=axes[i])
        axes[i].set_title(col.replace("_", " ").title())
    axes[-1].axis("off")
    fig.suptitle("Daily wellness metric distributions", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "wellness_histograms.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.boxplot(data=wellness[wellness_cols], orient="v", ax=ax)
    ax.set_title("Wellness metrics: distributions and outliers")
    ax.set_xlabel("Metric")
    ax.set_ylabel("Recorded value")
    fig.tight_layout()
    fig.savefig(OUT / "wellness_boxplots.png", bbox_inches="tight")
    plt.close(fig)

    # Activity load
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    sns.histplot(srpe["duration_min"].dropna(), bins=15, ax=axes[0])
    axes[0].set_title("Session duration")
    sns.histplot(srpe["perceived_exertion"].dropna(), bins=10, ax=axes[1])
    axes[1].set_title("Perceived exertion")
    fig.tight_layout()
    fig.savefig(OUT / "srpe_distributions.png", bbox_inches="tight")
    plt.close(fig)

    # SRPE activity categories
    activity_tokens = []
    for value in srpe["activity_names"].dropna():
        try:
            parsed = ast.literal_eval(str(value))
            if isinstance(parsed, list):
                activity_tokens.extend(str(v) for v in parsed)
        except (SyntaxError, ValueError):
            activity_tokens.extend(str(value).split())
    if activity_tokens:
        activity_counts = pd.Series(activity_tokens).value_counts().head(12)
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.barplot(x=activity_counts.values, y=activity_counts.index, ax=ax)
        ax.set_title("Most frequent activity names in self-reported sessions")
        ax.set_xlabel("Mention count")
        fig.tight_layout()
        fig.savefig(OUT / "activity_categories.png", bbox_inches="tight")
        plt.close(fig)

    # Sleep and recovery
    sleep_cols = ["overall_score", "composition_score", "revitalization_score",
                  "duration_score", "deep_sleep_in_minutes",
                  "resting_heart_rate", "restlessness"]
    fig, ax = plt.subplots(figsize=(11, 8))
    corr = sleep[sleep_cols].corr(numeric_only=True)
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="vlag", center=0, ax=ax)
    ax.set_title("Sleep score correlations")
    fig.tight_layout()
    fig.savefig(OUT / "sleep_correlation_heatmap.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=sleep, x="restlessness", y="overall_score", alpha=0.55, ax=ax)
    ax.set_title("Sleep restlessness vs. overall sleep score")
    fig.tight_layout()
    fig.savefig(OUT / "sleep_scatter.png", bbox_inches="tight")
    plt.close(fig)

    # Wellness correlation heatmap
    fig, ax = plt.subplots(figsize=(9, 7))
    wellness_corr = wellness[wellness_cols].corr(numeric_only=True)
    sns.heatmap(wellness_corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Daily wellness correlations")
    fig.tight_layout()
    fig.savefig(OUT / "wellness_correlation_heatmap.png", bbox_inches="tight")
    plt.close(fig)

    # Daily readiness trend
    trend = wellness.dropna(subset=["date", "readiness"]).groupby("date", as_index=False)["readiness"].mean()
    fig, ax = plt.subplots(figsize=(12, 5))
    sns.lineplot(data=trend, x="date", y="readiness", ax=ax)
    ax.set_title("Average participant readiness over time")
    ax.set_xlabel("Date")
    ax.set_ylabel("Readiness")
    fig.tight_layout()
    fig.savefig(OUT / "readiness_time_series.png", bbox_inches="tight")
    plt.close(fig)

    # Reporting categorical patterns
    for col in ["meals", "alcohol_consumed"]:
        counts = reporting[col].value_counts(dropna=False).head(12)
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.barplot(x=counts.values, y=[str(v) for v in counts.index], ax=ax)
        ax.set_title(f"{col.replace('_', ' ').title()} frequency")
        ax.set_xlabel("Record count")
        fig.tight_layout()
        fig.savefig(OUT / f"{col}_frequency.png", bbox_inches="tight")
        plt.close(fig)

    # Cross-source daily relationship: wellness vs daily sleep
    combined = wellness.merge(sleep, on=["participant_id", "date"], how="inner", suffixes=("_wellness", "_sleep"))
    if not combined.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.scatterplot(data=combined, x="overall_score", y="readiness", alpha=0.55, ax=ax)
        ax.set_title("Sleep score vs. wellness readiness")
        fig.tight_layout()
        fig.savefig(OUT / "sleep_readiness_scatter.png", bbox_inches="tight")
        plt.close(fig)

        corr = combined["overall_score"].corr(combined["readiness"])
        combined.to_csv(OUT / "wellness_sleep_join.csv", index=False)
        return corr
    return np.nan


def format_number(value, digits=2):
    if pd.isna(value):
        return "N/A"
    return f"{value:.{digits}f}"


def generate_report(frames, overview, daily_fitbit, missing, outliers, sleep_readiness_corr):
    wellness = frames["wellness"]
    srpe = frames["srpe"]
    sleep = frames["sleep_score"]
    reporting = frames["reporting"]
    injury = frames["injury"]

    sleep_missing = missing.loc[missing["dataset"].eq("sleep_score"), "missing_percent"].mean()
    injury_rows = injury.copy()
    injury_text = injury_rows["injuries"].fillna("").astype(str)
    injury_reported = ~injury_text.isin(["", "{}", "nan"])
    injury_rate = injury_reported.mean() * 100

    sleep_corr = sleep[["overall_score", "restlessness", "resting_heart_rate"]].corr()
    restlessness_corr = sleep_corr.loc["restlessness", "overall_score"]

    wellness_corr = wellness[["fatigue", "mood", "readiness",
                              "sleep_duration_h", "sleep_quality",
                              "soreness", "stress"]].corr()
    readiness_corr_pairs = wellness_corr["readiness"].drop("readiness").abs().sort_values(ascending=False)
    top_ready_name = readiness_corr_pairs.index[0]
    top_ready_value = wellness_corr.loc[top_ready_name, "readiness"]

    activity_load = srpe.assign(load=srpe["duration_min"] * srpe["perceived_exertion"])
    load_stats = activity_load["load"].describe()

    lines = [
        "# PMData Exploratory Data Analysis Report",
        "",
        "## 1. Executive Summary",
        "",
        f"This analysis covers **{overview['participant_id'].nunique()} participants** across wellness, "
        f"self-reported exercise (SRPE), injury, nutrition reporting, sleep, and Fitbit intraday sources. "
        f"The tabular PMSys/Google/Fitbit sources contain a combined total of "
        f"{sum(len(df) for df in frames.values()):,} records. No single pre-defined prediction target is "
        "provided; readiness is used as the primary outcome for relationship analysis.",
        "",
        f"At an aggregate level, mean wellness readiness is **{format_number(wellness['readiness'].mean())}**, "
        f"mean fatigue is **{format_number(wellness['fatigue'].mean())}**, and mean sleep score is "
        f"**{format_number(sleep['overall_score'].mean())}**.",
        "",
        "## 2. Dataset Overview",
        "",
        "| Dataset | Rows | Columns | Main fields |",
        "|---|---:|---:|---|",
    ]
    descriptions = {
        "wellness": "Timestamp, fatigue, mood, readiness, sleep duration/quality, soreness, stress",
        "srpe": "End time, activity names, perceived exertion, duration",
        "injury": "Timestamp and injury status/body area",
        "reporting": "Date, timestamp, meals, weight, fluid, alcohol",
        "sleep_score": "Sleep timestamp and sleep score components",
    }
    for name, df in frames.items():
        lines.append(
            f"| {name} | {len(df):,} | {len(df.columns)} | "
            f"{descriptions.get(name, 'Participant-date Fitbit measure')} |"
        )
    lines += [
        "",
        "### Participant overview",
        "",
        f"- Participants: **{len(overview)}**",
        f"- Age range: **{format_number(overview['age'].min())}–{format_number(overview['age'].max())} years**",
        f"- Gender categories: **{overview['gender'].dropna().value_counts().to_dict()}**",
        f"- Person type categories: **{overview['person_type'].dropna().value_counts().to_dict()}**",
        f"- No pre-defined target variable. `readiness` is used only as an analysis outcome.",
        "",
        "### Column interpretation",
        "",
        "- **participant_id:** anonymous participant identifier.",
        "- **fatigue/mood/readiness/sleep_quality/soreness/stress:** PMSys daily ordinal wellness measures.",
        "- **sleep_duration_h:** PMSys-reported hours of sleep.",
        "- **perceived_exertion:** self-rated exertion scale for recorded sessions.",
        "- **duration_min:** self-reported exercise duration.",
        "- **overall_score and components:** Fitbit sleep quality measures.",
        "- **steps, calories, distance, activity minutes, heart rate:** participant-level Fitbit-derived measures.",
        "",
        "## 3. Data Quality Assessment",
        "",
        f"- Duplicate wellness rows: **{frames['wellness'].duplicated().sum():,}**",
        f"- Duplicate SRPE rows: **{frames['srpe'].duplicated().sum():,}**",
        f"- Duplicate sleep rows: **{frames['sleep_score'].duplicated().sum():,}**",
        f"- Mean missingness across sleep-score columns: **{format_number(sleep_missing)}%**",
        f"- Injury records with a non-empty injury value: **{format_number(injury_rate)}%**",
        f"- Fitbit participant-day aggregates: **{len(daily_fitbit):,} rows**",
        f"- Numerical columns with at least one IQR-rule outlier: **{len(outliers)}**",
        "",
        "The percentage missing in each tabular source is saved in "
        "`eda_output/missing_values_by_dataset.csv`. Values should be checked against the raw sources "
        "before imputation or modeling. IQR outlier counts are saved in "
        "`eda_output/outlier_summary.csv`; they are flags for review, not automatic removals.",
        "",
        "## 4. Statistical Analysis",
        "",
        "### Wellness descriptive statistics",
        "",
        "| Metric | Mean | Median | Std. dev. | Minimum | Maximum |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    wellness_numeric = ["fatigue", "mood", "readiness", "sleep_duration_h",
                        "sleep_quality", "soreness", "stress"]
    for col in wellness_numeric:
        s = wellness[col].dropna()
        lines.append(
            f"| {col} | {format_number(s.mean())} | {format_number(s.median())} | "
            f"{format_number(s.std())} | {format_number(s.min())} | {format_number(s.max())} |"
        )

    lines += [
        "",
        "### SRPE descriptive statistics",
        "",
        f"- Mean duration: **{format_number(srpe['duration_min'].mean())} minutes**",
        f"- Median duration: **{format_number(srpe['duration_min'].median())} minutes**",
        f"- Mean perceived exertion: **{format_number(srpe['perceived_exertion'].mean())}**",
        f"- Median perceived exertion: **{format_number(srpe['perceived_exertion'].median())}**",
        f"- Estimated duration × exertion load mean: **{format_number(load_stats['mean'])}**",
        "",
        "## 5. Visualizations and interpretations",
        "",
        "- `participant_demographics.png`: compares age and demographic groups.",
        "- `wellness_histograms.png`: shows the shape and skew of daily wellness measures.",
        "- `wellness_boxplots.png`: highlights spread and potential outliers.",
        "- `srpe_distributions.png`: shows typical session duration and exertion.",
        "- `activity_categories.png`: identifies repeated activity names.",
        "- `sleep_correlation_heatmap.png`: identifies associations among sleep components.",
        "- `wellness_correlation_heatmap.png`: identifies wellness relationships.",
        "- `readiness_time_series.png`: shows aggregate readiness movement over time.",
        "- `sleep_readiness_scatter.png`: compares matched sleep-score and readiness records.",
        "- `*_frequency.png`: shows categories in reporting and alcohol fields.",
        "",
        "## 6. Key Findings",
        "",
    ]

    findings = [
        f"The dataset covers {overview['participant_id'].nunique()} participants and includes repeated measures over time.",
        f"Mean wellness readiness is {format_number(wellness['readiness'].mean())}; readiness has the strongest absolute relationship with {top_ready_name} (correlation {format_number(top_ready_value)}).",
        f"Mean sleep score is {format_number(sleep['overall_score'].mean())}, while mean resting heart rate is {format_number(sleep['resting_heart_rate'].mean())}.",
        f"Restlessness and overall sleep score correlate at {format_number(restlessness_corr)}; lower restlessness tends to accompany better sleep score.",
        f"Mean SRPE duration is {format_number(srpe['duration_min'].mean())} minutes and mean perceived exertion is {format_number(srpe['perceived_exertion'].mean())}.",
        f"Mean estimated training load (duration × perceived exertion) is {format_number(load_stats['mean'])}.",
        f"A non-empty injury is recorded in {format_number(injury_rate)}% of injury records.",
        f"The daily sleep-score/readiness correlation is {format_number(sleep_readiness_corr)} across matched participant-days.",
        f"Data completeness varies by source and participant; mean sleep-score missingness is {format_number(sleep_missing)}%.",
        f"Repeated participant-level measurements mean that pooled row-level correlations may overstate independent evidence.",
    ]
    for i, finding in enumerate(findings, 1):
        lines.append(f"{i}. {finding}")

    lines += [
        "",
        "## 7. Business Insights and Recommendations",
        "",
        "- Treat readiness and sleep as monitoring signals rather than isolated diagnosis measures.",
        "- Prioritize missingness reduction for sleep, wellness, and participation reporting.",
        "- Segment exercise load by participant and activity before making training recommendations.",
        "- Investigate high-load/low-readiness periods for potential overload or recovery concerns.",
        "- Use participant-level mixed effects or repeated-measures analysis instead of assuming independence.",
        "",
        "## 8. Limitations",
        "",
        "- This is observational, repeated-measures data, so associations do not prove causation.",
        "- Time alignment is approximate: timestamps come from several reporting systems.",
        "- Missing records may reflect non-participation or system failures, not true zero values.",
        "- Some fields are ordinal or self-reported and may contain subjective bias.",
        "- Participant count is small and may not generalize to broader populations.",
        "- Fitbit intraday JSON was summarized to participant-day measures; exercise JSON and sleep JSON structures were not all incorporated.",
        "",
        "## 9. Recommendations",
        "",
        "1. Build a daily participant dashboard covering readiness, sleep, exertion, and injury status.",
        "2. Establish alert rules for sustained readiness decline or unusually high training load.",
        "3. Standardize timestamps and merge records with a validated participant-date key.",
        "4. Audit low-completeness participants and sources before modeling.",
        "5. Use repeated-measures models for prediction; retain participant and date as grouping variables.",
        "6. Validate injury, soreness, and sleep findings with domain experts.",
        "",
        "## 10. Conclusion",
        "",
        "The PMData collection provides a useful longitudinal view of wellness, sleep, activity, and injury.",
        "The strongest evidence is descriptive and relationship-focused rather than causal. Improved data",
        "completeness, consistent timestamping, and participant-level modeling would make the dataset more",
        "decision-ready for recovery and training monitoring.",
        "",
    ]

    (OUT / "EDA_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    overview = load_overview()
    frames = load_csv_sources()
    daily_fitbit = json_daily_metrics()

    missing = missing_report(frames)
    missing.to_csv(OUT / "missing_values_by_dataset.csv", index=False)
    outliers = outlier_report(frames)
    outliers.to_csv(OUT / "outlier_summary.csv", index=False)
    overview.to_csv(OUT / "participant_overview_clean.csv", index=False)
    for name, df in frames.items():
        df.to_csv(OUT / f"{name}_combined.csv", index=False)
    if not daily_fitbit.empty:
        daily_fitbit.to_csv(OUT / "daily_fitbit_metrics.csv", index=False)

    save_descriptive_tables(frames)
    sleep_readiness_corr = make_visualizations(frames, overview, daily_fitbit)
    generate_report(frames, overview, daily_fitbit, missing, outliers, sleep_readiness_corr)

    print(f"EDA complete. Output written to: {OUT}")


if __name__ == "__main__":
    main()
