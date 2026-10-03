import json
import logging
import httpx
from ddgs.exceptions import DDGSException
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class WebSearchResult(BaseModel):
    title: str
    link: str
    snippet: str

class WebSearchTool:
    NAME = "web_search"
    UNAVAILABLE = "WEB_SEARCH_UNAVAILABLE: the search failed. Tell the user you could not verify live information."

    def __init__(self, max_results: int, backend: DuckDuckGoSearchResults | None = None) -> None:
        self._backend = backend or DuckDuckGoSearchResults(max_results=max_results, output_format="list")

    def as_langchain_tool(self) -> BaseTool:
        return StructuredTool.from_function(
            coroutine=self.search,
            name=self.NAME,
            description="Search the web for live information about companies, reputation, news, culture, salaries or similar roles. Input: a focused search query.",
        )

    async def search(self, query: str) -> str:
        try:
            raw = await self._backend.ainvoke(query)
        except (DDGSException, httpx.HTTPError, TimeoutError, ValueError) as error:
            logger.warning("web_search_failed", extra={"error_type": type(error).__name__})
            return self.UNAVAILABLE
        results = self._parse(raw)
        if not results:
            return "WEB_SEARCH_EMPTY: no results were found."
        logger.info("web_search_completed", extra={"results": len(results)})
        return json.dumps([result.model_dump() for result in results], ensure_ascii=False)

    @staticmethod
    def _parse(raw: object) -> list[WebSearchResult]:
        if not isinstance(raw, list):
            return []
        return [
            WebSearchResult(title=str(item.get("title", "")), link=str(item.get("link", "")), snippet=str(item.get("snippet", "")))
            for item in raw if isinstance(item, dict) and item.get("link")
        ]

    @staticmethod
    def extract_links(tool_output: str) -> list[str]:
        try:
            items = json.loads(tool_output)
        except json.JSONDecodeError:
            return []
        return [f"{item.get('title', '')} - {item['link']}" for item in items if isinstance(item, dict) and item.get("link")]
