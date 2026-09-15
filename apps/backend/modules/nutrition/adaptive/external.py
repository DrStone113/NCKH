"""Controlled N3.1 external recipe discovery and evidence acquisition.

The module intentionally keeps web content at an untrusted boundary.  It
returns typed recipe evidence, never a catalog mutation.  A caller may stage a
candidate only after source policy, deterministic mapping, canonical nutrient
calculation, and N3 quality gates all pass.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlencode, urlparse

import httpx

from .contracts import (
    CandidateSource,
    CanonicalIngredientMapping,
    ConstraintContext,
    MappingStatus,
    NutrientTotals,
    RawIngredient,
    RecipeCandidate,
    TrustDomain,
)
from .discovery import RecipeDiscoveryRequest, should_trigger_external_discovery
from .engine import (
    AdaptiveRecipeError,
    CanonicalIngredientMapper,
    RecipePortionFitter,
    RecipeQualityGate,
    build_recipe_candidate,
    load_adaptive_source_registry,
)
from .repository import AdaptiveRecipeRepository


MAX_FETCH_BYTES = 1_000_000
DEFAULT_CACHE_TTL = timedelta(hours=12)


class FetchStrategy(str, Enum):
    API_FETCH = "API_FETCH"
    HTTP_FETCH = "HTTP_FETCH"
    PLAYWRIGHT_FETCH = "PLAYWRIGHT_FETCH"


class CacheStatus(str, Enum):
    MISS = "MISS"
    HIT = "HIT"
    STALE = "STALE"


class RecipeRelation(str, Enum):
    SAME_RECIPE = "SAME_RECIPE"
    RECIPE_VARIANT = "RECIPE_VARIANT"
    REGIONAL_VARIANT = "REGIONAL_VARIANT"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    DISTINCT_RECIPE = "DISTINCT_RECIPE"


class ExternalDiscoveryError(AdaptiveRecipeError):
    """Typed boundary failure; callers must retain their local fallback."""


@dataclass(frozen=True)
class RecipeSearchQuery:
    query: str
    meal_type: str | None = None
    cuisine: str | None = None
    preferred_ingredients: tuple[str, ...] = ()
    dietary_constraints: tuple[str, ...] = ()
    language_region: str | None = None
    nutrition_intent: str | None = None
    limit: int = 3
    confirmed_ingredient_grams: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RecipeSearchResult:
    source_id: str
    title: str
    source_url: str
    source_recipe_id: str | None
    discovery_confidence: float


@dataclass(frozen=True)
class FetchTarget:
    source_id: str
    url: str
    source_recipe_id: str | None = None
    explicit_user_url: bool = False


@dataclass(frozen=True)
class FetchedRecipePage:
    source_id: str
    url: str
    final_url: str
    content: str
    content_type: str
    fetched_at: datetime
    source_last_modified: str | None = None
    source_recipe_id: str | None = None
    strategy: FetchStrategy = FetchStrategy.HTTP_FETCH
    http_status: int | None = None
    content_fingerprint_override: str | None = None

    @property
    def content_fingerprint(self) -> str:
        return self.content_fingerprint_override or hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class ExtractedRecipe:
    title: str
    aliases: tuple[str, ...]
    raw_ingredients: tuple[RawIngredient, ...]
    source_reported_nutrition: NutrientTotals | None
    recipe_yield: str | None
    cuisine: str | None
    category: str | None
    prep_time: str | None
    cook_time: str | None
    total_time: str | None
    instructions: tuple[str, ...]
    extractor_type: str
    structured_data_present: bool
    untrusted_data_text: str


@dataclass(frozen=True)
class MappingCoverage:
    ingredient_count_coverage: float
    mass_coverage: float | None
    required_unmapped_count: int
    optional_unmapped_count: int
    nutrition_verified: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CachedRecipeEvidence:
    source_id: str
    source_url: str
    extracted: ExtractedRecipe
    fetched_at: datetime
    content_fingerprint: str
    source_last_modified: str | None


@dataclass(frozen=True)
class CacheLookup:
    status: CacheStatus
    entry: CachedRecipeEvidence | None


@dataclass(frozen=True)
class AdaptedRecipeRevision:
    base_candidate_id: str
    candidate: RecipeCandidate
    label: str = "Công thức đã được điều chỉnh khẩu phần"


@dataclass(frozen=True)
class ExternalRecipeDetails:
    """Transient display data; instructions are never persisted in candidates."""

    raw_ingredients: tuple[RawIngredient, ...]
    instructions: tuple[str, ...]
    recipe_yield: str | None = None
    cuisine: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class ExternalAcquisitionResult:
    trigger_reason: str
    candidates: tuple[RecipeCandidate, ...]
    staged_candidates: tuple[RecipeCandidate, ...]
    adaptations: tuple[AdaptedRecipeRevision, ...]
    public_trace: tuple[str, ...]
    debug_trace: Mapping[str, Any]
    fallback_reason: str | None = None
    recipe_details: Mapping[str, ExternalRecipeDetails] = field(default_factory=dict)


class RecipeSearchProvider(Protocol):
    source_id: str

    async def search(self, query: RecipeSearchQuery) -> Sequence[RecipeSearchResult]:
        """Find source-owned recipe identifiers/URLs only; never nutrition."""


class RecipeFetcher(Protocol):
    strategy: FetchStrategy

    async def fetch(self, target: FetchTarget) -> FetchedRecipePage:
        """Fetch an approved target after its source-policy check."""


class RecipeExtractor(Protocol):
    def supports(self, page: FetchedRecipePage) -> bool:
        ...

    def extract(self, page: FetchedRecipePage, policy: Mapping[str, Any]) -> ExtractedRecipe:
        ...


def build_recipe_search_text(query: RecipeSearchQuery) -> str:
    """Build a compact, non-sensitive discovery query.

    No account identifier, health history, weight, diagnosis, or free-form chat
    text is included.  The result is only a retrieval hint and has no nutrition
    or policy authority.
    """

    fields = (
        query.cuisine,
        *query.preferred_ingredients,
        query.meal_type,
        query.nutrition_intent,
        *query.dietary_constraints,
        query.query,
    )
    parts: list[str] = []
    for value in fields:
        cleaned = re.sub(r"[^\w\s\-]", " ", str(value or ""), flags=re.UNICODE)
        cleaned = " ".join(cleaned.split())
        if cleaned and cleaned.casefold() not in {part.casefold() for part in parts}:
            parts.append(cleaned)
    return " ".join(parts)


def _source_policies(
    source_policies: Mapping[str, Mapping[str, Any]] | None = None,
) -> Mapping[str, Mapping[str, Any]]:
    return source_policies or load_adaptive_source_registry()


def _policy_for(
    source_id: str, source_policies: Mapping[str, Mapping[str, Any]] | None = None
) -> Mapping[str, Any]:
    try:
        return _source_policies(source_policies)[source_id]
    except KeyError as exc:
        raise ExternalDiscoveryError("UNKNOWN_EXTERNAL_RECIPE_SOURCE") from exc


def _is_allowed_host(url: str, policy: Mapping[str, Any]) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return False
    for allowed in policy.get("allowed_hosts") or ():
        normalized = str(allowed).casefold()
        if host == normalized or host.endswith(f".{normalized}"):
            return True
    return False


def _assert_fetch_allowed(
    target: FetchTarget,
    strategy: FetchStrategy,
    source_policies: Mapping[str, Mapping[str, Any]] | None = None,
) -> Mapping[str, Any]:
    policy = _policy_for(target.source_id, source_policies)
    if policy["access_status"] in {"BLOCKED", "REQUIRES_REVIEW"} or not policy["fetch_allowed"]:
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_FETCH_FORBIDDEN_BY_SOURCE_POLICY")
    if policy["preferred_fetch_method"] != strategy.value:
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_FETCH_STRATEGY_FORBIDDEN")
    if policy.get("requires_explicit_user_url") and not target.explicit_user_url:
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_REQUIRES_EXPLICIT_USER_URL")
    if not _is_allowed_host(target.url, policy):
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_TARGET_HOST_FORBIDDEN")
    return policy


class SourceRateLimiter:
    """In-memory source-specific rate limiter for development/shadow workers."""

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def acquire(self, source_id: str, policy: Mapping[str, Any]) -> None:
        limit = int((policy.get("rate_limit_policy") or {}).get("requests_per_minute", 0))
        if limit <= 0:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_SOURCE_RATE_DISABLED")
        now = time.monotonic()
        bucket = self._requests[source_id]
        while bucket and now - bucket[0] >= 60.0:
            bucket.popleft()
        if len(bucket) >= limit:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_SOURCE_RATE_LIMITED")
        bucket.append(now)


class SourceCircuitBreaker:
    """Fails over to local/other sources without modifying source policy."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = defaultdict(int)
        self._open_until: dict[str, float] = {}

    def allow(self, source_id: str) -> None:
        if self._open_until.get(source_id, 0.0) > time.monotonic():
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_SOURCE_CIRCUIT_OPEN")

    def success(self, source_id: str) -> None:
        self._failures[source_id] = 0
        self._open_until.pop(source_id, None)

    def failure(self, source_id: str, policy: Mapping[str, Any]) -> None:
        self._failures[source_id] += 1
        settings = policy.get("rate_limit_policy") or {}
        threshold = int(settings.get("circuit_breaker_failures", 3))
        if self._failures[source_id] >= threshold:
            self._open_until[source_id] = time.monotonic() + int(
                settings.get("cooldown_seconds", 120)
            )


class SourceHealthTracker:
    """Operational metrics only, never research-outcome metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._latency_ms: dict[str, list[float]] = defaultdict(list)
        self._downgraded: set[str] = set()

    def record(
        self,
        source_id: str,
        *,
        success: bool,
        structured: bool | None = None,
        latency_ms: float | None = None,
        blocked_response: bool = False,
    ) -> None:
        counters = self._counters[source_id]
        counters["fetch_attempts"] += 1
        counters["fetch_successes" if success else "fetch_failures"] += 1
        if structured is True:
            counters["structured_extractions"] += 1
        if blocked_response:
            counters["blocked_responses"] += 1
        if latency_ms is not None:
            self._latency_ms[source_id].append(round(latency_ms, 3))
        # Downgrade only the live worker's availability after three failed
        # attempts.  It can never auto-upgrade a source or mutate the registry.
        if counters["fetch_attempts"] >= 3 and counters["fetch_failures"] / counters["fetch_attempts"] >= 0.75:
            self._downgraded.add(source_id)

    def is_downgraded(self, source_id: str) -> bool:
        return source_id in self._downgraded

    def report(self, source_id: str) -> Mapping[str, float | int | bool]:
        counters = self._counters[source_id]
        attempts = counters["fetch_attempts"]
        latencies = self._latency_ms[source_id]
        return {
            "fetch_attempts": attempts,
            "fetch_success_rate": round(counters["fetch_successes"] / attempts, 4) if attempts else 0.0,
            "structured_extraction_rate": round(counters["structured_extractions"] / attempts, 4) if attempts else 0.0,
            "blocked_responses": counters["blocked_responses"],
            "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "runtime_downgraded": self.is_downgraded(source_id),
        }


class RecipeEvidenceCache:
    """Metadata-only cache.  It deliberately never stores a fetched HTML page."""

    def __init__(self, *, ttl: timedelta = DEFAULT_CACHE_TTL) -> None:
        self._ttl = ttl
        self._entries: dict[tuple[str, str], CachedRecipeEvidence] = {}

    def get(self, source_id: str, source_url: str, *, now: datetime | None = None) -> CacheLookup:
        entry = self._entries.get((source_id, source_url))
        if entry is None:
            return CacheLookup(CacheStatus.MISS, None)
        current = now or datetime.now(timezone.utc)
        if current - entry.fetched_at > self._ttl:
            return CacheLookup(CacheStatus.STALE, entry)
        return CacheLookup(CacheStatus.HIT, entry)

    def put(self, page: FetchedRecipePage, extracted: ExtractedRecipe, policy: Mapping[str, Any]) -> None:
        if not policy["recipe_storage_allowed"]:
            return
        cached_extracted = (
            extracted
            if policy["instruction_storage_allowed"]
            else replace(extracted, instructions=())
        )
        self._entries[(page.source_id, page.final_url)] = CachedRecipeEvidence(
            source_id=page.source_id,
            source_url=page.final_url,
            extracted=cached_extracted,
            fetched_at=page.fetched_at,
            content_fingerprint=page.content_fingerprint,
            source_last_modified=page.source_last_modified,
        )


class HttpRecipeFetcher:
    """Policy-gated async HTTP/API transport; it contains no recipe logic."""

    def __init__(
        self,
        strategy: FetchStrategy,
        *,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        if strategy not in {FetchStrategy.API_FETCH, FetchStrategy.HTTP_FETCH}:
            raise ValueError("HTTP_FETCHER_REQUIRES_HTTP_OR_API_STRATEGY")
        self.strategy = strategy
        self._policies = _source_policies(source_policies)
        self._client_factory = client_factory

    async def fetch(self, target: FetchTarget) -> FetchedRecipePage:
        policy = _assert_fetch_allowed(target, self.strategy, self._policies)
        rate = policy["rate_limit_policy"]
        timeout = httpx.Timeout(float(rate.get("timeout_seconds", 10)))
        headers = {"User-Agent": "NCKH-N3.1-RecipeEvidence/1.0 (+policy-gated)"}
        try:
            async with self._client_factory(
                follow_redirects=True, timeout=timeout, headers=headers
            ) as client:
                response = await client.get(target.url)
        except httpx.HTTPError as exc:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_HTTP_UNAVAILABLE") from exc
        if response.status_code >= 400:
            raise ExternalDiscoveryError(f"EXTERNAL_RECIPE_HTTP_STATUS:{response.status_code}")
        if len(response.content) > MAX_FETCH_BYTES:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_RESPONSE_TOO_LARGE")
        final_url = str(response.url)
        if not _is_allowed_host(final_url, policy):
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_REDIRECT_HOST_FORBIDDEN")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].casefold()
        if self.strategy == FetchStrategy.API_FETCH and "json" not in content_type:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_API_CONTENT_TYPE_INVALID")
        if self.strategy == FetchStrategy.HTTP_FETCH and not any(
            token in content_type for token in ("html", "json", "ld+json")
        ):
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_HTTP_CONTENT_TYPE_INVALID")
        return FetchedRecipePage(
            source_id=target.source_id,
            url=target.url,
            final_url=final_url,
            content=response.text,
            content_type=content_type,
            fetched_at=datetime.now(timezone.utc),
            source_last_modified=response.headers.get("last-modified"),
            source_recipe_id=target.source_recipe_id,
            strategy=self.strategy,
            http_status=response.status_code,
        )


class BrowserPageTransport(Protocol):
    async def fetch_dom(self, target: FetchTarget, policy: Mapping[str, Any]) -> FetchedRecipePage:
        ...


class PlaywrightCliEdgeTransport:
    """Small Edge transport with fixed agent-owned JavaScript only.

    It uses no cookie persistence, log-in, CAPTCHA handling, downloads, page
    supplied scripts, or selectors.  Page scripts execute only as unavoidable
    browser rendering; their text is subsequently treated as untrusted data.
    """

    _DOM_PAYLOAD = (
        "() => JSON.stringify({url:location.href,title:document.title,"
        "html:document.documentElement.outerHTML,lastModified:document.lastModified})"
    )

    def __init__(
        self,
        *,
        node_binary: str = "node",
        cli_script: Path | None = None,
        browser: str = "msedge",
    ) -> None:
        self._node_binary = node_binary
        self._cli_script = cli_script or Path(
            r"C:\Users\Khang\AppData\Roaming\npm\node_modules\@playwright\cli\playwright-cli.js"
        )
        self._browser = browser

    async def _run(self, *args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            self._node_binary,
            str(self._cli_script),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise ExternalDiscoveryError(
                f"PLAYWRIGHT_FETCH_UNAVAILABLE:{stderr.decode('utf-8', errors='replace')[:160]}"
            )
        return stdout.decode("utf-8", errors="replace").strip()

    async def fetch_dom(self, target: FetchTarget, policy: Mapping[str, Any]) -> FetchedRecipePage:
        if not self._cli_script.is_file():
            raise ExternalDiscoveryError("PLAYWRIGHT_CLI_NOT_INSTALLED")
        session = "n3recipe-" + hashlib.sha256(
            f"{target.source_id}|{target.url}|{time.monotonic()}".encode("utf-8")
        ).hexdigest()[:16]
        try:
            await self._run(f"-s={session}", "open", target.url, f"--browser={self._browser}")
            raw = await self._run("--raw", f"-s={session}", "eval", self._DOM_PAYLOAD)
            payload: Any = json.loads(raw)
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict) or not isinstance(payload.get("html"), str):
                raise ExternalDiscoveryError("PLAYWRIGHT_FETCH_INVALID_DOM_PAYLOAD")
            final_url = str(payload.get("url") or "")
            if not _is_allowed_host(final_url, policy):
                raise ExternalDiscoveryError("EXTERNAL_RECIPE_REDIRECT_HOST_FORBIDDEN")
            content = str(payload["html"])
            if len(content.encode("utf-8")) > MAX_FETCH_BYTES:
                raise ExternalDiscoveryError("EXTERNAL_RECIPE_RESPONSE_TOO_LARGE")
            return FetchedRecipePage(
                source_id=target.source_id,
                url=target.url,
                final_url=final_url,
                content=content,
                content_type="text/html",
                fetched_at=datetime.now(timezone.utc),
                source_last_modified=str(payload.get("lastModified") or "") or None,
                source_recipe_id=target.source_recipe_id,
                strategy=FetchStrategy.PLAYWRIGHT_FETCH,
            )
        finally:
            try:
                await self._run(f"-s={session}", "close")
            except ExternalDiscoveryError:
                pass


class PlaywrightRecipeFetcher:
    strategy = FetchStrategy.PLAYWRIGHT_FETCH

    def __init__(
        self,
        transport: BrowserPageTransport,
        *,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._transport = transport
        self._policies = _source_policies(source_policies)

    async def fetch(self, target: FetchTarget) -> FetchedRecipePage:
        policy = _assert_fetch_allowed(target, self.strategy, self._policies)
        page = await self._transport.fetch_dom(target, policy)
        if page.source_id != target.source_id or page.strategy != self.strategy:
            raise ExternalDiscoveryError("PLAYWRIGHT_FETCH_SOURCE_SPOOFING")
        if not _is_allowed_host(page.final_url, policy):
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_REDIRECT_HOST_FORBIDDEN")
        return page


class _JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "script":
            return
        values = {str(key).casefold(): str(value or "") for key, value in attrs}
        self._active = "application/ld+json" in values.get("type", "").casefold()
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._active:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._active:
            self.scripts.append("".join(self._parts))
            self._active = False
            self._parts = []


def _json_ld_nodes(text: str) -> Iterable[Mapping[str, Any]]:
    parser = _JsonLdScriptParser()
    parser.feed(text)
    for script in parser.scripts:
        try:
            value = json.loads(script)
        except json.JSONDecodeError:
            continue
        stack: list[Any] = list(value) if isinstance(value, list) else [value]
        while stack:
            current = stack.pop()
            if not isinstance(current, Mapping):
                continue
            graph = current.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            yield current


def _is_recipe_node(node: Mapping[str, Any]) -> bool:
    recipe_type = node.get("@type")
    types = recipe_type if isinstance(recipe_type, list) else (recipe_type,)
    return any(str(value).casefold() == "recipe" for value in types)


def _fraction_to_float(value: str) -> float | None:
    cleaned = value.strip().replace(",", ".")
    fractions = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
    if cleaned in fractions:
        return fractions[cleaned]
    try:
        if " " in cleaned and "/" in cleaned:
            whole, fraction = cleaned.split(maxsplit=1)
            numerator, denominator = fraction.split("/", maxsplit=1)
            return float(whole) + float(numerator) / float(denominator)
        if "/" in cleaned:
            numerator, denominator = cleaned.split("/", maxsplit=1)
            return float(numerator) / float(denominator)
        return float(cleaned)
    except (ValueError, ZeroDivisionError):
        return None


_UNIT_ALIASES = (
    ("tablespoons", "tbsp"),
    ("tablespoon", "tbsp"),
    ("tbsp", "tbsp"),
    ("thìa canh", "tbsp"),
    ("muỗng canh", "tbsp"),
    ("teaspoons", "tsp"),
    ("teaspoon", "tsp"),
    ("tsp", "tsp"),
    ("thìa cà phê", "tsp"),
    ("muỗng cà phê", "tsp"),
    ("grams", "g"),
    ("gram", "g"),
    ("g", "g"),
    ("kilograms", "kg"),
    ("kilogram", "kg"),
    ("kg", "kg"),
    ("milliliters", "ml"),
    ("milliliter", "ml"),
    ("ml", "ml"),
    ("liters", "l"),
    ("liter", "l"),
    ("l", "l"),
    ("cups", "cup"),
    ("cup", "cup"),
    ("quả", "piece"),
    ("củ", "piece"),
    ("pieces", "piece"),
    ("piece", "piece"),
    ("slices", "piece"),
    ("slice", "piece"),
)
_OPTIONAL_MARKERS = ("optional", "to taste", "as needed", "tuỳ chọn", "tùy chọn")
_QUANTITY_PATTERN = re.compile(
    r"^\s*(?P<quantity>(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|[½¼¾⅓⅔]))\s*(?P<rest>.*)$",
    re.UNICODE,
)


def normalize_ingredient_line(raw_text: str) -> RawIngredient:
    """Parse a line while preserving unresolved units/amounts as uncertainty."""

    raw = " ".join(str(raw_text or "").split())
    optional = any(marker in raw.casefold() for marker in _OPTIONAL_MARKERS)
    quantity: float | None = None
    rest = raw
    match = _QUANTITY_PATTERN.match(raw)
    if match:
        quantity = _fraction_to_float(match.group("quantity"))
        rest = match.group("rest").strip()
    unit = "UNSPECIFIED"
    lowered = rest.casefold()
    for alias, normalized in _UNIT_ALIASES:
        if lowered == alias or lowered.startswith(f"{alias} "):
            unit = normalized
            rest = rest[len(alias) :].strip(" ,.-")
            break
    preparation = None
    declared_state = None
    lowered_rest = rest.casefold()
    if any(token in lowered_rest for token in ("cooked", "chín", "đã nấu")):
        declared_state = "COOKED"
        preparation = "COOKED"
    elif any(token in lowered_rest for token in ("raw", "sống")):
        declared_state = "RAW"
        preparation = "RAW"
    elif any(token in lowered_rest for token in ("dried", "dry", "khô")):
        declared_state = "DRY"
        preparation = "DRY"
    ingredient_name = re.sub(r"\([^)]*\)", "", rest).strip(" ,.-") or raw
    return RawIngredient(
        raw_text=raw,
        amount=quantity,
        unit=unit,
        declared_state=declared_state,
        ingredient_name=ingredient_name,
        preparation_state=preparation,
        optional=optional,
        quantity_uncertain=quantity is None or unit == "UNSPECIFIED",
    )


def apply_confirmed_ingredient_grams(
    extracted: ExtractedRecipe,
    confirmed_grams: Mapping[str, float],
) -> ExtractedRecipe:
    """Apply only explicit user-confirmed gram values to exact source lines."""

    if not confirmed_grams:
        return extracted
    normalized: dict[str, float] = {}
    for source_text, raw_grams in confirmed_grams.items():
        key = " ".join(str(source_text).split()).casefold()
        try:
            grams = float(raw_grams)
        except (TypeError, ValueError) as exc:
            raise ExternalDiscoveryError("CONFIRMED_INGREDIENT_GRAMS_INVALID") from exc
        if not key or not (0 < grams <= 5000):
            raise ExternalDiscoveryError("CONFIRMED_INGREDIENT_GRAMS_INVALID")
        normalized[key] = grams

    matched: set[str] = set()
    ingredients: list[RawIngredient] = []
    for ingredient in extracted.raw_ingredients:
        key = " ".join(ingredient.raw_text.split()).casefold()
        grams = normalized.get(key)
        if grams is None:
            ingredients.append(ingredient)
            continue
        matched.add(key)
        ingredients.append(
            replace(
                ingredient,
                amount=grams,
                unit="g",
                quantity_uncertain=False,
            )
        )
    if matched != set(normalized):
        raise ExternalDiscoveryError("CONFIRMED_INGREDIENT_SOURCE_TEXT_NOT_FOUND")
    return replace(extracted, raw_ingredients=tuple(ingredients))


def _parse_reference_nutrition(value: Mapping[str, Any] | None) -> NutrientTotals | None:
    if not isinstance(value, Mapping):
        return None

    def numeric(key: str) -> float | None:
        raw = value.get(key)
        match = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(raw or ""))
        return float(match.group(0).replace(",", ".")) if match else None

    energy = numeric("calories")
    protein = numeric("proteinContent")
    carbs = numeric("carbohydrateContent")
    fat = numeric("fatContent")
    if None in {energy, protein, carbs, fat}:
        return None
    return NutrientTotals(energy or 0.0, protein or 0.0, carbs or 0.0, fat or 0.0)


def _instructions(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, Mapping):
            text = str(item.get("text") or item.get("name") or "").strip()
        else:
            text = ""
        if text:
            result.append(text)
    return tuple(result)


class JsonLdRecipeExtractor:
    def supports(self, page: FetchedRecipePage) -> bool:
        return "html" in page.content_type or "ld+json" in page.content_type

    def extract(self, page: FetchedRecipePage, policy: Mapping[str, Any]) -> ExtractedRecipe:
        recipe = next((node for node in _json_ld_nodes(page.content) if _is_recipe_node(node)), None)
        if recipe is None:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_JSON_LD_NOT_FOUND")
        raw_lines = tuple(str(value) for value in recipe.get("recipeIngredient") or () if str(value).strip())
        if not raw_lines or not str(recipe.get("name") or "").strip():
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_JSON_LD_INCOMPLETE")
        parsed_instructions = _instructions(recipe.get("recipeInstructions"))
        instructions = parsed_instructions if policy["instruction_display_allowed"] else ()
        untrusted = "\n".join((str(recipe.get("name") or ""), *raw_lines, *parsed_instructions))
        return ExtractedRecipe(
            title=str(recipe["name"]).strip(),
            aliases=(),
            raw_ingredients=tuple(normalize_ingredient_line(line) for line in raw_lines),
            source_reported_nutrition=_parse_reference_nutrition(recipe.get("nutrition")),
            recipe_yield=str(recipe.get("recipeYield") or "").strip() or None,
            cuisine=str(recipe.get("recipeCuisine") or "").strip() or None,
            category=str(recipe.get("recipeCategory") or "").strip() or None,
            prep_time=str(recipe.get("prepTime") or "").strip() or None,
            cook_time=str(recipe.get("cookTime") or "").strip() or None,
            total_time=str(recipe.get("totalTime") or "").strip() or None,
            instructions=instructions,
            extractor_type="JSON_LD_RECIPE",
            structured_data_present=True,
            untrusted_data_text=untrusted,
        )


class TheMealDbApiExtractor:
    def supports(self, page: FetchedRecipePage) -> bool:
        return page.source_id == "THEMEALDB_OFFICIAL_API" and "json" in page.content_type

    def extract(self, page: FetchedRecipePage, policy: Mapping[str, Any]) -> ExtractedRecipe:
        try:
            payload = json.loads(page.content)
            meal = (payload.get("meals") or [])[0]
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_API_PAYLOAD_INVALID") from exc
        if not isinstance(meal, Mapping) or not str(meal.get("strMeal") or "").strip():
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_API_RECIPE_NOT_FOUND")
        raw_lines: list[str] = []
        for index in range(1, 21):
            ingredient = str(meal.get(f"strIngredient{index}") or "").strip()
            measure = str(meal.get(f"strMeasure{index}") or "").strip()
            if ingredient:
                raw_lines.append(" ".join(item for item in (measure, ingredient) if item))
        if not raw_lines:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_API_INGREDIENTS_MISSING")
        raw_instructions = str(meal.get("strInstructions") or "").strip()
        instructions = (
            (raw_instructions,)
            if raw_instructions and policy["instruction_display_allowed"]
            else ()
        )
        return ExtractedRecipe(
            title=str(meal["strMeal"]).strip(),
            aliases=tuple(
                item.strip()
                for item in str(meal.get("strTags") or "").split(",")
                if item.strip()
            ),
            raw_ingredients=tuple(normalize_ingredient_line(line) for line in raw_lines),
            source_reported_nutrition=None,
            recipe_yield=None,
            cuisine=str(meal.get("strArea") or "").strip() or None,
            category=str(meal.get("strCategory") or "").strip() or None,
            prep_time=None,
            cook_time=None,
            total_time=None,
            instructions=instructions,
            extractor_type="OFFICIAL_API_JSON",
            structured_data_present=True,
            untrusted_data_text="\n".join((str(meal["strMeal"]), *raw_lines, raw_instructions)),
        )


class StructuredRecipeExtractionService:
    """Uses a deterministic extractor registry; it never invokes an LLM."""

    def __init__(self, extractors: Sequence[RecipeExtractor] | None = None) -> None:
        self._extractors = tuple(extractors or (TheMealDbApiExtractor(), JsonLdRecipeExtractor()))

    def extract(
        self,
        page: FetchedRecipePage,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> ExtractedRecipe:
        policy = _policy_for(page.source_id, source_policies)
        for extractor in self._extractors:
            if extractor.supports(page):
                return extractor.extract(page, policy)
        raise ExternalDiscoveryError("EXTERNAL_RECIPE_NO_PERMITTED_EXTRACTOR")


def _mass_from_raw(ingredient: RawIngredient) -> float | None:
    if ingredient.amount is None:
        return None
    unit = ingredient.unit.casefold()
    factors = {"g": 1.0, "gram": 1.0, "grams": 1.0, "kg": 1000.0, "mg": 0.001}
    return ingredient.amount * factors[unit] if unit in factors else None


def calculate_mapping_coverage(mappings: Sequence[CanonicalIngredientMapping]) -> MappingCoverage:
    if not mappings:
        return MappingCoverage(0.0, None, 0, 0, False, ("MAPPING_COVERAGE_EMPTY",))
    resolved = [
        mapping
        for mapping in mappings
        if mapping.status in {MappingStatus.EXACT, MappingStatus.HIGH_CONFIDENCE}
        and mapping.grams is not None
        and mapping.grams > 0
    ]
    required_unmapped = [
        mapping
        for mapping in mappings
        if mapping not in resolved and not mapping.raw_ingredient.optional
    ]
    optional_unmapped = [
        mapping
        for mapping in mappings
        if mapping not in resolved and mapping.raw_ingredient.optional
    ]
    known_total_mass = sum(
        mass
        for mass in (_mass_from_raw(mapping.raw_ingredient) for mapping in mappings)
        if mass is not None and mass > 0
    )
    resolved_mass = sum(mapping.grams or 0.0 for mapping in resolved)
    mass_coverage = round(resolved_mass / known_total_mass, 4) if known_total_mass else None
    codes: list[str] = []
    if required_unmapped:
        codes.append("NUTRITION_NOT_VERIFIED")
    elif optional_unmapped:
        codes.append("NUTRITION_PARTIALLY_VERIFIED")
    return MappingCoverage(
        ingredient_count_coverage=round(len(resolved) / len(mappings), 4),
        mass_coverage=mass_coverage,
        required_unmapped_count=len(required_unmapped),
        optional_unmapped_count=len(optional_unmapped),
        nutrition_verified=not required_unmapped and not optional_unmapped,
        reason_codes=tuple(codes),
    )


def stable_runtime_recipe_identity(
    source: CandidateSource, mappings: Sequence[CanonicalIngredientMapping]
) -> str:
    structure = sorted(
        (
            mapping.canonical_food_id or mapping.raw_ingredient.ingredient_name or mapping.raw_ingredient.raw_text,
            f"{mapping.grams:.4f}" if mapping.grams is not None else "UNRESOLVED",
            mapping.canonical_state or mapping.raw_ingredient.declared_state or "UNKNOWN",
        )
        for mapping in mappings
    )
    payload = json.dumps(
        {
            "source_id": source.source_id,
            "source_recipe_id": source.source_recipe_id,
            "source_url": source.source_url,
            "structure": structure,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RecipeVariantClassifier:
    """Ingredient-structure comparator; embedding similarity has no authority."""

    def classify(self, left: RecipeCandidate, right: RecipeCandidate) -> RecipeRelation:
        if left.runtime_recipe_identity and left.runtime_recipe_identity == right.runtime_recipe_identity:
            return RecipeRelation.SAME_RECIPE
        left_ids = {item.canonical_food_id for item in left.mappings if item.canonical_food_id}
        right_ids = {item.canonical_food_id for item in right.mappings if item.canonical_food_id}
        if not left_ids or not right_ids:
            return RecipeRelation.POSSIBLE_DUPLICATE
        overlap = len(left_ids & right_ids) / len(left_ids | right_ids)
        same_title = _identity_text(left.title) == _identity_text(right.title)
        if same_title and overlap == 1.0:
            return RecipeRelation.RECIPE_VARIANT
        if overlap >= 0.75 and _has_regional_alias(left, right):
            return RecipeRelation.REGIONAL_VARIANT
        if overlap >= 0.75:
            return RecipeRelation.POSSIBLE_DUPLICATE
        return RecipeRelation.DISTINCT_RECIPE


def _identity_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _has_regional_alias(left: RecipeCandidate, right: RecipeCandidate) -> bool:
    aliases = {_identity_text(item) for item in (*left.aliases, *right.aliases)}
    titles = {_identity_text(left.title), _identity_text(right.title)}
    return bool(aliases & titles) or any(
        marker in " ".join(titles) for marker in ("hue", "ha noi", "saigon", "mien")
    )


class ExternalCandidateFactory:
    def __init__(
        self,
        mapper: CanonicalIngredientMapper,
        *,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._mapper = mapper
        self._policies = _source_policies(source_policies)

    def create(
        self,
        page: FetchedRecipePage,
        extracted: ExtractedRecipe,
        constraints: ConstraintContext = ConstraintContext(),
    ) -> RecipeCandidate:
        policy = _policy_for(page.source_id, self._policies)
        provisional_mappings = tuple(self._mapper.map(item) for item in extracted.raw_ingredients)
        coverage = calculate_mapping_coverage(provisional_mappings)
        source = CandidateSource(
            source_type=str(policy["source_type"]),
            source_id=page.source_id,
            source_url=page.final_url,
            fetched_at=page.fetched_at.isoformat(),
            license_status=str(policy["license_status"]),
            source_recipe_id=page.source_recipe_id,
            source_last_modified=page.source_last_modified,
            content_fingerprint=page.content_fingerprint,
            cache_status=CacheStatus.MISS.value,
            fetch_strategy=page.strategy.value,
        )
        raw_evidence = (
            "\n".join(item.raw_text for item in extracted.raw_ingredients)
            if policy["raw_source_text_storage"] == "EVIDENCE_ONLY"
            else ""
        )
        candidate = build_recipe_candidate(
            trust_domain=TrustDomain.RUNTIME_EXTERNAL_CANDIDATE,
            title=extracted.title,
            aliases=extracted.aliases,
            source=source,
            raw_ingredients=extracted.raw_ingredients,
            raw_source_text=raw_evidence,
            source_reported_nutrition=extracted.source_reported_nutrition,
            runtime_recipe_identity=stable_runtime_recipe_identity(source, provisional_mappings),
            extraction_method=extracted.extractor_type,
            structured_data_present=extracted.structured_data_present,
            mapping_count_coverage=coverage.ingredient_count_coverage,
            mapping_mass_coverage=coverage.mass_coverage,
            untrusted_content=extracted.untrusted_data_text,
            mapper=self._mapper,
            source_policies=self._policies,
            constraints=constraints,
        )
        score = self._quality_score(candidate, coverage, policy)
        return replace(candidate, quality_score=score)

    @staticmethod
    def _quality_score(
        candidate: RecipeCandidate,
        coverage: MappingCoverage,
        policy: Mapping[str, Any],
    ) -> float | None:
        if not RecipeQualityGate.hard_pass(candidate.validation_codes):
            return None
        score = 0.25
        score += 0.20 if policy["access_status"] == "APPROVED" else 0.10
        score += 0.15 if candidate.evidence.structured_data_present else 0.0
        score += 0.20 * coverage.ingredient_count_coverage
        score += 0.15 if coverage.nutrition_verified else 0.0
        score += 0.05 if not any(code.endswith("_CONFLICT") for code in candidate.validation_codes) else 0.0
        return round(min(score, 1.0), 4)


class TheMealDbSearchProvider:
    """A vendor adapter; discovery stays vendor-neutral at the protocol layer."""

    source_id = "THEMEALDB_OFFICIAL_API"

    def __init__(
        self,
        *,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
        client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
        api_key: str = "1",
    ) -> None:
        self._policies = _source_policies(source_policies)
        self._client_factory = client_factory
        self._api_key = api_key

    async def search(self, query: RecipeSearchQuery) -> Sequence[RecipeSearchResult]:
        policy = _policy_for(self.source_id, self._policies)
        if not policy["discovery_allowed"] or policy["access_status"] != "APPROVED":
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_DISCOVERY_FORBIDDEN_BY_SOURCE_POLICY")
        term = build_recipe_search_text(query)
        if not term:
            return ()
        endpoint = f"https://www.themealdb.com/api/json/v1/{self._api_key}/search.php?" + urlencode({"s": term})
        target = FetchTarget(self.source_id, endpoint)
        page = await HttpRecipeFetcher(
            FetchStrategy.API_FETCH, source_policies=self._policies, client_factory=self._client_factory
        ).fetch(target)
        try:
            meals = json.loads(page.content).get("meals") or ()
        except (AttributeError, json.JSONDecodeError) as exc:
            raise ExternalDiscoveryError("EXTERNAL_RECIPE_SEARCH_PAYLOAD_INVALID") from exc
        results: list[RecipeSearchResult] = []
        result_limit = max(1, min(int(query.limit), 5))
        for meal in meals[:result_limit]:
            if not isinstance(meal, Mapping):
                continue
            meal_id = str(meal.get("idMeal") or "").strip()
            title = str(meal.get("strMeal") or "").strip()
            if not meal_id or not title:
                continue
            results.append(
                RecipeSearchResult(
                    source_id=self.source_id,
                    title=title,
                    source_url=f"https://www.themealdb.com/api/json/v1/{self._api_key}/lookup.php?{urlencode({'i': meal_id})}",
                    source_recipe_id=meal_id,
                    discovery_confidence=0.75,
                )
            )
        return tuple(results)


class ControlledSearchDiscoveryProvider:
    """Policy-filter an injected search backend down to registered sources.

    A search engine can identify a URL, but does not confer permission to
    fetch, cache, stage, or use its nutrition.  Unknown/blocked result hosts
    are discarded before the fetcher layer sees them.
    """

    source_id = "CONTROLLED_RECIPE_SEARCH"

    def __init__(
        self,
        backend: Callable[[RecipeSearchQuery], Awaitable[Sequence[RecipeSearchResult]]],
        *,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._backend = backend
        self._policies = _source_policies(source_policies)

    async def search(self, query: RecipeSearchQuery) -> Sequence[RecipeSearchResult]:
        policy = _policy_for(self.source_id, self._policies)
        if not policy["discovery_allowed"] or policy["access_status"] == "BLOCKED":
            raise ExternalDiscoveryError("CONTROLLED_SEARCH_DISCOVERY_FORBIDDEN")
        accepted: list[RecipeSearchResult] = []
        for result in await self._backend(query):
            source_policy = self._policies.get(result.source_id)
            if (
                source_policy is None
                or source_policy["access_status"] in {"BLOCKED", "REQUIRES_REVIEW"}
                or not source_policy["fetch_allowed"]
                or not _is_allowed_host(result.source_url, source_policy)
            ):
                continue
            accepted.append(result)
        return tuple(accepted)


class ExternalRecipeAcquisitionService:
    """Local-first development/shadow orchestration with no canonical writer."""

    def __init__(
        self,
        *,
        search_providers: Iterable[RecipeSearchProvider],
        fetchers: Mapping[FetchStrategy, RecipeFetcher],
        extractor: StructuredRecipeExtractionService,
        candidate_factory: ExternalCandidateFactory,
        repository: AdaptiveRecipeRepository,
        source_policies: Mapping[str, Mapping[str, Any]] | None = None,
        cache: RecipeEvidenceCache | None = None,
        rate_limiter: SourceRateLimiter | None = None,
        circuit_breaker: SourceCircuitBreaker | None = None,
        health: SourceHealthTracker | None = None,
        portion_fitter: RecipePortionFitter | None = None,
    ) -> None:
        self._providers = tuple(search_providers)
        self._fetchers = dict(fetchers)
        self._extractor = extractor
        self._factory = candidate_factory
        self._repository = repository
        self._policies = _source_policies(source_policies)
        self._cache = cache or RecipeEvidenceCache()
        self._rate_limiter = rate_limiter or SourceRateLimiter()
        self._circuit_breaker = circuit_breaker or SourceCircuitBreaker()
        self._health = health or SourceHealthTracker()
        self._portion_fitter = portion_fitter

    async def acquire_and_stage(
        self,
        request: RecipeDiscoveryRequest,
        search_query: RecipeSearchQuery,
        constraints: ConstraintContext = ConstraintContext(),
    ) -> ExternalAcquisitionResult:
        if not should_trigger_external_discovery(request):
            return self._fallback(request.reason.value, "LOCAL_CANDIDATES_SUFFICIENT")
        candidates: list[RecipeCandidate] = []
        staged: list[RecipeCandidate] = []
        adaptations: list[AdaptedRecipeRevision] = []
        recipe_details: dict[str, ExternalRecipeDetails] = {}
        debug: dict[str, Any] = {"trigger_reason": request.reason.value, "sources": []}
        for provider in self._providers:
            try:
                results = await provider.search(search_query)
            except ExternalDiscoveryError as exc:
                debug["sources"].append({"source_id": provider.source_id, "error": str(exc)})
                continue
            for result in results:
                policy = _policy_for(result.source_id, self._policies)
                if self._health.is_downgraded(result.source_id):
                    debug["sources"].append({"source_id": result.source_id, "error": "SOURCE_RUNTIME_DOWNGRADED"})
                    continue
                strategy = FetchStrategy(str(policy["preferred_fetch_method"]))
                target = FetchTarget(result.source_id, result.source_url, result.source_recipe_id)
                lookup = self._cache.get(result.source_id, result.source_url)
                started = time.monotonic()
                try:
                    self._circuit_breaker.allow(result.source_id)
                    self._rate_limiter.acquire(result.source_id, policy)
                    cache_has_displayable_instructions = bool(
                        lookup.entry
                        and lookup.entry.extracted.instructions
                    )
                    use_cached_extraction = bool(
                        lookup.status == CacheStatus.HIT
                        and lookup.entry
                        and (
                            not policy["instruction_display_allowed"]
                            or cache_has_displayable_instructions
                        )
                    )
                    if use_cached_extraction and lookup.entry:
                        extracted = lookup.entry.extracted
                        page = FetchedRecipePage(
                            source_id=result.source_id,
                            url=result.source_url,
                            final_url=result.source_url,
                            content="",
                            content_type="application/json" if strategy == FetchStrategy.API_FETCH else "text/html",
                            fetched_at=lookup.entry.fetched_at,
                            source_last_modified=lookup.entry.source_last_modified,
                            source_recipe_id=result.source_recipe_id,
                            strategy=strategy,
                            content_fingerprint_override=lookup.entry.content_fingerprint,
                        )
                        cache_status = CacheStatus.HIT
                    else:
                        fetcher = self._fetchers.get(strategy)
                        if fetcher is None:
                            raise ExternalDiscoveryError("EXTERNAL_RECIPE_FETCHER_NOT_CONFIGURED")
                        page = await fetcher.fetch(target)
                        extracted = self._extractor.extract(page, self._policies)
                        self._cache.put(page, extracted, policy)
                        cache_status = lookup.status
                    extracted = apply_confirmed_ingredient_grams(
                        extracted,
                        search_query.confirmed_ingredient_grams,
                    )
                    candidate = self._factory.create(page, extracted, constraints)
                    source = replace(candidate.source, cache_status=cache_status.value)
                    candidate = replace(candidate, source=source)
                    saved = self._repository.save_candidate(candidate)
                    candidates.append(saved)
                    recipe_details[saved.candidate_id] = ExternalRecipeDetails(
                        raw_ingredients=extracted.raw_ingredients,
                        instructions=extracted.instructions,
                        recipe_yield=extracted.recipe_yield,
                        cuisine=extracted.cuisine,
                        category=extracted.category,
                    )
                    if saved.status.value == "VALIDATED":
                        staged_candidate = self._repository.stage(saved.candidate_id)
                        staged.append(staged_candidate)
                        if self._portion_fitter:
                            adapted = self._portion_fitter.create_adapted_variant(staged_candidate, constraints)
                            if adapted is not None:
                                saved_adapted = self._repository.save_candidate(adapted)
                                if saved_adapted.status.value == "VALIDATED":
                                    adaptations.append(
                                        AdaptedRecipeRevision(
                                            base_candidate_id=staged_candidate.candidate_id,
                                            candidate=self._repository.stage(saved_adapted.candidate_id),
                                        )
                                    )
                    latency = (time.monotonic() - started) * 1000
                    self._circuit_breaker.success(result.source_id)
                    self._health.record(
                        result.source_id,
                        success=True,
                        structured=extracted.structured_data_present,
                        latency_ms=latency,
                    )
                    debug["sources"].append(
                        {
                            "source_id": result.source_id,
                            "fetch_strategy": strategy.value,
                            "extractor": extracted.extractor_type,
                            "json_ld": extracted.extractor_type == "JSON_LD_RECIPE",
                            "cache_status": cache_status.value,
                            "mapping_coverage": saved.evidence.mapping_count_coverage,
                            "conflicts": [code for code in saved.validation_codes if code.endswith("_CONFLICT")],
                            "latency_ms": round(latency, 3),
                        }
                    )
                except ExternalDiscoveryError as exc:
                    self._circuit_breaker.failure(result.source_id, policy)
                    self._health.record(
                        result.source_id,
                        success=False,
                        latency_ms=(time.monotonic() - started) * 1000,
                        blocked_response="FORBIDDEN" in str(exc) or "STATUS:403" in str(exc),
                    )
                    debug["sources"].append({"source_id": result.source_id, "error": str(exc)})
        if not staged:
            return self._fallback(
                request.reason.value,
                "NO_VERIFIED_EXTERNAL_RECIPE",
                debug=debug,
                candidates=candidates,
                recipe_details=recipe_details,
            )
        public = [
            "Đang tìm thêm lựa chọn phù hợp",
            "Đã đọc thành phần công thức",
            "Đã đối chiếu với dữ liệu thực phẩm",
            "Đã tính lại dinh dưỡng",
        ]
        if adaptations:
            public.append("Đã điều chỉnh khẩu phần")
        return ExternalAcquisitionResult(
            trigger_reason=request.reason.value,
            candidates=tuple(candidates),
            staged_candidates=tuple(staged),
            adaptations=tuple(adaptations),
            public_trace=tuple(public),
            debug_trace=debug,
            recipe_details=recipe_details,
        )

    @staticmethod
    def _fallback(
        trigger_reason: str,
        reason: str,
        *,
        debug: Mapping[str, Any] | None = None,
        candidates: Sequence[RecipeCandidate] = (),
        recipe_details: Mapping[str, ExternalRecipeDetails] | None = None,
    ) -> ExternalAcquisitionResult:
        return ExternalAcquisitionResult(
            trigger_reason=trigger_reason,
            candidates=tuple(candidates),
            staged_candidates=(),
            adaptations=(),
            public_trace=("Không thể xác lập công thức bên ngoài đã kiểm chứng; ưu tiên lựa chọn địa phương đã xác minh.",),
            debug_trace=debug or {"trigger_reason": trigger_reason, "fallback_reason": reason},
            fallback_reason=reason,
            recipe_details=recipe_details or {},
        )


__all__ = [
    "AdaptedRecipeRevision",
    "apply_confirmed_ingredient_grams",
    "BrowserPageTransport",
    "CacheLookup",
    "CacheStatus",
    "CachedRecipeEvidence",
    "ExternalAcquisitionResult",
    "ExternalCandidateFactory",
    "ExternalDiscoveryError",
    "ExternalRecipeAcquisitionService",
    "ExternalRecipeDetails",
    "ExtractedRecipe",
    "FetchStrategy",
    "FetchTarget",
    "FetchedRecipePage",
    "HttpRecipeFetcher",
    "JsonLdRecipeExtractor",
    "MappingCoverage",
    "PlaywrightCliEdgeTransport",
    "PlaywrightRecipeFetcher",
    "RecipeEvidenceCache",
    "RecipeFetcher",
    "RecipeRelation",
    "RecipeSearchProvider",
    "RecipeSearchQuery",
    "RecipeSearchResult",
    "RecipeVariantClassifier",
    "ControlledSearchDiscoveryProvider",
    "SourceCircuitBreaker",
    "SourceHealthTracker",
    "SourceRateLimiter",
    "StructuredRecipeExtractionService",
    "TheMealDbApiExtractor",
    "TheMealDbSearchProvider",
    "build_recipe_search_text",
    "calculate_mapping_coverage",
    "normalize_ingredient_line",
    "stable_runtime_recipe_identity",
]
