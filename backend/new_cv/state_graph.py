from new_cv.react_state import ImproveCVState
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from new_cv.nodes import (
    extract_cv_sections,
    improve_cv_structure,
    format_improved_cv
)

improve_workflow = StateGraph(ImproveCVState)

improve_workflow.add_node("extract_sections", extract_cv_sections)
improve_workflow.add_node("improve_structure", improve_cv_structure)
improve_workflow.add_node("format_cv", format_improved_cv)

improve_workflow.set_entry_point("extract_sections")
improve_workflow.add_edge("extract_sections", "improve_structure")
improve_workflow.add_edge("improve_structure", "format_cv")
improve_workflow.add_edge("format_cv", END)

improve_checkpointer = MemorySaver()

improve_cv_app = improve_workflow.compile(checkpointer=improve_checkpointer)