from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from app.ports.job_queue import JobHandler

QUEUE_KEY = "cs:jobs:queue"
CLAIM_PREFIX = "cs:jobs:claimed:"
ATTEMPT_PREFIX = "cs:jobs:attempts:"
EVENT_CHANNEL_PREFIX = "cs:jobs:events:"


class RedisJobQueue:
    name = "redis"

    def __init__(
        self,
        url: str = "",
        concurrency: int = 2,
        max_attempts: int = 3,
        brpop_timeout: int = 2,
        queue_key: str = QUEUE_KEY,
    ) -> None:
        self.url = url
        self.concurrency = max(1, int(concurrency or 1))
        self.max_attempts = max(1, int(max_attempts or 1))
        self.brpop_timeout = max(1, int(brpop_timeout or 1))
        self.queue_key = queue_key
        self._client = None
        self._handler: JobHandler | None = None
        self._workers: list[asyncio.Task] = []
        self._closed = False
        self._running = 0
        self._requeue: list[str] = []

    def client(self):
        if self._client is not None:
            return self._client
        import redis

        client = redis.Redis.from_url(self.url, decode_responses=True)
        client.ping()
        self._client = client
        return client

    def enqueue(self, job_id: str) -> None:
        self.client().lpush(self.queue_key, job_id)

    def start(self, handler: JobHandler) -> None:
        self._handler = handler
        self._closed = False
        self.client()
        loop = asyncio.get_event_loop()
        for index in range(self.concurrency):
            task = loop.create_task(self._worker(index), name=f"redis-job-worker-{index}")
            self._workers.append(task)

    async def _worker(self, index: int) -> None:
        loop = asyncio.get_event_loop()
        while not self._closed:
            job_id = None
            try:
                item = await loop.run_in_executor(
                    None, lambda: self.client().brpop(self.queue_key, self.brpop_timeout)
                )
                if not item:
                    await asyncio.sleep(0)
                    continue
                job_id = item[1]
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"[queue] redis worker {index} 取任务失败: {exc!r}")
                await asyncio.sleep(1)
                continue
            claim_key = CLAIM_PREFIX + job_id
            try:
                claimed = self.client().set(claim_key, "1", nx=True, ex=86400)
            except Exception as exc:
                print(f"[queue] redis claim 失败 {job_id}: {exc!r}")
                continue
            if not claimed:
                print(f"[queue] 任务 {job_id} 已被其它实例领取，跳过")
                continue
            self._running += 1
            try:
                if self._handler is not None:
                    await self._handler(job_id)
            except asyncio.CancelledError:
                self._running = max(0, self._running - 1)
                break
            except Exception as exc:
                print(f"[queue] redis worker {index} 任务 {job_id} 异常: {exc!r}")
                self._retry(job_id)
            finally:
                self._running = max(0, self._running - 1)

    def _retry(self, job_id: str) -> None:
        try:
            client = self.client()
            attempts = int(client.incr(ATTEMPT_PREFIX + job_id))
            if attempts < self.max_attempts:
                client.delete(CLAIM_PREFIX + job_id)
                client.lpush(self.queue_key, job_id)
                print(f"[queue] 任务 {job_id} 第 {attempts} 次失败，重新入队")
        except Exception as exc:
            print(f"[queue] 任务 {job_id} 重试入队失败: {exc!r}")

    async def aclose(self) -> None:
        self._closed = True
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._workers = []
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def stats(self) -> dict[str, int]:
        try:
            length = int(self.client().llen(self.queue_key))
        except Exception:
            length = 0
        return {"pending": length, "running": self._running, "concurrency": self.concurrency}

    def healthcheck(self) -> bool:
        try:
            return bool(self.client().ping())
        except Exception:
            return False


class RedisJobEventBus:
    name = "redis"

    def __init__(self, url: str = "", client=None) -> None:
        self.url = url
        self._client = client

    def client(self):
        if self._client is not None:
            return self._client
        import redis

        client = redis.Redis.from_url(self.url, decode_responses=True)
        client.ping()
        self._client = client
        return client

    def channel(self, job_id: str) -> str:
        return EVENT_CHANNEL_PREFIX + job_id

    def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        try:
            body = json.dumps(payload, ensure_ascii=False)
            self.client().publish(self.channel(job_id), body)
        except Exception as exc:
            print(f"[jobs] 事件发布失败 {job_id}: {exc!r}")

    async def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        pubsub = self.client().pubsub(ignore_subscribe_messages=True)
        await loop.run_in_executor(None, lambda: pubsub.subscribe(self.channel(job_id)))
        try:
            while True:
                message = await loop.run_in_executor(
                    None, lambda: pubsub.get_message(timeout=1.0)
                )
                if not message:
                    yield {}
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    parsed = json.loads(data)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
        finally:
            try:
                await loop.run_in_executor(None, pubsub.close)
            except Exception:
                pass

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def healthcheck(self) -> bool:
        try:
            return bool(self.client().ping())
        except Exception:
            return False


def build_redis_job_queue(
    url: str = "",
    concurrency: int = 2,
    max_attempts: int = 3,
    brpop_timeout: int = 2,
) -> RedisJobQueue:
    queue = RedisJobQueue(
        url=url,
        concurrency=concurrency,
        max_attempts=max_attempts,
        brpop_timeout=brpop_timeout,
    )
    queue.client()
    return queue


def build_redis_job_event_bus(url: str = "") -> RedisJobEventBus:
    bus = RedisJobEventBus(url=url)
    bus.client()
    return bus
