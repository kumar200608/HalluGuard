"""Final Answer Gate.

Evaluates the full verification report and makes the ALLOW / REWRITE /
BLOCK_AND_REGENERATE / RETURN_UNCERTAIN_ANSWER decision.
This is the last checkpoint before a response reaches the user.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.core.enums import (
    GateDecision,
    HallucinationRisk,
    VerificationStatus,
)
from app.models.schemas import ClaimVerificationResult

logger = logging.getLogger(__name__)


def _count_by_status(results: list[ClaimVerificationResult], status: VerificationStatus) -> int:
    return sum(1 for r in results if r.status == status)


def _has_high_risk_unsupported(results: list[ClaimVerificationResult]) -> bool:
    return any(
        r.status in (VerificationStatus.UNSUPPORTED, VerificationStatus.CONTRADICTED)
        and r.claim.risk_level in (HallucinationRisk.HIGH, HallucinationRisk.CRITICAL)
        for r in results
    )


def _any_fake_citation(results: list[ClaimVerificationResult]) -> bool:
    return any(r.fake_citation_detected for r in results)


def _any_contradicted(results: list[ClaimVerificationResult]) -> bool:
    return any(r.status == VerificationStatus.CONTRADICTED for r in results)


def _all_important_verified(results: list[ClaimVerificationResult]) -> bool:
    for r in results:
        if not r.claim.requires_external_evidence:
            continue
        if r.status not in (
            VerificationStatus.VERIFIED,
            VerificationStatus.PARTIALLY_VERIFIED,
            VerificationStatus.USER_PROVIDED,
        ):
            return False
    return True


class FinalAnswerGate:
    """Decide whether the verified answer may be returned to the user."""

    def evaluate(
        self,
        results: list[ClaimVerificationResult],
        overall_risk: HallucinationRisk,
    ) -> GateDecision:
        """
        Gate rules (applied in priority order):
        1. Fake citations → BLOCK_AND_REGENERATE
        2. Contradicted high-risk claims → REGENERATE_WITH_CONFLICT_DISCLOSURE
        3. Critical hallucination risk → BLOCK_AND_REGENERATE
        4. High-risk unsupported claims → BLOCK_AND_REGENERATE
        5. Minor unsupported claims only → REWRITE
        6. Evidence unavailable entirely → RETURN_UNCERTAIN_ANSWER
        7. All important claims verified → ALLOW
        8. Default → REWRITE
        """
        if _any_fake_citation(results):
            logger.warning("Gate: fake citation detected → BLOCK_AND_REGENERATE")
            return GateDecision.BLOCK_AND_REGENERATE

        if _any_contradicted(results) and _has_high_risk_unsupported(results):
            logger.warning("Gate: contradicted + high-risk unsupported → REGENERATE_WITH_CONFLICT_DISCLOSURE")
            return GateDecision.REGENERATE_WITH_CONFLICT_DISCLOSURE

        if overall_risk == HallucinationRisk.CRITICAL:
            logger.warning("Gate: CRITICAL risk → BLOCK_AND_REGENERATE")
            return GateDecision.BLOCK_AND_REGENERATE

        if _has_high_risk_unsupported(results):
            logger.warning("Gate: high-risk unsupported claims → BLOCK_AND_REGENERATE")
            return GateDecision.BLOCK_AND_REGENERATE

        verification_unavailable = all(
            r.status == VerificationStatus.VERIFICATION_UNAVAILABLE
            for r in results
            if r.claim.requires_external_evidence
        ) and any(r.claim.requires_external_evidence for r in results)
        if verification_unavailable:
            logger.warning("Gate: verification unavailable → RETURN_UNCERTAIN_ANSWER")
            return GateDecision.RETURN_UNCERTAIN_ANSWER

        if _all_important_verified(results):
            unsupported_minor = _count_by_status(results, VerificationStatus.UNSUPPORTED)
            if unsupported_minor == 0:
                logger.info("Gate: all claims verified → ALLOW")
                return GateDecision.ALLOW
            logger.info("Gate: minor unsupported claims → REWRITE")
            return GateDecision.REWRITE

        if overall_risk == HallucinationRisk.HIGH:
            return GateDecision.BLOCK_AND_REGENERATE

        logger.info("Gate: default → REWRITE")
        return GateDecision.REWRITE


answer_gate = FinalAnswerGate()
