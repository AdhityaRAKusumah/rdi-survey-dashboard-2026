import streamlit as st

from ui_theme import apply_global_theme, render_footer, render_hero, render_home_card


def home_page():
    st.set_page_config(
        page_title="Biru Karbon Nusantara Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
    )

    apply_global_theme()

    render_hero(
        "Survey Dashboard",
        eyebrow="Biru Karbon Nusantara | RDI Dashboard 2026",
        body=(
            "Explore biogas survey insights across user adoption, kitchen performance, "
            "and leakage assessment."
        ),
    )

    dashboard_cards = st.columns(3, vertical_alignment="top")

    with dashboard_cards[0]:
        render_home_card(
            "Biogas User Survey 2026",
            (
                "Respondent profile, adoption patterns, household impact, gender, "
                "agriculture, energy, and emissions analysis."
            ),
        )
        if st.button("Biogas User Survey 2026", key="data 1", width="stretch", type="primary"):
            st.switch_page("Page_BUS.py", query_params={"utm_source": "new_main.py"})

    with dashboard_cards[1]:
        render_home_card(
            "Kitchen Performance Test 2026",
            "A focused workspace for kitchen performance indicators and related survey outputs.",
        )
        if st.button("Kitchen Performance Test 2026", key="data 2", width="stretch", type="primary"):
            st.switch_page("Page_KPT.py", query_params={"utm_source": "new_main.py"})

    with dashboard_cards[2]:
        render_home_card(
            "Leakage Assessment 2026",
            "Assessment view for leakage-related indicators and monitoring context.",
        )
        if st.button("Leakage Assessment 2026", key="data 3", width="stretch", type="primary"):
            st.switch_page("Page_LA.py", query_params={"utm_source": "new_main.py"})

    render_footer()


pg = st.navigation(
    [
        home_page,
        # st.Page("survey_2025.py"),
        st.Page("Page_BUS.py"),
        st.Page("Page_KPT.py"),
        st.Page("Page_LA.py"),
    ],
    position="hidden",
)
pg.run()
