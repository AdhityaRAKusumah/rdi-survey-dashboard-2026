from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import folium
    from streamlit_folium import folium_static
except ModuleNotFoundError:
    folium = None
    folium_static = None

from translation import translate_display_text, translate_label_text
from ui_theme import DEEP_BLUE, INK, MUTED, PLOTLY_COLORWAY, SURFACE


DATA_NEW_DIR = Path(__file__).resolve().parent / "Data New"


def load_survey_workbook(filename):
    path = DATA_NEW_DIR / filename
    workbook = pd.ExcelFile(path)
    frames = []
    for sheet in workbook.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet)
        frame["_source_sheet"] = sheet
        if "province" not in frame.columns:
            frame["province"] = sheet
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def clean_display_text(value):
    return translate_display_text(value)


def normalize_common_columns(df):
    data = df.copy()
    aliases = {
        "A. Profil Rumah Tangga/2. Provinsi": "province",
        "A. Profil Rumah Tangga/3. Kabupaten": "district",
        "A. Profil Rumah Tangga/4. Kecamatan": "subdistrict",
        "A. Profil Rumah Tangga/5. Desa": "village",
        "A. Profil Rumah Tangga/_8a. Koordinat Rumah_latitude": "house_lat",
        "A. Profil Rumah Tangga/_8a. Koordinat Rumah_longitude": "house_long",
        "A. Profil Rumah Tangga/10. Jenis kelamin responden": "gender",
        "A. Profil Rumah Tangga/11. Usia responden": "age",
        "A. Profil Rumah Tangga/12. Tingkat pendidikan": "education",
        "A. Profil Rumah Tangga/16. Jumlah orang yang tinggal di dalam rumah tangga": "hh_members",
        "16. Jumlah orang yang tinggal di dalam rumah tangga": "hh_members",
        "Provinsi Data": "province",
        "Kabupaten Data": "district",
        "Kecamatan Data": "subdistrict",
        "Desa Data": "village",
        "Status Biogas": "biogas_status",
        "IDBP Biogas": "plant_code",
        "Koordinat rumah_latitude": "house_lat",
        "Koordinat rumah_longitude": "house_long",
    }
    data = data.rename(columns={k: v for k, v in aliases.items() if k in data.columns})
    if data.columns.duplicated().any():
        data = data.T.groupby(level=0).first().T
    if "years_of_use" not in data.columns and "year_of_use" in data.columns:
        data["years_of_use"] = data["year_of_use"]
    if "province" in data.columns:
        data["province"] = data["province"].fillna(data.get("_source_sheet")).astype(str).str.strip()
    string_columns = data.select_dtypes(include=["object"]).columns
    data[string_columns] = data[string_columns].apply(lambda series: series.apply(clean_display_text))
    return data


def apply_sidebar_filters(data, key_prefix, title="Dashboard Filters"):
    st.sidebar.markdown(f"### {title}")
    filtered = data.copy()
    for label, column in [("Province", "province"), ("District", "district")]:
        if column not in filtered.columns:
            continue
        options = sorted(v for v in filtered[column].dropna().astype(str).unique() if v and v != "nan")
        if not options:
            continue
        default = options
        selected = st.sidebar.multiselect(label, options=options, default=default, key=f"{key_prefix}_{column}")
        if selected and len(selected) < len(options):
            filtered = filtered[filtered[column].astype(str).isin(selected)]
    st.sidebar.markdown(f"**Filtered data:** {len(filtered):,} rows")
    return filtered


def apply_plot_theme(fig):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        colorway=PLOTLY_COLORWAY,
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=18, color=DEEP_BLUE), x=0.02, xanchor="left"),
        margin=dict(l=50, r=28, t=72, b=52),
        legend=dict(bgcolor="rgba(255,255,255,0)", font=dict(color=INK, size=12)),
        hoverlabel=dict(bgcolor=DEEP_BLUE, bordercolor=DEEP_BLUE, font=dict(color="#FFFFFF")),
    )
    fig.update_xaxes(gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def unique_chart_key(key):
    if key is None:
        return None
    counter_key = "_bkn_chart_key_counter"
    st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
    return f"{key}_{st.session_state[counter_key]}"


def shorten_chart_label(value, max_length=36):
    text = translate_display_text(value)
    if pd.isna(text):
        return text
    text = str(text).strip()
    compact_map = {
        "Yes, Stove Type Changed": "Stove Changed",
        "No, Stove Type Remains The Same": "No Change",
        "Forest/Garden Firewood Is More Available And Easier To Obtain": "Firewood Easier To Obtain",
        "Forest/Garden Firewood Is Cheaper": "Cheaper Forest Firewood",
        "Fuel Is Easier To Obtain Nearby": "Fuel Easier To Obtain",
        "Fuel Is More Affordable/Cheaper": "Fuel Is Cheaper",
        "Household Members Increased": "Household Increased",
        "More Stoves Used At The Same Time": "More Stoves Used",
        "Cooking Needs Increased": "Cooking Needs Increased",
        "Lower Fuel Or Stove Cost": "Lower Fuel/Stove Cost",
        "Cleaner And Healthier Kitchen": "Cleaner Kitchen",
        "Received Assistance/Subsidy": "Assistance/Subsidy",
    }
    for phrase, short in compact_map.items():
        if text.startswith(phrase) or phrase in text:
            return short
    return text if len(text) <= max_length else text[: max_length - 1].rstrip() + "..."


def render_basic_metrics(data, prefix=""):
    cols = st.columns(4)
    cols[0].metric("Respondents", f"{len(data):,}")
    cols[1].metric("Provinces", f"{data['province'].nunique() if 'province' in data else 0:,}")
    cols[2].metric("Districts", f"{data['district'].nunique() if 'district' in data else 0:,}")
    age = pd.to_numeric(data["age"], errors="coerce") if "age" in data else pd.Series(dtype=float)
    cols[3].metric("Average Age", f"{age.mean():.1f}" if age.notna().any() else "-")


def _valid_text_series(data, column):
    if column not in data.columns:
        return pd.Series(dtype=object)
    series = data[column].dropna().astype(str).str.strip()
    series = series[series.ne("") & series.str.lower().ne("nan")]
    return series.apply(translate_display_text)


def _format_pct(value):
    return f"{value:.1f}%"


def distribution_insight(data, column, label=None):
    if not column or column not in data.columns:
        return None
    label = label or str(column)
    series = _valid_text_series(data, column)
    if series.empty:
        return f"{label}: no valid data is available for the current filter."
    counts = series.value_counts()
    top_label = counts.index[0]
    top_count = int(counts.iloc[0])
    pct = top_count / len(series) * 100
    missing = len(data) - len(series)
    insight = f"{label}: the most common category is {top_label} ({top_count:,} respondents, {_format_pct(pct)} of valid responses)."
    if len(counts) > 1:
        second_label = counts.index[1]
        second_count = int(counts.iloc[1])
        insight += f" The next category is {second_label} ({second_count:,})."
    if missing:
        insight += f" There are {missing:,} rows without a response."
    return insight


def numeric_insight(data, column, label=None, unit=""):
    if not column or column not in data.columns:
        return None
    label = label or str(column)
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    if values.empty:
        return f"{label}: no valid numeric data is available for the current filter."
    unit_text = f" {unit}" if unit else ""
    return (
        f"{label}: average {values.mean():.2f}{unit_text}, median {values.median():.2f}{unit_text}, "
        f"with a range of {values.min():.2f}-{values.max():.2f}{unit_text} from {len(values):,} valid records."
    )


def option_insight(data, prefixes, label):
    prefixes = prefixes if isinstance(prefixes, (list, tuple)) else [prefixes]
    cols = option_columns_by_prefixes(data, prefixes)
    rows = []
    for col in cols:
        count = truthy_count(data[col])
        if count:
            display_label = translate_display_text(option_label(col).replace(".1", "").strip())
            rows.append((display_label, count))
    if not rows:
        return f"{label}: no selected options are available for the current filter."
    rows = sorted(rows, key=lambda item: item[1], reverse=True)
    total = sum(count for _, count in rows)
    top = rows[:3]
    top_text = ", ".join(f"{name} ({count:,})" for name, count in top)
    return f"{label}: the most frequently selected options are {top_text}. Total selected options: {total:,}; this can exceed the respondent count when the question is multi-select."


def grouped_comparison_insight(data, group_col, value_col, label):
    if group_col not in data.columns or not value_col or value_col not in data.columns:
        return None
    rows = []
    for group, subset in data.groupby(group_col):
        values = pd.to_numeric(subset[value_col], errors="coerce").dropna()
        if values.notna().any():
            rows.append((translate_display_text(group), values.mean(), len(values)))
    if not rows:
        return f"{label}: no valid numeric data is available for comparison."
    rows = sorted(rows, key=lambda item: item[1], reverse=True)
    best = rows[0]
    return f"{label}: the highest average is found in {best[0]} ({best[1]:.2f}, n={best[2]:,})."


def map_insight(data, label="Map"):
    if "house_lat" not in data.columns or "house_long" not in data.columns:
        return f"{label}: coordinate columns are not available."
    lat = normalize_coordinate_series(data["house_lat"], -12, 7)
    lon = normalize_coordinate_series(data["house_long"], 94, 142)
    valid = lat.notna() & lon.notna()
    valid_count = int(valid.sum())
    if valid_count == 0:
        return f"{label}: no valid coordinate points are available for the current filter."
    province_count = data.loc[valid, "province"].nunique() if "province" in data.columns else 0
    district_count = data.loc[valid, "district"].nunique() if "district" in data.columns else 0
    return f"{label}: {valid_count:,} valid coordinate points are available, spread across {province_count:,} provinces and {district_count:,} districts/cities for the current filter."


def quality_insight(data, columns, label="Quality"):
    rows = []
    for name, column in columns.items():
        if column and column in data.columns:
            valid = _valid_text_series(data, column).shape[0]
            rows.append((name, valid, len(data) - valid))
        else:
            rows.append((name, 0, len(data)))
    if not rows:
        return None
    weakest = sorted(rows, key=lambda item: item[1])[0]
    return f"{label}: the field with the lowest completeness is {weakest[0]} ({weakest[1]:,} filled, {weakest[2]:,} missing)."


def render_summary_panel(title, insights, caveats=None):
    cleaned = [item for item in insights if item]
    caveats = [item for item in (caveats or []) if item]
    if not cleaned and not caveats:
        return
    items = "".join(f"<li>{item}</li>" for item in cleaned[:7])
    caveat_items = "".join(f"<li>{item}</li>" for item in caveats[:3])
    caveat_block = f"<div class='summary-caveats'><b>Notes:</b><ul>{caveat_items}</ul></div>" if caveat_items else ""
    st.markdown(
        f"""
        <div class="summary-panel">
            <div class="summary-title">{title}</div>
            <ul>{items}</ul>
            {caveat_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_value_counts(data, column, title, key=None, top=10, category_label="Category"):
    if column not in data.columns:
        st.info(f"Column is not available for this chart: {title}")
        return
    series = data[column].dropna().astype(str).str.strip()
    series = series[series.ne("") & series.ne("nan")]
    series = series.apply(translate_display_text)
    if series.empty:
        st.info(f"No valid data is available for this chart: {title}")
        return
    counts = series.value_counts().head(top).reset_index()
    counts.columns = ["Category", "Count"]
    counts["Display Category"] = counts["Category"].apply(shorten_chart_label)
    use_horizontal = len(counts) > 5 or counts["Category"].astype(str).str.len().mean() > 18
    if use_horizontal:
        counts = counts.sort_values("Count", ascending=True)
        fig = px.bar(
            counts,
            x="Count",
            y="Display Category",
            title=title,
            text_auto=True,
            orientation="h",
            labels={"Display Category": category_label},
            hover_data={"Category": True, "Display Category": False},
            height=max(520, 42 * max(len(counts), 8)),
        )
    else:
        fig = px.bar(
            counts,
            x="Display Category",
            y="Count",
            title=title,
            text_auto=True,
            labels={"Display Category": category_label},
            hover_data={"Category": True, "Display Category": False},
        )
    fig.update_traces(marker_color=PLOTLY_COLORWAY[0])
    fig.update_layout(xaxis_tickangle=0 if use_horizontal else -20)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def render_histogram(data, column, title, key=None, x_label=None):
    if column not in data.columns:
        st.info(f"Column is not available for this chart: {title}")
        return
    values = pd.to_numeric(data[column], errors="coerce").dropna()
    if values.empty:
        st.info(f"No valid numeric data is available for this chart: {title}")
        return
    fig = px.histogram(values.to_frame(name=x_label or column), x=x_label or column, nbins=20, title=title)
    fig.update_traces(marker_color=PLOTLY_COLORWAY[0], opacity=0.86)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def option_columns(data, question_prefix, exclude_suffixes=None):
    exclude_suffixes = tuple(exclude_suffixes or ())
    return [
        col for col in data.columns
        if str(col).startswith(question_prefix + "/") and not str(col).endswith(exclude_suffixes)
    ]


def option_columns_by_prefixes(data, prefixes, exclude_suffixes=None):
    columns = []
    for prefix in prefixes:
        for col in option_columns(data, prefix, exclude_suffixes=exclude_suffixes):
            if col not in columns:
                columns.append(col)
    return columns


def option_label(column):
    """Return option text without breaking labels that contain a slash."""
    text = str(column)
    return text.split("/", 1)[1].strip() if "/" in text else text.strip()


def truthy_count(series):
    cleaned = series.dropna().astype(str).str.strip().str.lower()
    cleaned = cleaned[~cleaned.isin(["", "0", "0.0", "false", "no", "tidak", "nan", "none"])]
    return int(cleaned.shape[0])


def normalize_coordinate_series(series, lower, upper):
    values = pd.to_numeric(series, errors="coerce")

    def normalize_value(value):
        if pd.isna(value):
            return pd.NA
        value = float(value)
        for divisor in (1, 10, 100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000):
            candidate = value / divisor
            if lower <= candidate <= upper:
                return candidate
        return pd.NA

    return values.apply(normalize_value)


def render_option_counts(data, question_prefix, title, key=None):
    prefixes = question_prefix if isinstance(question_prefix, (list, tuple)) else [question_prefix]
    cols = option_columns_by_prefixes(data, prefixes)
    if not cols:
        st.info(f"Option columns are not available for this chart: {title}")
        return
    rows = []
    for col in cols:
        label = translate_display_text(option_label(col).replace(".1", "").strip())
        rows.append({"Category": label, "Count": truthy_count(data[col])})
    chart_data = pd.DataFrame(rows).sort_values("Count", ascending=False)
    chart_data = chart_data[chart_data["Count"] > 0]
    if chart_data.empty:
        st.info(f"No selected options are available for this chart: {title}")
        return
    chart_data["Display Category"] = chart_data["Category"].apply(shorten_chart_label)
    use_horizontal = len(chart_data) > 5 or chart_data["Category"].astype(str).str.len().mean() > 18
    if use_horizontal:
        chart_data = chart_data.sort_values("Count", ascending=True)
        fig = px.bar(
            chart_data,
            x="Count",
            y="Display Category",
            title=title,
            text_auto=True,
            orientation="h",
            labels={"Display Category": "Category"},
            hover_data={"Category": True, "Display Category": False},
            height=max(520, 42 * max(len(chart_data), 8)),
        )
    else:
        fig = px.bar(
            chart_data,
            x="Display Category",
            y="Count",
            title=title,
            text_auto=True,
            labels={"Display Category": "Category"},
            hover_data={"Category": True, "Display Category": False},
        )
    fig.update_traces(marker_color=PLOTLY_COLORWAY[1])
    fig.update_layout(xaxis_tickangle=0 if use_horizontal else -20)
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def render_livestock_summary(data, option_prefixes, count_columns, key_prefix):
    render_option_counts(data, option_prefixes, "Livestock Types Owned", key=f"{key_prefix}_livestock_types")
    rows = []
    for label, candidates in count_columns.items():
        col = find_column(data, candidates=candidates)
        if col:
            values = pd.to_numeric(data[col], errors="coerce")
            if values.notna().any():
                rows.append({
                    "Livestock": label,
                    "Total": values.sum(),
                    "Average": values.mean(),
                    "Valid N": int(values.notna().sum()),
                })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Livestock count columns are not available or do not contain valid numeric data.")
        return
    fig = px.bar(chart_data, x="Livestock", y="Total", title="Total Livestock Counts", text_auto=".0f", hover_data=["Average", "Valid N"])
    fig.update_traces(marker_color=PLOTLY_COLORWAY[2])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_livestock_counts"))


def render_key_field_quality_summary(data, field_specs, title, key=None):
    rows = []
    for label, spec in field_specs.items():
        column = find_column(data, candidates=spec.get("candidates"), keywords=spec.get("keywords"))
        if column and column in data.columns:
            series = data[column].dropna().astype(str).str.strip()
            filled = int(series[series.ne("") & series.ne("nan")].shape[0])
            rows.append({
                "Field": label,
                "Column": translate_label_text(str(column).split("/")[-1], max_length=96),
                "Filled": filled,
                "Missing": int(len(data) - filled),
                "Completeness (%)": round((filled / len(data) * 100), 1) if len(data) else 0,
            })
        else:
            rows.append({
                "Field": label,
                "Column": "Not found",
                "Filled": 0,
                "Missing": int(len(data)),
                "Completeness (%)": 0,
            })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    chart_data = pd.DataFrame(rows)
    fig = px.bar(chart_data, x="Field", y="Completeness (%)", title=title, text="Completeness (%)")
    fig.update_traces(marker_color=PLOTLY_COLORWAY[0], texttemplate="%{text:.1f}%")
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def find_column(data, candidates=None, keywords=None):
    candidates = candidates or []
    for candidate in candidates:
        if candidate in data.columns:
            return candidate
    if not keywords:
        return None
    lowered = [(col, str(col).lower()) for col in data.columns]
    matches = []
    for col, low in lowered:
        if all(keyword.lower() in low for keyword in keywords):
            matches.append(col)
    if not matches:
        return None
    return sorted(matches, key=lambda value: ("/" in str(value), len(str(value))))[0]


def render_numeric_columns(data, columns, title, key=None, unit=""):
    rows = []
    for label, column in columns.items():
        if column and column in data.columns:
            values = pd.to_numeric(data[column], errors="coerce")
            if values.notna().any():
                rows.append({"Metric": label, "Average": values.mean(), "Median": values.median(), "Valid N": int(values.notna().sum())})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info(f"No valid numeric data is available for this chart: {title}")
        return
    fig = px.bar(chart_data, x="Metric", y="Average", title=title, text_auto=".2f", hover_data=["Median", "Valid N"])
    fig.update_traces(marker_color=PLOTLY_COLORWAY[2])
    fig.update_yaxes(title_text=f"Average {unit}".strip())
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(key))


def render_daily_fuel_usage(data, key_prefix):
    fuels = {
        "LPG": ["10a. Total penggunaan LPG Hari 1", "10b. Total penggunaan LPG Hari 2", "10c. Total penggunaan LPG Hari 3", "10d. Total penggunaan LPG Hari 4"],
        "Firewood": ["13a. Total penggunaan KAYU BAKAR Hari 1", "13b. Total penggunaan KAYU BAKAR Hari 2", "13c. Total penggunaan KAYU BAKAR Hari 3", "13d. Total penggunaan KAYU BAKAR Hari 4"],
        "Kerosene": ["16a. Total penggunaan MINYAK TANAH Hari 1", "16b. Total penggunaan MINYAK TANAH Hari 2", "16c. Total penggunaan MINYAK TANAH Hari 3", "16d. Total penggunaan MINYAK TANAH Hari 4"],
    }
    rows = []
    for fuel, columns in fuels.items():
        for day, col in enumerate(columns, start=1):
            if col in data.columns:
                values = pd.to_numeric(data[col], errors="coerce")
                if values.notna().any():
                    rows.append({"Fuel": fuel, "Day": f"Day {day}", "Average Usage": values.mean(), "Valid N": int(values.notna().sum())})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("Daily fuel usage columns are not available or do not contain valid numeric data.")
        return
    fig = px.line(chart_data, x="Day", y="Average Usage", color="Fuel", markers=True, title="Average Daily Fuel Usage During KPT", hover_data=["Valid N"])
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_daily_fuel"))


def render_person_meals(data, key_prefix):
    groups = {
        "Breakfast": ["4c_men", "4c_women", "4c_children", "4c_elders"],
        "Lunch": ["4d_men", "4d_women", "4d_children", "4d_elders"],
        "Dinner": ["4e_men", "4e_women", "4e_children", "4e_elders"],
        "Warm Water": ["4f_men", "4f_women", "4f_children", "4f_elders"],
    }
    rows = []
    for meal, cols in groups.items():
        for col in cols:
            if col in data.columns:
                values = pd.to_numeric(data[col], errors="coerce")
                label = col.split("_")[-1].title()
                rows.append({"Meal": meal, "Group": label, "Average Person-Meals": values.mean()})
    chart_data = pd.DataFrame(rows).dropna()
    if chart_data.empty:
        st.info("Person-meals columns are not available or do not contain valid numeric data.")
        return
    fig = px.bar(chart_data, x="Meal", y="Average Person-Meals", color="Group", barmode="group", title="Average Person-Meals by Meal Time")
    st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_person_meals"))


def render_location_map(data, key_prefix):
    if "house_lat" not in data.columns or "house_long" not in data.columns:
        st.info("House coordinate columns are not available in this dataset.")
        return
    points = data.copy()
    original_lat = pd.to_numeric(points["house_lat"], errors="coerce")
    original_long = pd.to_numeric(points["house_long"], errors="coerce")
    points["house_lat"] = normalize_coordinate_series(points["house_lat"], -12, 7)
    points["house_long"] = normalize_coordinate_series(points["house_long"], 94, 142)
    points = points.dropna(subset=["house_lat", "house_long"])
    points = points[
        points["house_lat"].between(-12, 7)
        & points["house_long"].between(94, 142)
    ]
    if points.empty:
        st.info("House coordinates do not contain valid latitude/longitude values for the current filter.")
        return
    corrected = (
        original_lat.abs().gt(90).fillna(False)
        | original_long.abs().gt(180).fillna(False)
    ).sum()
    st.caption(
        f"Showing {len(points):,} respondent points with valid coordinates"
        + (f"; {corrected:,} coordinates were normalized from a missing-decimal format." if corrected else ".")
    )
    with st.expander("Coordinate sample", expanded=False):
        sample_cols = [col for col in ["province", "district", "subdistrict", "dataset", "house_lat", "house_long"] if col in points.columns]
        st.dataframe(points[sample_cols].head(20), use_container_width=True, hide_index=True)
    if folium is None or folium_static is None:
        fig = px.scatter_geo(
            points,
            lat="house_lat",
            lon="house_long",
            color="province" if "province" in points.columns else None,
            hover_name="district" if "district" in points.columns else None,
            hover_data=[col for col in ["province", "district", "subdistrict", "dataset"] if col in points.columns],
            title="Respondent Geographic Distribution",
            height=560,
        )
        fig.update_traces(marker=dict(size=8, opacity=0.78, line=dict(width=0.8, color="#FFFFFF")))
        fig.update_geos(
            projection_type="natural earth",
            lataxis_range=[-12, 7],
            lonaxis_range=[94, 142],
            showland=True,
            landcolor="#EFF6FF",
            showcountries=True,
            countrycolor="rgba(20, 36, 58, 0.22)",
            showocean=True,
            oceancolor="#E0F2FE",
            showframe=False,
        )
        st.plotly_chart(apply_plot_theme(fig), use_container_width=True, key=unique_chart_key(f"{key_prefix}_geo_map"))
        return

    center = [points["house_lat"].mean(), points["house_long"].mean()]
    fmap = folium.Map(location=center, zoom_start=6, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Standard").add_to(fmap)
    folium.TileLayer("CartoDB positron", name="Light").add_to(fmap)
    folium.TileLayer("OpenTopoMap", name="Topo").add_to(fmap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(fmap)

    marker_layer = folium.FeatureGroup(name="Respondent points", overlay=True, control=True, show=True)
    marker_colors = ["#184F8F", "#E66F51", "#3FA46A", "#F4B942", "#6C63B8", "#1F9D9A", "#7C8AA5"]
    color_map = {
        province: marker_colors[idx % len(marker_colors)]
        for idx, province in enumerate(sorted(points["province"].dropna().astype(str).unique())) if "province" in points.columns
    }
    for _, row in points.iterrows():
        province = str(row.get("province", ""))
        popup_lines = [
            f"<b>Province:</b> {province}",
            f"<b>District:</b> {row.get('district', '')}",
            f"<b>Subdistrict:</b> {row.get('subdistrict', '')}",
        ]
        if "dataset" in points.columns:
            popup_lines.append(f"<b>Dataset:</b> {row.get('dataset', '')}")
        folium.CircleMarker(
            [row["house_lat"], row["house_long"]],
            radius=7,
            color=color_map.get(province, DEEP_BLUE),
            fill=True,
            fill_color=color_map.get(province, DEEP_BLUE),
            fill_opacity=0.9,
            weight=2,
            popup=folium.Popup("<br>".join(popup_lines), max_width=320),
        ).add_to(marker_layer)
    marker_layer.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    folium_static(fmap, width=1500, height=680)


def render_quality_notes(data, key_prefix):
    note_cols = [
        col for col in data.columns
        if any(token in str(col).lower() for token in ["jelaskan jika", "catatan validasi", "sebutkan alasan lainnya", "lainnya:"])
    ]
    filled = []
    for col in note_cols:
        count = data[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().shape[0]
        if count:
            filled.append({"Column": translate_label_text(str(col).split("/")[-1], max_length=96), "Filled Rows": count})
    if not filled:
        st.info("No long-text note columns are filled for the current filter.")
        return
    st.dataframe(pd.DataFrame(filled).sort_values("Filled Rows", ascending=False), use_container_width=True, hide_index=True)
