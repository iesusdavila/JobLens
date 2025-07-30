from utils.react_state import State
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from utils.nodes import (
    extract_cv_content, validate_cv_structure,
    provide_feedback, person_is_postuled_to_job,
    ask_info_about_job, create_cv_summary,
    analyze_cv_job_compatibility, route_after_validation,
    route_after_postuling_to_job
)

workflow = StateGraph(State)

workflow.add_node("extract_content", extract_cv_content)
workflow.add_node("validate_structure", validate_cv_structure)
workflow.add_node("provide_feedback", provide_feedback)
workflow.add_node("person_is_postuled_to_job", person_is_postuled_to_job)
workflow.add_node("ask_info_about_job", ask_info_about_job)
workflow.add_node("create_summary", create_cv_summary)
workflow.add_node("analyze_compatibility", analyze_cv_job_compatibility)

workflow.set_entry_point("extract_content")
workflow.add_edge("extract_content", "validate_structure")
workflow.add_conditional_edges("validate_structure", route_after_validation)
workflow.add_conditional_edges("person_is_postuled_to_job", route_after_postuling_to_job)
workflow.add_edge("ask_info_about_job", "analyze_compatibility")
workflow.add_edge("analyze_compatibility", END)
workflow.add_edge("provide_feedback", END)
workflow.add_edge("create_summary", END)

checkpointer = MemorySaver()

app = workflow.compile(checkpointer=checkpointer)