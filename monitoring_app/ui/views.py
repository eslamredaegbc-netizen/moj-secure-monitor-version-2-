from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from monitoring_app.config import (
    APP_NAME,
    CATEGORY_LABELS,
    COPYRIGHT_NOTICE,
    DEFAULT_PASSWORD,
    DEFAULT_SOURCE_SELECTION,
    DEFAULT_USERNAME,
    OWNER_NAME,
    SOURCE_LABELS,
)
from monitoring_app.models import SearchOptions
from monitoring_app.services.ai_assistant import InternalAssistantService
from monitoring_app.services.pipeline import MonitoringPipeline
from monitoring_app.services.report_service import ReportService
from monitoring_app.storage import DatabaseManager
from monitoring_app.ui.theme import info_tags, metric_card, render_banner
from monitoring_app.utils.text import compact_text, split_lines_to_list

PAGE_DASHBOARD = "الصفحة الرئيسية Dashboard"
PAGE_SEARCH = "صفحة البحث والنتائج"
PAGE_CASE_DETAILS = "صفحة تفاصيل القضية"
PAGE_REPORTS = "صفحة التقارير"
PAGE_ASSISTANT = "صفحة اسأل الذكاء الاصطناعي"

PAGE_OPTIONS = [
    PAGE_DASHBOARD,
    PAGE_SEARCH,
    PAGE_CASE_DETAILS,
    PAGE_REPORTS,
    PAGE_ASSISTANT,
]


def render_login_page(repository: DatabaseManager) -> None:
    render_banner()
    left, right = st.columns([1.3, 1])
    with left:
        st.markdown(
            """
            <div class="gold-card">
                <h3 style="margin-top:0;color:#111111;">دخول آمن إلى منصة الرصد</h3>
                <p style="color:#4E4E4E;">
                    التطبيق مبني من الصفر لرصد الأخبار، المواقع الرسمية، X، YouTube، وروابط الويب العامة
                    مع دمج النتائج في قضايا، تصنيفها، وتوليد تقارير احترافية.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        info_tags(["أبيض + ذهبي + أسود", "تقارير PDF / DOCX / CSV / JSON", "مساعد داخلي مبني على بيانات النظام"])
    with right:
        with st.form("login_form", clear_on_submit=False):
            st.subheader("تسجيل الدخول")
            username = st.text_input("اسم المستخدم", value=DEFAULT_USERNAME)
            password = st.text_input("كلمة المرور", type="password", value=DEFAULT_PASSWORD)
            submitted = st.form_submit_button("دخول")
        if submitted:
            user = repository.authenticate_user(username, password)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["user"] = user
                st.success("تم تسجيل الدخول بنجاح.")
                st.rerun()
            else:
                st.error("بيانات الدخول غير صحيحة.")
        st.caption("بيانات الدخول الافتراضية مهيأة تلقائيًا عند أول تشغيل: admin / Admin@123")


def render_sidebar() -> str:
    st.session_state.setdefault("current_page", PAGE_DASHBOARD)
    st.sidebar.markdown(f"### {APP_NAME}")
    st.sidebar.caption(f"{OWNER_NAME}\n\n{COPYRIGHT_NOTICE}")
    page = st.sidebar.radio(
        "التنقل",
        PAGE_OPTIONS,
        key="current_page",
    )
    user = st.session_state.get("user", {})
    st.sidebar.markdown(f"**المستخدم:** {user.get('full_name', '-')}")
    if st.sidebar.button("تسجيل الخروج", use_container_width=True):
        for key in ("authenticated", "user", "last_search_result", "selected_case_id", "last_generated_report"):
            st.session_state.pop(key, None)
        st.rerun()
    return page


def render_dashboard_page(repository: DatabaseManager) -> None:
    render_banner()
    snapshot = repository.dashboard_snapshot()
    metrics = snapshot["metrics"]
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("إجمالي القضايا", str(metrics.get("total_cases", 0)))
    with col2:
        metric_card("إجمالي السجلات", str(metrics.get("total_results", 0)))
    with col3:
        metric_card("القضايا عالية الخطورة", str(metrics.get("high_risk_cases", 0)))
    with col4:
        metric_card("نتائج الاستغاثة", str(metrics.get("distress_results", 0)))

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("أحدث القضايا")
        latest_cases = snapshot["latest_cases"]
        if latest_cases.empty:
            st.info("لا توجد قضايا بعد. ابدأ من شاشة البحث.")
        else:
            st.dataframe(
                latest_cases.rename(
                    columns={
                        "id": "رقم القضية",
                        "title": "العنوان",
                        "primary_category": "التصنيف",
                        "risk_score": "الخطورة",
                        "evidence_count": "الأدلة",
                        "updated_at": "آخر تحديث",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
    with right:
        st.subheader("توزيع القضايا حسب التصنيف")
        categories = snapshot["categories"]
        if categories.empty:
            st.info("لا توجد بيانات تصنيف لعرضها.")
        else:
            chart = categories.set_index("category")
            st.bar_chart(chart)

    st.subheader("توزيع النتائج حسب المصدر")
    sources = snapshot["sources"]
    if sources.empty:
        st.info("لا توجد بيانات مصادر لعرضها.")
    else:
        source_chart = sources.replace({"source_type": SOURCE_LABELS}).set_index("source_type")
        st.bar_chart(source_chart)


def render_search_page(pipeline: MonitoringPipeline) -> None:
    render_banner()
    st.subheader("بحث متعدد المصادر")
    with st.form("search_form", clear_on_submit=False):
        query = st.text_input("موضوع البحث", placeholder="مثال: شكاوى قطاع الإعلام أو اسم جهة أو قضية محددة")
        dork = st.text_input("Google Dorking / استعلام متقدم", placeholder='مثال: site:gov.eg filetype:pdf "اسم الجهة"')
        sources = st.multiselect(
            "المصادر",
            options=list(SOURCE_LABELS.keys()),
            default=DEFAULT_SOURCE_SELECTION,
            format_func=lambda item: SOURCE_LABELS[item],
        )
        col1, col2 = st.columns(2)
        with col1:
            official_domains_text = st.text_area("نطاقات المواقع الرسمية", placeholder="gov.eg\ngov.sa\nmedia.gov.sa")
            direct_urls_text = st.text_area("روابط مباشرة", placeholder="https://example.com/article\nhttps://youtube.com/watch?v=...")
        with col2:
            max_results = st.slider("عدد النتائج لكل مصدر", min_value=3, max_value=12, value=5)
            fetch_full_text = st.checkbox("استخراج النص الكامل من الصفحات", value=True)
            enable_ocr = st.checkbox("تشغيل OCR للصور عند الإمكان", value=False)
            enable_video_transcript = st.checkbox("استخراج نص الفيديو عند الإمكان", value=True)
            search_images = st.checkbox("إضافة بحث الصور", value=False)
        submitted = st.form_submit_button("تنفيذ الرصد")

    if submitted:
        if not query.strip():
            st.error("أدخل موضوع البحث أولًا.")
        elif not sources:
            st.error("اختر مصدرًا واحدًا على الأقل.")
        else:
            direct_urls = split_lines_to_list(direct_urls_text)
            enabled_sources = list(sources)
            if direct_urls and "direct" not in enabled_sources:
                enabled_sources.append("direct")
            options = SearchOptions(
                enabled_sources=enabled_sources,
                google_dork=dork.strip(),
                official_domains=split_lines_to_list(official_domains_text),
                direct_urls=direct_urls,
                max_results_per_source=max_results,
                fetch_full_text=fetch_full_text,
                enable_ocr=enable_ocr,
                enable_video_transcript=enable_video_transcript,
                search_images=search_images,
            )
            with st.spinner("جاري تنفيذ الرصد وتحليل النتائج ودمج القضايا..."):
                st.session_state["last_search_result"] = pipeline.execute_search(query.strip(), options)
            st.success("اكتملت عملية الرصد.")

    outcome = st.session_state.get("last_search_result")
    if not outcome:
        st.info("نفّذ عملية بحث لعرض النتائج هنا.")
        return

    cases = outcome.get("cases", [])
    results = outcome.get("results", [])
    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("القضايا الناتجة", str(len(cases)))
    with col2:
        metric_card("إجمالي النتائج", str(len(results)))
    with col3:
        high_risk = sum(1 for item in results if getattr(item, "risk_score", 0) >= 80)
        metric_card("نتائج خطورتها 80+", str(high_risk))

    case_tab, result_tab = st.tabs(["القضايا", "النتائج التفصيلية"])
    with case_tab:
        if not cases:
            st.warning("لم يتم العثور على قضايا قابلة للدمج.")
        for case in cases:
            with st.expander(
                f"القضية #{case.case_id or '-'} | {case.title} | {case.primary_category} | خطورة {case.risk_score}/100",
                expanded=False,
            ):
                st.write(case.summary)
                info_tags(
                    [
                        f"الثقة {case.confidence}",
                        f"الأدلة {len(case.results)}",
                        *[f"{SOURCE_LABELS.get(source, source)}: {count}" for source, count in case.source_mix.items()],
                    ]
                )
                if st.button(f"فتح القضية #{case.case_id or '-'}", key=f"open_case_{case.case_id}"):
                    st.session_state["selected_case_id"] = case.case_id
                    st.session_state["current_page"] = PAGE_CASE_DETAILS
                    st.rerun()
                for item in case.results[:5]:
                    st.markdown(
                        f"- **{item.title}** | {SOURCE_LABELS.get(item.source_type, item.source_type)} | "
                        f"{item.classification} | خطورة {item.risk_score}/100"
                    )
                    if item.url:
                        st.markdown(f"[فتح المصدر]({item.url})")
    with result_tab:
        if not results:
            st.warning("لا توجد نتائج محفوظة لهذه العملية.")
        else:
            rows = []
            for item in results:
                rows.append(
                    {
                        "القضية": item.case_id,
                        "المصدر": SOURCE_LABELS.get(item.source_type, item.source_type),
                        "العنوان": item.title,
                        "التصنيف": item.classification,
                        "الخطورة": item.risk_score,
                        "الثقة": item.classification_confidence,
                        "الصلة": item.relevance_score,
                        "الرابط": item.url,
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_case_details_page(repository: DatabaseManager) -> None:
    render_banner()
    st.subheader("تفاصيل القضية")
    cases_df = repository.list_cases(limit=200)
    if cases_df.empty:
        st.info("لا توجد قضايا لعرضها حتى الآن.")
        return

    case_options = {
        int(row["id"]): f"#{int(row['id'])} | {row['title']} | {row['primary_category']} | خطورة {int(row['risk_score'])}"
        for _, row in cases_df.iterrows()
    }
    default_case_id = st.session_state.get("selected_case_id")
    case_ids = list(case_options.keys())
    if default_case_id not in case_ids:
        default_case_id = case_ids[0]
    selected_case_id = st.selectbox(
        "اختر القضية",
        options=case_ids,
        format_func=lambda case_id: case_options[case_id],
        index=case_ids.index(default_case_id),
    )
    st.session_state["selected_case_id"] = selected_case_id

    case = repository.get_case(int(selected_case_id))
    if not case:
        st.error("تعذر العثور على القضية.")
        return

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown(
            f"""
            <div class="gold-card">
                <h3 style="margin-top:0;color:#111111;">{escape(str(case['title']))}</h3>
                <p style="color:#333333;">{escape(str(case.get('summary') or 'لا يوجد ملخص.'))}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        metric_card("الخطورة", f"{int(case['risk_score'])}/100")
        metric_card("الثقة", str(case.get("confidence", 0)))
        metric_card("الأدلة", str(case.get("evidence_count", 0)))
    info_tags(
        [
            f"التصنيف {case['primary_category']}",
            f"الحالة {case['status']}",
            *[f"{SOURCE_LABELS.get(source, source)}: {count}" for source, count in case.get("source_mix", {}).items()],
        ]
    )

    results_df = repository.get_case_results(int(selected_case_id))
    st.subheader("الأدلة والنتائج المرتبطة")
    if results_df.empty:
        st.info("لا توجد نتائج مرتبطة بهذه القضية.")
    else:
        display_df = results_df.rename(
            columns={
                "source_name": "المصدر",
                "title": "العنوان",
                "classification": "التصنيف",
                "risk_score": "الخطورة",
                "classification_confidence": "الثقة",
                "published_at": "تاريخ النشر",
                "url": "الرابط",
            }
        )
        st.dataframe(
            display_df[["المصدر", "العنوان", "التصنيف", "الخطورة", "الثقة", "تاريخ النشر", "الرابط"]],
            use_container_width=True,
            hide_index=True,
        )
        for _, row in results_df.head(10).iterrows():
            with st.expander(f"{row['title']} | {row['classification']} | خطورة {int(row['risk_score'])}/100"):
                st.write(compact_text(str(row["snippet"] or row["content_text"] or row["title"]), 600))
                if row["transcript"]:
                    st.caption("تم استخراج نص فيديو لهذه النتيجة.")
                if row["ocr_text"]:
                    st.caption("تم استخراج نص OCR لهذه النتيجة.")
                if row["url"]:
                    st.markdown(f"[فتح المصدر]({row['url']})")


def render_reports_page(repository: DatabaseManager, report_service: ReportService) -> None:
    render_banner()
    st.subheader("التقارير")
    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox("تصفية حسب التصنيف", options=[""] + CATEGORY_LABELS, format_func=lambda item: item or "الكل")
    with col2:
        minimum_risk = st.slider("الحد الأدنى للخطورة", min_value=0, max_value=100, value=0)

    cols = st.columns(4)
    formats = ["PDF", "DOCX", "CSV", "JSON"]
    for column, format_name in zip(cols, formats):
        with column:
            if st.button(f"توليد {format_name}", use_container_width=True, key=f"generate_{format_name}"):
                with st.spinner(f"جاري توليد تقرير {format_name}..."):
                    try:
                        path = report_service.generate_report(format_name.lower(), category, minimum_risk)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["last_generated_report"] = str(path)
                        st.success(f"تم توليد التقرير: {path.name}")

    report_path = st.session_state.get("last_generated_report")
    if report_path:
        file_path = Path(report_path)
        if file_path.exists():
            with file_path.open("rb") as file_handle:
                st.download_button(
                    label=f"تنزيل آخر تقرير: {file_path.name}",
                    data=file_handle.read(),
                    file_name=file_path.name,
                    mime="application/octet-stream",
                )

    st.subheader("التقارير المولدة مؤخرًا")
    reports_df = repository.list_reports()
    if reports_df.empty:
        st.info("لم يتم توليد أي تقارير بعد.")
    else:
        st.dataframe(
            reports_df.rename(
                columns={
                    "report_name": "اسم التقرير",
                    "format": "الصيغة",
                    "file_path": "المسار",
                    "created_at": "تاريخ الإنشاء",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_assistant_page(assistant_service: InternalAssistantService) -> None:
    render_banner()
    st.subheader("اسأل الذكاء الاصطناعي")
    st.caption("الإجابات هنا مبنية فقط على البيانات الموجودة داخل النظام، مع أدلة وثقة.")
    with st.form("assistant_form"):
        question = st.text_area("اكتب سؤالك", placeholder="مثال: ما أخطر القضايا الحالية؟ أو كم عدد القضايا المتعلقة بالشكاوى؟")
        submitted = st.form_submit_button("تحليل السؤال")

    if submitted:
        if not question.strip():
            st.error("أدخل سؤالًا أولًا.")
        else:
            answer = assistant_service.answer_question(question)
            st.markdown(
                f"""
                <div class="gold-card">
                    <h3 style="margin-top:0;color:#111111;">الإجابة</h3>
                    <p style="color:#222222;">{escape(answer.answer)}</p>
                    <p style="color:#6A5420;">الثقة: {answer.confidence} | نطاق البيانات: {answer.data_scope}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if answer.evidence:
                st.subheader("الأدلة")
                for item in answer.evidence:
                    st.markdown(
                        f"""
                        <div class="gold-card">
                            <strong>القضية #{item.case_id}: {escape(item.title)}</strong><br/>
                            <span>التطابق: {item.similarity}</span><br/>
                            <span>{escape(item.snippet)}</span><br/>
                            {"<a href='" + item.url + "' target='_blank'>فتح المصدر</a>" if item.url else ""}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
