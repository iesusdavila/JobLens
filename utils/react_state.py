from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]
    cv_content: str
    is_cv_valid: bool
    feedback: str
    summary: str
    person_is_postuled_to_job: Optional[bool]
    job_info: Optional[str]