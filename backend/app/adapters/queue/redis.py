from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from app.ports.job_queue import JobHandler

QUEUE_KEY = "cs:jobs:queue"
DELAYED_KEY = "cs:jobs:delayed"
CLAIM_PREFIX = "cs:jobs:claimed:"
ATTEMPT_PREFIX = "cs:jobs:attempts:"
EVENT_CHANNEL_PREFIX = "cs:jobs:events:"
BACKOFF_BASE = 2
MAX_BACKOFF = 60
STALE_CLAIM_SECONDS = 900
LEGACY_CLAIM_FLOOR = 1000000000
STALE_SWEEP_INTERVAL = 30.0
QUEUED_STATUS = "queued"
RUNNING_STATUS = "running"


class RedisJobQueue:
    name = "redis"

    def __init__(
        self,
        url: str = "",
        concurrency: int = 2,
        max_attempts: int = 3,
        brpop_timeout: int = 2,
        queue_key: str = QUEUE_KEY,
        delayed_key: str = DELAYED_KEY,
        stale_seconds: int = STALE_CLAIM_SECONDS,
    ) -> None:
        self.url = url
        self.concurrency = max(0, int(concurrency or 0))
        self.max_attempts = max(1, int(max_attempts or 1))
        self.brpop_timeout = max(1, int(brpop_timeout or 1))
        self.queue_key = queue_key
        self.delayed_key = delayed_key
        self.stale_seconds = max(60, int(stale_seconds or STALE_CLAIM_SECONDS))
        self._client = None
        self._handler: JobHandler | None = None
        self._repository: Any = None
        self._workers: list[asyncio.Task] = []
        self._closed = False
        self._running = 0
        self._last_sweep = 0.0

    def set_job_repository(self, repository: Any) -> None:
        self._repository = repository

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
        if self.concurrency <= 0:
            return
        loop = asyncio.get_event_loop()
        for index in range(self.concurrency):
            task = loop.create_task(self._worker(index), name=f"redis-job-worker-{index}")
            self._workers.append(task)

    async def _worker(self, index: int) -> None:
        loop = asyncio.get_event_loop()
        while not self._closed:
            job_id = None
            try:
                self._promote_delayed()
                self._sweep_stale()
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
                print(f"[queue] redis worker {index} failed to take a job: {exc!r}")
                await asyncio.sleep(1)
                continue
            claim_key = CLAIM_PREFIX + job_id
            try:
                claimed = self.client().set(claim_key, str(time.time()), nx=True, ex=86400)
            except Exception as exc:
                print(f"[queue] redis claim failed {job_id}: {exc!r}")
                continue
            if not claimed:
                print(f"[queue] job {job_id} was already claimed by another instance; skipping")
                continue
            self._running += 1
            failed = False
            try:
                if self._handler is not None:
                    await self._handler(job_id)
            except asyncio.CancelledError:
                self._running = max(0, self._running - 1)
                break
            except Exception as exc:
                failed = True
                print(f"[queue] redis worker {index} job {job_id} raised: {exc!r}")
            finally:
                self._running = max(0, self._running - 1)
            try:
                if failed:
                    self._schedule_retry(job_id)
                else:
                    self._clear_claim(job_id)
            except Exception as exc:
                print(f"[queue] failed to finalize job {job_id}: {exc!r}")
                self._clear_claim(job_id)

    def _clear_claim(self, job_id: str) -> None:
        try:
            client = self.client()
            client.delete(CLAIM_PREFIX + job_id)
            client.delete(ATTEMPT_PREFIX + job_id)
        except Exception as exc:
            print(f"[queue] failed to clean up the status key for job {job_id}: {exc!r}")

    def _schedule_retry(self, job_id: str) -> None:
        client = self.client()
        attempts = int(client.incr(ATTEMPT_PREFIX + job_id))
        client.delete(CLAIM_PREFIX + job_id)
        if attempts >= self.max_attempts:
            client.delete(ATTEMPT_PREFIX + job_id)
            print(f"[queue] job {job_id} reached the maximum of {self.max_attempts} attempts; marking as permanently failed")
            return
        delay = min(BACKOFF_BASE ** attempts, MAX_BACKOFF)
        client.zadd(self.delayed_key, {job_id: time.time() + delay})
        if self._repository is not None:
            try:
                self._repository.update_status(job_id, QUEUED_STATUS, None, "")
            except Exception as exc:
                print(f"[queue] failed to reset the status of job {job_id} before retrying: {exc!r}")
        print(f"[queue] job {job_id} failed on attempt {attempts}; retrying in {delay}s")

    def _promote_delayed(self) -> None:
        client = self.client()
        due = client.zrangebyscore(self.delayed_key, 0, time.time(), start=0, num=5)
        for job_id in due or []:
            if client.zrem(self.delayed_key, job_id):
                client.lpush(self.queue_key, job_id)
                print(f"[queue] delayed job {job_id} is due; re-enqueued")

    def _sweep_stale(self) -> None:
        if self._repository is None:
            return
        now = time.time()
        if now - self._last_sweep < STALE_SWEEP_INTERVAL:
            return
        self._last_sweep = now
        client = self.client()
        for key in client.scan_iter(match=CLAIM_PREFIX + "*", count=100):
            name = key if isinstance(key, str) else key.decode()
            job_id = name.split(CLAIM_PREFIX)[-1]
            try:
                claimed_at = float(client.get(name) or 0.0)
            except (TypeError, ValueError):
                claimed_at = 0.0
            if claimed_at < LEGACY_CLAIM_FLOOR:
                client.delete(name)
                print(f"[queue] cleaning up the historical claim key for job {job_id}")
                continue
            if now - claimed_at < self.stale_seconds:
                continue
            try:
                job = self._repository.get(job_id)
            except Exception:
                job = None
            if job is None:
                client.delete(name)
                continue
            status = getattr(job, "status", "")
            client.delete(name)
            if status in (QUEUED_STATUS, RUNNING_STATUS):
                client.delete(ATTEMPT_PREFIX + job_id)
                client.lpush(self.queue_key, job_id)
                print(f"[queue] job {job_id} looks interrupted ({status}); re-enqueued")

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
            client = self.client()
            length = int(client.llen(self.queue_key))
            delayed = int(client.zcard(self.delayed_key))
        except Exception:
            length = 0
            delayed = 0
        return {
            "pending": length,
            "delayed": delayed,
            "running": self._running,
            "concurrency": self.concurrency,
        }

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
            print(f"[jobs] failed to publish the event for {job_id}: {exc!r}")

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
