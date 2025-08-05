import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from langserve import add_routes
from utils.state_graph import app
from new_cv.state_graph import improve_cv_app
from langchain_core.runnables import RunnableLambda
from utils.config import THREAD_CONFIG, INITIAL_STATE

class ImproveCVRequest(BaseModel):
    cv_content: str
    feedback: str
    cv_file_path: str

def improve_cv_wrapper(info: dict):
    cv_content = info.get("cv_content", "")
    feedback = info.get("feedback", "")
    cv_file_path = info.get("cv_file_path", "")
    
    state = {
        "cv_content": cv_content,
        "feedback": feedback,
        "cv_file_path": cv_file_path,
        "improved_cv": ""
    }
    
    return improve_cv_app.invoke(state, config=THREAD_CONFIG)


def simple_llm_wrapper(info: dict):
    person_is_postuled_to_job = info.get("person_is_postuled_to_job", True)
    job_info = info.get("job_info", None)
    cv_file_path = info.get("cv_file_path", "")

    state = {
        **INITIAL_STATE,
        "person_is_postuled_to_job": person_is_postuled_to_job,
        "job_info": job_info,
        "cv_file_path": cv_file_path
    }
    return app.invoke(state, config=THREAD_CONFIG)

simple_llm_chain = RunnableLambda(simple_llm_wrapper)
improve_cv_chain = RunnableLambda(improve_cv_wrapper)

server=FastAPI(
    title="Langchain Server",
    version="1.0",
    description="A simple API Server"
)

add_routes(
    server,
    simple_llm_chain,
    path="/joblens",
)

add_routes(
    server,
    improve_cv_chain,
    path="/joblens/improve-cv",
)

if __name__=="__main__":
    uvicorn.run(server, host="localhost", port=8000)