import asyncio
import logging
from typing import TypeVar
import anthropic
import botocore.exceptions
import groq
import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from app.clients.chat_model_factory import ChatModelFactoryResolver
from app.config.settings import Settings
from app.core.exceptions import LlmOutputError, LlmServiceError

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)
LLM_TRANSPORT_ERRORS = (anthropic.APIError, groq.GroqError, botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError, httpx.HTTPError, asyncio.TimeoutError)

class MissingToolCallError(ValueError):
    pass

class LlmClient:
    STRUCTURED_INSTRUCTION = "\n\nDeliver your answer by calling the `{tool_name}` tool exactly once. Do not answer in plain text."

    def __init__(
        self,
        settings: Settings,
        precise_model: BaseChatModel | None = None,
        conversational_model: BaseChatModel | None = None,
    ) -> None:
        self._settings = settings
        factory = ChatModelFactoryResolver().resolve(settings) if precise_model is None or conversational_model is None else None
        self._precise_model = precise_model or factory.precise_model()
        self._conversational_model = conversational_model or factory.conversational_model()

    @property
    def agent_model(self) -> BaseChatModel:
        return self._precise_model

    @property
    def conversation_model(self) -> BaseChatModel:
        return self._conversational_model

    async def generate_structured(self, schema: type[SchemaT], system_prompt: str, user_prompt: str) -> SchemaT:
        runnable = self._precise_model.bind_tools([schema])
        base_messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt + self.STRUCTURED_INSTRUCTION.format(tool_name=schema.__name__)),
            HumanMessage(content=user_prompt),
        ]
        messages = base_messages
        last_error: Exception | None = None
        for attempt in range(1, self._settings.llm_schema_retries + 1):
            try:
                response = await runnable.ainvoke(messages)
                return schema.model_validate(self._tool_arguments(response, schema.__name__))
            except (ValidationError, OutputParserException, MissingToolCallError, groq.BadRequestError) as error:
                last_error = error
                logger.warning("llm_schema_retry", extra={"schema": schema.__name__, "attempt": attempt, "error_type": type(error).__name__})
                messages = [*base_messages, HumanMessage(content=self._schema_correction(schema.__name__, error))]
            except LLM_TRANSPORT_ERRORS as error:
                logger.warning("llm_call_failed", extra={"schema": schema.__name__, "error_type": type(error).__name__})
                raise LlmServiceError(self.describe_error(error)) from error
        raise LlmOutputError(f"The language model could not produce a valid {schema.__name__} after {self._settings.llm_schema_retries} attempts.") from last_error

    @staticmethod
    def _tool_arguments(response: AIMessage, tool_name: str) -> dict:
        call = next((item for item in response.tool_calls if item["name"] == tool_name), None)
        if call is None:
            raise MissingToolCallError(f"The model did not call the {tool_name} tool.")
        return call["args"]

    @staticmethod
    def _schema_correction(tool_name: str, error: Exception) -> str:
        return f"Your previous answer was invalid: {str(error)[:500]}. Answer again by calling the `{tool_name}` tool with arguments that follow its schema exactly."

    @staticmethod
    def describe_error(error: Exception) -> str:
        if isinstance(error, botocore.exceptions.ClientError):
            return LlmClient._describe_bedrock_error(error)
        if isinstance(error, (anthropic.AuthenticationError, groq.AuthenticationError)):
            return "The LLM provider rejected the credentials. Check AWS_BEARER_TOKEN_BEDROCK (or GROQ_API_KEY) in .env; Bedrock short-term keys expire after 12 hours."
        if isinstance(error, anthropic.PermissionDeniedError):
            return f"Amazon Bedrock denied access to the model: {str(error)[:200]}. Choose a model your account can use, or request access in the Bedrock console."
        if isinstance(error, (anthropic.NotFoundError, groq.NotFoundError)):
            return "The configured model id was not found on the Claude in Amazon Bedrock endpoint. Older models with versioned ids (for example anthropic.claude-sonnet-4-5-20250929-v1:0) are served through the Converse API; set BEDROCK_API=converse or use a versioned id. Also check GROQ_MODEL and BEDROCK_REGION."
        if isinstance(error, (anthropic.RateLimitError, groq.RateLimitError)):
            return "The LLM provider rate limit was reached. Wait a minute and retry."
        if isinstance(error, anthropic.BadRequestError):
            return f"The LLM provider rejected the request: {str(error)[:300]}"
        return "The LLM provider is unreachable or returned an error. Check BEDROCK_REGION, your network, and try again."

    @staticmethod
    def _describe_bedrock_error(error: botocore.exceptions.ClientError) -> str:
        code = error.response.get("Error", {}).get("Code", "")
        message = error.response.get("Error", {}).get("Message", "")
        if code in ("UnrecognizedClientException", "ExpiredTokenException") or "token" in message.lower() and "invalid" in message.lower():
            return "Amazon Bedrock rejected the API key. Check AWS_BEARER_TOKEN_BEDROCK in .env; short-term keys expire after 12 hours."
        if code == "AccessDeniedException":
            return f"Amazon Bedrock denied access to the model: {message[:200]}"
        if code in ("ResourceNotFoundException", "ValidationException"):
            return f"Amazon Bedrock rejected the model or request: {message[:250]}. Check BEDROCK_MODEL_ID and BEDROCK_REGION."
        if code in ("ThrottlingException", "ServiceQuotaExceededException"):
            return "Amazon Bedrock throttled the request. Wait a minute and retry."
        return f"Amazon Bedrock returned an error ({code or 'unknown'}). Try again in a moment."
