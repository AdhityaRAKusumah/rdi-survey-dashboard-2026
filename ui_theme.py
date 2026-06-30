import base64
from pathlib import Path

import streamlit as st


PRIMARY_BLUE = "#184F8F"
DEEP_BLUE = "#0E376D"
OCEAN_BLUE = "#2F7FC1"
SKY_BLUE = "#DDEEFF"
LEAF_GREEN = "#3FA46A"
WARM_GOLD = "#F4B942"
INK = "#14243A"
MUTED = "#64748B"
SURFACE = "#FFFFFF"
BACKGROUND = "#F4F8FC"

PLOTLY_COLORWAY = [
    PRIMARY_BLUE,
    OCEAN_BLUE,
    LEAF_GREEN,
    WARM_GOLD,
    "#7C8AA5",
    "#1F9D9A",
    "#E66F51",
    "#6C63B8",
]


def apply_global_theme():
    st.markdown(
        f"""
        <style>
        :root {{
            --bkn-primary: {PRIMARY_BLUE};
            --bkn-deep: {DEEP_BLUE};
            --bkn-ocean: {OCEAN_BLUE};
            --bkn-sky: {SKY_BLUE};
            --bkn-green: {LEAF_GREEN};
            --bkn-gold: {WARM_GOLD};
            --bkn-ink: {INK};
            --bkn-muted: {MUTED};
            --bkn-bg: {BACKGROUND};
            --bkn-surface: {SURFACE};
        }}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(47, 127, 193, 0.18), transparent 34rem),
                linear-gradient(180deg, #f8fbff 0%, var(--bkn-bg) 42%, #ffffff 100%);
            color: var(--bkn-ink);
            font-family: Inter, "Segoe UI", Arial, sans-serif;
        }}

        .block-container {{
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1320px;
        }}

        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, var(--bkn-deep) 0%, var(--bkn-primary) 100%);
            border-right: 1px solid rgba(255, 255, 255, 0.18);
        }}

        [data-testid="stSidebar"] * {{
            color: #ffffff;
        }}

        [data-testid="stSidebar"] [data-baseweb="select"] *,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {{
            color: var(--bkn-ink) !important;
        }}

        [data-testid="stSidebar"] [data-baseweb="tag"] {{
            background: var(--bkn-sky) !important;
            border-radius: 6px;
        }}

        [data-testid="stSidebar"] [data-baseweb="tag"] *,
        [data-testid="stSidebar"] [data-baseweb="tag"] span {{
            color: var(--bkn-deep) !important;
            font-weight: 750;
        }}

        [data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p {{
            color: rgba(255, 255, 255, 0.78);
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: var(--bkn-ink);
            font-family: Inter, "Segoe UI", Arial, sans-serif;
            letter-spacing: 0;
        }}

        h1 {{
            font-size: 2.65rem;
            line-height: 1.08;
            font-weight: 800;
        }}

        h2, h3 {{
            font-weight: 760;
        }}

        div[data-testid="stMetric"] {{
            background: var(--bkn-surface);
            border: 1px solid rgba(24, 79, 143, 0.12);
            border-radius: 8px;
            padding: 1.05rem 1rem;
            box-shadow: 0 14px 36px rgba(14, 55, 109, 0.08);
        }}

        div[data-testid="stMetricLabel"] p {{
            color: var(--bkn-muted);
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0;
        }}

        div[data-testid="stMetricValue"] {{
            color: var(--bkn-deep);
            font-weight: 800;
        }}

        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.35rem;
            border-bottom: 1px solid rgba(20, 36, 58, 0.12);
        }}

        .stTabs [data-baseweb="tab"] {{
            border-radius: 8px 8px 0 0;
            color: var(--bkn-muted);
            font-weight: 700;
            padding: 0.8rem 1rem;
        }}

        .stTabs [aria-selected="true"] {{
            color: var(--bkn-primary);
            background: rgba(221, 238, 255, 0.65);
        }}

        .stButton > button {{
            border-radius: 8px;
            border: 1px solid rgba(24, 79, 143, 0.2);
            background: linear-gradient(135deg, var(--bkn-primary), var(--bkn-ocean));
            color: #ffffff;
            font-weight: 750;
            min-height: 2.85rem;
            box-shadow: 0 12px 28px rgba(24, 79, 143, 0.18);
        }}

        .stButton > button:hover {{
            border-color: var(--bkn-deep);
            box-shadow: 0 16px 34px rgba(24, 79, 143, 0.24);
            transform: translateY(-1px);
        }}

        [data-testid="stPlotlyChart"],
        iframe[title="streamlit_folium.st_folium"] {{
            background: var(--bkn-surface);
            border: 1px solid rgba(24, 79, 143, 0.10);
            border-radius: 8px;
            box-shadow: 0 14px 36px rgba(14, 55, 109, 0.08);
            padding: 1.1rem 0.9rem 0.85rem;
            overflow: visible;
        }}

        [data-testid="stPlotlyChart"] > div {{
            overflow: visible !important;
        }}

        .summary-panel {{
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid rgba(24, 79, 143, 0.14);
            border-left: 5px solid var(--bkn-green);
            border-radius: 8px;
            box-shadow: 0 12px 30px rgba(14, 55, 109, 0.08);
            padding: 1rem 1.1rem;
            margin: 0.85rem 0 1.1rem;
        }}

        .summary-panel .summary-title {{
            color: var(--bkn-deep);
            font-size: 1rem;
            font-weight: 800;
            margin-bottom: 0.45rem;
        }}

        .summary-panel ul {{
            margin: 0.15rem 0 0 1.15rem;
            padding: 0;
        }}

        .summary-panel li {{
            color: var(--bkn-ink);
            font-size: 0.94rem;
            line-height: 1.48;
            margin: 0.25rem 0;
        }}

        .summary-caveats {{
            border-top: 1px solid rgba(20, 36, 58, 0.10);
            margin-top: 0.7rem;
            padding-top: 0.6rem;
            color: var(--bkn-muted);
        }}

        hr {{
            border: none;
            border-top: 1px solid rgba(20, 36, 58, 0.12);
            margin: 2.2rem 0 1rem;
        }}

        .bkn-topbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: 0.6rem 0 1rem;
        }}

        .bkn-brand {{
            display: flex;
            align-items: center;
            gap: 0.72rem;
            color: var(--bkn-deep);
            font-weight: 800;
            line-height: 1.05;
        }}

        .bkn-logo-img {{
            width: 8.8rem;
            max-width: 42vw;
            height: auto;
            display: block;
            object-fit: contain;
        }}

        .bkn-hero {{
            background:
                linear-gradient(135deg, rgba(14, 55, 109, 0.96), rgba(24, 79, 143, 0.92)),
                linear-gradient(90deg, rgba(63, 164, 106, 0.18), transparent);
            color: #ffffff;
            border-radius: 8px;
            padding: clamp(1.8rem, 4vw, 3.3rem);
            margin: 0.6rem 0 1.4rem;
            box-shadow: 0 22px 54px rgba(14, 55, 109, 0.22);
            overflow: hidden;
            position: relative;
        }}

        .bkn-hero::after {{
            content: "";
            position: absolute;
            right: -4rem;
            bottom: -5rem;
            width: 18rem;
            height: 18rem;
            border-radius: 50%;
            border: 2rem solid rgba(255, 255, 255, 0.08);
        }}

        .bkn-eyebrow {{
            color: var(--bkn-sky);
            font-weight: 800;
            text-transform: uppercase;
            font-size: 0.78rem;
            letter-spacing: 0;
            margin-bottom: 0.65rem;
        }}

        .bkn-hero h1 {{
            color: #ffffff;
            max-width: 860px;
            margin: 0;
        }}

        .bkn-hero p {{
            max-width: 760px;
            margin: 1rem 0 0;
            color: rgba(255, 255, 255, 0.82);
            font-size: 1.02rem;
            line-height: 1.65;
        }}

        .bkn-section-note {{
            color: var(--bkn-muted);
            margin: -0.35rem 0 1.25rem;
            font-size: 1rem;
        }}

        .bkn-card {{
            background: var(--bkn-surface);
            border: 1px solid rgba(24, 79, 143, 0.12);
            border-radius: 8px;
            padding: 1.15rem;
            min-height: 8.5rem;
            box-shadow: 0 14px 36px rgba(14, 55, 109, 0.08);
        }}

        .bkn-card-title {{
            color: var(--bkn-deep);
            font-size: 1.1rem;
            font-weight: 800;
            margin: 0 0 0.4rem;
        }}

        .bkn-card-body {{
            color: var(--bkn-muted);
            line-height: 1.55;
            margin: 0;
        }}

        .bkn-footer {{
            color: var(--bkn-muted);
            font-size: 0.88rem;
            text-align: center;
            padding-top: 0.4rem;
        }}

        @media (max-width: 760px) {{
            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}

            h1 {{
                font-size: 2rem;
            }}

            .bkn-topbar {{
                align-items: flex-start;
                flex-direction: column;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand_bar():
    logo_uri = _asset_data_uri(Path(__file__).resolve().parent.parent / "LogoBiru.png")
    logo_html = (
        f'<img class="bkn-logo-img" src="{logo_uri}" alt="Biru Karbon Nusantara logo"/>'
        if logo_uri
        else "<div>Biru Karbon<br/>Nusantara</div>"
    )
    st.markdown(
        f"""
        <div class="bkn-topbar">
            <div class="bkn-brand">
                {logo_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _asset_data_uri(path):
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_hero(title, eyebrow="RDI Dashboard 2026", body=None):
    body_html = f"<p>{body}</p>" if body else ""
    st.markdown(
        f"""
        <section class="bkn-hero">
            <div class="bkn-eyebrow">{eyebrow}</div>
            <h1>{title}</h1>
            {body_html}
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title, subtitle):
    render_brand_bar()
    render_hero(title, eyebrow=subtitle)


def render_home_card(title, body):
    st.markdown(
        f"""
        <div class="bkn-card">
            <p class="bkn-card-title">{title}</p>
            <p class="bkn-card-body">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_header(filtered_rows=None):
    st.sidebar.markdown("### Dashboard Filters")
    st.sidebar.markdown("Refine the survey scope before reviewing the charts.")
    if filtered_rows is not None:
        st.sidebar.markdown(f"**Filtered data:** {filtered_rows:,} rows")


def render_footer():
    st.markdown("---")
    st.markdown(
        '<div class="bkn-footer">Biru Karbon Nusantara Survey Dashboard | RDI 2026</div>',
        unsafe_allow_html=True,
    )
