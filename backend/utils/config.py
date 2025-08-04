from langchain_core.messages import HumanMessage

THREAD_CONFIG = {"configurable": {"thread_id": 1}}

INITIAL_STATE = {
    "messages": [HumanMessage(content="Analizar CV")],
    "cv_content": "",
    "is_cv_valid": False,
    "feedback": "",
    "summary": "",
    "person_is_postuled_to_job": False,
    "job_info": "",
    "cv_file_path": ""
}
