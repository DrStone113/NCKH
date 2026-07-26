"""Tests for web knowledge retrieval and ingestion.

No network is touched: providers are driven through injected fake HTTP clients,
so these run in CI and stay deterministic.
"""

from __future__ import annotations

import pytest

from services.agent.knowledge_ingest import (
    MAX_PERSISTED_TIER,
    MIN_CONTENT_CHARS,
    KnowledgeIngestService,
)
from services.agent.web_search import (
    BLOCKED_DOMAINS,
    DuckDuckGoProvider,
    PubMedProvider,
    WebKnowledgeService,
    WebResult,
    trust_tier,
)


# --------------------------------------------------------------------------- #
# Trust tiering
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.who.int/news-room/fact-sheets/obesity", 1),
        ("https://pubmed.ncbi.nlm.nih.gov/12345678/", 1),
        ("https://moh.gov.vn/tin-tuc", 1),
        ("https://apps.who.int/nutrition", 1),          # subdomain inherits
        ("https://www.mayoclinic.org/protein", 2),
        ("https://vinmec.com/vi/dinh-duong", 3),
        ("https://example.com/blog/keto", None),        # unknown → dropped
        ("https://reddit.com/r/fitness", None),         # blocked
        ("https://www.facebook.com/groups/gym", None),  # blocked subdomain
        ("not a url", None),
        ("", None),
    ],
)
def test_trust_tier_classification(url, expected):
    assert trust_tier(url) == expected


def test_blocked_domains_beat_any_tier_match():
    """A blocked host must never be rescued by a parent-domain tier entry."""
    for domain in ("reddit.com", "youtube.com", "shopee.vn"):
        assert domain in BLOCKED_DOMAINS
        assert trust_tier(f"https://{domain}/anything") is None


# --------------------------------------------------------------------------- #
# DuckDuckGo parsing
# --------------------------------------------------------------------------- #

_DDG_HTML = """
<div class="result">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.who.int%2Fobesity">WHO on obesity</a>
  <a class="result__snippet">Obesity is defined as abnormal fat accumulation.</a>
</div>
<div class="result">
  <a class="result__a" href="https://reddit.com/r/keto">Reddit keto thread</a>
  <a class="result__snippet">Bro just cut carbs completely.</a>
</div>
<div class="result">
  <a class="result__a" href="https://vinmec.com/dinh-duong">Dinh d&#432;&#7905;ng c&#417; b&#7843;n</a>
  <a class="result__snippet">Ch&#7871; &#273;&#7897; &#259;n c&#226;n b&#7857;ng gi&#250;p ki&#7875;m so&#225;t c&#226;n n&#7863;ng.</a>
</div>
"""


def test_ddg_parser_unwraps_redirect_and_drops_untrusted():
    results = DuckDuckGoProvider._parse(_DDG_HTML, limit=10)

    urls = [r.url for r in results]
    assert "https://www.who.int/obesity" in urls      # redirect unwrapped
    assert not any("reddit" in u for u in urls)       # blocked source dropped
    assert len(results) == 2


def test_ddg_parser_decodes_entities():
    results = DuckDuckGoProvider._parse(_DDG_HTML, limit=10)
    vinmec = [r for r in results if "vinmec" in r.url][0]
    assert "Dinh dưỡng" in vinmec.title


def test_ddg_parser_respects_limit():
    assert len(DuckDuckGoProvider._parse(_DDG_HTML, limit=1)) == 1


def test_ddg_parser_survives_unrecognised_markup():
    """DDG's HTML is not a contract; a layout change must not raise."""
    assert DuckDuckGoProvider._parse("<html><body>nothing here</body></html>", 5) == []
    assert DuckDuckGoProvider._parse("", 5) == []


def test_ddg_resolve_handles_plain_urls():
    assert DuckDuckGoProvider._resolve("https://who.int/x") == "https://who.int/x"
    assert DuckDuckGoProvider._resolve("") == ""


# --------------------------------------------------------------------------- #
# PubMed
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakePubMedClient:
    """Returns esearch then esummary payloads in order."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    async def get(self, url, params=None, headers=None):
        self.requests.append((url, params))
        return _FakeResponse(self._payloads.pop(0))


@pytest.mark.asyncio
async def test_pubmed_search_maps_summaries_to_results():
    client = _FakePubMedClient([
        {"esearchresult": {"idlist": ["111", "222"]}},
        {
            "result": {
                "uids": ["111", "222"],
                "111": {
                    "title": "Creatine and strength: a meta-analysis",
                    "fulljournalname": "J Sports Sci",
                    "pubdate": "2023 Mar",
                    "authors": [{"name": "Nguyen T"}],
                },
                "222": {
                    "title": "Protein timing revisited",
                    "source": "Nutrients",
                    "pubdate": "2021",
                    "authors": [],
                },
            }
        },
    ])
    provider = PubMedProvider(client=client)

    results = await provider.search("creatine strength", limit=2)

    assert len(results) == 2
    assert results[0].url == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert results[0].tier == 1
    assert results[0].source == "pubmed"
    assert results[0].published == "2023 Mar"
    assert "J Sports Sci" in results[0].snippet


@pytest.mark.asyncio
async def test_pubmed_returns_empty_when_nothing_found():
    client = _FakePubMedClient([{"esearchresult": {"idlist": []}}])
    assert await PubMedProvider(client=client).search("xyzzy") == []


@pytest.mark.asyncio
async def test_pubmed_network_failure_is_swallowed():
    """Search is an enhancement — a dead upstream must not break the turn."""

    class Boom:
        async def get(self, *args, **kwargs):
            raise RuntimeError("connection reset")

    assert await PubMedProvider(client=Boom()).search("protein") == []


@pytest.mark.asyncio
async def test_pubmed_ignores_blank_query():
    assert await PubMedProvider(client=_FakePubMedClient([])).search("   ") == []


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

class _StubProvider:
    def __init__(self, results):
        self._results = results

    async def search(self, query, limit=4):
        return list(self._results)


class _ExplodingProvider:
    async def search(self, query, limit=4):
        raise RuntimeError("provider down")


def _result(url, tier, source="web"):
    return WebResult(title=f"t-{url}", url=url, snippet="s" * 200,
                     source=source, tier=tier)


@pytest.mark.asyncio
async def test_results_are_ordered_by_trust_tier():
    svc = WebKnowledgeService(
        pubmed=_StubProvider([_result("https://pubmed.ncbi.nlm.nih.gov/1/", 1, "pubmed")]),
        web=_StubProvider([_result("https://vinmec.com/a", 3)]),
    )
    results = await svc.search("protein", limit=5)
    assert [r.tier for r in results] == [1, 3]


@pytest.mark.asyncio
async def test_one_dead_provider_does_not_sink_the_other():
    svc = WebKnowledgeService(
        pubmed=_ExplodingProvider(),
        web=_StubProvider([_result("https://who.int/a", 1)]),
    )
    results = await svc.search("obesity")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_duplicate_urls_are_collapsed():
    dup = _result("https://who.int/a", 1)
    svc = WebKnowledgeService(
        pubmed=_StubProvider([dup]),
        web=_StubProvider([_result("https://who.int/a/", 1)]),  # trailing slash
    )
    assert len(await svc.search("x")) == 1


@pytest.mark.asyncio
async def test_scope_research_skips_the_web_provider():
    web = _StubProvider([_result("https://vinmec.com/a", 3)])
    svc = WebKnowledgeService(
        pubmed=_StubProvider([_result("https://pubmed.ncbi.nlm.nih.gov/1/", 1, "pubmed")]),
        web=web,
    )
    results = await svc.search("x", scope="research")
    assert all(r.source == "pubmed" for r in results)


@pytest.mark.asyncio
async def test_blank_query_short_circuits():
    svc = WebKnowledgeService(pubmed=_ExplodingProvider(), web=_ExplodingProvider())
    assert await svc.search("  ") == []


# --------------------------------------------------------------------------- #
# Ingestion eligibility
# --------------------------------------------------------------------------- #

def test_tier_three_sources_are_not_persisted():
    """Good enough to quote with a visible URL; not good enough to memorise."""
    svc = KnowledgeIngestService(db_session=None)
    tier3 = WebResult("t", "https://vinmec.com/a", "x" * 500, "web", 3)
    assert svc._is_eligible(tier3) is False


def test_tier_one_and_two_are_persisted():
    svc = KnowledgeIngestService(db_session=None)
    for tier in (1, MAX_PERSISTED_TIER):
        r = WebResult("t", f"https://who.int/{tier}", "x" * 500, "web", tier)
        assert svc._is_eligible(r) is True


def test_headline_length_snippets_are_rejected():
    svc = KnowledgeIngestService(db_session=None)
    short = WebResult("t", "https://who.int/a", "x" * (MIN_CONTENT_CHARS - 1), "web", 1)
    assert svc._is_eligible(short) is False


def test_result_without_url_is_rejected():
    svc = KnowledgeIngestService(db_session=None)
    assert svc._is_eligible(WebResult("t", "", "x" * 500, "web", 1)) is False


@pytest.mark.asyncio
async def test_ingest_with_no_session_is_a_noop():
    svc = KnowledgeIngestService(db_session=None)
    assert await svc.ingest([_result("https://who.int/a", 1)]) == 0


@pytest.mark.asyncio
async def test_ingest_of_empty_list_is_a_noop():
    assert await KnowledgeIngestService(db_session=object()).ingest([]) == 0
