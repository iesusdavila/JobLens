from abc import ABC, abstractmethod
from langchain_anthropic import ChatAnthropic
from langchain_aws import ChatBedrockConverse
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from app.config.settings import Settings

class ChatModelFactory(ABC):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @abstractmethod
    def precise_model(self) -> BaseChatModel:
        raise NotImplementedError

    @abstractmethod
    def conversational_model(self) -> BaseChatModel:
        raise NotImplementedError

class BedrockChatModelFactory(ChatModelFactory):
    def precise_model(self) -> BaseChatModel:
        return self._create()

    def conversational_model(self) -> BaseChatModel:
        return self._create()

    def _create(self) -> ChatAnthropic:
        options: dict[str, object] = {
            "model": self._settings.bedrock_model_id,
            "base_url": self._settings.bedrock_endpoint,
            "api_key": self._settings.aws_bearer_token_bedrock.get_secret_value(),
            "max_tokens": self._settings.llm_max_tokens,
            "timeout": self._settings.llm_timeout_seconds,
            "max_retries": 2,
        }
        if self._settings.bedrock_temperature is not None:
            options["temperature"] = self._settings.bedrock_temperature
        return ChatAnthropic(**options)

class BedrockConverseChatModelFactory(ChatModelFactory):
    def precise_model(self) -> BaseChatModel:
        return self._create()

    def conversational_model(self) -> BaseChatModel:
        return self._create()

    def _create(self) -> ChatBedrockConverse:
        options: dict[str, object] = {
            "model_id": self._settings.bedrock_converse_model_id,
            "region_name": self._settings.bedrock_region,
            "bedrock_api_key": self._settings.aws_bearer_token_bedrock.get_secret_value(),
            "max_tokens": self._settings.llm_max_tokens,
        }
        if self._settings.bedrock_temperature is not None:
            options["temperature"] = self._settings.bedrock_temperature
        return ChatBedrockConverse(**options)

class GroqChatModelFactory(ChatModelFactory):
    def precise_model(self) -> BaseChatModel:
        return self._create(self._settings.groq_extraction_temperature)

    def conversational_model(self) -> BaseChatModel:
        return self._create(self._settings.groq_chat_temperature)

    def _create(self, temperature: float) -> ChatGroq:
        return ChatGroq(
            model=self._settings.groq_model,
            api_key=self._settings.groq_api_key.get_secret_value(),
            temperature=temperature,
            max_tokens=self._settings.llm_max_tokens,
            timeout=self._settings.llm_timeout_seconds,
            max_retries=2,
        )

class ChatModelFactoryResolver:
    def resolve(self, settings: Settings) -> ChatModelFactory:
        if settings.llm_provider == "groq":
            return GroqChatModelFactory(settings)
        if settings.uses_bedrock_converse:
            return BedrockConverseChatModelFactory(settings)
        return BedrockChatModelFactory(settings)
