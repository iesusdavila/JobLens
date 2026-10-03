import asyncio
import json
import logging
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel
from app.core.exceptions import InvalidJobInputError
from app.domain.enums import IngestionStatus, JobSourceType
from app.domain.job_models import JobInput, JobPosting
from app.services.document_parser_service import TextNormalizer

logger = logging.getLogger(__name__)

class FetchOutcome(BaseModel):
    status: IngestionStatus
    text: str = ""
    message: str | None = None

class RobotsPolicy:
    USER_AGENT = "JobFitAgent"

    def __init__(self, http_client: httpx.AsyncClient, enabled: bool) -> None:
        self._http_client = http_client
        self._enabled = enabled

    async def allows(self, url: str) -> bool:
        if not self._enabled:
            return True
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            response = await self._http_client.get(robots_url)
        except httpx.HTTPError:
            return True
        if response.status_code >= 400:
            return True
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser.can_fetch(self.USER_AGENT, url)

class JobPageTextExtractor:
    NOISE_TAGS = ("script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe", "button")
    CONTENT_HINTS = re.compile(r"job|description|posting|vacancy|position|career|details", re.IGNORECASE)

    def __init__(self, normalizer: TextNormalizer) -> None:
        self._normalizer = normalizer

    def extract(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        structured = self._structured_posting(soup)
        if structured:
            return structured
        for tag in soup(self.NOISE_TAGS):
            tag.decompose()
        container = self._main_container(soup)
        return self._normalizer.normalize(container.get_text("\n")) if container else ""

    def _structured_posting(self, soup: BeautifulSoup) -> str:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            for item in self._json_items(script.string or ""):
                if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                    return self._render_structured(item)
        return ""

    def _render_structured(self, item: dict) -> str:
        description = BeautifulSoup(str(item.get("description", "")), "html.parser").get_text("\n")
        organization = item.get("hiringOrganization")
        company = organization.get("name") if isinstance(organization, dict) else None
        header = [value for value in (item.get("title"), company) if value]
        return self._normalizer.normalize("\n".join([*header, description]))

    @staticmethod
    def _json_items(raw: str) -> list[object]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(data, dict) and "@graph" in data:
            return list(data["@graph"])
        return data if isinstance(data, list) else [data]

    def _main_container(self, soup: BeautifulSoup) -> Tag | None:
        for selector in ("main", "article", "[role=main]"):
            found = soup.select_one(selector)
            if found and len(found.get_text(strip=True)) > 200:
                return found
        candidates = [tag for tag in soup.find_all(["div", "section"]) if self._looks_like_posting(tag)]
        if candidates:
            return max(candidates, key=lambda tag: len(tag.get_text(strip=True)))
        return soup.body or soup

    def _looks_like_posting(self, tag: Tag) -> bool:
        attributes = " ".join([tag.get("id") or "", *(tag.get("class") or [])])
        return bool(self.CONTENT_HINTS.search(attributes))

class AccessBarrierDetector:
    LOGIN_PATTERNS = re.compile(r"sign in to (view|see|continue)|log in to (view|see|continue)|join now to see|authwall|please log in|inicia sesi[oó]n para", re.IGNORECASE)
    CAPTCHA_PATTERNS = re.compile(r"captcha|are you a robot|verify you are (a )?human|unusual traffic|cf-challenge|access denied", re.IGNORECASE)
    BLOCKING_STATUSES = {401, 403, 407, 429, 451, 999}

    def __init__(self, min_chars: int) -> None:
        self._min_chars = min_chars

    def barrier_message(self, status_code: int, html: str, text: str) -> str | None:
        if status_code in self.BLOCKING_STATUSES:
            return f"The site refused automated access (HTTP {status_code}). Paste the job description instead."
        if self.CAPTCHA_PATTERNS.search(html[:20000]) and len(text) < self._min_chars * 3:
            return "The page shows a captcha or bot check. Paste the job description instead."
        if self.LOGIN_PATTERNS.search(text[:5000]) and len(text) < self._min_chars * 5:
            return "The page requires login to show the posting. Paste the job description instead."
        if len(text) < self._min_chars:
            return "The page content was empty or truncated. Paste the job description instead."
        return None

class UrlJobFetcher:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 JobFitAgent/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    }

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        robots_policy: RobotsPolicy,
        extractor: JobPageTextExtractor,
        barrier_detector: AccessBarrierDetector,
        max_text_chars: int,
    ) -> None:
        self._http_client = http_client
        self._robots_policy = robots_policy
        self._extractor = extractor
        self._barrier_detector = barrier_detector
        self._max_text_chars = max_text_chars

    async def fetch(self, url: str) -> FetchOutcome:
        if not await self._robots_policy.allows(url):
            return FetchOutcome(status=IngestionStatus.NEEDS_MANUAL_PASTE, message="The site's robots.txt disallows automated reading of this page. Paste the job description instead.")
        try:
            response = await self._http_client.get(url, headers=self.HEADERS)
        except httpx.TimeoutException:
            return FetchOutcome(status=IngestionStatus.NEEDS_MANUAL_PASTE, message="The page took too long to respond. Paste the job description instead.")
        except httpx.HTTPError as error:
            logger.info("job_fetch_failed", extra={"host": urlparse(url).netloc, "error_type": type(error).__name__})
            return FetchOutcome(status=IngestionStatus.NEEDS_MANUAL_PASTE, message="The URL could not be reached. Check it or paste the job description instead.")
        return self._outcome(response)

    def _outcome(self, response: httpx.Response) -> FetchOutcome:
        html = response.text if "html" in response.headers.get("content-type", "html") else ""
        text = self._extractor.extract(html) if html else ""
        barrier = self._barrier_detector.barrier_message(response.status_code, html, text)
        if barrier:
            return FetchOutcome(status=IngestionStatus.NEEDS_MANUAL_PASTE, message=barrier)
        if response.status_code >= 400:
            return FetchOutcome(status=IngestionStatus.NEEDS_MANUAL_PASTE, message=f"The page returned HTTP {response.status_code}. Paste the job description instead.")
        return FetchOutcome(status=IngestionStatus.OK, text=text[: self._max_text_chars])

class PastedTextJobProvider:
    def __init__(self, normalizer: TextNormalizer, min_chars: int, max_chars: int) -> None:
        self._normalizer = normalizer
        self._min_chars = min_chars
        self._max_chars = max_chars

    def provide(self, raw_text: str) -> FetchOutcome:
        text = self._normalizer.normalize(raw_text)
        if len(text) < self._min_chars:
            return FetchOutcome(status=IngestionStatus.FAILED, message=f"The pasted job description is too short (minimum {self._min_chars} characters).")
        return FetchOutcome(status=IngestionStatus.OK, text=text[: self._max_chars])

class JobIngestionService:
    def __init__(self, url_fetcher: UrlJobFetcher, text_provider: PastedTextJobProvider, max_jobs: int) -> None:
        self._url_fetcher = url_fetcher
        self._text_provider = text_provider
        self._max_jobs = max_jobs

    async def ingest_many(self, inputs: list[JobInput]) -> list[JobPosting]:
        if not inputs:
            raise InvalidJobInputError("Add at least one job URL or pasted job description.")
        return list(await asyncio.gather(*(self.ingest(item) for item in inputs)))

    async def ingest(self, job_input: JobInput) -> JobPosting:
        if job_input.url:
            outcome = await self._url_fetcher.fetch(job_input.url)
            posting = self._posting(JobSourceType.URL, job_input, outcome)
        else:
            posting = self._posting(JobSourceType.TEXT, job_input, self._text_provider.provide(job_input.text or ""))
        logger.info("job_ingested", extra={"job_id": posting.id, "source": posting.source_type.value, "status": posting.ingestion_status.value})
        return posting

    def replace_text(self, posting: JobPosting, raw_text: str) -> JobPosting:
        outcome = self._text_provider.provide(raw_text)
        return posting.model_copy(update={"text": outcome.text, "ingestion_status": outcome.status, "message": outcome.message})

    @property
    def max_jobs(self) -> int:
        return self._max_jobs

    @staticmethod
    def _posting(source_type: JobSourceType, job_input: JobInput, outcome: FetchOutcome) -> JobPosting:
        return JobPosting(
            source_type=source_type,
            url=job_input.url,
            label=job_input.label,
            text=outcome.text,
            ingestion_status=outcome.status,
            message=outcome.message,
        )
