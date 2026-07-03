import pandas as pd
import plotly.express as px
import streamlit as st

from survey_dashboard import (
    apply_plot_theme,
    apply_sidebar_filters,
    distribution_insight,
    find_column,
    load_survey_workbook,
    map_insight,
    normalize_common_columns,
    numeric_insight,
    option_label,
    option_columns,
    option_insight,
    quality_insight,
    render_histogram,
    render_key_field_quality_summary,
    render_livestock_summary,
    render_daily_fuel_usage,
    render_location_map,
    render_option_counts,
    render_person_meals,
    render_quality_notes,
    render_summary_panel,
    render_value_counts,
    shorten_chart_label,
    truthy_count,
    unique_chart_key,
)
from translation import translate_display_text
from ui_theme import PLOTLY_COLORWAY, apply_global_theme, render_footer, render_page_header


@st.cache_data(show_spinner="Loading KPT data...")
def load_kpt_data(_cache_version="kpt_tor_analysis_v2"):
    bu = normalize_common_columns(load_survey_workbook("Clean Data KPT BU.xlsx"))
    nbu = normalize_common_columns(load_survey_workbook("Clean Data KPT NBU.xlsx"))
    bu = bu.copy()
    nbu = nbu.copy()
    for frame in (bu, nbu):
        if "district" in frame.columns:
            frame["district"] = frame["district"].replace({"Band": "Bandung"})
    bu["dataset"] = "Biogas User"
    nbu["dataset"] = "Non-Biogas User"
    combined = pd.concat([bu, nbu], ignore_index=True, sort=False)
    return bu, nbu, combined


KPT_FUEL_DELTA_COLUMNS = {
    "LPG": ["9a_lpg_delta_b_a", "9a_lpg_delta_d_c", "9a_lpg_delta_f_e"],
    "Firewood": ["12a_firewood_delta_b_a", "12a_firewood_delta_d_c", "12a_firewood_delta_f_e"],
    "Kerosene": ["15a_kerosene_delta_b_a", "15a_kerosene_delta_d_c", "15a_kerosene_delta_f_e"],
}

KPT_DURATION_COLUMNS = {
    "LPG": "5e_LPG_duration",
    "Firewood": "5e_firewood_duration",
    "Kerosene": "5e_kerosene_duration",
    "Biogas": "5e_biogas_duration",
}

KPT_MIN_COMPARISON_HOUSEHOLDS = 10

KPT_MEAL_SPECS = {
    "Breakfast": ("4c_fam_members_breakfast", ["4c_men", "4c_women", "4c_children", "4c_elders"]),
    "Lunch": ("4d_fam_members_lunch", ["4d_men", "4d_women", "4d_children", "4d_elders"]),
    "Dinner": ("4e_fam_members_dinner", ["4e_men", "4e_women", "4e_children", "4e_elders"]),
    "Warm Water": ("4f_fam_members_warmwater", ["4f_men", "4f_women", "4f_children", "4f_elders"]),
}

KPT_GROUP_LABELS = {
    "men": "Men",
    "women": "Women",
    "children": "Children",
    "elders": "Older People",
}


def normalize_meal_frequency(value):
    text = str(value).strip().lower()
    if "lebih dari 3" in text or "more than 3" in text:
        return "More Than 3 Meal Times"
    if "3 kali" in text or "3 meal" in text:
        return "3 Meal Times"
    if "2 kali" in text or "2 meal" in text:
        return "2 Meal Times"
    if "1 kali" in text or "1 meal" in text:
        return "1 Meal Time"
    return translate_display_text(value)


def dataset_groups(data):
    return data.groupby("dataset") if "dataset" in data.columns else [("Current Dataset", data)]


def find_best_filled_column(data, keywords):
    matches = [
        column for column in data.columns
        if all(keyword.casefold() in str(column).casefold() for keyword in keywords)
    ]
    if not matches:
        return None
    return max(matches, key=lambda column: int(data[column].notna().sum()))


def household_stock_column(data, dataset_name):
    candidates = {
        "Biogas User": "5f. Apakah stok bahan bakar memasak tersebut hanya untuk keluarga?",
        "Non-Biogas User": "5f. Stok hanya untuk keluarga?",
    }
    column = candidates.get(dataset_name)
    if column in data.columns:
        return column
    return find_column(data, keywords=["stok", "keluarga"])


def meal_consistency_mask(data):
    masks = []
    for meal, (total_column, group_columns) in KPT_MEAL_SPECS.items():
        if meal == "Warm Water" or total_column not in data.columns:
            continue
        available_groups = [column for column in group_columns if column in data.columns]
        if not available_groups:
            continue
        total = pd.to_numeric(data[total_column], errors="coerce")
        group_total = data[available_groups].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
        masks.append(total.notna() & group_total.notna() & total.eq(group_total))
    if not masks:
        return pd.Series(False, index=data.index)
    return pd.concat(masks, axis=1).all(axis=1)


def complete_person_meal_mask(data):
    required = []
    for meal, (total_column, group_columns) in KPT_MEAL_SPECS.items():
        if meal == "Warm Water":
            continue
        required.extend([total_column] + group_columns)
    available = [column for column in required if column in data.columns]
    if len(available) != len(required):
        return pd.Series(False, index=data.index)
    return data[available].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)


def assessment_date_columns(data):
    candidates = [
        column for column in data.columns
        if "date_asessment" in str(column) or "d4ate_asessment" in str(column)
    ]
    ordered = [
        column for column in ["7a_date_asessment1", "7a_date_asessment2", "7a_date_asessment3"]
        if column in candidates
    ]
    remaining = [column for column in candidates if column not in ordered]
    if remaining:
        ordered.append(max(remaining, key=lambda column: int(pd.to_datetime(data[column], errors="coerce").notna().sum())))
    return ordered


def normalize_duration_minutes(series):
    """Normalize Excel-hour fractions and minute entries to minutes per day."""
    values = pd.to_numeric(series, errors="coerce")
    hour_like = values.gt(0) & values.le(6)
    return values.where(~hour_like, values * 60)


def duration_insight(data, column, label):
    if not column or column not in data.columns:
        return None
    values = normalize_duration_minutes(data[column]).dropna()
    if values.empty:
        return None
    return (
        f"{label}: median {values.median():.0f} minutes/day and average {values.mean():.1f} minutes/day "
        f"from {len(values):,} valid numeric records."
    )


def total_person_meals(data):
    meal_columns = [
        "4c_fam_members_breakfast",
        "4d_fam_members_lunch",
        "4e_fam_members_dinner",
    ]
    available = [column for column in meal_columns if column in data.columns]
    if not available:
        return pd.Series(index=data.index, dtype=float)
    return data[available].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)


def build_measured_fuel_records(data):
    rows = []
    datasets = data["dataset"] if "dataset" in data.columns else pd.Series("Current Dataset", index=data.index)
    person_meals = total_person_meals(data)
    for fuel, columns in KPT_FUEL_DELTA_COLUMNS.items():
        for measurement, column in enumerate(columns, start=1):
            if column not in data.columns:
                continue
            values = pd.to_numeric(data[column], errors="coerce")
            for index in values[values.notna()].index:
                value = float(values.loc[index])
                meals = person_meals.get(index, pd.NA)
                rows.append({
                    "Respondent Key": f"{datasets.loc[index]}-{index}",
                    "Dataset": datasets.loc[index],
                    "Fuel": fuel,
                    "Measurement": f"Interval {measurement}",
                    "Consumption (kg)": value,
                    "Person-Meals": meals,
                    "Negative Reading": value < 0,
                    "kg per Person-Meal": value / meals if pd.notna(meals) and meals > 0 and value >= 0 else pd.NA,
                })
    return pd.DataFrame(rows)


def build_household_fuel_metrics(data):
    rows = []
    datasets = data["dataset"] if "dataset" in data.columns else pd.Series("Current Dataset", index=data.index)
    person_meals = total_person_meals(data)
    for fuel, configured_columns in KPT_FUEL_DELTA_COLUMNS.items():
        columns = [column for column in configured_columns if column in data.columns]
        if not columns:
            continue
        measurements = data[columns].apply(pd.to_numeric, errors="coerce")
        valid_measurements = measurements.where(measurements.ge(0))
        for index in measurements.index[measurements.notna().any(axis=1)]:
            valid_values = valid_measurements.loc[index].dropna()
            if valid_values.empty:
                continue
            meals = person_meals.get(index, pd.NA)
            average_daily = float(valid_values.mean())
            rows.append({
                "Respondent Key": f"{datasets.loc[index]}-{index}",
                "Dataset": datasets.loc[index],
                "Fuel": fuel,
                "Average Consumption per Measurement Day (kg)": average_daily,
                "Median Consumption per Measurement Day (kg)": float(valid_values.median()),
                "Valid Measurement Intervals": int(valid_values.size),
                "Recorded Measurement Intervals": int(measurements.loc[index].notna().sum()),
                "Negative Measurement Intervals": int(measurements.loc[index].lt(0).sum()),
                "Complete Three-Interval Measurement": int(valid_values.size) == len(columns),
                "Person-Meals": meals,
                "kg per Person-Meal per Measurement Day": (
                    average_daily / meals if pd.notna(meals) and meals > 0 else pd.NA
                ),
            })
    return pd.DataFrame(rows)


def stove_chart_prefixes(dataset):
    if dataset == "bu":
        return {
            "Before biogas": "5a_1. Sebelum menggunakan biogas, jenis kompor apa saja yang Anda miliki?",
            "Current": "5a_2. Setelah menggunakan biogas, jenis kompor apa saja yang Anda miliki saat ini?",
            "Used in last 24 hours": "5a_3. Tipe kompor digunakan dalam 24 jam terakhir",
        }
    return {
        "Current": "5a_1. Kompor apa yang sekarang dimiliki?",
        "Used in last 24 hours": "5a_2. Tipe kompor digunakan dalam 24 jam terakhir",
    }


def truthy_mask(series):
    cleaned = series.fillna("").astype(str).str.strip().str.casefold()
    return ~cleaned.isin(["", "0", "0.0", "false", "no", "tidak", "nan", "none"])


def normalized_stove_type(column):
    label = translate_display_text(option_label(column).replace(".1", "").strip())
    normalized = label.casefold()
    if "biogas" in normalized:
        return "Biogas Stove"
    if "lpg" in normalized:
        return "LPG Stove"
    if "kayu" in normalized or "firewood" in normalized:
        return "Firewood Stove"
    if "minyak" in normalized or "kerosene" in normalized:
        return "Kerosene Stove"
    if "listrik" in normalized or "electric" in normalized:
        return "Electric Cooking Appliance"
    return label


def dataset_stove_prefix(dataset_name, phase):
    dataset_key = "bu" if dataset_name == "Biogas User" else "nbu"
    return stove_chart_prefixes(dataset_key).get(phase)


def stove_option_masks(data, prefix):
    if not prefix:
        return {}
    return {
        normalized_stove_type(column): truthy_mask(data[column])
        for column in option_columns(data, prefix)
    }


def stove_profile_records(data, phases):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        for phase in phases:
            masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, phase))
            for stove_type, mask in masks.items():
                count = int(mask.sum())
                rows.append({
                    "Dataset": dataset_name,
                    "Phase": phase,
                    "Stove Type": stove_type,
                    "Respondents": count,
                    "Percent of Households": count / len(subset) * 100 if len(subset) else 0,
                    "Dataset N": len(subset),
                })
    return pd.DataFrame(rows)


def render_stove_profile(data, phases, title, key_prefix, color_field="Phase"):
    chart_data = stove_profile_records(data, phases)
    chart_data = chart_data[chart_data["Respondents"] > 0] if not chart_data.empty else chart_data
    if chart_data.empty:
        st.info(f"No valid stove data is available for this chart: {title}")
        return
    fig = px.bar(
        chart_data,
        x="Stove Type",
        y="Percent of Households",
        color=color_field,
        barmode="group",
        title=title,
        text="Percent of Households",
        hover_data={
            "Respondents": True,
            "Dataset N": True,
            "Percent of Households": ":.1f",
        },
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis_title="Households (%)",
        yaxis_range=[0, 112],
        xaxis_tickangle=-15,
    )
    st.plotly_chart(
        apply_plot_theme(fig),
        use_container_width=True,
        key=unique_chart_key(f"{key_prefix}_stove_profile_{'_'.join(phases)}"),
    )
    st.caption("Multiple stove types may be selected, so percentages across stove types can exceed 100%.")


def stove_count_per_household(data, prefix):
    masks = stove_option_masks(data, prefix)
    if not masks:
        return pd.Series(index=data.index, dtype=float)
    return pd.concat(masks.values(), axis=1).sum(axis=1)


def stacking_category(value):
    if value <= 0:
        return "No Stove Recorded"
    if value == 1:
        return "1 Stove Type"
    if value == 2:
        return "2 Stove Types"
    return "3+ Stove Types"


def render_stove_stacking(data, phases, title, key_prefix):
    rows = []
    category_order = ["No Stove Recorded", "1 Stove Type", "2 Stove Types", "3+ Stove Types"]
    for dataset_name, subset in dataset_groups(data):
        for phase in phases:
            counts = stove_count_per_household(subset, dataset_stove_prefix(dataset_name, phase))
            if counts.empty:
                continue
            distribution = counts.apply(stacking_category).value_counts()
            for category in category_order:
                count = int(distribution.get(category, 0))
                rows.append({
                    "Dataset": dataset_name,
                    "Phase": phase,
                    "Stove Stacking": category,
                    "Respondents": count,
                    "Percent of Households": count / len(subset) * 100 if len(subset) else 0,
                    "Average Stove Types": counts.mean(),
                })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info(f"No valid stove-stacking data is available for this chart: {title}")
        return
    color_field = "Dataset" if chart_data["Dataset"].nunique() > 1 else "Phase"
    fig = px.bar(
        chart_data,
        x="Stove Stacking",
        y="Percent of Households",
        color=color_field,
        barmode="group",
        category_orders={"Stove Stacking": category_order},
        title=title,
        text="Percent of Households",
        hover_data={"Respondents": True, "Average Stove Types": ":.2f", "Percent of Households": ":.1f"},
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig.update_layout(yaxis_title="Households (%)", yaxis_range=[0, 112], xaxis_tickangle=-10)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_stacking"))


def stove_use_mask(data, dataset_name, fuel):
    prefix = dataset_stove_prefix(dataset_name, "Used in last 24 hours")
    masks = stove_option_masks(data, prefix)
    target = {
        "LPG": "LPG Stove",
        "Firewood": "Firewood Stove",
        "Kerosene": "Kerosene Stove",
        "Biogas": "Biogas Stove",
    }.get(fuel)
    return masks.get(target, pd.Series(False, index=data.index))


def render_kpt_duration_chart(data, key_prefix):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        for fuel, column in KPT_DURATION_COLUMNS.items():
            if column not in subset.columns:
                continue
            used_mask = stove_use_mask(subset, dataset_name, fuel)
            values = normalize_duration_minutes(subset.loc[used_mask, column])
            values = values[values.gt(0)].dropna()
            if values.empty:
                continue
            rows.append({
                "Dataset": dataset_name,
                "Stove/Fuel": fuel,
                "Median Minutes/Day": values.median(),
                "Average Minutes/Day": values.mean(),
                "Valid N": len(values),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("No validated stove-duration data is available for the current filter.")
        return
    fig = px.bar(
        chart_data,
        x="Stove/Fuel",
        y="Median Minutes/Day",
        color="Dataset" if chart_data["Dataset"].nunique() > 1 else None,
        barmode="group",
        title="Median Daily Stove Active Duration (24-Hour Users Only)",
        text_auto=".0f",
        hover_data={"Average Minutes/Day": ":.1f", "Valid N": True},
    )
    if chart_data["Dataset"].nunique() == 1:
        fig.update_traces(marker_color=PLOTLY_COLORWAY[2])
    fig.update_layout(yaxis_title="Median Minutes per Day")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_duration_minutes"))
    st.caption(
        "Only households reporting use of the corresponding stove in the last 24 hours are included. "
        "Positive numeric values up to 6 are treated as Excel/hour values and converted to minutes; "
        "non-numeric date values and zero durations are excluded."
    )


def kpt_sample_summary(data, key_prefix):
    metrics = build_household_fuel_metrics(data)
    insights = []
    caveats = []
    person_meals = total_person_meals(data)
    complete_meals = complete_person_meal_mask(data)

    if metrics["Dataset"].nunique() <= 1:
        dataset_name = data["dataset"].iloc[0] if "dataset" in data.columns and not data.empty else "Current Dataset"
        lpg = metrics[(metrics["Dataset"].eq(dataset_name)) & (metrics["Fuel"].eq("LPG"))]
        normalized_lpg = lpg["kg per Person-Meal per Measurement Day"].dropna()
        if not normalized_lpg.empty:
            insights.append(
                f"Median normalized LPG consumption was {normalized_lpg.median():.3f} "
                "kg/person-meal/measurement day."
            )
        used_prefix = dataset_stove_prefix(dataset_name, "Used in last 24 hours")
        stove_counts = stove_count_per_household(data, used_prefix)
        if not stove_counts.empty:
            insights.append(
                f"{stove_counts.ge(2).mean() * 100:.1f}% of households used at least two stove types in the "
                "last 24 hours."
            )
        if person_meals.notna().any():
            insights.append(
                f"Median recorded cooking load was {person_meals.median():.1f} person-meals per household."
            )
    else:
        normalized = metrics.dropna(subset=["kg per Person-Meal per Measurement Day"])
        lpg = normalized[normalized["Fuel"].eq("LPG")]
        summary = lpg.groupby("Dataset")["kg per Person-Meal per Measurement Day"].agg(["median", "count"])
        if {"Biogas User", "Non-Biogas User"}.issubset(summary.index):
            bu = summary.loc["Biogas User"]
            nbu = summary.loc["Non-Biogas User"]
            if min(int(bu["count"]), int(nbu["count"])) >= KPT_MIN_COMPARISON_HOUSEHOLDS and nbu["median"] != 0:
                difference = (bu["median"] / nbu["median"] - 1) * 100
                direction = "lower" if difference < 0 else "higher"
                insights.append(
                    f"LPG median: {bu['median']:.3f} kg/person-meal/day for Biogas Users versus "
                    f"{nbu['median']:.3f} for Non-Biogas Users ({abs(difference):.1f}% {direction} for Biogas Users)."
                )
        age_parts = []
        meal_parts = []
        for dataset_name, subset in dataset_groups(data):
            age = pd.to_numeric(subset.get("age"), errors="coerce")
            meals = total_person_meals(subset)
            if age.notna().any():
                age_parts.append(f"{dataset_name}: {age.mean():.1f} years")
            if meals.notna().any():
                meal_parts.append(f"{dataset_name}: {meals.median():.1f}")
        if age_parts:
            insights.append("Mean respondent age - " + "; ".join(age_parts) + ".")
        if meal_parts:
            insights.append("Median household person-meals - " + "; ".join(meal_parts) + ".")

    if complete_meals.any():
        insights.append(
            f"Complete person-meal records are available for {complete_meals.mean() * 100:.1f}% of households."
        )
    caveats.extend([
        "Source structure: four consecutive dates and three intervals; TOR requirement: one 24-hour campaign.",
        "Normal-day eligibility is unconfirmed, and firewood moisture content is unavailable.",
    ])
    render_summary_panel("KPT Performance Overview", insights, caveats=caveats)


def render_kpt_overview_metrics(data):
    metrics = build_household_fuel_metrics(data)
    interval_records = build_measured_fuel_records(data)
    complete_meals = complete_person_meal_mask(data)
    negative_count = int(interval_records["Negative Reading"].sum()) if not interval_records.empty else 0
    cols = st.columns(4)

    if "dataset" in data.columns and data["dataset"].nunique() > 1:
        lpg_counts = metrics[metrics["Fuel"].eq("LPG")].groupby("Dataset")["Respondent Key"].nunique()
        bu_lpg = int(lpg_counts.get("Biogas User", 0))
        nbu_lpg = int(lpg_counts.get("Non-Biogas User", 0))
        common_provinces = 0
        if "province" in data.columns:
            province_sets = [set(subset["province"].dropna()) for _, subset in dataset_groups(data)]
            common_provinces = len(set.intersection(*province_sets)) if province_sets else 0
        cols[0].metric("Valid LPG Households", f"{bu_lpg} BU / {nbu_lpg} NBU")
        cols[1].metric("Complete Person-Meals", f"{complete_meals.mean() * 100:.1f}%")
        cols[2].metric("Common Provinces", f"{common_provinces}")
        cols[3].metric("Negative Intervals", f"{negative_count}")
    else:
        lpg_households = metrics.loc[metrics["Fuel"].eq("LPG"), "Respondent Key"].nunique()
        person_meals = total_person_meals(data)
        cols[0].metric("Valid LPG Households", f"{lpg_households:,}")
        cols[1].metric("Complete Person-Meals", f"{complete_meals.mean() * 100:.1f}%")
        cols[2].metric("Median Person-Meals", f"{person_meals.median():.1f}" if person_meals.notna().any() else "-")
        cols[3].metric("Negative Intervals", f"{negative_count}")


def render_kpt_overview_readiness(data, key_prefix):
    metrics = build_household_fuel_metrics(data)
    if metrics.empty:
        st.info("Measured-fuel readiness data is not available for the current filter.")
        return
    dataset_sizes = data.groupby("dataset").size() if "dataset" in data.columns else pd.Series({"Current Dataset": len(data)})
    rows = []
    for (dataset_name, fuel), subset in metrics.groupby(["Dataset", "Fuel"]):
        denominator = int(dataset_sizes.get(dataset_name, len(data)))
        valid_households = subset["Respondent Key"].nunique()
        complete_households = int(subset["Complete Three-Interval Measurement"].sum())
        for status, count in [
            ("At Least One Valid Interval", valid_households),
            ("Complete Three Intervals", complete_households),
        ]:
            rows.append({
                "Dataset": dataset_name,
                "Fuel": fuel,
                "Measurement Status": status,
                "Households": count,
                "Share of Dataset (%)": count / denominator * 100 if denominator else 0,
            })
    chart_data = pd.DataFrame(rows)
    fig = px.bar(
        chart_data,
        x="Fuel",
        y="Share of Dataset (%)",
        color="Measurement Status",
        facet_col="Dataset" if chart_data["Dataset"].nunique() > 1 else None,
        barmode="group",
        title="Measured-Fuel Readiness by Dataset",
        text="Share of Dataset (%)",
        hover_data=["Households"],
        category_orders={"Fuel": ["LPG", "Firewood", "Kerosene"]},
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig.update_yaxes(range=[0, 112])
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0),
        legend_title_text="Measurement Status",
        margin=dict(b=110),
    )
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_overview_readiness"))


def render_kpt_baseline_comparability(data, key_prefix):
    if "dataset" not in data.columns or data["dataset"].nunique() < 2:
        return
    rows = []
    for dataset_name, subset in dataset_groups(data):
        measures = {
            "Respondent Age": pd.to_numeric(subset.get("age"), errors="coerce"),
            "Household Size": pd.to_numeric(subset.get("hh_members"), errors="coerce"),
            "Person-Meals": total_person_meals(subset),
        }
        for measure, values in measures.items():
            values = values.dropna()
            if values.empty:
                continue
            rows.append({
                "Dataset": dataset_name,
                "Measure": measure,
                "Mean": values.mean(),
                "Median": values.median(),
                "Valid N": len(values),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return
    fig = px.bar(
        chart_data,
        x="Dataset",
        y="Mean",
        color="Dataset",
        facet_col="Measure",
        facet_col_wrap=3,
        title="Project and Baseline Household Comparability",
        text="Mean",
        hover_data={"Median": ":.2f", "Valid N": True},
        category_orders={"Dataset": ["Biogas User", "Non-Biogas User"]},
    )
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_yaxes(matches=None, title_text=None, showticklabels=True)
    fig.update_xaxes(title_text=None)
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.update_layout(showlegend=False)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_baseline_balance"))
    st.caption(
        "Panels use independent scales. Differences indicate sample composition and should be considered before "
        "treating Non-Biogas Users as an equivalent baseline group."
    )


def kpt_cooking_summary(data, dataset_key):
    meal_frequency_parts = []
    consistency_parts = []
    stock_parts = []
    commercial_parts = []
    for dataset_name, subset in dataset_groups(data):
        meal_column = find_column(
            subset,
            candidates=["4b. Waktu makan masakan rumah"],
            keywords=["waktu", "makan", "masakan", "rumah"],
        )
        if meal_column:
            meal_values = subset[meal_column].dropna().apply(normalize_meal_frequency)
            three_meals = meal_values.eq("3 Meal Times").mean() * 100 if not meal_values.empty else 0
            meal_frequency_parts.append(f"{dataset_name}: {three_meals:.1f}%")

        consistency = meal_consistency_mask(subset)
        consistency_parts.append(f"{dataset_name}: {consistency.mean() * 100:.1f}%")

        stock_column = household_stock_column(subset, dataset_name)
        if stock_column:
            stock_values = subset[stock_column].dropna().apply(translate_display_text).astype(str).str.casefold()
            household_only = stock_values.isin({"yes", "ya"}).mean() * 100 if not stock_values.empty else 0
            stock_parts.append(f"{dataset_name}: {household_only:.1f}%")

        side_column = find_best_filled_column(subset, ["industri", "sampingan"])
        if side_column:
            side_values = subset[side_column].dropna().astype(str).str.strip().str.casefold()
            commercial_count = int((~side_values.str.startswith("tidak") & ~side_values.eq("no")).sum())
            commercial_parts.append(f"{dataset_name}: {commercial_count:,}")

    insights = [
        "Households reporting exactly three daily meal times - " + "; ".join(meal_frequency_parts) + "." if meal_frequency_parts else None,
        "Person-meal totals match the demographic-group sums across breakfast, lunch, and dinner - " + "; ".join(consistency_parts) + ".",
        "Fuel stock reported as reserved for household use - " + "; ".join(stock_parts) + "." if stock_parts else None,
        "Households with a side-business or commercial-cooking context - " + "; ".join(commercial_parts) + "." if commercial_parts else None,
        "The source contains four assessment dates, while the TOR defines a one-day/24-hour measurement campaign; final protocol eligibility remains subject to confirmation.",
    ]
    render_summary_panel("Test Condition Highlights", insights)


def kpt_fuel_summary(data, key_prefix):
    metrics = build_household_fuel_metrics(data)
    insights = []
    if not metrics.empty:
        if metrics["Dataset"].nunique() == 1:
            for (dataset_name, fuel), subset in metrics.groupby(["Dataset", "Fuel"]):
                normalized = subset["kg per Person-Meal per Measurement Day"].dropna()
                normalized_text = (
                    f" and median {normalized.median():.3f} kg/person-meal/day"
                    if not normalized.empty else ""
                )
                insights.append(
                    f"{fuel}: median household consumption was "
                    f"{subset['Average Consumption per Measurement Day (kg)'].median():.3f} kg/measurement day"
                    f"{normalized_text}, based on {len(subset):,} households with at least one valid measurement day."
                )
        else:
            summary = (
                metrics.dropna(subset=["kg per Person-Meal per Measurement Day"])
                .groupby(["Dataset", "Fuel"])["kg per Person-Meal per Measurement Day"]
                .agg(["median", "count"])
            )
            limited_fuels = []
            for fuel in summary.index.get_level_values("Fuel").unique():
                try:
                    bu = summary.loc[("Biogas User", fuel)]
                    nbu = summary.loc[("Non-Biogas User", fuel)]
                except KeyError:
                    limited_fuels.append(fuel)
                    continue
                if min(int(bu["count"]), int(nbu["count"])) < KPT_MIN_COMPARISON_HOUSEHOLDS or nbu["median"] == 0:
                    limited_fuels.append(fuel)
                    continue
                difference = (bu["median"] / nbu["median"] - 1) * 100
                direction = "lower" if difference < 0 else "higher"
                insights.append(
                    f"{fuel}: median normalized consumption was {bu['median']:.3f} kg/person-meal/day for "
                    f"Biogas Users and {nbu['median']:.3f} for Non-Biogas Users, or "
                    f"{abs(difference):.1f}% {direction} among Biogas Users."
                )
            if limited_fuels:
                insights.append(
                    "A cross-dataset comparison is not presented for " + ", ".join(limited_fuels) +
                    f" because at least one dataset has fewer than {KPT_MIN_COMPARISON_HOUSEHOLDS} valid households."
                )
    render_summary_panel(
        "Summary - Measured Fuel Performance",
        insights or ["No valid measured stock-weight differences are available for the current filter."],
    )


def kpt_map_summary(data):
    render_summary_panel("Summary - Map", [map_insight(data, "KPT location distribution")])


def kpt_quality_summary_text(data):
    metrics = build_household_fuel_metrics(data)
    measured_households = metrics["Respondent Key"].nunique() if not metrics.empty else 0
    complete_meals = complete_person_meal_mask(data)
    latitude = pd.to_numeric(data.get("house_lat"), errors="coerce")
    longitude = pd.to_numeric(data.get("house_long"), errors="coerce")
    mapped_locations = int((latitude.between(-90, 90) & longitude.between(-180, 180)).sum())
    render_summary_panel("Summary - Data Coverage", [
        f"The active filter contains {len(data):,} KPT households; measured fuel results are available for {measured_households:,} households.",
        f"Complete person-meal records are available for {complete_meals.mean() * 100:.1f}% of households.",
        f"Valid mapped coordinates are available for {mapped_locations:,} households.",
        "All displayed fuel-performance results apply the same household-level validation and aggregation rules.",
    ])


def render_kpt_demographics(data, key_prefix):
    col1, col2 = st.columns(2)
    with col1:
        render_histogram(data, "age", "Respondent Age Distribution", key=f"{key_prefix}_age", x_label="Age")
    with col2:
        render_histogram(data, "hh_members", "Household Size Distribution", key=f"{key_prefix}_hh_members", x_label="Household Members")
        render_value_counts(data, "income", "Household Income", key=f"{key_prefix}_income")


def render_kpt_household_meal_frequency(data, key_prefix):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        meal_column = find_column(
            subset,
            candidates=["4b. Waktu makan masakan rumah"],
            keywords=["waktu", "makan", "masakan", "rumah"],
        )
        if not meal_column:
            continue
        values = subset[meal_column].dropna().apply(normalize_meal_frequency)
        counts = values.value_counts()
        total = counts.sum()
        for category, count in counts.items():
            rows.append({
                "Dataset": dataset_name,
                "Meal Frequency": category,
                "Count": int(count),
                "Share (%)": count / total * 100 if total else 0,
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Household meal-frequency data is not available for the current filter.")
        return
    fig = px.bar(
        chart_data,
        x="Dataset",
        y="Share (%)",
        color="Meal Frequency",
        barmode="stack",
        title="Daily Household Meal Frequency by Dataset",
        text="Share (%)",
        hover_data=["Count"],
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_meal_frequency"))


def render_kpt_person_meal_comparison(data, key_prefix):
    total_rows = []
    group_rows = []
    for dataset_name, subset in dataset_groups(data):
        for meal, (total_column, group_columns) in KPT_MEAL_SPECS.items():
            if total_column in subset.columns:
                totals = pd.to_numeric(subset[total_column], errors="coerce")
                if totals.notna().any():
                    total_rows.append({
                        "Dataset": dataset_name,
                        "Meal/Use": meal,
                        "Average Person-Meals": totals.mean(),
                        "Median Person-Meals": totals.median(),
                        "Valid N": int(totals.notna().sum()),
                    })
            for column in group_columns:
                if column not in subset.columns:
                    continue
                values = pd.to_numeric(subset[column], errors="coerce")
                if not values.notna().any():
                    continue
                group = KPT_GROUP_LABELS.get(column.split("_")[-1], column.split("_")[-1].title())
                group_rows.append({
                    "Dataset": dataset_name,
                    "Meal/Use": meal,
                    "Group": group,
                    "Average Person-Meals": values.mean(),
                    "Valid N": int(values.notna().sum()),
                })

    total_data = pd.DataFrame(total_rows)
    if not total_data.empty:
        total_fig = px.bar(
            total_data,
            x="Meal/Use",
            y="Average Person-Meals",
            color="Dataset" if total_data["Dataset"].nunique() > 1 else None,
            barmode="group",
            title="Average Person-Meals by Meal Time and Dataset",
            text_auto=".2f",
            hover_data=["Median Person-Meals", "Valid N"],
        )
        st.plotly_chart(
            apply_plot_theme(total_fig),
            use_container_width=True,
            key=unique_chart_key(f"{key_prefix}_person_meal_totals"),
        )

    group_data = pd.DataFrame(group_rows)
    if not group_data.empty:
        multiple_datasets = group_data["Dataset"].nunique() > 1
        group_fig = px.bar(
            group_data,
            x="Meal/Use",
            y="Average Person-Meals",
            color="Group",
            facet_col="Dataset" if multiple_datasets else None,
            barmode="group",
            title="Average Person-Meals by Demographic Group",
            hover_data=["Valid N"],
            height=560,
        )
        group_fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
        st.plotly_chart(
            apply_plot_theme(group_fig),
            use_container_width=True,
            key=unique_chart_key(f"{key_prefix}_person_meal_groups"),
        )
        st.caption(
            "The source fields use Men, Women, Children, and Older People. Confirmation is still required that "
            "these labels exactly match the TOR age/sex definitions."
        )


def render_kpt_test_condition_checks(data, key_prefix):
    check_rows = []
    schedule_rows = []
    for dataset_name, subset in dataset_groups(data):
        complete_meals = complete_person_meal_mask(subset)
        consistent_meals = meal_consistency_mask(subset)
        stock_column = household_stock_column(subset, dataset_name)
        if stock_column:
            stock_values = subset[stock_column].dropna().apply(translate_display_text).astype(str).str.casefold()
            stock_rate = stock_values.isin({"yes", "ya"}).mean() * 100 if not stock_values.empty else 0
        else:
            stock_rate = 0
        for check, rate in [
            ("Complete Person-Meals", complete_meals.mean() * 100),
            ("Consistent Meal Totals", consistent_meals.mean() * 100),
            ("Household-Only Fuel Stock", stock_rate),
        ]:
            check_rows.append({"Dataset": dataset_name, "Condition Check": check, "Pass Rate (%)": rate})

        date_columns = assessment_date_columns(subset)
        if date_columns:
            dates = subset[date_columns].apply(pd.to_datetime, errors="coerce")
            complete_dates = dates.notna().all(axis=1)
            consecutive_dates = (
                dates.diff(axis=1).iloc[:, 1:].eq(pd.Timedelta(days=1)).all(axis=1)
                if len(date_columns) > 1 else pd.Series(False, index=subset.index)
            )
            includes_weekend = dates.apply(lambda column: column.dt.dayofweek.ge(5)).any(axis=1)
            schedule_rows.append({
                "Dataset": dataset_name,
                "Complete Four-Date Records": int(complete_dates.sum()),
                "Four Consecutive Dates": int(consecutive_dates.sum()),
                "Campaign Includes Weekend": int(includes_weekend.sum()),
            })

    check_data = pd.DataFrame(check_rows)
    if not check_data.empty:
        fig = px.bar(
            check_data,
            x="Condition Check",
            y="Pass Rate (%)",
            color="Dataset" if check_data["Dataset"].nunique() > 1 else None,
            barmode="group",
            title="Test Condition Data Checks",
            text="Pass Rate (%)",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_yaxes(range=[0, 105])
        st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_condition_checks"))

    if schedule_rows:
        st.markdown("**Assessment Schedule Context**")
        st.dataframe(pd.DataFrame(schedule_rows), use_container_width=True, hide_index=True)


def render_kpt_cooking_context_flags(data, key_prefix):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        side_column = find_best_filled_column(subset, ["industri", "sampingan"])
        if side_column:
            side_values = subset[side_column].dropna().astype(str).str.strip().str.casefold()
            side_flag = ~side_values.str.startswith("tidak") & ~side_values.eq("no")
            rows.append({
                "Dataset": dataset_name,
                "Context Flag": "Side Business/Commercial Cooking",
                "Flagged Households": int(side_flag.sum()),
                "Share (%)": side_flag.mean() * 100 if len(side_flag) else 0,
            })

        household_size = pd.to_numeric(subset.get("hh_members"), errors="coerce")
        meal_totals = []
        for meal, (total_column, _) in KPT_MEAL_SPECS.items():
            if meal != "Warm Water" and total_column in subset.columns:
                meal_totals.append(pd.to_numeric(subset[total_column], errors="coerce"))
        if meal_totals:
            maximum_meal = pd.concat(meal_totals, axis=1).max(axis=1)
            valid = household_size.notna() & maximum_meal.notna()
            above_household = valid & maximum_meal.gt(household_size)
            rows.append({
                "Dataset": dataset_name,
                "Context Flag": "Person-Meals Above Household Size",
                "Flagged Households": int(above_household.sum()),
                "Share (%)": above_household.sum() / valid.sum() * 100 if valid.sum() else 0,
            })

    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return
    fig = px.bar(
        chart_data,
        x="Context Flag",
        y="Share (%)",
        color="Dataset" if chart_data["Dataset"].nunique() > 1 else None,
        barmode="group",
        title="Cooking-Load Context Flags",
        text="Share (%)",
        hover_data=["Flagged Households"],
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_yaxes(range=[0, max(20, chart_data["Share (%)"].max() * 1.25)])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_cooking_context"))
    st.caption(
        "Context flags are not automatic exclusions. They identify households that may include regular commercial "
        "cooking or people eating beyond the recorded household size."
    )


def render_kpt_fuel_stock_only_family(data, key_prefix):
    dataset_columns = {
        "Biogas User": "5f. Apakah stok bahan bakar memasak tersebut hanya untuk keluarga?",
        "Non-Biogas User": "5f. Stok hanya untuk keluarga?",
    }
    rows = []
    grouped = data.groupby("dataset") if "dataset" in data.columns else [("Current Dataset", data)]
    for dataset_name, subset in grouped:
        column = dataset_columns.get(dataset_name)
        if column not in subset.columns:
            column = find_column(subset, keywords=["stok", "keluarga"])
        if not column or column not in subset.columns:
            continue
        values = subset[column].dropna().apply(translate_display_text).astype(str).str.strip()
        for response, count in values.value_counts().items():
            rows.append({"Dataset": dataset_name, "Response": response, "Count": int(count)})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Fuel-stock household-use data is not available for the current filter.")
        return
    chart_data["Share (%)"] = chart_data["Count"] / chart_data.groupby("Dataset")["Count"].transform("sum") * 100
    fig = px.bar(
        chart_data,
        x="Dataset",
        y="Share (%)",
        color="Response",
        barmode="stack",
        title="Fuel Stock Reserved for Household Use",
        text="Share (%)",
        hover_data=["Count"],
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_fuel_stock_family"))


def render_kpt_lpg_cylinder_size(data, key_prefix):
    dataset_prefixes = {
        "Biogas User": "5c_3. Tabung LPG beli ukuran apa?",
        "Non-Biogas User": "5c_2. Tabung LPG beli ukuran apa?",
    }
    rows = []
    grouped = data.groupby("dataset") if "dataset" in data.columns else [("Current Dataset", data)]
    for dataset_name, subset in grouped:
        prefix = dataset_prefixes.get(dataset_name)
        if not prefix:
            prefix = next((candidate for candidate in dataset_prefixes.values() if option_columns(subset, candidate)), None)
        for column in option_columns(subset, prefix) if prefix else []:
            count = truthy_count(subset[column])
            if count:
                rows.append({
                    "Dataset": dataset_name,
                    "Cylinder Size": translate_display_text(option_label(column)),
                    "Count": count,
                })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("LPG cylinder-size data is not available for the current filter.")
        return
    grouped_data = chart_data.groupby(["Dataset", "Cylinder Size"], as_index=False)["Count"].sum()
    fig = px.bar(
        grouped_data,
        x="Cylinder Size",
        y="Count",
        color="Dataset" if grouped_data["Dataset"].nunique() > 1 else None,
        barmode="group",
        title="LPG Cylinder Size",
        text_auto=True,
    )
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_lpg_size"))


def render_kpt_reported_fuel_context(data, key_prefix):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        columns = {
            "Reported Firewood Use per Day": find_column(
                subset,
                [
                    "5b_3. Penggunaan jumlah kayu bakar rata-rata per hari",
                    "5b_2. Penggunaan jumlah kayu bakar rata-rata per hari",
                ],
                ["kayu", "rata-rata", "hari"],
            ),
            "LPG Cylinder Lifetime": find_column(
                subset,
                ["5c_3. Berapa hari tabung LPG habis?"],
                ["lpg", "hari", "habis"],
            ),
            "Reported Kerosene Use per Day": find_column(
                subset,
                [
                    "5d_3. Penggunaan jumlah minyak tanah rata-rata per harinya (berat)",
                    "5d_2. Penggunaan jumlah minyak tanah rata-rata per hari",
                ],
                ["minyak", "rata-rata", "hari"],
            ),
        }
        units = {
            "Reported Firewood Use per Day": "Source unit/day",
            "LPG Cylinder Lifetime": "Days",
            "Reported Kerosene Use per Day": "Source unit/day",
        }
        for metric, column in columns.items():
            if not column or column not in subset.columns:
                continue
            values = pd.to_numeric(subset[column], errors="coerce").dropna()
            if values.empty:
                continue
            rows.append({
                "Dataset": dataset_name,
                "Metric": metric,
                "Median": values.median(),
                "Mean": values.mean(),
                "Valid N": len(values),
                "Unit": units[metric],
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("No reported fuel-use context is available for the current filter.")
        return
    fig = px.bar(
        chart_data,
        x="Dataset",
        y="Median",
        color="Dataset",
        facet_col="Metric",
        facet_col_wrap=3,
        title="Reported Fuel-Use Context",
        text="Median",
        hover_data={"Mean": ":.2f", "Valid N": True, "Unit": True},
    )
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_yaxes(matches=None, title_text=None)
    fig.update_yaxes(title_text="Median (see panel unit)", row=1, col=1)
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.update_layout(showlegend=chart_data["Dataset"].nunique() > 1)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_reported_fuel_context"))
    st.caption(
        "Panels use independent axes and source-specific units. Firewood, LPG cylinder lifetime, and kerosene "
        "values must not be compared directly with one another."
    )
    render_kpt_lpg_cylinder_size(data, key_prefix)


def render_kpt_biogas_context(data, key_prefix):
    biogas_data = data[data["dataset"].eq("Biogas User")] if "dataset" in data.columns else data
    if biogas_data.empty:
        st.info("Biogas type and capacity charts are only relevant for Biogas User data.")
        return
    col1, col2 = st.columns(2)
    with col1:
        render_value_counts(
            biogas_data,
            find_column(biogas_data, candidates=["6a. Tipe Biogas", "7. Tipe Biogas"], keywords=["tipe", "biogas"]),
            "Biogas Type",
            key=f"{key_prefix}_biogas_type",
        )
    with col2:
        render_value_counts(
            biogas_data,
            find_column(biogas_data, candidates=["6b. Ukuran/kapasitas biogas", "7a. Ukuran/kapasitas biogas"], keywords=["kapasitas", "biogas"]),
            "Biogas Capacity",
            key=f"{key_prefix}_biogas_capacity",
        )


def render_kpt_livestock(data, key_prefix):
    count_columns = {
        "Beef Cattle": ["3a_1. Jumlah sapi pedaging", "3a_1. Jumlah sapi potong"],
        "Dairy Cattle": ["3a_2. Jumlah sapi perah"],
        "Other Cattle/Buffalo": ["3a_3. Jumlah sapi untuk kegunaan lain", "3a_3. Jumlah kerbau"],
        "Pigs": ["3a_4. Jumlah babi ternak", "3a_4. Jumlah babi"],
        "Goats": ["3a_6. Jumlah kambing", "3a_5. Jumlah kambing"],
        "Sheep": ["3a_6. Jumlah domba"],
        "Horses": ["3a_5. Jumlah kuda", "3a_6. Jumlah kuda", "3a_7. Jumlah kuda"],
        "Poultry": ["3a_7. Jumlah ayam", "3a_8. Jumlah unggas", "3a_8. Jumlah unggas lainnya"],
    }
    render_livestock_summary(
        data,
        ["3a. Jenis hewan ternak yang dimiliki"],
        count_columns,
        key_prefix,
    )


def render_kpt_measurement_coverage(metrics, interval_records, key_prefix):
    coverage = (
        metrics.groupby(["Dataset", "Fuel", "Valid Measurement Intervals"], as_index=False)
        .size()
        .rename(columns={"size": "Households"})
    )
    coverage["Share of Measured Households (%)"] = (
        coverage["Households"]
        / coverage.groupby(["Dataset", "Fuel"])["Households"].transform("sum")
        * 100
    )
    coverage["Valid Days"] = coverage["Valid Measurement Intervals"].apply(
        lambda value: f"{int(value)} Valid Day" if value == 1 else f"{int(value)} Valid Days"
    )
    fig = px.bar(
        coverage,
        x="Fuel",
        y="Share of Measured Households (%)",
        color="Valid Days",
        facet_col="Dataset" if coverage["Dataset"].nunique() > 1 else None,
        barmode="stack",
        title="Valid Measurement-Day Coverage",
        text="Share of Measured Households (%)",
        hover_data={"Households": True, "Valid Measurement Intervals": False},
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
    fig.update_yaxes(range=[0, 100])
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_fuel_coverage"))


def fuel_metric_summary(metrics, metric):
    return (
        metrics.dropna(subset=[metric])
        .groupby(["Dataset", "Fuel"], as_index=False)
        .agg(
            Median=(metric, "median"),
            Mean=(metric, "mean"),
            **{
                "Valid Households": ("Respondent Key", "nunique"),
                "Complete Three-Interval Households": ("Complete Three-Interval Measurement", "sum"),
            },
        )
    )


def render_fuel_metric_bar(metrics, metric, title, y_axis_title, key):
    chart_data = fuel_metric_summary(metrics, metric)
    if chart_data.empty:
        return
    fig = px.bar(
        chart_data,
        x="Dataset",
        y="Median",
        color="Dataset",
        facet_col="Fuel",
        facet_col_wrap=3,
        category_orders={
            "Fuel": ["LPG", "Firewood", "Kerosene"],
            "Dataset": ["Biogas User", "Non-Biogas User"],
        },
        title=title,
        text="Median",
        hover_data={
            "Mean": ":.3f",
            "Valid Households": True,
            "Complete Three-Interval Households": True,
        },
    )
    fig.update_traces(texttemplate="%{text:.3f}", textposition="outside", cliponaxis=False)
    fig.update_yaxes(matches=None, title_text=None, showticklabels=True)
    fig.update_yaxes(title_text=y_axis_title, row=1, col=1)
    fig.update_xaxes(title_text=None)
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.update_layout(showlegend=chart_data["Dataset"].nunique() > 1)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))
    st.caption("Fuel panels use independent y-axis scales. Compare datasets within the same fuel panel only.")


def render_fuel_distribution(metrics, key_prefix):
    metric = "Average Consumption per Measurement Day (kg)"
    fig = px.box(
        metrics,
        x="Dataset",
        y=metric,
        color="Dataset",
        facet_col="Fuel",
        facet_col_wrap=3,
        category_orders={
            "Fuel": ["LPG", "Firewood", "Kerosene"],
            "Dataset": ["Biogas User", "Non-Biogas User"],
        },
        points="outliers",
        title="Distribution of Household Fuel Consumption per Measurement Day",
        hover_data=["Valid Measurement Intervals", "Person-Meals"],
    )
    fig.update_yaxes(matches=None, title_text=None, showticklabels=True)
    fig.update_yaxes(title_text="kg per Measurement Day", row=1, col=1)
    fig.update_xaxes(title_text=None)
    fig.for_each_annotation(lambda annotation: annotation.update(text=annotation.text.split("=")[-1]))
    fig.update_layout(showlegend=metrics["Dataset"].nunique() > 1)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_fuel_distribution"))
    st.caption("Fuel panels use independent y-axis scales. Distribution shapes are comparable within each fuel panel.")


def render_relative_fuel_performance(metrics, key_prefix):
    metric = "kg per Person-Meal per Measurement Day"
    summary = fuel_metric_summary(metrics, metric)
    rows = []
    for fuel, fuel_data in summary.groupby("Fuel"):
        indexed = fuel_data.set_index("Dataset")
        if not {"Biogas User", "Non-Biogas User"}.issubset(indexed.index):
            continue
        bu = indexed.loc["Biogas User"]
        nbu = indexed.loc["Non-Biogas User"]
        if min(int(bu["Valid Households"]), int(nbu["Valid Households"])) < KPT_MIN_COMPARISON_HOUSEHOLDS:
            continue
        if nbu["Median"] == 0:
            continue
        rows.append({
            "Fuel": fuel,
            "Difference vs Non-Biogas User (%)": (bu["Median"] / nbu["Median"] - 1) * 100,
            "Biogas User Median": bu["Median"],
            "Non-Biogas User Median": nbu["Median"],
            "Biogas User N": int(bu["Valid Households"]),
            "Non-Biogas User N": int(nbu["Valid Households"]),
        })
    comparison = pd.DataFrame(rows)
    if comparison.empty:
        st.info(
            f"No fuel has at least {KPT_MIN_COMPARISON_HOUSEHOLDS} valid households in both datasets for a stable "
            "relative comparison."
        )
        return
    fig = px.bar(
        comparison,
        x="Fuel",
        y="Difference vs Non-Biogas User (%)",
        title="Relative Difference in Median Fuel Consumption per Person-Meal",
        text="Difference vs Non-Biogas User (%)",
        color="Difference vs Non-Biogas User (%)",
        color_continuous_scale=["#2F855A", "#F8FAFC", "#C2413B"],
        color_continuous_midpoint=0,
        hover_data={
            "Biogas User Median": ":.3f",
            "Non-Biogas User Median": ":.3f",
            "Biogas User N": True,
            "Non-Biogas User N": True,
        },
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.add_hline(y=0, line_color="#64748B", line_dash="dash")
    fig.update_coloraxes(showscale=False)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_relative_fuel"))
    st.caption(
        f"Relative comparisons are shown only when both datasets contain at least "
        f"{KPT_MIN_COMPARISON_HOUSEHOLDS} valid households for the fuel. Results are descriptive and unadjusted; "
        "use matched province filters or an equivalent-baseline design for formal project attribution."
    )


def render_kpt_measured_fuel_change(data, key_prefix):
    interval_records = build_measured_fuel_records(data)
    metrics = build_household_fuel_metrics(data)
    if metrics.empty:
        st.info("Measured fuel weight-change columns are not available or do not contain valid numeric data.")
        return

    normalized_metric = "kg per Person-Meal per Measurement Day"
    render_fuel_metric_bar(
        metrics,
        normalized_metric,
        "Median Measured Fuel Consumption per Person-Meal",
        "kg per Person-Meal per Measurement Day",
        f"{key_prefix}_normalized_fuel",
    )
    render_fuel_distribution(metrics, key_prefix)
    render_fuel_metric_bar(
        metrics,
        "Average Consumption per Measurement Day (kg)",
        "Median Household Fuel Consumption per Measurement Day",
        "kg per Measurement Day",
        f"{key_prefix}_raw_fuel",
    )
    if metrics["Dataset"].nunique() > 1:
        render_relative_fuel_performance(metrics, key_prefix)

    with st.expander("Measurement Coverage and Quality"):
        render_kpt_measurement_coverage(metrics, interval_records, key_prefix)
        moisture_columns = [
            column for column in data.columns
            if any(keyword in str(column).casefold() for keyword in ["moisture", "kadar air", "kelembaban"])
        ]
        if not moisture_columns:
            st.info(
                "Firewood moisture content is not available in the current KPT workbook. Firewood results are "
                "therefore not moisture-adjusted, although the TOR identifies moisture as an important fuel-quality condition."
            )

    st.caption(
        "Each A-B, C-D, and E-F stock-weight difference is treated as one measurement-day interval because the "
        "source records four consecutive assessment dates. Valid intervals are averaged within each household "
        "before household-level summaries are calculated. This interpretation should be confirmed against the "
        "field protocol before final reporting under the TOR's one-day/24-hour requirement."
    )


def render_kpt_quality_summary(data, key_prefix):
    render_key_field_quality_summary(
        data,
        {
            "Province": {"candidates": ["province"]},
            "District": {"candidates": ["district"]},
            "Age": {"candidates": ["age"]},
            "Meal Frequency": {"candidates": ["4b. Waktu makan masakan rumah"], "keywords": ["waktu", "makan", "masakan", "rumah"]},
            "Stove Last 24h": {"keywords": ["tipe", "kompor", "24"]},
            "Fuel Stock Only Family": {"keywords": ["stok", "keluarga"]},
            "House Latitude": {"candidates": ["house_lat"]},
            "House Longitude": {"candidates": ["house_long"]},
        },
        "KPT Key Field Completeness",
        key=f"{key_prefix}_quality_completeness",
    )


def render_kpt_protocol_quality(data):
    rows = []
    grouped = data.groupby("dataset") if "dataset" in data.columns else [("Current Dataset", data)]
    for dataset_name, subset in grouped:
        owned_masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, "Current"))
        used_masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, "Used in last 24 hours"))
        for stove_type, used_mask in used_masks.items():
            owned_mask = owned_masks.get(stove_type, pd.Series(False, index=subset.index))
            inconsistent_use = int((used_mask & ~owned_mask).sum())
            if inconsistent_use:
                rows.append({
                    "Dataset": dataset_name,
                    "Quality Flag": f"{stove_type} used but not recorded as currently owned",
                    "Affected Records": inconsistent_use,
                    "Treatment": "Retained in reported use; excluded from owner-utilization numerator",
                })
        for fuel, column in KPT_DURATION_COLUMNS.items():
            if column not in subset.columns:
                continue
            raw = subset[column].dropna()
            non_numeric = int(pd.to_numeric(raw, errors="coerce").isna().sum())
            if non_numeric:
                rows.append({
                    "Dataset": dataset_name,
                    "Quality Flag": f"Non-numeric values in {column}",
                    "Affected Records": non_numeric,
                    "Treatment": "Excluded from duration charts",
                })
            normalized_duration = normalize_duration_minutes(subset[column])
            used_mask = stove_use_mask(subset, dataset_name, fuel)
            duration_without_use = int((normalized_duration.gt(0) & ~used_mask).sum())
            if duration_without_use:
                rows.append({
                    "Dataset": dataset_name,
                    "Quality Flag": f"{fuel} duration recorded without 24-hour stove use",
                    "Affected Records": duration_without_use,
                    "Treatment": "Excluded from duration charts",
                })
        records = build_measured_fuel_records(subset)
        if not records.empty:
            for fuel, fuel_data in records.groupby("Fuel"):
                negative_count = int(fuel_data["Negative Reading"].sum())
                if negative_count:
                    rows.append({
                        "Dataset": dataset_name,
                        "Quality Flag": f"Negative {fuel} stock-weight difference",
                        "Affected Records": negative_count,
                        "Treatment": "Excluded from outcome averages",
                    })
        if "district" in subset.columns:
            missing_district = int(subset["district"].isna().sum())
            if missing_district:
                rows.append({
                    "Dataset": dataset_name,
                    "Quality Flag": "District not recorded",
                    "Affected Records": missing_district,
                    "Treatment": "Retained; district analysis unavailable",
                })
    if rows:
        table = pd.DataFrame(rows).rename(columns={
            "Quality Flag": "Validation Rule",
            "Affected Records": "Records Processed",
            "Treatment": "Dashboard Treatment",
        })
        st.dataframe(table, use_container_width=True, hide_index=True)


def render_kpt_dataset(data, dataset_key):
    tabs = st.tabs([
        "Overview",
        "Test Conditions",
        "Stoves & Context",
        "Measured Fuel Use",
        "Map",
        "Data Coverage",
    ])

    with tabs[0]:
        render_kpt_overview_metrics(data)
        kpt_sample_summary(data, dataset_key)
        render_kpt_overview_readiness(data, dataset_key)
        with st.expander("Sample Geography and Demographics"):
            col1, col2 = st.columns(2)
            with col1:
                render_value_counts(data, "province", "Households per Province", key=f"{dataset_key}_province")
                render_value_counts(data, "gender", "Respondent Gender", key=f"{dataset_key}_gender")
            with col2:
                render_value_counts(data, "district", "Top Districts", key=f"{dataset_key}_district")
                render_value_counts(data, "income", "Household Income", key=f"{dataset_key}_income_profile")
            render_kpt_demographics(data, dataset_key)

    with tabs[1]:
        kpt_cooking_summary(data, dataset_key)
        render_kpt_test_condition_checks(data, dataset_key)
        render_kpt_household_meal_frequency(data, dataset_key)
        render_kpt_person_meal_comparison(data, dataset_key)
        render_kpt_cooking_context_flags(data, dataset_key)
        render_kpt_fuel_stock_only_family(data, dataset_key)

    with tabs[2]:
        st.subheader("Stove Ownership and Actual Use")
        phases = ["Before biogas", "Current", "Used in last 24 hours"] if dataset_key == "bu" else ["Current", "Used in last 24 hours"]
        render_stove_context_summary(data, "Stove-Use Highlights")
        render_stove_profile(
            data,
            phases,
            "Stove Ownership and Use Profile",
            dataset_key,
        )
        render_stove_stacking(
            data,
            phases,
            "Number of Stove Types per Household",
            dataset_key,
        )
        render_kpt_duration_chart(data, dataset_key)
        if dataset_key == "bu":
            with st.expander("Biogas System Context"):
                render_kpt_biogas_context(data, dataset_key)
        with st.expander("Household Livestock Context"):
            render_kpt_livestock(data, dataset_key)

    with tabs[3]:
        kpt_fuel_summary(data, dataset_key)
        render_kpt_measured_fuel_change(data, dataset_key)
        with st.expander("Reported Fuel-Use Context"):
            render_kpt_reported_fuel_context(data, dataset_key)
        st.info(
            "The source workbook's Day 1-Day 4 total-use columns are retained but are not treated as measured fuel "
            "mass because their unit and relationship to the stock-weight intervals remain unconfirmed."
        )

    with tabs[4]:
        kpt_map_summary(data)
        render_location_map(data, dataset_key)

    with tabs[5]:
        kpt_quality_summary_text(data)
        render_kpt_quality_summary(data, dataset_key)
        with st.expander("Technical Validation Details"):
            render_kpt_protocol_quality(data)
            render_quality_notes(data, dataset_key)


def render_grouped_percentages(data, column, title, key, top=10):
    if column not in data.columns or "dataset" not in data.columns:
        st.info(f"Column is not available for this chart: {title}")
        return
    chart_data = (
        data[[column, "dataset"]]
        .dropna()
        .assign(**{column: lambda frame: frame[column].astype(str).str.strip()})
        .groupby(["dataset", column])
        .size()
        .reset_index(name="Count")
    )
    chart_data[column] = chart_data[column].apply(translate_display_text)
    if chart_data.empty:
        st.info(f"No valid data is available for this chart: {title}")
        return
    chart_data["Share within Dataset (%)"] = (
        chart_data["Count"] / chart_data.groupby("dataset")["Count"].transform("sum") * 100
    )
    top_categories = list(
        chart_data.groupby(column)["Count"].sum().sort_values(ascending=False).head(top).index
    )
    chart_data = chart_data[chart_data[column].isin(top_categories)]
    chart_data["Display Category"] = chart_data[column].apply(shorten_chart_label)
    display_order = [shorten_chart_label(category) for category in top_categories]
    use_horizontal = chart_data[column].nunique() > 5
    if use_horizontal:
        fig = px.bar(
            chart_data,
            x="Share within Dataset (%)",
            y="Display Category",
            color="dataset",
            barmode="group",
            orientation="h",
            title=title,
            text="Share within Dataset (%)",
            labels={"Display Category": "Category"},
            hover_data={column: True, "Display Category": False, "Count": True},
            height=max(520, 48 * max(chart_data[column].nunique(), 8)),
        )
    else:
        fig = px.bar(
            chart_data,
            x="Display Category",
            y="Share within Dataset (%)",
            color="dataset",
            barmode="group",
            title=title,
            text="Share within Dataset (%)",
            labels={"Display Category": "Category"},
            hover_data={column: True, "Display Category": False, "Count": True},
        )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    if use_horizontal:
        fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(display_order)))
    else:
        fig.update_xaxes(categoryorder="array", categoryarray=display_order)
    fig.update_layout(
        xaxis_tickangle=0 if use_horizontal else -20,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0),
        legend_title_text="Dataset",
        margin=dict(b=110),
    )
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def render_stove_utilization(data, key_prefix):
    rows = []
    for dataset_name, subset in dataset_groups(data):
        owned_masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, "Current"))
        used_masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, "Used in last 24 hours"))
        for stove_type in sorted(set(owned_masks) | set(used_masks)):
            owned = owned_masks.get(stove_type, pd.Series(False, index=subset.index))
            used = used_masks.get(stove_type, pd.Series(False, index=subset.index))
            owner_count = int(owned.sum())
            if not owner_count:
                continue
            owner_users = int((owned & used).sum())
            rows.append({
                "Dataset": dataset_name,
                "Stove Type": stove_type,
                "Current Owners": owner_count,
                "Owners Using Stove in Last 24 Hours": owner_users,
                "Utilization Rate": owner_users / owner_count * 100,
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Stove ownership and use data are not available for utilization analysis.")
        return
    fig = px.bar(
        chart_data,
        x="Stove Type",
        y="Utilization Rate",
        color="Dataset",
        barmode="group",
        title="Stove Utilization Among Current Owners",
        text="Utilization Rate",
        hover_data={
            "Current Owners": True,
            "Owners Using Stove in Last 24 Hours": True,
            "Utilization Rate": ":.1f",
        },
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig.update_layout(yaxis_title="Current Owners Using Stove (%)", yaxis_range=[0, 112], xaxis_tickangle=-15)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_utilization"))


def render_stove_context_summary(data, title):
    insights = []
    for dataset_name, subset in dataset_groups(data):
        used_masks = stove_option_masks(subset, dataset_stove_prefix(dataset_name, "Used in last 24 hours"))
        if not used_masks:
            continue
        counts = stove_count_per_household(subset, dataset_stove_prefix(dataset_name, "Used in last 24 hours"))
        stacking_share = counts.ge(2).mean() * 100
        leading = sorted(
            ((stove_type, int(mask.sum())) for stove_type, mask in used_masks.items()),
            key=lambda item: item[1],
            reverse=True,
        )[:2]
        leading_text = " and ".join(
            f"{stove_type} ({count / len(subset) * 100:.1f}%)"
            for stove_type, count in leading
        )
        insights.append(
            f"{dataset_name}: the most frequently used stove types in the last 24 hours were "
            f"{leading_text}; {stacking_share:.1f}% of households used at least two stove types."
        )
    render_summary_panel(title, insights)


def render_combined_person_meals(data):
    groups = {
        "Breakfast": ["4c_men", "4c_women", "4c_children", "4c_elders"],
        "Lunch": ["4d_men", "4d_women", "4d_children", "4d_elders"],
        "Dinner": ["4e_men", "4e_women", "4e_children", "4e_elders"],
        "Warm Water": ["4f_men", "4f_women", "4f_children", "4f_elders"],
    }
    rows = []
    for dataset, subset in data.groupby("dataset"):
        for meal, cols in groups.items():
            available = [pd.to_numeric(subset[col], errors="coerce") for col in cols if col in subset.columns]
            if available:
                total = pd.concat(available, axis=1).sum(axis=1, min_count=1)
                if total.notna().any():
                    rows.append({"dataset": dataset, "Meal": meal, "Average Person-Meals": total.mean()})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Person-meals columns are not available for the combined comparison.")
        return
    fig = px.bar(chart_data, x="Meal", y="Average Person-Meals", color="dataset", barmode="group", title="Average Total Person-Meals by Dataset")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("kpt_combined_person_meals"))


def render_combined_daily_fuel_usage(data):
    fuels = {
        "LPG": ["10a. Total penggunaan LPG Hari 1", "10b. Total penggunaan LPG Hari 2", "10c. Total penggunaan LPG Hari 3", "10d. Total penggunaan LPG Hari 4"],
        "Firewood": ["13a. Total penggunaan KAYU BAKAR Hari 1", "13b. Total penggunaan KAYU BAKAR Hari 2", "13c. Total penggunaan KAYU BAKAR Hari 3", "13d. Total penggunaan KAYU BAKAR Hari 4"],
        "Kerosene": ["16a. Total penggunaan MINYAK TANAH Hari 1", "16b. Total penggunaan MINYAK TANAH Hari 2", "16c. Total penggunaan MINYAK TANAH Hari 3", "16d. Total penggunaan MINYAK TANAH Hari 4"],
    }
    rows = []
    for dataset, subset in data.groupby("dataset"):
        for fuel, columns in fuels.items():
            for day, col in enumerate(columns, start=1):
                if col in subset.columns:
                    values = pd.to_numeric(subset[col], errors="coerce")
                    if values.notna().any():
                        rows.append({"dataset": dataset, "Fuel": fuel, "Day": f"Day {day}", "Average Usage": values.mean(), "Valid N": int(values.notna().sum())})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Daily fuel usage columns are not available for the combined comparison.")
        return
    fig = px.line(chart_data, x="Day", y="Average Usage", color="dataset", line_dash="Fuel", markers=True, title="Average Daily Fuel Usage by Dataset and Fuel", hover_data=["Fuel", "Valid N"])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("kpt_combined_daily_fuel"))


def render_kpt_combined(data):
    tabs = st.tabs([
        "Overview",
        "Test Conditions",
        "Stove Comparison",
        "Fuel Performance",
        "Map",
        "Data Coverage",
    ])

    with tabs[0]:
        render_kpt_overview_metrics(data)
        kpt_sample_summary(data, "kpt_combined")
        render_kpt_overview_readiness(data, "kpt_combined")
        render_kpt_baseline_comparability(data, "kpt_combined")
        render_grouped_percentages(
            data,
            "province",
            "Province Representation within Each Dataset",
            key="combined_province_share",
        )
        with st.expander("Sample Geography and Demographics"):
            col1, col2 = st.columns(2)
            with col1:
                render_grouped_percentages(data, "gender", "Gender Composition by Dataset", key="combined_gender_share")
                render_grouped_percentages(data, "income", "Household Income by Dataset", key="combined_income_share")
            with col2:
                render_grouped_percentages(data, "district", "Top District Representation by Dataset", key="combined_district_share")

    with tabs[1]:
        kpt_cooking_summary(data, "combined")
        render_kpt_test_condition_checks(data, "kpt_combined")
        render_kpt_household_meal_frequency(data, "kpt_combined")
        render_kpt_person_meal_comparison(data, "kpt_combined")
        render_kpt_cooking_context_flags(data, "kpt_combined")
        render_kpt_fuel_stock_only_family(data, "kpt_combined")

    with tabs[2]:
        st.subheader("Biogas User and Non-Biogas User Stove Comparison")
        render_stove_context_summary(data, "Comparative Stove-Use Highlights")
        render_stove_profile(
            data,
            ["Current"],
            "Current Stove Ownership by Dataset",
            "kpt_combined_current",
            color_field="Dataset",
        )
        render_stove_profile(
            data,
            ["Used in last 24 hours"],
            "Stove Types Used in the Last 24 Hours by Dataset",
            "kpt_combined_24h",
            color_field="Dataset",
        )
        render_stove_utilization(data, "kpt_combined")
        render_stove_stacking(
            data,
            ["Used in last 24 hours"],
            "Stove Stacking in the Last 24 Hours",
            "kpt_combined",
        )
        render_kpt_duration_chart(data, "kpt_combined")
        with st.expander("Biogas User System Context"):
            render_kpt_biogas_context(data, "kpt_combined")
        with st.expander("Household Livestock Context"):
            render_kpt_livestock(data, "kpt_combined")

    with tabs[3]:
        kpt_fuel_summary(data, "kpt_combined")
        render_kpt_measured_fuel_change(data, "kpt_combined")
        with st.expander("Reported Fuel-Use Context"):
            render_kpt_reported_fuel_context(data, "kpt_combined")
        st.info(
            "Cross-dataset results use household-level averages from the measured stock-weight differences. The "
            "Day 1-Day 4 total-use columns remain available in the source workbook but are not pooled into the "
            "primary comparison until their unit and measurement-period definition are confirmed."
        )

    with tabs[4]:
        kpt_map_summary(data)
        render_location_map(data, "kpt_combined")

    with tabs[5]:
        kpt_quality_summary_text(data)
        render_kpt_quality_summary(data, "kpt_combined")
        with st.expander("Technical Validation Details"):
            render_kpt_protocol_quality(data)
            render_quality_notes(data, "kpt_combined")


def Page_KPT():
    st.set_page_config(page_title="Kitchen Performance Test", page_icon=":bar_chart:", layout="wide")
    apply_global_theme()
    render_page_header("Kitchen Performance Test", "Survey 2026")

    if st.button("Home", key="Home KPT", type="primary"):
        st.switch_page("main_app.py", query_params={"utm_source": "main_app.py"})

    bu, nbu, combined = load_kpt_data()
    dataset = st.sidebar.radio("Dataset", ["Biogas User", "Non-Biogas User", "Combined"], horizontal=False)
    source = {"Biogas User": bu, "Non-Biogas User": nbu, "Combined": combined}[dataset]
    dataset_key = {"Biogas User": "bu", "Non-Biogas User": "nbu", "Combined": "combined"}[dataset]
    data = apply_sidebar_filters(source, f"kpt_{dataset_key}", title="KPT Filters")

    st.caption(
        "KPT analysis prioritizes measured fuel use, person-meals, and project-versus-baseline comparison under "
        "the TOR's 24-hour objective. The source workbook's four-date campaign is flagged separately for protocol review."
    )
    if dataset == "Combined":
        render_kpt_combined(data)
    else:
        render_kpt_dataset(data, dataset_key)
    render_footer()


pg = st.navigation([Page_KPT, st.Page("main_app.py")], position="hidden")
pg.run()
