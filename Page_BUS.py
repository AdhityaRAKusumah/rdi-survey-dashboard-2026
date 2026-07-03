import streamlit as st
import pandas as pd
import numpy as np
import re
import plotly.express as px
import plotly.graph_objects as go
from streamlit_folium import folium_static
from chart_gen import ChartGenerator # Import chart generator class
from survey_dashboard import distribution_insight, numeric_insight, render_summary_panel
from translation import translate_display_text, translate_label_text
from ui_theme import DEEP_BLUE, INK, MUTED, PLOTLY_COLORWAY, SURFACE, apply_global_theme, render_footer, render_page_header, render_sidebar_header

BUS_DATA_FILE = r'Data New\Clean Data BUS.xlsx'
BUS_COLUMN_CHANGES_FILE = r'Data New\Column Name Changes.xlsx'
BUS_SCHEMA_SHEET = 'V1'
BUS_DATA_SHEETS = [
    'Jawa Tengah',
    'Sulawesi Selatan',
    'Bali',
    'DIY',
    'NTT',
    'Jawa Barat',
    'Jawa Timur',
]


@st.cache_data(show_spinner=False)
def load_bus_column_changes():
    mapping = pd.read_excel(BUS_COLUMN_CHANGES_FILE)
    mapping = mapping.dropna(subset=["Old Columns", "New Columns"]).copy()
    mapping["old"] = mapping["Old Columns"].astype(str).str.strip()
    mapping["new"] = mapping["New Columns"].astype(str).str.strip()
    mapping["old_index"] = pd.to_numeric(mapping["No."], errors="coerce").sub(1).astype("Int64")
    old_to_new = dict(zip(mapping["old"], mapping["new"]))
    new_to_old = dict(zip(mapping["new"], mapping["old"]))
    index_to_new = {
        int(row.old_index): row.new
        for row in mapping.itertuples(index=False)
        if pd.notna(row.old_index)
    }
    return mapping[["old_index", "old", "new"]], old_to_new, new_to_old, index_to_new


def normalize_bus_columns(data, schema_columns):
    schema_columns = list(schema_columns)
    source_columns = set(data.columns)
    rename_map = {}
    for column in data.columns:
        normalized_name = normalize_bus_column_name(column, source_columns)
        if normalized_name in schema_columns and normalized_name != column:
            rename_map[column] = normalized_name

    normalized_data = data.rename(columns=rename_map)
    if normalized_data.columns.duplicated().any():
        normalized_data = normalized_data.groupby(level=0, axis=1).first()
    return normalized_data


def normalize_bus_column_name(column, source_columns):
    name = str(column).strip()
    name = name.replace('E3-a. Hewan ternak apa saja yang Anda miliki sebelum menggunakan  biogas?', 'E. Dampak Terhadap Agrikultur /E3. Hewan ternak apa saja yang Anda miliki sebelum menggunakan  biogas?')
    name = name.replace('firewoord', 'firewood')
    name = name.replace('pride', 'price')
    name = name.replace('priee', 'price')
    name = name.replace('priff', 'price')
    name = name.replace('B5-b2_LPG_qty', 'B5-b2_LPG_price')

    a5_prefix = 'A. Performa Teknis Sistem Biogas /A5. Siapa yang mengajukan pemasangan biogas di rumah?/'
    a5_options = {
        'a. Anggota keluarga - laki-laki': 'Anggota keluarga - laki-laki',
        'b. Anggota keluarga - perempuan dewasa': 'Anggota keluarga - perempuan dewasa',
        'c. Koperasi': 'Koperasi',
        'd. Lainnya': 'Lainnya',
    }
    if name.startswith(a5_prefix):
        option = name.replace(a5_prefix, '', 1)
        if option in a5_options:
            return a5_prefix + a5_options[option]
        prefixed_source_exists = any(
            f'{a5_prefix}{prefix}. {option}' in source_columns
            for prefix in ['a', 'b', 'c', 'd']
        )
        if prefixed_source_exists and not option.endswith('.1'):
            return f'{name}.1'

    return name


@st.cache_data(show_spinner="Loading BUS data...")
def load_bus_data(_cache_version="dashboard_4_short_columns_v1"):
    _, _, new_to_old, index_to_new = load_bus_column_changes()
    workbook = pd.ExcelFile(BUS_DATA_FILE)
    if "Data" in workbook.sheet_names:
        combined = pd.read_excel(BUS_DATA_FILE, sheet_name="Data")
    else:
        schema_columns = pd.read_excel(BUS_DATA_FILE, sheet_name=BUS_SCHEMA_SHEET, nrows=0).columns
        data_sheets = pd.read_excel(BUS_DATA_FILE, sheet_name=BUS_DATA_SHEETS)
        aligned_sheets = [
            normalize_bus_columns(data_sheets[sheet_name], schema_columns).reindex(columns=schema_columns)
            for sheet_name in BUS_DATA_SHEETS
        ]
        combined = pd.concat(aligned_sheets, ignore_index=True)
    string_columns = combined.select_dtypes(include=["object"]).columns
    combined[string_columns] = combined[string_columns].apply(lambda series: series.apply(clean_display_text))
    combined.attrs["new_to_old_column"] = new_to_old
    combined.attrs["old_index_to_new_column"] = index_to_new
    return combined


def change_column_types(df, columns, to_type):
    """
    Change the data type of specified columns in a dataframe.
    
    Args:
        df (pandas.DataFrame): The dataframe to modify
        columns (list): List of column names to change
        to_type (str): Target data type - one of 'string', 'int', or 'float'
        
    Returns:
        pandas.DataFrame: DataFrame with modified column types
    """
    # Create a copy to avoid modifying the original unexpectedly
    df_copy = df.copy()
    
    # Map the requested type to pandas data type
    type_mapping = {
        'string': str,
        'int': 'int64',
        'float': 'float64'
    }
    
    # Check if the requested type is valid
    if to_type not in type_mapping:
        raise ValueError(f"to_type must be one of {list(type_mapping.keys())}")
    
    # Convert each column
    for col in columns:
        if col in df_copy.columns:
            try:
                df_copy[col] = df_copy[col].astype(type_mapping[to_type])
            except Exception as e:
                print(f"Could not convert column '{col}' to {to_type}: {e}")
        else:
            print(f"Column '{col}' not found in dataframe")
    
    return df_copy

def remove_zero_values(df, columns):
    """
    Remove 0 values for unnecessary columns.

    Args:
        df (pandas.DataFrame): The dataframe to modify
        columns (list): List of column indices to change

    Returns:
        pandas.DataFrame: Dataframe with cleaned columns
    """

    # Create a copy to avoid modifying the original unexpectedly
    df_copy = df.copy()

    # Modify columns
    for idx in columns:
        col = df_copy.columns[idx]

        df_copy[col] = df_copy[col].replace(0, np.nan)

    return df_copy

def calculate_fuel_costs(df, columns):
    """
    Calculate fuel costs per kg of fuel.

    Args:
        df (pandas.DataFrame): The dataframe to modify
        columns (list): List of price column names to calculate from

    Returns:
        pandas.DataFrame: Dataframe with cleaned columns
    """

    # Create a copy to avoid modifying the original unexpectedly
    df_copy = df.copy()

    for col in columns:
        col2_idx = df_copy.columns.get_loc(col)
        col2 = df_copy.columns[col2_idx - 1]

        new_col_name = '_'.join([col, 'per_kg'])

        try:
            price = pd.to_numeric(df_copy[col], errors="coerce")
            quantity = pd.to_numeric(df_copy[col2], errors="coerce")
            unit_cost = price.div(quantity.where(quantity > 0)).replace([np.inf, -np.inf], np.nan)
            if "lpg" in col.lower():
                unit_cost = unit_cost.where(unit_cost.between(1000, 100000))
            df_copy[new_col_name] = unit_cost
        except (TypeError, ValueError, ZeroDivisionError):
            df_copy[new_col_name] = np.nan

    return df_copy


def clean_display_text(value):
    translated = translate_display_text(value)
    return np.nan if pd.isna(translated) else translated


def bus_question_label(column):
    _, _, new_to_old, _ = load_bus_column_changes()
    text = new_to_old.get(str(column), str(column))
    text = str(text).split("/")[-1].strip()
    return translate_label_text(text, max_length=96)


def bus_section_columns(data, prefix, focus_terms=None, limit=5):
    focus_terms = [term.lower() for term in (focus_terms or [])]
    mapping, _, _, _ = load_bus_column_changes()
    columns = []
    for row in mapping.itertuples(index=False):
        old_name = str(row.old)
        new_name = str(row.new)
        if new_name not in data.columns:
            continue
        if (
            old_name.startswith(prefix + " /")
            and old_name.count("/") == 1
            and not old_name.lower().endswith("_url")
        ):
            columns.append(new_name)
    if focus_terms:
        focused = [
            col for col in columns
            if any(term in str(col).lower() or term in str(data.attrs.get("new_to_old_column", {}).get(col, "")).lower() for term in focus_terms)
        ]
        columns = focused or columns
    scored = []
    for col in columns:
        valid = data[col].dropna().shape[0]
        unique = data[col].dropna().astype(str).nunique()
        if valid and unique > 0:
            scored.append((col, valid, unique))
    scored = sorted(scored, key=lambda item: (-item[1], item[2], len(str(item[0]))))
    return [col for col, _, _ in scored[:limit]]


def bus_section_summary(data, title, prefix, focus_terms=None):
    insights = build_bus_section_highlights(data, title)
    if not insights:
        insights = ["No major finding is available for the current filter selection."]
    render_summary_panel(f"Summary - {title}", insights)


def bus_response_series(data, column):
    if column not in data.columns:
        return pd.Series(dtype=object)
    series = data[column].dropna().apply(translate_display_text)
    series = series.dropna().astype(str).str.strip()
    return series[series.ne("") & series.str.lower().ne("nan")]


def bus_share_highlight(data, column, categories, message):
    series = bus_response_series(data, column)
    if series.empty:
        return None
    category_keys = {str(value).strip().casefold() for value in categories}
    count = int(series.str.casefold().isin(category_keys).sum())
    if not count:
        return None
    percentage = count / len(series) * 100
    return message.format(count=count, percentage=percentage, total=len(series))


def bus_section_a_highlights(data):
    return [
        bus_share_highlight(
            data, "c2", ["Cleaner", "Much Cleaner"],
            "Kitchen cleanliness improved for {percentage:.1f}% of respondents ({count:,} people) after adopting biogas.",
        ),
        bus_share_highlight(
            data, "c22", ["Somewhat Improved", "Much Better"],
            "Household health was reported to have improved by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "c27", ["Somewhat Improved", "Much Better"],
            "Livestock-shed cleanliness improved for {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "c16", ["Never"],
            "Fire-related household accidents after biogas adoption were absent for {percentage:.1f}% of respondents ({count:,} people).",
        ),
    ]


def bus_section_b_highlights(data):
    return [
        bus_share_highlight(
            data, "d1a", ["Yes"],
            "Household income increased after biogas adoption for {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "d8", ["Yes"],
            "More free time was reported by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "d28", ["Better", "Much Better"],
            "Family social and economic conditions improved for {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "d29", ["Better", "Much Better"],
            "Cooking processes and workloads improved for {percentage:.1f}% of respondents ({count:,} people).",
        ),
    ]


def bus_section_c_highlights(data):
    return [
        bus_share_highlight(
            data, "a9_operable_biogas", ["Yes", "Functioning Well", "1"],
            "Biogas systems remained operational for {percentage:.1f}% of respondents ({count:,} systems).",
        ),
        bus_share_highlight(
            data, "a14_clear_instructions",
            ["Yes, Clear Enough and Easy to Follow", "Yes, Very Clear and Easy to Follow"],
            "Clear and easy-to-follow operating instructions were received by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "a26_gas_leak_knowledge", ["Know"],
            "Correct gas-leak checking procedures were understood by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "a33", ["Know"],
            "The requirement to close the gas tap when it is not in use was understood by {percentage:.1f}% of respondents ({count:,} people).",
        ),
    ]


def bus_section_d_highlights(data):
    return [
        bus_share_highlight(
            data, "g2", ["Satisfied", "Very Satisfied"],
            "Overall satisfaction with biogas reached {percentage:.1f}% ({count:,} respondents were satisfied or very satisfied).",
        ),
        bus_share_highlight(
            data, "g4", ["Satisfied", "Very Satisfied"],
            "Satisfaction with system installation reached {percentage:.1f}% ({count:,} respondents).",
        ),
        bus_share_highlight(
            data, "g5", ["Satisfied", "Very Satisfied"],
            "Satisfaction with household energy-cost reductions reached {percentage:.1f}% ({count:,} respondents).",
        ),
        bus_share_highlight(
            data, "g13", ["Yes, Always"],
            "Service providers consistently listened to user feedback according to {percentage:.1f}% of respondents ({count:,} people).",
        ),
    ]


def bus_section_e_highlights(data):
    return [
        bus_share_highlight(
            data, "f1",
            ["Moderately Significant Daily Benefits", "Major Benefits For Daily Life", "Very Significant Benefits", "Transformative Daily Benefits"],
            "Meaningful daily benefits for women or children were reported by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "f2", ["Reduced", "Significantly Reduced"],
            "Women's household workload decreased for {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "f3", ["Adult Female Family Member"],
            "Women were identified as the primary managers of savings or additional income by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "f4", ["Agree", "Strongly Agree"],
            "Biogas was perceived to strengthen women's empowerment by {percentage:.1f}% of respondents ({count:,} people).",
        ),
    ]


def bus_section_f_highlights(data):
    return [
        bus_share_highlight(
            data, "e13", ["Yes"],
            "Bio-slurry was actively used by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "e15", ["Yes"],
            "Training on bio-slurry utilization had reached {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "e16", ["Know"],
            "The benefits of bio-slurry were understood by {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "e31", ["Moderately Improved", "Significantly Improved"],
            "Among respondents assessing soil outcomes, {percentage:.1f}% reported improved soil quality ({count:,} people).",
        ),
    ]


def bus_section_g_highlights(data):
    return [
        bus_share_highlight(
            data, "b9", ["Yes"],
            "Biogas helped reduce tree cutting for fuel according to {percentage:.1f}% of respondents ({count:,} people).",
        ),
        bus_share_highlight(
            data, "B1_biogas_use", ["Full Use (100%)"],
            "Among households with a recorded utilization level, biogas fully met cooking-energy needs for {percentage:.1f}% ({count:,} households).",
        ),
        bus_share_highlight(
            data, "b8", ["1-3 Hours", "3-5 Hours", "More Than 5 Hours"],
            "Daily biogas-stove use reached at least one hour for {percentage:.1f}% of respondents ({count:,} households).",
        ),
        bus_share_highlight(
            data, "b7", ["30-50 Kg", "50-65 Kg", "65-80 Kg", "80-100 Kg", ">100 Kg"],
            "At least 30 kg of manure was fed into biogas systems each day by {percentage:.1f}% of respondents ({count:,} households).",
        ),
    ]


BUS_SECTION_HIGHLIGHT_BUILDERS = {
    "Section A": bus_section_a_highlights,
    "Section B": bus_section_b_highlights,
    "Section C": bus_section_c_highlights,
    "Section D": bus_section_d_highlights,
    "Section E": bus_section_e_highlights,
    "Section F": bus_section_f_highlights,
    "Section G": bus_section_g_highlights,
}


def build_bus_section_highlights(data, title):
    builder = BUS_SECTION_HIGHLIGHT_BUILDERS.get(title)
    return [insight for insight in (builder(data) if builder else []) if insight]


def clean_plotly_title(title):
    title = "" if title is None else str(title)
    title = re.sub(r"<br\s*/?>", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"<[^>]+>", "", title)
    return re.sub(r"\s+", " ", title).strip() or "Untitled chart"


def plotly_sequence_has_values(values):
    if values is None:
        return False
    try:
        values = list(values)
    except TypeError:
        values = [values]
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        if str(value).strip() != "":
            return True
    return False


def plotly_figure_has_data(fig):
    meta = getattr(getattr(fig, "layout", None), "meta", None)
    if isinstance(meta, dict) and meta.get("empty_chart"):
        return False
    traces = list(getattr(fig, "data", []) or [])
    if not traces:
        return False
    for trace in traces:
        for attr in ("x", "y", "labels", "values", "lat", "lon", "z", "r", "theta"):
            if plotly_sequence_has_values(getattr(trace, attr, None)):
                return True
    return False


def register_hidden_empty_chart(fig):
    title = clean_plotly_title(getattr(getattr(fig, "layout", None), "title", None).text)
    hidden = st.session_state.setdefault("BUS_hidden_empty_charts", [])
    if title not in hidden:
        hidden.append(title)


def install_empty_chart_filter():
    if not hasattr(st, "_bus_original_plotly_chart"):
        st._bus_original_plotly_chart = st.plotly_chart

    def filtered_plotly_chart(fig_or_data, *args, **kwargs):
        if hasattr(fig_or_data, "data") and not plotly_figure_has_data(fig_or_data):
            register_hidden_empty_chart(fig_or_data)
            return None
        return st._bus_original_plotly_chart(fig_or_data, *args, **kwargs)

    st.plotly_chart = filtered_plotly_chart


def create_kitchen_adaptation_comparison(data, outcome_column, title):
    required_columns = ["c1", outcome_column]
    if any(column not in data.columns for column in required_columns):
        return go.Figure().update_layout(meta={"empty_chart": True})

    comparison = data[required_columns].dropna().copy()
    comparison.columns = ["Kitchen Adaptation", "Outcome"]
    comparison["Kitchen Adaptation"] = comparison["Kitchen Adaptation"].apply(clean_display_text)
    comparison["Outcome"] = comparison["Outcome"].apply(clean_display_text)
    comparison = comparison.dropna()
    if comparison.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})

    grouped = (
        comparison.groupby(["Kitchen Adaptation", "Outcome"], dropna=False)
        .size()
        .rename("Respondents")
        .reset_index()
    )
    group_totals = grouped.groupby("Kitchen Adaptation")["Respondents"].transform("sum")
    grouped["Percentage"] = grouped["Respondents"] / group_totals * 100
    sample_sizes = grouped.groupby("Kitchen Adaptation")["Respondents"].sum().to_dict()
    grouped["Kitchen Adaptation Group"] = grouped["Kitchen Adaptation"].map(
        lambda value: f"{value} (N={int(sample_sizes[value])})"
    )

    fig = px.bar(
        grouped,
        x="Percentage",
        y="Kitchen Adaptation Group",
        color="Outcome",
        orientation="h",
        barmode="stack",
        text="Percentage",
        color_discrete_sequence=PLOTLY_COLORWAY,
        custom_data=["Respondents"],
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="inside",
        insidetextanchor="middle",
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.1f}% (%{customdata[0]} respondents)<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white",
        title={"text": title, "x": 0.02, "xanchor": "left"},
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        height=440,
        margin=dict(l=40, r=30, t=90, b=70),
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        xaxis=dict(title="Share Within Each Kitchen Adaptation Group", range=[0, 100], ticksuffix="%"),
        yaxis=dict(title="New or Renovated Kitchen for Biogas Cooking"),
        legend=dict(title="Reported Outcome", orientation="h", y=-0.22, x=0.5, xanchor="center"),
        hoverlabel=dict(bgcolor=DEEP_BLUE, bordercolor=DEEP_BLUE, font=dict(color="#FFFFFF")),
    )
    return fig


def kitchen_adaptation_outcome_share(data, outcome_column, positive_outcomes):
    if "c1" not in data.columns or outcome_column not in data.columns:
        return {}
    comparison = data[["c1", outcome_column]].dropna().copy()
    comparison.columns = ["Kitchen Adaptation", "Outcome"]
    comparison["Kitchen Adaptation"] = comparison["Kitchen Adaptation"].apply(clean_display_text)
    comparison["Outcome"] = comparison["Outcome"].apply(clean_display_text)
    comparison = comparison.dropna()
    positive_keys = {str(value).casefold() for value in positive_outcomes}
    comparison["Positive Outcome"] = comparison["Outcome"].astype(str).str.casefold().isin(positive_keys)
    return comparison.groupby("Kitchen Adaptation")["Positive Outcome"].mean().mul(100).to_dict()


SATISFACTION_DIMENSIONS = {
    "Technical Performance": ["a9_operable_biogas", "g3", "g4"],
    "Economic Impact": ["g5", "d25", "d1a"],
    "Health & Sanitation": ["c2", "c3", "c22", "c26"],
    "Operations & Maintenance": [
        "a18_maintenance_frequency",
        "a21_manometer_reading_frequency",
        "a23_stove_cleaning_frequency",
        "a29_overflow_frequency",
        "a36",
    ],
    "Agricultural Impact": ["e13", "e16", "e31"],
    "Service Quality (CPO)": ["g7"],
    "Social & Gender Impact": ["f1", "f2", "f4", "d8"],
}

SATISFACTION_ORDER = [
    "Very Satisfied",
    "Satisfied",
    "Moderately Satisfied",
    "Dissatisfied",
    "Very Dissatisfied",
]

SATISFACTION_SCORE_MAP = {
    "very satisfied": 100,
    "sangat puas": 100,
    "satisfied": 75,
    "puas": 75,
    "moderately satisfied": 50,
    "cukup puas": 50,
    "dissatisfied": 25,
    "tidak puas": 25,
    "very dissatisfied": 0,
    "sangat tidak puas": 0,
    "much better": 100,
    "jauh lebih baik": 100,
    "much cleaner": 100,
    "jauh lebih bersih": 100,
    "strongly agree": 100,
    "sangat setuju": 100,
    "major benefits for daily life": 100,
    "very significant benefits": 100,
    "transformative daily benefits": 100,
    "manfaat sangat besar": 100,
    "significant/clear benefits that change daily life": 100,
    "manfaat besar/jelas/mengubah kehidupan sehari-hari": 100,
    "yes": 100,
    "ya": 100,
    "1": 100,
    "know": 100,
    "berfungsi dengan baik": 100,
    "always (daily)": 100,
    "selalu (setiap hari)": 100,
    "setiap hari": 100,
    "understand very well": 100,
    "sangat memahami": 100,
    "never": 100,
    "tidak pernah": 100,
    "better": 75,
    "lebih baik": 75,
    "cleaner": 75,
    "lebih bersih": 75,
    "somewhat improved": 75,
    "slightly improved": 75,
    "moderately improved": 75,
    "significantly improved": 100,
    "cukup membaik": 75,
    "sedikit meningkat": 75,
    "cukup meningkat": 75,
    "agree": 75,
    "setuju": 75,
    "memahami": 75,
    "often": 75,
    "often (weekly)": 75,
    "sering": 75,
    "setiap minggu": 75,
    "less often": 75,
    "lebih jarang": 75,
    "lebih jarang (lebih sering tidak terpapar asap)": 75,
    "reduced": 75,
    "significantly reduced": 100,
    "sangat berkurang": 100,
    "moderately significant daily benefits": 75,
    "manfaat sedang/cukup signifikan dalam kehidupan sehari-hari": 75,
    "no change": 50,
    "sama saja": 50,
    "neutral/do not know": 50,
    "netral/tidak tahu": 50,
    "uncertain": 50,
    "cukup memahami": 50,
    "fairly often (every 2 weeks)": 50,
    "cukup sering": 50,
    "cukup sering (2 minggu sekali)": 50,
    "minor/limited benefits": 25,
    "limited benefits": 25,
    "manfaat sangat kecil/terbatas": 25,
    "less improved": 25,
    "kurang membaik": 25,
    "less clean": 25,
    "kurang bersih": 25,
    "slightly decreased": 25,
    "sedikit menurun": 25,
    "disagree": 25,
    "tidak setuju": 25,
    "rarely": 25,
    "jarang": 25,
    "jarang sekali": 25,
    "setiap bulan": 25,
    "rarely (monthly or less)": 25,
    "jarang (setiap bulan atau lebih)": 25,
    "more often": 25,
    "lebih sering": 25,
    "increased": 25,
    "bertambah": 25,
    "do not know": 0,
    "tidak mengetahui": 0,
    "tidak tahu": 0,
    "do not understand": 0,
    "tidak memahami": 0,
    "kurang memahami": 25,
    "no": 0,
    "tidak": 0,
    "not functioning at all": 0,
    "tidak berfungsi sama sekali": 0,
    "worse": 25,
    "memburuk": 25,
    "much worse": 0,
    "jauh lebih buruk": 0,
    "very frequent": 0,
    "sangat sering": 0,
    "no benefits at all": 0,
    "tidak ada manfaat sama sekali": 0,
    "strongly disagree": 0,
    "sangat tidak setuju": 0,
    "strongly decreased": 0,
    "sangat menurun": 0,
    "sangat bertambah": 0,
}


def satisfaction_score_series(series):
    return series.map(lambda value: SATISFACTION_SCORE_MAP.get(str(value).strip().lower(), np.nan))


def score_satisfaction_dimensions(data):
    if data.empty:
        return pd.DataFrame()

    working = data.copy()
    if "g2" in working.columns:
        working["_satisfaction_level"] = working["g2"].apply(clean_display_text)

    for dimension, columns in SATISFACTION_DIMENSIONS.items():
        available_columns = [col for col in columns if col in working.columns]
        if not available_columns:
            continue
        scored = pd.concat(
            [satisfaction_score_series(working[col]) for col in available_columns],
            axis=1,
        )
        working[dimension] = scored.mean(axis=1, skipna=True)
    return working


def build_satisfaction_profile(data):
    scored = score_satisfaction_dimensions(data)
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in scored.columns]
    if scored.empty or not dimensions:
        return pd.DataFrame()
    row = {"Profile": "All BUS Respondents", "Sample": int(len(scored))}
    for dimension in dimensions:
        row[dimension] = scored[dimension].mean(skipna=True)
    return pd.DataFrame([row])


def style_satisfaction_polar_layout(fig, title, height=680, legend_y=-0.08):
    fig.update_layout(
        template="plotly_white",
        title={"text": title, "x": 0.02, "xanchor": "left"},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        height=height,
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        margin=dict(l=80, r=80, t=120, b=120),
        polar=dict(
            bgcolor="#F8FBFF",
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[0, 25, 50, 75, 100],
                ticktext=["0", "25", "50", "75", "100"],
                tickfont=dict(color=MUTED, size=11),
                gridcolor="rgba(24, 79, 143, 0.14)",
                linecolor="rgba(20, 36, 58, 0.16)",
            ),
            angularaxis=dict(
                tickfont=dict(color=DEEP_BLUE, size=12),
                gridcolor="rgba(24, 79, 143, 0.14)",
                linecolor="rgba(20, 36, 58, 0.16)",
            ),
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=legend_y,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0)",
            font=dict(size=11, color=INK),
        ),
        hoverlabel=dict(
            bgcolor=DEEP_BLUE,
            bordercolor=DEEP_BLUE,
            font=dict(color="#FFFFFF", family='Inter, "Segoe UI", Arial, sans-serif'),
        ),
        annotations=[
            dict(
                text="Matrix score: 0 = lowest outcome, 50 = neutral, 100 = highest outcome",
                x=0.5,
                y=1.08,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=12, color=MUTED),
            )
        ],
    )
    return fig


def create_satisfaction_spider_plot(data, title):
    profile = build_satisfaction_profile(data)
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in profile.columns]
    if profile.empty or not dimensions:
        fig = go.Figure()
        fig.add_annotation(
            text="There is not enough valid satisfaction data to generate this profile.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=14, color=MUTED),
        )
        fig.update_layout(meta={"empty_chart": True, "empty_reason": "No valid satisfaction data."})
        return fig

    row = profile.iloc[0]
    theta = dimensions + [dimensions[0]]
    values = [row[dimension] for dimension in dimensions]
    values = values + [values[0]]
    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=[50] * len(theta),
            theta=theta,
            mode="lines",
            name="Neutral benchmark (50)",
            line=dict(color="#94A3B8", width=2, dash="dot"),
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=values,
            theta=theta,
            mode="lines+markers",
            fill="toself",
            fillcolor="rgba(28, 142, 93, 0.14)",
            name=f"All respondents (N={row['Sample']})",
            line=dict(color="#1C8E5D", width=4),
            marker=dict(color="#1C8E5D", size=8),
            hovertemplate="<b>%{theta}</b><br>Matrix score: %{r:.1f}/100<extra></extra>",
        )
    )
    return style_satisfaction_polar_layout(fig, title)


def build_provincial_satisfaction_profile(data, satisfaction_levels):
    scored = score_satisfaction_dimensions(data)
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in scored.columns]
    if scored.empty or not dimensions or "province" not in scored.columns or "_satisfaction_level" not in scored.columns:
        return pd.DataFrame()

    subset = scored[scored["_satisfaction_level"].isin(satisfaction_levels)].copy()
    rows = []
    for province, province_data in subset.groupby("province", dropna=True):
        row = {"Province": province, "Sample": int(len(province_data))}
        for dimension in dimensions:
            row[dimension] = province_data[dimension].mean(skipna=True)
        rows.append(row)
    return pd.DataFrame(rows)


def create_provincial_satisfaction_spider(profile, title, province_order):
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in profile.columns]
    theta = dimensions + [dimensions[0]]
    color_map = {
        province: PLOTLY_COLORWAY[idx % len(PLOTLY_COLORWAY)]
        for idx, province in enumerate(province_order)
    }
    fig = go.Figure()

    fig.add_trace(
        go.Scatterpolar(
            r=[50] * len(theta),
            theta=theta,
            mode="lines",
            name="Neutral benchmark (50)",
            line=dict(color="#94A3B8", width=1.5, dash="dot"),
            hoverinfo="skip",
        )
    )

    for _, row in profile.sort_values("Province").iterrows():
        province = row["Province"]
        sample = int(row["Sample"])
        color = color_map.get(province, PLOTLY_COLORWAY[0])
        values = [row[dimension] for dimension in dimensions]
        values = values + [values[0]]
        small_sample = sample < 5
        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=theta,
                mode="lines+markers",
                fill="toself",
                fillcolor=f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.04)",
                opacity=0.55 if small_sample else 0.9,
                name=f"{province} (N={sample}{'*' if small_sample else ''})",
                line=dict(color=color, width=2.5, dash="dot" if small_sample else "solid"),
                marker=dict(color=color, size=5),
                hovertemplate=f"<b>{province} (N={sample})</b><br>%{{theta}}: %{{r:.1f}}/100<extra></extra>",
            )
        )
    return style_satisfaction_polar_layout(fig, title, height=760, legend_y=-0.12)


def render_provincial_satisfaction_spider(data, satisfaction_levels, title, key, province_order):
    profile = build_provincial_satisfaction_profile(data, satisfaction_levels)
    if profile.empty:
        st.info(f"No respondents are available for {title.lower()} under the current filters.")
        return
    st.plotly_chart(
        create_provincial_satisfaction_spider(profile, title, province_order),
        use_container_width=True,
        key=key,
    )
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in profile.columns]
    weighted_scores = {}
    for dimension in dimensions:
        valid = profile[[dimension, "Sample"]].dropna()
        if not valid.empty:
            weighted_scores[dimension] = np.average(valid[dimension], weights=valid["Sample"])
    if weighted_scores:
        strongest = max(weighted_scores, key=weighted_scores.get)
        priority = min(weighted_scores, key=weighted_scores.get)
        st.markdown(
            f"**Key reading:** Across {int(profile['Sample'].sum()):,} respondents in this group, "
            f"**{strongest}** records the highest matrix score ({weighted_scores[strongest]:.1f}), "
            f"while **{priority}** records the lowest ({weighted_scores[priority]:.1f})."
        )
    if (profile["Sample"] < 5).any():
        st.caption("* Fewer than five respondents; interpret the provincial pattern cautiously.")


def render_satisfaction_spider(data, title, key):
    profile = build_satisfaction_profile(data)
    st.plotly_chart(create_satisfaction_spider_plot(data, title), use_container_width=True, key=key)
    dimensions = [dimension for dimension in SATISFACTION_DIMENSIONS if dimension in profile.columns]
    if profile.empty or not dimensions:
        return
    scores = profile.iloc[0][dimensions].dropna()
    if scores.empty:
        return
    metrics = st.columns(3)
    metrics[0].metric("Average Composite Score", f"{scores.mean():.1f} / 100")
    metrics[1].metric("Strongest Outcome Dimension", str(scores.idxmax()), f"{scores.max():.1f} / 100")
    metrics[2].metric("Priority Outcome Dimension", str(scores.idxmin()), f"{scores.min():.1f} / 100")
    st.caption(
        "This is a composite outcome index, not a raw satisfaction percentage. Scores are respondent-level "
        "averages derived from the 0, 25, 50, 75, and 100 response matrix across selected BUS indicators."
    )


def coerce_numeric_for_bins(series):
    cleaned = series.replace(
        {
            "No Change": 0,
            "no change": 0,
            "Tidak Ada Perubahan": 0,
            "tidak ada perubahan": 0,
            "Sama Saja": 0,
            "sama saja": 0,
        }
    )
    return pd.to_numeric(cleaned, errors="coerce")


def create_binned_count_chart(data, column, bins, labels, title, x_label, y_label="Respondents", height=540):
    if column not in data.columns:
        fig = go.Figure()
        fig.update_layout(meta={"empty_chart": True, "empty_reason": f"Column {column} is not available."})
        return fig

    values = coerce_numeric_for_bins(data[column]).dropna()
    if values.empty:
        fig = go.Figure()
        fig.update_layout(meta={"empty_chart": True, "empty_reason": f"No numeric data for {column}."})
        return fig

    grouped = pd.cut(values, bins=bins, labels=labels, include_lowest=True, right=True)
    counts = grouped.value_counts(sort=False).reindex(labels, fill_value=0).reset_index()
    counts.columns = [x_label, y_label]

    fig = px.bar(
        counts,
        x=x_label,
        y=y_label,
        title=title,
        text=y_label,
        height=height,
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=42, t=128, b=96),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    fig.update_yaxes(showgrid=True, gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    return fig


def create_hour_group_chart(data, column, title):
    normalized_data = data.copy()
    if column in normalized_data.columns:
        values = pd.to_numeric(normalized_data[column], errors="coerce")
        normalized_data[column] = values.where(values <= 24, values / 60)
    return create_binned_count_chart(
        normalized_data,
        column,
        bins=[-0.001, 0, 1, 3, 5, 8, np.inf],
        labels=["0 hours", ">0-1", ">1-3", ">3-5", ">5-8", ">8 hours"],
        title=title,
        x_label="Reported hours",
    )


def create_currency_group_chart(data, column, title):
    return create_binned_count_chart(
        data,
        column,
        bins=[-0.001, 0, 100000, 250000, 500000, 1000000, np.inf],
        labels=["No change", ">0-100k", ">100k-250k", ">250k-500k", ">500k-1M", ">1M"],
        title=title,
        x_label="Reported change (Rp)",
    )


def create_average_comparison_chart(data, columns_before, columns_after, group_labels, title, y_label="Average minutes per day"):
    rows = []
    for label, before_col, after_col in zip(group_labels, columns_before, columns_after):
        before_values = coerce_numeric_for_bins(data[before_col]) if before_col in data.columns else pd.Series(dtype=float)
        after_values = coerce_numeric_for_bins(data[after_col]) if after_col in data.columns else pd.Series(dtype=float)
        rows.append({"Group": label, "Period": "Before Using Biogas", y_label: before_values.mean(skipna=True)})
        rows.append({"Group": label, "Period": "After Using Biogas", y_label: after_values.mean(skipna=True)})

    chart_data = pd.DataFrame(rows).dropna(subset=[y_label])
    if chart_data.empty:
        fig = go.Figure()
        fig.update_layout(meta={"empty_chart": True, "empty_reason": "No numeric data available."})
        return fig

    fig = px.bar(
        chart_data,
        x="Group",
        y=y_label,
        color="Period",
        barmode="group",
        title=title,
        text=y_label,
        height=560,
        color_discrete_sequence=PLOTLY_COLORWAY,
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=42, t=128, b=96),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    fig.update_yaxes(showgrid=True, gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    return fig


def paired_time_change_insights(data, columns_before, columns_after, group_labels):
    insights = []
    for label, before_col, after_col in zip(group_labels, columns_before, columns_after):
        if before_col not in data.columns or after_col not in data.columns:
            continue
        paired = pd.DataFrame(
            {
                "before": pd.to_numeric(data[before_col], errors="coerce"),
                "after": pd.to_numeric(data[after_col], errors="coerce"),
            }
        ).dropna()
        if paired.empty:
            continue
        before_mean = paired["before"].mean()
        after_mean = paired["after"].mean()
        reduction = before_mean - after_mean
        reduction_pct = reduction / before_mean * 100 if before_mean > 0 else np.nan
        percentage_text = f" ({reduction_pct:.1f}%)" if pd.notna(reduction_pct) else ""
        insights.append(
            f"{label}: average fuel-collection time changed from {before_mean:.1f} to {after_mean:.1f} minutes per day, "
            f"a reduction of {reduction:.1f} minutes{percentage_text}."
        )
    return insights


def create_activity_gender_average_chart(data, activity_columns, title):
    rows = []
    for activity, group_columns in activity_columns.items():
        for group, column in group_columns.items():
            if column not in data.columns:
                continue
            values = pd.to_numeric(data[column], errors="coerce")
            rows.append(
                {
                    "Activity": activity,
                    "Household Group": group,
                    "Average Minutes per Day": values.mean(skipna=True),
                    "Active Participants": int(values.gt(0).sum()),
                }
            )
    chart_data = pd.DataFrame(rows).dropna(subset=["Average Minutes per Day"])
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})

    fig = px.bar(
        chart_data,
        x="Activity",
        y="Average Minutes per Day",
        color="Household Group",
        barmode="group",
        text="Average Minutes per Day",
        custom_data=["Active Participants"],
        title=title,
        color_discrete_sequence=PLOTLY_COLORWAY,
        height=570,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}: %{y:.1f} minutes/day<br>Active participants: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=42, t=118, b=100),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    fig.update_yaxes(showgrid=True, gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False)
    return fig


def create_ordered_category_chart(data, column, order, title, x_label="Respondents"):
    if column not in data.columns:
        return go.Figure().update_layout(meta={"empty_chart": True})
    series = data[column].dropna().apply(clean_display_text).dropna().astype(str)
    counts = series.value_counts().reindex(order, fill_value=0).reset_index()
    counts.columns = ["Category", "Respondents"]
    counts = counts[counts["Respondents"] > 0]
    if counts.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        counts,
        x="Respondents",
        y="Category",
        orientation="h",
        text="Respondents",
        title=f"{title} (N={len(series):,})",
        color_discrete_sequence=[DEEP_BLUE],
        height=max(500, 48 * len(counts) + 180),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=80, r=50, t=100, b=70),
        yaxis=dict(categoryorder="array", categoryarray=list(reversed(order)), title="Category"),
        xaxis=dict(title=x_label, showgrid=True, gridcolor="rgba(24, 79, 143, 0.08)"),
    )
    return fig


def create_section_c_knowledge_practice_chart(data):
    indicators = [
        ("Read manometer", "a20_manometer_reading_knowledge", "a21_manometer_reading_frequency", "frequency"),
        ("Clean stove components", "a22_stove_cleaning_knowledge", "a23_stove_cleaning_frequency", "frequency"),
        ("Light stove correctly", "a24_proper_stove_activation_knowledge", "a25_proper_stove_activation_frequency", "frequency"),
        ("Check for gas leaks", "a26_gas_leak_knowledge", "a27_gas_leak_frequency", "frequency"),
        ("Clean overflow and outlet", "a28_overflow_knowledge", "a29_overflow_frequency", "frequency"),
        ("Drain the water trap", "a30", "a31", "frequency"),
        ("Close concrete outlet", "a32", "a32a", "yes_no"),
        ("Close gas tap", "a33", "a34", "gas_tap"),
    ]
    rows = []
    for label, knowledge_col, practice_col, practice_type in indicators:
        if knowledge_col not in data.columns or practice_col not in data.columns:
            continue
        knowledge = bus_response_series(data, knowledge_col)
        practice = bus_response_series(data, practice_col)
        knowledge_positive = knowledge.str.casefold().eq("know")
        if practice_type == "frequency":
            practice_positive = ~practice.str.casefold().isin({"never", "not at all"})
        elif practice_type == "yes_no":
            practice_positive = practice.str.casefold().isin({"yes", "yes, always"})
        else:
            practice_positive = practice.str.casefold().isin({"yes", "yes, always", "yes, sometimes", "sometimes"})
        if not knowledge.empty:
            rows.append({"Indicator": label, "Measure": "Knows procedure", "Percentage": knowledge_positive.mean() * 100, "Valid responses": len(knowledge)})
        if not practice.empty:
            rows.append({"Indicator": label, "Measure": "Reports performing practice", "Percentage": practice_positive.mean() * 100, "Valid responses": len(practice)})

    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data,
        x="Percentage",
        y="Indicator",
        color="Measure",
        barmode="group",
        orientation="h",
        text="Percentage",
        custom_data=["Valid responses"],
        title="Knowledge and Reported Operation and Maintenance Practices",
        color_discrete_sequence=[DEEP_BLUE, "#3AA76D"],
        height=650,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        hovertemplate="%{y}<br>%{fullData.name}: %{x:.1f}%<br>Valid responses: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=90, r=70, t=120, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Share of valid responses", range=[0, 108], ticksuffix="%"),
        yaxis=dict(title="O&M indicator", categoryorder="array", categoryarray=list(reversed(chart_data["Indicator"].drop_duplicates().tolist()))),
    )
    return fig


def create_recommendation_score_chart(data):
    column = "a41"
    if column not in data.columns:
        return go.Figure().update_layout(meta={"empty_chart": True})
    scores = pd.to_numeric(data[column], errors="coerce").dropna()
    scores = scores[scores.between(1, 10)]
    if scores.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    counts = scores.value_counts().reindex(range(1, 11), fill_value=0).rename_axis("Recommendation score").reset_index(name="Respondents")
    mean_score = scores.mean()
    fig = px.bar(
        counts,
        x="Recommendation score",
        y="Respondents",
        text="Respondents",
        title=f"Likelihood of Recommending Biogas (Mean score: {mean_score:.1f}/10, N={len(scores):,})",
        color_discrete_sequence=[DEEP_BLUE],
        height=540,
    )
    fig.update_traces(textposition="outside")
    fig.add_vline(x=mean_score, line_color="#E09F3E", line_width=2, line_dash="dash")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=42, t=120, b=80),
        xaxis=dict(dtick=1, range=[0.5, 10.5]),
    )
    return fig


def create_satisfaction_likert_chart(data):
    indicators = [
        ("Overall biogas satisfaction", "g2"),
        ("Construction and equipment quality", "g3"),
        ("Digester installation", "g4"),
        ("Reduced household energy costs", "g5"),
        ("CPO service", "g7"),
    ]
    levels = ["Very Dissatisfied", "Dissatisfied", "Moderately Satisfied", "Satisfied", "Very Satisfied"]
    colors = ["#B42318", "#E76F51", "#A7B0BE", "#3887C4", "#1F9D5A"]
    rows = []
    for label, column in indicators:
        series = bus_response_series(data, column)
        if series.empty:
            continue
        counts = series.value_counts()
        for level in levels:
            count = int(counts.get(level, 0))
            rows.append(
                {
                    "Indicator": f"{label} (N={len(series):,})",
                    "Response": level,
                    "Respondents": count,
                    "Percentage": count / len(series) * 100,
                }
            )
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})

    fig = go.Figure()
    indicator_order = chart_data["Indicator"].drop_duplicates().tolist()
    for level, color in zip(levels, colors):
        subset = chart_data[chart_data["Response"].eq(level)].set_index("Indicator").reindex(indicator_order).reset_index()
        fig.add_trace(
            go.Bar(
                y=subset["Indicator"],
                x=subset["Percentage"],
                name=level,
                orientation="h",
                marker_color=color,
                customdata=subset[["Respondents"]],
                text=[f"{value:.1f}%" if value >= 4 else "" for value in subset["Percentage"]],
                textposition="inside",
                hovertemplate="%{y}<br>%{fullData.name}: %{x:.1f}% (%{customdata[0]} respondents)<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        title="Satisfaction Across Core Service and System Dimensions",
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        height=610,
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title_font=dict(size=17, color=DEEP_BLUE),
        title_x=0.02,
        margin=dict(l=90, r=45, t=125, b=90),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Share of valid responses", range=[0, 100], ticksuffix="%"),
        yaxis=dict(title="Satisfaction dimension", categoryorder="array", categoryarray=list(reversed(indicator_order))),
    )
    return fig


def create_gender_decision_participation_chart(data):
    decisions = [
        ("Proposed installation", {
            "Adult Male": ["a5_biogas_installation_proposer_adult_male"],
            "Adult Female": ["a5_biogas_installation_proposer_adult_female"],
            "CPO / Cooperative": ["a5_biogas_installation_proposer_cooperative"],
            "Other": ["a5_biogas_installation_proposer_others"],
        }),
        ("Agreed to installation", {
            "Adult Male": ["a6_agreed_to_installation_adult_male"],
            "Adult Female": ["a6_agreed_to_installation_adult_female"],
            "Other": ["a6_agreed_to_installation_others1"],
        }),
        ("Selected digester location", {
            "Adult Male": ["a7_installation_location_adult_male"],
            "Adult Female": ["a7_installation_location_adult_female"],
            "CPO / Cooperative": ["a7_installation_location_CPO"],
            "Other": ["a7_installation_location_others1"],
        }),
        ("Supervised installation", {
            "Adult Male": ["a8_installation_supervisor_adult_male"],
            "Adult Female": ["a8_installation_supervisor_adult_female"],
            "CPO / Cooperative": ["a8_installation_supervisor_CPO"],
            "Other": ["a8_installation_supervisor_others1"],
        }),
    ]
    rows = []
    for decision, groups in decisions:
        available = [column for columns in groups.values() for column in columns if column in data.columns]
        if not available:
            continue
        denominator = int(data[available].notna().any(axis=1).sum())
        if not denominator:
            continue
        for group, columns in groups.items():
            valid_columns = [column for column in columns if column in data.columns]
            if not valid_columns:
                continue
            selected_mask = pd.Series(False, index=data.index)
            generator = ChartGenerator(data)
            for column in valid_columns:
                selected_mask |= generator._coerce_numeric_series(data[column]).fillna(0).gt(0)
            selected = int(selected_mask.sum())
            rows.append({
                "Decision": decision,
                "Participant": group,
                "Percentage": selected / denominator * 100,
                "Respondents": selected,
                "Valid responses": denominator,
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data,
        x="Decision",
        y="Percentage",
        color="Participant",
        barmode="group",
        text="Percentage",
        custom_data=["Respondents", "Valid responses"],
        title="Participation in Biogas Installation Decisions",
        color_discrete_sequence=[DEEP_BLUE, "#3AA76D", "#E09F3E", "#7A6BB7"],
        height=600,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}: %{y:.1f}% (%{customdata[0]} of %{customdata[1]})<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=45, t=125, b=105),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Decision stage"),
        yaxis=dict(title="Share of valid responses", range=[0, 110], ticksuffix="%"),
    )
    return fig


def create_gender_task_time_chart(data):
    activities = {
        "Cooking": {
            "Adult Female": "d26_cooking_time_adult_female",
            "Adult Male": "d26_cooking_time_adult_male",
            "Children / Others": "d26_cooking_time_children",
        },
        "Collecting manure": {
            "Adult Female": "d5_manure_collection_adult_female",
            "Adult Male": "d5_manure_collection_adult_male",
            "Children / Others": "d5_manure_collection_others",
        },
        "Mixing manure and water": {
            "Adult Female": "d6_manure_mixing_adult_female",
            "Adult Male": "d6_manure_mixing_adult_male",
            "Children / Others": "d6_manure_mixing_others",
        },
        "Stirring manure mixture": {
            "Adult Female": "d7_manure_blending_adult_female",
            "Adult Male": "d7_manure_blending_adult_male",
            "Children / Others": "d7_manure_blending_others",
        },
        "Operating and maintaining biogas": {
            "Adult Female": "d27_operating_time_adult_female",
            "Adult Male": "d27_operating_time_adult_male",
            "Children / Others": "d27_operating_time_children",
        },
    }
    rows = []
    for activity, groups in activities.items():
        for group, column in groups.items():
            if column not in data.columns:
                continue
            values = pd.to_numeric(data[column], errors="coerce")
            values = values[values.between(0, 1440)]
            active = values[values.gt(0)]
            if values.empty:
                continue
            rows.append({
                "Activity": activity,
                "Household Group": group,
                "Median Minutes": active.median() if not active.empty else 0,
                "Active Households": int(active.shape[0]),
                "Participation Rate": active.shape[0] / values.shape[0] * 100,
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data,
        x="Activity",
        y="Median Minutes",
        color="Household Group",
        barmode="group",
        text="Median Minutes",
        custom_data=["Active Households", "Participation Rate"],
        title="Daily Task Time by Household Group",
        color_discrete_sequence=["#3AA76D", DEEP_BLUE, "#E09F3E"],
        height=640,
    )
    fig.update_traces(
        texttemplate="%{text:.0f}",
        textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}: median %{y:.0f} minutes/day"
        "<br>Active households: %{customdata[0]} (%{customdata[1]:.1f}%)<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=45, t=125, b=125),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Activity"),
        yaxis=dict(title="Median minutes per day among active participants"),
    )
    return fig


LIVESTOCK_TYPES = {
    "Beef Cattle": "beef_cow",
    "Dairy Cattle": "dairy_cow",
    "Other Cattle": "other_cows",
    "Pigs": "pig",
    "Horses": "horse",
    "Goats": "goat",
    "Chickens": "chicken",
    "Other Poultry": "other_poultry",
}


def create_livestock_before_after_chart(data):
    rows = []
    for animal, suffix in LIVESTOCK_TYPES.items():
        before_col = f"e5a_{suffix}"
        after_col = f"e5b_{suffix}"
        if before_col not in data.columns or after_col not in data.columns:
            continue
        paired = pd.DataFrame({
            "Before biogas": pd.to_numeric(data[before_col], errors="coerce"),
            "Current": pd.to_numeric(data[after_col], errors="coerce"),
        }).dropna()
        paired = paired[(paired.ge(0) & paired.le(10000)).all(axis=1)]
        if paired.empty:
            continue
        for period in ["Before biogas", "Current"]:
            rows.append({
                "Animal Type": animal,
                "Period": period,
                "Median Animals": paired[period].median(),
                "Paired Households": len(paired),
                "Households Owning Animals": int(paired[period].gt(0).sum()),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data,
        x="Animal Type",
        y="Median Animals",
        color="Period",
        barmode="group",
        text="Median Animals",
        custom_data=["Paired Households", "Households Owning Animals"],
        title="Paired Livestock Holdings Before Biogas and at Present",
        color_discrete_sequence=[DEEP_BLUE, "#3AA76D"],
        height=610,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}",
        textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}: median %{y:.1f} animals"
        "<br>Paired households: %{customdata[0]}<br>Households with animals: %{customdata[1]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=45, t=125, b=105),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Animal type"), yaxis=dict(title="Median number of animals"),
    )
    return fig


def create_livestock_dynamics_chart(data):
    rows = []
    changes = {"Sold": "sold", "Bought": "bought", "Born": "born", "Died": "died"}
    for animal, suffix in LIVESTOCK_TYPES.items():
        for change, change_suffix in changes.items():
            column = f"e5c_{suffix}_{change_suffix}"
            if column not in data.columns:
                continue
            values = pd.to_numeric(data[column], errors="coerce")
            values = values[values.between(0, 10000)]
            if values.empty:
                continue
            rows.append({
                "Animal Type": animal,
                "Change": change,
                "Animals": values.sum(),
                "Valid Responses": int(values.notna().sum()),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data,
        x="Animal Type", y="Animals", color="Change", barmode="group",
        custom_data=["Valid Responses"], title="Reported Livestock Changes in the Last 12 Months",
        color_discrete_sequence=[DEEP_BLUE, "#E09F3E", "#3AA76D", "#B42318"], height=620,
    )
    fig.update_traces(
        hovertemplate="%{x}<br>%{fullData.name}: %{y:.0f} animals<br>Valid responses: %{customdata[0]}<extra></extra>"
    )
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=45, t=125, b=105),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Animal type"), yaxis=dict(title="Total animals reported"),
    )
    return fig


def create_livestock_practice_heatmap(data, prefix, categories, title):
    rows = []
    for animal, suffix in LIVESTOCK_TYPES.items():
        column = f"{prefix}_{suffix}"
        if column not in data.columns:
            continue
        series = data[column].dropna().astype(str).str.casefold()
        if series.empty:
            continue
        for category, keywords in categories.items():
            selected = series.apply(lambda value: any(keyword.casefold() in value for keyword in keywords))
            rows.append({
                "Animal Type": animal,
                "Practice": category,
                "Percentage": selected.mean() * 100,
                "Respondents": int(selected.sum()),
                "Valid Responses": len(series),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    pivot = chart_data.pivot(index="Animal Type", columns="Practice", values="Percentage")
    counts = chart_data.pivot(index="Animal Type", columns="Practice", values="Respondents").reindex(index=pivot.index, columns=pivot.columns)
    valid = chart_data.pivot(index="Animal Type", columns="Practice", values="Valid Responses").reindex(index=pivot.index, columns=pivot.columns)
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        customdata=np.dstack([counts.values, valid.values]),
        colorscale=[[0, "#F2F7FC"], [0.5, "#73B3E7"], [1, DEEP_BLUE]], zmin=0, zmax=100,
        text=np.where(pivot.values >= 5, np.char.add(np.round(pivot.values, 1).astype(str), "%"), ""),
        texttemplate="%{text}",
        hovertemplate="%{y}<br>%{x}: %{z:.1f}% (%{customdata[0]:.0f} of %{customdata[1]:.0f})<extra></extra>",
        colorbar=dict(title="Share"),
    ))
    fig.update_layout(
        title=title, template="plotly_white", paper_bgcolor=SURFACE, height=max(580, 48 * len(pivot.index) + 220),
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title_font=dict(size=17, color=DEEP_BLUE), title_x=0.02,
        margin=dict(l=100, r=55, t=125, b=115), xaxis_title="Practice", yaxis_title="Animal type",
    )
    return fig


def create_manure_feed_fraction_chart(data):
    rows = []
    for animal, suffix in LIVESTOCK_TYPES.items():
        column = f"e10_{suffix}"
        if column not in data.columns:
            continue
        values = pd.to_numeric(data[column], errors="coerce")
        values = values[values.between(0, 100)]
        if values.empty:
            continue
        rows.append({"Animal Type": animal, "Median Percentage": values.median(), "Valid Responses": len(values)})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    fig = px.bar(
        chart_data, x="Animal Type", y="Median Percentage", text="Median Percentage",
        custom_data=["Valid Responses"], title="Median Share of Manure Fed into the Biodigester",
        color_discrete_sequence=[DEEP_BLUE], height=560,
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%", textposition="outside",
        hovertemplate="%{x}: %{y:.1f}%<br>Valid responses: %{customdata[0]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left"),
        margin=dict(l=70, r=45, t=120, b=100), yaxis=dict(title="Median share", range=[0, 110], ticksuffix="%"),
        xaxis=dict(title="Animal type"),
    )
    return fig


def create_paired_median_chart(data, before_col, after_col, title, before_label, after_label, y_label):
    if before_col not in data.columns or after_col not in data.columns:
        return go.Figure().update_layout(meta={"empty_chart": True})
    paired = pd.DataFrame({
        before_label: pd.to_numeric(data[before_col], errors="coerce"),
        after_label: pd.to_numeric(data[after_col], errors="coerce"),
    }).replace([np.inf, -np.inf], np.nan).dropna()
    paired = paired[(paired.ge(0) & paired.le(1_000_000)).all(axis=1)]
    if paired.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    chart_data = pd.DataFrame({
        "Period": [before_label, after_label],
        "Median": [paired[before_label].median(), paired[after_label].median()],
        "Mean": [paired[before_label].mean(), paired[after_label].mean()],
        "Paired Records": [len(paired), len(paired)],
    })
    fig = px.bar(
        chart_data, x="Period", y="Median", text="Median", custom_data=["Mean", "Paired Records"],
        title=title, color="Period", color_discrete_sequence=[DEEP_BLUE, "#3AA76D"], height=530,
    )
    fig.update_traces(
        texttemplate="%{text:,.1f}", textposition="outside",
        hovertemplate="%{x}<br>Median: %{y:,.1f}<br>Mean: %{customdata[0]:,.1f}<br>Paired records: %{customdata[1]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF", showlegend=False,
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left"),
        margin=dict(l=70, r=45, t=120, b=80), xaxis_title="Period", yaxis_title=y_label,
    )
    return fig


FUEL_TRANSITION_COLUMNS = {
    "Firewood": ("B5-a1_firewood_qty", "B6-a1_firewood_reduction_mass", "B5-a2_firewood_price", "B6-a2_firewood_reduction_price"),
    "LPG": ("B5-b1_LPG_qty", "B6-b1_LPG_reduction_mass", "B5-b2_LPG_price", "B6-b2_LPG_reduction_price"),
    "Agricultural Waste": ("B5-c1_agricultural-waste_qty", "B6-c1_agriculture-waste_reduction_mass", "B5-c2_agricultural-waste_price", "B6-c2_agriculture-waste_reduction_price"),
    "Animal Manure": ("B5-d1_animal-manure_qty", "B6-d1_animal-manure_reduction_mass", "B5-d2_animal-manure_price", "B6-d2_animal-manure_reduction_price"),
    "Charcoal": ("B5-e1_charcoal_qty", "B6-e1_charcoal_reduction_mass", "B5-e2_charcoal_price", "B6-e2_charcoal_reduction_price"),
    "Kerosene": ("B5-f1_kerosene_qty", "B6-f1_kerosene_reduction_mass", "B5-f2_kerosene_price", "B6-f2_kerosene_reduction_price"),
}


def create_paired_fuel_transition_chart(data, metric="quantity"):
    rows = []
    for fuel, columns in FUEL_TRANSITION_COLUMNS.items():
        after_col, reduction_col = (columns[0], columns[1]) if metric == "quantity" else (columns[2], columns[3])
        if after_col not in data.columns or reduction_col not in data.columns:
            continue
        paired = pd.DataFrame({
            "After biogas": pd.to_numeric(data[after_col], errors="coerce"),
            "Reduction": pd.to_numeric(data[reduction_col], errors="coerce"),
        }).dropna()
        paired = paired[(paired.ge(0) & paired.le(10_000_000)).all(axis=1)]
        if len(paired) < 5:
            continue
        paired["Before biogas"] = paired["After biogas"] + paired["Reduction"]
        for period in ["Before biogas", "After biogas"]:
            rows.append({
                "Fuel": fuel,
                "Period": period,
                "Median": paired[period].median(),
                "Mean": paired[period].mean(),
                "Paired Households": len(paired),
            })
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    title = "Paired Fuel Quantity Before and After Biogas" if metric == "quantity" else "Paired Fuel Expenditure Before and After Biogas"
    y_label = "Median reported quantity (source units)" if metric == "quantity" else "Median reported expenditure (Rp)"
    fig = px.bar(
        chart_data, x="Fuel", y="Median", color="Period", barmode="group", text="Median",
        custom_data=["Mean", "Paired Households"], title=title,
        color_discrete_sequence=[DEEP_BLUE, "#3AA76D"], height=580,
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}", textposition="outside",
        hovertemplate="%{x}<br>%{fullData.name}<br>Median: %{y:,.1f}<br>Mean: %{customdata[0]:,.1f}"
        "<br>Paired households: %{customdata[1]}<extra></extra>",
    )
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left"),
        margin=dict(l=75, r=45, t=120, b=85),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="Fuel", yaxis_title=y_label,
    )
    return fig


def create_fuel_data_coverage_chart(data):
    rows = []
    for fuel, columns in FUEL_TRANSITION_COLUMNS.items():
        for metric, after_col, reduction_col in [
            ("Quantity", columns[0], columns[1]),
            ("Expenditure", columns[2], columns[3]),
        ]:
            after = pd.to_numeric(data[after_col], errors="coerce") if after_col in data.columns else pd.Series(dtype=float)
            reduction = pd.to_numeric(data[reduction_col], errors="coerce") if reduction_col in data.columns else pd.Series(dtype=float)
            paired = pd.concat([after.rename("after"), reduction.rename("reduction")], axis=1).dropna()
            rows.append({"Fuel": fuel, "Metric": metric, "Paired Households": len(paired)})
    chart_data = pd.DataFrame(rows)
    fig = px.bar(
        chart_data, x="Fuel", y="Paired Households", color="Metric", barmode="group", text="Paired Households",
        title="Paired Fuel Data Coverage", color_discrete_sequence=[DEEP_BLUE, "#E09F3E"], height=520,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        template="plotly_white", paper_bgcolor=SURFACE, plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left"),
        margin=dict(l=70, r=45, t=120, b=85),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def render_bus_section_f(data):
    section_data = data.copy()
    charts = ChartGenerator(section_data)

    st.subheader("Livestock Ownership and Population Change")
    st.plotly_chart(
        charts.create_pie_chart(names_col="e1", agg_method="count", title="Livestock Personally Owned by the Household"),
        use_container_width=True, key="F_livestock_owned",
    )
    st.caption("Before-after values use paired households. Medians limit distortion from exceptionally large herds.")
    st.plotly_chart(create_livestock_before_after_chart(section_data), use_container_width=True, key="F_livestock_before_after")
    st.plotly_chart(create_livestock_dynamics_chart(section_data), use_container_width=True, key="F_livestock_dynamics")

    st.subheader("Livestock and Manure Management")
    st.plotly_chart(
        create_livestock_practice_heatmap(
            section_data, "e4",
            {"Spread on Open Land": ["disebarkan ke lahan terbuka"], "Disposed to River": ["dibuang ke sungai"], "Sold": ["dijual"], "Other": ["lainnya"]},
            "Manure Handling Before Biogas Adoption",
        ), use_container_width=True, key="F_baseline_manure_handling",
    )
    st.plotly_chart(
        create_livestock_practice_heatmap(
            section_data, "e6",
            {"Stall-Fed": ["pemberian pakan di kandang"], "Semi-Open Grazing": ["semi-terbuka"], "Open Grazing": ["penggembalaan terbuka"]},
            "Livestock Grazing and Housing Method",
        ), use_container_width=True, key="F_grazing_method",
    )
    manure_codes = {"beef_cow": "a", "dairy_cow": "b", "other_cows": "c", "pig": "d", "horse": "e", "goat": "f", "chicken": "g", "other_poultry": "h"}
    for suffix, code in manure_codes.items():
        if f"e9{code}" in section_data.columns:
            section_data[f"manure_storage_{suffix}"] = section_data[f"e9{code}"]
    st.plotly_chart(
        create_livestock_practice_heatmap(
            section_data, "manure_storage",
            {
                "Anaerobic Lagoon": ["anaerobik", "anaerobic"], "Liquid / Slurry": ["slurry", "disimpan basah"],
                "Dry Lot": ["dry lot", "disimpan terbuka"], "Solid Storage": ["kotak bersekat", "solid storage"],
                "Daily Spread": ["disebar di tanah", "daily spread"], "Biodigester": ["digester"],
                "Left Scattered": ["dibiarkan tersebar"],
            },
            "Current Manure Storage Methods",
        ), use_container_width=True, key="F_manure_storage",
    )
    st.plotly_chart(create_manure_feed_fraction_chart(section_data), use_container_width=True, key="F_manure_fraction")

    with st.expander("Detailed Livestock Management Practices", expanded=False):
        st.plotly_chart(
            create_livestock_practice_heatmap(
                section_data, "e7",
                {"Daily": ["setiap hari"], "Every 2-6 Days": ["2-6 hari"], "Weekly": ["setiap minggu"], "Every 2-3 Weeks": ["2-3 minggu"], "Less Often than Monthly": [">1 bulan"]},
                "Frequency of Livestock Health Management",
            ), use_container_width=True, key="F_health_management",
        )
        st.plotly_chart(
            create_livestock_practice_heatmap(
                section_data, "e8",
                {"More Than Daily": [">1 kali sehari"], "Daily": ["1 kali sehari"], "Every 2-6 Days": ["2-6 hari"], "Every 1-3 Weeks": ["1-3 minggu"], "Less Often than Monthly": [">1 bulan"]},
                "Frequency of Livestock-Shed Cleaning",
            ), use_container_width=True, key="F_shed_cleaning",
        )
        st.plotly_chart(
            create_livestock_practice_heatmap(
                section_data, "e12", {"Fresh Fodder": ["pakan segar", "rumput"], "Dry or Processed Feed": ["pakan kering", "konsentrat", "silase", "pelet"]},
                "Main Livestock Feed Type",
            ), use_container_width=True, key="F_fodder_type",
        )

    st.subheader("Bio-slurry Adoption and Utilization")
    adoption_cols = st.columns(3)
    for container, column, title, key in zip(
        adoption_cols,
        ["e13", "e15", "e16"],
        ["Households Using Bio-slurry", "Received CPO Training on Bio-slurry", "Knowledge of Bio-slurry Benefits"],
        ["F_bioslurry_use", "F_bioslurry_training", "F_bioslurry_knowledge"],
    ):
        with container:
            st.plotly_chart(charts.create_pie_chart(names_col=column, agg_method="count", title=title), use_container_width=True, key=key)
    form_n = int(section_data["e13a_bioslurry_form_used"].notna().sum()) if "e13a_bioslurry_form_used" in section_data.columns else 0
    st.caption(f"Bio-slurry form is conditional on reported use (N={form_n:,}).")
    st.plotly_chart(
        charts.create_selection_summary_chart(
            columns=["e13a_bioslurry_form_used_liquid", "e13a_bioslurry_form_used_solid"], option_names=["Liquid", "Solid"],
            title="Form of Bio-slurry Used", x_label="Users", y_label="Bio-slurry form",
        ), use_container_width=True, key="F_bioslurry_form",
    )
    st.plotly_chart(
        charts.create_selection_summary_chart(
            columns=[
                "e17_bioslurry_usage_fertilizer", "e17_bioslurry_usage_livestock", "e17_bioslurry_usage_sold",
                "e17_bioslurry_usage_disposed_near_shed", "e17_bioslurry_usage_given_for_free",
                "e17_bioslurry_usage_left_in_place", "e17_bioslurry_usage_disposed_in_drain",
            ],
            option_names=["Fertilizer on Own Farmland", "Livestock or Fishery Use", "Sold", "Applied Near Livestock Shed", "Given Away", "Left in Storage", "Disposed to Drainage"],
            title="Bio-slurry Utilization and Disposal Methods", x_label="Respondents", y_label="Method",
        ), use_container_width=True, key="F_bioslurry_methods",
    )
    nonuse_n = int(section_data["e36"].notna().sum()) if "e36" in section_data.columns else 0
    st.caption(f"Reasons for non-use are a conditional multiple-response question (N={nonuse_n:,}).")
    st.plotly_chart(
        charts.create_selection_summary_chart(
            columns=["e36_unsuitable", "e36_lack_of_storage", "e36_no_collection_time", "e36_difficult_to_transport", "e36_unaware", "e36_chemical_fertilizer", "e36_others1"],
            option_names=["Unsuitable for Intended Use", "No Storage Space", "No Time to Collect", "Difficult to Transport", "Unaware of Benefits", "Prefer Chemical Fertilizer", "Other"],
            title="Reasons for Not Using Bio-slurry", x_label="Respondents", y_label="Reason",
        ), use_container_width=True, key="F_bioslurry_nonuse",
    )

    with st.expander("Detailed Bio-slurry Uses", expanded=False):
        st.plotly_chart(
            charts.create_selection_summary_chart(
                columns=["e18_farming_fertilizer", "e18_farming_soil_conditioner", "e18_farming_pesticides", "e18_farming_planting_medium", "e18_farming_others1"],
                option_names=["Fertilizer", "Soil Conditioner", "Pesticide Input", "Planting Medium", "Other"],
                title="Agricultural Uses of Bio-slurry", x_label="Users", y_label="Agricultural use",
            ), use_container_width=True, key="F_farming_uses",
        )
        st.plotly_chart(
            charts.create_selection_summary_chart(
                columns=["e18_livestock_fish_feed", "e18_livestock_poultry_feed", "e18_livestock_worm_farming", "e18_livestock_fish_fertilizer", "e18_livestock_others1"],
                option_names=["Fish Feed", "Poultry Feed", "Worm Farming", "Fishpond Fertilizer", "Other"],
                title="Livestock and Fishery Uses of Bio-slurry", x_label="Users", y_label="Livestock or fishery use",
            ), use_container_width=True, key="F_livestock_uses",
        )

    st.subheader("Agricultural Application")
    crop_categories = {
        "Rice and Cereals": ["padi", "jagung", "gandum", "sorgum"],
        "Vegetables and Legumes": ["sayur", "cabai", "tomat", "terong", "bawang", "kacang", "kol", "sawi"],
        "Fruit Crops": ["pisang", "mangga", "pepaya", "jeruk", "durian", "buah"],
        "Plantation or Cash Crops": ["kopi", "kakao", "cengkeh", "tembakau", "tebu", "kelapa"],
        "Fodder and Grass": ["rumput", "pakan"],
    }
    application_cols = st.columns(2)
    with application_cols[0]:
        st.plotly_chart(create_categorized_text_chart(section_data, "e20", crop_categories, "Crop Groups Receiving Bio-slurry", x_label="Responses", y_label="Crop group"), use_container_width=True, key="F_crop_groups")
    with application_cols[1]:
        st.plotly_chart(charts.create_bar_chart(x_col="e21", agg_method="count", title="Frequency of Applying Bio-slurry to Farmland", x_label="Application frequency", y_label="Respondents"), use_container_width=True, key="F_application_frequency")
    st.plotly_chart(
        create_binned_count_chart(section_data, "e22", [-0.001, 100, 500, 1000, 5000, 10000, np.inf], ["Up to 100", ">100-500", ">500-1,000", ">1,000-5,000", ">5,000-10,000", ">10,000"], "Farmland Area Fertilized with Bio-slurry", "Land area (m²)"),
        use_container_width=True, key="F_land_area",
    )
    quantity_cols = st.columns(2)
    for container, column, title, label, key in zip(
        quantity_cols, ["e24_liquid", "e24_solid"], ["Liquid Bio-slurry Used per Application", "Solid Bio-slurry Used per Application"],
        ["Liters per application", "Kilograms per application"], ["F_liquid_application", "F_solid_application"],
    ):
        with container:
            st.plotly_chart(create_binned_count_chart(section_data, column, [-0.001, 10, 25, 50, 100, 250, np.inf], ["Up to 10", ">10-25", ">25-50", ">50-100", ">100-250", ">250"], title, label), use_container_width=True, key=key)

    st.subheader("Agricultural Outcomes")
    st.caption("Before-after charts use paired records and medians. Quantities remain in respondents' reported units because no harmonized unit field is available.")
    comparison_cols = st.columns(2)
    with comparison_cols[0]:
        st.plotly_chart(create_paired_median_chart(section_data, "e26", "e27", "Chemical Fertilizer Use Before and After Bio-slurry", "Before Bio-slurry", "After Bio-slurry", "Median reported quantity"), use_container_width=True, key="F_fertilizer_before_after")
    with comparison_cols[1]:
        st.plotly_chart(create_paired_median_chart(section_data, "e28", "e29", "Harvest Output Before and After Bio-slurry", "Before Bio-slurry", "After Bio-slurry", "Median reported harvest quantity"), use_container_width=True, key="F_harvest_before_after")
    outcome_cols = st.columns(2)
    with outcome_cols[0]:
        st.plotly_chart(charts.create_pie_chart(names_col="e30", agg_method="count", title="Bio-slurry Enabled Cultivation of New Crops"), use_container_width=True, key="F_new_crops")
        st.plotly_chart(create_ordered_category_chart(section_data, "e32", ["Decreased", "No Change", "Moderately Improved", "Significantly Improved"], "Crop Resistance to Pests and Diseases"), use_container_width=True, key="F_pest_resistance")
    with outcome_cols[1]:
        st.plotly_chart(create_ordered_category_chart(section_data, "e31", ["Decreased", "No Change", "Moderately Improved", "Significantly Improved"], "Soil Quality After Bio-slurry Application"), use_container_width=True, key="F_soil_quality")
        st.plotly_chart(create_ordered_category_chart(section_data, "e33", ["Decreased", "No Change", "Moderately Improved", "Significantly Improved"], "Crop Drought Resistance"), use_container_width=True, key="F_drought_resistance")

    with st.expander("Livestock Productivity and Bio-slurry Sales", expanded=False):
        productivity_cols = st.columns(2)
        with productivity_cols[0]:
            st.plotly_chart(create_ordered_category_chart(section_data, "e34", ["Decreased", "No Change", "Moderately Improved", "Significantly Improved"], "Quality or Quantity of Livestock Feed"), use_container_width=True, key="F_feed_outcome")
        with productivity_cols[1]:
            st.plotly_chart(create_ordered_category_chart(section_data, "e35", ["Decreased", "No Change", "Moderately Improved", "Significantly Improved"], "Livestock Productivity"), use_container_width=True, key="F_livestock_productivity")
        sales_n = int(section_data["e19"].notna().sum()) if "e19" in section_data.columns else 0
        st.caption(f"Bio-slurry sales form has a small conditional sample (N={sales_n:,}); interpret it descriptively.")
        st.plotly_chart(charts.create_bar_chart(x_col="e19", agg_method="count", title="Form of Bio-slurry Sold", x_label="Form sold", y_label="Respondents"), use_container_width=True, key="F_bioslurry_sales_form")
        st.plotly_chart(create_bioslurry_revenue_chart(section_data), use_container_width=True, key="F_bioslurry_revenue")

    st.info(
        "Extreme livestock, land-area, application-volume, and harvest values remain in the source data. "
        "Primary comparisons use paired medians, and unharmonized quantities are not converted into percentages or causal estimates."
    )


def render_bus_section_g(data):
    section_data = data.copy()
    charts = ChartGenerator(section_data)

    st.subheader("Biogas Utilization")
    utilization_cols = st.columns(2)
    with utilization_cols[0]:
        st.plotly_chart(
            charts.create_pie_chart(names_col="B1_biogas_use", agg_method="count", title="Biogas Use for Cooking"),
            use_container_width=True, key="G_biogas_usage_rate",
        )
        st.plotly_chart(
            create_ordered_category_chart(
                section_data, "b8", ["Less Than 1 Hour", "1-3 Hours", "3-5 Hours", "More Than 5 Hours"],
                "Average Daily Biogas Stove Burning Duration",
            ), use_container_width=True, key="G_burning_duration",
        )
    with utilization_cols[1]:
        st.plotly_chart(
            charts.create_pie_chart(names_col="b9", agg_method="count", title="Reduced Tree Cutting for Fuel"),
            use_container_width=True, key="G_tree_cutting",
        )
        st.plotly_chart(
            create_ordered_category_chart(
                section_data, "b7", ["<15 Kg", "15-30 Kg", "30-50 Kg", "50-65 Kg", "65-80 Kg", "80-100 Kg", ">100 Kg"],
                "Daily Manure Input for Biogas Production",
            ), use_container_width=True, key="G_manure_input",
        )
    usage_n = int(section_data["B1_biogas_use"].notna().sum()) if "B1_biogas_use" in section_data.columns else 0
    st.caption(
        f"Full or partial utilization is available for {usage_n:,} respondents. This is an unweighted survey rate, not the age- and drop-off-weighted program usage rate required for carbon monitoring."
    )

    st.subheader("Household Fuel Transition")
    st.caption(
        "Baseline fuel use is derived as reported post-biogas use plus reported reduction. Charts include only households with both fields and use medians because fuel quantities contain large values."
    )
    st.plotly_chart(
        create_paired_fuel_transition_chart(section_data, metric="quantity"),
        use_container_width=True, key="G_fuel_quantity_transition",
    )
    st.plotly_chart(
        create_paired_fuel_transition_chart(section_data, metric="expenditure"),
        use_container_width=True, key="G_fuel_cost_transition",
    )
    st.caption(
        "Only fuels with at least five paired households are shown. Firewood and LPG meet this threshold; charcoal, agricultural waste, animal manure, and kerosene do not."
    )
    with st.expander("Fuel Data Coverage", expanded=False):
        st.plotly_chart(create_fuel_data_coverage_chart(section_data), use_container_width=True, key="G_fuel_coverage")

    st.subheader("Reported Environmental Co-benefits")
    st.caption(
        "These indicators reflect respondents' reported household conditions and perceptions; they are not direct environmental measurements."
    )
    environment_cols = st.columns(2)
    with environment_cols[0]:
        st.plotly_chart(
            create_ordered_category_chart(
                section_data, "c2", ["No Change", "Cleaner", "Much Cleaner"],
                "Kitchen Cleanliness After Biogas Adoption",
            ), use_container_width=True, key="G_kitchen_cleanliness",
        )
    with environment_cols[1]:
        st.plotly_chart(
            create_ordered_category_chart(
                section_data, "c27", ["No Change", "Somewhat Improved", "Much Better"],
                "Livestock-Shed Cleanliness After Biogas Adoption",
            ), use_container_width=True, key="G_shed_cleanliness",
        )

    st.subheader("Supporting Monitoring Indicators")
    st.markdown(
        "- Plant operating status and drop-off context are reported in **Section C**.\n"
        "- Livestock population, manure storage, animal housing, and manure fractions are reported in **Section F**.\n"
        "- These indicators are not duplicated here so Section G remains focused on household energy transition."
    )
    st.info(
        "The BUS workbook does not contain direct daily gas-volume measurements, a complete stove-type variable, project-population weighting parameters, or approved emission factors. "
        "Accordingly, this dashboard does not calculate verified greenhouse-gas reductions or CO₂e from BUS responses alone."
    )


def create_bioslurry_revenue_chart(data):
    required = ["d15_liter_sold", "d15_kilogram_sold", "d16_price_per_liter", "d16_price_per_kilogram"]
    if not all(column in data.columns for column in required):
        return go.Figure().update_layout(meta={"empty_chart": True})
    liquid_revenue = pd.to_numeric(data[required[0]], errors="coerce") * pd.to_numeric(data[required[2]], errors="coerce")
    solid_revenue = pd.to_numeric(data[required[1]], errors="coerce") * pd.to_numeric(data[required[3]], errors="coerce")
    revenue = pd.concat([liquid_revenue, solid_revenue], axis=1).sum(axis=1, min_count=1).dropna()
    revenue = revenue[revenue >= 0]
    if revenue.empty:
        return go.Figure().update_layout(meta={"empty_chart": True})
    bins = [-0.001, 100000, 250000, 500000, 1000000, np.inf]
    labels = ["Up to Rp100k", ">Rp100k-250k", ">Rp250k-500k", ">Rp500k-1M", ">Rp1M"]
    grouped = pd.cut(revenue, bins=bins, labels=labels, include_lowest=True).value_counts(sort=False).reset_index()
    grouped.columns = ["Estimated Monthly Revenue", "Respondents"]
    grouped = grouped[grouped["Respondents"] > 0]
    fig = px.bar(
        grouped,
        x="Estimated Monthly Revenue",
        y="Respondents",
        text="Respondents",
        title=f"Estimated Monthly Income from Bio-slurry Sales (N={len(revenue)})",
        color_discrete_sequence=[DEEP_BLUE],
        height=500,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=70, r=42, t=110, b=90),
    )
    return fig


def categorize_section_b_text(value, category_map):
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if not text or text.casefold().strip(" .,-") in {"", "0", "0.0", "x", "no", "none", "n/a", "na", "tidak"}:
        return np.nan
    lower = text.lower()
    for category, keywords in category_map.items():
        if any(keyword in lower for keyword in keywords):
            return category
    return "Other"


def create_categorized_text_chart(data, column, category_map, title, x_label="Respondents", y_label="Category"):
    if column not in data.columns:
        fig = go.Figure()
        fig.update_layout(meta={"empty_chart": True, "empty_reason": f"Column {column} is not available."})
        return fig

    categories = data[column].apply(lambda value: categorize_section_b_text(value, category_map)).dropna()
    if categories.empty:
        fig = go.Figure()
        fig.update_layout(meta={"empty_chart": True, "empty_reason": "No valid text data available."})
        return fig

    counts = categories.value_counts().reset_index()
    counts.columns = [y_label, x_label]
    counts = counts.sort_values(x_label, ascending=True)
    height = max(520, 52 * max(len(counts), 7))
    fig = px.bar(
        counts,
        x=x_label,
        y=y_label,
        orientation="h",
        title=title,
        text=x_label,
        height=height,
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor="#F8FBFF",
        font=dict(family='Inter, "Segoe UI", Arial, sans-serif', color=INK, size=13),
        title=dict(font=dict(size=17, color=DEEP_BLUE), x=0.02, xanchor="left", y=0.98, yanchor="top"),
        margin=dict(l=170, r=70, t=128, b=86),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(24, 79, 143, 0.08)", zeroline=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    fig.update_yaxes(showgrid=False, tickfont=dict(color=MUTED), title_font=dict(color=INK))
    return fig


WORK_ACTIVITY_CATEGORIES = {
    "Gardening/Farming": ["bertani", "berkebun", "bercocok", "pertanian", "tani", "sawah", "tanam", "panen", "rumput", "bawang", "tembakau", "tebu", "pakan"],
    "Selling/Trading": ["jual", "berjualan", "jualan", "trading", "selling", "dagang"],
    "Daily Labor/Construction": ["buruh", "harian", "bangunan", "tukang"],
    "Livestock/Fishery": ["ternak", "kambing", "ikan", "tambak", "unggas", "sapi"],
    "Services/Office": ["kantor", "gojek", "service", "print", "fotocopy", "elektronik"],
    "Care/Education": ["anak", "sekolah", "mengantar", "jemput"],
}

NON_WORK_ACTIVITY_CATEGORIES = {
    "Rest/Relaxation": ["istirahat", "beristirahat", "santai", "lelah", "capek", "capai", "cpaek", "capak"],
    "No Saved/Free Time": ["tidak ada waktu", "no saved", "tidak ada waktu luang", "waktu mepet", "masih mencari firewood", "no"],
    "Family/Childcare": ["keluarga", "anak", "cucu", "mengasuh", "pondok", "mengaji"],
    "Household/Garden Chores": ["membersihkan", "rumah", "kebun", "ternak"],
    "Work/Selling": ["bekerja", "berjualan", "harian", "sawah"],
    "Social/Community": ["sosial", "tetangga", "pkk", "tahlil", "acara"],
}

SOCIAL_ACTIVITY_CATEGORIES = {
    "Religious Activities": ["pengajian", "tahlil", "jama", "diba", "sholawat", "manaqib", "gereja", "sembahyang", "majelis", "religious"],
    "Community Meetings": ["rt", "pkk", "pertemuan", "warga", "desa", "program kerja", "community"],
    "Mutual Aid/Customary Events": ["gotong", "adat", "upacara", "kemanusian", "lingkungan"],
    "Family/Neighbor Gathering": ["keluarga", "tetangga", "berkumpul", "kumpul", "undangan"],
    "Savings/Cooperative Activities": ["simpan pinjam", "koperasi", "pelayanan anggota"],
}

OTHER_ACTIVITY_CATEGORIES = {
    "Household Chores": ["membersihkan", "rumah", "kebun"],
    "Selling/Trading": ["jual", "berjualan", "trading", "selling"],
    "Family/Care": ["orang tua", "anak", "keluarga"],
    "Social/Community": ["sosial", "tetangga", "gotong", "adat", "kemanusian", "community"],
    "Hobby/Personal": ["olahraga", "menjahit", "nonton", "tv"],
    "Gardening/Farming": ["berkebun", "farming", "tegal"],
}

SAVINGS_OTHER_CATEGORIES = {
    "No Additional Income/Savings": ["tidak ada peningkatan", "tidak ada penghematan", "tidak ada peningkatan pendapatan", "tidak ada peningkatan atau penurunan"],
    "Biogas Program/System Not Yet Successful": ["program biogas", "belum berhasil", "not functioning", "menyala sebentar"],
}

GRANT_OTHER_CATEGORIES = {
    "University/Higher Education": ["higher education", "universitas", "widyagama"],
    "YRE/Partner Organization": ["yayasan rumah energi", "yre", "pgn", "danone"],
    "Government Agency": ["dinas", "pertanian"],
    "Do Not Know/Remember": ["do not know", "tidak ingat"],
    "Individual Donor": ["usman"],
}

LOAN_OTHER_CATEGORIES = {
    "KIVA Partner Institution": ["kiva", "lembaga mitra"],
}

CREDITOR_CONTACT_OTHER_CATEGORIES = {
    "Livestock Group Leader": ["ketua kelompok ternak"],
    "Milk Group/Leader": ["kelompok susu", "ketua kelompok susu"],
    "Family Member": ["bapak", "responden", "keluarga"],
}

SELF_FINANCE_OTHER_CATEGORIES = {
    "Child": ["anak"],
    "Parents": ["orang tua"],
    "Tourism Board Leader": ["pengurus wisata", "wisata"],
    "Do Not Know": ["do not know", "tidak tahu"],
}


def bus_overview_summary(data):
    insights = [
        bus_share_highlight(
            data, "c2", ["Cleaner", "Much Cleaner"],
            "Section A - Health and sanitation: {percentage:.1f}% reported a cleaner kitchen after adopting biogas "
            "({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "d1a", ["Yes"],
            "Section B - Socio-economic conditions: {percentage:.1f}% reported increased household income after "
            "biogas adoption ({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "a9_operable_biogas", ["Yes", "Functioning Well", "1"],
            "Section C - Technical performance: {percentage:.1f}% of assessed biogas systems were recorded as "
            "operational ({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "g2", ["Satisfied", "Very Satisfied"],
            "Section D - User satisfaction: {percentage:.1f}% were satisfied or very satisfied with biogas "
            "({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "f2", ["Reduced", "Significantly Reduced"],
            "Section E - Gender impacts: {percentage:.1f}% reported a reduction in women's household workload "
            "({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "e13", ["Yes"],
            "Section F - Agricultural systems: {percentage:.1f}% reported actively using bio-slurry "
            "({count:,} of {total:,} valid responses).",
        ),
        bus_share_highlight(
            data, "b9", ["Yes"],
            "Section G - Energy and sustainable development: {percentage:.1f}% reported that biogas helped reduce "
            "tree cutting for household fuel ({count:,} of {total:,} valid responses).",
        ),
    ]
    render_summary_panel("Key Findings Across Sections A-G", [insight for insight in insights if insight])


def bus_cross_section_reading(data):
    operational = bus_response_series(data, "a9_operable_biogas")
    satisfaction = bus_response_series(data, "g2")
    bio_slurry = bus_response_series(data, "e13")

    readings = []
    if not operational.empty and not satisfaction.empty:
        operational_share = operational.str.casefold().isin({"yes", "functioning well", "1"}).mean() * 100
        satisfaction_share = satisfaction.str.casefold().isin({"satisfied", "very satisfied"}).mean() * 100
        readings.append(
            f"User sentiment is strong ({satisfaction_share:.1f}% satisfied or very satisfied), but recorded system "
            f"operability is lower ({operational_share:.1f}%). Restoring non-operational systems is therefore a "
            "central technical priority."
        )
    if not bio_slurry.empty:
        bio_slurry_share = bio_slurry.str.casefold().eq("yes").mean() * 100
        readings.append(
            f"Bio-slurry use remains limited to {bio_slurry_share:.1f}% of valid responses, indicating that the "
            "agricultural value of biogas is not yet being captured consistently."
        )
    if readings:
        render_summary_panel("Cross-Section Reading", readings)


def render_e4_manure_handling_chart(data, chart_gen):
    livestock_columns = {
        "Beef Cattle": "e4_beef_cow",
        "Dairy Cattle": "e4_dairy_cow",
        "Other Cattle/Buffalo": "e4_other_cows",
        "Pigs": "e4_pig",
        "Horses": "e4_horse",
        "Goats": "e4_goat",
        "Chickens": "e4_chicken",
        "Other Poultry": "e4_other_poultry",
    }
    handling_options = {
        "Spread Over Open Land": "disebarkan ke lahan terbuka",
        "Thrown Into River": "dibuang ke sungai",
        "Sold": "dijual",
        "Other": "lainnya",
    }
    rows = []
    for livestock, column in livestock_columns.items():
        if column not in data.columns:
            continue
        series = data[column].dropna().astype(str).str.lower()
        series = series[series.str.strip().ne("") & series.ne("nan")]
        for handling, keyword in handling_options.items():
            count = int(series.str.contains(keyword, regex=False).sum())
            if count:
                rows.append({"Livestock": livestock, "Handling": handling, "Count": count})
    chart_data = pd.DataFrame(rows)
    if chart_data.empty:
        st.info("E4 manure handling data is not available for the current filter.")
        return
    fig = px.bar(
        chart_data,
        x="Livestock",
        y="Count",
        color="Handling",
        barmode="group",
        title="E4. Manure Handling Before Using Biogas by Livestock Type",
        text_auto=True,
    )
    fig.update_layout(xaxis_tickangle=-20, legend_title_text="Handling")
    st.plotly_chart(chart_gen._apply_theme(fig), use_container_width=True, key="F_E4_manure_handling")


def Page_BUS():
    # Set page configuration
    st.set_page_config(
        page_title="Biogas User Survey",
        page_icon=":bar_chart:",
        layout="wide"
    )

    st.session_state["BUS_hidden_empty_charts"] = []
    install_empty_chart_filter()
    apply_global_theme()
    render_page_header("Biogas User Survey", "Survey 2026")

    # Add home button
    if st.button("Home", key="Home BUS", type="primary"):
        st.switch_page("main_app.py", query_params={"utm_source": "main_app.py"})

    # Process BUS data
    BUS_data = load_bus_data()
    BUS_data = change_column_types(BUS_data, ['year_completion'],'string')
    BUS_data['year_completion_clean'] = pd.to_numeric(BUS_data['year_completion'], errors='coerce')
    BUS_data.loc[
        ~BUS_data['year_completion_clean'].between(2000, 2026),
        'year_completion_clean'
    ] = np.nan
    BUS_data['year_completion_clean'] = BUS_data['year_completion_clean'].astype('Int64').astype('string')
    BUS_data = remove_zero_values(BUS_data, [397, 398, 399, 400, 401, 402, 403, 404])
    BUS_data = calculate_fuel_costs(BUS_data, ['B5-a2_firewood_price', 'B5-b2_LPG_price', 'B5-c2_agricultural-waste_price', 'B5-d2_animal-manure_price', 'B5-e2_charcoal_price', 'B5-f2_kerosene_price'])

    # Store data in session state
    st.session_state.BUS_data = BUS_data

    # Create a chart generator instance
    st.session_state.chart_gen = ChartGenerator(BUS_data)

    # Identify potential filter columns (categorical with low cardinality)
    st.session_state.filter_columns = [
        'Province',
        'Gender',
        'Marriage Status',
        'Education',
        'VPA'
    ]

    # Map filter columns to column name
    column_map = {
        'Province':'province',
        'Gender':'gender',
        'Marriage Status':'marriage_status',
        'Education':'education',
        'VPA':'vpa'
    }

    # Create sidebar filters if data is loaded
    render_sidebar_header()

    # Define list of filter columns
    filter_columns = st.sidebar.multiselect(
        'Select Filter Columns:',
        options=st.session_state.filter_columns,
        default=st.session_state.filter_columns[:min(3, len(st.session_state.filter_columns))]
    )

    # Create filters for selected columns
    applied_filters = {}
    for ID in filter_columns:
        col = column_map[ID]
        unique_values = sorted(st.session_state.BUS_data[col].dropna().unique())
        selected_values = st.sidebar.multiselect(
            f'Select {ID}:',
            options=unique_values,
            default=unique_values
        )

        if len(selected_values) > 0 and len(selected_values) < len(unique_values):
            applied_filters[col] = selected_values

    # Apply filters
    filtered_data = st.session_state.BUS_data.copy()
    for col, values in applied_filters.items():
        filtered_data = filtered_data[filtered_data[col].isin(values)]

    # Store filtered data
    st.session_state.filtered_data = filtered_data

    # Update chart generator with filtered data
    st.session_state.chart_gen.update_data(filtered_data)

    # Display data size after filtering
    st.sidebar.markdown(f"**Filtered data:** {len(filtered_data):,} rows")
    
    # Create tabs for different sections
    tabs = st.tabs([
        "Summary", "Section A", "Section B", "Section C", "Section D",
        "Section E", "Section F", "Section G", "Exploration"
    ])

    # Get data for analysis
    data = st.session_state.filtered_data
    chart_gen = st.session_state.chart_gen

    # Summary Tab
    with tabs[0]:
        st.header("Biogas User Survey Summary")
        st.caption(
            "Executive findings are presented first. Respondent characteristics and geographic coverage are "
            "shown separately below to distinguish survey results from sample distribution."
        )

        st.subheader("Executive Summary")
        bus_overview_summary(data)
        bus_cross_section_reading(data)

        st.space("medium")
        st.subheader("Composite BUS Outcome Profile")
        render_satisfaction_spider(
            data,
            "Composite Outcome Profile Across BUS Survey Dimensions",
            "BUS_summary_satisfaction_spider",
        )

        st.divider()
        st.subheader("Respondent Profile and Data Distribution")
        st.caption(
            "The indicators below describe the composition and geographic coverage of the active survey sample; "
            "they are contextual information rather than survey outcomes."
        )

        # Create summary metrics
        cols = st.columns(5)

        with cols[0]:
            st.metric("Sample Size", len(data))

        with cols[1]:
            average_age = pd.to_numeric(data['age'], errors='coerce').mean()
            st.metric("Average Age", round(average_age, 1) if pd.notna(average_age) else "N/A")

        with cols[2]:
            st.metric("Number of Provinces", data['province'].dropna().astype(str).str.lower().nunique())

        with cols[3]:
            st.metric("Number of Districts", data['district'].dropna().astype(str).str.lower().nunique())

        with cols[4]:
            st.metric("Number of Subdistricts", data['subdistrict'].dropna().astype(str).str.lower().nunique())

        st.space("medium")
        cols = st.columns(2)

        # Create summary charts
        with cols[0]:
            fig_1 = chart_gen.create_bar_chart(
                x_col='province',
                agg_method='count',
                title='Number of Respondents by Province',
                x_label='Provinces',
                color='gender',
                legend_title='Gender',
                orientation='h',
                y_label='Number of Respondents'
            )
            st.plotly_chart(fig_1, use_container_width=True)

            fig_2 = chart_gen.create_pie_chart(
                names_col='marriage_status',
                agg_method='count',
                title='Marriage Status'
            )
            st.plotly_chart(fig_2, use_container_width=True)

        with cols[1]:
            fig_3 = chart_gen.create_pie_chart(
                names_col='gender',
                agg_method='count',
                title='Gender'
            )
            st.plotly_chart(fig_3, use_container_width=True)

            fig_4 = chart_gen.create_bar_chart(
                x_col='education',
                agg_method='count',
                title='Education Level',
                x_label='Education',
                color='gender',
                legend_title='Gender',
                orientation='h',
                y_label='Number of Respondents'
            )
            st.plotly_chart(fig_4, use_container_width=True)

        # Age histogram
        fig_6 = chart_gen.create_histogram(
            column='age',
            bins=20,
            title='Respondent Age Distribution',
            x_label='Age',
            y_label='Number',
            color='gender',
            legend_title='Gender',
            show_normal=False,                  # Show normal distribution curve
            show_stats=True                     # Show mean and median lines
        )
        st.plotly_chart(fig_6, use_container_width=True)

        # Salary distribution bar chart
        fig_7 = chart_gen.create_bar_chart(
            x_col='monthly_income',
            agg_method='count',
            title='Monthly Income',
            x_label='Income',
            color='gender',
            legend_title='Gender',
            orientation='h',
            y_label='Number of Respondents'
        )
        st.plotly_chart(fig_7, use_container_width=True)

        # Geographic distribution
        st.subheader("Geographic Distribution")

        color_col = 'province'
        info_cols = ['name', 'gender', 'age', 'province', 'district']

        geo_map = chart_gen.create_geo_plot(
            lat_col='biogas_lat',
            lon_col='biogas_long',
            info_col=info_cols,
            color_col=color_col,
            zoom_start=6,
            title='Respondent Locations'
        )
        folium_static(geo_map, width=1500, height=750)
    
    # Section A Tab
    with tabs[1]:
        st.header("Section A: Impact on Health and Sanitation")
        bus_section_summary(
            data,
            "Section A",
            "C. Dampak Kesehatan dan Sanitasi",
            focus_terms=["dapur", "asap", "sakit", "dokter", "kebersihan", "kesehatan"],
        )

        cols = st.columns(2)

        with cols[0]:
            fig_a1 = chart_gen.create_pie_chart(
                names_col='c1',
                agg_method='count',
                title='New or Renovated Kitchen for Biogas Cooking'
            )
            st.plotly_chart(fig_a1, use_container_width=True)

        with cols[1]:
            fig_a2 = chart_gen.create_bar_chart(
                x_col='c2',
                agg_method='count',
                title='Kitchen Cleanliness After Using Biogas',
                x_label='Response Category',
                y_label='Respondents',
                orientation='h'
            )
            st.plotly_chart(fig_a2, use_container_width=True)
        
        fig_a3 = chart_gen.create_bar_chart(
            x_col='c3',
            agg_method='count',
            title='Kitchen Smoke Exposure After Using Biogas',
            x_label='Response Category',
            y_label='Respondents',
            orientation='h'
        )
        st.plotly_chart(fig_a3, use_container_width=True)

        st.subheader("Focused Comparison: Outcomes by Kitchen Adaptation")
        st.caption(
            "These charts compare response shares within each kitchen-adaptation group. They show association, not causation."
        )
        kitchen_comparison_cols = st.columns(2)
        with kitchen_comparison_cols[0]:
            fig_a2_comparison = create_kitchen_adaptation_comparison(
                data,
                "c2",
                "Kitchen Cleanliness by Kitchen Adaptation",
            )
            st.plotly_chart(fig_a2_comparison, use_container_width=True, key="A2_kitchen_adaptation")
        with kitchen_comparison_cols[1]:
            fig_a3_comparison = create_kitchen_adaptation_comparison(
                data,
                "c3",
                "Smoke Exposure by Kitchen Adaptation",
            )
            st.plotly_chart(fig_a3_comparison, use_container_width=True, key="A3_kitchen_adaptation")

        cleanliness_shares = kitchen_adaptation_outcome_share(data, "c2", ["Cleaner", "Much Cleaner"])
        smoke_shares = kitchen_adaptation_outcome_share(data, "c3", ["Never"])
        comparison_insights = []
        if "Yes" in cleanliness_shares and "No" in cleanliness_shares:
            comparison_insights.append(
                f"Improved kitchen cleanliness was reported by {cleanliness_shares['Yes']:.1f}% of households "
                f"with a new or renovated kitchen, compared with {cleanliness_shares['No']:.1f}% without one."
            )
        if "Yes" in smoke_shares and "No" in smoke_shares:
            comparison_insights.append(
                f"No kitchen-smoke exposure was reported by {smoke_shares['Yes']:.1f}% of households "
                f"with a new or renovated kitchen, compared with {smoke_shares['No']:.1f}% without one."
            )
        if comparison_insights:
            comparison_insights.append(
                "These differences are descriptive associations and should not be interpreted as proof that kitchen adaptation caused the outcomes."
            )
            render_summary_panel("Key Reading - Kitchen Adaptation", comparison_insights)

        fig_a4 = chart_gen.create_bar_chart(
            x_col='c4',
            agg_method='count',
            title='Respiratory Issues After Using Biogas',
            x_label='Response Category',
            y_label='Respondents',
            orientation='h'
        )
        st.plotly_chart(fig_a4, use_container_width=True)

        fig_a5 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c5_respiratory_before_biogas_adult_male',
                'c5_respiratory_before_biogas_adult_female',
                'c5_respiratory_before_biogas_children',
            ],
            y2=[
                'c6_respiratory_after_biogas_adult_male',
                'c6_respiratory_after_biogas_adult_female',
                'c6_respiratory_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Respiratory Issues',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a5, use_container_width=True)

        fig_a6 = chart_gen.create_bar_chart(
            x_col='c7',
            agg_method='count',
            title='Eye Irritation Issues After Using Biogas',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a6, use_container_width=True)

        fig_a7 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c8_eye_infection_before_biogas_adult_male',
                'c8_eye_infection_before_biogas_adult_female',
                'c8_eye_infection_before_biogas_children',
            ],
            y2=[
                'c9_eye_infection_after_biogas_adult_male',
                'c9_eye_infection_after_biogas_adult_female',
                'c9_eye_infection_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Eye Infection',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a7, use_container_width=True)

        fig_a8 = chart_gen.create_bar_chart(
            x_col='c10',
            agg_method='count',
            title='Family Members Having Gastro-intestinal Issues',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a8, use_container_width=True)

        fig_a9 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c11_digestive_before_biogas_adult_male',
                'c11_digestive_before_biogas_adult_female',
                'c11_digestive_before_biogas_children',
            ],
            y2=[
                'c12_digestive_after_biogas_adult_male',
                'c12_digestive_after_biogas_adult_female',
                'c12_digestive_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Gastro-intestinal Issues',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a9, use_container_width=True)

        fig_a10 = chart_gen.create_bar_chart(
            x_col='c13',
            agg_method='count',
            title='Family Members Having Mosquito Induced Diseases and Nuisance',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a10, use_container_width=True)

        fig_a11 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c14_mosquito_before_biogas_adult_male',
                'c14_mosquito_before_biogas_adult_female',
                'c14_mosquito_before_biogas_children',
            ],
            y2=[
                'c15_mosquito_after_biogas_adult_male',
                'c15_mosquito_after_biogas_adult_female',
                'c15_mosquito_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Mosquito Induced Diseases and Nuisance',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a11, use_container_width=True)

        fig_a12 = chart_gen.create_bar_chart(
            x_col='c16',
            agg_method='count',
            title='Family Members Having Fire/Burning Accidents',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a12, use_container_width=True)

        fig_a13 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c17_fire_before_biogas_adult_male',
                'c17_fire_before_biogas_adult_female',
                'c17_fire_before_biogas_children',
            ],
            y2=[
                'c18_fire_after_biogas_adult_male',
                'c18_fire_after_biogas_adult_female',
                'c18_fire_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Fire/Burning Accidents',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a13, use_container_width=True)

        fig_a14 = chart_gen.create_bar_chart(
            x_col='c19',
            agg_method='count',
            title='Family Members Having Psychological Problems',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a14, use_container_width=True)

        fig_a15 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)'],
            y1=[
                'c20_psychology_before_biogas_adult_male',
                'c20_psychology_before_biogas_adult_female',
                'c20_psychology_before_biogas_children',
            ],
            y2=[
                'c21_psychology_after_biogas_adult_male',
                'c21_psychology_after_biogas_adult_female',
                'c21_psychology_after_biogas_children',
            ],
            name1='Before Using Biogas',
            name2='After Using Biogas',
            title='Family Members Having Psychological Problems',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a15, use_container_width=True)

        fig_a16 = chart_gen.create_bar_chart(
            x_col='c22',
            agg_method='count',
            title='General Physical Condition of Family Members After Using Biogas',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a16, use_container_width=True)

        cols = st.columns(2)

        with cols[0]:
            fig_a17 = chart_gen.create_bar_chart(
                x_col='c23',
                agg_method='count',
                title='Visits to Doctor/Hospital Before Using Biogas',
                x_label='Visits per Year',
                y_label='Number',
                orientation='v'
            )
            st.plotly_chart(fig_a17, use_container_width=True)

        with cols[1]:
            fig_a18 = chart_gen.create_bar_chart(
                x_col='c24',
                agg_method='count',
                title='Visits to Doctor/Hospital After Using Biogas',
                x_label='Visits per Year',
                y_label='Number',
                orientation='v'
            )
            st.plotly_chart(fig_a18, use_container_width=True)

        fig_a19 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Adult Male', 'Adult Female', 'Children (0-18 Years Old)', 'None'],
            y1=[
                'c25_checkup_adult_male',
                'c25_checkup_adult_female',
                'c25_checkup_children',
                'c25_checkup_none',
            ],
            title='Visits to Doctor/Hospital in the Past Year',
            x_label='Group',
            y_label='Number'
        )
        st.plotly_chart(fig_a19, use_container_width=True)

        fig_a20 = chart_gen.create_bar_chart(
            x_col='c26',
            agg_method='count',
            title='Biogas Installation Improved House Cleanliness',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a20, use_container_width=True)

        fig_a21 = chart_gen.create_bar_chart(
            x_col='c27',
            agg_method='count',
            title='Biogas Installation Improved Shed Cleanliness',
            x_label='Answer',
            y_label='Number',
            orientation='h'
        )
        st.plotly_chart(fig_a21, use_container_width=True)

    # Section B Tab
    with tabs[2]:
        st.header("Section B: Impact on Socio-Economic Conditions")
        bus_section_summary(
            data,
            "Section B",
            "D. Dampak Sosial-Ekonomi",
            focus_terms=["waktu", "uang", "pendapatan", "pekerjaan", "ekonomi", "bioslurry", "bahan bakar"],
        )

        st.subheader("Income-Generating Activities After Biogas Adoption")
        cols = st.columns(2)

        with cols[0]:
            fig_b1 = create_hour_group_chart(
                data,
                'd1_farming',
                title='Time Spent for Income Generating Activity After Using Biogas (Farming)',
            )
            st.plotly_chart(fig_b1, use_container_width=True)

            fig_b1b = create_hour_group_chart(
                data,
                'd1_selling_activities',
                title='Time Spent for Income Generating Activity After Using Biogas (Selling Activities)',
            )
            st.plotly_chart(fig_b1b, use_container_width=True)

        with cols[1]:
            fig_b2 = create_hour_group_chart(
                data,
                'd1_livestock_farming',
                title='Time Spent for Income Generating Activity After Using Biogas (Livestock Farming)',
            )
            st.plotly_chart(fig_b2, use_container_width=True)

            fig_b2b = create_hour_group_chart(
                data,
                'd1_others',
                title='Time Spent for Income Generating Activity After Using Biogas (Other Activities)',
            )
            st.plotly_chart(fig_b2b, use_container_width=True)

        st.caption("Reported durations above 24 were interpreted as minutes and converted to hours; the source question does not state a reporting period.")

        st.subheader("Income, Savings, and Economic Benefits")
        fig_b3 = chart_gen.create_pie_chart(
            names_col='d1a',
            agg_method='count',
            title='Was There an Increase in Income After Using Biogas'
        )
        st.plotly_chart(fig_b3, use_container_width=True)

        cols = st.columns(2)

        with cols[0]:
            fig_b4 = create_currency_group_chart(
                data,
                'd2',
                title='Distribution of Increase in Income',
            )
            st.plotly_chart(fig_b4, use_container_width=True)

        with cols[1]:
            fig_b5 = create_currency_group_chart(
                data,
                'd3',
                title='Reported Income Decrease or No Change',
            )
            st.plotly_chart(fig_b5, use_container_width=True)

        fig_b6 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Savings', 'Healthcare', 'Venture Capital', 'Other Investments', 'Household Needs', 'Education of Family Members', 'Others'],
            y1=[
                'd4_savings_usage_savings',
                'd4_savings_usage_healthcare',
                'd4_savings_usage_venture',
                'd4_savings_usage_invest',
                'd4_savings_usage_household',
                'd4_savings_usage_education',
                'd4_savings_usage_others1',
            ],
            title='Use of Saved Income from Having Biogas',
            agg_method='sum',
            x_label='Answer',
            y_label='Number'
        )
        st.plotly_chart(fig_b6, use_container_width=True)
        st.caption("Respondents could select more than one use; totals may exceed the number of households.")

        fig_b7 = create_categorized_text_chart(
            data,
            'd4_savings_usage_others2',
            SAVINGS_OTHER_CATEGORIES,
            title='Other Uses',
        )
        st.plotly_chart(fig_b7, use_container_width=True)

        st.subheader("Time Savings and Daily Biogas Work")
        fig_b8 = create_activity_gender_average_chart(
            data,
            {
                "Collect Manure": {
                    "Adult Male": "d5_manure_collection_adult_male",
                    "Adult Female": "d5_manure_collection_adult_female",
                    "Others": "d5_manure_collection_others",
                },
                "Mix Manure and Water": {
                    "Adult Male": "d6_manure_mixing_adult_male",
                    "Adult Female": "d6_manure_mixing_adult_female",
                    "Others": "d6_manure_mixing_others",
                },
                "Blend Manure and Water": {
                    "Adult Male": "d7_manure_blending_adult_male",
                    "Adult Female": "d7_manure_blending_adult_female",
                    "Others": "d7_manure_blending_others",
                },
            },
            "Average Daily Time for Biogas Feedstock Preparation",
        )
        st.plotly_chart(fig_b8, use_container_width=True, key="B8_consolidated")
        st.caption("Averages include zero minutes for household groups that did not perform the activity; hover labels show active participant counts.")

        fig_b9 = chart_gen.create_pie_chart(
            names_col='d8',
            agg_method='count',
            title='Increase of Free Time After Using Biogas'
        )
        st.plotly_chart(fig_b9, use_container_width=True)

        fig_b10 = create_average_comparison_chart(
            data,
            columns_before=['d9_a1', 'd9_b1', 'd9_c1'],
            columns_after=['d9_a2', 'd9_b2', 'd9_c2'],
            group_labels=['Adult Male', 'Adult Female', 'Others (Children, Workers, etc.)'],
            title='Time Needed to Collect Fuel',
        )
        st.plotly_chart(fig_b10, use_container_width=True)
        st.caption("Average fuel-collection time includes zero minutes for household groups that did not collect fuel.")
        fuel_time_insights = paired_time_change_insights(
            data,
            ['d9_a1', 'd9_b1', 'd9_c1'],
            ['d9_a2', 'd9_b2', 'd9_c2'],
            ['Adult Male', 'Adult Female', 'Others'],
        )
        if fuel_time_insights:
            render_summary_panel("Key Reading - Fuel Collection Time", fuel_time_insights)

        fig_b11 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Child Education', 'Social Activities', 'Relaxation', 'Self Education', 'Working', 'Others'],
            y1=[
                'd10_time_usage_child_education',
                'd10_time_usage_social_activities',
                'd10_time_usage_relaxation',
                'd10_time_usage_self_education',
                'd10_time_usage_working',
                'd10_time_usage_others1',
            ],
            title='Use of Saved Time After Using Biogas',
            agg_method='sum',
            x_label='Activity',
            y_label='Number'
        )
        st.plotly_chart(fig_b11, use_container_width=True)
        st.caption("Respondents could select more than one saved-time activity; totals may exceed the number of households.")

        fig_b12 = create_categorized_text_chart(
            data,
            'd10_time_usage_others2',
            OTHER_ACTIVITY_CATEGORIES,
            title='Other Activities',
        )
        st.plotly_chart(fig_b12, use_container_width=True)

        fig_b13 = create_categorized_text_chart(
            data,
            'd11_a',
            WORK_ACTIVITY_CATEGORIES,
            title='If Saved Time was Used for Work, What Type of Work Do You Do?',
        )
        st.plotly_chart(fig_b13, use_container_width=True)

        fig_b14 = create_categorized_text_chart(
            data,
            'd11_b',
            NON_WORK_ACTIVITY_CATEGORIES,
            title='If Saved Time was Not Used for Work, What Activity Do You Do?',
        )
        st.plotly_chart(fig_b14, use_container_width=True)

        fig_b15 = create_categorized_text_chart(
            data,
            'd12_a',
            SOCIAL_ACTIVITY_CATEGORIES,
            title='If Saved Time was Used for Social Activities, What Type of Activity Do You Participate In?',
        )
        st.plotly_chart(fig_b15, use_container_width=True)

        fig_b16 = create_categorized_text_chart(
            data,
            'd12_b',
            NON_WORK_ACTIVITY_CATEGORIES,
            title='If Saved Time was Not Used for Social Activities, What Activity Do You Do?',
        )
        st.plotly_chart(fig_b16, use_container_width=True)

        st.subheader("Employment Generation")
        fig_b17 = chart_gen.create_pie_chart(
            names_col='d13_employment_generation',
            agg_method='count',
            title='Biogas Installation Generates Employment'
        )
        st.plotly_chart(fig_b17, use_container_width=True)

        fig_b18 = chart_gen.create_comparison_bar_chart(
            x_ticks=['Biogas System Maintenance', 'Biogas System Installation', 'Bio-slurry Production and Selling', 'Others'],
            y1=[
                'd13a_employment_generation_type_maintenance',
                'd13a_employment_generation_type_installation',
                'd13a_employment_generation_type_production',
                'd13a_employment_generation_type_others1',
            ],
            title='Generated Employment Types',
            agg_method='sum',
            x_label='Type',
            y_label='Number'
        )
        st.plotly_chart(fig_b18, use_container_width=True)
        st.caption("Employment types are multiple-response selections.")

        fig_b19 = chart_gen.create_bar_chart(
            x_col='d13a_employment_generation_type_others2',
            agg_method='count',
            title='Other Employment Types',
            x_label='Type',
            y_label='Number'
        )
        st.plotly_chart(fig_b19, use_container_width=True)

        fig_b20 = chart_gen.create_bar_chart(
            x_col='d13b_employment_generation_number',
            agg_method='count',
            title='Workers Hired for Biogas System Management',
            x_label='Number of Workers',
            y_label='Number'
        )
        st.plotly_chart(fig_b20, use_container_width=True)

        st.subheader("Economic Value of Bio-slurry")
        bioslurry_sales_sample = int(data["d14_sold_bioslurry"].notna().sum()) if "d14_sold_bioslurry" in data.columns else 0
        with st.expander("Bio-slurry sales details", expanded=True):
            fig_b21 = chart_gen.create_comparison_bar_chart(
                x_ticks=['Liquid', 'Solid'],
                y1=['d14_sold_bioslurry_liquid', 'd14_sold_bioslurry_solid'],
                title='Form of Bio-slurry Sold',
                agg_method='sum',
                x_label='Form',
                y_label='Respondents'
            )
            st.plotly_chart(fig_b21, use_container_width=True)

            bioslurry_cols = st.columns(2)
            with bioslurry_cols[0]:
                fig_b22 = chart_gen.create_bar_chart(
                    x_col='d15_liter_sold',
                    agg_method='count',
                    title='Monthly Liquid Bio-slurry Sales Volume',
                    x_label='Liters per Month',
                    y_label='Respondents'
                )
                st.plotly_chart(fig_b22, use_container_width=True)
                fig_b24 = chart_gen.create_bar_chart(
                    x_col='d16_price_per_liter',
                    agg_method='count',
                    title='Liquid Bio-slurry Selling Price',
                    x_label='Rupiah per Liter',
                    y_label='Respondents'
                )
                st.plotly_chart(fig_b24, use_container_width=True)

            with bioslurry_cols[1]:
                fig_b23 = chart_gen.create_bar_chart(
                    x_col='d15_kilogram_sold',
                    agg_method='count',
                    title='Monthly Solid Bio-slurry Sales Volume',
                    x_label='Kilograms per Month',
                    y_label='Respondents'
                )
                st.plotly_chart(fig_b23, use_container_width=True)
                fig_b25 = chart_gen.create_bar_chart(
                    x_col='d16_price_per_kilogram',
                    agg_method='count',
                    title='Solid Bio-slurry Selling Price',
                    x_label='Rupiah per Kilogram',
                    y_label='Respondents'
                )
                st.plotly_chart(fig_b25, use_container_width=True)

            fig_b26a = create_bioslurry_revenue_chart(data)
            st.plotly_chart(fig_b26a, use_container_width=True, key="B26a_bioslurry_revenue")

            fig_b26b = chart_gen.create_pie_chart(
                names_col='e19',
                agg_method='count',
                title='Bio-slurry Sold as Raw or Processed Product'
            )
            st.plotly_chart(fig_b26b, use_container_width=True, key="B26b_bioslurry_product_type")
            st.caption("Agricultural production outcomes associated with bio-slurry are presented in Section F: Agricultural Systems.")

        st.subheader("Financing of Biogas Installation")
        fig_b27 = chart_gen.create_bar_chart(
            x_col='d18',
            agg_method='count',
            title='Financing Source for Biogas System Installation',
            x_label='Source',
            y_label='Number'
        )
        st.plotly_chart(fig_b27, use_container_width=True)

        fig_b28 = create_ordered_category_chart(
            data,
            'd19',
            [
                'Rp0 (100% Grant Funded)',
                '1-1.000.000',
                '1.000.001-3.000.000',
                '3.000.001-5.000.000',
                '5.000.001-7.000.000',
                '7.000.001-9.000.000',
                '9.000.001-11.000.000',
                '>11.000.001',
            ],
            title='Total Cost of Biogas System Installation',
            x_label='Respondents',
        )
        st.plotly_chart(fig_b28, use_container_width=True)

        st.subheader('Financing Source from Grant Funds')
        
        fig_b29 = chart_gen.create_bar_chart(
            x_col='d20',
            agg_method='count',
            title='Source of Grant Funds',
            x_label='Source',
            y_label='Number'
        )
        st.plotly_chart(fig_b29, use_container_width=True)

        fig_b30 = create_categorized_text_chart(
            data,
            'd20a',
            GRANT_OTHER_CATEGORIES,
            title='Other Sources',
        )
        st.plotly_chart(fig_b30, use_container_width=True)

        st.subheader('Financing Source from Credits or Loans')

        fig_b31 = chart_gen.create_bar_chart(
            x_col='d21',
            agg_method='count',
            title='Source of Credits or Loans',
            x_label='Source',
            y_label='Number'
        )
        st.plotly_chart(fig_b31, use_container_width=True)

        fig_b32 = create_categorized_text_chart(
            data,
            'd21a',
            LOAN_OTHER_CATEGORIES,
            title='Other Sources',
        )
        st.plotly_chart(fig_b32, use_container_width=True, key='B32')

        fig_b33 = create_binned_count_chart(
            data,
            'd22',
            bins=[0, 12, 24, 36, 48, 60, np.inf],
            labels=["1-12 months", "13-24 months", "25-36 months", "37-48 months", "49-60 months", ">60 months"],
            title='Loan Period',
            x_label='Loan period',
        )
        st.plotly_chart(fig_b33, use_container_width=True)

        fig_b34 = chart_gen.create_bar_chart(
            x_col='d23',
            agg_method='count',
            title='Who Contacted the Creditor?',
            x_label='Answer',
            y_label='Number'
        )
        st.plotly_chart(fig_b34, use_container_width=True)

        fig_b35 = create_categorized_text_chart(
            data,
            'd23a',
            CREDITOR_CONTACT_OTHER_CATEGORIES,
            title='Other Answers',
        )
        st.plotly_chart(fig_b35, use_container_width=True)

        st.subheader('Independent Financing Source')

        fig_b36 = chart_gen.create_bar_chart(
            x_col='d24',
            agg_method='count',
            title='Who Decided to Finance Independently?',
            x_label='Answer',
            y_label='Number'
        )
        st.plotly_chart(fig_b36, use_container_width=True)

        fig_b37 = create_categorized_text_chart(
            data,
            'd24a',
            SELF_FINANCE_OTHER_CATEGORIES,
            title='Other Answers',
        )
        st.plotly_chart(fig_b37, use_container_width=True, key='B37')

        st.subheader("Household Economic Well-being and Workload")
        fig_b38 = chart_gen.create_pie_chart(
            names_col='d25',
            agg_method='count',
            title="Have Investment in Biogas System Improved Your Family's Economic Well-being?"
        )
        st.plotly_chart(fig_b38, use_container_width=True)

        st.subheader("Household Workload After Biogas Adoption")
        fig_b39 = create_activity_gender_average_chart(
            data,
            {
                "Cooking": {
                    "Adult Female": "d26_cooking_time_adult_female",
                    "Adult Male": "d26_cooking_time_adult_male",
                    "Children": "d26_cooking_time_children",
                },
                "Operate and Maintain Biogas": {
                    "Adult Female": "d27_operating_time_adult_female",
                    "Adult Male": "d27_operating_time_adult_male",
                    "Children": "d27_operating_time_children",
                },
            },
            "Average Daily Household Time by Activity and Group",
        )
        st.plotly_chart(fig_b39, use_container_width=True, key="B39_consolidated")

        cols = st.columns(2)

        with cols[0]:
            fig_b45 = chart_gen.create_pie_chart(
                names_col='d28',
                agg_method='count',
                title="Social and Economic Condition of Your Family After Using Biogas"
            )
            st.plotly_chart(fig_b45, use_container_width=True)

        with cols[1]:
            fig_b46 = chart_gen.create_pie_chart(
                names_col='d29',
                agg_method='count',
                title='Change of Cooking Process and Workload Before and After Using Biogas'
            )
            st.plotly_chart(fig_b46, use_container_width=True)

        st.subheader("Household Economic and Education Profile")
        profile_cols = st.columns(2)
        with profile_cols[0]:
            fig_b47 = create_ordered_category_chart(
                data,
                'monthly_income',
                ['<Rp1.500.000', 'Rp1.500.000 - Rp2.500.000', 'Rp2.500.000 - Rp3.500.000', '>Rp3.500.000'],
                title='Reported Monthly Household Income',
                x_label='Respondents',
            )
            st.plotly_chart(fig_b47, use_container_width=True, key='B47')

        with profile_cols[1]:
            fig_b48 = create_ordered_category_chart(
                data,
                'education',
                ['No Formal Schooling', 'Elementary School', 'Junior High School', 'Senior High School', 'Vocational High School', 'Diploma/Bachelor Degree', 'Master Degree Or Higher'],
                title='Respondent Education Level (Household Proxy)',
                x_label='Respondents',
            )
            st.plotly_chart(fig_b48, use_container_width=True, key='B48')
        st.caption("The survey records the respondent's education level, not the education of every household member.")
        st.info("A direct variable for the perceived economic value of livestock after biodigester installation is not available in the current BUS dataset.")

        fig_b49 = create_ordered_category_chart(
            data,
            'a19_maintenance_cost_rp',
            ['Rp0', '< Rp 200,000', 'Rp 200,001 - Rp 500,000', '> Rp 500,001'],
            title='Reported Biodigester Maintenance Expenditure',
            x_label='Respondents',
        )
        st.plotly_chart(fig_b49, use_container_width=True, key='B49_maintenance_cost')

        st.subheader('Reported Fuel Expenditure and Unit Costs')
        st.caption(
            "Only fuel types with at least five valid expenditure records are shown. The shortened source fields do not encode the reporting period, so confirm the period before treating these values as annual TOR expenditure. One LPG record yielding an implausible Rp1/kg unit cost is excluded from the derived unit-cost chart."
        )
        tabs_B = st.tabs(['Firewood', 'LPG'])

        with tabs_B[0]:
            fig_b51 = chart_gen.create_histogram(
                column='B5-a2_firewood_price',
                bins=8,
                title='Reported Firewood Expenditure',
                x_label='Reported Expenditure (Rp)',
                y_label='Respondents'
            )
            st.plotly_chart(fig_b51, use_container_width=True)

            fig_b52 = chart_gen.create_histogram(
                column='B5-a2_firewood_price_per_kg',
                bins=8,
                title='Derived Firewood Unit Cost',
                x_label='Rupiah per Kilogram',
                y_label='Respondents'
            )
            st.plotly_chart(fig_b52, use_container_width=True, key='B52')

        with tabs_B[1]:
            fig_b53 = chart_gen.create_histogram(
                column='B5-b2_LPG_price',
                bins=8,
                title='Reported LPG Expenditure',
                x_label='Reported Expenditure (Rp)',
                y_label='Respondents'
            )
            st.plotly_chart(fig_b53, use_container_width=True)

            fig_b54 = chart_gen.create_histogram(
                column='B5-b2_LPG_price_per_kg',
                bins=8,
                title='Derived LPG Unit Cost',
                x_label='Rupiah per Kilogram',
                y_label='Respondents'
            )
            st.plotly_chart(fig_b54, use_container_width=True, key='B54')

    # Section C Tab
    with tabs[3]:
        st.header("Section C: Technical Performance of the Biogas Plants")
        bus_section_summary(
            data,
            "Section C",
            "A. Performa Teknis Sistem Biogas",
            focus_terms=["instalasi", "berfungsi", "operasi", "kerusakan", "masalah", "instruksi", "biogas"],
        )

        section_c_data = data.copy()
        if "a9_operable_biogas" in section_c_data.columns:
            section_c_data["a9_operable_biogas"] = section_c_data["a9_operable_biogas"].replace(
                {1: "Yes", 1.0: "Yes", "1": "Yes", "1.0": "Yes", "Functioning Well": "Yes"}
            )
        for column in ["a10_time_since_inoperable", "a11_reason_for_inoperation", "a11_reason_for_inoperation_others"]:
            if column in section_c_data.columns:
                section_c_data[column] = section_c_data[column].replace(
                    {0: np.nan, 0.0: np.nan, 1: np.nan, 1.0: np.nan, "0": np.nan, "0.0": np.nan, "1": np.nan, "1.0": np.nan}
                )
        section_c_chart_gen = ChartGenerator(section_c_data)

        st.subheader("Plant Profile")
        profile_cols = st.columns(2)
        with profile_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_pie_chart(
                    names_col="type_digester",
                    agg_method="count",
                    title="Biogas Digester Type",
                ),
                use_container_width=True,
                key="C_profile_type",
            )
        with profile_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="size_digester",
                    agg_method="count",
                    title="Biogas Digester Size",
                    x_label="Digester size",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_profile_size",
            )
        st.plotly_chart(
            section_c_chart_gen.create_bar_chart(
                x_col="year_completion_clean",
                agg_method="count",
                title="Biogas Digester Completion Year",
                x_label="Completion year",
                y_label="Respondents",
            ),
            use_container_width=True,
            key="C_profile_year",
        )

        st.subheader("Operational Performance")
        st.caption(
            "Operational performance is based on the current functioning status and reported time since failure. "
            "The workbook does not contain an exact annual count of operating days, so that TOR indicator is not inferred."
        )
        operational_cols = st.columns(2)
        with operational_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_pie_chart(
                    names_col="a9_operable_biogas",
                    agg_method="count",
                    title="Current Operating Status of the Biogas System",
                ),
                use_container_width=True,
                key="C_operating_status",
            )
        with operational_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="a10_time_since_inoperable",
                    agg_method="count",
                    title="Time Since the Biogas System Stopped Operating",
                    x_label="Time since failure",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_inoperative_duration",
            )
        st.plotly_chart(
            section_c_chart_gen.create_bar_chart(
                x_col="a11_reason_for_inoperation",
                agg_method="count",
                title="Main Reasons for Biogas System Inoperation",
                x_label="Respondents",
                y_label="Reason",
                orientation="h",
            ),
            use_container_width=True,
            key="C_inoperation_reason",
        )

        st.subheader("Problems Encountered")
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a12_technical_problems_stove", "a12_technical_problems_lamp",
                    "a12_technical_problems_gas_tap", "a12_technical_problems_manometer",
                    "a12_technical_problems_main_gas_pipe", "a12_technical_problems_main_gas_valve",
                    "a12_technical_problems_turret", "a12_technical_problems_mixer",
                    "a12_technical_problems_inlet", "a12_technical_problems_biogas_reactor",
                    "a12_technical_problems_gas_pipeline", "a12_technical_problems_water_drain",
                    "a12_technical_problems_water_pipe", "a12_technical_problems_bioslurry_outlet",
                ],
                option_names=[
                    "Stove", "Lamp", "Gas Tap", "Manometer", "Main Gas Pipe", "Main Gas Valve",
                    "Turret", "Mixer", "Inlet", "Biogas Reactor", "Gas Pipeline", "Water Drain",
                    "Water Pipe", "Bio-slurry Outlet",
                ],
                title="Technical Problems by Component",
                x_label="Respondents reporting the problem",
                y_label="Component",
            ),
            use_container_width=True,
            key="C_technical_problems",
        )
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a13_non-technical_problems_conflict", "a13_non-technical_problems_lack_of_support",
                    "a13_non-technical_problems_accessibility", "a13_non-technical_problems_none",
                    "a13_non-technical_problems_others1",
                ],
                option_names=[
                    "Family or Community Conflict", "Limited Government or CPO Support",
                    "Limited Access to Information or Training", "No Non-Technical Problems", "Other",
                ],
                title="Non-Technical Problems Reported by Users",
                x_label="Respondents reporting the problem",
                y_label="Problem",
            ),
            use_container_width=True,
            key="C_nontechnical_problems",
        )

        st.subheader("Operation and Maintenance Instructions")
        instruction_cols = st.columns(2)
        with instruction_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="a14_clear_instructions",
                    agg_method="count",
                    title="Clarity of Operation and Maintenance Instructions",
                    x_label="Respondents",
                    y_label="Assessment",
                    orientation="h",
                ),
                use_container_width=True,
                key="C_instruction_clarity",
            )
        with instruction_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_pie_chart(
                    names_col="a15_instruction_type",
                    agg_method="count",
                    title="Type of Instruction Received",
                ),
                use_container_width=True,
                key="C_instruction_type",
            )
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a16_instruction_provider_cpo", "a16_instruction_provider_biru",
                    "a16_instruction_provider_cooperative", "a16_instruction_provider_others1",
                ],
                option_names=["CPO or Facilitator", "BIRU Staff", "Cooperative Employee", "Other"],
                title="Providers of Operation and Maintenance Instruction",
                x_label="Respondents",
                y_label="Instruction provider",
            ),
            use_container_width=True,
            key="C_instruction_provider",
        )
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a17_instruction_receiver_adult_male", "a17_instruction_receiver_adult_female",
                    "a17_instruction_receiver_others1",
                ],
                option_names=["Adult Male", "Adult Female", "Other Household Member"],
                title="Household Members Receiving Operation and Maintenance Instruction",
                x_label="Respondents",
                y_label="Participant",
            ),
            use_container_width=True,
            key="C_instruction_receiver",
        )

        st.subheader("Maintenance")
        maintenance_cols = st.columns(2)
        with maintenance_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="a18_maintenance_frequency",
                    agg_method="count",
                    title="Frequency of Biogas Maintenance or Repair",
                    x_label="Frequency",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_maintenance_frequency",
            )
        with maintenance_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="a19_maintenance_cost_rp",
                    agg_method="count",
                    title="Annual Biogas Maintenance Cost",
                    x_label="Annual cost category",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_maintenance_cost",
            )

        st.subheader("Operation and Maintenance Knowledge and Practice")
        st.caption(
            "Knowledge indicates awareness of the correct procedure. Reported practice indicates that the activity is performed "
            "at least occasionally; it does not imply that every procedure must be performed daily."
        )
        st.plotly_chart(
            create_section_c_knowledge_practice_chart(section_c_data),
            use_container_width=True,
            key="C_knowledge_practice",
        )
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a35_biogas_maintenance_responsibility_adult_male",
                    "a35_biogas_maintenance_responsibility_adult_female",
                    "a35_biogas_maintenance_responsibility_children",
                    "a35_biogas_maintenance_responsibility_workers",
                ],
                option_names=["Adult Male", "Adult Female", "Children", "Additional Workers"],
                title="Responsibility for Biogas Operation and Maintenance",
                x_label="Respondents",
                y_label="Responsible household group",
            ),
            use_container_width=True,
            key="C_maintenance_responsibility",
        )

        st.subheader("Safety Awareness and Practice")
        safety_cols = st.columns(2)
        with safety_cols[0]:
            st.plotly_chart(
                create_ordered_category_chart(
                    section_c_data,
                    "a36",
                    ["Fully Understand", "Understand", "Partly Understand", "Limited Understanding", "Do Not Understand"],
                    "Understanding of Biogas Safety Measures",
                ),
                use_container_width=True,
                key="C_safety_understanding",
            )
        with safety_cols[1]:
            st.plotly_chart(
                create_ordered_category_chart(
                    section_c_data,
                    "a38",
                    ["Always", "Often", "Sometimes", "Rarely", "Never"],
                    "Frequency of Applying Biogas Safety Measures",
                ),
                use_container_width=True,
                key="C_safety_frequency",
            )
        st.plotly_chart(
            section_c_chart_gen.create_selection_summary_chart(
                columns=[
                    "a37_knowledge_source_CPO", "a37_knowledge_source_training",
                    "a37_knowledge_source_relatives", "a37_knowledge_source_others1",
                ],
                option_names=["CPO", "Training", "Friends or Family", "Other"],
                title="Sources of Knowledge About Biogas Safety Measures",
                x_label="Respondents",
                y_label="Knowledge source",
            ),
            use_container_width=True,
            key="C_safety_source",
        )

        st.subheader("Promotion and Recommendation")
        promotion_cols = st.columns(2)
        with promotion_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_pie_chart(
                    names_col="a39",
                    agg_method="count",
                    title="Promoted the Benefits of Biogas to Others",
                ),
                use_container_width=True,
                key="C_promotion_status",
            )
        with promotion_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_selection_summary_chart(
                    columns=[
                        "a40_promotion_neighbors", "a40_promotion_relatives",
                        "a40_promotion_community", "a40_promotion_others1",
                    ],
                    option_names=["Neighbors", "Friends or Family", "Local Community", "Other"],
                    title="Audiences Reached by Biogas Promotion",
                    x_label="Respondents who promoted biogas",
                    y_label="Audience",
                ),
                use_container_width=True,
                key="C_promotion_audience",
            )
        st.plotly_chart(
            create_recommendation_score_chart(section_c_data),
            use_container_width=True,
            key="C_recommendation_score",
        )

        st.subheader("Daily Biogas Operation Inputs")
        daily_cols = st.columns(2)
        with daily_cols[0]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="b7",
                    agg_method="count",
                    title="Daily Manure Input for Biogas Production",
                    x_label="Manure input per day",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_daily_manure",
            )
        with daily_cols[1]:
            st.plotly_chart(
                section_c_chart_gen.create_bar_chart(
                    x_col="b8",
                    agg_method="count",
                    title="Average Daily Biogas Stove Burning Duration",
                    x_label="Burning duration per day",
                    y_label="Respondents",
                ),
                use_container_width=True,
                key="C_daily_burning_hours",
            )

        with st.expander("Installation Participation Context", expanded=False):
            st.caption("These indicators provide contextual information on household participation but are not primary technical-performance measures.")
            participation_charts = [
                (
                    ["a5_biogas_installation_proposer_adult_male", "a5_biogas_installation_proposer_adult_female", "a5_biogas_installation_proposer_cooperative", "a5_biogas_installation_proposer_others"],
                    ["Adult Male", "Adult Female", "Cooperative", "Other"],
                    "Who Proposed the Biogas Installation?",
                    "C_installation_proposer",
                ),
                (
                    ["a6_agreed_to_installation_adult_male", "a6_agreed_to_installation_adult_female", "a6_agreed_to_installation_others1"],
                    ["Adult Male", "Adult Female", "Other"],
                    "Who Agreed to the Biogas Installation?",
                    "C_installation_agreement",
                ),
                (
                    ["a7_installation_location_adult_male", "a7_installation_location_adult_female", "a7_installation_location_CPO", "a7_installation_location_others1"],
                    ["Adult Male", "Adult Female", "CPO or Facilitator", "Other"],
                    "Who Determined the Digester Location?",
                    "C_installation_location",
                ),
                (
                    ["a8_installation_supervisor_adult_male", "a8_installation_supervisor_adult_female", "a8_installation_supervisor_CPO", "a8_installation_supervisor_others1"],
                    ["Adult Male", "Adult Female", "CPO or Facilitator", "Other"],
                    "Who Supervised the Biogas Installation?",
                    "C_installation_supervisor",
                ),
            ]
            for columns, labels, title, key in participation_charts:
                st.plotly_chart(
                    section_c_chart_gen.create_selection_summary_chart(
                        columns=columns,
                        option_names=labels,
                        title=title,
                        x_label="Respondents",
                        y_label="Participant",
                    ),
                    use_container_width=True,
                    key=key,
                )


    # Section D Tab
    with tabs[4]:
        st.header("Section D: User Satisfaction and Perception")
        bus_section_summary(
            data,
            "Section D",
            "G. Kepuasan dan Persepsi Pengguna",
            focus_terms=["puas", "manfaat", "perbaikan", "layanan", "rekomendasi"],
        )

        section_d_data = data.copy()
        section_d_chart_gen = ChartGenerator(section_d_data)

        st.subheader("Provincial Satisfaction Profile")
        st.caption(
            "Each line represents a province. Solid lines indicate N >= 5; dotted lines marked with an asterisk indicate smaller samples."
        )
        province_order = sorted(section_d_data["province"].dropna().astype(str).unique()) if "province" in section_d_data.columns else []
        render_provincial_satisfaction_spider(
            section_d_data,
            ["Very Satisfied"],
            "Highly Satisfied Profile Across Provinces",
            "BUS_section_d_high_satisfaction_spider",
            province_order,
        )
        st.space("medium")
        render_provincial_satisfaction_spider(
            section_d_data,
            ["Dissatisfied", "Very Dissatisfied"],
            "Dissatisfied Profile Across Provinces",
            "BUS_section_d_dissatisfaction_spider",
            province_order,
        )

        st.subheader("Satisfaction Overview")
        st.caption(
            "Percentages are calculated independently for each satisfaction dimension using its valid responses."
        )
        st.plotly_chart(
            create_satisfaction_likert_chart(section_d_data),
            use_container_width=True,
            key="D_satisfaction_likert",
        )

        st.subheader("Equipment Reliability")
        equipment_cols = st.columns(2)
        with equipment_cols[0]:
            st.plotly_chart(
                section_d_chart_gen.create_pie_chart(
                    names_col="g6",
                    agg_method="count",
                    title="Equipment Replaced in the Last 12 Months",
                ),
                use_container_width=True,
                key="D_equipment_replaced",
            )
        with equipment_cols[1]:
            st.plotly_chart(
                section_d_chart_gen.create_component_text_summary_chart(
                    column="g6a",
                    component_keywords={
                        "Stove": ["kompor", "stove"],
                        "Igniter": ["igniter", "pemantik"],
                        "Gas Tap / Valve": ["kran", "keran", "tap", "valve", "krangas"],
                        "Hose / Pipe": ["selang", "slang", "pipa", "pipe", "hose"],
                        "Manometer / Meter": ["meter", "meteran", "manometer"],
                        "Mixer": ["mixer"],
                        "Reactor / Digester": ["reaktor", "digester", "biodigester"],
                        "Total System Repair": ["perbaikan total", "total"],
                    },
                    title="Replaced Equipment by Component",
                    x_label="Respondents mentioning component",
                    y_label="Component",
                ),
                use_container_width=True,
                key="D_replaced_components",
            )
        replacement_n = int(section_d_data["g6a"].notna().sum()) if "g6a" in section_d_data.columns else 0
        st.caption(f"Component results are conditional on respondents reporting equipment replacement (N={replacement_n:,}).")

        st.subheader("CPO Service and Damage Response")
        dissatisfaction_columns = [
            "g8_unfriendly_service", "g8_inadequate_training", "g8_difficult_to_contact",
            "g8_difficult_to_operate", "g8_non-routine_supervision", "g8_slow_response",
            "g8_inadequate_quality", "g8_others1",
        ]
        dissatisfaction_labels = [
            "Unfriendly Service", "Inadequate or Missing Training", "Difficult to Contact",
            "System Difficult to Operate After Construction", "Irregular Monitoring or Supervision",
            "Slow Repair Response", "Service Quality Did Not Justify Cost", "Other",
        ]
        dissatisfaction_n = int(section_d_data["g8"].notna().sum()) if "g8" in section_d_data.columns else 0
        st.caption(
            f"Reasons for dissatisfaction are a conditional multiple-response question (N={dissatisfaction_n:,})."
        )
        st.plotly_chart(
            section_d_chart_gen.create_selection_summary_chart(
                columns=dissatisfaction_columns,
                option_names=dissatisfaction_labels,
                title="Reasons for Dissatisfaction with CPO Service",
                x_label="Respondents",
                y_label="Reason",
            ),
            use_container_width=True,
            key="D_cpo_dissatisfaction_reasons",
        )
        st.plotly_chart(
            section_d_chart_gen.create_selection_summary_chart(
                columns=["g9_cpo", "g9_self_repair", "g9_leave_it_be", "g9_others1"],
                option_names=["Contact CPO or Facilitator", "Repair Independently", "Leave It Unrepaired", "Other"],
                title="Response When the Biogas System Is Damaged",
                x_label="Respondents",
                y_label="Response",
            ),
            use_container_width=True,
            key="D_damage_response",
        )

        st.subheader("Communication, Complaints, and Feedback")
        communication_cols = st.columns(2)
        with communication_cols[0]:
            st.plotly_chart(
                section_d_chart_gen.create_pie_chart(
                    names_col="d17",
                    agg_method="count",
                    title="IDBP Hotline Sticker Availability",
                ),
                use_container_width=True,
                key="D_hotline_sticker",
            )
            st.plotly_chart(
                section_d_chart_gen.create_bar_chart(
                    x_col="g10",
                    agg_method="count",
                    title="Person Responsible for Contacting the CPO",
                    x_label="Respondents",
                    y_label="Responsible person",
                    orientation="h",
                ),
                use_container_width=True,
                key="D_cpo_contact_person",
            )
        with communication_cols[1]:
            st.plotly_chart(
                section_d_chart_gen.create_pie_chart(
                    names_col="g13",
                    agg_method="count",
                    title="Service Provider Responsiveness to User Feedback",
                ),
                use_container_width=True,
                key="D_feedback_response",
            )
            st.plotly_chart(
                section_d_chart_gen.create_bar_chart(
                    x_col="g11",
                    agg_method="count",
                    title="Communication Channel Used to Contact the CPO",
                    x_label="Respondents",
                    y_label="Communication channel",
                    orientation="h",
                ),
                use_container_width=True,
                key="D_communication_channel",
            )

        improvement_categories = {
            "Routine Monitoring and Follow-up": ["kontrol", "monitor", "pemantauan", "kunjung", "pengecekan", "cek lokasi"],
            "Repair and Spare-Part Support": ["perbaikan", "rusak", "sparepart", "spare part", "suku cadang", "filter", "pengurasan"],
            "Training and User Maintenance": ["pelatihan", "training", "perawatan oleh user", "edukasi", "pemahaman"],
            "Subsidy or Financial Support": ["subsidi", "bantuan", "biaya", "dana"],
            "System Quality or Capacity": ["kualitas", "kapasitas", "teknologi", "pengembangan", "desain"],
        }
        st.plotly_chart(
            create_categorized_text_chart(
                section_d_data,
                "g12",
                improvement_categories,
                "Suggestions for Improving the Biogas Program and Service",
                x_label="Open-ended responses",
                y_label="Suggestion theme",
            ),
            use_container_width=True,
            key="D_improvement_suggestions",
        )

        with st.expander("Additional Complaint and Contact Responses", expanded=False):
            contact_categories = {
                "Group Leader or Community Contact": ["ketua kelompok", "kelompok", "rekan", "tetangga", "teman"],
                "Household or Family Member": ["anak", "cucu", "pemilik rumah", "keluarga"],
                "Self-Repair or Local Technician": ["sendiri", "tukang", "perbaiki", "diperbaiki"],
                "No Damage or Contact Needed": ["tidak pernah", "tidak ada kerusakan", "tidak menghubungi", "tidak dilaporkan"],
            }
            st.plotly_chart(
                create_categorized_text_chart(
                    section_d_data,
                    "g10a",
                    contact_categories,
                    "Other People Involved in Contacting or Reporting Damage",
                    x_label="Open-ended responses",
                    y_label="Response theme",
                ),
                use_container_width=True,
                key="D_other_contact_person",
            )
            st.plotly_chart(
                create_categorized_text_chart(
                    section_d_data,
                    "g11a",
                    contact_categories,
                    "Other Communication and Assistance Channels",
                    x_label="Open-ended responses",
                    y_label="Response theme",
                ),
                use_container_width=True,
                key="D_other_contact_channel",
            )

        st.subheader("Perceived Benefits and Adoption Drivers")
        st.plotly_chart(
            section_d_chart_gen.create_selection_summary_chart(
                columns=[
                    "g14_expenditure_reduction", "g14_easier_access", "g14_reliable_supply",
                    "g14_faster_cooking", "g14_safer", "g14_saves_time", "g14_shed_hygiene",
                    "g14_fertilizer", "g14_cleaner_kitchen", "g14_credit_available",
                    "g14_subsidies_available", "g14_others1",
                ],
                option_names=[
                    "Reduced Household Expenditure", "Easier Energy Access", "Reliable Energy Supply",
                    "Faster Cooking", "Safer Cooking", "Time and Effort Savings", "Cleaner Livestock Shed",
                    "Bio-slurry Used as Fertilizer", "Cleaner Smoke-Free Kitchen", "Credit Scheme Available",
                    "Subsidy Available", "Other",
                ],
                title="Benefits of Having a Biogas Installation",
                x_label="Respondents selecting benefit",
                y_label="Benefit",
            ),
            use_container_width=True,
            key="D_biogas_benefits",
        )
        adoption_cols = st.columns(2)
        with adoption_cols[0]:
            st.plotly_chart(
                section_d_chart_gen.create_bar_chart(
                    x_col="g15",
                    agg_method="count",
                    title="Main Reason for Installing Biogas",
                    x_label="Respondents",
                    y_label="Reason",
                    orientation="h",
                ),
                use_container_width=True,
                key="D_installation_reason",
            )
        with adoption_cols[1]:
            st.plotly_chart(
                section_d_chart_gen.create_bar_chart(
                    x_col="g16",
                    agg_method="count",
                    title="Information Source Before Becoming a Biogas User",
                    x_label="Respondents",
                    y_label="Information source",
                    orientation="h",
                ),
                use_container_width=True,
                key="D_information_source",
            )

        with st.expander("Additional Adoption Context", expanded=False):
            st.plotly_chart(
                section_d_chart_gen.create_selection_summary_chart(
                    columns=["g1_adult_male", "g1_adult_female", "g1_children", "g1_none"],
                    option_names=["Adult Male", "Adult Female", "Children", "No Household Beneficiary"],
                    title="Household Members Benefiting from Biogas",
                    x_label="Respondents",
                    y_label="Household group",
                ),
                use_container_width=True,
                key="D_household_beneficiaries",
            )
            st.caption(
                "Detailed operation and maintenance instruction indicators are reported in Section C. "
                "The chart below is retained as a concise satisfaction-context indicator required by the TOR."
            )
            st.plotly_chart(
                section_d_chart_gen.create_bar_chart(
                    x_col="a14_clear_instructions",
                    agg_method="count",
                    title="Clarity of Operation and Maintenance Instructions",
                    x_label="Respondents",
                    y_label="Assessment",
                    orientation="h",
                ),
                use_container_width=True,
                key="D_instruction_clarity_context",
            )

    # Section E Tab
    with tabs[5]:
        st.header("Section E: Gender Impacts")
        bus_section_summary(
            data,
            "Section E",
            "F. Dampak Terhadap Gender",
            focus_terms=["perempuan", "anak", "beban", "keuangan", "pemberdayaan"],
        )

        section_e_data = data.copy()
        section_e_chart_gen = ChartGenerator(section_e_data)

        st.subheader("Gender Outcomes")
        outcome_cols = st.columns(2)
        with outcome_cols[0]:
            st.plotly_chart(
                create_ordered_category_chart(
                    section_e_data,
                    "f1",
                    [
                        "No Benefits", "Limited Benefits", "Moderately Significant Daily Benefits",
                        "Major Benefits For Daily Life", "Very Significant Benefits",
                        "Transformative Daily Benefits",
                    ],
                    "Benefits for Women and Children",
                ),
                use_container_width=True,
                key="E_women_children_benefits",
            )
            st.plotly_chart(
                section_e_chart_gen.create_bar_chart(
                    x_col="f3",
                    agg_method="count",
                    title="Management of Savings or Additional Household Income",
                    x_label="Respondents",
                    y_label="Financial manager",
                    orientation="h",
                ),
                use_container_width=True,
                key="E_financial_management",
            )
        with outcome_cols[1]:
            st.plotly_chart(
                create_ordered_category_chart(
                    section_e_data,
                    "f2",
                    ["Significantly Reduced", "Reduced", "No Change", "Increased", "Significantly Increased"],
                    "Women's Household Workload Change",
                ),
                use_container_width=True,
                key="E_women_workload",
            )
            st.plotly_chart(
                create_ordered_category_chart(
                    section_e_data,
                    "f4",
                    ["Strongly Disagree", "Disagree", "Neutral/Do Not Know", "Agree", "Strongly Agree"],
                    "Biogas and Women's Empowerment",
                ),
                use_container_width=True,
                key="E_women_empowerment",
            )

        st.subheader("Decision-Making and Installation Participation")
        st.caption(
            "Questions allow multiple participants; percentages therefore do not sum to 100% within a decision stage."
        )
        st.plotly_chart(
            create_gender_decision_participation_chart(section_e_data),
            use_container_width=True,
            key="E_decision_participation",
        )

        st.subheader("Division of Labour and Time Use")
        st.caption(
            "Fuel-collection averages include zero-minute records to represent the distribution of responsibility across all surveyed households."
        )
        st.plotly_chart(
            create_average_comparison_chart(
                section_e_data,
                ["d9_a1", "d9_b1", "d9_c1"],
                ["d9_a2", "d9_b2", "d9_c2"],
                ["Adult Male", "Adult Female", "Children / Other Household Members"],
                "Average Daily Fuel-Collection Time Before and After Biogas Adoption",
                y_label="Average minutes per day",
            ),
            use_container_width=True,
            key="E_fuel_collection_before_after",
        )
        st.caption(
            "Task-time bars use the median among household members who reported spending time on the activity. "
            "Hover information shows both the number and percentage of active households."
        )
        st.plotly_chart(
            create_gender_task_time_chart(section_e_data),
            use_container_width=True,
            key="E_gender_task_time",
        )

        st.subheader("Training and Technical Participation")
        training_cols = st.columns(2)
        with training_cols[0]:
            st.plotly_chart(
                section_e_chart_gen.create_selection_summary_chart(
                    columns=[
                        "a17_instruction_receiver_adult_male",
                        "a17_instruction_receiver_adult_female",
                        "a17_instruction_receiver_others1",
                    ],
                    option_names=["Adult Male", "Adult Female", "Other Household Member"],
                    title="Household Members Receiving O&M Training or Instruction",
                    x_label="Respondents",
                    y_label="Training participant",
                ),
                use_container_width=True,
                key="E_training_participants",
            )
        with training_cols[1]:
            st.plotly_chart(
                section_e_chart_gen.create_selection_summary_chart(
                    columns=[
                        "a35_biogas_maintenance_responsibility_adult_male",
                        "a35_biogas_maintenance_responsibility_adult_female",
                        "a35_biogas_maintenance_responsibility_children",
                        "a35_biogas_maintenance_responsibility_workers",
                    ],
                    option_names=["Adult Male", "Adult Female", "Children", "Additional Workers"],
                    title="Responsibility for Biogas Operation and Maintenance",
                    x_label="Respondents",
                    y_label="Responsible household group",
                ),
                use_container_width=True,
                key="E_maintenance_responsibility",
            )
        st.caption(
            "The survey records who received training and who performs O&M, but it does not provide a direct gender-disaggregated technical-knowledge score."
        )

        st.subheader("Saved Time and Economic Participation")
        saved_time_cols = st.columns(2)
        with saved_time_cols[0]:
            st.plotly_chart(
                section_e_chart_gen.create_pie_chart(
                    names_col="d8",
                    agg_method="count",
                    title="Households Reporting More Free Time After Biogas Adoption",
                ),
                use_container_width=True,
                key="E_more_free_time",
            )
        with saved_time_cols[1]:
            st.plotly_chart(
                section_e_chart_gen.create_bar_chart(
                    x_col="d13_employment_generation",
                    agg_method="count",
                    title="Employment Opportunities Generated by Biogas Installation",
                    x_label="Respondents",
                    y_label="Employment outcome",
                    orientation="h",
                ),
                use_container_width=True,
                key="E_employment_generation",
            )

        saved_time_n = int(section_e_data["d10_time_usage"].notna().sum()) if "d10_time_usage" in section_e_data.columns else 0
        st.caption(
            f"Uses of saved time are a conditional multiple-response question (N={saved_time_n:,}). "
            "The questionnaire records household use, not the gender of the individual using the saved time."
        )
        st.plotly_chart(
            section_e_chart_gen.create_selection_summary_chart(
                columns=[
                    "d10_time_usage_child_education", "d10_time_usage_social_activities",
                    "d10_time_usage_relaxation", "d10_time_usage_self_education",
                    "d10_time_usage_working", "d10_time_usage_others1",
                ],
                option_names=[
                    "Supporting Children's Education", "Social Activities", "Rest and Recreation",
                    "Personal Education", "Productive Work", "Other",
                ],
                title="How Households Use Time Saved Through Biogas",
                x_label="Respondents selecting use",
                y_label="Use of saved time",
            ),
            use_container_width=True,
            key="E_saved_time_use",
        )

        st.info(
            "Gender-specific health outcomes and direct technical-knowledge scores are not available in the current BUS variables. "
            "The dashboard therefore reports benefits, workload, training participation, responsibility, and time allocation without inferring unsupported gender differences."
        )

    # Section F Tab
    with tabs[6]:
        st.header("Section F: Agricultural Systems")
        bus_section_summary(
            data,
            "Section F",
            "E. Dampak Terhadap Agrikultur",
            focus_terms=["ternak", "kotoran", "slurry", "pupuk", "lahan", "pertanian", "produksi"],
        )
        render_bus_section_f(data)



    # Section G Tab
    with tabs[7]:
        st.header("Section G: Energy, Emission Reduction and Sustainable Development Impacts")
        bus_section_summary(
            data,
            "Section G",
            "B. Energi, Pengurangan Emisi, dan Dampak Terhadap Lingkungan",
            focus_terms=["biogas", "bahan bakar", "kayu", "lpg", "lingkungan"],
        )

        render_bus_section_g(data)



    with tabs[8]:
        st.header("Exploration")
        st.caption(f"Data preview for the current selection ({len(data):,} respondents).")
        preview_cols = [
            col for col in ["province", "district", "subdistrict", "village", "gender", "age", "vpa", "year_completion_clean", "status_biogas"]
            if col in data.columns
        ]
        st.dataframe(data[preview_cols].head(200), use_container_width=True, hide_index=True)

    render_footer()

pg = st.navigation([Page_BUS, st.Page("main_app.py")], position="hidden")
pg.run()
