from __future__ import annotations

import streamlit as st

from monitoring_app.config import APP_NAME
from monitoring_app.services.ai_assistant import InternalAssistantService
from monitoring_app.services.pipeline import MonitoringPipeline
from monitoring_app.services.report_service import ReportService
from monitoring_app.storage import DatabaseManager
from monitoring_app.ui.theme import apply_theme
from monitoring_app.ui.views import (
    PAGE_ASSISTANT,
    PAGE_CASE_DETAILS,
    PAGE_DASHBOARD,
    PAGE_REPORTS,
    PAGE_SEARCH,
    render_assistant_page,
    render_case_details_page,
    render_dashboard_page,
    render_login_page,
    render_reports_page,
    render_search_page,
    render_sidebar,
)


@st.cache_resource
def get_repository() -> DatabaseManager:
    repository = DatabaseManager()
    repository.initialize()
    return repository


@st.cache_resource
def get_pipeline() -> MonitoringPipeline:
    return MonitoringPipeline(get_repository())


@st.cache_resource
def get_report_service() -> ReportService:
    return ReportService(get_repository())


@st.cache_resource
def get_assistant_service() -> InternalAssistantService:
    return InternalAssistantService(get_repository())


def main() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="*", layout="wide")
    apply_theme()

    st.session_state.setdefault("authenticated", False)
    repository = get_repository()

    if not st.session_state.get("authenticated"):
        render_login_page(repository)
        return

    page = render_sidebar()
    if page == PAGE_DASHBOARD:
        render_dashboard_page(repository)
    elif page == PAGE_SEARCH:
        render_search_page(get_pipeline())
    elif page == PAGE_CASE_DETAILS:
        render_case_details_page(repository)
    elif page == PAGE_REPORTS:
        render_reports_page(repository, get_report_service())
    elif page == PAGE_ASSISTANT:
        render_assistant_page(get_assistant_service())


if __name__ == "__main__":
    main()
