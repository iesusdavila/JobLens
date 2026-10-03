import streamlit as st
from api_client import ApiClient, ApiError
from components.state import current_session_id, show_api_error

ALL_JOBS = "__all__"

def render_chat_tab(client: ApiClient) -> None:
    session_id = current_session_id()
    if not session_id:
        st.info("Start in the Setup tab.")
        return
    try:
        jobs = client.get_session(session_id)["jobs"]
    except ApiError as error:
        show_api_error(error)
        return
    options = {ALL_JOBS: "All jobs"} | {job["id"]: job["display_name"] for job in jobs if not job["needs_manual_paste"]}
    scope = st.selectbox("Conversation scope", list(options), format_func=options.__getitem__)
    history = st.session_state.setdefault("chat_history", {}).setdefault(scope, [])
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("Ask about the company, similar roles, skill gaps, interviews...")
    if not prompt:
        return
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(client.stream_chat(session_id, prompt, None if scope == ALL_JOBS else scope))
        except ApiError as error:
            show_api_error(error)
            return
    history.append({"role": "assistant", "content": reply if isinstance(reply, str) else "".join(map(str, reply))})
