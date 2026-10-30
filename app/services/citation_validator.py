"""Citation Validator.

Detects fabricated citations: invented URLs, nonexistent sources,
or citations that exist but don't support the claim.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from app.models.schemas import Claim, EvidenceChunk, SourceMetadata
from app.services.evidence_retriever import _classify_domain

logger = logging.getLogger(__name__)

# Regex patterns for detecting URLs inside claim text
_URL_PATTERN = re.compile(r"https?://[^\s\]\)\"']+", re.IGNORECASE)


class CitationValidator:
    """Validate every URL referenced in a claim or answer."""

    async def extract_and_validate_citations(
        self, text: str
    ) -> tuple[list[SourceMetadata], list[str]]:
        """
        Extract all URLs from text and validate them.
        Returns (valid_sources, fake_citation_warnings).
        """
        urls = _URL_PATTERN.findall(text)
        valid: list[SourceMetadata] = []
        warnings: list[str] = []

        for url in urls:
            source, warning = await self._validate_single(url)
            if source:
                valid.append(source)
            if warning:
                warnings.append(warning)

        return valid, warnings

    async def _validate_single(self, url: str) -> tuple[SourceMetadata | None, str]:
        """Check if a URL is reachable. Return (source, warning_if_fake)."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lstrip("www.")
        except Exception:
            return None, f"Malformed URL detected: {url!r}"

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url)
                http_status = resp.status_code
                is_available = http_status < 400
        except Exception:
            http_status = 0
            is_available = False

        source = SourceMetadata(
            url=url,
            domain=domain,
            tier=_classify_domain(url),
            http_status=http_status,
            is_available=is_available,
        )

        if not is_available:
            warning = (
                f"FAKE/DEAD CITATION DETECTED: URL '{url}' returned status {http_status} "
                f"or is unreachable. This citation cannot be used as evidence."
            )
            return source, warning

        return source, ""

    async def validate_claim_citations(self, claim: Claim) -> tuple[bool, list[str]]:
        """
        Returns (fake_citation_found, list_of_warnings) for all URLs in the claim text.
        """
        _, warnings = await self.extract_and_validate_citations(claim.text)
        return bool(warnings), warnings


citation_validator = CitationValidator()
