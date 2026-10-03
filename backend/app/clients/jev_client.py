import asyncio
import json
import logging
from collections.abc import Sequence
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    Noul,
    NoulCriteria,
    RetryPolicy,
    Score,
    SystemOneResponse,
    TypeSafeAPIError,
    TypeSafeError,
)
from app.clients.jev_questions import ChoiceQuestion, JevQuestion, JevState, NoulQuestion, ScoreQuestion
from app.config.settings import Settings
from app.core.exceptions import ConfigurationError, JevServiceError, JevStateTooLargeError
from app.domain.validation_models import ChoiceResult, JevEvaluation, NoulResult, ScoreResult

logger = logging.getLogger(__name__)

class JevQuestionTranslator:
    def to_sdk(self, questions: Sequence[JevQuestion]) -> dict[str, Noul | Choice | Score]:
        return {question.key: self._translate(question) for question in questions}

    def _translate(self, question: JevQuestion) -> Noul | Choice | Score:
        if isinstance(question, NoulQuestion):
            return self._noul(question)
        if isinstance(question, ChoiceQuestion):
            return Choice(instructions=question.instructions, criteria=dict(question.options))
        return Score(instructions=question.instructions, criteria=list(question.levels))

    def _noul(self, question: NoulQuestion) -> Noul:
        if question.true_criteria and question.false_criteria:
            criteria = NoulCriteria(true=question.true_criteria, false=question.false_criteria)
            return Noul(instructions=question.instructions, criteria=criteria)
        return Noul(instructions=question.instructions)

class JevResponseTranslator:
    def to_evaluation(self, response: SystemOneResponse, levels_by_key: dict[str, int]) -> JevEvaluation:
        nouls = {
            key: NoulResult(probability=answer.noul, confidence=self.noul_confidence(answer.noul))
            for key, answer in response.nouls.items()
        }
        choices = {
            key: ChoiceResult(choice=str(answer.choice), probabilities=self._string_keys(answer.probabilities), confidence=answer.confidence)
            for key, answer in response.choices.items()
        }
        scores = {
            key: ScoreResult(
                score=answer.score,
                normalized=self._normalize(answer.score, levels_by_key.get(key, len(answer.probabilities))),
                probabilities=self._string_keys(answer.probabilities),
                legend={str(level): str(description) for level, description in answer.legend.items()},
                confidence=answer.confidence,
            )
            for key, answer in response.scores.items()
        }
        return JevEvaluation(nouls=nouls, choices=choices, scores=scores)

    @staticmethod
    def _string_keys(values: dict) -> dict[str, float]:
        return {str(key): float(value) for key, value in values.items()}

    @staticmethod
    def noul_confidence(probability: float) -> float:
        return abs(2 * probability - 1)

    @staticmethod
    def _normalize(score: float, level_count: int) -> float:
        if level_count <= 1:
            return 0.0
        return max(0.0, min(1.0, score / (level_count - 1)))

class JevClient:
    def __init__(
        self,
        settings: Settings,
        sdk_client: AsyncTypeSafeClient | None = None,
        question_translator: JevQuestionTranslator | None = None,
        response_translator: JevResponseTranslator | None = None,
    ) -> None:
        self._settings = settings
        self._question_translator = question_translator or JevQuestionTranslator()
        self._response_translator = response_translator or JevResponseTranslator()
        self._semaphore = asyncio.Semaphore(settings.jev_max_concurrent_calls)
        self._sdk_client = sdk_client or self._create_sdk_client(settings)

    @property
    def max_state_chars(self) -> int:
        return self._settings.jev_max_state_chars

    async def evaluate(self, state: JevState, questions: Sequence[JevQuestion]) -> JevEvaluation:
        if not questions:
            return JevEvaluation()
        self._ensure_state_fits(state)
        batches = self._batch(questions)
        evaluations = await asyncio.gather(*(self._evaluate_batch(state, batch) for batch in batches))
        merged = JevEvaluation()
        for evaluation in evaluations:
            merged = merged.merge(evaluation)
        return merged

    async def aclose(self) -> None:
        await self._sdk_client.aclose()

    async def _evaluate_batch(self, state: JevState, questions: Sequence[JevQuestion]) -> JevEvaluation:
        levels_by_key = {question.key: len(question.levels) for question in questions if isinstance(question, ScoreQuestion)}
        async with self._semaphore:
            try:
                response = await self._sdk_client.system_one(state, self._question_translator.to_sdk(questions))
            except TypeSafeAPIError as error:
                logger.warning("jev_call_failed", extra={"status": error.status, "request_id": error.request_id})
                raise JevServiceError(f"Jev validation service returned HTTP {error.status}. Try again in a moment.") from error
            except TypeSafeError as error:
                logger.warning("jev_call_failed", extra={"error_type": type(error).__name__})
                raise JevServiceError("Jev validation service is unreachable. Check your network and TYPESAFE_API_KEY.") from error
        logger.info("jev_call_completed", extra={"questions": len(questions), "model": response.model, "request_id": response.request_id})
        return self._response_translator.to_evaluation(response, levels_by_key)

    def _batch(self, questions: Sequence[JevQuestion]) -> list[Sequence[JevQuestion]]:
        size = self._settings.jev_max_questions_per_call
        return [questions[index:index + size] for index in range(0, len(questions), size)]

    def _ensure_state_fits(self, state: JevState) -> None:
        size = len(state) if isinstance(state, str) else len(json.dumps(state, ensure_ascii=False))
        if size > self._settings.jev_max_state_chars:
            raise JevStateTooLargeError(f"Validation state has {size} characters, above the {self._settings.jev_max_state_chars} limit.")

    @staticmethod
    def _create_sdk_client(settings: Settings) -> AsyncTypeSafeClient:
        retry = RetryPolicy(max_retries=settings.jev_max_retries, timeout=settings.jev_timeout_seconds * (settings.jev_max_retries + 1))
        try:
            return AsyncTypeSafeClient(
                api_key=settings.typesafe_api_key.get_secret_value(),
                model=settings.typesafe_default_model,
                base_url=settings.typesafe_base_url,
                retry=retry,
                timeout=settings.jev_timeout_seconds,
            )
        except TypeSafeError as error:
            raise ConfigurationError("TYPESAFE_API_KEY is missing or malformed. Set a valid Jev key in .env.") from error
