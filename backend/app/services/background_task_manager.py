import asyncio
from collections.abc import Coroutine
from typing import Any

class BackgroundTaskManager:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def launch(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
