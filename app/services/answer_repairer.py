"""Answer Repair Service.

Takes the original agent answer and the per-claim verification results,
then surgically rewrites only the unsupported/contradicted portions.
Does NOT throw away the entire answer when only minor claims fail.
"""
from __future__ import annotations

import json
import logging
import re

from app.core.enums import VerificationStatus
from app.models.schemas import ClaimVerificationResult
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

_REPAIR_SYSTEM = """You are an answer repair specialist.
You receive an original agent answer and a structured JSON list of claim
verification results, each containing the claim text, its verification status,
and repair instructions.

Your job:
1. Rewrite ONLY the portions of the answer corresponding to failed claims.
2. Do NOT change verified claims.
3. Use these uncertainty phrases based on status:
   - UNSUPPORTED / UNVERIFIABLE: "I could not verify that..."
   - CONTRADICTED: "Evidence contradicts the claim that..."
   - PARTIALLY_VERIFIED: "Available information suggests..." or "According to partial evidence..."
   - INFERENCE: "This appears to suggest..." (never state as fact)
4. Do NOT invent new facts or citations.
5. If a high-impact claim cannot be supported at all, remove it from the answer.
6. Return ONLY the repaired answer text — no JSON, no markdown, no preamble."""

_REPAIR_USER = """ORIGINAL ANSWER:
{answer}

CLAIM VERIFICATION RESULTS:
{results_json}

Return the repaired answer."""

# Uncertainty language mapping
UNCERTAINTY_PHRASES = {
    VerificationStatus.VERIFIED: "According to {source}",
    VerificationStatus.PARTIALLY_VERIFIED: "Available documentation indicates",
    VerificationStatus.UNSUPPORTED: "I could not verify",
    VerificationStatus.UNVERIFIABLE: "I could not verify",
    VerificationStatus.CONTRADICTED: "Evidence contradicts the claim that",
    VerificationStatus.INFERENCE: "This suggests",
    VerificationStatus.USER_PROVIDED: "Based on the information you provided",
    VerificationStatus.OPINION: "In opinion",
    VerificationStatus.VERIFICATION_UNAVAILABLE: "I was unable to verify (service unavailable)",
}


class AnswerRepairer:
    """Repair an answer by replacing unsupported claims with appropriately-hedged language."""

    async def repair(
        self,
        original_answer: str,
        results: list[ClaimVerificationResult],
    ) -> tuple[str, list[str]]:
        """
        Returns (repaired_answer, list_of_changes).
        """
        failed = [
            r for r in results
            if r.status not in (VerificationStatus.VERIFIED, VerificationStatus.USER_PROVIDED,
                                VerificationStatus.OPINION, VerificationStatus.COMMON_KNOWLEDGE
                                if hasattr(VerificationStatus, 'COMMON_KNOWLEDGE') else VerificationStatus.VERIFIED)
        ]
        if not failed:
            return original_answer, []

        results_data = [
            {
                "claim": r.claim.text,
                "status": r.status.value,
                "repair_instruction": r.repair_instruction or _default_instruction(r.status),
                "evidence_sources": [e.source.url for e in r.evidence[:2]],
            }
            for r in results
        ]

        try:
            repaired = await llm_client.complete(
                system=_REPAIR_SYSTEM,
                user=_REPAIR_USER.format(
                    answer=original_answer,
                    results_json=json.dumps(results_data, indent=2),
                ),
            )
        except Exception as exc:
            logger.error("Answer repair failed: %s", exc)
            repaired = original_answer

        changes = [
            f"Claim '{r.claim.text[:60]}...' → status {r.status.value}"
            for r in failed
        ]
        return repaired.strip(), changes


def _default_instruction(status: VerificationStatus) -> str:
    instructions = {
        VerificationStatus.UNSUPPORTED: "Remove this claim or state it could not be verified.",
        VerificationStatus.CONTRADICTED: "Remove this claim or state that evidence contradicts it.",
        VerificationStatus.PARTIALLY_VERIFIED: "Qualify this claim with 'available evidence suggests'.",
        VerificationStatus.UNVERIFIABLE: "State that this claim cannot be verified.",
        VerificationStatus.INFERENCE: "Label this clearly as an inference, not a fact.",
        VerificationStatus.VERIFICATION_UNAVAILABLE: "State that verification was unavailable.",
    }
    return instructions.get(status, "Review and qualify this claim.")


answer_repairer = AnswerRepairer()
