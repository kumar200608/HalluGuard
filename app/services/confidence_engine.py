"""Confidence Engine.

Computes a structured confidence score for each claim based on
evidence quality, freshness, source authority, and cross-source agreement.

Also computes an aggregate Hallucination Risk score for the full answer.
"""
from __future__ import annotations

import logging

from app.core.enums import (
    EntailmentResult,
    HallucinationRisk,
    SourceTier,
    VerificationStatus,
)
from app.models.schemas import ClaimVerificationResult, EvidenceChunk

logger = logging.getLogger(__name__)


def _source_authority_score(chunks: list[EvidenceChunk]) -> float:
    if not chunks:
        return 0.0
    tier_scores = {
        SourceTier.TIER1_PRIMARY: 1.0,
        SourceTier.TIER2_SECONDARY: 0.75,
        SourceTier.TIER3_COMMUNITY: 0.4,
        SourceTier.TIER4_LOW_CONFIDENCE: 0.1,
    }
    return max(tier_scores.get(c.source.tier, 0.1) for c in chunks)


def _evidence_quality_score(chunks: list[EvidenceChunk]) -> float:
    supporting = [c for c in chunks if c.entailment == EntailmentResult.SUPPORTS]
    partial = [c for c in chunks if c.entailment == EntailmentResult.PARTIALLY_SUPPORTS]
    if supporting:
        return min(1.0, 0.6 + 0.2 * len(supporting))
    if partial:
        return 0.4
    return 0.0


def _cross_source_agreement(chunks: list[EvidenceChunk]) -> float:
    if len(chunks) < 2:
        return 0.5  # neutral when only one source
    supporting = sum(1 for c in chunks if c.entailment in (EntailmentResult.SUPPORTS, EntailmentResult.PARTIALLY_SUPPORTS))
    contradicting = sum(1 for c in chunks if c.entailment == EntailmentResult.CONTRADICTS)
    total = len(chunks)
    if contradicting > 0:
        return max(0.0, (supporting - contradicting) / total)
    return supporting / total


def compute_confidence(
    chunks: list[EvidenceChunk],
    temporal_valid: bool | None,
    fake_citation: bool,
    calculation_verified: bool | None,
) -> float:
    """Return a 0–1 confidence score for a single claim."""
    eq = _evidence_quality_score(chunks)
    authority = _source_authority_score(chunks)
    agreement = _cross_source_agreement(chunks)
    freshness = 1.0 if temporal_valid is True else (0.5 if temporal_valid is None else 0.2)
    citation_penalty = 0.0 if not fake_citation else 0.4
    calc_bonus = 0.1 if calculation_verified is True else 0.0

    score = (
        eq * 0.35
        + authority * 0.25
        + agreement * 0.20
        + freshness * 0.15
        + calc_bonus
        - citation_penalty
    )
    return max(0.0, min(1.0, score))


def determine_verification_status(
    chunks: list[EvidenceChunk],
    confidence: float,
    fake_citation: bool,
    requires_evidence: bool,
    calculation_verified: bool | None,
) -> VerificationStatus:
    """Map confidence and evidence signals to a VerificationStatus."""
    if fake_citation:
        return VerificationStatus.UNSUPPORTED

    if not requires_evidence:
        if calculation_verified is False:
            return VerificationStatus.CONTRADICTED
        return VerificationStatus.VERIFIED

    contradicting = [c for c in chunks if c.entailment == EntailmentResult.CONTRADICTS]
    supporting = [c for c in chunks if c.entailment in (EntailmentResult.SUPPORTS, EntailmentResult.PARTIALLY_SUPPORTS)]
    direct_support = [c for c in chunks if c.entailment == EntailmentResult.SUPPORTS]

    if contradicting and not supporting:
        return VerificationStatus.CONTRADICTED

    if not chunks or not supporting:
        return VerificationStatus.UNSUPPORTED

    if contradicting:
        return VerificationStatus.PARTIALLY_VERIFIED

    if confidence >= 0.75 and direct_support:
        return VerificationStatus.VERIFIED

    if confidence >= 0.4 and supporting:
        return VerificationStatus.PARTIALLY_VERIFIED

    return VerificationStatus.UNSUPPORTED


class HallucinationRiskEngine:
    """Aggregate risk scoring across all claims in a response."""

    def compute(self, results: list[ClaimVerificationResult]) -> tuple[float, HallucinationRisk]:
        if not results:
            return 0.0, HallucinationRisk.LOW

        unsupported = sum(1 for r in results if r.status == VerificationStatus.UNSUPPORTED)
        contradicted = sum(1 for r in results if r.status == VerificationStatus.CONTRADICTED)
        fake_citations = sum(1 for r in results if r.fake_citation_detected)
        unverified_current = sum(
            1 for r in results
            if r.claim.temporal_sensitive and r.temporal_valid is False
        )
        calc_errors = sum(
            1 for r in results
            if r.calculation_verified is False
        )

        total = len(results)
        score = (
            (unsupported / total) * 30
            + (contradicted / total) * 30
            + (fake_citations / total) * 25
            + (unverified_current / total) * 10
            + (calc_errors / total) * 5
        )

        if score >= 60:
            risk = HallucinationRisk.CRITICAL
        elif score >= 35:
            risk = HallucinationRisk.HIGH
        elif score >= 15:
            risk = HallucinationRisk.MEDIUM
        else:
            risk = HallucinationRisk.LOW

        return score, risk


risk_engine = HallucinationRiskEngine()
