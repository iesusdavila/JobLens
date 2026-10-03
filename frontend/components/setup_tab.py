from typing import Any
import streamlit as st
from api_client import ApiClient, ApiError
from components.state import ensure_session, show_api_error

def render_setup_tab(client: ApiClient) -> None:
    try:
        session_id = ensure_session(client)
        session = client.get_session(session_id)
    except ApiError as error:
        show_api_error(error)
        return
    render_preferences(client, session_id, session["preferences"])
    render_documents(client, session_id, session)
    render_job_form(client, session_id)
    render_job_list(client, session_id, session["jobs"])

def render_preferences(client: ApiClient, session_id: str, preferences: dict[str, Any]) -> None:
    with st.expander("Your preferences (optional, used to detect conflicts)"):
        with st.form("preferences_form"):
            locations = st.text_input("Preferred locations (comma separated)", ", ".join(preferences.get("desired_locations", [])))
            modality = st.selectbox("Preferred modality", ["", "remote", "hybrid", "onsite"], index=["", "remote", "hybrid", "onsite"].index(preferences.get("preferred_modality") or ""))
            salary = st.text_input("Minimum salary", preferences.get("minimum_salary") or "")
            notes = st.text_area("Other notes", preferences.get("notes") or "", height=80)
            if st.form_submit_button("Save preferences"):
                payload = {
                    "desired_locations": [item.strip() for item in locations.split(",") if item.strip()],
                    "preferred_modality": modality or None,
                    "minimum_salary": salary or None,
                    "notes": notes or None,
                }
                submit(lambda: client.update_preferences(session_id, payload), "Preferences saved.")

def render_documents(client: ApiClient, session_id: str, session: dict[str, Any]) -> None:
    st.subheader("1. Your documents")
    if session.get("cv"):
        cv = session["cv"]
        st.success(f"CV loaded: {cv['filename']} ({cv['word_count']} words, sections: {', '.join(cv['sections'])})")
    if session.get("extra_document"):
        st.info(f"Extra document loaded: {session['extra_document']['filename']}")
    with st.form("documents_form", clear_on_submit=True):
        left, right = st.columns(2)
        with left:
            cv_file = st.file_uploader("CV (PDF, DOCX, TXT, MD)", type=["pdf", "docx", "txt", "md"])
            cv_text = st.text_area("...or paste your CV", height=150)
        with right:
            extra_file = st.file_uploader("Extra document (optional)", type=["pdf", "docx", "txt", "md"])
            extra_text = st.text_area("...or paste notes, achievements, cover letter", height=150)
        if st.form_submit_button("Upload documents", type="primary"):
            submit(
                lambda: client.upload_documents(session_id, file_tuple(cv_file), cv_text, file_tuple(extra_file), extra_text),
                "Documents processed.",
            )

def render_job_form(client: ApiClient, session_id: str) -> None:
    st.subheader("2. Job postings")
    with st.form("jobs_form", clear_on_submit=True):
        urls = st.text_area("Job URLs, one per line", height=90, placeholder="https://company.com/careers/123")
        label = st.text_input("Label for the pasted description (optional)")
        pasted = st.text_area("...or paste a job description", height=150)
        if st.form_submit_button("Add jobs", type="primary"):
            jobs = [{"url": url.strip()} for url in urls.splitlines() if url.strip()]
            if pasted.strip():
                jobs.append({"text": pasted, "label": label or None})
            if not jobs:
                st.warning("Add at least one URL or a pasted description.")
                return
            submit(lambda: client.add_jobs(session_id, jobs), f"{len(jobs)} job(s) added.")

def render_job_list(client: ApiClient, session_id: str, jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        with st.container(border=True):
            header, action = st.columns([5, 1])
            status = ":green-badge[ready]" if not job["needs_manual_paste"] else ":orange-badge[needs paste]"
            header.markdown(f"**{job['display_name']}** {status}")
            if action.button("Remove", key=f"remove_{job['id']}"):
                submit(lambda job_id=job["id"]: client.remove_job(session_id, job_id), "Job removed.")
            if job["needs_manual_paste"]:
                render_manual_paste(client, session_id, job)
            else:
                st.caption(job["text_preview"][:240] + "...")

def render_manual_paste(client: ApiClient, session_id: str, job: dict[str, Any]) -> None:
    st.warning(job.get("message") or "This posting could not be read. Paste its description.")
    text = st.text_area("Paste the job description for this posting", key=f"paste_{job['id']}", height=150)
    if st.button("Save pasted description", key=f"save_{job['id']}"):
        submit(lambda: client.update_job_text(session_id, job["id"], text), "Description saved.")

def file_tuple(uploaded: Any) -> tuple[str, bytes] | None:
    return (uploaded.name, uploaded.getvalue()) if uploaded is not None else None

def submit(action: Any, success_message: str) -> None:
    try:
        action()
    except ApiError as error:
        show_api_error(error)
        return
    st.toast(success_message)
    st.rerun()
