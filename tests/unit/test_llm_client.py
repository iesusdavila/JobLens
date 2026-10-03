from typing import Any
import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from app.clients.chat_model_factory import BedrockChatModelFactory, BedrockConverseChatModelFactory, ChatModelFactoryResolver, GroqChatModelFactory
from app.clients.llm_client import LlmClient
from app.config.settings import Settings
from app.core.exceptions import LlmOutputError
from app.domain.job_models import ParsedJob
from tests.conftest import build_settings

class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    bound_kwargs: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "ScriptedModel":
        self.bound_kwargs.append(kwargs)
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])

def tool_reply(args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "ParsedJob", "args": args, "id": "t1", "type": "tool_call"}])

async def test_structured_output_uses_auto_tool_choice_and_retries(tmp_path: object) -> None:
    model = ScriptedModel(replies=[AIMessage(content="plain text answer"), tool_reply({"title": "Data Engineer", "must_have_requirements": ["SQL"]})], bound_kwargs=[])
    client = LlmClient(build_settings(tmp_path), precise_model=model, conversational_model=model)
    parsed = await client.generate_structured(ParsedJob, "system", "user")
    assert parsed.title == "Data Engineer"
    assert model.bound_kwargs == [{}]

async def test_structured_output_gives_up_after_retries(tmp_path: object) -> None:
    model = ScriptedModel(replies=[AIMessage(content="no")] * 3, bound_kwargs=[])
    client = LlmClient(build_settings(tmp_path, llm_schema_retries=3), precise_model=model, conversational_model=model)
    with pytest.raises(LlmOutputError):
        await client.generate_structured(ParsedJob, "system", "user")

def test_bedrock_factory_targets_messages_endpoint_without_sampling(tmp_path: object) -> None:
    settings = build_settings(tmp_path, bedrock_region="eu-west-1", bedrock_model_id="anthropic.claude-sonnet-5-5")
    model = BedrockChatModelFactory(settings).precise_model()
    assert model.model == "anthropic.claude-sonnet-5-5"
    assert model.anthropic_api_url == "https://bedrock-mantle.eu-west-1.api.aws/anthropic"
    assert model.temperature is None
    assert model.max_tokens == 16000

def test_provider_selection_and_required_keys(tmp_path: object) -> None:
    groq_settings = build_settings(tmp_path, llm_provider="groq", groq_api_key="", aws_bearer_token_bedrock="")
    assert isinstance(ChatModelFactoryResolver().resolve(groq_settings), GroqChatModelFactory)
    assert groq_settings.missing_required_keys() == ["GROQ_API_KEY"]
    bedrock_settings = Settings(_env_file=None, typesafe_api_key="k", aws_bearer_token_bedrock="")
    assert bedrock_settings.missing_required_keys() == ["AWS_BEARER_TOKEN_BEDROCK"]
    assert bedrock_settings.llm_model == "anthropic.claude-opus-5-5"

def test_versioned_bedrock_ids_use_converse_with_inference_profile(tmp_path: object) -> None:
    settings = build_settings(tmp_path, bedrock_model_id="anthropic.claude-sonnet-4-5-20250929-v1:0", bedrock_region="us-east-1")
    factory = ChatModelFactoryResolver().resolve(settings)
    assert isinstance(factory, BedrockConverseChatModelFactory)
    model = factory.precise_model()
    assert model.model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert settings.llm_model == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    explicit = build_settings(tmp_path, bedrock_model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0")
    assert explicit.bedrock_converse_model_id == "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert isinstance(ChatModelFactoryResolver().resolve(build_settings(tmp_path)), BedrockChatModelFactory)
