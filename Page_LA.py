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
    option_insight,
    option_columns,
    quality_insight,
    render_basic_metrics,
    render_histogram,
    render_key_field_quality_summary,
    render_livestock_summary,
    render_location_map,
    render_numeric_columns,
    render_option_counts,
    render_quality_notes,
    render_summary_panel,
    render_value_counts,
    truthy_count,
    unique_chart_key,
)
from ui_theme import PLOTLY_COLORWAY, apply_global_theme, render_footer, render_page_header


@st.cache_data(show_spinner="Loading Leakage Assessment data...")
def load_la_data(_cache_version="english_display_labels_v1"):
    return normalize_common_columns(load_survey_workbook("Clean Data - LA.xlsx"))


LA_RESPONDENT_BIOGAS = "17. Apakah rumah responden ini memiliki biogas?"
LA_NEIGHBOR_BIOGAS = "18. Apakah tetangga Bapak/Ibu memiliki Biogas?"
LA_STOVE_CHANGE = (
    "34. Secara keseluruhan, apakah terjadi perubahan jenis kompor yang Bapak/Ibu gunakan dibandingkan "
    "sebelum tetangga  (user BIRU) mulai menggunakan biogas?"
)
LA_STOVE_CHANGE_YEAR = "35. Kapan Bapak/Ibu mulai beralih atau menambah jenis kompor tersebut?"
LA_ADDED_STOVE = (
    "37. Sejak tahun tetangga (user BIRU) mulai menggunakan biogas hingga saat ini, apakah Bapak/Ibu "
    "menambah jumlah kompor atau tungku kayu baru, baik untuk kebutuhan memasak keluarga maupun untuk "
    "kebutuhan pakan ternak?"
)
LA_STOVE_REASON_QUESTION = "36. Apa alasan utama Bapak/Ibu menambah atau mengganti jenis kompor/tungku tersebut?"
LA_FUEL_CHANGE = (
    "39. Apakah ada perubahan JUMLAH penggunaan bahan bakar memasak jika dibandingkan dengan sebelum "
    "tetangga (user BIRU) menggunakan biogas?"
)
LA_FUEL_CHANGE_YEAR = "40. Kapan perubahan tersebut mulai terjadi?"
LA_CHANGED_FUEL_QUESTION = "41. Jenis bahan bakar apa saja yang berubah jumlah penggunaannya?"
LA_FUEL_INCREASE_REASON_QUESTION = "45. Apa yang menyebabkan PENAMBAHAN jumlah penggunaan bahan bakar tersebut?"
LA_FOREST_FIREWOOD = (
    "46. Apakah keluarga Bapak/Ibu menggunakan kayu bakar yang berasal dari hutan/kebun (baik mengambil "
    "sendiri maupun membeli dari orang lain)?"
)
LA_MORE_FOREST_FIREWOOD = (
    "47.  Jika dibandingkan dengan sebelum tetangga (user BIRU) menggunakan biogas, apakah saat ini "
    "Bapak/Ibu menggunakan kayu bakar dari hutan/kebun dalam jumlah yang LEBIH BANYAK?"
)
LA_FOREST_REASON_QUESTION = "48. Mengapa Bapak/Ibu menggunakan kayu bakar (hutan/kebun) dalam jumlah yang lebih banyak?"

LA_FUEL_SPECS = {
    "Firewood": {
        "Initial": "42c. PENGGUNAAN AWAL: Berapa rata-rata konsumsi kayu bakar harian keluarga Anda? (Berat/Hari = ____ kg/hari)",
        "Current": "42f. PENGGUNAAN SEKARANG: Berapa rata-rata konsumsi harian keluarga Anda? (Berat/Hari = ____ kg/hari)",
        "Difference": "42g. Berapa selisih berat penggunaan kayu bakar? (Konsumsi Sekarang - Konsumsi Awal = __ kg/hari)",
        "Daily Unit": "kg/day",
        "Weekly Unit": "kg/week",
    },
    "LPG": {
        "Initial": "43c. PENGGUNAAN AWAL: Berapa rata-rata konsumsi LPG harian keluarga Anda? (Berat/Hari = ____ kg/hari)",
        "Current": "43f. PENGGUNAAN SEKARANG: Berapa rata-rata konsumsi LPG harian keluarga Anda saat ini? (Berat/Hari = ____ kg/hari)",
        "Difference": "43g. Berapa selisih berat penggunaan LPG? (Konsumsi Sekarang - Konsumsi Awal = __ kg/hari)",
        "Daily Unit": "kg/day",
        "Weekly Unit": "kg/week",
    },
    "Kerosene": {
        "Initial": "44c. PENGGUNAAN AWAL: Berapa rata-rata konsumsi minyak tanah harian keluarga Anda? (Liter/Hari = ____ L/hari)",
        "Current": "44f. PENGGUNAAN SEKARANG: Berapa rata-rata konsumsi Minyak Tanah harian keluarga Anda saat ini? (Liter/Hari = ____ L/hari)",
        "Difference": "44g. Berapa selisih berat penggunaan minyak tanah? (Konsumsi Sekarang - Konsumsi Awal = __ L/hari)",
        "Daily Unit": "L/day",
        "Weekly Unit": "L/week",
    },
}


def la_yes_mask(series):
    values = series.fillna("").astype(str).str.strip().str.casefold()
    return values.str.startswith("ya") | values.str.startswith("yes")


def la_no_mask(series):
    values = series.fillna("").astype(str).str.strip().str.casefold()
    return values.str.startswith("tidak") | values.str.startswith("no")


def la_eligibility_mask(data):
    if LA_RESPONDENT_BIOGAS not in data.columns or LA_NEIGHBOR_BIOGAS not in data.columns:
        return pd.Series(False, index=data.index)
    return la_no_mask(data[LA_RESPONDENT_BIOGAS]) & la_yes_mask(data[LA_NEIGHBOR_BIOGAS])


def eligible_la_data(data):
    return data.loc[la_eligibility_mask(data)].copy()


def build_la_fuel_records(data, eligible_only=True):
    source = eligible_la_data(data) if eligible_only else data
    rows = []
    for fuel, spec in LA_FUEL_SPECS.items():
        if not all(spec[key] in source.columns for key in ["Initial", "Current", "Difference"]):
            continue
        initial = pd.to_numeric(source[spec["Initial"]], errors="coerce")
        current = pd.to_numeric(source[spec["Current"]], errors="coerce")
        difference = pd.to_numeric(source[spec["Difference"]], errors="coerce")
        for index in source.index[difference.notna()]:
            delta = float(difference.loc[index])
            rows.append({
                "Respondent Index": index,
                "Fuel": fuel,
                "Initial Daily Use": initial.loc[index],
                "Current Daily Use": current.loc[index],
                "Daily Difference": delta,
                "Weekly Difference": delta * 7,
                "Daily Unit": spec["Daily Unit"],
                "Weekly Unit": spec["Weekly Unit"],
                "Direction": "Increase" if delta > 0 else "Decrease" if delta < 0 else "No Change",
                "Formula Mismatch": (
                    pd.notna(initial.loc[index])
                    and pd.notna(current.loc[index])
                    and abs((current.loc[index] - initial.loc[index]) - delta) > 1e-6
                ),
            })
    return pd.DataFrame(rows)


def la_temporal_status(data, change_column):
    change_year = pd.to_numeric(data.get(change_column), errors="coerce")
    completion_year = pd.to_numeric(data.get("year_completion"), errors="coerce")
    completion_year = completion_year.where(completion_year.between(2000, 2026))
    status = pd.Series("Timing Unavailable", index=data.index, dtype=object)
    valid = change_year.notna() & completion_year.notna()
    status.loc[valid & change_year.lt(completion_year)] = "Before Neighbor Installation"
    status.loc[valid & change_year.eq(completion_year)] = "Same Year"
    status.loc[valid & change_year.gt(completion_year)] = "After Neighbor Installation"
    return status


def compact_stove_label(column):
    text = str(column)
    candidates = [
        ("32a", "Simple wood stove"),
        ("32b", "Semi-permanent wood stove"),
        ("32c", "Permanent wood stove"),
        ("32d", "Improved wood stove"),
        ("32e", "Kerosene stove"),
        ("32f", "LPG stove"),
        ("32g", "Electric cooker"),
        ("32h", "Other stove"),
        ("33a", "Simple wood stove"),
        ("33b", "Semi-permanent wood stove"),
        ("33c", "Permanent wood stove"),
        ("33d", "Improved wood stove"),
        ("33e", "Kerosene stove"),
        ("33f", "LPG stove"),
        ("33g", "Electric cooker"),
        ("33h", "Other stove"),
        ("38a", "Simple wood stove"),
        ("38b", "Semi-permanent wood stove"),
        ("38c", "Permanent wood stove"),
        ("38d", "Improved wood stove"),
        ("38e", "Kerosene stove"),
        ("38f", "LPG stove"),
        ("38g", "Electric cooker"),
        ("38h", "Other stove"),
    ]
    for token, label in candidates:
        if token in text:
            return label
    return text.split("/")[-1][:42]


def stove_columns(data, code_prefix):
    pattern = re_prefix(code_prefix)
    return [col for col in data.columns if pattern.search(str(col))]


def re_prefix(code_prefix):
    import re

    return re.compile(rf"(^|/){re.escape(code_prefix)}[a-h]\.", re.IGNORECASE)


def build_la_stove_inventory(data):
    rows = []
    before_columns = {compact_stove_label(column): column for column in stove_columns(data, "32")}
    current_columns = {compact_stove_label(column): column for column in stove_columns(data, "33")}
    for stove_type in sorted(set(before_columns) & set(current_columns)):
        before = pd.to_numeric(data[before_columns[stove_type]], errors="coerce")
        current = pd.to_numeric(data[current_columns[stove_type]], errors="coerce")
        valid = before.notna() & current.notna()
        for index in data.index[valid]:
            before_value = float(before.loc[index])
            current_value = float(current.loc[index])
            before_used = before_value > 0
            current_used = current_value > 0
            transition = (
                "Started Using" if not before_used and current_used
                else "Stopped Using" if before_used and not current_used
                else "Continued Using" if before_used and current_used
                else "Never Used"
            )
            rows.append({
                "Respondent Index": index,
                "Stove Type": stove_type,
                "Before Units": before_value,
                "Current Units": current_value,
                "Derived Difference": current_value - before_value,
                "Transition": transition,
            })
    return pd.DataFrame(rows)


def la_cohort_stats(data):
    eligible = eligible_la_data(data)
    years = pd.to_numeric(eligible.get("years_of_use"), errors="coerce")
    counts = years.value_counts().reindex(range(1, 10), fill_value=0).astype(int)
    quota_fulfilled = int(counts.clip(upper=15).sum())
    return eligible, years, counts, quota_fulfilled


def la_sample_summary(data, full_sample=False):
    eligible, years, counts, quota_fulfilled = la_cohort_stats(data)
    fuel_records = build_la_fuel_records(data)
    positive_households = fuel_records.loc[fuel_records["Direction"].eq("Increase"), "Respondent Index"].nunique() if not fuel_records.empty else 0
    stove_change = la_yes_mask(eligible[LA_STOVE_CHANGE]).sum() if LA_STOVE_CHANGE in eligible.columns else 0
    fuel_change = la_yes_mask(eligible[LA_FUEL_CHANGE]).sum() if LA_FUEL_CHANGE in eligible.columns else 0
    insights = [
            f"{len(eligible):,} of {len(data):,} records meet the basic LA eligibility rule: the respondent does "
            "not own biogas and the referenced neighbor does.",
            f"Among eligible households, {stove_change:,} reported a stove-type change and {fuel_change:,} "
            "reported a fuel-quantity change relative to the neighbor comparison point.",
            f"Positive measured fuel differences are recorded for {positive_households:,} eligible households.",
    ]
    caveats = [
            "The workbook establishes a before/after timeline but does not directly ask whether the change was "
            "caused by the neighbor's biodigester.",
            "Firewood and LPG can be converted to kg/week; kerosene remains L/week without a density factor.",
    ]
    if full_sample:
        in_scope = int(years.between(1, 9).sum())
        out_of_scope = int((years.notna() & ~years.between(1, 9)).sum())
        insights.insert(1, f"{in_scope:,} eligible households fall within the TOR Y1-Y9 scope; {out_of_scope:,} are outside it.")
        caveats.insert(0, f"Under the strict 15-per-cohort rule, {quota_fulfilled:,} of 135 required cohort places are filled, leaving a shortfall of {135 - quota_fulfilled:,}.")
    else:
        caveats.insert(0, "TOR cohort compliance is assessed only on the full unfiltered sample, not on a province or district subset.")
    render_summary_panel("LA Sampling and Outcome Overview", insights, caveats=caveats)


def la_leakage_summary(data):
    eligible = eligible_la_data(data)
    stove_changers = eligible.loc[la_yes_mask(eligible[LA_STOVE_CHANGE])] if LA_STOVE_CHANGE in eligible.columns else eligible.iloc[0:0]
    fuel_changers = eligible.loc[la_yes_mask(eligible[LA_FUEL_CHANGE])] if LA_FUEL_CHANGE in eligible.columns else eligible.iloc[0:0]
    stove_status = la_temporal_status(stove_changers, LA_STOVE_CHANGE_YEAR)
    fuel_status = la_temporal_status(fuel_changers, LA_FUEL_CHANGE_YEAR)
    render_summary_panel(
        "Attribution Evidence and Timing",
        [
            f"{int(stove_status.eq('Before Neighbor Installation').sum()):,} stove changes and "
            f"{int(fuel_status.eq('Before Neighbor Installation').sum()):,} fuel changes were recorded before "
            "the neighbor installation year.",
            f"{int(stove_status.isin(['Same Year', 'After Neighbor Installation']).sum()):,} stove changes and "
            f"{int(fuel_status.isin(['Same Year', 'After Neighbor Installation']).sum()):,} fuel changes are "
            "temporally compatible with the neighbor comparison point.",
        ],
        caveats=[
            "Temporal compatibility does not prove causality because the questionnaire does not directly ask "
            "whether the neighboring biodigester caused the change.",
            "Changes recorded in the same calendar year remain ambiguous because installation and change months "
            "are unavailable.",
        ],
    )


def la_fuel_stove_summary(data):
    records = build_la_fuel_records(data)
    eligible = eligible_la_data(data)
    positive = records.loc[records["Direction"].eq("Increase")].copy() if not records.empty else records
    positive_households = positive["Respondent Index"].nunique() if not positive.empty else 0
    timing = la_temporal_status(eligible, LA_FUEL_CHANGE_YEAR)
    positive_indices = pd.Index(positive["Respondent Index"].unique()) if not positive.empty else pd.Index([])
    positive_timing = timing.reindex(positive_indices)
    after_count = int(positive_timing.eq("After Neighbor Installation").sum())
    same_year_count = int(positive_timing.eq("Same Year").sum())
    conflict_count = int(positive_timing.eq("Before Neighbor Installation").sum())
    render_summary_panel(
        "Measured Fuel Change and Potential Leakage",
        [
            f"{positive_households:,} eligible households recorded at least one positive measured fuel-use change.",
            f"{after_count:,} positive-change households were recorded after the neighbor installation year; "
            f"{same_year_count:,} occurred in the same calendar year and remain temporally ambiguous.",
            f"{conflict_count:,} positive-change households predate the neighbor installation and are excluded "
            "from potential leakage interpretation.",
        ] if positive_households else ["No positive quantified fuel changes are available for the current filter."],
        caveats=[
            "Even changes recorded after installation are temporal associations, not confirmed causal leakage.",
            "Firewood and LPG are expressed in kg/week. Kerosene remains in L/week because the dataset does not "
            "provide an approved density conversion factor.",
        ],
    )


def la_map_summary(data):
    render_summary_panel("Summary - Map", [map_insight(data, "LA location distribution")])


def la_quality_summary_text(data):
    eligible = eligible_la_data(data)
    fuel_records = build_la_fuel_records(data)
    latitude = pd.to_numeric(data.get("house_lat"), errors="coerce")
    longitude = pd.to_numeric(data.get("house_long"), errors="coerce")
    mapped_locations = int((latitude.between(-90, 90) & longitude.between(-180, 180)).sum())
    comparable_households = fuel_records["Respondent Index"].nunique() if not fuel_records.empty else 0
    render_summary_panel("Summary - Data Coverage", [
        f"The active filter contains {len(data):,} LA records, of which {len(eligible):,} meet the non-user household eligibility rule.",
        f"Comparable before-current fuel measurements are available for {comparable_households:,} eligible households.",
        f"Valid mapped coordinates are available for {mapped_locations:,} records.",
        "Eligibility, timing, and fuel-difference rules are applied consistently before results are displayed.",
    ])


def render_stove_change(data):
    inventory = build_la_stove_inventory(data)
    if inventory.empty:
        st.info("Stove ownership change columns are not available or do not contain valid numeric data.")
        return
    before = inventory.groupby("Stove Type", as_index=False).agg(
        **{"Average Units per Household": ("Before Units", "mean"), "Households with Data": ("Respondent Index", "nunique")}
    )
    before["Period"] = "Before Neighbor Installation"
    current = inventory.groupby("Stove Type", as_index=False).agg(
        **{"Average Units per Household": ("Current Units", "mean"), "Households with Data": ("Respondent Index", "nunique")}
    )
    current["Period"] = "Current"
    chart_data = pd.concat([before, current], ignore_index=True)
    fig = px.bar(
        chart_data,
        x="Stove Type",
        y="Average Units per Household",
        color="Period",
        barmode="group",
        title="Average Stove Ownership: Before Neighbor Installation vs Current",
        hover_data=["Households with Data"],
    )
    fig.update_layout(xaxis_tickangle=-25)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_stove_change"))


def render_la_overview_metrics(data, full_sample=False):
    eligible, years, counts, quota_fulfilled = la_cohort_stats(data)
    in_scope = int(years.between(1, 9).sum())
    out_of_scope = int((years.notna() & ~years.between(1, 9)).sum())
    metrics = [
        ("Filtered Records", len(data), None),
        ("Protocol Eligible", len(eligible), "Respondent has no biogas and the referenced neighbor has biogas."),
        ("In-Scope Y1-Y9", in_scope, None),
    ]
    if full_sample:
        metrics.extend([
            ("Cohort Quota Fulfilled", f"{quota_fulfilled}/135", "Each cohort contributes at most 15 responses toward the TOR quota."),
            ("Cohort Shortfall", 135 - quota_fulfilled, None),
        ])
    else:
        metrics.extend([
            ("Outside Y1-Y9", out_of_scope, None),
            ("TOR Quota Assessment", "Full sample only", None),
        ])
    columns = st.columns(len(metrics))
    for column, (label, value, help_text) in zip(columns, metrics):
        column.metric(label, f"{value:,}" if isinstance(value, int) else value, help=help_text)


def render_la_outcome_snapshot(data):
    eligible = eligible_la_data(data)
    records = add_la_fuel_timing(data, build_la_fuel_records(data))
    positive = records.loc[records["Direction"].eq("Increase")]
    household_timing = positive.drop_duplicates("Respondent Index").set_index("Respondent Index")["Timing"] if not positive.empty else pd.Series(dtype=object)
    metrics = [
        ("Reported Stove Change", int(la_yes_mask(eligible[LA_STOVE_CHANGE]).sum()) if LA_STOVE_CHANGE in eligible else 0),
        ("Reported Fuel Change", int(la_yes_mask(eligible[LA_FUEL_CHANGE]).sum()) if LA_FUEL_CHANGE in eligible else 0),
        ("Measured Positive Fuel Change", int(positive["Respondent Index"].nunique()) if not positive.empty else 0),
        ("Positive Change After Installation", int(household_timing.eq("After Installation").sum())),
    ]
    st.markdown("#### Outcome Snapshot")
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, f"{value:,}")


def render_la_eligibility_breakdown(data):
    respondent_has = la_yes_mask(data[LA_RESPONDENT_BIOGAS]) if LA_RESPONDENT_BIOGAS in data else pd.Series(False, index=data.index)
    neighbor_has = la_yes_mask(data[LA_NEIGHBOR_BIOGAS]) if LA_NEIGHBOR_BIOGAS in data else pd.Series(False, index=data.index)
    labels = pd.Series("Eligible LA Household", index=data.index)
    labels.loc[respondent_has] = "Respondent Owns Biogas"
    labels.loc[~respondent_has & ~neighbor_has] = "Neighbor Does Not Own Biogas"
    chart_data = labels.value_counts().rename_axis("Eligibility Status").reset_index(name="Households")
    fig = px.bar(
        chart_data,
        x="Households",
        y="Eligibility Status",
        orientation="h",
        text_auto=True,
        title="LA Eligibility Check",
        color="Eligibility Status",
        color_discrete_sequence=PLOTLY_COLORWAY,
    )
    fig.update_layout(showlegend=False, yaxis_title=None)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_eligibility"))


def render_la_years_of_use_coverage(data, full_sample=False):
    eligible, years, counts, quota_fulfilled = la_cohort_stats(data)
    years = years.dropna()
    if years.empty:
        st.info("Years-of-use data are not available for the current filter.")
        return
    chart_data = counts.rename_axis("Years Since Neighbor Installation").reset_index(name="Households")
    chart_data["Cohort Status"] = chart_data["Households"].map(lambda value: "Target Met" if value >= 15 else "Below Target")
    fig = px.bar(
        chart_data,
        x="Years Since Neighbor Installation",
        y="Households",
        text_auto=True,
        color="Cohort Status",
        title="Eligible Y1-Y9 Sample Coverage",
        color_discrete_map={"Target Met": "#2C9C69", "Below Target": "#D95D52"},
    )
    if full_sample:
        fig.add_hline(y=15, line_dash="dash", line_color="#E89B2D", annotation_text="TOR target: 15 per cohort")
    fig.update_xaxes(dtick=1)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_years_coverage"))
    if full_sample:
        cohort_table = chart_data[["Years Since Neighbor Installation", "Households"]].copy()
        cohort_table["TOR Target"] = 15
        cohort_table["Shortfall"] = (15 - cohort_table["Households"]).clip(lower=0)
        st.dataframe(cohort_table, use_container_width=True, hide_index=True)
        out_of_scope = years.loc[~years.between(1, 9)].round().astype(int).value_counts().sort_index()
        st.caption(f"Strict cohort fulfillment is {quota_fulfilled:,}/135. Oversampling in one cohort does not replace a shortfall in another cohort.")
    else:
        st.caption("Counts reflect the current filter. The TOR target line is hidden because the 15-per-cohort quota applies to the full survey sample.")


def render_la_sampling_quality(data, full_sample=False):
    eligible, years, counts, quota_fulfilled = la_cohort_stats(data)
    completion_year = pd.to_numeric(eligible.get("year_completion"), errors="coerce")
    invalid_completion = int((completion_year.notna() & ~completion_year.between(2000, 2026)).sum())
    vpa_values = eligible.get("vpa", pd.Series(index=eligible.index, dtype=object)).fillna("").astype(str).str.strip().str.casefold()
    unexpected_vpa = int((vpa_values.ne("") & ~vpa_values.isin(["vpa1", "vpa2"])).sum())
    rows = [
        ("Eligible records outside Y1-Y9", int((years.notna() & ~years.between(1, 9)).sum()), "Exclude from strict Y1-Y9 quota fulfillment"),
        ("Invalid neighbor installation year", invalid_completion, "Verify the source year before timing analysis"),
        ("VPA label outside VPA1/VPA2", unexpected_vpa, "Verify project-activity coding"),
    ]
    if full_sample:
        provinces = set(eligible.get("province", pd.Series(dtype=object)).dropna().astype(str).str.strip().str.casefold())
        rows.extend([
            ("Strict cohort quota shortfall", 135 - quota_fulfilled, "Collect or validate responses in underfilled cohorts"),
            ("TOR-named Banten coverage missing", int("banten" not in provinces), "Document actual geographic coverage"),
        ])
    st.dataframe(pd.DataFrame(rows, columns=["Sampling Quality Check", "Records/Flag", "Recommended Treatment"]), use_container_width=True, hide_index=True)
    st.caption("Quality flags are derived in the dashboard and do not alter the source workbook.")


def render_la_temporal_evidence(data):
    eligible = eligible_la_data(data)
    rows = []
    for event, flag_column, year_column in [
        ("Stove Type Change", LA_STOVE_CHANGE, LA_STOVE_CHANGE_YEAR),
        ("Fuel Quantity Change", LA_FUEL_CHANGE, LA_FUEL_CHANGE_YEAR),
    ]:
        if flag_column not in eligible:
            continue
        changed = eligible.loc[la_yes_mask(eligible[flag_column])]
        counts = la_temporal_status(changed, year_column).value_counts()
        total = int(counts.sum())
        rows.extend({
            "Event": event,
            "Timing": timing,
            "Households": int(count),
            "Share": count / total * 100 if total else 0,
        } for timing, count in counts.items())
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Change-timing data are not available for the current filter.")
        return
    order = ["Before Neighbor Installation", "Same Year", "After Neighbor Installation", "Timing Unavailable"]
    fig = px.bar(
        chart_data,
        x="Event",
        y="Share",
        color="Timing",
        barmode="stack",
        text=chart_data.apply(lambda row: f"{row['Share']:.1f}%" if row["Share"] >= 5 else "", axis=1),
        hover_data={"Households": True, "Share": ":.1f"},
        category_orders={"Timing": order},
        title="Temporal Compatibility of Reported Changes",
        color_discrete_sequence=PLOTLY_COLORWAY,
    )
    fig.update_layout(yaxis_title="Share of Households Reporting Each Change (%)", yaxis_range=[0, 100])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_temporal_evidence"))


def render_la_time_lag_distribution(data):
    eligible = eligible_la_data(data)
    completion_year = pd.to_numeric(eligible.get("year_completion"), errors="coerce")
    completion_year = completion_year.where(completion_year.between(2000, 2026))
    rows = []
    for event, flag_column, year_column in [
        ("Stove Type Change", LA_STOVE_CHANGE, LA_STOVE_CHANGE_YEAR),
        ("Fuel Quantity Change", LA_FUEL_CHANGE, LA_FUEL_CHANGE_YEAR),
    ]:
        if flag_column not in eligible or year_column not in eligible:
            continue
        changed = la_yes_mask(eligible[flag_column])
        change_year = pd.to_numeric(eligible[year_column], errors="coerce")
        valid = changed & change_year.notna() & completion_year.notna()
        for lag, count in (change_year.loc[valid] - completion_year.loc[valid]).astype(int).value_counts().items():
            rows.append({
                "Event": event,
                "Year Difference": int(lag),
                "Households": int(count),
                "Interpretation": "Before Installation" if lag < 0 else "Same Calendar Year" if lag == 0 else "After Installation",
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("A valid year difference cannot be calculated for the current filter.")
        return
    chart_data = chart_data.sort_values(["Year Difference", "Event"])
    fig = px.bar(
        chart_data,
        x="Year Difference",
        y="Households",
        color="Event",
        barmode="group",
        text_auto=True,
        hover_data=["Interpretation"],
        title="Years Between Neighbor Installation and Reported Change",
        color_discrete_sequence=PLOTLY_COLORWAY,
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#E89B2D")
    fig.update_xaxes(dtick=1, title="Change Year Minus Neighbor Installation Year")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_time_lag"))
    st.caption("Negative values conflict with project attribution; zero indicates an unresolved within-year sequence; positive values are temporally compatible but not proof of causality.")


def render_la_demographics(data):
    col1, col2 = st.columns(2)
    with col1:
        render_histogram(data, "age", "Respondent Age Distribution", key="la_age", x_label="Age")
    with col2:
        render_histogram(data, "hh_members", "Household Size Distribution", key="la_hh_members", x_label="Household Members")


def render_stove_difference(data):
    inventory = build_la_stove_inventory(data)
    if inventory.empty:
        st.info("Paired before-current stove ownership data are not available for the current filter.")
        return
    chart_data = inventory.groupby("Stove Type", as_index=False).agg(
        **{
            "Average Unit Change per Household": ("Derived Difference", "mean"),
            "Total Derived Unit Change": ("Derived Difference", "sum"),
            "Valid N": ("Respondent Index", "nunique"),
        }
    ).sort_values("Average Unit Change per Household")
    chart_data["Direction"] = chart_data["Average Unit Change per Household"].map(
        lambda value: "Increase" if value > 0 else "Decrease" if value < 0 else "No Change"
    )
    fig = px.bar(
        chart_data,
        x="Average Unit Change per Household",
        y="Stove Type",
        orientation="h",
        color="Direction",
        title="Derived Net Change in Stove Ownership (Current - Before)",
        text_auto=".2f",
        hover_data=["Total Derived Unit Change", "Valid N"],
        color_discrete_map={"Increase": "#2C9C69", "Decrease": "#D95D52", "No Change": "#7C8AA5"},
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#7C8AA5")
    fig.update_layout(yaxis_title=None)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_stove_difference"))


def render_la_stove_transitions(data):
    inventory = build_la_stove_inventory(data)
    if inventory.empty:
        st.info("Stove transition data are not available for the current filter.")
        return
    chart_data = inventory.groupby(["Stove Type", "Transition"], as_index=False).size().rename(columns={"size": "Households"})
    chart_data["Share"] = chart_data["Households"] / chart_data.groupby("Stove Type")["Households"].transform("sum") * 100
    fig = px.bar(
        chart_data,
        x="Share",
        y="Stove Type",
        orientation="h",
        color="Transition",
        barmode="stack",
        text=chart_data.apply(lambda row: f"{row['Share']:.1f}%" if row["Share"] >= 8 else "", axis=1),
        hover_data={"Households": True, "Share": ":.1f"},
        category_orders={"Transition": ["Started Using", "Continued Using", "Stopped Using", "Never Used"]},
        title="Stove-Type Ownership Transitions",
        color_discrete_map={
            "Started Using": "#2C9C69",
            "Continued Using": "#2474B5",
            "Stopped Using": "#D95D52",
            "Never Used": "#B7C3D0",
        },
    )
    fig.update_layout(xaxis_title="Share of Households with Comparable Data (%)", xaxis_range=[0, 100], yaxis_title=None)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_stove_transitions"))


def compact_stove_reason_label(column):
    option = str(column).split(LA_STOVE_REASON_QUESTION + "/", 1)[-1].strip()
    translations = {
        "Harga lebih murah (bahan bakar atau unit kompor)": "Lower Fuel or Stove Cost",
        "Bahan bakar lebih mudah didapatkan": "Easier Fuel Access",
        "Lebih aman digunakan": "Safer to Use",
        "Dapur lebih bersih dan sehat (bebas asap)": "Cleaner and Healthier Kitchen",
        "Lebih nyaman dan praktis digunakan": "More Convenient and Practical",
        "Menerima bantuan atau subsidi (pemerintah/lembaga)": "Received Assistance or Subsidy",
        "Kebutuhan memasak bertambah (anggota keluarga/pakan ternak)": "Increased Cooking Needs",
        "Lainnya": "Other",
    }
    return translations.get(option, option)


def render_la_stove_reasons(data):
    columns = [column for column in data.columns if str(column).startswith(LA_STOVE_REASON_QUESTION + "/")]
    if not columns:
        st.info("Structured stove-change reason fields are not available for the current filter.")
        return
    selected = data[columns].apply(lambda series: pd.to_numeric(series, errors="coerce").fillna(0).gt(0))
    chart_data = pd.DataFrame({
        "Reason": [compact_stove_reason_label(column) for column in columns],
        "Households": [int(selected[column].sum()) for column in columns],
    })
    chart_data = chart_data.loc[chart_data["Households"].gt(0)].sort_values("Households")
    if chart_data.empty:
        st.info("No structured reasons were selected for the current filter.")
        return
    fig = px.bar(
        chart_data,
        x="Households",
        y="Reason",
        orientation="h",
        text_auto=True,
        title="Reasons Selected by Households Reporting a Stove Change",
        color_discrete_sequence=[PLOTLY_COLORWAY[1]],
    )
    fig.update_layout(yaxis_title=None, xaxis_title="Households Selecting the Reason")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_stove_reasons"))
    respondents_with_reason = int(selected.any(axis=1).sum())
    st.caption(
        f"Multiple responses were allowed. {respondents_with_reason:,} of {len(data):,} households reporting "
        "a stove change selected at least one structured reason, so category counts should not be summed as unique households."
    )


def render_la_stove_consistency(data):
    inventory = build_la_stove_inventory(data)
    if inventory.empty:
        return
    reported_type_change = la_yes_mask(data[LA_STOVE_CHANGE]) if LA_STOVE_CHANGE in data else pd.Series(False, index=data.index)
    reported_added = la_yes_mask(data[LA_ADDED_STOVE]) if LA_ADDED_STOVE in data else pd.Series(False, index=data.index)
    presence_change = inventory.assign(
        Changed=inventory["Transition"].isin(["Started Using", "Stopped Using"])
    ).groupby("Respondent Index")["Changed"].any().reindex(data.index, fill_value=False)
    any_increase = inventory.assign(
        Increased=inventory["Derived Difference"].gt(0)
    ).groupby("Respondent Index")["Increased"].any().reindex(data.index, fill_value=False)
    checks = pd.DataFrame([
        ("Reported type change, but no type-presence transition", int((reported_type_change & ~presence_change).sum())),
        ("Reported no type change, but a type-presence transition exists", int((~reported_type_change & presence_change).sum())),
        ("Reported adding a stove, but no stove type increased", int((reported_added & ~any_increase).sum())),
        ("Reported no added stove, but at least one stove type increased", int((~reported_added & any_increase).sum())),
    ], columns=["Consistency Check", "Households"])
    st.dataframe(checks, use_container_width=True, hide_index=True)
    st.caption("Q38 is retained only for data-quality review. Analytical net change is recalculated directly from Q33 minus Q32 because Q38 uses an inconsistent sign convention.")


def add_la_fuel_timing(data, records):
    enriched = records.copy()
    if enriched.empty:
        enriched["Timing"] = pd.Series(dtype=object)
        return enriched
    timing = la_temporal_status(eligible_la_data(data), LA_FUEL_CHANGE_YEAR)
    enriched["Timing"] = enriched["Respondent Index"].map(timing).replace({
        "After Neighbor Installation": "After Installation",
        "Same Year": "Same-Year Ambiguous",
        "Before Neighbor Installation": "Before Installation Conflict",
        "Timing Unavailable": "Timing Unavailable",
    })
    return enriched


def render_la_fuel_metrics(data):
    eligible = eligible_la_data(data)
    records = add_la_fuel_timing(data, build_la_fuel_records(data))
    reported = int(la_yes_mask(eligible[LA_FUEL_CHANGE]).sum()) if LA_FUEL_CHANGE in eligible else 0
    positive = records.loc[records["Direction"].eq("Increase")]
    household_timing = positive.drop_duplicates("Respondent Index").set_index("Respondent Index")["Timing"] if not positive.empty else pd.Series(dtype=object)
    metrics = [
        ("Reported Fuel Change", reported),
        ("Measured Positive Change", int(positive["Respondent Index"].nunique()) if not positive.empty else 0),
        ("After Installation", int(household_timing.eq("After Installation").sum())),
        ("Same-Year Ambiguous", int(household_timing.eq("Same-Year Ambiguous").sum())),
        ("Timing Conflicts", int(household_timing.eq("Before Installation Conflict").sum())),
    ]
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, f"{value:,}")


def render_la_positive_fuel_timing(data):
    records = add_la_fuel_timing(data, build_la_fuel_records(data))
    positive = records.loc[records["Direction"].eq("Increase")]
    if positive.empty:
        return
    household_timing = positive.drop_duplicates("Respondent Index")["Timing"].value_counts().rename_axis("Timing").reset_index(name="Households")
    order = ["After Installation", "Same-Year Ambiguous", "Before Installation Conflict", "Timing Unavailable"]
    fig = px.bar(
        household_timing,
        x="Households",
        y="Timing",
        orientation="h",
        text_auto=True,
        color="Timing",
        category_orders={"Timing": order},
        title="Timing Classification of Households with a Measured Fuel Increase",
        color_discrete_map={
            "After Installation": "#2C9C69",
            "Same-Year Ambiguous": "#E89B2D",
            "Before Installation Conflict": "#D95D52",
            "Timing Unavailable": "#7C8AA5",
        },
    )
    fig.update_layout(showlegend=False, yaxis_title=None)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_positive_fuel_timing"))


def render_la_changed_fuel_types(data):
    columns = [column for column in data.columns if str(column).startswith(LA_CHANGED_FUEL_QUESTION + "/")]
    translations = {"Kayu Bakar": "Firewood", "LPG": "LPG", "Minyak Tanah": "Kerosene", "Lainnya": "Other"}
    if not columns:
        st.info("Structured changed-fuel fields are not available for the current filter.")
        return
    selected = data[columns].apply(lambda series: pd.to_numeric(series, errors="coerce").fillna(0).gt(0))
    chart_data = pd.DataFrame({
        "Fuel": [translations.get(str(column).split("/")[-1].strip(), str(column).split("/")[-1].strip()) for column in columns],
        "Households": [int(selected[column].sum()) for column in columns],
    }).sort_values("Households")
    chart_data = chart_data.loc[chart_data["Households"].gt(0)]
    fig = px.bar(chart_data, x="Households", y="Fuel", orientation="h", text_auto=True, title="Fuel Types Reported as Changed", color_discrete_sequence=[PLOTLY_COLORWAY[1]])
    fig.update_layout(yaxis_title=None, xaxis_title="Households Selecting the Fuel")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_changed_fuel_types"))
    st.caption(f"Multiple responses were allowed. {int(selected.any(axis=1).sum()):,} of {len(data):,} households reporting a fuel change selected at least one fuel type.")


def render_la_fuel_increase_reasons(data):
    columns = [column for column in data.columns if str(column).startswith(LA_FUEL_INCREASE_REASON_QUESTION + "/")]
    translations = {
        "Bahan bakar lebih mudah didapatkan di lingkungan sekitar": "Easier Local Fuel Availability",
        "Harga bahan bakar lebih terjangkau atau lebih murah": "More Affordable Fuel",
        "Penambahan jumlah tungku kompor yang digunakan secara bersamaan": "More Stoves Used Simultaneously",
        "Terjadi penambahan jumlah anggota keluarga (beban memasak meningkat)": "More Household Members",
        "Jumlah makanan yang dimasak lebih banyak (untuk pakan ternak, usaha rumahan, atau frekuensi makan bertambah) meskipun anggota keluarga tetap": "More Food, Feed, or Business Cooking",
        "Alasan Lainnya": "Other",
    }
    if not columns:
        st.info("Structured fuel-increase reason fields are not available for the current filter.")
        return
    selected = data[columns].apply(lambda series: pd.to_numeric(series, errors="coerce").fillna(0).gt(0))
    chart_data = pd.DataFrame({
        "Reason": [translations.get(str(column).split("/")[-1].strip(), str(column).split("/")[-1].strip()) for column in columns],
        "Households": [int(selected[column].sum()) for column in columns],
    })
    chart_data = chart_data.loc[chart_data["Households"].gt(0)].sort_values("Households")
    fig = px.bar(chart_data, x="Households", y="Reason", orientation="h", text_auto=True, title="Reasons for a Measured Fuel Increase", color_discrete_sequence=[PLOTLY_COLORWAY[1]])
    fig.update_layout(yaxis_title=None, xaxis_title="Households Selecting the Reason")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_fuel_increase_reasons"))
    st.caption(f"Multiple responses were allowed. {int(selected.any(axis=1).sum()):,} of {len(data):,} households with a measured increase selected at least one structured reason.")


def render_la_fuel_leakage(data):
    records = build_la_fuel_records(data)
    if records.empty:
        st.info("Comparable fuel-use measurements are not available for the current filter.")
        return

    comparison_rows = []
    for fuel, subset in records.groupby("Fuel"):
        unit = subset["Daily Unit"].iloc[0]
        comparison_rows.extend([
            {"Fuel": fuel, "Period": "Before", "Median Daily Use": subset["Initial Daily Use"].median(), "Unit": unit, "Valid N": int(subset["Initial Daily Use"].notna().sum())},
            {"Fuel": fuel, "Period": "Current", "Median Daily Use": subset["Current Daily Use"].median(), "Unit": unit, "Valid N": int(subset["Current Daily Use"].notna().sum())},
        ])
    comparison = pd.DataFrame(comparison_rows)
    for fuel in ["Firewood", "LPG", "Kerosene"]:
        subset = comparison.loc[comparison["Fuel"].eq(fuel)]
        if subset.empty:
            continue
        fig = px.bar(
            subset,
            x="Period",
            y="Median Daily Use",
            color="Period",
            text_auto=".2f",
            hover_data=["Valid N"],
            title=f"{fuel}: Median Daily Use Before vs Current",
            color_discrete_sequence=PLOTLY_COLORWAY,
        )
        fig.update_layout(showlegend=False, yaxis_title=subset["Unit"].iloc[0])
        st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"la_fuel_before_after_{fuel}"))

    direction = records.groupby(["Fuel", "Direction"], as_index=False).size().rename(columns={"size": "Households"})
    direction["Share"] = direction["Households"] / direction.groupby("Fuel")["Households"].transform("sum") * 100
    fig = px.bar(
        direction,
        x="Fuel",
        y="Share",
        color="Direction",
        barmode="stack",
        text=direction["Share"].map(lambda value: f"{value:.1f}%" if value >= 5 else ""),
        title="Direction of Measured Fuel-Use Change",
        category_orders={"Direction": ["Increase", "No Change", "Decrease"]},
        color_discrete_map={"Increase": "#E89B2D", "No Change": "#7C8AA5", "Decrease": "#2C9C69"},
    )
    fig.update_layout(yaxis_title="Share of Comparable Households (%)", yaxis_range=[0, 100])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_fuel_direction"))

    render_la_positive_fuel_timing(data)

    timed_records = add_la_fuel_timing(data, records)
    positive = timed_records.loc[timed_records["Direction"].eq("Increase")]
    summary_rows = []
    for (fuel, unit), subset in positive.groupby(["Fuel", "Weekly Unit"]):
        summary_rows.append({
            "Fuel": fuel,
            "Observed Positive Measurements": int(subset["Respondent Index"].nunique()),
            "After Installation": int(subset.loc[subset["Timing"].eq("After Installation"), "Respondent Index"].nunique()),
            "Same-Year Ambiguous": int(subset.loc[subset["Timing"].eq("Same-Year Ambiguous"), "Respondent Index"].nunique()),
            "Timing Conflicts": int(subset.loc[subset["Timing"].eq("Before Installation Conflict"), "Respondent Index"].nunique()),
            "Mean Weekly Increase": subset["Weekly Difference"].mean(),
            "Median Weekly Increase": subset["Weekly Difference"].median(),
            "Unit": unit,
        })
    st.markdown("#### Weekly Increase Summary")
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True, column_config={
        "Mean Weekly Increase": st.column_config.NumberColumn(format="%.2f"),
        "Median Weekly Increase": st.column_config.NumberColumn(format="%.2f"),
    })
    st.info("Firewood and LPG are reported in kg/week. Kerosene remains in L/week and is not converted without an approved density factor.")


def render_la_fuel_consistency(data):
    eligible = eligible_la_data(data)
    records = add_la_fuel_timing(data, build_la_fuel_records(data))
    if records.empty:
        return
    reported = la_yes_mask(eligible[LA_FUEL_CHANGE]) if LA_FUEL_CHANGE in eligible else pd.Series(False, index=eligible.index)
    nonzero_indices = pd.Index(records.loc[records["Direction"].ne("No Change"), "Respondent Index"].unique())
    positive_indices = pd.Index(records.loc[records["Direction"].eq("Increase"), "Respondent Index"].unique())
    rows = [
        ("Reported fuel change but no non-zero measured difference", int((reported & ~eligible.index.isin(nonzero_indices)).sum())),
        ("Positive measured change before neighbor installation", int(records.loc[records["Direction"].eq("Increase") & records["Timing"].eq("Before Installation Conflict"), "Respondent Index"].nunique())),
        ("Fuel difference formula mismatch", int(records["Formula Mismatch"].sum())),
    ]

    changed_columns = [column for column in eligible.columns if str(column).startswith(LA_CHANGED_FUEL_QUESTION + "/")]
    option_names = {"Firewood": "Kayu Bakar", "LPG": "LPG", "Kerosene": "Minyak Tanah"}
    for fuel, option_name in option_names.items():
        option_column = next((column for column in changed_columns if str(column).endswith("/" + option_name)), None)
        if option_column is None:
            continue
        selected_indices = pd.Index(eligible.index[pd.to_numeric(eligible[option_column], errors="coerce").fillna(0).gt(0)])
        measured_indices = pd.Index(records.loc[records["Fuel"].eq(fuel), "Respondent Index"].unique())
        rows.append((f"{fuel}: selected but measurement missing", len(selected_indices.difference(measured_indices))))
        rows.append((f"{fuel}: measurement available but fuel not selected", len(measured_indices.difference(selected_indices))))

    reason_columns = [column for column in eligible.columns if str(column).startswith(LA_FUEL_INCREASE_REASON_QUESTION + "/")]
    if reason_columns:
        reason_selected = eligible[reason_columns].apply(lambda series: pd.to_numeric(series, errors="coerce").fillna(0).gt(0)).any(axis=1)
        rows.append(("Positive measured change without a structured reason", int((eligible.index.isin(positive_indices) & ~reason_selected).sum())))
        rows.append(("Structured increase reason without a positive measured change", int((~eligible.index.isin(positive_indices) & reason_selected).sum())))

    st.dataframe(pd.DataFrame(rows, columns=["Consistency Check", "Households"]), use_container_width=True, hide_index=True)
    st.caption("These checks do not modify the source workbook. They identify records that require review before final leakage attribution or reporting.")


def la_forest_masks(data):
    forest_user = la_yes_mask(data[LA_FOREST_FIREWOOD]) if LA_FOREST_FIREWOOD in data else pd.Series(False, index=data.index)
    reported_more = la_yes_mask(data[LA_MORE_FOREST_FIREWOOD]) if LA_MORE_FOREST_FIREWOOD in data else pd.Series(False, index=data.index)
    delta_column = LA_FUEL_SPECS["Firewood"]["Difference"]
    firewood_delta = pd.to_numeric(data.get(delta_column), errors="coerce")
    return forest_user, reported_more, firewood_delta


def render_la_forest_metrics(data):
    eligible = eligible_la_data(data)
    forest_user, reported_more, firewood_delta = la_forest_masks(eligible)
    supporting = forest_user & reported_more & firewood_delta.gt(0)
    timing = la_temporal_status(eligible, LA_FUEL_CHANGE_YEAR)
    metrics = [
        ("Valid Source Responses", int(eligible[LA_FOREST_FIREWOOD].notna().sum()) if LA_FOREST_FIREWOOD in eligible else 0),
        ("Current Forest/Garden Users", int(forest_user.sum())),
        ("Reported Using More", int((forest_user & reported_more).sum())),
        ("Supported by Measured Increase", int(supporting.sum())),
        ("Measured Increase After Installation", int((supporting & timing.eq("After Neighbor Installation")).sum())),
    ]
    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, f"{value:,}")


def render_la_forest_evidence(data):
    eligible = eligible_la_data(data)
    forest_user, reported_more, firewood_delta = la_forest_masks(eligible)
    target = forest_user & reported_more
    evidence = pd.Series("Measurement Missing", index=eligible.index)
    evidence.loc[target & firewood_delta.gt(0)] = "Measured Increase"
    evidence.loc[target & firewood_delta.lt(0)] = "Measured Decrease"
    evidence.loc[target & firewood_delta.eq(0)] = "Measured No Change"
    counts = evidence.loc[target].value_counts().rename_axis("Evidence").reset_index(name="Households")
    order = ["Measured Increase", "Measured No Change", "Measured Decrease", "Measurement Missing"]
    fig = px.bar(
        counts,
        x="Households",
        y="Evidence",
        orientation="h",
        text_auto=True,
        color="Evidence",
        category_orders={"Evidence": order},
        title="Measured Evidence for Reported Higher Forest/Garden Firewood Use",
        color_discrete_map={
            "Measured Increase": "#2C9C69",
            "Measured No Change": "#7C8AA5",
            "Measured Decrease": "#D95D52",
            "Measurement Missing": "#B7C3D0",
        },
    )
    fig.update_layout(showlegend=False, yaxis_title=None)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_forest_evidence"))

    supporting = target & firewood_delta.gt(0)
    timing = la_temporal_status(eligible, LA_FUEL_CHANGE_YEAR)
    timing_counts = timing.loc[supporting].replace({
        "After Neighbor Installation": "After Installation",
        "Same Year": "Same-Year Ambiguous",
        "Before Neighbor Installation": "Before Installation Conflict",
        "Timing Unavailable": "Timing Unavailable",
    }).value_counts().rename_axis("Timing").reset_index(name="Households")
    if not timing_counts.empty:
        fig = px.bar(
            timing_counts,
            x="Households",
            y="Timing",
            orientation="h",
            text_auto=True,
            color="Timing",
            title="Timing of Measured Supporting Cases",
            color_discrete_map={
                "After Installation": "#2C9C69",
                "Same-Year Ambiguous": "#E89B2D",
                "Before Installation Conflict": "#D95D52",
                "Timing Unavailable": "#7C8AA5",
            },
        )
        fig.update_layout(showlegend=False, yaxis_title=None)
        st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_forest_evidence_timing"))

    weekly = firewood_delta.loc[supporting] * 7
    if not weekly.empty:
        summary = pd.DataFrame([{
            "Measured Supporting Households": int(supporting.sum()),
            "After Installation": int((supporting & timing.eq("After Neighbor Installation")).sum()),
            "Same-Year Ambiguous": int((supporting & timing.eq("Same Year")).sum()),
            "Timing Conflicts": int((supporting & timing.eq("Before Neighbor Installation")).sum()),
            "Mean Total Firewood Increase": weekly.mean(),
            "Median Total Firewood Increase": weekly.median(),
            "Unit": "kg/week",
        }])
        st.dataframe(summary, use_container_width=True, hide_index=True, column_config={
            "Mean Total Firewood Increase": st.column_config.NumberColumn(format="%.2f"),
            "Median Total Firewood Increase": st.column_config.NumberColumn(format="%.2f"),
        })
        st.caption("The quantified amount is total firewood use, not a source-specific forest/garden quantity.")


def render_la_forest_reasons(data):
    columns = [column for column in data.columns if str(column).startswith(LA_FOREST_REASON_QUESTION + "/")]
    translations = {
        "Kayu bakar di hutan/kebon tersedia lebih banyak sekarang ini, lebih mudah diperoleh": "More Available or Easier to Obtain",
        "Kayu bakar yang berasal dari hutan/kebon harganya lebih murah": "Lower Cost",
        "Alasan lainnya": "Other",
    }
    if not columns:
        st.info("Structured forest/garden firewood reason fields are not available for the current filter.")
        return
    selected = data[columns].apply(lambda series: pd.to_numeric(series, errors="coerce").fillna(0).gt(0))
    chart_data = pd.DataFrame({
        "Reason": [translations.get(str(column).split(LA_FOREST_REASON_QUESTION + "/", 1)[-1].strip(), str(column)) for column in columns],
        "Households": [int(selected[column].sum()) for column in columns],
    })
    chart_data = chart_data.loc[chart_data["Households"].gt(0)].sort_values("Households")
    fig = px.bar(chart_data, x="Households", y="Reason", orientation="h", text_auto=True, title="Reasons for Reported Higher Forest/Garden Firewood Use", color_discrete_sequence=[PLOTLY_COLORWAY[1]])
    fig.update_layout(yaxis_title=None, xaxis_title="Households Selecting the Reason")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_forest_reasons"))
    st.caption(f"Multiple responses were allowed. {int(selected.any(axis=1).sum()):,} of {len(data):,} households selected at least one structured reason.")


def render_la_forest_consistency(data):
    eligible = eligible_la_data(data)
    forest_user, reported_more, firewood_delta = la_forest_masks(eligible)
    q39_change = la_yes_mask(eligible[LA_FUEL_CHANGE]) if LA_FUEL_CHANGE in eligible else pd.Series(False, index=eligible.index)
    changed_columns = [column for column in eligible.columns if str(column).startswith(LA_CHANGED_FUEL_QUESTION + "/")]
    firewood_option = next((column for column in changed_columns if str(column).endswith("/Kayu Bakar")), None)
    selected_firewood = pd.to_numeric(eligible[firewood_option], errors="coerce").fillna(0).gt(0) if firewood_option else pd.Series(False, index=eligible.index)
    timing = la_temporal_status(eligible, LA_FUEL_CHANGE_YEAR)
    target = forest_user & reported_more
    checks = pd.DataFrame([
        ("Missing forest/garden firewood source response", int(eligible[LA_FOREST_FIREWOOD].isna().sum()) if LA_FOREST_FIREWOOD in eligible else len(eligible)),
        ("Reported higher forest/garden firewood but no general fuel-quantity change", int((target & ~q39_change).sum())),
        ("Reported higher forest/garden firewood but firewood not selected in Q41", int((target & ~selected_firewood).sum())),
        ("Reported higher forest/garden firewood but Q42 difference is missing", int((target & firewood_delta.isna()).sum())),
        ("Reported higher forest/garden firewood but Q42 shows a decrease", int((target & firewood_delta.lt(0)).sum())),
        ("Measured supporting increase predates neighbor installation", int((target & firewood_delta.gt(0) & timing.eq("Before Neighbor Installation")).sum())),
    ], columns=["Consistency Check", "Households"])
    st.dataframe(checks, use_container_width=True, hide_index=True)
    st.caption("These checks flag interpretive limitations and do not modify the source workbook.")


def la_forest_summary(data):
    eligible = eligible_la_data(data)
    forest_mask = la_yes_mask(eligible[LA_FOREST_FIREWOOD]) if LA_FOREST_FIREWOOD in eligible else pd.Series(False, index=eligible.index)
    more_mask = la_yes_mask(eligible[LA_MORE_FOREST_FIREWOOD]) if LA_MORE_FOREST_FIREWOOD in eligible else pd.Series(False, index=eligible.index)
    forest_users = int(forest_mask.sum())
    more_users = int((forest_mask & more_mask).sum())
    valid_forest = int(eligible[LA_FOREST_FIREWOOD].notna().sum()) if LA_FOREST_FIREWOOD in eligible else 0
    render_summary_panel(
        "Forest/Garden Firewood Risk",
        [
            f"{forest_users:,} of {valid_forest:,} eligible households with a valid response reported using "
            "firewood sourced from forests or gardens.",
            f"{more_users:,} of {forest_users:,} current forest/garden firewood users reported using more than "
            "before the neighbor installation.",
        ],
        caveats=[
            "The source field combines forests and gardens and includes both collected and purchased firewood, "
            "so it cannot be interpreted as deforestation.",
            "Q42 measures total firewood use and cannot isolate the forest/garden-sourced portion.",
        ],
    )


def render_la_protocol_quality(data):
    eligible = eligible_la_data(data)
    fuel_records = build_la_fuel_records(data)
    fuel_changers = eligible.loc[la_yes_mask(eligible[LA_FUEL_CHANGE])] if LA_FUEL_CHANGE in eligible else eligible.iloc[0:0]
    invalid_years = pd.to_numeric(data.get("year_completion"), errors="coerce").notna() & ~pd.to_numeric(data.get("year_completion"), errors="coerce").between(2000, 2026)
    respondent_has = la_yes_mask(data[LA_RESPONDENT_BIOGAS]) if LA_RESPONDENT_BIOGAS in data else pd.Series(False, index=data.index)
    neighbor_no = la_no_mask(data[LA_NEIGHBOR_BIOGAS]) if LA_NEIGHBOR_BIOGAS in data else pd.Series(False, index=data.index)
    checks = [
        ("Respondent owns biogas", int(respondent_has.sum()), "Exclude from the non-user LA analytical base"),
        ("Referenced neighbor does not own biogas", int((~respondent_has & neighbor_no).sum()), "Exclude from the basic LA eligibility rule"),
        ("Fuel change predates neighbor installation", int(la_temporal_status(fuel_changers, LA_FUEL_CHANGE_YEAR).eq("Before Neighbor Installation").sum()), "Review chronology before attribution"),
        ("Invalid neighbor completion year", int(invalid_years.sum()), "Verify source year"),
        ("Fuel difference formula mismatch", int(fuel_records["Formula Mismatch"].sum()) if not fuel_records.empty else 0, "Recalculate current minus initial"),
    ]
    table = pd.DataFrame(checks, columns=["Validation Rule", "Records Processed", "Dashboard Treatment"])
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_fuel_change(data):
    fuel_specs = {
        "Firewood": {
            "Initial": [["jumlah penggunaan kayu awal"], ["42c", "kayu"]],
            "Current": [["jumlah penggunaan kayu saat ini"], ["42f", "kayu"]],
            "Difference": [["42g", "kayu"], ["selisih", "kayu"]],
        },
        "LPG": {
            "Initial": [["jumlah penggunaan lpg awal"], ["43c", "lpg"]],
            "Current": [["jumlah penggunaan lpg saat ini"], ["43f", "lpg"]],
            "Difference": [["43g", "lpg"], ["selisih", "lpg"]],
        },
        "Kerosene": {
            "Initial": [["44c", "minyak"], ["minyak", "awal"]],
            "Current": [["44f", "minyak"], ["minyak", "sekarang"]],
            "Difference": [["44g", "minyak"], ["selisih", "minyak"]],
        },
    }
    rows = []
    for fuel, measures in fuel_specs.items():
        for measure, keyword_options in measures.items():
            col = None
            for keywords in keyword_options:
                col = find_column(data, keywords=keywords)
                if col:
                    break
            if col:
                values = pd.to_numeric(data[col], errors="coerce")
                if values.notna().any():
                    rows.append({"Fuel": fuel, "Measure": measure, "Average Daily Use": values.mean(), "Valid N": int(values.notna().sum())})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Fuel consumption change columns are not available or do not contain valid numeric data.")
        return
    fig = px.bar(chart_data, x="Fuel", y="Average Daily Use", color="Measure", barmode="group", title="Average Fuel Use Change by Measurement", hover_data=["Valid N"])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_fuel_change"))


def render_fuel_difference_distribution(data):
    specs = {
        "Firewood": [["42g", "kayu"], ["selisih", "kayu"]],
        "LPG": [["43g", "lpg"], ["selisih", "lpg"]],
        "Kerosene": [["44g", "minyak"], ["selisih", "minyak"]],
    }
    rows = []
    for fuel, keyword_options in specs.items():
        col = None
        for keywords in keyword_options:
            col = find_column(data, keywords=keywords)
            if col:
                break
        if col:
            values = pd.to_numeric(data[col], errors="coerce").dropna()
            rows.extend({"Fuel": fuel, "Difference": value} for value in values)
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Fuel difference distribution columns are not available or do not contain valid numeric data.")
        return
    fig = px.box(chart_data, x="Fuel", y="Difference", points="outliers", title="Fuel Use Difference Distribution by Fuel (After - Before)")
    fig.add_hline(y=0, line_dash="dash", line_color="#7C8AA5")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key("la_fuel_difference_distribution"))


def render_la_neighbor_biogas_context(data):
    eligible = eligible_la_data(data)
    col1, col2, col3 = st.columns(3)
    with col1:
        render_value_counts(
            eligible,
            "year_completion",
            "Neighbor Biogas Installation Year",
            key="la_neighbor_installation_year",
        )
    with col2:
        render_value_counts(
            eligible,
            find_column(eligible, candidates=["19c. Tipe instalasi biogas tetangga", "B. Pengamatan Kondisi Rumah/19c. Tipe instalasi biogas tetangga"], keywords=["tipe", "instalasi", "biogas", "tetangga"]),
            "Neighbor Biogas Type",
            key="la_neighbor_biogas_type",
        )
    with col3:
        render_value_counts(
            eligible,
            find_column(eligible, candidates=["19b. Kapasitas instalasi biogas tetangga (m^3)", "B. Pengamatan Kondisi Rumah/19b. Kapasitas instalasi biogas tetangga (m^3)"], keywords=["kapasitas", "biogas", "tetangga"]),
            "Neighbor Biogas Digester Capacity (m³)",
            key="la_neighbor_biogas_capacity",
            category_label="Capacity (m³)",
        )


def render_la_livestock(data):
    count_columns = {
        "Pigs": ["31a. Jumlah Babi", "Jumlah Babi"],
        "Goats": ["31b. Jumlah Kambing"],
        "Sheep": ["31c. Jumlah Domba"],
        "Buffalo": ["31d. Jumlah Kerbau"],
        "Cattle": ["31e. Jumlah Sapi", "Jumlah Sapi"],
        "Poultry": ["31f. Jumlah Unggas (ayam, bebek, burung puyuh, dsb)", "Jumlah Unggas"],
    }
    render_livestock_summary(
        data,
        ["30. Apa saja hewan ternak yang pernah dimiliki?", "D. Ternak/30. Apa saja hewan ternak yang pernah dimiliki?"],
        count_columns,
        "la",
    )


def render_la_quality_summary(data):
    render_key_field_quality_summary(
        data,
        {
            "Province": {"candidates": ["province"]},
            "District": {"candidates": ["district"]},
            "Neighbor Has Biogas": {"keywords": ["tetangga", "memiliki", "biogas"]},
            "Respondent Has Biogas": {"keywords": ["rumah", "responden", "biogas"]},
            "Stove Change": {"keywords": ["perubahan", "jenis", "kompor"]},
            "Fuel Quantity Change": {"keywords": ["perubahan", "jumlah", "bahan", "bakar"]},
            "Firewood Difference": {"keywords": ["42g", "kayu"]},
            "LPG Difference": {"keywords": ["43g", "lpg"]},
            "Kerosene Difference": {"keywords": ["44g", "minyak"]},
            "House Latitude": {"candidates": ["house_lat"]},
            "House Longitude": {"candidates": ["house_long"]},
        },
        "LA Key Field Completeness",
        key="la_quality_completeness",
    )


def Page_LA():
    st.set_page_config(page_title="Leakage Assessment", page_icon=":bar_chart:", layout="wide")
    apply_global_theme()
    render_page_header("Leakage Assessment", "Survey 2026")

    if st.button("Home", key="Home LA", type="primary"):
        st.switch_page("new_main.py", query_params={"utm_source": "new_main.py"})

    source = load_la_data()
    data = apply_sidebar_filters(source, "la", title="LA Filters")

    st.caption("LA charts assess changes among non-user households living near a biogas user. Timing supports interpretation but does not by itself prove causality.")
    eligible = eligible_la_data(data)
    full_sample = len(data) == len(source)

    tabs = st.tabs([
        "Overview & Eligibility",
        "Attribution Evidence & Timing",
        "Stove Change",
        "Fuel Change & Leakage",
        "Forest/Garden Firewood Risk",
        "Map",
        "Data Coverage",
    ])

    with tabs[0]:
        render_la_overview_metrics(data, full_sample=full_sample)
        la_sample_summary(data, full_sample=full_sample)
        render_la_eligibility_breakdown(data)
        render_la_years_of_use_coverage(data, full_sample=full_sample)
        render_value_counts(eligible, "province", "Eligible Sample by Province", key="la_province")
        render_la_outcome_snapshot(data)
        with st.expander("District and Respondent Demographics"):
            col1, col2 = st.columns(2)
            with col1:
                render_value_counts(eligible, "gender", "Respondent Gender", key="la_gender")
                render_value_counts(eligible, "education", "Education Level", key="la_education")
            with col2:
                render_value_counts(eligible, "district", "Top Districts", key="la_district")
            render_la_demographics(eligible)
        with st.expander("Sampling Quality Notes"):
            render_la_sampling_quality(data, full_sample=full_sample)

    with tabs[1]:
        la_leakage_summary(data)
        render_la_temporal_evidence(data)
        render_la_time_lag_distribution(data)
        with st.expander("Neighbor Biogas Context"):
            render_la_neighbor_biogas_context(data)

    with tabs[2]:
        stove_changers = eligible.loc[la_yes_mask(eligible[LA_STOVE_CHANGE])] if LA_STOVE_CHANGE in eligible else eligible.iloc[0:0]
        added_stoves = int(la_yes_mask(eligible[LA_ADDED_STOVE]).sum()) if LA_ADDED_STOVE in eligible else 0
        eligible_count = len(eligible)
        stove_change_share = len(stove_changers) / eligible_count * 100 if eligible_count else 0
        added_stove_share = added_stoves / eligible_count * 100 if eligible_count else 0
        render_summary_panel(
            "Stove Change",
            [
                f"{len(stove_changers):,} of {eligible_count:,} eligible households "
                f"({stove_change_share:.1f}%) reported changing stove type.",
                f"{added_stoves:,} eligible households "
                f"({added_stove_share:.1f}%) reported adding a stove since the neighbor installation.",
                "Before-current comparisons and net changes are calculated directly from Q32 and Q33.",
            ],
            caveats=[
                "Reported changes are temporally associated with the neighbor comparison point; the questionnaire does not prove that the neighboring biodigester caused them."
            ],
        )
        col1, col2 = st.columns(2)
        with col1:
            render_value_counts(
                eligible,
                LA_STOVE_CHANGE,
                "Any Stove Type Change",
                key="la_stove_any_change",
            )
        with col2:
            render_value_counts(
                eligible,
                LA_ADDED_STOVE,
                "Added New Stove Since Neighbor Uses Biogas",
                key="la_added_new_stove",
            )
        render_stove_change(eligible)
        render_la_stove_transitions(eligible)
        render_stove_difference(eligible)
        render_la_stove_reasons(stove_changers)
        with st.expander("Stove Data Consistency Notes"):
            render_la_stove_consistency(eligible)

    with tabs[3]:
        render_la_fuel_metrics(data)
        la_fuel_stove_summary(data)
        fuel_changers = eligible.loc[la_yes_mask(eligible[LA_FUEL_CHANGE])] if LA_FUEL_CHANGE in eligible else eligible.iloc[0:0]
        col1, col2 = st.columns(2)
        with col1:
            render_value_counts(
                eligible,
                LA_FUEL_CHANGE,
                "Any Fuel Quantity Change",
                key="la_any_fuel_change",
            )
        with col2:
            render_la_changed_fuel_types(fuel_changers)
        render_la_fuel_leakage(data)
        fuel_records = build_la_fuel_records(data)
        positive_indices = fuel_records.loc[fuel_records["Direction"].eq("Increase"), "Respondent Index"].unique() if not fuel_records.empty else []
        positive_households = eligible.loc[eligible.index.isin(positive_indices)]
        render_la_fuel_increase_reasons(positive_households)
        with st.expander("Fuel Data Consistency Notes"):
            render_la_fuel_consistency(data)

    with tabs[4]:
        render_la_forest_metrics(data)
        la_forest_summary(data)
        forest_users = eligible.loc[la_yes_mask(eligible[LA_FOREST_FIREWOOD])] if LA_FOREST_FIREWOOD in eligible else eligible.iloc[0:0]
        col1, col2 = st.columns(2)
        with col1:
            render_value_counts(eligible.loc[eligible[LA_FOREST_FIREWOOD].notna()], LA_FOREST_FIREWOOD, "Current Forest/Garden Firewood Use", key="la_forest_firewood")
        with col2:
            render_value_counts(forest_users, LA_MORE_FOREST_FIREWOOD, "Reported Higher Use among Current Users", key="la_more_forest_firewood")
        render_la_forest_evidence(data)
        more_forest = forest_users.loc[la_yes_mask(forest_users[LA_MORE_FOREST_FIREWOOD])] if LA_MORE_FOREST_FIREWOOD in forest_users else forest_users.iloc[0:0]
        render_la_forest_reasons(more_forest)
        with st.expander("Forest/Garden Firewood Data Consistency Notes"):
            render_la_forest_consistency(data)
        with st.expander("Livestock Context"):
            render_la_livestock(eligible)

    with tabs[5]:
        la_map_summary(eligible)
        render_location_map(eligible, "la")

    with tabs[6]:
        la_quality_summary_text(data)
        render_la_quality_summary(data)
        with st.expander("Technical Validation Details"):
            render_la_protocol_quality(data)
            render_quality_notes(data, "la")

    render_footer()


pg = st.navigation([Page_LA, st.Page("new_main.py")], position="hidden")
pg.run()
