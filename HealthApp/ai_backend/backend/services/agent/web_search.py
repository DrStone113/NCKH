"""Web retrieval of authoritative health knowledge.

Why this exists
---------------
The internal RAG corpus only knows what has been loaded into it. When a user
asks about a drug interaction, a 2024 guideline, or a nutrient the dataset
never covered, the model previously had two bad options: answer from parametric
memory (and risk confabulating a number) or say it doesn't know. This module
gives it a third option — go look it up in sources a nutritionist would
actually cite.

Providers
---------
Both are key-free by design, so the research project has no billing dependency
and no secret to leak:

``PubMedProvider``
    NCBI E-utilities. Peer-reviewed biomedical literature — the strongest
    citation available, and the right source for "is there evidence that X".
    Two round-trips: ``esearch`` returns PMIDs, ``esummary`` expands them.
``DuckDuckGoProvider``
    The HTML endpoint of DuckDuckGo Lite. Covers Vietnamese-language sources
    (Vinmec, Bộ Y tế, Viện Dinh dưỡng) that PubMed structurally cannot.

Trust tiering
-------------
Not every URL deserves equal weight in a health context. Results are scored
into three tiers by domain, and anything untiered is *dropped* rather than
merely ranked lower — a forum post about creatine dosing has no business
reaching a user who asked a medical question. See :data:`TRUST_TIERS`.

Failure policy
--------------
Search is an enhancement, never a dependency. Every network path returns an
empty list on failure rather than raising, so a DNS hiccup degrades the answer
instead of breaking the conversation.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"

# NCBI asks unauthenticated clients to stay at or below 3 requests/second and to
# identify themselves. Exceeding it gets the IP blocked, so the limiter below is
# not optional politeness.
PUBMED_MIN_INTERVAL_S = 0.34

USER_AGENT = "HealthApp-NCKH/1.0 (research project; contact: healthapp@example.com)"

TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)

# Hard ceiling on characters kept per result. Long abstracts otherwise crowd out
# the user's own data in the context window.
MAX_SNIPPET_CHARS = 1200


# --------------------------------------------------------------------------- #
# Trust tiers
# --------------------------------------------------------------------------- #

# tier 1 = peer-reviewed / government / international health bodies
# tier 2 = established medical institutions and reference works
# tier 3 = reputable Vietnamese-language health publishers
#
# Matching is on registrable-domain suffix, so ``www.who.int`` and
# ``apps.who.int`` both match ``who.int``.
TRUST_TIERS: dict[str, int] = {
    # --- tier 1 --------------------------------------------------------------
    "pubmed.ncbi.nlm.nih.gov": 1,
    "ncbi.nlm.nih.gov": 1,
    "who.int": 1,
    "nih.gov": 1,
    "cdc.gov": 1,
    "fda.gov": 1,
    "efsa.europa.eu": 1,
    "nice.org.uk": 1,
    "cochrane.org": 1,
    "moh.gov.vn": 1,          # Bộ Y tế
    "vncdc.gov.vn": 1,        # Cục Y tế dự phòng
    "viendinhduong.vn": 1,    # Viện Dinh dưỡng Quốc gia
    # --- tier 2 --------------------------------------------------------------
    "mayoclinic.org": 2,
    "hopkinsmedicine.org": 2,
    "health.harvard.edu": 2,
    "hsph.harvard.edu": 2,
    "clevelandclinic.org": 2,
    "nhs.uk": 2,
    "medlineplus.gov": 2,
    "eatright.org": 2,
    "diabetes.org": 2,
    "heart.org": 2,
    "acsm.org": 2,
    "examine.com": 2,
    "usda.gov": 2,
    # --- tier 3 --------------------------------------------------------------
    "vinmec.com": 3,
    "hongngochospital.vn": 3,
    "tamanhhospital.vn": 3,
    "medlatec.vn": 3,
    "suckhoedoisong.vn": 3,   # cơ quan ngôn luận của Bộ Y tế
    "nhathuoclongchau.com.vn": 3,
}

# Domains explicitly rejected regardless of ranking: user-generated content and
# commerce, where health claims are unreviewed or actively motivated.
BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "reddit.com", "quora.com", "facebook.com", "x.com", "twitter.com",
    "tiktok.com", "pinterest.com", "youtube.com", "webtretho.com",
    "shopee.vn", "lazada.vn", "tiki.vn", "amazon.com",
})


def _registrable_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def trust_tier(url: str) -> int | None:
    """Return 1/2/3 for a recognised health domain, ``None`` otherwise.

    ``None`` means "do not show this to a user asking a health question".
    Matching walks up the domain so subdomains inherit their parent's tier.
    """
    host = _registrable_domain(url)
    if not host:
        return None

    parts = host.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in BLOCKED_DOMAINS:
            return None
        if candidate in TRUST_TIERS:
            return TRUST_TIERS[candidate]
    return None


# --------------------------------------------------------------------------- #
# Result type
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class WebResult:
    """One retrieved document, normalised across providers."""

    title: str
    url: str
    snippet: str
    source: str           # "pubmed" | "web"
    tier: int
    published: str = ""   # free-form, e.g. "2023 Mar" — often unavailable
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "title": self.title,
            "url": self.url,
            "noi_dung": self.snippet,
            "nguon": self.source,
            "do_tin_cay": self.tier,
        }
        if self.published:
            payload["nam_xuat_ban"] = self.published
        return payload


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #

class _RateLimiter:
    """Minimum-interval limiter shared across concurrent callers."""

    def __init__(self, min_interval_s: float) -> None:
        self._min_interval = min_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last = time.monotonic()


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #

def _clean_text(raw: str) -> str:
    """Strip tags/entities and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return " ".join(text.split())


def _truncate(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


class PubMedProvider:
    """NCBI E-utilities client (esearch → esummary)."""

    name = "pubmed"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._limiter = _RateLimiter(PUBMED_MIN_INTERVAL_S)

    async def search(self, query: str, limit: int = 4) -> list[WebResult]:
        if not query.strip():
            return []
        try:
            pmids = await self._esearch(query, limit)
            if not pmids:
                return []
            return await self._esummary(pmids)
        except Exception as exc:  # noqa: BLE001 - search must never break a turn
            logger.warning("PubMed search failed for %r: %s", query[:60], exc)
            return []

    async def _request(self, path: str, params: dict[str, Any]) -> Any:
        await self._limiter.wait()
        url = f"{PUBMED_BASE}/{path}"
        headers = {"User-Agent": USER_AGENT}
        if self._client is not None:
            response = await self._client.get(url, params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
                response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def _esearch(self, query: str, limit: int) -> list[str]:
        payload = await self._request("esearch.fcgi", {
            "db": "pubmed",
            "term": query,
            "retmax": str(max(1, min(limit, 10))),
            "retmode": "json",
            # Relevance beats recency here: a 2015 meta-analysis outranks a
            # 2024 single-arm pilot for answering a practical question.
            "sort": "relevance",
        })
        idlist = (payload or {}).get("esearchresult", {}).get("idlist", [])
        return [str(pmid) for pmid in idlist if str(pmid).isdigit()]

    async def _esummary(self, pmids: list[str]) -> list[WebResult]:
        payload = await self._request("esummary.fcgi", {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        })
        result_block = (payload or {}).get("result", {})
        results: list[WebResult] = []
        for pmid in result_block.get("uids", []):
            entry = result_block.get(pmid)
            if not isinstance(entry, dict):
                continue
            title = _clean_text(entry.get("title", ""))
            if not title:
                continue
            journal = _clean_text(entry.get("fulljournalname") or entry.get("source", ""))
            pubdate = _clean_text(entry.get("pubdate", ""))
            authors = entry.get("authors") or []
            first_author = ""
            if isinstance(authors, list) and authors:
                first = authors[0]
                if isinstance(first, dict):
                    first_author = _clean_text(first.get("name", ""))

            snippet_parts = [title]
            if journal:
                snippet_parts.append(f"Đăng trên {journal}.")
            if first_author:
                snippet_parts.append(f"Tác giả đầu: {first_author}.")
            results.append(WebResult(
                title=title,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                snippet=_truncate(" ".join(snippet_parts)),
                source="pubmed",
                tier=1,
                published=pubdate,
                metadata={"pmid": pmid, "journal": journal},
            ))
        return results


class DuckDuckGoProvider:
    """Scrapes the DuckDuckGo HTML endpoint.

    DDG has no free official API. The HTML endpoint is stable in practice but
    is not a contract, so the parser is written defensively: an unrecognised
    layout yields zero results rather than an exception.
    """

    name = "web"

    _RESULT_RE = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
        r'.*?class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def search(self, query: str, limit: int = 4) -> list[WebResult]:
        if not query.strip():
            return []
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    DDG_ENDPOINT, data={"q": query}, headers=headers
                )
            else:
                async with httpx.AsyncClient(
                    timeout=TIMEOUT, headers=headers, follow_redirects=True
                ) as client:
                    response = await client.post(DDG_ENDPOINT, data={"q": query})
            response.raise_for_status()
            return self._parse(response.text, limit)
        except Exception as exc:  # noqa: BLE001 - search must never break a turn
            logger.warning("DuckDuckGo search failed for %r: %s", query[:60], exc)
            return []

    @classmethod
    def _parse(cls, body: str, limit: int) -> list[WebResult]:
        results: list[WebResult] = []
        for match in cls._RESULT_RE.finditer(body or ""):
            url = cls._resolve(match.group("href"))
            tier = trust_tier(url)
            if tier is None:
                # Untrusted or blocked domain — drop rather than downrank.
                continue
            title = _clean_text(match.group("title"))
            snippet = _clean_text(match.group("snippet"))
            if not title or not snippet:
                continue
            results.append(WebResult(
                title=title,
                url=url,
                snippet=_truncate(snippet),
                source="web",
                tier=tier,
            ))
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _resolve(href: str) -> str:
        """Unwrap DDG's ``/l/?uddg=<encoded>`` redirect into the real URL."""
        if not href:
            return ""
        if href.startswith("//"):
            href = "https:" + href
        if "duckduckgo.com/l/" in href or href.startswith("/l/"):
            query = urlparse(href).query
            target = parse_qs(query).get("uddg", [])
            if target:
                return unquote(target[0])
        return href


# --------------------------------------------------------------------------- #
# Aggregator
# --------------------------------------------------------------------------- #

class WebKnowledgeService:
    """Runs the providers concurrently and merges their results.

    Ordering is by trust tier first and provider position second, so a PubMed
    abstract always precedes a hospital blog post even when the blog post
    matched the query text more literally.
    """

    def __init__(
        self,
        pubmed: PubMedProvider | None = None,
        web: DuckDuckGoProvider | None = None,
    ) -> None:
        self.pubmed = pubmed if pubmed is not None else PubMedProvider()
        self.web = web if web is not None else DuckDuckGoProvider()

    async def search(
        self,
        query: str,
        limit: int = 5,
        *,
        scope: str = "all",
    ) -> list[WebResult]:
        """Search health sources for ``query``.

        Parameters
        ----------
        query:
            Natural-language query. Vietnamese is fine for the web provider;
            PubMed indexes English, so Vietnamese queries there simply return
            nothing and the web results carry the answer.
        limit:
            Maximum results returned after merging.
        scope:
            ``"research"`` for PubMed only, ``"web"`` for general sources,
            ``"all"`` (default) to query both.
        """
        if not isinstance(query, str) or not query.strip():
            return []
        limit = max(1, min(limit, 10))

        tasks = []
        if scope in ("all", "research"):
            tasks.append(self.pubmed.search(query, limit=limit))
        if scope in ("all", "web"):
            tasks.append(self.web.search(query, limit=limit))
        if not tasks:
            return []

        # ``return_exceptions`` guarantees one dead provider cannot cancel the
        # other; a partial answer beats no answer.
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[WebResult] = []
        for batch in batches:
            if isinstance(batch, BaseException):
                logger.warning("A search provider raised: %s", batch)
                continue
            merged.extend(batch)

        return self._rank(merged, limit)

    @staticmethod
    def _rank(results: Iterable[WebResult], limit: int) -> list[WebResult]:
        seen: set[str] = set()
        deduped: list[tuple[int, int, WebResult]] = []
        for position, result in enumerate(results):
            key = result.url.rstrip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append((result.tier, position, result))
        deduped.sort(key=lambda item: (item[0], item[1]))
        return [result for _tier, _pos, result in deduped[:limit]]


__all__ = [
    "BLOCKED_DOMAINS",
    "DuckDuckGoProvider",
    "MAX_SNIPPET_CHARS",
    "PubMedProvider",
    "TRUST_TIERS",
    "WebKnowledgeService",
    "WebResult",
    "trust_tier",
]
