from typing import Any
import streamlit as st
from api_client import ApiClient, ApiError
from components.badges import percent
from components.state import cached_results, current_session_id, show_api_error

FORMATS = {"docx": ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "pdf": ("PDF", "application/pdf"), "md": ("Markdown", "text/markdown")}

def render_tailored_cv_tab(client: ApiClient) -> None:
    session_id = current_session_id()
    results = cached_results()
    tailored = [item for item in (results or {}).get("results", []) if item.get("tailored_cv")]
    if not session_id or not tailored:
        st.info("Run the analysis to get a tailored CV for each job.")
        return
    names = {item["job_id"]: item.get("title") or item["job_name"] for item in tailored}
    job_id = st.selectbox("Job", list(names), format_func=names.__getitem__)
    result = next(item for item in tailored if item["job_id"] == job_id)
    render_alignment(result)
    render_downloads(client, session_id, job_id)
    preview, changes = st.columns([3, 2])
    with preview:
        st.subheader("Preview")
        st.markdown(result["markdown_preview"])
    with changes:
        st.subheader("Changes and why")
        st.markdown(result.get("change_log_markdown") or "No changes recorded.")

def render_alignment(result: dict[str, Any]) -> None:
    validation = result.get("cv_validation")
    if not validation:
        st.warning("This CV could not be validated. Review it carefully.")
        return
    original = validation["ats_original"]["score"]
    tailored = validation["ats_tailored"]["score"]
    left, middle, right = st.columns(3)
    left.metric("ATS alignment, original", percent(original))
    middle.metric("ATS alignment, tailored", percent(tailored), delta=f"{(tailored - original) * 100:+.0f} pts")
    unsupported = sum(1 for check in validation["claim_checks"] if not check["supported"])
    right.metric("Claims verified against your documents", f"{len(validation['claim_checks']) - unsupported}/{len(validation['claim_checks'])}")
    for warning in result.get("warnings", []):
        st.warning(warning)

def render_downloads(client: ApiClient, session_id: str, job_id: str) -> None:
    columns = st.columns(len(FORMATS))
    for column, (export_format, (label, mime)) in zip(columns, FORMATS.items()):
        try:
            content = client.download_cv(session_id, job_id, export_format)
        except ApiError as error:
            show_api_error(error)
            continue
        column.download_button(f"Download {label}", content, file_name=f"tailored_cv_{job_id}.{export_format}", mime=mime, width="stretch")
