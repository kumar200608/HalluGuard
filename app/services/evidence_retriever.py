"""Evidence Retrieval Service.

Generates targeted search queries for each claim, retrieves web evidence,
and returns EvidenceChunk objects with source metadata.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.enums import SourceTier
from app.models.schemas import Claim, EvidenceChunk, SourceMetadata
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

# Source-tier domain patterns (non-exhaustive reference list)
_TIER1_DOMAINS = {
    "python.org", "docs.python.org",
    "developer.mozilla.org", "reactjs.org", "react.dev",
    "docs.microsoft.com", "learn.microsoft.com",
    "docs.aws.amazon.com", "cloud.google.com",
    "developer.apple.com", "docs.github.com",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "who.int", "cdc.gov", "fda.gov", "nih.gov",
    "sec.gov", "ftc.gov", "regulations.gov",
    "arxiv.org", "nature.com", "science.org",
    "openai.com", "anthropic.com",
    "w3.org", "ietf.org", "rfc-editor.org",
}
_TIER2_DOMAINS = {
    "techcrunch.com", "theverge.com", "wired.com",
    "arstechnica.com", "zdnet.com", "infoq.com",
    "hbr.org", "ft.com", "economist.com",
    "reuters.com", "apnews.com", "bbc.com", "npr.org",
}
_TIER3_DOMAINS = {
    "stackoverflow.com", "github.com",
    "reddit.com", "medium.com",
}


def _classify_domain(url: str) -> SourceTier:
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return SourceTier.TIER4_LOW_CONFIDENCE
    if domain in _TIER1_DOMAINS or any(domain.endswith("." + d) for d in _TIER1_DOMAINS):
        return SourceTier.TIER1_PRIMARY
    if domain in _TIER2_DOMAINS:
        return SourceTier.TIER2_SECONDARY
    if domain in _TIER3_DOMAINS:
        return SourceTier.TIER3_COMMUNITY
    return SourceTier.TIER4_LOW_CONFIDENCE


_QUERY_SYSTEM = """You are a search query specialist. Given a factual claim, generate 1-3
highly targeted search queries to find evidence that confirms OR refutes this claim.
Return ONLY valid JSON: {"queries": ["query1", "query2"]}"""


class EvidenceRetriever:
    """Retrieves web evidence for claims using a configured search provider."""

    def __init__(self) -> None:
        self._cache: dict[str, list[EvidenceChunk]] = {}

    async def retrieve(self, claim: Claim, max_results: int = 5) -> list[EvidenceChunk]:
        if not settings.enable_web_verification:
            return []

        cache_key = hashlib.md5(claim.text.encode()).hexdigest()
        if settings.enable_caching and cache_key in self._cache:
            logger.debug("Cache hit for claim: %s", claim.id)
            return self._cache[cache_key]

        queries = await self._generate_queries(claim)
        chunks: list[EvidenceChunk] = []

        for query in queries[:2]:  # limit parallel search cost
            results = await self._search(query, max_results)
            chunks.extend(results)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_chunks: list[EvidenceChunk] = []
        for chunk in chunks:
            url = chunk.source.url
            if url not in seen_urls:
                seen_urls.add(url)
                unique_chunks.append(chunk)

        if settings.enable_caching:
            self._cache[cache_key] = unique_chunks

        return unique_chunks

    async def _generate_queries(self, claim: Claim) -> list[str]:
        try:
            raw = await llm_client.complete(
                system=_QUERY_SYSTEM,
                user=f"Claim: {claim.text}\nClaim type: {claim.claim_type}",
            )
            raw = re.sub(r"^```(?:json)?\n?", "", raw.strip())
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            return data.get("queries", [claim.text])
        except Exception as exc:
            logger.warning("Query generation failed: %s", exc)
            return [claim.text]

    async def _search(self, query: str, max_results: int) -> list[EvidenceChunk]:
        if settings.search_provider == "tavily":
            return await self._search_tavily(query, max_results)
        # Fallback to a simple DuckDuckGo-style fetch (no API key required but limited)
        return await self._search_fallback(query, max_results)

    async def _search_tavily(self, query: str, max_results: int) -> list[EvidenceChunk]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.search_api_key,
                        "query": query,
                        "max_results": max_results,
                        "include_raw_content": False,
                        "search_depth": "advanced",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []

        chunks: list[EvidenceChunk] = []
        for r in data.get("results", []):
            url = r.get("url", "")
            source = SourceMetadata(
                url=url,
                domain=urlparse(url).netloc.lstrip("www."),
                title=r.get("title", ""),
                tier=_classify_domain(url),
                retrieved_at=datetime.now(timezone.utc),
                is_available=True,
            )
            chunks.append(EvidenceChunk(source=source, text=r.get("content", ""), relevance_score=r.get("score", 0.5)))
        return chunks

    async def _search_fallback(self, query: str, max_results: int) -> list[EvidenceChunk]:
        """Minimal fallback: returns empty list when no search provider configured."""
        logger.warning("No search provider configured — skipping web retrieval for: %s", query)
        return []

    async def validate_url(self, url: str) -> tuple[bool, int]:
        """Check if a URL is reachable and return (is_available, http_status)."""
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url)
                return resp.status_code < 400, resp.status_code
        except Exception:
            return False, 0


evidence_retriever = EvidenceRetriever()
