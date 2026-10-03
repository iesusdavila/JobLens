import json
import httpx
import pytest
from app.core.exceptions import InvalidJobInputError
from app.domain.enums import IngestionStatus
from app.domain.job_models import JobInput
from app.services.document_parser_service import TextNormalizer
from app.services.job_ingestion_service import AccessBarrierDetector, JobIngestionService, JobPageTextExtractor, PastedTextJobProvider, RobotsPolicy, UrlJobFetcher
from tests.sample_data import JOB_TEXT

def service_with(handler: httpx.MockTransport, respect_robots: bool = False) -> JobIngestionService:
    client = httpx.AsyncClient(transport=handler, follow_redirects=True)
    normalizer = TextNormalizer()
    fetcher = UrlJobFetcher(client, RobotsPolicy(client, respect_robots), JobPageTextExtractor(normalizer), AccessBarrierDetector(min_chars=200), max_text_chars=30000)
    return JobIngestionService(fetcher, PastedTextJobProvider(normalizer, min_chars=80, max_chars=30000), max_jobs=5)

def html_page(body: str) -> str:
    return f"<html><head><title>Job</title><script>var tracking = 1;</script></head><body><nav>Home Jobs About</nav>{body}<footer>Cookie policy</footer></body></html>"

async def test_main_posting_text_is_extracted_without_boilerplate() -> None:
    body = "<main><h1>Senior Python Engineer</h1>" + "".join(f"<p>{line}</p>" for line in JOB_TEXT.splitlines()) + "</main>"
    service = service_with(httpx.MockTransport(lambda request: httpx.Response(200, html=html_page(body))))
    posting = await service.ingest(JobInput(url="https://careers.example.com/jobs/1"))
    assert posting.ingestion_status == IngestionStatus.OK
    assert "Kubernetes in production" in posting.text
    assert "Cookie policy" not in posting.text and "tracking" not in posting.text

async def test_json_ld_job_posting_is_preferred() -> None:
    data = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Data Engineer", "hiringOrganization": {"name": "Delta"}, "description": "<p>" + "Build data pipelines with Spark and Airflow. " * 10 + "</p>"}
    page = html_page(f'<script type="application/ld+json">{json.dumps(data)}</script><div>Menu</div>')
    service = service_with(httpx.MockTransport(lambda request: httpx.Response(200, html=page)))
    posting = await service.ingest(JobInput(url="https://jobs.example.com/2"))
    assert posting.text.startswith("Data Engineer\nDelta")
    assert "Airflow" in posting.text

async def test_login_wall_requires_manual_paste() -> None:
    page = html_page("<main><p>Sign in to view this job. Join now to see who you already know.</p></main>")
    service = service_with(httpx.MockTransport(lambda request: httpx.Response(200, html=page)))
    posting = await service.ingest(JobInput(url="https://www.linkedin.com/jobs/view/1"))
    assert posting.ingestion_status == IngestionStatus.NEEDS_MANUAL_PASTE
    assert "Paste the job description" in posting.message
    assert posting.text == ""

async def test_captcha_and_blocked_status_require_manual_paste() -> None:
    blocked = service_with(httpx.MockTransport(lambda request: httpx.Response(403, html=html_page("<p>Access denied</p>"))))
    captcha = service_with(httpx.MockTransport(lambda request: httpx.Response(200, html=html_page("<div class='g-recaptcha'>Please complete the captcha</div>"))))
    assert (await blocked.ingest(JobInput(url="https://a.example.com/job"))).ingestion_status == IngestionStatus.NEEDS_MANUAL_PASTE
    captcha_posting = await captcha.ingest(JobInput(url="https://b.example.com/job"))
    assert captcha_posting.ingestion_status == IngestionStatus.NEEDS_MANUAL_PASTE
    assert "captcha" in captcha_posting.message

async def test_unreachable_url_requires_manual_paste() -> None:
    def raise_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")
    posting = await service_with(httpx.MockTransport(raise_error)).ingest(JobInput(url="https://down.example.com/job"))
    assert posting.ingestion_status == IngestionStatus.NEEDS_MANUAL_PASTE

async def test_robots_disallow_is_respected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /jobs/")
        return httpx.Response(200, html=html_page("<main>" + "<p>content</p>" * 100 + "</main>"))
    posting = await service_with(httpx.MockTransport(handler), respect_robots=True).ingest(JobInput(url="https://c.example.com/jobs/9"))
    assert posting.ingestion_status == IngestionStatus.NEEDS_MANUAL_PASTE
    assert "robots.txt" in posting.message

async def test_pasted_text_is_accepted_and_short_text_rejected() -> None:
    service = service_with(httpx.MockTransport(lambda request: httpx.Response(500)))
    good, short = await service.ingest_many([JobInput(text=JOB_TEXT, label="Gamma"), JobInput(text="too short")])
    assert good.ingestion_status == IngestionStatus.OK and good.display_name == "Gamma"
    assert short.ingestion_status == IngestionStatus.FAILED

async def test_failed_url_can_be_replaced_with_pasted_text() -> None:
    service = service_with(httpx.MockTransport(lambda request: httpx.Response(401)))
    posting = await service.ingest(JobInput(url="https://private.example.com/job"))
    fixed = service.replace_text(posting, JOB_TEXT)
    assert fixed.id == posting.id and fixed.is_ready

def test_job_input_requires_exactly_one_source() -> None:
    with pytest.raises(ValueError):
        JobInput(url="https://x.example.com", text="text")
    with pytest.raises(ValueError):
        JobInput()

async def test_empty_input_list_is_rejected() -> None:
    with pytest.raises(InvalidJobInputError):
        await service_with(httpx.MockTransport(lambda request: httpx.Response(200))).ingest_many([])
