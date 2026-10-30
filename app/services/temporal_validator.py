"""Temporal Validator.

Checks whether time-sensitive claims are still current and whether the
evidence used to support them is fresh enough.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.models.schemas import Claim, EvidenceChunk

logger = logging.getLogger(__name__)

FRESHNESS_LIMIT = timedelta(days=settings.source_freshness_limit_days)

# Triggers that indicate a query needs current/live information
CURRENT_TRIGGERS = {
    "latest", "today", "current", "now", "recent", "available",
    "price", "status", "version", "newest", "right now",
    "at the moment", "currently", "present", "live",
}


def _is_stale(dt: Optional[datetime]) -> bool:
    if dt is None:
        return False  # unknown date — cannot determine freshness
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) > FRESHNESS_LIMIT


class TemporalValidator:
    """Validates temporal freshness of claims and their evidence."""

    def requires_fresh_evidence(self, query: str, claim: Claim) -> bool:
        """Return True if the query/claim demands up-to-date information."""
        text = (query + " " + claim.text).lower()
        return any(trigger in text for trigger in CURRENT_TRIGGERS) or claim.temporal_sensitive

    def validate_evidence_freshness(self, chunks: list[EvidenceChunk]) -> list[str]:
        """Return list of staleness warnings for the evidence set."""
        warnings: list[str] = []
        for chunk in chunks:
            pub = chunk.source.publication_date or chunk.source.last_updated
            if _is_stale(pub):
                age_days = (datetime.now(timezone.utc) - pub.replace(tzinfo=timezone.utc)).days if pub else -1
                warnings.append(
                    f"Source '{chunk.source.url}' may be stale (published ~{age_days} days ago, "
                    f"freshness limit is {settings.source_freshness_limit_days} days)."
                )
        return warnings

    def validate_claim_temporality(
        self,
        claim: Claim,
        chunks: list[EvidenceChunk],
        query: str,
    ) -> tuple[Optional[bool], list[str]]:
        """
        Returns (temporal_valid, list_of_warnings).
        temporal_valid = None means not applicable.
        """
        if not self.requires_fresh_evidence(query, claim):
            return None, []

        freshness_warnings = self.validate_evidence_freshness(chunks)
        if not chunks:
            return False, [f"Claim '{claim.text[:80]}' requires current evidence but none was found."]

        all_stale = all(
            _is_stale(c.source.publication_date or c.source.last_updated)
            for c in chunks
            if (c.source.publication_date or c.source.last_updated)
        )
        if all_stale and freshness_warnings:
            return False, freshness_warnings

        return True, freshness_warnings


temporal_validator = TemporalValidator()
