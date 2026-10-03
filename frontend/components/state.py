from typing import Any
import streamlit as st
from api_client import ApiClient, ApiError
from settings import FrontendSettings

@st.cache_resource
def get_settings() -> FrontendSettings:
    return FrontendSettings()

@st.cache_resource
def get_client() -> ApiClient:
    settings = get_settings()
    return ApiClient(settings.backend_url, settings.request_timeout_seconds)

def current_session_id() -> str | None:
    return st.session_state.get("session_id")

def ensure_session(client: ApiClient) -> str:
    session_id = current_session_id()
    if session_id:
        try:
            client.get_session(session_id)
            return session_id
        except ApiError as error:
            if error.status != 404:
                raise
            st.warning("Your previous session expired. A new one was created.")
    session_id = client.create_session()["id"]
    st.session_state["session_id"] = session_id
    st.session_state.pop("results", None)
    return session_id

def reset_session() -> None:
    for key in ("session_id", "results", "chat_history"):
        st.session_state.pop(key, None)

def show_api_error(error: ApiError) -> None:
    st.error(f"{error.message} (code: {error.code})")

def cached_results() -> dict[str, Any] | None:
    return st.session_state.get("results")
