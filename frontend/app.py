import streamlit as st
from api_client import ApiError
from components.analysis_tab import render_analysis_tab
from components.chat_tab import render_chat_tab
from components.setup_tab import render_setup_tab
from components.state import current_session_id, get_client, reset_session
from components.tailored_cv_tab import render_tailored_cv_tab

def render_sidebar() -> None:
    client = get_client()
    with st.sidebar:
        st.header("Job Fit Agent")
        try:
            health = client.health()
            st.success(f"Backend online. LLM: {health['llm_model']} ({health['llm_provider']}), validator: {health['jev_model']}")
            if not health["web_search_enabled"]:
                st.caption("Web search is disabled; the chat cannot verify live information.")
        except ApiError as error:
            st.error(error.message)
        if current_session_id():
            st.caption(f"Session {current_session_id()[:8]}... Documents are deleted when the session expires.")
        if st.button("Start a new session"):
            reset_session()
            st.rerun()

def main() -> None:
    st.set_page_config(page_title="Job Fit Agent", layout="wide")
    render_sidebar()
    st.title("Is this job worth applying to?")
    st.caption("Fit analysis validated by Jev, CV tailoring by the configured LLM (Claude on Amazon Bedrock by default). Your CV is only reordered and reworded, never invented.")
    client = get_client()
    setup, analysis, tailored, chat = st.tabs(["Setup", "Analysis", "Tailored CV", "Chat"])
    with setup:
        render_setup_tab(client)
    with analysis:
        render_analysis_tab(client)
    with tailored:
        render_tailored_cv_tab(client)
    with chat:
        render_chat_tab(client)

main()