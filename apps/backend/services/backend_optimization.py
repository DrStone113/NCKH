"""Dependency-free runtime primitives for Backend Optimization V2.

The module intentionally stores only aggregate counters and public cache
entries. It never accepts user identifiers, prompts, health profiles, or raw
chat text as metric labels or global cache keys.
"""

from __future__ import annotations

import asyncio
import heapq
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from collections import Counter, OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Awaitable, Callable, Generic, TypeVar
from urllib.parse import urlparse


_SAFE_METRIC_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
T = TypeVar("T")


class BackendCostMetrics:
    """Small process-local aggregate suitable for one-worker deployments."""

    def __init__(self, *, max_samples: int = 512) -> None:
        self._lock = Lock()
        self._started_at = datetime.now(timezone.utc)
        self._counters: Counter[str] = Counter()
        self._gauges: dict[str, float] = {}
        self._samples: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=max_samples)
        )

    @staticmethod
    def _key(name: str) -> str:
        key = str(name or "").strip().casefold()
        if not _SAFE_METRIC_KEY.fullmatch(key):
            raise ValueError("INVALID_METRIC_KEY")
        return key

    def increment(self, name: str, value: int = 1) -> None:
        key = self._key(name)
        with self._lock:
            self._counters[key] += int(value)

    def gauge(self, name: str, value: float) -> None:
        key = self._key(name)
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float) -> None:
        key = self._key(name)
        with self._lock:
            self._samples[key].append(float(value))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = {
                key: _sample_summary(list(values))
                for key, values in sorted(self._samples.items())
            }
            return {
                "window_started_at": self._started_at.isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "counters": dict(sorted(self._counters.items())),
                "gauges": dict(sorted(self._gauges.items())),
                "samples": samples,
            }


def _sample_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    percentile = lambda p: ordered[min(len(ordered) - 1, math.ceil(len(ordered) * p) - 1)]
    return {
        "count": len(ordered),
        "avg": round(sum(ordered) / len(ordered), 3),
        "p50": round(percentile(0.50), 3),
        "p95": round(percentile(0.95), 3),
    }


class AdmissionRejected(RuntimeError):
    """Raised when enforce mode cannot admit work before its deadline."""


def chat_priority(text: str) -> tuple[int, bool]:
    """Return a privacy-safe priority class without persisting the message."""

    folded = str(text or "").casefold()
    urgent = any(
        cue in folded
        for cue in (
            "đau ngực", "dau nguc", "khó thở", "kho tho", "bị ngất",
            "bi ngat", "sốc phản vệ", "soc phan ve", "quá liều",
            "qua lieu", "tự tử", "tu tu", "tự làm hại", "tu lam hai",
        )
    )
    if urgent:
        return 0, True
    write_or_confirmation = any(
        cue in folded
        for cue in (
            "xác nhận", "xac nhan", "lưu", "luu", "ghi lại", "ghi lai",
            "đồng ý", "dong y", "thực hiện", "thuc hien",
        )
    )
    if write_or_confirmation:
        return 1, False
    external_or_evidence = any(
        cue in folded
        for cue in (
            "báº±ng chá»©ng", "bang chung", "nghiÃªn cá»©u", "nghien cuu",
            "pubmed", "tÃ¬m web", "tim web", "nguá»“n y khoa", "nguon y khoa",
        )
    )
    return (3, False) if external_or_evidence else (2, False)


@dataclass(slots=True)
class _Waiter:
    priority: int
    sequence: int
    urgent: bool
    queued_at: float
    future: asyncio.Future[float]

    def heap_item(self) -> tuple[int, int, "_Waiter"]:
        return self.priority, self.sequence, self


class AdaptiveAdmissionController:
    """Priority admission with a bounded AIMD concurrency window.

    Lower numeric priority wins. Urgent work may consume one reserved slot
    above the ordinary limit, so routine traffic cannot starve safety replies.
    """

    def __init__(
        self,
        *,
        minimum: int,
        initial: int,
        maximum: int,
        timeout_seconds: float,
        metrics: BackendCostMetrics | None = None,
        enforce: bool = False,
        adjustment_window: int = 20,
        queue_target_ms: float = 50.0,
    ) -> None:
        if not 1 <= minimum <= initial <= maximum:
            raise ValueError("INVALID_ADMISSION_LIMITS")
        self.minimum = minimum
        self.limit = initial
        self.maximum = maximum
        self.timeout_seconds = timeout_seconds
        self.metrics = metrics
        self.enforce = enforce
        self.adjustment_window = max(4, adjustment_window)
        self.queue_target_ms = queue_target_ms
        self._condition = asyncio.Condition()
        self._active = 0
        self._sequence = 0
        self._waiters: list[tuple[int, int, _Waiter]] = []
        self._window_queue_ms: list[float] = []
        self._window_failures = 0
        self._stable_windows = 0

    @property
    def active(self) -> int:
        return self._active

    @property
    def queued(self) -> int:
        return sum(not item[2].future.done() for item in self._waiters)

    def _capacity(self, urgent: bool) -> int:
        return self.limit + (1 if urgent else 0)

    async def acquire(self, *, priority: int, urgent: bool = False) -> float:
        started = time.perf_counter()
        if not self.enforce:
            async with self._condition:
                self._active += 1
                self._publish_gauges()
            return 0.0

        loop = asyncio.get_running_loop()
        async with self._condition:
            if self._active < self._capacity(urgent) and not self._waiters:
                self._active += 1
                self._publish_gauges()
                return 0.0
            future: asyncio.Future[float] = loop.create_future()
            self._sequence += 1
            waiter = _Waiter(priority, self._sequence, urgent, started, future)
            heapq.heappush(self._waiters, waiter.heap_item())
            self._publish_gauges()

        try:
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError as exc:
            async with self._condition:
                if not future.done():
                    future.cancel()
                self._window_failures += 1
                self._publish_gauges()
            if self.metrics:
                self.metrics.increment("chat.admission_rejected")
            raise AdmissionRejected("SERVER_BUSY") from exc

    async def release(self, *, queue_ms: float, failed: bool = False) -> None:
        async with self._condition:
            self._active = max(0, self._active - 1)
            self._window_queue_ms.append(max(0.0, queue_ms))
            if failed:
                self._window_failures += 1
            self._adjust_limit_if_ready()
            self._wake_waiters()
            self._publish_gauges()

    def _wake_waiters(self) -> None:
        deferred: list[tuple[int, int, _Waiter]] = []
        while self._waiters:
            item = heapq.heappop(self._waiters)
            waiter = item[2]
            if waiter.future.done():
                continue
            if self._active >= self._capacity(waiter.urgent):
                deferred.append(item)
                # A regular waiter may be blocked at ``limit`` while a later
                # urgent waiter is still entitled to the reserved slot. Scan
                # the remaining heap instead of letting FIFO traffic hide it.
                continue
            self._active += 1
            waited_ms = (time.perf_counter() - waiter.queued_at) * 1000
            waiter.future.set_result(waited_ms)
        for item in deferred:
            heapq.heappush(self._waiters, item)

    def _adjust_limit_if_ready(self) -> None:
        if len(self._window_queue_ms) < self.adjustment_window:
            return
        ordered = sorted(self._window_queue_ms)
        p50 = ordered[len(ordered) // 2]
        if self._window_failures or p50 > self.queue_target_ms:
            self.limit = max(self.minimum, math.floor(self.limit * 0.8))
            self._stable_windows = 0
        else:
            self._stable_windows += 1
            if self._stable_windows >= 2:
                self.limit = min(self.maximum, self.limit + 1)
                self._stable_windows = 0
        self._window_queue_ms.clear()
        self._window_failures = 0

    def observe_pressure(
        self, *, db_utilization: float = 0.0, timed_out: bool = False
    ) -> None:
        """Feed process-local DB/timeout pressure into the next AIMD window."""

        if timed_out or db_utilization >= 0.85:
            self._window_failures += 1

    def _publish_gauges(self) -> None:
        if not self.metrics:
            return
        self.metrics.gauge("chat.active", self._active)
        self.metrics.gauge("chat.queued", self.queued)
        self.metrics.gauge("chat.concurrency_limit", self.limit)

    @asynccontextmanager
    async def slot(self, *, priority: int, urgent: bool = False):
        queue_ms = await self.acquire(priority=priority, urgent=urgent)
        failed = False
        try:
            if self.metrics:
                self.metrics.observe("chat.queue_ms", queue_ms)
            yield queue_ms
        except Exception:
            failed = True
            raise
        finally:
            await self.release(queue_ms=queue_ms, failed=failed)


@dataclass(slots=True)
class _CacheEntry(Generic[T]):
    value: T
    fresh_until: float
    stale_until: float


class PublicSingleFlightCache(Generic[T]):
    """Bounded TTL/stale-if-error cache for explicitly public data only."""

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: float,
        stale_seconds: float | None = None,
        metrics: BackendCostMetrics | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.stale_seconds = stale_seconds if stale_seconds is not None else ttl_seconds
        self.metrics = metrics
        self._entries: OrderedDict[str, _CacheEntry[T]] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        owner = False
        stale: _CacheEntry[T] | None = None
        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                if now <= entry.fresh_until:
                    if self.metrics:
                        self.metrics.increment("public_cache.hit")
                    return entry.value
                if now <= entry.stale_until:
                    stale = entry
            future = self._inflight.get(key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                owner = True
            elif self.metrics:
                self.metrics.increment("public_cache.singleflight_join")

        if not owner:
            return await asyncio.shield(future)

        try:
            value = await loader()
        except Exception as exc:
            async with self._lock:
                self._inflight.pop(key, None)
                if not future.done():
                    if stale is not None:
                        future.set_result(stale.value)
                    else:
                        future.set_exception(exc)
                        future.exception()
            if stale is not None:
                if self.metrics:
                    self.metrics.increment("public_cache.stale_served")
                return stale.value
            raise

        async with self._lock:
            now = time.monotonic()
            self._entries[key] = _CacheEntry(
                value,
                now + self.ttl_seconds,
                now + self.ttl_seconds + self.stale_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            self._inflight.pop(key, None)
            if not future.done():
                future.set_result(value)
        if self.metrics:
            self.metrics.increment("public_cache.miss")
        return value


@dataclass(slots=True)
class _PrivateSnapshot:
    value: Any
    expires_at: float


class OwnerScopedSnapshotCache:
    """Short-lived typed cache isolated by HMAC owner and chat session."""

    _VERSION_FIELDS = (
        "updated_at", "revision_id", "revision", "catalog_version", "version",
    )

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 512,
        metrics: BackendCostMetrics | None = None,
    ) -> None:
        self.ttl_seconds = max(1.0, min(float(ttl_seconds), 300.0))
        self.max_entries = max(1, max_entries)
        self.metrics = metrics
        self._secret = secrets.token_bytes(32)
        self._entries: OrderedDict[str, _PrivateSnapshot] = OrderedDict()
        self._current: dict[str, str] = {}
        self._scope_entries: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def _scope_key(self, owner: str, session_id: str) -> str:
        return hmac.new(
            self._secret, f"{owner}\x1f{session_id}".encode(), hashlib.sha256
        ).hexdigest()

    def _base_key(
        self, owner: str, session_id: str, source: str, params: dict[str, Any]
    ) -> str:
        canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
        material = f"{owner}\x1f{session_id}\x1f{source}\x1f{canonical}".encode()
        return hmac.new(self._secret, material, hashlib.sha256).hexdigest()

    @classmethod
    def _version(cls, value: Any) -> str | None:
        data = getattr(value, "data", value)
        if not isinstance(data, dict):
            return None
        for field in cls._VERSION_FIELDS:
            candidate = data.get(field)
            if candidate is not None and str(candidate).strip():
                return str(candidate)
        presentation = data.get("presentation")
        return cls._version(presentation) if isinstance(presentation, dict) else None

    async def get(
        self, *, owner: str, session_id: str, source: str, params: dict[str, Any]
    ) -> Any | None:
        base = self._base_key(owner, session_id, source, params)
        async with self._lock:
            full = self._current.get(base)
            entry = self._entries.get(full or "")
            if entry is None or entry.expires_at < time.monotonic():
                if full:
                    self._entries.pop(full, None)
                    self._current.pop(base, None)
                if self.metrics:
                    self.metrics.increment("private_cache.miss")
                return None
            self._entries.move_to_end(full)
            if self.metrics:
                self.metrics.increment("private_cache.hit")
            return entry.value

    async def set(
        self,
        *,
        owner: str,
        session_id: str,
        source: str,
        params: dict[str, Any],
        value: Any,
    ) -> bool:
        version = self._version(value)
        if version is None:
            return False
        base = self._base_key(owner, session_id, source, params)
        full = hmac.new(
            self._secret, f"{base}\x1f{version}".encode(), hashlib.sha256
        ).hexdigest()
        async with self._lock:
            previous = self._current.get(base)
            if previous and previous != full:
                self._entries.pop(previous, None)
            self._current[base] = full
            self._scope_entries[self._scope_key(owner, session_id)].add(base)
            self._entries[full] = _PrivateSnapshot(
                value=value, expires_at=time.monotonic() + self.ttl_seconds
            )
            self._entries.move_to_end(full)
            while len(self._entries) > self.max_entries:
                evicted, _ = self._entries.popitem(last=False)
                for pointer, target in list(self._current.items()):
                    if target == evicted:
                        self._current.pop(pointer, None)
                        for scoped in self._scope_entries.values():
                            scoped.discard(pointer)
            return True

    async def invalidate(self, *, owner: str, session_id: str) -> None:
        scope = self._scope_key(owner, session_id)
        async with self._lock:
            for base in self._scope_entries.pop(scope, set()):
                full = self._current.pop(base, None)
                if full:
                    self._entries.pop(full, None)
        if self.metrics:
            self.metrics.increment("private_cache.invalidations")


@dataclass(slots=True)
class _CircuitState:
    failures: int = 0
    opened_until: float = 0.0


class ResilientHttpClient:
    """Lifespan-owned HTTP pool with a small per-origin circuit breaker."""

    def __init__(
        self,
        client: Any,
        *,
        failure_threshold: int = 3,
        reset_seconds: float = 30.0,
        metrics: BackendCostMetrics | None = None,
    ) -> None:
        self._client = client
        self.failure_threshold = max(1, int(failure_threshold))
        self.reset_seconds = max(1.0, float(reset_seconds))
        self.metrics = metrics
        self._circuits: dict[str, _CircuitState] = defaultdict(_CircuitState)
        self._lock = asyncio.Lock()

    async def request(self, method: str, url: str, **kwargs):
        origin = urlparse(url).netloc.casefold()
        now = time.monotonic()
        async with self._lock:
            state = self._circuits[origin]
            if state.opened_until > now:
                if self.metrics:
                    self.metrics.increment("http.circuit_rejected")
                raise RuntimeError("UPSTREAM_CIRCUIT_OPEN")
        try:
            response = await self._client.request(method, url, **kwargs)
            if response.status_code >= 500:
                response.raise_for_status()
        except Exception:
            async with self._lock:
                state = self._circuits[origin]
                state.failures += 1
                if state.failures >= self.failure_threshold:
                    state.opened_until = time.monotonic() + self.reset_seconds
                    if self.metrics:
                        self.metrics.increment("http.circuit_opened")
            raise
        async with self._lock:
            state = self._circuits[origin]
            state.failures = 0
            state.opened_until = 0.0
        return response

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = [
    "AdaptiveAdmissionController",
    "AdmissionRejected",
    "BackendCostMetrics",
    "OwnerScopedSnapshotCache",
    "PublicSingleFlightCache",
    "ResilientHttpClient",
    "chat_priority",
]
