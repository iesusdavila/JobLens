import uvicorn
from fastapi import FastAPI
from langserve import add_routes
from utils.state_graph import app
from langchain_core.runnables import RunnableLambda
from utils.config import THREAD_CONFIG, INITIAL_STATE

def simple_llm_wrapper(info: dict):
    person_is_postuled_to_job = info.get("person_is_postuled_to_job", True)
    job_info = info.get("job_info", None)

    state = {
        **INITIAL_STATE,
        "person_is_postuled_to_job": person_is_postuled_to_job,
        "job_info": job_info
    }
    return app.invoke(state, config=THREAD_CONFIG)

simple_llm_chain = RunnableLambda(simple_llm_wrapper)

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

if __name__=="__main__":
    uvicorn.run(server, host="localhost", port=8000)