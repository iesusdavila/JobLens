import time
import pytest
from fastapi.testclient import TestClient
from app.main import ApplicationFactory
from tests.conftest import build_llm
from tests.sample_data import CV_TEXT, JOB_TEXT

API = "/api/v1"

@pytest.fixture
def client(container_factory):
    container = container_factory(llm=build_llm(chat_replies=["Gamma Analytics builds data platforms.", "Focus on Kubernetes basics first."]))
    with TestClient(ApplicationFactory(container=container).create()) as test_client:
        yield test_client

def create_ready_session(client: TestClient) -> tuple[str, str]:
    session_id = client.post(f"{API}/sessions", json={"preferences": {"preferred_modality": "remote"}}).json()["id"]
    upload = client.post(f"{API}/sessions/{session_id}/documents", files={"cv_file": ("cv.txt", CV_TEXT.encode(), "text/plain")}, data={"extra_text": "Speaker at PyCon Spain 2023 about FastAPI performance tuning."})
    assert upload.status_code == 200, upload.text
    assert upload.json()["extra_document"]["kind"] == "extra"
    jobs = client.post(f"{API}/sessions/{session_id}/jobs", json={"jobs": [{"text": JOB_TEXT, "label": "Gamma"}]}).json()
    return session_id, jobs["jobs"][0]["id"]

def test_full_flow_analysis_downloads_and_chat(client: TestClient) -> None:
    assert client.get(f"{API}/health").json()["status"] == "ok"
    session_id, job_id = create_ready_session(client)
    analysis = client.post(f"{API}/sessions/{session_id}/analyze", params={"background": False})
    assert analysis.status_code == 202, analysis.text
    body = analysis.json()
    assert body["status"] == "completed"
    result = body["results"][0]
    assert result["status"] == "completed"
    assert result["fit"]["recommendation"] in {"apply", "apply_after_tailoring", "skip"}
    assert {item["verdict"] for item in result["fit"]["requirements"]} >= {"met", "missing"}
    assert result["cv_validation"]["ats_improved"] is True
    assert result["changes"] and "```diff" in result["change_log_markdown"]
    assert body["ranking"][0]["job_id"] == job_id
    assert client.get(f"{API}/sessions/{session_id}/status").json()["progress"] == 1.0
    docx = client.get(f"{API}/sessions/{session_id}/jobs/{job_id}/cv", params={"format": "docx"})
    pdf = client.get(f"{API}/sessions/{session_id}/jobs/{job_id}/cv", params={"format": "pdf"})
    markdown = client.get(f"{API}/sessions/{session_id}/jobs/{job_id}/cv", params={"format": "md"})
    assert docx.content[:2] == b"PK" and "attachment" in docx.headers["content-disposition"]
    assert pdf.content[:5] == b"%PDF-"
    assert markdown.text.startswith("# Jane Doe")
    reply = client.post(f"{API}/sessions/{session_id}/chat", json={"message": "What does Gamma do?", "job_id": job_id})
    assert reply.status_code == 200 and "Gamma" in reply.json()["reply"]
    streamed = client.post(f"{API}/sessions/{session_id}/chat", json={"message": "How do I close the Kubernetes gap?", "stream": True})
    assert "Kubernetes" in streamed.text

def test_background_analysis_can_be_polled(client: TestClient) -> None:
    session_id, _ = create_ready_session(client)
    started = client.post(f"{API}/sessions/{session_id}/analyze")
    assert started.json()["status"] == "running"
    deadline = time.time() + 10
    status = "running"
    while status == "running" and time.time() < deadline:
        time.sleep(0.05)
        status = client.get(f"{API}/sessions/{session_id}/status").json()["status"]
    assert status == "completed"
    assert client.get(f"{API}/sessions/{session_id}/results").json()["ranking"]

def test_failed_url_flow_and_errors(client: TestClient) -> None:
    session_id = client.post(f"{API}/sessions").json()["id"]
    assert client.post(f"{API}/sessions/{session_id}/analyze").json()["error"]["code"] == "missing_prerequisite"
    bad_file = client.post(f"{API}/sessions/{session_id}/documents", files={"cv_file": ("cv.exe", b"MZ", "application/octet-stream")})
    assert bad_file.status_code == 415
    assert client.get(f"{API}/sessions/{'f' * 32}").status_code == 404
    assert client.post(f"{API}/sessions/{session_id}/jobs", json={"jobs": [{"text": "short"}]}).json()["needs_manual_paste"]
    job_id = client.get(f"{API}/sessions/{session_id}").json()["jobs"][0]["id"]
    fixed = client.put(f"{API}/sessions/{session_id}/jobs/{job_id}/text", json={"text": JOB_TEXT})
    assert fixed.json()["needs_manual_paste"] is False
    assert client.get(f"{API}/sessions/{session_id}/jobs/{job_id}/cv").json()["error"]["code"] == "analysis_not_ready"
    invalid = client.post(f"{API}/sessions/{session_id}/jobs", json={"jobs": [{"url": "ftp://x"}]})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "validation_error"
