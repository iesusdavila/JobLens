import logging
from collections.abc import AsyncIterator
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import Runnable
from app.agents.chat.tools import WebSearchTool
from app.domain.enums import ChatRole
from app.domain.session_models import ChatMessage

logger = logging.getLogger(__name__)

class ChatReplyCollector:
    def __init__(self) -> None:
        self._parts: list[str] = []
        self.sources: list[str] = []

    def add_text(self, text: str) -> None:
        self._parts.append(text)

    def add_sources(self, sources: list[str]) -> None:
        self.sources.extend(source for source in sources if source not in self.sources)

    @property
    def text(self) -> str:
        return "".join(self._parts)

class ChatAgent:
    def __init__(self, model: BaseChatModel, web_search: WebSearchTool | None, max_tool_rounds: int) -> None:
        self._model = model
        self._web_search = web_search
        self._max_tool_rounds = max_tool_rounds
        self._bound_model: Runnable = model.bind_tools([web_search.as_langchain_tool()]) if web_search else model

    @property
    def web_search_enabled(self) -> bool:
        return self._web_search is not None

    async def stream(self, system_prompt: str, history: list[ChatMessage], user_message: str, collector: ChatReplyCollector) -> AsyncIterator[str]:
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt), *self._history(history), HumanMessage(content=user_message)]
        for round_index in range(self._max_tool_rounds + 1):
            model = self._bound_model if round_index < self._max_tool_rounds else self._model
            aggregate: AIMessageChunk | None = None
            async for chunk in model.astream(messages):
                aggregate = chunk if aggregate is None else aggregate + chunk
                text = self._text(chunk)
                if text:
                    collector.add_text(text)
                    yield text
            if aggregate is None or not aggregate.tool_calls:
                return
            messages.append(aggregate)
            for tool_call in aggregate.tool_calls:
                messages.append(await self._execute(tool_call, collector))

    async def _execute(self, tool_call: ToolCall, collector: ChatReplyCollector) -> ToolMessage:
        if self._web_search is None or tool_call["name"] != WebSearchTool.NAME:
            return ToolMessage(content=f"Unknown tool {tool_call['name']}.", tool_call_id=tool_call["id"])
        output = await self._web_search.search(str(tool_call["args"].get("query", "")))
        collector.add_sources(WebSearchTool.extract_links(output))
        logger.info("chat_tool_called", extra={"tool": tool_call["name"]})
        return ToolMessage(content=output, tool_call_id=tool_call["id"])

    @staticmethod
    def _history(history: list[ChatMessage]) -> list[BaseMessage]:
        return [HumanMessage(content=item.content) if item.role == ChatRole.USER else AIMessage(content=item.content) for item in history]

    @staticmethod
    def _text(chunk: AIMessageChunk) -> str:
        if isinstance(chunk.content, str):
            return chunk.content
        return "".join(part.get("text", "") for part in chunk.content if isinstance(part, dict) and part.get("type") == "text")
