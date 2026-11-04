from __future__ import annotations

import asyncio

from app.ports.job_queue import JobHandler


class LocalJobQueue:
    name = "local"

    def __init__(self, concurrency: int = 2, maxsize: int = 0) -> None:
        self.concurrency = max(0, int(concurrency or 0))
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self._handler: JobHandler | None = None
        self._workers: list[asyncio.Task] = []
        self._closed = False
        self._running = 0

    def enqueue(self, job_id: str) -> None:
        self._queue.put_nowait(job_id)

    def start(self, handler: JobHandler) -> None:
        self._handler = handler
        self._closed = False
        if self.concurrency <= 0:
            return
        loop = asyncio.get_event_loop()
        for index in range(self.concurrency):
            task = loop.create_task(self._worker(index), name=f"job-worker-{index}")
            self._workers.append(task)

    async def _worker(self, index: int) -> None:
        while not self._closed:
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                break
            self._running += 1
            try:
                if self._handler is not None:
                    await self._handler(job_id)
            except asyncio.CancelledError:
                self._running -= 1
                self._queue.task_done()
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[queue] worker {index} 任务 {job_id} 异常: {exc!r}")
            finally:
                self._running = max(0, self._running - 1)
                self._queue.task_done()

    async def aclose(self) -> None:
        self._closed = True
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._workers = []

    def stats(self) -> dict[str, int]:
        return {
            "pending": self._queue.qsize(),
            "running": self._running,
            "concurrency": self.concurrency,
        }

    def healthcheck(self) -> bool:
        return True


class NullJobEventBus:
    name = "none"

    def publish(self, job_id: str, payload: dict) -> None:
        return None

    async def subscribe(self, job_id: str):
        if False:
            yield {}
        return

    async def aclose(self) -> None:
        return None

    def healthcheck(self) -> bool:
        return True
