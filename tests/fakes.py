import re
import httpx
from collections.abc import Callable, Sequence
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel
from app.clients.llm_client import LlmClient
from app.clients.jev_client import JevClient
from app.clients.jev_questions import ChoiceQuestion, JevQuestion, JevState, NoulQuestion, ScoreQuestion
from app.domain.validation_models import ChoiceResult, JevEvaluation, NoulResult, ScoreResult

class FakeJevClient(JevClient):
    FABRICATION_MARKER = "FABRICATED"

    def __init__(self, overrides: dict[str, float] | None = None, max_state_chars: int = 60000) -> None:
        self._overrides = overrides or {}
        self._max_state_chars = max_state_chars
        self.calls: list[tuple[JevState, list[JevQuestion]]] = []

    @property
    def max_state_chars(self) -> int:
        return self._max_state_chars

    async def evaluate(self, state: JevState, questions: Sequence[JevQuestion]) -> JevEvaluation:
        self.calls.append((state, list(questions)))
        evaluation = JevEvaluation()
        for question in questions:
            if isinstance(question, NoulQuestion):
                probability = self._noul(state, question)
                evaluation.nouls[question.key] = NoulResult(probability=probability, confidence=abs(2 * probability - 1))
            elif isinstance(question, ChoiceQuestion):
                evaluation.choices[question.key] = self._choice(question)
            elif isinstance(question, ScoreQuestion):
                evaluation.scores[question.key] = self._score(question)
        return evaluation

    async def aclose(self) -> None:
        return None

    def _noul(self, state: JevState, question: NoulQuestion) -> float:
        if question.key in self._overrides:
            return self._overrides[question.key]
        instructions = question.instructions if isinstance(question.instructions, dict) else {}
        state_text = str(state).lower()
        if "term" in instructions:
            return 0.9 if str(instructions["term"]).lower() in str(state.get("cv", "")).lower() else 0.1
        if "claim" in instructions:
            return 0.05 if self.FABRICATION_MARKER in instructions["claim"] else 0.92
        if "requirement" in instructions:
            tokens = [token for token in re.findall(r"[a-z0-9+#]{3,}", instructions["requirement"].lower()) if token not in {"years", "experience", "with", "and"}]
            return 0.85 if any(token in state_text for token in tokens) else 0.1
        if question.key == "filler_present":
            return 0.1
        if question.key == "relevance_ordering":
            return 0.8
        return 0.05

    def _choice(self, question: ChoiceQuestion) -> ChoiceResult:
        options = list(question.options)
        chosen = "matches" if "matches" in options else options[0]
        probabilities = {option: (0.8 if option == chosen else 0.2 / (len(options) - 1)) for option in options}
        return ChoiceResult(choice=chosen, probabilities=probabilities, confidence=0.7)

    def _score(self, question: ScoreQuestion) -> ScoreResult:
        level_count = len(question.levels)
        target = level_count - 2
        probabilities = {str(index): (0.8 if index == target else 0.2 / (level_count - 1)) for index in range(level_count)}
        score = sum(index * probability for index, probability in enumerate(probabilities.values()))
        return ScoreResult(
            score=score,
            normalized=score / (level_count - 1),
            probabilities=probabilities,
            legend={str(index): level for index, level in enumerate(question.levels)},
            confidence=0.75,
        )

class PolicyAgentModel(BaseChatModel):
    calls: int = 0
    fail: bool = False
    stop_without_tools_after: int | None = None
    duplicate_tool_calls: bool = False

    @property
    def _llm_type(self) -> str:
        return "policy-agent-fake"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "PolicyAgentModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("Groq is down")
        if self.stop_without_tools_after is not None and self.calls > self.stop_without_tools_after:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="I am done."))])
        tool_name = self._next_tool(messages)
        tool_calls = [{"name": tool_name, "args": {}, "id": f"call_{self.calls}", "type": "tool_call"}]
        if self.duplicate_tool_calls:
            tool_calls.append({"name": "finalize_outputs", "args": {}, "id": f"call_{self.calls}_extra", "type": "tool_call"})
        message = AIMessage(content="", tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @staticmethod
    def _next_tool(messages: list[BaseMessage]) -> str:
        tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
        tool_messages = [message for message in tool_messages if "STATUS: SKIPPED" not in str(message.content)]
        called = {message.name for message in tool_messages if "STATUS: OK" in str(message.content) or "STATUS: READY" in str(message.content) or "STATUS: NEEDS" in str(message.content)}
        for name in ("extract_job_requirements", "parse_candidate_profile", "run_fit_validation", "draft_tailored_cv", "run_cv_validation"):
            if name not in called:
                return name
        last = tool_messages[-1] if tool_messages else None
        content = str(last.content) if last else ""
        if "READY_TO_FINALIZE" in content or "ITERATION_CAP_REACHED" in content or "STATUS: ERROR" in content:
            return "finalize_outputs"
        if last is not None and last.name == "draft_tailored_cv":
            return "run_cv_validation"
        return "draft_tailored_cv"

class FakeLlmClient(LlmClient):
    def __init__(self, responders: dict[type, Callable[[int], BaseModel]], agent_model: BaseChatModel, conversation_model: BaseChatModel) -> None:
        self._responders = responders
        self._precise_model = agent_model
        self._conversational_model = conversation_model
        self.structured_calls: dict[type, int] = {}

    async def generate_structured(self, schema: type, system_prompt: str, user_prompt: str) -> Any:
        count = self.structured_calls.get(schema, 0) + 1
        self.structured_calls[schema] = count
        return self._responders[schema](count)
