from __future__ import annotations

import streamlit as st

from monitoring_app.config import APP_NAME, COPYRIGHT_NOTICE, OWNER_NAME


def apply_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --app-gold: #B68A28;
                --app-gold-soft: #F7E7B1;
                --app-panel: #FFF9EB;
                --app-line: #E4D2A1;
                --app-black: #141414;
                --app-white: #FFFFFF;
            }
            .stApp {
                background: linear-gradient(180deg, #FFFFFF 0%, #FFFCF2 100%);
                color: var(--app-black);
            }
            .block-container {
                padding-top: 1.5rem;
                padding-bottom: 2rem;
                max-width: 1250px;
            }
            div[data-testid="stSidebar"] {
                background: linear-gradient(180deg, #FFFDF6 0%, #F8EBC2 100%);
                border-left: 1px solid var(--app-line);
            }
            .gold-card {
                border: 1px solid var(--app-line);
                border-radius: 16px;
                padding: 1rem 1.1rem;
                background: var(--app-white);
                box-shadow: 0 10px 28px rgba(182, 138, 40, 0.08);
                margin-bottom: 0.75rem;
            }
            .gold-banner {
                background: linear-gradient(120deg, #FFFDF8 0%, #F8E4A6 100%);
                border: 1px solid var(--app-line);
                border-radius: 20px;
                padding: 1.2rem 1.3rem;
                margin-bottom: 1rem;
            }
            .gold-tag {
                display: inline-block;
                border: 1px solid var(--app-gold);
                border-radius: 999px;
                padding: 0.2rem 0.65rem;
                color: var(--app-black);
                background: #FFF7DA;
                font-size: 0.82rem;
                margin-left: 0.35rem;
                margin-bottom: 0.35rem;
            }
            .metric-title {
                color: #71561A;
                font-size: 0.86rem;
                margin-bottom: 0.2rem;
            }
            .metric-value {
                color: var(--app-black);
                font-size: 1.6rem;
                font-weight: 700;
            }
            .stButton > button, .stDownloadButton > button {
                background: linear-gradient(120deg, #B68A28 0%, #D4AF37 100%);
                color: #111111;
                border: none;
                border-radius: 12px;
                font-weight: 700;
            }
            .stTextInput input, .stTextArea textarea, .stNumberInput input {
                border-radius: 12px;
                border: 1px solid var(--app-line);
            }
            div[data-baseweb="select"] > div {
                border-radius: 12px;
                border-color: var(--app-line);
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 0.5rem;
            }
            .stTabs [data-baseweb="tab"] {
                border-radius: 10px;
                padding: 0.5rem 0.9rem;
                background: #FFF9EB;
                color: #111111;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_banner() -> None:
    st.markdown(
        f"""
        <div class="gold-banner">
            <div style="font-size:1.65rem;font-weight:800;color:#111111;">{APP_NAME}</div>
            <div style="margin-top:0.35rem;color:#5E4A18;">الجهة المالكة: {OWNER_NAME}</div>
            <div style="margin-top:0.2rem;color:#5E4A18;">{COPYRIGHT_NOTICE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(title: str, value: str) -> None:
    st.markdown(
        f"""
        <div class="gold-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_tags(values) -> None:
    html = "".join(f'<span class="gold-tag">{value}</span>' for value in values if value)
    if html:
        st.markdown(html, unsafe_allow_html=True)

