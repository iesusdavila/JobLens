import time
from typing import Any
import pandas as pd
import streamlit as st
from api_client import ApiClient, ApiError
from components.badges import confidence_badge, percent, recommendation_badge, verdict_badge
from components.state import current_session_id, get_settings, show_api_error

def render_analysis_tab(client: ApiClient) -> None:
    session_id = current_session_id()
    if not session_id:
        st.info("Start in the Setup tab.")
        return
    if st.button("Run analysis", type="primary"):
        try:
            client.start_analysis(session_id)
        except ApiError as error:
            show_api_error(error)
    try:
        status = client.get_status(session_id)
    except ApiError as error:
        show_api_error(error)
        return
    if status["status"] == "running":
        wait_for_completion(client, session_id)
        return
    if status["status"] == "idle":
        st.info("Upload your CV, add jobs and press Run analysis.")
        return
    try:
        results = client.get_results(session_id)
    except ApiError as error:
        show_api_error(error)
        return
    st.session_state["results"] = results
    render_results(results)

def wait_for_completion(client: ApiClient, session_id: str) -> None:
    progress = st.progress(0.0, text="The agent is analyzing your jobs...")
    while True:
        status = client.get_status(session_id)
        done = sum(1 for value in status["job_statuses"].values() if value not in ("pending", "running"))
        progress.progress(status["progress"], text=f"Analyzed {done} of {len(status['job_statuses'])} jobs...")
        if status["status"] != "running":
            break
        time.sleep(get_settings().poll_interval_seconds)
    st.rerun()

def render_results(results: dict[str, Any]) -> None:
    if results.get("error"):
        st.error(results["error"])
    if len(results["ranking"]) > 1:
        render_ranking(results["ranking"])
    for result in sorted(results["results"], key=lambda item: -(item["fit"] or {}).get("overall_score", -1)):
        render_job_card(result)

def render_ranking(ranking: list[dict[str, Any]]) -> None:
    st.subheader("Which job to prioritize")
    table = pd.DataFrame([
        {
            "Rank": entry["rank"],
            "Job": entry["title"] or entry["job_name"],
            "Company": entry["company"] or "",
            "Fit": entry["overall_score"],
            "Recommendation": entry["recommendation"].replace("_", " "),
            "Must-haves": percent(entry["must_have_coverage"]),
            "ATS original": percent(entry["ats_original"]),
            "ATS tailored": percent(entry["ats_tailored"]),
        }
        for entry in ranking
    ])
    st.dataframe(table, hide_index=True, width="stretch")

def render_job_card(result: dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"### {result.get('title') or result['job_name']}" + (f" at {result['company']}" if result.get("company") else ""))
        for warning in result.get("warnings", []):
            st.warning(warning)
        if result.get("error"):
            st.error(result["error"])
        fit = result.get("fit")
        if not fit:
            return
        render_fit_header(fit)
        render_dimensions(fit)
        render_requirements(fit)
        render_strengths_and_gaps(fit)

def render_fit_header(fit: dict[str, Any]) -> None:
    left, middle, right = st.columns(3)
    left.metric("Overall fit", f"{fit['overall_score']:.0f}/100")
    middle.metric("Must-haves covered", percent(fit["must_have_coverage"]))
    right.metric("ATS alignment (original CV)", percent(fit["ats_original"]["score"]))
    st.markdown(f"**Recommendation:** {recommendation_badge(fit['recommendation'])}")
    for reason in fit["recommendation_reasons"]:
        st.markdown(f"- {reason}")
    seniority = fit["seniority"]
    st.markdown(f"**Seniority:** {seniority['match']} {confidence_badge(seniority['confidence'])}")
    if fit["low_confidence_items"]:
        st.caption("Uncertain verdicts: " + "; ".join(fit["low_confidence_items"]))

def render_dimensions(fit: dict[str, Any]) -> None:
    columns = st.columns(len(fit["dimensions"]))
    for column, dimension in zip(columns, fit["dimensions"]):
        column.metric(dimension["dimension"].replace("_", " ").title(), percent(dimension["score"]))
        column.markdown(confidence_badge(dimension["confidence"]))

def render_requirements(fit: dict[str, Any]) -> None:
    with st.expander("Requirements"):
        for item in fit["requirements"]:
            priority = "must-have" if item["priority"] == "must_have" else "nice-to-have"
            st.markdown(f"{verdict_badge(item['verdict'])} **{priority}** {item['text']} {confidence_badge(item['confidence'])}")
    triggered = [flag for flag in fit["red_flags"] if flag["triggered"]]
    if triggered:
        st.markdown("**Red flags**")
        for flag in triggered:
            st.markdown(f":red-badge[{flag['side']}] {flag['description']} ({flag['probability']:.0%})")

def render_strengths_and_gaps(fit: dict[str, Any]) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("**Strengths**")
        for item in fit["strengths"] or ["No clear strengths detected."]:
            st.markdown(f"- {item}")
    with right:
        st.markdown("**Gaps**")
        for item in fit["gaps"] or ["No gaps detected."]:
            st.markdown(f"- {item}")
