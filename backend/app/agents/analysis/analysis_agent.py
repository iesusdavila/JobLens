import logging
from typing import Any, Literal
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from app.agents.analysis.agent_state import AnalysisAgentState
from app.agents.analysis.finalizer import AnalysisFinalizer
from app.agents.analysis.prompts import AnalysisPrompts
from app.agents.analysis.stop_policy import AgentStopPolicy, NextStepAdvisor
from app.agents.analysis.tools import AnalysisToolkit
from app.clients.llm_client import LLM_TRANSPORT_ERRORS, LlmClient
from app.domain.analysis_models import JobAnalysisResult
from app.domain.document_models import ParsedDocument
from app.domain.enums import AgentStatus, JobAnalysisStatus
from app.domain.job_models import JobPosting
from app.domain.session_models import CandidatePreferences

logger = logging.getLogger(__name__)

class AnalysisAgent:
    def __init__(
        self,
        llm_client: LlmClient,
        toolkit: AnalysisToolkit,
        finalizer: AnalysisFinalizer,
        stop_policy: AgentStopPolicy,
        advisor: NextStepAdvisor,
        recursion_limit: int,
    ) -> None:
        self._tools = toolkit.tools()
        self._tool_node = ToolNode(self._tools)
        self._model = llm_client.agent_model.bind_tools(self._tools)
        self._finalizer = finalizer
        self._stop_policy = stop_policy
        self._advisor = advisor
        self._recursion_limit = recursion_limit
        self._graph = self._build_graph()

    async def run(
        self,
        session_id: str,
        job: JobPosting,
        cv: ParsedDocument,
        extra: ParsedDocument | None,
        preferences: CandidatePreferences,
    ) -> JobAnalysisResult:
        initial: AnalysisAgentState = {
            "messages": [HumanMessage(content=f"Analyze the job posting '{job.display_name}' (job id {job.id}) for the candidate. Begin.")],
            "session_id": session_id,
            "job": job,
            "cv_document": cv,
            "extra_document": extra,
            "preferences": preferences,
            "iteration": 0,
            "agent_steps": 0,
            "nudges": 0,
            "tool_errors": 0,
            "warnings": [],
            "last_feedback": [],
            "status": AgentStatus.RUNNING,
        }
        try:
            final_state = await self._graph.ainvoke(initial, config={"recursion_limit": self._recursion_limit})
        except GraphRecursionError:
            logger.error("agent_recursion_limit", extra={"job_id": job.id})
            return JobAnalysisResult(job_id=job.id, status=JobAnalysisStatus.FAILED, job_name=job.display_name, error="The analysis agent exceeded its step budget.")
        return final_state["result"]

    def _build_graph(self) -> Any:
        graph = StateGraph(AnalysisAgentState)
        graph.add_node("agent", self._agent_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("nudge", self._nudge_node)
        graph.add_node("force_finalize", self._force_finalize_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self._route_after_agent, ["tools", "nudge", "force_finalize"])
        graph.add_conditional_edges("tools", self._route_after_tools, ["agent", END])
        graph.add_edge("nudge", "agent")
        graph.add_edge("force_finalize", END)
        return graph.compile()

    async def _agent_node(self, state: AnalysisAgentState) -> dict[str, Any]:
        steps = state.get("agent_steps", 0)
        if self._stop_policy.steps_exhausted(steps):
            return {"agent_failed": True, "last_error": state.get("last_error") or "The agent step budget was exhausted."}
        try:
            response = await self._model.ainvoke([SystemMessage(content=AnalysisPrompts.AGENT_SYSTEM), *state["messages"]])
        except LLM_TRANSPORT_ERRORS as error:
            logger.warning("agent_model_failed", extra={"job_id": state["job"].id, "error_type": type(error).__name__})
            return {"agent_failed": True, "last_error": LlmClient.describe_error(error)}
        logger.info("agent_step", extra={"job_id": state["job"].id, "step": steps + 1, "tools": [call["name"] for call in response.tool_calls]})
        return {"messages": [response], "agent_steps": steps + 1}

    async def _tools_node(self, state: AnalysisAgentState, config: RunnableConfig) -> list[Command]:
        last_message: AIMessage = state["messages"][-1]
        first_call, *extra_calls = last_message.tool_calls
        single_call = last_message.model_copy(update={"tool_calls": [first_call]})
        executed = await self._tool_node.ainvoke({**state, "messages": [*state["messages"][:-1], single_call]}, config)
        outputs = executed if isinstance(executed, list) else [executed]
        commands = [item if isinstance(item, Command) else Command(update=item) for item in outputs]
        if extra_calls:
            commands.append(Command(update={"messages": [self._skipped(call) for call in extra_calls]}))
        return commands

    def _nudge_node(self, state: AnalysisAgentState) -> dict[str, Any]:
        next_step = self._advisor.suggest(state)
        return {
            "messages": [HumanMessage(content=f"You have not finished. Continue by calling a tool. Suggested next tool: {next_step}.")],
            "nudges": state.get("nudges", 0) + 1,
        }

    def _force_finalize_node(self, state: AnalysisAgentState) -> dict[str, Any]:
        reason = f"The agent stopped before finishing: {state.get('last_error') or 'it ended without calling finalize_outputs'}."
        return {"result": self._finalizer.finalize(state, forced=True, reason=reason), "status": AgentStatus.FINALIZED}

    def _route_after_agent(self, state: AnalysisAgentState) -> Literal["tools", "nudge", "force_finalize"]:
        if state.get("agent_failed"):
            return "force_finalize"
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        if self._stop_policy.nudges_exhausted(state.get("nudges", 0)):
            return "force_finalize"
        return "nudge"

    @staticmethod
    def _route_after_tools(state: AnalysisAgentState) -> str:
        return END if state.get("status") == AgentStatus.FINALIZED else "agent"

    @staticmethod
    def _skipped(tool_call: dict[str, Any]) -> ToolMessage:
        return ToolMessage(
            content="STATUS: SKIPPED\nOnly one tool runs per turn. Call this tool again in a later turn if it is still needed.",
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
        )
