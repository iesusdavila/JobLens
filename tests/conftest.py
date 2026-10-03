import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from app.api.dependencies import ServiceContainer
from app.config.settings import Settings
from app.domain.cv_models import TailoredCvDraft
from app.domain.job_models import ParsedJob
from app.domain.profile_models import CandidateProfile
from tests.fakes import FakeLlmClient, FakeJevClient, PolicyAgentModel
from tests.sample_data import candidate_profile, parsed_job, tailored_draft

def build_settings(tmp_path: object, **overrides: object) -> Settings:
    values = {
        "typesafe_api_key": "ts_test_key",
        "aws_bearer_token_bedrock": "bedrock_test_token",
        "enable_web_search": False,
        "respect_robots_txt": False,
        "max_agent_iterations": 3,
        "session_storage_path": tmp_path,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)

def build_llm(agent_model: PolicyAgentModel | None = None, fabricate_always: bool = False, chat_replies: list[str] | None = None) -> FakeLlmClient:
    replies = iter([AIMessage(content=text) for text in (chat_replies or ["Hello from the assistant."] * 4)])
    return FakeLlmClient(
        responders={
            ParsedJob: lambda count: parsed_job(),
            CandidateProfile: lambda count: candidate_profile(),
            TailoredCvDraft: lambda count: tailored_draft(fabricate=fabricate_always or count == 1),
        },
        agent_model=agent_model or PolicyAgentModel(),
        conversation_model=GenericFakeChatModel(messages=replies),
    )

@pytest.fixture
def settings(tmp_path: object) -> Settings:
    return build_settings(tmp_path)

@pytest.fixture
def fake_jev() -> FakeJevClient:
    return FakeJevClient()

@pytest.fixture
def container_factory(tmp_path: object):
    created: list[ServiceContainer] = []

    def factory(llm: FakeLlmClient | None = None, jev: FakeJevClient | None = None, **settings_overrides: object) -> ServiceContainer:
        container = ServiceContainer(build_settings(tmp_path, **settings_overrides), jev_client=jev or FakeJevClient(), llm_client=llm or build_llm())
        created.append(container)
        return container

    return factory
