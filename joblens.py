from utils.config import THREAD_CONFIG, INITIAL_STATE
from utils.state_graph import app

result = app.invoke(INITIAL_STATE, config=THREAD_CONFIG)
print(result)